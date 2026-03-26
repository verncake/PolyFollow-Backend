"""
Bridge API Client for Polymarket.

Handles asset bridging: deposits, withdrawals, quotes.
"""
from typing import Optional, Any
from app.services.auth.base import AuthenticatedClient


class BridgeClient(AuthenticatedClient):
    """
    Async client for Polymarket Bridge API.

    Base URL: https://clob.polymarket.com
    Requires authentication.
    """

    def __init__(self, api_key: Optional[str] = None):
        super().__init__("https://clob.polymarket.com", api_key)

    async def get_supported_assets(self) -> list[dict[str, Any]]:
        """
        Get list of supported assets for bridging.

        Returns:
            List of supported asset objects
        """
        url = self._build_url("/bridge/assets")
        return await self._get(url)

    async def create_deposit_address(
        self, asset: str, amount: str, signature: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Create a deposit address for bridging.

        Args:
            asset: Asset symbol (e.g., 'USDC')
            amount: Amount to deposit
            signature: Wallet signature if required

        Returns:
            Deposit address response
        """
        url = self._build_url("/bridge/deposit-address")
        data = {"asset": asset, "amount": amount}
        return await self._post(url, wallet_sig=signature, json=data)

    async def get_quote(
        self,
        from_asset: str,
        to_asset: str,
        amount: str,
        signature: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Get a quote for bridging.

        Args:
            from_asset: Source asset
            to_asset: Target asset
            amount: Amount to bridge
            signature: Wallet signature if required

        Returns:
            Quote response
        """
        url = self._build_url("/bridge/quote")
        data = {
            "from_asset": from_asset,
            "to_asset": to_asset,
            "amount": amount,
        }
        return await self._post(url, wallet_sig=signature, json=data)

    async def get_transaction_status(
        self, transaction_id: str, signature: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Get status of a bridge transaction.

        Args:
            transaction_id: Transaction ID
            signature: Wallet signature if required

        Returns:
            Transaction status
        """
        url = self._build_url(f"/bridge/transaction/{transaction_id}")
        return await self._get(url, wallet_sig=signature)

    async def create_withdrawal_address(
        self,
        asset: str,
        amount: str,
        destination: str,
        signature: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Create a withdrawal address.

        Args:
            asset: Asset symbol
            amount: Amount to withdraw
            destination: Withdrawal destination address
            signature: Wallet signature if required

        Returns:
            Withdrawal response
        """
        url = self._build_url("/bridge/withdrawal-address")
        data = {
            "asset": asset,
            "amount": amount,
            "destination": destination,
        }
        return await self._post(url, wallet_sig=signature, json=data)


# Singleton instance
_bridge_client: Optional[BridgeClient] = None


def get_bridge_client(api_key: Optional[str] = None) -> BridgeClient:
    """Get the singleton Bridge client instance."""
    global _bridge_client
    if _bridge_client is None or api_key:
        _bridge_client = BridgeClient(api_key)
    return _bridge_client


async def close_bridge_client() -> None:
    """Close the Bridge client connection."""
    global _bridge_client
    if _bridge_client is not None:
        await _bridge_client.close()
        _bridge_client = None
