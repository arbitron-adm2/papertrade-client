"""
papertrade — Unofficial Python client for papertrade.xyz

⚠️  DISCLAIMER: This is an unofficial, reverse-engineered client. It is not
affiliated with, endorsed by, or supported by PaperTrade or its developers.
Use of this client is subject to PaperTrade's Terms of Service. The ToS risk
is the user's to own. This client may break at any time if the site's
undocumented internal API changes.
"""

from .client import PaperTradeClient
from .wallet import (
    generate_okx_wallet,
    wallet_from_mnemonic,
    wallet_from_private_key,
    wallet_from_env,
    save_wallet,
    load_wallet,
)
from .exceptions import PaperTradeError, HttpError, IntentError, SigningError

__version__ = "0.1.0"
__all__ = [
    "PaperTradeClient",
    "generate_okx_wallet",
    "wallet_from_mnemonic",
    "wallet_from_private_key",
    "wallet_from_env",
    "save_wallet",
    "load_wallet",
    "PaperTradeError",
    "HttpError",
    "IntentError",
    "SigningError",
]
