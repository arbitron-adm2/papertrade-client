# Architecture — papertrade-client

## Target overview

**papertrade.xyz** is a paper-trading (simulated) perpetuals exchange built on top of Hyperliquid's HyperEVM (chainId 999). Users open synthetic leveraged positions in BTC and ETH with USDC collateral. Everything is on-chain via smart contracts; the frontend signs EIP-712 typed messages locally and submits them to the exchange API.

## Service topology

```
Browser / Python client
  │
  ├─→  exchange.papertrade.xyz   (HTTPS, REST)
  │      /query/…   → read-only data queries
  │      /state/…   → real-time global state
  │      /intents   → EIP-712 signed actions (write)
  │      /telemetry → client-side error reporting
  │
  ├─→  stream.papertrade.xyz/connection/websocket  (WSS, Centrifuge)
  │      Real-time streaming: prices, positions, trading state
  │
  ├─→  sign.papertrade.xyz   (iFrame, browser only)
  │      Secure key custody iframe — irrelevant to Python client
  │      (Python client signs directly with local private key)
  │
  └─→  api.hyperliquid.xyz   (HTTPS, external)
         /info     → HyperCore account state
         /exchange → HyperCore signed actions (deposits)
```

## Auth classification: Tier 0 (reads) / Tier 5 (writes)

### Read endpoints — Tier 0

All `/query/…` and `/state/…` endpoints work with no credentials at all. The browser
sends `credentials: 'same-origin'` but this is a no-op for Python clients making
cross-origin requests. No cookie, token, or API key is required.

**Proof**: 19 read endpoints confirmed returning HTTP 200 from curl / Python httpx
with only `Accept: application/json` and `User-Agent` headers.

### Write endpoints — Tier 5 (self-derived EIP-712)

Every mutation is submitted as a signed EIP-712 "intent". The client:
1. Constructs the typed data message (fields vary by action type)
2. Hashes it with the EIP-712 domain separator
3. Signs with secp256k1 ECDSA (local private key, no server round-trip)
4. POSTs `{action, signed: {…fields, r, s, v}}` to `/intents`

No server secret, no API key, no bearer token. The wallet IS the credential.
The signature scheme is the same as standard Ethereum transactions.

## Intent architecture

```
User Action
  │
  ├─ main_wallet signs:
  │    RegisterSessionKey  (once, 30-day validity)
  │    WithdrawToCore
  │    Stake / Unstake / Claim  (PAPER token)
  │    CancelIntent
  │
  └─ session_key signs:  (defaults to main_wallet if not separate)
       OpenPosition
       Close
```

The session key separation is a UX convenience (the browser keeps the session key
in an iframe at sign.papertrade.xyz so MetaMask pop-ups aren't needed for every
trade). Python clients can use one key for both roles.

## EIP-712 domains

| Domain | name | version | chainId | verifyingContract |
|---|---|---|---|---|
| exchange | `"String"` | `"1"` | 999 | `0x6cd566…` |
| paperStaking | `"PaperStaking"` | `"1"` | 999 | `0xaad6c7…` |
| cancellation | `"PaperTrade Intent Cancel"` | `"2"` | 999 | `0x6cd566…` |

Note: the exchange domain name is literally the string `"String"` — unusual but
that's what the contract was deployed with (extracted from `typed-data-B0hqt2-N.js`).

## Nonce management

Nonces are **client-managed** (stored in the browser's localStorage under the key
`papertrade.clientNonce.v1:{chainId}:{verifyingContract}:{type}:{userAddress}`).
The server only enforces that each nonce hasn't been used before — it does NOT
enforce strict monotonicity. Using `int(time.time() * 1000)` as the seed provides
uniqueness across process restarts.

## Size encoding

All amounts use 18 internal decimal places regardless of the collateral token's
external precision:

| Amount | Formula |
|---|---|
| $100 USDC margin | `100 * 10^18 = 100000000000000000000` |
| 50 USDC withdrawal | `50 * 10^18 = 50000000000000000000` |
| 100 PAPER stake | `100 * 10^18 = 100000000000000000000` |

## Rate limits

No HTTP 429 observed in a 20-request burst at 50ms intervals on public endpoints.
Cloudflare is the edge layer; the server doesn't return `Retry-After` headers
on normal traffic. The client uses a conservative 200ms gap (5 req/s) and
implements exponential backoff starting at 500ms on any 429.

## HTTP transport

```
Transport
  ├─ /query/…  → "query" rate-limit bucket (per query-api-client.js)
  ├─ /state/…  → "edge" rate-limit bucket
  ├─ 3 retries with exponential backoff (0.5s, 1.5s, 4.0s)
  ├─ 35s timeout per request
  └─ X-Papertrade-Build header (version identifier, ignored by server on errors)
```

## Contract addresses (HyperEVM chainId 999)

| Contract | Address |
|---|---|
| Exchange | `0x6cd5661646289fb6e65ea5c032310fded797d0a2` |
| PAPER token | `0xe40f17915daa230324030003a197cdaef2261c0e` |
| PaperStaking | `0xaad6c7b0cc3014fc80ffedae0ed7ce5967b0f016` |
| DepositProxyFactory | `0x1629b7d46bef6e13ff754174fc9f32dea309b38f` |
| Collateral (USDC) | `0x6b9e773128f453f5c2c60935ee2de2cbc5390a24` |

## Source evidence

All findings are extracted from live JS bundles downloaded from
`https://exchange.papertrade.xyz/assets/` on 2026-10-10:

| Bundle | Evidence |
|---|---|
| `typed-data-B0hqt2-N.js` | All EIP-712 types and domain configs |
| `deployment-C3VOxZVa.js` | Contract addresses, chain config, RPC URLs |
| `index-Tu4xzYeT.js` | All `Tt()` GET calls, `Ob()` POST logic, intent submission |
| `execution-CNs4GYCc.js` | Hyperliquid API calls, funding flows |
| `query-api-client-DGxZQjmt.js` | Rate-limit bucket logic (query vs edge) |
