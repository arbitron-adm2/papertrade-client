"""
PaperTradeClient — unified client combining read and write operations.

Quickstart (read-only, no wallet needed):
    from papertrade import PaperTradeClient
    c = PaperTradeClient()
    print(c.read.protocol_summary())

Quickstart (full trading, wallet required):
    from papertrade import PaperTradeClient
    from papertrade.wallet import wallet_from_private_key
    acct = wallet_from_private_key("0x…")
    c = PaperTradeClient(wallet=acct)
    # Register session key first (once):
    c.write.register_session_key(dry_run=False)
    # Then trade:
    c.write.open_position("BTC", is_long=True, margin_usdc=100, leverage=10)
"""
from __future__ import annotations

from typing import Optional

from eth_account.signers.local import LocalAccount

from .transport import Transport
from .read import PaperTradeReader
from .write import PaperTradeWriter
from .wallet import wallet_from_env
from .constants import EXCHANGE_BASE


class PaperTradeClient:
    """
    Unified PaperTrade API client.

    Parameters
    ----------
    wallet       : LocalAccount | None
        If None, only read-only operations are available.
        If provided, write operations become available via `.write`.
    session_key  : LocalAccount | None
        Separate key for signing trading intents (OpenPosition / Close).
        Defaults to ``wallet`` if not provided.
    base_url     : str
        Override the exchange base URL (default: exchange.papertrade.xyz).
    timeout      : float
        Per-request timeout in seconds.
    """

    def __init__(
        self,
        wallet: Optional[LocalAccount] = None,
        session_key: Optional[LocalAccount] = None,
        base_url: str = EXCHANGE_BASE,
        timeout: float = 35.0,
    ) -> None:
        # Try loading wallet from environment if not passed explicitly
        _wallet = wallet or wallet_from_env()

        self._transport = Transport(base_url=base_url, timeout=timeout)
        self.read = PaperTradeReader(self._transport)

        if _wallet is not None:
            self.write = PaperTradeWriter(
                transport=self._transport,
                main_wallet=_wallet,
                session_key=session_key,
            )
            self.address: str = _wallet.address
        else:
            self.write = None  # type: ignore[assignment]
            self.address = ""

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._transport.close()

    def __enter__(self) -> "PaperTradeClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ── Convenience shortcuts ─────────────────────────────────────────

    def is_ready(self) -> bool:
        """Return True if the exchange is live."""
        try:
            resp = self.read.ready()
            return resp.get("status") == "ok"
        except Exception:
            return False

    def instruments(self) -> list[dict]:
        """Return instruments from the live trading state."""
        state = self.read.trading_state()
        raw = state.get("instruments", [])
        result = []
        for row in raw:
            # Instrument row: [id, name, assetIndex, priceScale, ...]
            result.append({
                "id":          row[0],
                "name":        row[1],
                "assetIndex":  row[2],
                "priceScale":  row[3],
                "active":      row[4],
            })
        return result
