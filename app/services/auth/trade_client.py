"""
Authenticated Trade API Client for Polymarket.

Handles trading operations: orders, trades, heartbeat.
Requires API Key and/or wallet signature authentication.
"""
from typing import Optional, Any
from app.services.auth.base import AuthenticatedClient


class TradeClient(AuthenticatedClient):
    """
    Async client for Polymarket Trade API.

    Base URL: https://clob.polymarket.com
    Requires authentication via API Key and/or wallet signature.
    """

    def __init__(self, api_key: Optional[str] = None):
        super().__init__("https://clob.polymarket.com", api_key)

    # ====================
    # Order Management
    # ====================

    async def post_order(
        self,
        token_id: str,
        side: str,
        size: str,
        price: str,
        signature: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Post a new order.

        Args:
            token_id: ERC-1155 token ID
            side: BUY or SELL
            size: Order size
            price: Order price
            signature: Wallet signature if required

        Returns:
            Order response
        """
        url = self._build_url("/order")
        data = {
            "token_id": token_id,
            "side": side,
            "size": size,
            "price": price,
        }
        return await self._post(url, wallet_sig=signature, json=data)

    async def cancel_order(
        self, order_id: str, signature: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Cancel a single order.

        Args:
            order_id: Order ID to cancel
            signature: Wallet signature if required

        Returns:
            Cancel response
        """
        url = self._build_url("/order")
        data = {"orderID": order_id}
        return await self._delete(url, wallet_sig=signature, json=data)

    async def get_order_by_id(
        self, order_id: str, signature: Optional[str] = None
    ) -> Optional[dict[str, Any]]:
        """
        Get a single order by ID.

        Args:
            order_id: Order ID
            signature: Wallet signature if required

        Returns:
            Order object or None
        """
        url = self._build_url(f"/order/{order_id}")
        try:
            return await self._get(url, wallet_sig=signature)
        except PolymarketAPIError as e:
            if e.status_code == 404:
                return None
            raise

    async def post_orders(
        self, orders: list[dict], signature: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Post multiple orders (max 15).

        Args:
            orders: List of order objects
            signature: Wallet signature if required

        Returns:
            List of order responses
        """
        url = self._build_url("/orders")
        return await self._post(url, wallet_sig=signature, json={"orders": orders})

    async def get_orders(
        self, signature: Optional[str] = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """
        Get user orders.

        Args:
            signature: Wallet signature if required
            limit: Max number of orders

        Returns:
            List of order objects
        """
        url = self._build_url("/orders")
        params = {"limit": limit}
        return await self._get(url, wallet_sig=signature, params=params)

    async def cancel_orders(
        self, order_ids: list[str], signature: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Cancel multiple orders.

        Args:
            order_ids: List of order IDs to cancel
            signature: Wallet signature if required

        Returns:
            Cancel response
        """
        url = self._build_url("/orders")
        data = {"orderIDs": order_ids}
        return await self._delete(url, wallet_sig=signature, json=data)

    async def cancel_all_orders(self, signature: Optional[str] = None) -> dict[str, Any]:
        """
        Cancel all orders.

        Args:
            signature: Wallet signature if required

        Returns:
            Cancel response
        """
        url = self._build_url("/cancel-all")
        return await self._delete(url, wallet_sig=signature)

    async def cancel_market_orders(
        self, condition_id: str, signature: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Cancel all orders for a market.

        Args:
            condition_id: Market condition ID
            signature: Wallet signature if required

        Returns:
            Cancel response
        """
        url = self._build_url("/cancel-market-orders")
        data = {"condition_id": condition_id}
        return await self._delete(url, wallet_sig=signature, json=data)

    async def get_order_scoring_status(
        self, order_ids: list[str], signature: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Get order scoring status.

        Args:
            order_ids: List of order IDs
            signature: Wallet signature if required

        Returns:
            Scoring status response
        """
        url = self._build_url("/order/scoring-status")
        params = {"orderIDs": ",".join(order_ids)}
        return await self._get(url, wallet_sig=signature, params=params)

    async def send_heartbeat(
        self, order_ids: list[str], signature: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Send heartbeat for orders.

        Args:
            order_ids: List of order IDs
            signature: Wallet signature if required

        Returns:
            Heartbeat response
        """
        url = self._build_url("/order/heartbeat")
        data = {"orderIDs": order_ids}
        return await self._post(url, wallet_sig=signature, json=data)

    # ====================
    # Trades (Authenticated)
    # ====================

    async def get_trades(
        self,
        market: Optional[str] = None,
        user: Optional[str] = None,
        limit: int = 100,
        signature: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Get trades (authenticated version).

        Args:
            market: Filter by market
            user: Filter by user
            limit: Max number of trades
            signature: Wallet signature if required

        Returns:
            List of trade objects
        """
        url = self._build_url("/trades")
        params = {"limit": limit}
        if market:
            params["market"] = market
        if user:
            params["user"] = user.lower()
        return await self._get(url, wallet_sig=signature, params=params)

    async def get_builder_trades(
        self, signature: Optional[str] = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """
        Get builder trades.

        Args:
            signature: Wallet signature if required
            limit: Max number of trades

        Returns:
            List of builder trade objects
        """
        url = self._build_url("/builder/trades")
        params = {"limit": limit}
        return await self._get(url, wallet_sig=signature, params=params)


# Singleton instance
_trade_client: Optional[TradeClient] = None


def get_trade_client(api_key: Optional[str] = None) -> TradeClient:
    """Get the singleton Trade client instance."""
    global _trade_client
    if _trade_client is None or api_key:
        _trade_client = TradeClient(api_key)
    return _trade_client


async def close_trade_client() -> None:
    """Close the Trade client connection."""
    global _trade_client
    if _trade_client is not None:
        await _trade_client.close()
        _trade_client = None
