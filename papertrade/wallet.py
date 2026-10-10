"""
OKX-compatible wallet generation.

OKX Wallet uses standard BIP-39 mnemonic + BIP-44 derivation path
m/44'/60'/0'/0/0 (same as MetaMask and most EVM wallets).
The result is a standard secp256k1 Ethereum key pair, fully compatible
with PaperTrade's EIP-712 signing requirements.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from eth_account import Account
from eth_account.signers.local import LocalAccount
from mnemonic import Mnemonic

Account.enable_unaudited_hdwallet_features()


def generate_okx_wallet(words: int = 12) -> dict:
    """
    Generate a fresh OKX-compatible BIP-39 wallet.

    Returns a dict with:
        mnemonic    – 12-word seed phrase (KEEP SECRET)
        private_key – hex private key 0x… (KEEP SECRET)
        address     – checksummed Ethereum address (public)
        path        – BIP-44 derivation path used

    ⚠️  NEVER commit or print the mnemonic or private_key.
    """
    mnemo = Mnemonic("english")
    mnemonic_phrase = mnemo.generate(strength=128 if words == 12 else 256)
    account: LocalAccount = Account.from_mnemonic(
        mnemonic_phrase,
        account_path="m/44'/60'/0'/0/0",
    )
    return {
        "mnemonic":    mnemonic_phrase,
        "private_key": account.key.hex(),
        "address":     account.address,
        "path":        "m/44'/60'/0'/0/0",
    }


def wallet_from_mnemonic(mnemonic: str, index: int = 0) -> LocalAccount:
    """Restore an Ethereum account from a BIP-39 mnemonic."""
    path = f"m/44'/60'/0'/0/{index}"
    return Account.from_mnemonic(mnemonic, account_path=path)


def wallet_from_private_key(private_key: str) -> LocalAccount:
    """Load a wallet from a raw hex private key (with or without 0x prefix)."""
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key
    return Account.from_key(private_key)


def save_wallet(wallet_info: dict, path: str | Path, overwrite: bool = False) -> Path:
    """
    Save wallet credentials to a JSON file with 0600 permissions.

    ⚠️  This file contains the private key — store it securely and
    never commit it to version control.
    """
    p = Path(path)
    if p.exists() and not overwrite:
        raise FileExistsError(f"{p} already exists; pass overwrite=True to replace it.")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(wallet_info, indent=2))
    p.chmod(0o600)
    return p


def load_wallet(path: str | Path) -> LocalAccount:
    """Load a wallet from a previously saved JSON file."""
    info = json.loads(Path(path).read_text())
    if "mnemonic" in info:
        return wallet_from_mnemonic(info["mnemonic"])
    if "private_key" in info:
        return wallet_from_private_key(info["private_key"])
    raise ValueError("Wallet file must contain 'mnemonic' or 'private_key'")


def wallet_from_env(env_var: str = "PAPERTRADE_PRIVATE_KEY") -> Optional[LocalAccount]:
    """Load a wallet from an environment variable (hex private key)."""
    pk = os.environ.get(env_var)
    if not pk:
        return None
    return wallet_from_private_key(pk)
