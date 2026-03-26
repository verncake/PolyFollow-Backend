"""
CLOB API Client using official Polymarket SDK.

Provides market data and trading via py-clob-client SDK.
Note: The py-clob-client SDK is synchronous, so this wrapper provides an async interface
      using asyncio.to_thread to avoid blocking the event loop.
"""
import asyncio
from typing import Optional, Any, List, Dict
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, MarketOrderArgs
import os


def _to_dict(obj: Any) -> Dict[str, Any]:
    """Convert SDK object to dict."""
    if hasattr(obj, '__dict__'):
        return {k: _to_dict(v) for k, v in obj.__dict__.items() if not k.startswith('_')}
    elif isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


class ClobSDKClient:
    """
    Wrapper around py-clob-client SDK for Polymarket CLOB API.

    Supports both public market data and authenticated trading.
    Note: SDK methods are synchronous, this wrapper provides async interface.
    """

    def __init__(
        self,
        private_key: Optional[str] = None,
        address: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        api_passphrase: Optional[str] = None,
        funder: Optional[str] = None,
        signature_type: int = 0,  # 0 = EOA, 1 = POLY_PROXY, 2 = GNOSIS_SAFE
        host: str = "https://clob.polymarket.com",
        chain_id: int = 137,  # Polygon
    ):
        """
        Initialize CLOB SDK client.

        Args:
            private_key: Wallet private key for signing
            address: Wallet address
            api_key: L2 API key (from create_or_derive_api_creds)
            api_secret: L2 API secret
            api_passphrase: L2 API passphrase
            funder: Funder address for proxy wallet
            signature_type: Signature type (0=EOA, 1=POLY_PROXY, 2=GNOSIS_SAFE)
            host: CLOB API host
            chain_id: Chain ID (137 = Polygon)
        """
        self._private_key = private_key or os.getenv("WALLET_PRIVATE_KEY")
        self._address = address or os.getenv("WALLET_ADDRESS")
        self._api_key = api_key or os.getenv("POLYMARKET_API_KEY")
        self._api_secret = api_secret or os.getenv("POLYMARKET_API_SECRET")
        self._api_passphrase = api_passphrase or os.getenv("POLYMARKET_API_PASSPHRASE")
        self._funder = funder or os.getenv("POLYMARKET_FUNDER")
        self._signature_type = signature_type
        self._host = host
        self._chain_id = chain_id
        self._client: Optional[ClobClient] = None

    def _get_client(self) -> ClobClient:
        """Get or create the SDK client."""
        if self._client is None:
            key = self._private_key or os.getenv("WALLET_PRIVATE_KEY")
            if key and self._address:
                self._client = ClobClient(
                    host=self._host,
                    chain_id=self._chain_id,
                    private_key=key,
                    address=self._address,
                    signature_type=self._signature_type,
                    api_key=self._api_key,
                    api_secret=self._api_secret,
                    api_passphrase=self._api_passphrase,
                    funder=self._funder,
                )
            else:
                # Read-only client
                self._client = ClobClient(
                    host=self._host,
                    chain_id=self._chain_id,
                )
        return self._client

    @property
    def client(self) -> ClobClient:
        """Get the underlying SDK client."""
        return self._get_client()

    # ====================
    # Public Market Data
    # ====================

    async def get_server_time(self) -> Dict[str, Any]:
        """Get CLOB server time."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_server_time)
        return _to_dict(result)

    async def get_markets(self, next_cursor: str = "MA==") -> List[Dict[str, Any]]:
        """Get list of markets using cursor pagination."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_markets, next_cursor)
        return _to_dict(result)

    async def get_market(self, market_id: str) -> Dict[str, Any]:
        """Get a specific market."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_market, market_id)
        return _to_dict(result)

    async def get_simplified_markets(self, next_cursor: str = "MA==") -> List[Dict[str, Any]]:
        """Get simplified markets using cursor pagination."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_simplified_markets, next_cursor)
        return _to_dict(result)

    async def get_sampling_markets(self, next_cursor: str = "MA==") -> List[Dict[str, Any]]:
        """Get sampling markets using cursor pagination."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_sampling_markets, next_cursor)
        return _to_dict(result)

    async def get_sampling_simplified_markets(self, next_cursor: str = "MA==") -> List[Dict[str, Any]]:
        """Get sampling simplified markets using cursor pagination."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_sampling_simplified_markets, next_cursor)
        return _to_dict(result)

    async def get_order_book(self, token_id: str) -> Dict[str, Any]:
        """Get order book for a token."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_order_book, token_id)
        return _to_dict(result)

    async def get_order_books(self, token_ids: List[str]) -> List[Dict[str, Any]]:
        """Get order books for multiple tokens."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_order_books, token_ids)
        return _to_dict(result)

    async def get_price(self, token_id: str, side: str) -> float:
        """Get best bid/ask price."""
        client = self._get_client()
        return await asyncio.to_thread(client.get_price, token_id, side)

    async def get_prices(self, token_ids: List[str], sides: List[str]) -> List[Dict[str, Any]]:
        """Get prices for tokens."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_prices, token_ids, sides)
        return _to_dict(result)

    async def get_midpoint(self, token_id: str) -> float:
        """Get mid-market price."""
        client = self._get_client()
        return await asyncio.to_thread(client.get_midpoint, token_id)

    async def get_midpoints(self, token_ids: List[str]) -> List[Dict[str, Any]]:
        """Get mid-market prices for multiple tokens."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_midpoints, token_ids)
        return _to_dict(result)

    async def get_spread(self, token_id: str) -> Dict[str, Any]:
        """Get bid-ask spread."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_spread, token_id)
        return _to_dict(result)

    async def get_spreads(self, token_ids: List[str]) -> List[Dict[str, Any]]:
        """Get spreads for multiple tokens."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_spreads, token_ids)
        return _to_dict(result)

    async def get_last_trade_price(self, token_id: str) -> float:
        """Get last trade price."""
        client = self._get_client()
        return await asyncio.to_thread(client.get_last_trade_price, token_id)

    async def get_last_trades_prices(self, token_ids: List[str]) -> List[Dict[str, Any]]:
        """Get last trade prices for multiple tokens."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_last_trades_prices, token_ids)
        return _to_dict(result)

    async def get_fee_rate(self, token_id: Optional[str] = None) -> float:
        """Get fee rate."""
        client = self._get_client()
        return await asyncio.to_thread(client.get_fee_rate_bps, token_id)

    async def get_tick_size(self, token_id: Optional[str] = None) -> float:
        """Get tick size."""
        client = self._get_client()
        return await asyncio.to_thread(client.get_tick_size, token_id)

    async def get_neg_risk(self, token_id: Optional[str] = None) -> bool:
        """Get neg risk status."""
        client = self._get_client()
        return await asyncio.to_thread(client.get_neg_risk, token_id)

    # ====================
    # Trading (Authenticated)
    # ====================

    async def create_order(self, order_args: OrderArgs) -> Dict[str, Any]:
        """Create a limit order."""
        client = self._get_client()
        result = await asyncio.to_thread(client.create_order, order_args)
        return _to_dict(result)

    async def create_market_order(self, order_args: MarketOrderArgs) -> Dict[str, Any]:
        """Create a market order (FOK)."""
        client = self._get_client()
        result = await asyncio.to_thread(client.create_market_order, order_args)
        return _to_dict(result)

    async def cancel(self, order_id: str) -> Dict[str, Any]:
        """Cancel a specific order."""
        client = self._get_client()
        result = await asyncio.to_thread(client.cancel, order_id)
        return _to_dict(result)

    async def cancel_all(self) -> Dict[str, Any]:
        """Cancel all open orders."""
        client = self._get_client()
        result = await asyncio.to_thread(client.cancel_all)
        return _to_dict(result)

    async def cancel_orders(self, order_ids: List[str]) -> Dict[str, Any]:
        """Cancel multiple orders."""
        client = self._get_client()
        result = await asyncio.to_thread(client.cancel_orders, order_ids)
        return _to_dict(result)

    async def cancel_market_orders(self, condition_id: str) -> Dict[str, Any]:
        """Cancel all orders for a market."""
        client = self._get_client()
        result = await asyncio.to_thread(client.cancel_market_orders, condition_id)
        return _to_dict(result)

    async def get_orders(self, **kwargs) -> List[Dict[str, Any]]:
        """Get open orders."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_orders, **kwargs)
        return _to_dict(result)

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get a specific order."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_order, order_id)
        return _to_dict(result)

    async def get_trades(self, **kwargs) -> List[Dict[str, Any]]:
        """Get user trades."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_trades, **kwargs)
        return _to_dict(result)

    async def get_builder_trades(self, **kwargs) -> List[Dict[str, Any]]:
        """Get builder trades."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_builder_trades, **kwargs)
        return _to_dict(result)

    async def post_heartbeat(self, order_ids: List[str]) -> Dict[str, Any]:
        """Send heartbeat for orders."""
        client = self._get_client()
        result = await asyncio.to_thread(client.post_heartbeat, order_ids)
        return _to_dict(result)

    async def are_orders_scoring(self, order_ids: List[str]) -> bool:
        """Check if orders are being scored."""
        client = self._get_client()
        return await asyncio.to_thread(client.are_orders_scoring, order_ids)

    # ====================
    # API Key Management
    # ====================

    async def create_or_derive_api_creds(self) -> Dict[str, Any]:
        """Create or derive API credentials."""
        client = self._get_client()
        result = await asyncio.to_thread(client.create_or_derive_api_creds)
        return _to_dict(result)

    async def get_api_keys(self) -> List[Dict[str, Any]]:
        """Get all API keys."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_api_keys)
        return _to_dict(result)

    async def delete_api_key(self, key_id: str) -> Dict[str, Any]:
        """Delete an API key."""
        client = self._get_client()
        result = await asyncio.to_thread(client.delete_api_key, key_id)
        return _to_dict(result)

    # ====================
    # Balance & Allowance
    # ====================

    async def get_balance_allowance(self) -> Dict[str, Any]:
        """Get balance and allowance."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_balance_allowance)
        return _to_dict(result)

    async def update_balance_allowance(self) -> Dict[str, Any]:
        """Update balance and allowance."""
        client = self._get_client()
        result = await asyncio.to_thread(client.update_balance_allowance)
        return _to_dict(result)

    # ====================
    # Notifications
    # ====================

    async def get_notifications(self) -> List[Dict[str, Any]]:
        """Get notifications."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_notifications)
        return _to_dict(result)

    async def drop_notifications(self) -> Dict[str, Any]:
        """Drop notifications."""
        client = self._get_client()
        result = await asyncio.to_thread(client.drop_notifications)
        return _to_dict(result)

    async def get_address(self) -> str:
        """Get wallet address."""
        client = self._get_client()
        return await asyncio.to_thread(client.get_address)

    # ====================
    # Market Data Events
    # ====================

    async def get_market_trades_events(self, condition_id: str) -> List[Dict[str, Any]]:
        """Get market trades events."""
        client = self._get_client()
        result = await asyncio.to_thread(client.get_market_trades_events, condition_id)
        return _to_dict(result)


# Singleton instance
_clob_sdk_client: Optional[ClobSDKClient] = None


def get_clob_sdk_client() -> ClobSDKClient:
    """Get the singleton CLOB SDK client instance."""
    global _clob_sdk_client
    if _clob_sdk_client is None:
        _clob_sdk_client = ClobSDKClient()
    return _clob_sdk_client


def configure_clob_sdk_client(
    private_key: str,
    address: str,
    signature_type: int = 0,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    api_passphrase: Optional[str] = None,
    funder: Optional[str] = None,
) -> ClobSDKClient:
    """
    Configure the CLOB SDK client with wallet credentials.

    Args:
        private_key: Wallet private key
        address: Wallet address
        signature_type: 0=EOA, 1=POLY_PROXY, 2=GNOSIS_SAFE
        api_key: Optional L2 API key
        api_secret: Optional L2 API secret
        api_passphrase: Optional L2 API passphrase
        funder: Funder address for proxy wallet

    Returns:
        Configured client
    """
    global _clob_sdk_client
    _clob_sdk_client = ClobSDKClient(
        private_key=private_key,
        address=address,
        signature_type=signature_type,
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase,
        funder=funder,
    )
    return _clob_sdk_client
