"""
Pytest tests for Wallet Authenticator.

Tests cover:
- Wallet initialization from private key
- Message signing
- Address derivation
"""
import pytest
from eth_account import Account

from app.services.auth.wallet import WalletAuthenticator, WalletCredentials


@pytest.fixture
def test_account():
    """Generate a test account."""
    return Account.create()


class TestWalletCredentials:
    """Tests for WalletCredentials dataclass."""

    def test_credentials_with_private_key(self):
        """Should store private key."""
        creds = WalletCredentials(
            address="0x123",
            private_key="0xabc",
        )
        assert creds.address == "0x123"
        assert creds.private_key == "0xabc"

    def test_credentials_without_private_key(self):
        """Should work without private key."""
        creds = WalletCredentials(address="0x123")
        assert creds.address == "0x123"
        assert creds.private_key is None


class TestWalletAuthenticator:
    """Tests for WalletAuthenticator class."""

    def test_init_without_key(self):
        """Should initialize without key."""
        auth = WalletAuthenticator()
        assert auth._private_key is None
        assert auth._account is None
        assert auth.address is None
        assert not auth.is_configured()

    def test_init_with_key(self, test_account):
        """Should initialize with private key."""
        auth = WalletAuthenticator(private_key=f"0x{test_account.key.hex()}")
        assert auth.is_configured()
        assert auth.address is not None
        assert auth.address.startswith("0x")

    def test_address_format(self, test_account):
        """Should derive correct address format."""
        auth = WalletAuthenticator(private_key=f"0x{test_account.key.hex()}")
        # Ethereum addresses are 42 chars starting with 0x
        assert len(auth.address) == 42
        assert auth.address[:2] == "0x"

    def test_sign_message_not_configured(self):
        """Should return None when not configured."""
        auth = WalletAuthenticator()
        result = auth.sign_message("test message")
        assert result is None

    def test_sign_message_configured(self, test_account):
        """Should sign message when configured."""
        auth = WalletAuthenticator(private_key=f"0x{test_account.key.hex()}")

        signature = auth.sign_message("Hello, Polymarket!")

        assert signature is not None
        assert signature.startswith("0x")
        assert len(signature) == 132  # 65 bytes * 2 + 0x prefix

    def test_sign_text(self, test_account):
        """Should sign text using personal_sign."""
        auth = WalletAuthenticator(private_key=f"0x{test_account.key.hex()}")

        signature = auth.sign_text("Test message")

        assert signature is not None
        assert signature.startswith("0x")

    def test_sign_same_message_same_signature(self, test_account):
        """Same message should produce same signature."""
        auth = WalletAuthenticator(private_key=f"0x{test_account.key.hex()}")

        sig1 = auth.sign_message("Consistent message")
        sig2 = auth.sign_message("Consistent message")

        assert sig1 == sig2

    def test_sign_different_messages_different_signatures(self, test_account):
        """Different messages should produce different signatures."""
        auth = WalletAuthenticator(private_key=f"0x{test_account.key.hex()}")

        sig1 = auth.sign_message("Message 1")
        sig2 = auth.sign_message("Message 2")

        assert sig1 != sig2


class TestWalletAuthenticatorEnv:
    """Tests for environment variable loading."""

    def test_env_var_not_set(self, monkeypatch):
        """Should handle missing env var."""
        monkeypatch.delenv("WALLET_PRIVATE_KEY", raising=False)

        auth = WalletAuthenticator()

        assert auth._private_key is None
        assert not auth.is_configured()


class TestSingletonPattern:
    """Tests for singleton getter functions."""

    def test_get_wallet_authenticator_returns_instance(self):
        """Should return WalletAuthenticator instance."""
        from app.services.auth.wallet import get_wallet_authenticator

        auth = get_wallet_authenticator()

        assert isinstance(auth, WalletAuthenticator)

    def test_configure_wallet_authenticator(self):
        """Should configure and return authenticator."""
        from app.services.auth.wallet import (
            get_wallet_authenticator,
            configure_wallet_authenticator,
        )

        # Generate a new key
        account = Account.create()
        key = account.key.hex()

        auth = configure_wallet_authenticator(f"0x{key}")

        assert isinstance(auth, WalletAuthenticator)
        assert auth.is_configured()
        assert auth.address == account.address
