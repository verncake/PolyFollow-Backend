"""
Blockchain Service - Polygon USDC.e Balance Queries.

Queries on-chain ERC20 token balances using Polygon RPC.
Supports custom RPC endpoints via POLYGON_RPC_URL environment variable.
"""
import os
from decimal import Decimal
from typing import Optional
from dataclasses import dataclass

from web3 import Web3


# USDC.e (PoS USDC on Polygon) - ERC20 token address
USDC_E_ADDRESS = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"

# Standard ERC20 ABI - only what we need
ERC20_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]


@dataclass
class WalletBalance:
    """Wallet balance information."""
    address: str
    usdc_e_balance: Decimal  # USDC.e on Polygon
    formatted_balance: str  # Human readable with 6 decimals
    raw_balance: int  # Raw token amount (includes decimals)


class BlockchainClient:
    """
    Client for querying blockchain state.

    Currently supports:
    - USDC.e balance on Polygon
    """

    # Fallback public RPCs (free, rate-limited)
    FALLBACK_RPCS = [
        "https://polygon.llamarpc.com",
        "https://rpc.ankr.com/polygon",
    ]

    def __init__(self, rpc_url: Optional[str] = None):
        """
        Initialize blockchain client.

        Args:
            rpc_url: Polygon RPC URL. Defaults to POLYGON_RPC_URL env var,
                     then falls back to public RPCs.
        """
        self.rpc_url = rpc_url or os.getenv("POLYGON_RPC_URL")
        self._web3: Optional[Web3] = None

    def _get_web3(self) -> Web3:
        """Get or create Web3 instance with automatic failover."""
        if self._web3 is None:
            # Try configured RPC first, then fallbacks
            rpcs = []
            if self.rpc_url:
                rpcs.append(self.rpc_url)
            rpcs.extend(self.FALLBACK_RPCS)

            for rpc in rpcs:
                try:
                    w3 = Web3(Web3.HTTPProvider(rpc))
                    if w3.is_connected():
                        self._web3 = w3
                        self.rpc_url = rpc
                        break
                except Exception:
                    continue
            else:
                # No working RPC found
                self._web3 = Web3(Web3.HTTPProvider(rpcs[0]))

        return self._web3

    def is_connected(self) -> bool:
        """Check if RPC connection is healthy."""
        try:
            w3 = self._get_web3()
            return w3.is_connected()
        except Exception:
            return False

    def get_usdc_e_balance(self, address: str) -> WalletBalance:
        """
        Get USDC.e (PoS USDC) balance on Polygon.

        Args:
            address: Wallet address

        Returns:
            WalletBalance with USDC.e info

        Raises:
            Web3ConnectionError: If no RPC is reachable
        """
        w3 = self._get_web3()

        # Normalize address to checksum
        address = address.lower().strip()
        if not w3.is_checksum_address(address):
            address = w3.to_checksum_address(address)

        # Create contract instance
        contract = w3.eth.contract(
            address=w3.to_checksum_address(USDC_E_ADDRESS),
            abi=ERC20_ABI
        )

        # Fetch balance and decimals
        raw_balance: int = contract.functions.balanceOf(address).call()
        decimals: int = contract.functions.decimals().call()

        # Convert to Decimal for precision
        balance = Decimal(raw_balance) / Decimal(10 ** decimals)

        return WalletBalance(
            address=address,
            usdc_e_balance=balance,
            formatted_balance=f"{balance:.6f}",
            raw_balance=raw_balance,
        )


# Singleton instance
_blockchain_client: Optional[BlockchainClient] = None


def get_blockchain_client() -> BlockchainClient:
    """Get the singleton blockchain client instance."""
    global _blockchain_client
    if _blockchain_client is None:
        _blockchain_client = BlockchainClient()
    return _blockchain_client
