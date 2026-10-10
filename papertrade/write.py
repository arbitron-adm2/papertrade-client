"""
Write (mutating) endpoints for PaperTrade.

Every mutation is an "intent" — an EIP-712 signed payload submitted to
POST /intents on exchange.papertrade.xyz.

Architecture:
  main_wallet  → signs RegisterSessionKey, WithdrawToCore, Stake, Unstake, Claim, CancelIntent
  session_key  → signs OpenPosition, Close
  (can be the same key — the contract allows self-registration)

The server returns {"intentId": "0x…", …} on success or {"error": "…"} on failure.

All methods are **safe to call in dry-run mode** (they return the signed
payload without sending it) when `dry_run=True` is passed.  The CLI
gates every write behind `--write` for an extra layer of safety.
"""
from __future__ import annotations

from typing import Any

from eth_account.signers.local import LocalAccount

from .transport import Transport
from .signing import (
    sign_register_session_key,
    sign_open_position,
    sign_close_positions,
    sign_withdraw_to_core,
    sign_stake,
    sign_unstake,
    sign_claim,
    sign_cancel_intent,
    next_nonce,
    deadline,
)
from .constants import (
    INTENT_ACTION,
    COLLATERAL_SCALE,
    PAPER_SCALE,
    INSTRUMENTS,
    INSTRUMENT_BY_NAME,
)
from .exceptions import IntentError


