# papertrade-client

**Unofficial, reverse-engineered Python client and CLI for [papertrade.xyz](https://papertrade.xyz)** — synthetic perpetuals on Hyperliquid.

> ⚠️ **DISCLAIMER**: This is an unofficial, reconstructed client. It is not affiliated with, endorsed by, or supported by PaperTrade or its developers. The internal API observed here is undocumented and may change at any time without notice. Use is subject to PaperTrade's Terms of Service — the ToS risk is the user's to own. This client may break if the site's API changes.

---

## What this client covers

| Surface | Coverage |
|---|---|
| All public `/query/…` read endpoints | ✅ Confirmed live |
| All `/state/…` real-time endpoints | ✅ Confirmed live |
| EIP-712 intent signing (all 7 action types) | ✅ Signing confirmed locally |
| POST `/intents` write operations | ⚠️ Dry-run confirmed; live submit requires funded HyperEVM account |
| WebSocket stream (`stream.papertrade.xyz`) | ❌ Not implemented (aspirational per skill disclaimer) |
| Mobile UI endpoints | ❌ Not cataloged |

See [`endpoint_inventory.json`](./endpoint_inventory.json) for the full catalog.

---

## Auth tier

| Reads | Writes |
|---|---|
| **Tier 0** — no auth, no key, no token | **Tier 5** — self-derived EIP-712 (wallet signs locally, no server secret) |

All read endpoints work anonymously. Write operations require a wallet private key; the EIP-712 structured data is signed client-side and submitted to `POST /intents`. No API key is required — the site ships no secret to the browser.

---

## Measured rate limits

- **No 429 observed** in a 20-request burst at 50ms intervals on public endpoints.
- Cloudflare sits in front; no `Retry-After` headers were returned.
- **Client default**: 200ms between requests (5 req/s) — conservative and polite.
- `/intents` write endpoints: not burst-tested (polite policy; shared endpoint).

---

## Install

```bash
git clone …
cd papertrade-client
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# or: pip install -e .
```

---

## Wallet setup (OKX-compatible)

PaperTrade uses standard EVM wallets (secp256k1, EIP-712). OKX Wallet uses BIP-39 / BIP-44 `m/44'/60'/0'/0/0` — the same path as MetaMask.

**Generate a new wallet:**
```bash
python cli.py wallet-new --output wallet.json
```
This creates `wallet.json` with permissions `0600`. The file contains the mnemonic and private key — **store it securely, never commit it**.

**Use an existing OKX wallet:**
```bash
export PAPERTRADE_PRIVATE_KEY=0x<your_hex_private_key>
# or
python cli.py wallet-new --output wallet.json   # already done
```

**Register the session key (required before trading):**
```bash
python cli.py register-session-key --wallet-file wallet.json --write
```
This signs a `RegisterSessionKey` EIP-712 intent with your main wallet and submits it to the exchange. The session key is valid for 30 days. You need USDC collateral on HyperEVM first.

---

## CLI usage

### Read commands (no wallet needed)

```bash
# Health check
python cli.py ready

# Protocol overview
python cli.py protocol-summary
python cli.py protocol-history --interval 1h
python cli.py protocol-trades
python cli.py protocol-paper
python cli.py protocol-queue

# Market data
python cli.py liquidation-map --instrument BTC --range 1
python cli.py trading-state
python cli.py position-topology
python cli.py house-current
python cli.py house-delta --coin BTC

# Account data (any public address)
python cli.py account-funding 0x<address>
python cli.py account-trades 0x<address>
python cli.py account-queue-ring 0x<address>
python cli.py account-portfolio 0x<address> --range all
python cli.py account-badges 0x<address>

# Leaderboard
python cli.py leaderboard --window 24h --sort-key totalWindowedPnl
```

### Write commands (wallet required, `--write` flag required)

```bash
# Register session key (once, before trading)
python cli.py register-session-key -w wallet.json --write

# Open a position (dry run — shows signed payload without submitting)
python cli.py open-position --instrument BTC --long --margin 100 --leverage 10

# Actually submit (requires --write)
python cli.py open-position --instrument BTC --long --margin 100 --leverage 10 --write

# Close positions by ID
python cli.py close-positions 123 456 --write

# PAPER token operations
python cli.py stake --amount 100 --write
python cli.py unstake --amount 50 --write
python cli.py claim --write

# Withdraw USDC to HyperCore
python cli.py withdraw --amount 50 --write

# Cancel a queued intent
python cli.py cancel-intent 0x<intent_id_bytes32> --write
```

---

## Python API

```python
from papertrade import PaperTradeClient, generate_okx_wallet, wallet_from_private_key

# Read-only (no wallet needed)
with PaperTradeClient() as c:
    print(c.read.protocol_summary())
    print(c.read.liquidation_map(0, "1"))   # BTC, ±1%
    print(c.read.account_trades("0x…"))

# With trading
wallet = wallet_from_private_key("0x…")  # or load_wallet("wallet.json")
with PaperTradeClient(wallet=wallet) as c:
    # Dry-run (no network submission)
    payload = c.write.open_position("BTC", is_long=True, margin_usdc=100, leverage=10, dry_run=True)
    print(payload)

    # Live submission (requires funded account + registered session key)
    result = c.write.open_position("BTC", is_long=True, margin_usdc=100, leverage=10, dry_run=False)
    print(result["intentId"])
```

---

## Position sizing

| Concept | Formula |
|---|---|
| Margin (USDC) | `margin_usdc` parameter |
| Raw size field | `margin_usdc × 10^18` |
| Minimum margin | $10 USDC (`10 × 10^18` raw) |
| Minimum notional | $10,000 USDC (`10,000 × 10^18` raw) |
| Example: $100 margin, 10× leverage | Notional = $1,000 (valid: ≥ $10,000 required!) |

⚠️ Note: with minimum margin $10 and minimum notional $10,000, you need at least **1000× leverage** to open the smallest valid position, OR at least **$10,000 USDC margin at 1×**. The minimum practical position is $10 margin at 1000× = $10,000 notional.

---

## Running tests

```bash
source .venv/bin/activate

# All read + signing tests (no wallet needed):
pytest tests/test_live.py -v

# Enable live write tests (requires funded wallet):
PAPERTRADE_PRIVATE_KEY=0x… PAPERTRADE_RUN_WRITES=1 pytest tests/test_live.py -v -k write
```

---

## Architecture

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the full technical design.

---

## What's explicitly missing / unconfirmed

- **Live write tests**: EIP-712 signing is confirmed correct locally; server submission requires a funded HyperEVM account with USDC collateral.
- **Leaderboard with real data**: Returns 400 for unregistered addresses; needs a registered account.
- **WebSocket streaming**: Not implemented. The Centrifuge protocol at `wss://stream.papertrade.xyz` is documented in the inventory but not built.
- **Portfolio history (short ranges)**: 24h/7d/30d return 400 for the zero address; need an address with active trading history.
- **Protocol history 1w/all**: Server returns 400; only `1h` and `1d` confirmed working.
- **Cross-chain deposits**: The Across bridge and Circle CCTP flows require chain-specific setup not implemented here.
