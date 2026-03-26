"""
Data API Client for Polymarket.

Handles public user data: Positions, Trades, Activity, Leaderboard, Holders.
"""
from typing import Optional, Any
from app.services.base import BasePolymarketClient, PolymarketAPIError


class DataClient(BasePolymarketClient):
    """
    Async client for Polymarket Data API.

    Base URL: https://data-api.polymarket.com
    """

    def __init__(self):
        super().__init__("https://data-api.polymarket.com")

    # ====================
    # Positions API
    # ====================

    async def get_positions(
        self,
        user: str,
        market: Optional[str] = None,
        event_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: Optional[str] = None,
        sort_direction: str = "DESC",
        redeemable: bool = False,
        mergeable: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Get current positions for a user.

        Args:
            user: Wallet address
            market: Filter by condition ID
            event_id: Filter by event ID
            limit: Max number of positions
            offset: Pagination offset
            sort_by: Sort field (TOKENS, CASHPNL, PERCENTPNL, etc.)
            sort_direction: ASC or DESC
            redeemable: Include redeemable positions
            mergeable: Include mergeable positions

        Returns:
            List of position objects
        """
        url = self._build_url("/positions")
        params = {
            "user": user.lower(),
            "limit": limit,
            "offset": offset,
            "sortDirection": sort_direction,
            "redeemable": redeemable,
            "mergeable": mergeable,
        }
        if market:
            params["market"] = market
        if event_id:
            params["eventId"] = event_id
        if sort_by:
            params["sortBy"] = sort_by
        return await self._request_with_retry("GET", url, params=params)

    async def get_closed_positions(
        self,
        user: str,
        market: Optional[str] = None,
        title: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: Optional[str] = None,
        sort_direction: str = "DESC",
    ) -> list[dict[str, Any]]:
        """
        Get closed positions for a user.

        Args:
            user: Wallet address
            market: Filter by condition ID
            title: Filter by market title
            limit: Max number of positions (max 50)
            offset: Pagination offset
            sort_by: Sort field (REALIZEDPNL, TITLE, PRICE, AVGPRICE, TIMESTAMP)
            sort_direction: ASC or DESC

        Returns:
            List of closed position objects
        """
        url = self._build_url("/closed-positions")
        params = {
            "user": user.lower(),
            "limit": min(limit, 50),
            "offset": offset,
            "sortDirection": sort_direction,
        }
        if market:
            params["market"] = market
        if title:
            params["title"] = title
        if sort_by:
            params["sortBy"] = sort_by
        return await self._request_with_retry("GET", url, params=params)

    async def get_total_value(
        self, user: str, market: Optional[str] = None
    ) -> Optional[float]:
        """
        Get total value of a user's positions.

        Args:
            user: Wallet address
            market: Optional specific market

        Returns:
            Total value or None
        """
        url = self._build_url("/value")
        params = {"user": user.lower()}
        if market:
            params["market"] = market
        try:
            data = await self._request_with_retry("GET", url, params=params)
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("value")
            return None
        except PolymarketAPIError:
            return None

    async def get_market_positions(
        self,
        condition_id: str,
        user: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: Optional[str] = None,
        sort_direction: str = "DESC",
    ) -> list[dict[str, Any]]:
        """
        Get all positions for a specific market.

        Args:
            condition_id: Market condition ID
            user: Optional user filter
            status: Filter by status
            limit: Max number of positions
            offset: Pagination offset
            sort_by: Sort field
            sort_direction: ASC or DESC

        Returns:
            List of market position objects
        """
        url = self._build_url("/v1/market-positions")
        params = {"market": condition_id, "limit": limit, "offset": offset}
        if user:
            params["user"] = user.lower()
        if status:
            params["status"] = status
        if sort_by:
            params["sortBy"] = sort_by
            params["sortDirection"] = sort_direction
        return await self._request_with_retry("GET", url, params=params)

    async def get_top_holders(
        self, market: str, limit: int = 20, min_balance: float = 1.0
    ) -> list[dict[str, Any]]:
        """
        Get top holders for a market.

        Args:
            market: Condition ID
            limit: Max number of holders (max 20)
            min_balance: Minimum balance filter

        Returns:
            List of holder objects
        """
        url = self._build_url("/holders")
        params = {
            "market": market,
            "limit": min(limit, 20),
            "minBalance": min_balance,
        }
        return await self._request_with_retry("GET", url, params=params)

    # ====================
    # Trades API
    # ====================

    async def get_trades(
        self,
        user: Optional[str] = None,
        market: Optional[str] = None,
        event_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        side: Optional[str] = None,
        taker_only: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Get trades for a user or market.

        Args:
            user: Filter by wallet address
            market: Filter by condition ID
            event_id: Filter by event ID
            limit: Max number of trades
            offset: Pagination offset
            side: Filter by BUY or SELL
            taker_only: Only taker trades

        Returns:
            List of trade objects
        """
        url = self._build_url("/trades")
        params = {"limit": limit, "offset": offset, "takerOnly": taker_only}
        if user:
            params["user"] = user.lower()
        if market:
            params["market"] = market
        if event_id:
            params["eventId"] = event_id
        if side:
            params["side"] = side
        return await self._request_with_retry("GET", url, params=params)

    async def get_markets_traded_count(self, user: str) -> Optional[int]:
        """
        Get total number of markets a user has traded.

        Args:
            user: Wallet address

        Returns:
            Number of markets traded or None
        """
        url = self._build_url("/traded")
        params = {"user": user.lower()}
        try:
            data = await self._request_with_retry("GET", url, params=params)
            if isinstance(data, dict):
                return data.get("traded")
            return None
        except PolymarketAPIError:
            return None

    # ====================
    # Activity API
    # ====================

    async def get_activity(
        self,
        user: str,
        market: Optional[str] = None,
        event_id: Optional[str] = None,
        activity_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        start: Optional[int] = None,
        end: Optional[int] = None,
        side: Optional[str] = None,
        sort_by: str = "TIMESTAMP",
        sort_direction: str = "DESC",
    ) -> list[dict[str, Any]]:
        """
        Get user activity history.

        Args:
            user: Wallet address
            market: Filter by condition ID
            event_id: Filter by event ID
            activity_type: Filter by type (TRADE, SPLIT, MERGE, REDEEM, REWARD, etc.)
            limit: Max number of activities
            offset: Pagination offset
            start: Start timestamp
            end: End timestamp
            side: Filter by BUY or SELL
            sort_by: Sort field (TIMESTAMP, TOKENS, CASH)
            sort_direction: ASC or DESC

        Returns:
            List of activity objects
        """
        url = self._build_url("/activity")
        params = {
            "user": user.lower(),
            "limit": limit,
            "offset": offset,
            "sortBy": sort_by,
            "sortDirection": sort_direction,
        }
        if market:
            params["market"] = market
        if event_id:
            params["eventId"] = event_id
        if activity_type:
            params["type"] = activity_type
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if side:
            params["side"] = side
        return await self._request_with_retry("GET", url, params=params)

    # ====================
    # Leaderboard API
    # ====================

    async def get_leaderboard(
        self,
        category: Optional[str] = None,
        time_period: Optional[str] = None,
        order_by: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
        user: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Get trader leaderboard rankings.

        Args:
            category: Filter by category
            time_period: Time period (24h, 7d, 30d, allTime) - optional
            order_by: Order by field (pnl, volume, etc.) - optional
            limit: Max number of entries
            offset: Pagination offset
            user: Filter by specific user
            user_name: Filter by username

        Returns:
            List of leaderboard entries
        """
        url = self._build_url("/v1/leaderboard")
        params = {
            "limit": min(limit, 200),
            "offset": offset,
        }
        if time_period:
            params["timePeriod"] = time_period
        if order_by:
            params["orderBy"] = order_by
        if category:
            params["category"] = category
        if user:
            params["user"] = user.lower()
        if user_name:
            params["userName"] = user_name
        return await self._request_with_retry("GET", url, params=params)

    # ====================
    # Market Data API
    # ====================

    async def get_open_interest(self, market: str) -> Optional[float]:
        """
        Get open interest for a market.

        Args:
            market: Condition ID

        Returns:
            Open interest value or None
        """
        url = self._build_url("/oi")
        params = {"market": market}
        try:
            data = await self._request_with_retry("GET", url, params=params)
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("openInterest")
            return None
        except PolymarketAPIError:
            return None

    async def get_live_volume(self, event_id: str) -> Optional[float]:
        """
        Get live volume for an event.

        Args:
            event_id: Event ID

        Returns:
            Live volume or None
        """
        url = self._build_url("/live-volume")
        params = {"id": event_id}
        try:
            data = await self._request_with_retry("GET", url, params=params)
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("volume")
            return None
        except PolymarketAPIError:
            return None


# Singleton instance
_data_client: Optional[DataClient] = None


def get_data_client() -> DataClient:
    """Get the singleton Data client instance."""
    global _data_client
    if _data_client is None:
        _data_client = DataClient()
    return _data_client


async def close_data_client() -> None:
    """Close the Data client connection."""
    global _data_client
    if _data_client is not None:
        await _data_client.close()
        _data_client = None
