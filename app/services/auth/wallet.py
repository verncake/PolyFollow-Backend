"""
Wallet authentication utilities for Polymarket API.

Provides EIP-712 signing and wallet-based authentication.
"""
import os
import json
from typing import Optional, Union
from dataclasses import dataclass
from eth_account import Account
from eth_account.messages import (
    HexBytes,
    SignableMessage,
    _hash_eip191_message,
)


@dataclass
class WalletCredentials:
    """Wallet credentials for authentication."""
    address: str
    private_key: Optional[str] = None


class WalletAuthenticator:
    """
    Handles wallet-based authentication for Polymarket API.

    Uses EIP-712 typed data signing for authentication.
    """

    def __init__(self, private_key: Optional[str] = None):
        """
        Initialize with private key or from environment.

        Args:
            private_key: Wallet private key (with 0x prefix)
        """
        self._private_key = private_key or os.getenv("WALLET_PRIVATE_KEY")
        self._account: Optional[Account] = None

        if self._private_key:
            self._account = Account.from_key(self._private_key)

    @property
    def address(self) -> Optional[str]:
        """Get wallet address."""
        return self._account.address if self._account else None

    def is_configured(self) -> bool:
        """Check if wallet is configured."""
        return self._account is not None

    def _to_signable(self, message: Union[str, bytes]) -> SignableMessage:
        """Convert message to SignableMessage format."""
        from eth_account.messages import encode_defunct
        if isinstance(message, str):
            return encode_defunct(text=message)
        return encode_defunct(hexstr=message.hex())

    def sign_message(self, message: str) -> Optional[str]:
        """
        Sign a simple message.

        Args:
            message: Message to sign

        Returns:
            Signature (0x prefixed) or None if not configured
        """
        if not self._account:
            return None
        signable = self._to_signable(message)
        signed = self._account.sign_message(signable)
        return f"0x{signed.signature.hex()}"

    def sign_text(self, text: str) -> Optional[str]:
        """
        Sign a text message using personal_sign.

        Args:
            text: Text to sign

        Returns:
            Signature (0x prefixed) or None if not configured
        """
        return self.sign_message(text)


# Singleton instance
_authenticator: Optional[WalletAuthenticator] = None


def get_wallet_authenticator() -> WalletAuthenticator:
    """Get the singleton wallet authenticator instance."""
    global _authenticator
    if _authenticator is None:
        _authenticator = WalletAuthenticator()
    return _authenticator


def configure_wallet_authenticator(private_key: str) -> WalletAuthenticator:
    """
    Configure and get the wallet authenticator.

    Args:
        private_key: Wallet private key (with 0x prefix)

    Returns:
        Configured authenticator
    """
    global _authenticator
    _authenticator = WalletAuthenticator(private_key)
    return _authenticator
