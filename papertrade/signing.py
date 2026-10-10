"""
EIP-712 signed-intent builder for PaperTrade.

Every write operation on the exchange is an "intent" — an EIP-712
typed-data message signed by the user's wallet (or session key) and
submitted to POST /intents.  This module:

  1. Normalises typed-data fields to the exact string representations
     the server expects (uint* → decimal string, bool kept, address
     lower-cased, bytes32 lower-cased).
  2. Signs the hash with eth_account's `sign_typed_data`.
  3. Extracts r / s / v in the format the server expects
     (v as "27" or "28", r/s as lowercase "0x…" hex strings).
  4. Returns the full signed payload ready for POST /intents.

Auth tier: **Tier 0 for reads / Tier 5 (self-derived EIP-712) for writes**.
No server secret is needed; the wallet signs locally.
"""
from __future__ import annotations

import time
from typing import Any

from eth_account import Account
from eth_account.signers.local import LocalAccount

from .constants import (
    INTENT_DOMAIN,
    INTENT_TYPES,
    FEE_ADDRESS,
    INTENT_DEADLINE_OFFSET_S,
    SESSION_KEY_LIFETIME_S,
)
from .exceptions import SigningError


# ── Nonce management (client-side, monotonically increasing) ──────────
_nonce_counter: dict[str, int] = {}


def next_nonce(key: str = "default") -> int:
    """
    Return a fresh uint256 nonce that is monotonically increasing.

    Uses millisecond timestamps as the initial seed so nonces are
    never re-used across process restarts.  The server only enforces
    that each (user, verifyingContract, type) tuple has a strictly
    increasing nonce, so timestamp * 1000 + counter is safe.
    """
    ts_ms = int(time.time() * 1_000)
    prev = _nonce_counter.get(key, 0)
    nonce = max(ts_ms, prev + 1)
    _nonce_counter[key] = nonce
    return nonce


def deadline() -> int:
    """Return an intent deadline: now + 3600 seconds (1 hour)."""
    return int(time.time()) + INTENT_DEADLINE_OFFSET_S


def session_expiry() -> int:
    """Return a session-key expiry: now + 30 days (seconds)."""
    return int(time.time()) + SESSION_KEY_LIFETIME_S


# ── Type normaliser (matches JS `ib()` function) ──────────────────────
def _normalise(soltype: str, value: Any) -> Any:
    """Convert a Python value to the form expected by eth_account sign_typed_data."""
    if soltype == "bool":
        return bool(value)
    if soltype == "address" or soltype.startswith("bytes"):
        return str(value).lower()
    if soltype == "uint256[]":
        return [int(v) for v in value]
    if soltype.startswith("uint") or soltype.startswith("int"):
        return int(value)
    return value


def _str_for_wire(soltype: str, value: Any) -> Any:
    """Convert to the string form sent in the POST body (matching JS `ib()`)."""
    if soltype == "bool":
        return bool(value)
    if soltype == "address" or soltype.startswith("bytes"):
        return str(value).lower()
    if soltype == "uint256[]":
        return [str(int(v)) for v in value]
    if soltype.startswith("uint") or soltype.startswith("int"):
        return str(int(value))
    return value


