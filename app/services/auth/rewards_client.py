"""
Rewards API Client for Polymarket.

Handles rewards, earnings, and market reward configurations.
"""
from typing import Optional, Any
from app.services.auth.base import AuthenticatedClient


class RewardsClient(AuthenticatedClient):
    """
    Async client for Polymarket Rewards API.

    Base URL: https://clob.polymarket.com
    Requires authentication.
    """

    def __init__(self, api_key: Optional[str] = None):
        super().__init__("https://clob.polymarket.com", api_key)

    async def get_current_rewards_configurations(
        self, signature: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Get current active rewards configurations.

        Args:
            signature: Wallet signature if required

        Returns:
            List of reward configurations
        """
        url = self._build_url("/rewards/configs")
        return await self._get(url, wallet_sig=signature)

    async def get_raw_rewards_for_market(
        self, market: str, signature: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Get raw rewards for a specific market.

        Args:
            market: Market condition ID
            signature: Wallet signature if required

        Returns:
            Raw rewards data
        """
        url = self._build_url("/rewards/raw")
        params = {"market": market}
        return await self._get(url, wallet_sig=signature, params=params)

    async def get_markets_with_rewards(
        self, signature: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Get multiple markets with rewards.

        Args:
            signature: Wallet signature if required

        Returns:
            List of markets with rewards
        """
        url = self._build_url("/rewards/markets")
        return await self._get(url, wallet_sig=signature)

    async def get_earnings_by_date(
        self,
        user: str,
        start_date: str,
        end_date: str,
        signature: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Get earnings for user by date range.

        Args:
            user: User wallet address
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            signature: Wallet signature if required

        Returns:
            List of earnings records
        """
        url = self._build_url("/rewards/earnings")
        params = {
            "user": user.lower(),
            "start_date": start_date,
            "end_date": end_date,
        }
        return await self._get(url, wallet_sig=signature, params=params)

    async def get_total_earnings_by_date(
        self,
        user: str,
        start_date: str,
        end_date: str,
        signature: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Get total earnings for user by date range.

        Args:
            user: User wallet address
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            signature: Wallet signature if required

        Returns:
            Total earnings data
        """
        url = self._build_url("/rewards/earnings/total")
        params = {
            "user": user.lower(),
            "start_date": start_date,
            "end_date": end_date,
        }
        return await self._get(url, wallet_sig=signature, params=params)

    async def get_reward_percentages(
        self, user: str, signature: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Get reward percentages for user.

        Args:
            user: User wallet address
            signature: Wallet signature if required

        Returns:
            Reward percentages data
        """
        url = self._build_url("/rewards/percentages")
        params = {"user": user.lower()}
        return await self._get(url, wallet_sig=signature, params=params)

    async def get_user_earnings_and_config(
        self, user: str, signature: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Get user earnings and markets configuration.

        Args:
            user: User wallet address
            signature: Wallet signature if required

        Returns:
            User earnings and config data
        """
        url = self._build_url("/rewards/user")
        params = {"user": user.lower()}
        return await self._get(url, wallet_sig=signature, params=params)


# Singleton instance
_rewards_client: Optional[RewardsClient] = None


def get_rewards_client(api_key: Optional[str] = None) -> RewardsClient:
    """Get the singleton Rewards client instance."""
    global _rewards_client
    if _rewards_client is None or api_key:
        _rewards_client = RewardsClient(api_key)
    return _rewards_client


async def close_rewards_client() -> None:
    """Close the Rewards client connection."""
    global _rewards_client
    if _rewards_client is not None:
        await _rewards_client.close()
        _rewards_client = None
