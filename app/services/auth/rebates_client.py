"""
Rebates API Client for Polymarket.

Handles maker rebate information.
"""
from typing import Optional, Any
from app.services.auth.base import AuthenticatedClient


class RebatesClient(AuthenticatedClient):
    """
    Async client for Polymarket Rebates API.

    Base URL: https://clob.polymarket.com
    Requires authentication.
    """

    def __init__(self, api_key: Optional[str] = None):
        super().__init__("https://clob.polymarket.com", api_key)

    async def get_current_rebated_fees(
        self, signature: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Get current rebated fees for a maker.

        Args:
            signature: Wallet signature if required

        Returns:
            Current rebate data
        """
        url = self._build_url("/rebates/current")
        return await self._get(url, wallet_sig=signature)


# Singleton instance
_rebates_client: Optional[RebatesClient] = None


def get_rebates_client(api_key: Optional[str] = None) -> RebatesClient:
    """Get the singleton Rebates client instance."""
    global _rebates_client
    if _rebates_client is None or api_key:
        _rebates_client = RebatesClient(api_key)
    return _rebates_client


async def close_rebates_client() -> None:
    """Close the Rebates client connection."""
    global _rebates_client
    if _rebates_client is not None:
        await _rebates_client.close()
        _rebates_client = None