def sign_intent(
    signer: LocalAccount,
    intent_type: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    """
    Sign an EIP-712 typed intent and return the wire-ready signed payload.

    Parameters
    ----------
    signer:      The LocalAccount that signs (wallet or session key).
    intent_type: One of the INTENT_TYPES keys, e.g. "OpenPosition".
    fields:      Dict with the message fields (not including r/s/v).

    Returns
    -------
    A dict ready to POST as the ``signed`` field of an intent body.
    Contains all message fields as strings/bools, plus 'r', 's', 'v'.
    """
    if intent_type not in INTENT_TYPES:
        raise SigningError(f"Unknown intent type: {intent_type!r}")

    type_fields = INTENT_TYPES[intent_type]
    domain = INTENT_DOMAIN[intent_type]

    # Build the normalised message for hashing
    message: dict[str, Any] = {}
    for fdef in type_fields:
        fname = fdef["name"]
        ftype = fdef["name"]
        sol_type = fdef["type"]
        if fname not in fields:
            raise SigningError(f"Missing field {fname!r} for {intent_type}")
        message[fname] = _normalise(sol_type, fields[fname])

    # Build EIP-712 structured data
    structured = {
        "types": {
            "EIP712Domain": [
                {"name": "name",              "type": "string"},
                {"name": "version",           "type": "string"},
                {"name": "chainId",           "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            intent_type: type_fields,
        },
        "domain": domain,
        "primaryType": intent_type,
        "message": message,
    }

    try:
        signed = signer.sign_typed_data(full_message=structured)
    except Exception as exc:
        raise SigningError(f"EIP-712 signing failed: {exc}") from exc

    # Extract r/s/v using direct attributes (avoids 0x prefix confusion)
    v_raw  = signed.v
    r_hex  = "0x" + hex(signed.r)[2:].zfill(64).lower()
    s_hex  = "0x" + hex(signed.s)[2:].zfill(64).lower()
    # Normalise v: Ethereum uses 27/28; eth_account sometimes returns 0/1
    v_norm = v_raw if v_raw in (27, 28) else 27 + (v_raw % 2)
    v_str  = str(v_norm)

    # Build the wire payload: all message fields as strings + r/s/v
    wire: dict[str, Any] = {}
    for fdef in type_fields:
        fname   = fdef["name"]
        sol_type = fdef["type"]
        wire[fname] = _str_for_wire(sol_type, fields[fname])
    wire["r"] = r_hex
    wire["s"] = s_hex
    wire["v"] = v_str

    return wire


# ── High-level helpers for each intent type ───────────────────────────

def sign_register_session_key(
    main_wallet: LocalAccount,
    session_key_address: str,
    nonce: int | None = None,
    expiry_s: int | None = None,
) -> dict:
    """
    Sign a RegisterSessionKey intent with the *main* wallet.

    The session key address is the address whose private key will sign
    future trading intents (OpenPosition, Close, etc.).
    """
    return sign_intent(
        signer=main_wallet,
        intent_type="RegisterSessionKey",
        fields={
            "user":       main_wallet.address,
            "key":        session_key_address,
            "expiry":     expiry_s or session_expiry(),
            "feeAddress": FEE_ADDRESS,
            "nonce":      nonce or next_nonce("register"),
            "deadline":   deadline(),
        },
    )


def sign_open_position(
    session_key: LocalAccount,
    user_address: str,
    instrument_id: int,
    is_long: bool,
    size_raw: int,        # margin in 10^18 units (1 USDC = 10^18)
    leverage: int,
    use_debt: bool = False,
    nonce: int | None = None,
) -> dict:
    """Sign an OpenPosition intent with the *session key*."""
    return sign_intent(
        signer=session_key,
        intent_type="OpenPosition",
        fields={
            "user":         user_address,
            "instrumentId": instrument_id,
            "isLong":       is_long,
            "size":         size_raw,
            "leverage":     leverage,
            "useDebt":      use_debt,
            "nonce":        nonce or next_nonce("trade"),
            "deadline":     deadline(),
        },
    )


def sign_close_positions(
    session_key: LocalAccount,
    user_address: str,
    position_ids: list[int],
    nonce: int | None = None,
) -> dict:
    """Sign a Close intent with the *session key*."""
    return sign_intent(
        signer=session_key,
        intent_type="Close",
        fields={
            "user":        user_address,
            "positionIds": position_ids,
            "nonce":       nonce or next_nonce("trade"),
            "deadline":    deadline(),
        },
    )


def sign_withdraw_to_core(
    main_wallet: LocalAccount,
    amount_raw: int,
    nonce: int | None = None,
) -> dict:
    """Sign a WithdrawToCore intent with the *main* wallet."""
    return sign_intent(
        signer=main_wallet,
        intent_type="WithdrawToCore",
        fields={
            "user":     main_wallet.address,
            "amount":   amount_raw,
            "nonce":    nonce or next_nonce("withdraw"),
            "deadline": deadline(),
        },
    )


def sign_stake(
    main_wallet: LocalAccount,
    amount_raw: int,
    nonce: int | None = None,
) -> dict:
    """Sign a Stake intent with the *main* wallet."""
    return sign_intent(
        signer=main_wallet,
        intent_type="Stake",
        fields={
            "user":     main_wallet.address,
            "amount":   amount_raw,
            "nonce":    nonce or next_nonce("stake"),
            "deadline": deadline(),
        },
    )


def sign_unstake(
    main_wallet: LocalAccount,
    amount_raw: int,
    nonce: int | None = None,
) -> dict:
    """Sign an Unstake intent with the *main* wallet."""
    return sign_intent(
        signer=main_wallet,
        intent_type="Unstake",
        fields={
            "user":     main_wallet.address,
            "amount":   amount_raw,
            "nonce":    nonce or next_nonce("unstake"),
            "deadline": deadline(),
        },
    )


def sign_claim(
    main_wallet: LocalAccount,
    nonce: int | None = None,
) -> dict:
    """Sign a Claim (paper rewards) intent with the *main* wallet."""
    return sign_intent(
        signer=main_wallet,
        intent_type="Claim",
        fields={
            "user":     main_wallet.address,
            "nonce":    nonce or next_nonce("claim"),
            "deadline": deadline(),
        },
    )


def sign_cancel_intent(
    main_wallet: LocalAccount,
    intent_id: str,         # bytes32 hex string "0x…"
    nonce: int | None = None,
) -> dict:
    """Sign a CancelIntent with the *main* wallet using the cancellation domain."""
    return sign_intent(
        signer=main_wallet,
        intent_type="CancelIntent",
        fields={
            "user":     main_wallet.address,
            "intentId": intent_id,
            "deadline": deadline(),
        },
    )
