"""
Pytest tests for BlockchainClient.

Tests balance queries with mocked RPC responses.
"""
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.services.blockchain import (
    BlockchainClient,
    WalletBalance,
    get_blockchain_client,
    USDC_E_ADDRESS,
)


class TestWalletBalance:
    """Tests for WalletBalance dataclass."""

    def test_wallet_balance_creation(self):
        """Should create balance with correct fields."""
        balance = WalletBalance(
            address="0x123",
            usdc_e_balance=Decimal("100.5"),
            formatted_balance="100.500000",
            raw_balance=100500000,
        )

        assert balance.address == "0x123"
        assert balance.usdc_e_balance == Decimal("100.5")
        assert balance.formatted_balance == "100.500000"
        assert balance.raw_balance == 100500000


class TestBlockchainClient:
    """Tests for BlockchainClient."""

    def test_client_init_default(self):
        """Should initialize with default RPC."""
        client = BlockchainClient()
        # Falls back to env var or None
        assert client.rpc_url is None or isinstance(client.rpc_url, str)

    def test_client_init_custom_rpc(self):
        """Should use custom RPC when provided."""
        client = BlockchainClient(rpc_url="https://custom.rpc.com")
        assert client.rpc_url == "https://custom.rpc.com"

    def test_usdc_e_address(self):
        """Should have correct USDC.e token address."""
        assert USDC_E_ADDRESS == "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"


class TestGetUsdcEBalance:
    """Tests for get_usdc_e_balance with mocked web3."""

    @patch('app.services.blockchain.Web3')
    def test_balance_success(self, mock_web3):
        """Should return balance when RPC call succeeds."""
        # Setup mocks
        mock_w3 = MagicMock()
        mock_web3.return_value = mock_w3
        mock_w3.is_connected.return_value = True
        mock_w3.is_checksum_address.return_value = False
        mock_w3.to_checksum_address.return_value = "0x680fa9c2689b9D045Cee214E7d748D085bb80B19"

        mock_contract = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract
        mock_contract.functions.balanceOf.return_value.call.return_value = 1000000  # 1 USDC.e (1 * 10^6)
        mock_contract.functions.decimals.return_value.call.return_value = 6

        # Create client and get balance
        client = BlockchainClient(rpc_url="https://fake.rpc.com")
        balance = client.get_usdc_e_balance("0x680fa9c2689b9D045Cee214E7d748D085bb80B19")

        assert balance.usdc_e_balance == Decimal("1.0")
        assert balance.formatted_balance == "1.000000"
        assert balance.raw_balance == 1000000

    @patch('app.services.blockchain.Web3')
    def test_balance_large_amount(self, mock_web3):
        """Should handle large balance correctly."""
        mock_w3 = MagicMock()
        mock_web3.return_value = mock_w3
        mock_w3.is_connected.return_value = True
        mock_w3.is_checksum_address.return_value = False
        mock_w3.to_checksum_address.return_value = "0x680fa9c2689b9D045Cee214E7d748D085bb80B19"

        mock_contract = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract
        # 1234.567 USDC.e (1234567 * 10^6 = 1234567000000) - wait, 1234.567 * 10^6 = 1234567000
        mock_contract.functions.balanceOf.return_value.call.return_value = 1234567000
        mock_contract.functions.decimals.return_value.call.return_value = 6

        client = BlockchainClient(rpc_url="https://fake.rpc.com")
        balance = client.get_usdc_e_balance("0x680fa9c2689b9D045Cee214E7d748D085bb80B19")

        assert balance.usdc_e_balance == Decimal("1234.567")
        assert balance.formatted_balance == "1234.567000"

    @patch('app.services.blockchain.Web3')
    def test_balance_zero(self, mock_web3):
        """Should handle zero balance."""
        mock_w3 = MagicMock()
        mock_web3.return_value = mock_w3
        mock_w3.is_connected.return_value = True
        mock_w3.is_checksum_address.return_value = False
        mock_w3.to_checksum_address.return_value = "0x680fa9c2689b9D045Cee214E7d748D085bb80B19"

        mock_contract = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract
        mock_contract.functions.balanceOf.return_value.call.return_value = 0
        mock_contract.functions.decimals.return_value.call.return_value = 6

        client = BlockchainClient(rpc_url="https://fake.rpc.com")
        balance = client.get_usdc_e_balance("0x680fa9c2689b9D045Cee214E7d748D085bb80B19")

        assert balance.usdc_e_balance == Decimal("0")
        assert balance.formatted_balance == "0.000000"


class TestSingleton:
    """Tests for singleton pattern."""

    def test_get_blockchain_client_returns_instance(self):
        """Should return blockchain client instance."""
        client = get_blockchain_client()
        assert isinstance(client, BlockchainClient)

    def test_get_blockchain_client_singleton(self):
        """Should return same instance on multiple calls."""
        client1 = get_blockchain_client()
        client2 = get_blockchain_client()
        assert client1 is client2
