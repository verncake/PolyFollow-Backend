"""
Relayer API Client for Polymarket.

Handles transaction submission, nonce management, and Safe deployment.
"""
from typing import Optional, Any
from app.services.auth.base import AuthenticatedClient


class RelayerClient(AuthenticatedClient):
    """
    Async client for Polymarket Relayer API.

    Base URL: https://clob.polymarket.com
    Requires authentication.
    """

    def __init__(self, api_key: Optional[str] = None):
        super().__init__("https://clob.polymarket.com", api_key)

    async def submit_transaction(
        self, transaction: dict, signature: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Submit a transaction via relayer.

        Args:
            transaction: Transaction object
            signature: Wallet signature if required

        Returns:
            Transaction submission response
        """
        url = self._build_url("/relayer/submit")
        return await self._post(url, wallet_sig=signature, json=transaction)

    async def get_transaction_by_id(
        self, transaction_id: str, signature: Optional[str] = None
    ) -> Optional[dict[str, Any]]:
        """
        Get a transaction by ID.

        Args:
            transaction_id: Transaction ID
            signature: Wallet signature if required

        Returns:
            Transaction object or None
        """
        url = self._build_url(f"/relayer/transaction/{transaction_id}")
        try:
            return await self._get(url, wallet_sig=signature)
        except PolymarketAPIError as e:
            if e.status_code == 404:
                return None
            raise

    async def get_recent_transactions(
        self, user: str, limit: int = 50, signature: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Get recent transactions for a user.

        Args:
            user: User wallet address
            limit: Max number of transactions
            signature: Wallet signature if required

        Returns:
            List of transaction objects
        """
        url = self._build_url("/relayer/transactions")
        params = {"user": user.lower(), "limit": limit}
        return await self._get(url, wallet_sig=signature, params=params)

    async def get_current_nonce(self, user: str) -> int:
        """
        Get current nonce for a user.

        Args:
            user: User wallet address

        Returns:
            Current nonce value
        """
        url = self._build_url("/relayer/nonce")
        params = {"user": user.lower()}
        data = await self._get(url, params=params)
        return data.get("nonce", 0)

    async def get_relayer_info(self) -> dict[str, Any]:
        """
        Get relayer address and nonce.

        Returns:
            Relayer info
        """
        url = self._build_url("/relayer/info")
        return await self._get(url)

    async def check_safe_deployed(self, address: str) -> bool:
        """
        Check if a Safe is deployed for an address.

        Args:
            address: Wallet address

        Returns:
            True if Safe is deployed
        """
        url = self._build_url("/relayer/safe")
        params = {"address": address.lower()}
        data = await self._get(url, params=params)
        return data.get("deployed", False)

    # ====================
    # Relayer API Keys
    # ====================

    async def get_all_api_keys(self, signature: Optional[str] = None) -> list[dict[str, Any]]:
        """
        Get all relayer API keys for the authenticated user.

        Args:
            signature: Wallet signature if required

        Returns:
            List of API key objects
        """
        url = self._build_url("/relayer/api-keys")
        return await self._get(url, wallet_sig=signature)


# Singleton instance
_relayer_client: Optional[RelayerClient] = None


def get_relayer_client(api_key: Optional[str] = None) -> RelayerClient:
    """Get the singleton Relayer client instance."""
    global _relayer_client
    if _relayer_client is None or api_key:
        _relayer_client = RelayerClient(api_key)
    return _relayer_client


async def close_relayer_client() -> None:
    """Close the Relayer client connection."""
    global _relayer_client
    if _relayer_client is not None:
        await _relayer_client.close()
        _relayer_client = None
