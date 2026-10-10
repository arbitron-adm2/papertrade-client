"""
Constants extracted from exchange.papertrade.xyz JS bundles.

All addresses are checksummed where possible; the EIP-712 signing
code lower-cases them before hashing, matching the site's behaviour.
"""

# ── Network ───────────────────────────────────────────────────────────
CHAIN_ID        = 999               # HyperEVM Mainnet
CHAIN_NAME      = "HyperEVM Mainnet"
GENESIS_MS      = 1_791_326_520_000 # genesisMs from deployment bundle

# ── Service origins ───────────────────────────────────────────────────
EXCHANGE_BASE   = "https://exchange.papertrade.xyz"
STREAM_WS       = "wss://stream.papertrade.xyz/connection/websocket"
HL_INFO_API     = "https://api.hyperliquid.xyz/info"
HL_WS_API       = "wss://api.hyperliquid.xyz/ws"

# ── Contracts ─────────────────────────────────────────────────────────
EXCHANGE_CONTRACT      = "0x6cd5661646289fb6e65ea5c032310fded797d0a2"
PAPER_TOKEN            = "0xe40f17915daa230324030003a197cdaef2261c0e"
PAPER_STAKING          = "0xaad6c7b0cc3014fc80ffedae0ed7ce5967b0f016"
DEPOSIT_PROXY_FACTORY  = "0x1629b7d46bef6e13ff754174fc9f32dea309b38f"
COLLATERAL_ADDRESS     = "0x6b9e773128f453f5c2c60935ee2de2cbc5390a24"
COLLATERAL_DECIMALS    = 6          # USDC

# ── Fee address (zero address, constant from JS bundle `rl`) ──────────
FEE_ADDRESS = "0x0000000000000000000000000000000000000000"

# ── Instruments ──────────────────────────────────────────────────────
INSTRUMENTS = {
    0: {"name": "BTC", "assetIndex": 0, "priceScale": 10},
    1: {"name": "ETH", "assetIndex": 1, "priceScale": 100},
}
INSTRUMENT_BY_NAME = {v["name"]: k for k, v in INSTRUMENTS.items()}

# ── Internal unit: 10^18 = 1 USDC of margin/collateral ───────────────
COLLATERAL_SCALE = 10 ** 18   # 1 USDC margin = 10^18 raw units
PAPER_SCALE      = 10 ** 18   # PAPER token uses 18 decimals

# ── EIP-712 domain templates  (extracted from typed-data-B0hqt2-N.js) ─
DOMAIN_EXCHANGE = {
    "name": "String",
    "version": "1",
    "chainId": CHAIN_ID,
    "verifyingContract": EXCHANGE_CONTRACT,
}
DOMAIN_PAPER_STAKING = {
    "name": "PaperStaking",
    "version": "1",
    "chainId": CHAIN_ID,
    "verifyingContract": PAPER_STAKING,
}
DOMAIN_CANCELLATION = {
    "name": "PaperTrade Intent Cancel",
    "version": "2",
    "chainId": CHAIN_ID,
    "verifyingContract": EXCHANGE_CONTRACT,
}

# ── EIP-712 message types (extracted from typed-data-B0hqt2-N.js) ────
INTENT_TYPES: dict[str, list[dict]] = {
    "RegisterSessionKey": [
        {"name": "user",       "type": "address"},
        {"name": "key",        "type": "address"},
        {"name": "expiry",     "type": "uint64"},
        {"name": "feeAddress", "type": "address"},
        {"name": "nonce",      "type": "uint256"},
        {"name": "deadline",   "type": "uint64"},
    ],
    "OpenPosition": [
        {"name": "user",         "type": "address"},
        {"name": "instrumentId", "type": "uint32"},
        {"name": "isLong",       "type": "bool"},
        {"name": "size",         "type": "uint128"},
        {"name": "leverage",     "type": "uint32"},
        {"name": "useDebt",      "type": "bool"},
        {"name": "nonce",        "type": "uint256"},
        {"name": "deadline",     "type": "uint64"},
    ],
    "Close": [
        {"name": "user",        "type": "address"},
        {"name": "positionIds", "type": "uint256[]"},
        {"name": "nonce",       "type": "uint256"},
        {"name": "deadline",    "type": "uint64"},
    ],
    "WithdrawToCore": [
        {"name": "user",     "type": "address"},
        {"name": "amount",   "type": "uint256"},
        {"name": "nonce",    "type": "uint256"},
        {"name": "deadline", "type": "uint64"},
    ],
    "Stake": [
        {"name": "user",     "type": "address"},
        {"name": "amount",   "type": "uint256"},
        {"name": "nonce",    "type": "uint256"},
        {"name": "deadline", "type": "uint64"},
    ],
    "Unstake": [
        {"name": "user",     "type": "address"},
        {"name": "amount",   "type": "uint256"},
        {"name": "nonce",    "type": "uint256"},
        {"name": "deadline", "type": "uint64"},
    ],
    "Claim": [
        {"name": "user",     "type": "address"},
        {"name": "nonce",    "type": "uint256"},
        {"name": "deadline", "type": "uint64"},
    ],
    "CancelIntent": [
        {"name": "user",      "type": "address"},
        {"name": "intentId",  "type": "bytes32"},
        {"name": "deadline",  "type": "uint256"},
    ],
}

# ── Domain selector per intent type ──────────────────────────────────
INTENT_DOMAIN: dict[str, dict] = {
    "RegisterSessionKey": DOMAIN_EXCHANGE,
    "OpenPosition":       DOMAIN_EXCHANGE,
    "Close":              DOMAIN_EXCHANGE,
    "WithdrawToCore":     DOMAIN_EXCHANGE,
    "Stake":              DOMAIN_PAPER_STAKING,
    "Unstake":            DOMAIN_PAPER_STAKING,
    "Claim":              DOMAIN_PAPER_STAKING,
    "CancelIntent":       DOMAIN_CANCELLATION,
}

# ── Action name on the /intents endpoint per intent type ─────────────
INTENT_ACTION: dict[str, str] = {
    "RegisterSessionKey": "registerSessionKey",
    "OpenPosition":       "openPosition",
    "Close":              "closePositions",
    "WithdrawToCore":     "withdrawToCore",
    "Stake":              "paperStake",
    "Unstake":            "paperUnstake",
    "Claim":              "paperClaim",
}

# ── Session-key lifetime: 30 days in seconds ──────────────────────────
SESSION_KEY_LIFETIME_S = 30 * 24 * 3600   # 2_592_000

# ── Intent deadline: current Unix seconds + 3600 ─────────────────────
INTENT_DEADLINE_OFFSET_S = 3_600

# ── Rate limit buckets (from query-api-client bundle) ────────────────
# /query/... → "query" bucket; other / paths → "edge" bucket
RATE_LIMIT_RETRY_DELAYS = [1.0, 2.0, 4.0]   # seconds, then give up

# ── Leaderboard window options ────────────────────────────────────────
LEADERBOARD_WINDOWS = ["24h", "7d", "30d", "all"]

# ── Protocol history intervals (confirmed: 1h and 1d only; 1w/all return 400) ──
HISTORY_INTERVALS = ["1h", "1d"]

# ── Liquidation-map range options ─────────────────────────────────────
LIQ_MAP_RANGES = ["0.1", "0.25", "0.5", "1", "2", "5", "10", "25"]
