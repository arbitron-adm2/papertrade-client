"""
All public read (GET) endpoints for PaperTrade.

Every method here works without authentication — auth tier 0.
No wallet or signing needed.
"""
from __future__ import annotations

from typing import Any, Optional

from .transport import Transport
from .constants import (
    HISTORY_INTERVALS,
    LEADERBOARD_WINDOWS,
    LIQ_MAP_RANGES,
    EXCHANGE_BASE,
)


class PaperTradeReader:
    """
    Read-only client for all public PaperTrade endpoints.

    Parameters
    ----------
    transport : Transport
        Shared transport instance.
    """

    def __init__(self, transport: Transport) -> None:
        self._t = transport

    # ── Health ────────────────────────────────────────────────────────

    def ready(self) -> dict:
        """
        GET /query/ready

        Returns `{"status": "ok"}` when the exchange is operational.
        Confirmed live: HTTP 200 {"status": ...}
        """
        return self._t.get("/query/ready")

    # ── Protocol-level metrics ────────────────────────────────────────

    def protocol_summary(self) -> dict:
        """
        GET /query/protocol/summary

        Returns overall TVL, activity, and fee metrics.
        Confirmed live: HTTP 200 {"ok", "source", "balances", "activity", "fees"}
        """
        return self._t.get("/query/protocol/summary")

    def protocol_history(self, interval: str = "1d") -> dict:
        """
        GET /query/protocol/history?interval={interval}

        interval: one of "1h", "1d"  (1w and all return HTTP 400)
        Returns time-series data for TVL, volume, PnL, etc.
        Confirmed live: HTTP 200 {"startMs", "intervalMs", "columns", "source", "totals"}
        """
        if interval not in HISTORY_INTERVALS:
            raise ValueError(f"interval must be one of {HISTORY_INTERVALS} (1w/all return 400 from server)")
        return self._t.get("/query/protocol/history", params={"interval": interval})

    def protocol_trades_recent(self) -> dict:
        """
        GET /query/protocol/trades/recent

        Returns the most recent trades across all accounts.
        Confirmed live: HTTP 200 {"ok", "count", "events"}
        """
        return self._t.get("/query/protocol/trades/recent")

    def protocol_paper_activity(self) -> dict:
        """
        GET /query/protocol/paper/activity

        Returns PAPER token distribution and staking activity.
        Confirmed live: HTTP 200 {"items", "latestDistribution"}
        """
        return self._t.get("/query/protocol/paper/activity")

    def protocol_queue_summary(self) -> dict:
        """
        GET /query/protocol/queue-summary

        Returns the global deposit queue summary.
        Confirmed live: HTTP 200 {"ok", "source", "total", "count", "largest"}
        """
        return self._t.get("/query/protocol/queue-summary")

    def notices(self) -> list[dict]:
        """
        GET /query/notices

        Returns active system notices/announcements.
        Confirmed live: HTTP 200 {"notices": [...]}
        """
        data = self._t.get("/query/notices")
        return data.get("notices", [])

    # ── Market data ───────────────────────────────────────────────────

    def liquidation_map(
        self,
        instrument_id: int,
        price_range_pct: str = "1",
    ) -> dict:
        """
        GET /query/markets/{instrument_id}/liquidation-map?range={pct}

        instrument_id: 0=BTC, 1=ETH
        price_range_pct: one of "0.1","0.25","0.5","1","2","5","10","25"
        Returns 150 price buckets with open interest per side.
        Confirmed live: HTTP 200 {"ok","instrumentId","range","fromRaw","toRaw","priceScale",...}
        """
        if price_range_pct not in LIQ_MAP_RANGES:
            raise ValueError(f"price_range_pct must be one of {LIQ_MAP_RANGES}")
        return self._t.get(
            f"/query/markets/{instrument_id}/liquidation-map",
            params={"range": price_range_pct},
        )

    # ── Trading state (real-time global parameters) ───────────────────

    def trading_state(self) -> dict:
        """
        GET /state/trading

        Returns current trading parameters: minimum sizes, instruments,
        intake actions, reward accumulators.
        Confirmed live: HTTP 200 {"schemaVersion","indexedThroughBlock","tradingPaused",...}
        """
        return self._t.get("/state/trading")

    def position_topology(self) -> dict:
        """
        GET /state/protocol/position-topology

        Returns the 96×64 grid of current open positions (heatmap data).
        Confirmed live: HTTP 200 {"ok","count","nExt","pExt","computedAtMs","grid"}
        """
        return self._t.get("/state/protocol/position-topology")

    def house_current(self) -> dict:
        """
        GET /state/house/current

        Returns the house (protocol reserve) current state.
        Confirmed live: HTTP 200 {"ok","revision","historyRevision","historyGeneration",...}
        """
        return self._t.get("/state/house/current")

    def house_delta(self, coin: str = "BTC") -> dict:
        """
        GET /state/house/delta?coin={coin}

        coin: "BTC" or "ETH"
        Returns the delta (change) in house state for the given coin.
        Confirmed live: HTTP 200 {"ok","revision","sourceAsOfMs","delta"}
        """
        return self._t.get("/state/house/delta", params={"coin": coin})

    # ── Account data ──────────────────────────────────────────────────

    def account_funding(self, address: str) -> dict:
        """
        GET /query/accounts/{address}/funding

        Returns deposit/withdrawal history and coreAccount status.
        Confirmed live: HTTP 200 {"items","coreAccount"}
        """
        addr = address.lower()
        return self._t.get(f"/query/accounts/{addr}/funding")

    def account_trades(
        self,
        address: str,
        cursor: Optional[str] = None,
    ) -> dict:
        """
        GET /query/accounts/{address}/trades[?cursor=...]

        Returns paginated trade history.
        Confirmed live: HTTP 200 {"items","nextCursor"}
        """
        addr = address.lower()
        params = {}
        if cursor:
            params["cursor"] = cursor
        return self._t.get(f"/query/accounts/{addr}/trades", params=params or None)

    def account_queue_ring(self, address: str) -> dict:
        """
        GET /query/accounts/{address}/queue-ring

        Returns the account's position in the deposit queue.
        Confirmed live: HTTP 200 {"ok","source","total","count","account","truncated","entries"}
        """
        addr = address.lower()
        return self._t.get(f"/query/accounts/{addr}/queue-ring")

    def account_queue_balances(
        self,
        address: str,
        cursor: Optional[str] = None,
        limit: int = 75,
    ) -> dict:
        """
        GET /query/accounts/{address}/queue-balances?limit=75[&cursor=...]

        Returns paginated queue balance entries.
        """
        addr = address.lower()
        params: dict[str, Any] = {"limit": str(limit)}
        if cursor:
            params["cursor"] = cursor
        return self._t.get(f"/query/accounts/{addr}/queue-balances", params=params)

    def account_portfolio_history(
        self,
        address: str,
        range_: str = "all",
    ) -> dict:
        """
        GET /query/accounts/{address}/portfolio-history?range={range_}

        range_: "all" confirmed working; shorter ranges may require active history.
        Returns time-series P&L / balance data.
        Confirmed live: HTTP 200 {"fromMs","toMs","intervalMs","baseTimeMs",...}
        """
        addr = address.lower()
        return self._t.get(
            f"/query/accounts/{addr}/portfolio-history",
            params={"range": range_},
        )

    def account_leaderboard_badges(self, address: str) -> dict:
        """
        GET /query/accounts/{address}/leaderboard-badges

        Returns badges/achievements for the address on the leaderboard.
        Confirmed live: HTTP 200 {"ok","badges","total"}
        """
        addr = address.lower()
        return self._t.get(f"/query/accounts/{addr}/leaderboard-badges")

    # ── Leaderboard ───────────────────────────────────────────────────

    def leaderboard(
        self,
        address: str,
        window: str = "24h",
        page: int = 0,
        sort_key: str = "totalWindowedPnl",
        sort_dir: str = "desc",
        query: str = "",
    ) -> dict:
        """
        GET /state/leaderboard/accounts/{address}?window=...&page=...&sortKey=...

        Returns the leaderboard with the account's own rank (selfRow) if
        address is registered.  Use the zero address for an anonymous view.
        window: one of "24h","7d","30d","all"
        sort_key: rank|address|totalWindowedPnl|realizedPnl|currentBalance|...
        """
        if window not in LEADERBOARD_WINDOWS:
            raise ValueError(f"window must be one of {LEADERBOARD_WINDOWS}")
        return self._t.get(
            f"/state/leaderboard/accounts/{address.lower()}",
            params={
                "window":  window,
                "page":    page,
                "sortKey": sort_key,
                "sortDir": sort_dir,
                "q":       query,
            },
        )
