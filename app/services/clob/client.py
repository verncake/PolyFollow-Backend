"""
CLOB API Client for Polymarket.

Handles market data: Order books, prices, spreads, last trade prices.
"""
from typing import Optional, Any
from app.services.base import BasePolymarketClient, PolymarketAPIError


class ClobClient(BasePolymarketClient):
    """
    Async client for Polymarket CLOB API.

    Base URL: https://clob.polymarket.com
    """

    def __init__(self):
        super().__init__("https://clob.polymarket.com")

    # ====================
    # Market Data API
    # ====================

    async def get_server_time(self) -> dict[str, Any]:
        """
        Get CLOB server time.

        Returns:
            Server time object
        """
        url = self._build_url("/time")
        return await self._request_with_retry("GET", url)

    async def get_orderbook(self, token_id: str) -> dict[str, Any]:
        """
        Get order book for a token.

        Args:
            token_id: The ERC-1155 token ID

        Returns:
            Order book with bids and asks
        """
        url = self._build_url("/book")
        params = {"token_id": token_id}
        return await self._request_with_retry("GET", url, params=params)

    async def get_orderbooks(self, token_ids: list[str]) -> list[dict[str, Any]]:
        """
        Get order books for multiple tokens.

        Args:
            token_ids: List of ERC-1155 token IDs

        Returns:
            List of order books
        """
        url = self._build_url("/books")
        params = {"token_ids": ",".join(token_ids)}
        return await self._request_with_retry("GET", url, params=params)

    async def get_prices(
        self, token_ids: list[str], sides: Optional[list[str]] = None
    ) -> list[dict[str, Any]]:
        """
        Get prices for tokens.

        Args:
            token_ids: List of token IDs
            sides: Optional list of sides (BUY/SELL)

        Returns:
            List of price objects
        """
        url = self._build_url("/prices")
        params = {"token_ids": ",".join(token_ids)}
        if sides:
            params["sides"] = ",".join(sides)
        return await self._request_with_retry("GET", url, params=params)

    async def get_market_price(
        self, token_id: str, side: Optional[str] = None
    ) -> Optional[float]:
        """
        Get market price for a token.

        Args:
            token_id: The token ID
            side: Optional BUY or SELL

        Returns:
            Market price or None
        """
        url = self._build_url("/price")
        params = {"token_id": token_id}
        if side:
            params["side"] = side
        try:
            data = await self._request_with_retry("GET", url, params=params)
            if isinstance(data, dict):
                return data.get("price")
            return None
        except PolymarketAPIError:
            return None

    async def get_prices_history(
        self,
        market: str,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        interval: Optional[str] = None,
        fidelity: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Get prices history for a market.

        Args:
            market: Market slug or ID
            start_ts: Start timestamp
            end_ts: End timestamp
            interval: Interval (1m, 5m, 15m, 1h, 4h, 1d)
            fidelity: Fidelity setting

        Returns:
            List of price history data points
        """
        url = self._build_url("/prices-history")
        params = {"market": market}
        if start_ts:
            params["startTs"] = start_ts
        if end_ts:
            params["endTs"] = end_ts
        if interval:
            params["interval"] = interval
        if fidelity:
            params["fidelity"] = fidelity
        return await self._request_with_retry("GET", url, params=params)

    async def get_midpoint_price(self, token_id: str) -> Optional[float]:
        """
        Get midpoint price for a token.

        Args:
            token_id: The token ID

        Returns:
            Midpoint price or None
        """
        url = self._build_url("/midpoint")
        params = {"token_id": token_id}
        try:
            data = await self._request_with_retry("GET", url, params=params)
            if isinstance(data, dict):
                return data.get("midpoint")
            return None
        except PolymarketAPIError:
            return None

    async def get_midpoint_prices(
        self, token_ids: list[str]
    ) -> list[dict[str, Any]]:
        """
        Get midpoint prices for multiple tokens.

        Args:
            token_ids: List of token IDs

        Returns:
            List of midpoint price objects
        """
        url = self._build_url("/midpoints")
        params = {"token_ids": ",".join(token_ids)}
        return await self._request_with_retry("GET", url, params=params)

    async def get_spread(self, token_id: str) -> Optional[dict[str, Any]]:
        """
        Get bid-ask spread for a token.

        Args:
            token_id: The token ID

        Returns:
            Spread object or None
        """
        url = self._build_url("/spread")
        params = {"token_id": token_id}
        try:
            return await self._request_with_retry("GET", url, params=params)
        except PolymarketAPIError:
            return None

    async def get_spreads(self, token_ids: list[str]) -> list[dict[str, Any]]:
        """
        Get spreads for multiple tokens.

        Args:
            token_ids: List of token IDs

        Returns:
            List of spread objects
        """
        url = self._build_url("/spreads")
        params = {"token_ids": ",".join(token_ids)}
        return await self._request_with_retry("GET", url, params=params)

    async def get_last_trade_price(self, token_id: str) -> Optional[float]:
        """
        Get last trade price for a token.

        Args:
            token_id: The token ID

        Returns:
            Last trade price or None
        """
        url = self._build_url("/last-trade-price")
        params = {"token_id": token_id}
        try:
            data = await self._request_with_retry("GET", url, params=params)
            if isinstance(data, dict):
                return data.get("price")
            return None
        except PolymarketAPIError:
            return None

    async def get_last_trade_prices(
        self, token_ids: list[str]
    ) -> list[dict[str, Any]]:
        """
        Get last trade prices for multiple tokens.

        Args:
            token_ids: List of token IDs

        Returns:
            List of last trade price objects
        """
        url = self._build_url("/last-trades-prices")
        params = {"token_ids": ",".join(token_ids)}
        return await self._request_with_retry("GET", url, params=params)

    # ====================
    # Fee & Tick Size API
    # ====================

    async def get_fee_rate(self, token_id: Optional[str] = None) -> Optional[float]:
        """
        Get fee rate for a token (query parameter version).

        Args:
            token_id: Optional token ID

        Returns:
            Fee rate or None
        """
        url = self._build_url("/fee-rate")
        params = {}
        if token_id:
            params["token_id"] = token_id
        try:
            data = await self._request_with_retry("GET", url, params=params)
            if isinstance(data, dict):
                return data.get("fee")
            return None
        except PolymarketAPIError:
            return None

    async def get_fee_rate_by_token(self, token_id: str) -> Optional[float]:
        """
        Get fee rate for a token (path parameter version).

        Args:
            token_id: Token ID

        Returns:
            Fee rate or None
        """
        url = self._build_url(f"/fee-rate/{token_id}")
        try:
            data = await self._request_with_retry("GET", url)
            if isinstance(data, dict):
                return data.get("base_fee")
            return None
        except PolymarketAPIError:
            return None

    async def get_tick_size(self, token_id: Optional[str] = None) -> Optional[float]:
        """
        Get tick size for a token (query parameter version).

        Args:
            token_id: Optional token ID

        Returns:
            Tick size or None
        """
        url = self._build_url("/tick-size")
        params = {}
        if token_id:
            params["token_id"] = token_id
        try:
            data = await self._request_with_retry("GET", url, params=params)
            if isinstance(data, dict):
                return data.get("tickSize")
            return None
        except PolymarketAPIError:
            return None

    async def get_tick_size_by_token(self, token_id: str) -> Optional[float]:
        """
        Get tick size for a token (path parameter version).

        Args:
            token_id: Token ID

        Returns:
            Tick size or None
        """
        url = self._build_url(f"/tick-size/{token_id}")
        try:
            data = await self._request_with_retry("GET", url)
            if isinstance(data, dict):
                return data.get("minimum_tick_size")
            return None
        except PolymarketAPIError:
            return None

    async def get_neg_risk(self, token_id: Optional[str] = None) -> Optional[bool]:
        """
        Get neg risk status for a token.

        Args:
            token_id: Optional token ID

        Returns:
            Neg risk status or None
        """
        url = self._build_url("/neg-risk")
        params = {}
        if token_id:
            params["token_id"] = token_id
        try:
            data = await self._request_with_retry("GET", url, params=params)
            if isinstance(data, dict):
                return data.get("negRisk")
            return None
        except PolymarketAPIError:
            return None

    # ====================
    # Simplified Markets API
    # ====================

    async def get_simplified_markets(
        self, next_cursor: Optional[str] = None, limit: int = 100
    ) -> dict[str, Any]:
        """
        Get simplified markets.

        Args:
            next_cursor: Pagination cursor
            limit: Max number of markets

        Returns:
            Market data with cursor
        """
        url = self._build_url("/simplified-markets")
        params = {"limit": limit}
        if next_cursor:
            params["next_cursor"] = next_cursor
        return await self._request_with_retry("GET", url, params=params)

    async def get_sampling_markets(
        self, next_cursor: Optional[str] = None, limit: int = 100
    ) -> dict[str, Any]:
        """
        Get sampling markets.

        Args:
            next_cursor: Pagination cursor
            limit: Max number of markets

        Returns:
            Market data with cursor
        """
        url = self._build_url("/sampling-markets")
        params = {"limit": limit}
        if next_cursor:
            params["next_cursor"] = next_cursor
        return await self._request_with_retry("GET", url, params=params)

    async def get_sampling_simplified_markets(
        self, next_cursor: Optional[str] = None, limit: int = 100
    ) -> dict[str, Any]:
        """
        Get sampling simplified markets.

        Args:
            next_cursor: Pagination cursor
            limit: Max number of markets

        Returns:
            Market data with cursor
        """
        url = self._build_url("/sampling-simplified-markets")
        params = {"limit": limit}
        if next_cursor:
            params["next_cursor"] = next_cursor
        return await self._request_with_retry("GET", url, params=params)


# Singleton instance
_clob_client: Optional[ClobClient] = None


def get_clob_client() -> ClobClient:
    """Get the singleton CLOB client instance."""
    global _clob_client
    if _clob_client is None:
        _clob_client = ClobClient()
    return _clob_client


async def close_clob_client() -> None:
    """Close the CLOB client connection."""
    global _clob_client
    if _clob_client is not None:
        await _clob_client.close()
        _clob_client = None