def _submit_intent(
    transport: Transport,
    action: str,
    signed: dict,
    extra: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """Send a signed intent to POST /intents and return the response."""
    body: dict[str, Any] = {"action": action, "signed": signed}
    if extra:
        body.update(extra)

    if dry_run:
        return {"dry_run": True, "would_post": body}

    resp = transport.post("/intents", body)

    # Server returns {"intentId":…} on success or {"error":…} on error
    if resp.get("error") or resp.get("ok") is False:
        raise IntentError(resp.get("error") or resp.get("message") or str(resp))

    return resp


class PaperTradeWriter:
    """
    Write client for all mutating PaperTrade intents.

    Parameters
    ----------
    transport    : Transport  – shared HTTP transport
    main_wallet  : LocalAccount – signs funding / staking / registration intents
    session_key  : LocalAccount – signs trading intents (OpenPosition, Close)
                   Defaults to main_wallet if not provided.
    """

    def __init__(
        self,
        transport: Transport,
        main_wallet: LocalAccount,
        session_key: LocalAccount | None = None,
    ) -> None:
        self._t       = transport
        self._wallet  = main_wallet
        self._skey    = session_key or main_wallet

    # ── Session key management ────────────────────────────────────────

    def register_session_key(
        self,
        session_key_address: str | None = None,
        dry_run: bool = False,
    ) -> dict:
        """
        Register the session key so it can sign trading intents.

        Call this once before placing trades.  The session key is valid
        for 30 days.  Reregistering before expiry is safe and resets
        the clock.

        POST /intents  {"action":"registerSessionKey", "signed":{…}}
        ⚠️  WRITE — requires --write flag in CLI.
        """
        key_addr = session_key_address or self._skey.address
        signed = sign_register_session_key(
            main_wallet=self._wallet,
            session_key_address=key_addr,
        )
        return _submit_intent(
            self._t,
            action=INTENT_ACTION["RegisterSessionKey"],
            signed=signed,
            dry_run=dry_run,
        )

    # ── Trading ───────────────────────────────────────────────────────

    def open_position(
        self,
        instrument: str | int,
        is_long: bool,
        margin_usdc: float,
        leverage: int,
        use_debt: bool = False,
        dry_run: bool = False,
    ) -> dict:
        """
        Open a new leveraged position.

        instrument  : "BTC" or "ETH" or instrument ID (0/1)
        is_long     : True = long, False = short
        margin_usdc : Margin in USDC (e.g. 100.0 = $100)
        leverage    : 1–1000
        use_debt    : True to open with borrowed collateral

        POST /intents  {"action":"openPosition", "signed":{…}}
        ⚠️  WRITE — requires --write flag in CLI.

        Size encoding: 1 USDC margin = 10^18 raw units.
        Minimum: $10 margin (10 * 10^18 raw); min notional $10,000.
        """
        if isinstance(instrument, str):
            if instrument not in INSTRUMENT_BY_NAME:
                raise ValueError(f"Unknown instrument {instrument!r}; use BTC or ETH")
            instrument_id = INSTRUMENT_BY_NAME[instrument]
        else:
            instrument_id = int(instrument)

        if instrument_id not in INSTRUMENTS:
            raise ValueError(f"Instrument ID {instrument_id} not in {list(INSTRUMENTS)}")
        if not 1 <= leverage <= 1000:
            raise ValueError("leverage must be 1–1000")
        if margin_usdc <= 0:
            raise ValueError("margin_usdc must be positive")

        size_raw = int(margin_usdc * COLLATERAL_SCALE)

        signed = sign_open_position(
            session_key=self._skey,
            user_address=self._wallet.address,
            instrument_id=instrument_id,
            is_long=is_long,
            size_raw=size_raw,
            leverage=leverage,
            use_debt=use_debt,
        )
        return _submit_intent(
            self._t,
            action=INTENT_ACTION["OpenPosition"],
            signed=signed,
            dry_run=dry_run,
        )

    def close_positions(
        self,
        position_ids: list[int],
        dry_run: bool = False,
    ) -> dict:
        """
        Close one or more open positions by their IDs.

        position_ids: list of integer position IDs (up to 25 at once)

        POST /intents  {"action":"closePositions", "signed":{…}}
        ⚠️  WRITE — requires --write flag in CLI.
        """
        if not position_ids:
            raise ValueError("position_ids cannot be empty")
        if len(position_ids) > 25:
            raise ValueError("Maximum 25 position IDs per close request")

        signed = sign_close_positions(
            session_key=self._skey,
            user_address=self._wallet.address,
            position_ids=position_ids,
        )
        return _submit_intent(
            self._t,
            action=INTENT_ACTION["Close"],
            signed=signed,
            dry_run=dry_run,
        )

    # ── Funding ───────────────────────────────────────────────────────

    def withdraw_to_core(
        self,
        amount_usdc: float,
        dry_run: bool = False,
    ) -> dict:
        """
        Withdraw USDC collateral from PaperTrade to Hyperliquid HyperCore.

        amount_usdc: Amount in USDC (e.g. 50.0 = $50)
        POST /intents  {"action":"withdrawToCore", "signed":{…}}
        ⚠️  WRITE — requires --write flag in CLI.
        """
        amount_raw = int(amount_usdc * COLLATERAL_SCALE)
        signed = sign_withdraw_to_core(
            main_wallet=self._wallet,
            amount_raw=amount_raw,
        )
        return _submit_intent(
            self._t,
            action=INTENT_ACTION["WithdrawToCore"],
            signed=signed,
            dry_run=dry_run,
        )

    # ── PAPER token ───────────────────────────────────────────────────

    def stake_paper(
        self,
        amount_paper: float,
        dry_run: bool = False,
    ) -> dict:
        """
        Stake PAPER governance tokens.

        amount_paper: Amount in PAPER (e.g. 100.0 = 100 PAPER)
        POST /intents  {"action":"paperStake", "signed":{…}}
        ⚠️  WRITE — requires --write flag in CLI.
        """
        amount_raw = int(amount_paper * PAPER_SCALE)
        signed = sign_stake(main_wallet=self._wallet, amount_raw=amount_raw)
        return _submit_intent(
            self._t, action=INTENT_ACTION["Stake"], signed=signed, dry_run=dry_run
        )

    def unstake_paper(
        self,
        amount_paper: float,
        dry_run: bool = False,
    ) -> dict:
        """
        Unstake PAPER governance tokens.

        POST /intents  {"action":"paperUnstake", "signed":{…}}
        ⚠️  WRITE — requires --write flag in CLI.
        """
        amount_raw = int(amount_paper * PAPER_SCALE)
        signed = sign_unstake(main_wallet=self._wallet, amount_raw=amount_raw)
        return _submit_intent(
            self._t, action=INTENT_ACTION["Unstake"], signed=signed, dry_run=dry_run
        )

    def claim_paper_rewards(self, dry_run: bool = False) -> dict:
        """
        Claim available PAPER token rewards.

        POST /intents  {"action":"paperClaim", "signed":{…}}
        ⚠️  WRITE — requires --write flag in CLI.
        """
        signed = sign_claim(main_wallet=self._wallet)
        return _submit_intent(
            self._t, action=INTENT_ACTION["Claim"], signed=signed, dry_run=dry_run
        )

    # ── Intent management ─────────────────────────────────────────────

    def cancel_intent(
        self,
        intent_id: str,
        dry_run: bool = False,
    ) -> dict:
        """
        Cancel a queued intent by ID.

        intent_id: bytes32 hex string "0x…" from a previous /intents response.
        POST /intents/{intent_id}/cancel  {"user","intentId","deadline","r","s","v"}
        ⚠️  WRITE — requires --write flag in CLI.
        """
        signed = sign_cancel_intent(
            main_wallet=self._wallet,
            intent_id=intent_id,
        )
        # CancelIntent posts to /intents/{id}/cancel with the signed fields
        # (without action/signed wrapper — the cancel endpoint takes them directly)
        cancel_body = {k: v for k, v in signed.items()}

        if dry_run:
            return {"dry_run": True, "would_post": cancel_body, "path": f"/intents/{intent_id}/cancel"}

        resp = self._t.post(f"/intents/{intent_id}/cancel", cancel_body)
        if resp.get("error") or resp.get("ok") is False:
            raise IntentError(resp.get("error") or str(resp))
        return resp
