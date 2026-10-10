"""
HTTP transport layer for PaperTrade.

Two request families, matching the client-side `query-api-client` bucket logic:
  • /query/…  → "query" bucket (rate-limited separately)
  • other /…  → "edge"  bucket (rate-limited separately)

Auth tier 0 for reads: no API key, no bearer token.  Only standard
browser-like headers.  The server uses same-origin cookies in the browser,
but public /query/ and /state/ endpoints work with no credentials at all.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from .constants import EXCHANGE_BASE
from .exceptions import HttpError


# Build ID injected by the site; use the one from the HTML bundle.
_PAPERTRADE_BUILD = "2026-10-10"  # pinned snapshot; update if 400 errors appear

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

_COMMON_HEADERS = {
    "User-Agent":         _UA,
    "Accept":             "application/json",
    "Origin":             EXCHANGE_BASE,
    "Referer":            EXCHANGE_BASE + "/",
    "X-Papertrade-Build": _PAPERTRADE_BUILD,
}


class _Bucket:
    """Minimal in-process rate-limit bucket — mirrors query-api-client.js."""

    def __init__(self) -> None:
        self._cooldown_until: float = 0.0

    def check(self) -> None:
        remaining = self._cooldown_until - time.time()
        if remaining > 0:
            raise HttpError(429)

    def on_429(self, retry_after: float | None) -> None:
        if retry_after:
            self._cooldown_until = time.time() + retry_after
        else:
            self._cooldown_until = time.time() + 2.0


_query_bucket = _Bucket()
_edge_bucket  = _Bucket()

_RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF = [0.5, 1.5, 4.0]


def _bucket_for(path: str) -> _Bucket:
    if path.startswith("/query/"):
        return _query_bucket
    if path.startswith("/"):
        return _edge_bucket
    return _Bucket()  # external URL — no shared bucket


def _parse_retry_after(headers: httpx.Headers) -> float | None:
    val = headers.get("Retry-After")
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


class Transport:
    """
    Thin wrapper around httpx with retry / rate-limit logic.

    Parameters
    ----------
    base_url : str
        Default base URL (exchange.papertrade.xyz).
    timeout  : float
        Per-request timeout in seconds.
    session_cookies : dict | None
        Optional cookie jar for authenticated /intents calls.
        If omitted, only public endpoints work.
    """

    def __init__(
        self,
        base_url: str = EXCHANGE_BASE,
        timeout: float = 35.0,
        session_cookies: dict | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            headers=_COMMON_HEADERS,
            cookies=session_cookies or {},
        )

    # ── public helpers ────────────────────────────────────────────────

    def get(self, path: str, params: dict | None = None) -> Any:
        """GET request with retry."""
        return self._request("GET", path, params=params)

    def post(self, path: str, body: dict) -> Any:
        """POST JSON request with retry."""
        return self._request("POST", path, json=body)

    def head(self, url: str) -> int:
        """HEAD request to an arbitrary URL; returns status code."""
        r = self._client.head(url)
        return r.status_code

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Transport":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ── internals ─────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
    ) -> Any:
        # Resolve full URL
        if path.startswith("http"):
            url = path
        else:
            url = self._base + path

        bucket = _bucket_for(path)

        for attempt in range(_MAX_RETRIES):
            bucket.check()
            try:
                resp = self._client.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers={"Content-Type": "application/json"} if json else {},
                )
            except httpx.TimeoutException as exc:
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_BACKOFF[attempt])
                    continue
                raise HttpError(408) from exc
            except httpx.RequestError as exc:
                raise HttpError(0) from exc

            if resp.status_code == 429:
                retry_after = _parse_retry_after(resp.headers)
                bucket.on_429(retry_after)
                if attempt < _MAX_RETRIES - 1:
                    delay = max(_BACKOFF[attempt], retry_after or 0)
                    time.sleep(delay)
                    continue
                raise HttpError(429, {"error": "Too many requests"})

            if resp.status_code in _RETRYABLE_STATUSES and attempt < _MAX_RETRIES - 1:
                time.sleep(_BACKOFF[attempt])
                continue

            if not resp.is_success:
                try:
                    body = resp.json()
                except Exception:
                    body = {}
                raise HttpError(resp.status_code, body)

            if resp.status_code == 204:
                return {}

            return resp.json()

        raise HttpError(0, {"error": "Max retries exceeded"})
