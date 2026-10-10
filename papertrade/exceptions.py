"""PaperTrade client exceptions."""


class PaperTradeError(Exception):
    """Base exception."""


class HttpError(PaperTradeError):
    def __init__(self, status: int, body: dict | None = None):
        self.status = status
        self.body = body or {}
        msg = self.body.get("error") or self.body.get("message") or f"HTTP {status}"
        super().__init__(msg)


class IntentError(PaperTradeError):
    """Intent submission rejected by the server."""


class SigningError(PaperTradeError):
    """EIP-712 signing failed."""


class ConfigError(PaperTradeError):
    """Bad configuration."""
