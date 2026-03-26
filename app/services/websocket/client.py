"""
WebSocket client for Polymarket real-time data.

Handles Market, User, and Sports channels.
"""
import asyncio
import json
from typing import Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum


class WebSocketChannel(Enum):
    """WebSocket channel types."""
    MARKET = "market"
    USER = "user"
    SPORTS = "sports"


@dataclass
class MarketSubscription:
    """Subscription configuration for market channel."""
    asset_ids: list[str]
    level: int = 2
    initial_dump: bool = True
    custom_feature_enabled: bool = False


class PolymarketWebSocket:
    """
    Async WebSocket client for Polymarket real-time data.

    Connection URLs:
    - Market: wss://ws-subscriptions-clob.polymarket.com/ws/market
    - User: wss://ws-subscriptions-clob.polymarket.com/ws/user
    - Sports: wss://ws-subscriptions-clob.polymarket.com/ws/sports
    """

    # Connection URLs
    MARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    USER_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
    SPORTS_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/sports"

    def __init__(self, channel: WebSocketChannel = WebSocketChannel.MARKET):
        self.channel = channel
        self._connection_url = self._get_connection_url(channel)
        self._ws: Optional[Any] = None
        self._running = False
        self._subscriptions: dict[str, MarketSubscription] = {}
        self._message_handler: Optional[Callable] = None
        self._pong_received = asyncio.Event()

    def _get_connection_url(self, channel: WebSocketChannel) -> str:
        """Get WebSocket URL for channel."""
        urls = {
            WebSocketChannel.MARKET: self.MARKET_WS_URL,
            WebSocketChannel.USER: self.USER_WS_URL,
            WebSocketChannel.SPORTS: self.SPORTS_WS_URL,
        }
        return urls.get(channel, self.MARKET_WS_URL)

    async def connect(self) -> bool:
        """
        Establish WebSocket connection.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            import websockets
            self._ws = await websockets.connect(
                self._connection_url,
                ping_interval=10,  # Send PING every 10 seconds
                ping_timeout=5,
            )
            self._running = True
            return True
        except Exception as e:
            print(f"WebSocket connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None

    def set_message_handler(self, handler: Callable[[dict], None]) -> None:
        """
        Set callback for incoming messages.

        Args:
            handler: Function to call with parsed JSON message
        """
        self._message_handler = handler

    async def subscribe(
        self,
        asset_ids: list[str],
        level: int = 2,
        initial_dump: bool = True,
        custom_feature_enabled: bool = False,
    ) -> bool:
        """
        Subscribe to market updates.

        Args:
            asset_ids: List of asset IDs to subscribe to
            level: Orderbook depth level
            initial_dump: Send full orderbook snapshot
            custom_feature_enabled: Enable custom features

        Returns:
            True if subscription successful
        """
        if not self._ws:
            return False

        message = {
            "assets_ids": asset_ids,
            "type": self.channel.value,
            "level": level,
            "initial_dump": initial_dump,
            "custom_feature_enabled": custom_feature_enabled,
        }

        try:
            await self._ws.send(json.dumps(message))
            self._subscriptions[",".join(asset_ids)] = MarketSubscription(
                asset_ids=asset_ids,
                level=level,
                initial_dump=initial_dump,
                custom_feature_enabled=custom_feature_enabled,
            )
            return True
        except Exception as e:
            print(f"Subscription failed: {e}")
            return False

    async def unsubscribe(self, asset_ids: list[str]) -> bool:
        """
        Unsubscribe from market updates.

        Args:
            asset_ids: List of asset IDs to unsubscribe from

        Returns:
            True if unsubscription successful
        """
        if not self._ws:
            return False

        message = {
            "operation": "unsubscribe",
            "assets_ids": asset_ids,
        }

        try:
            await self._ws.send(json.dumps(message))
            key = ",".join(asset_ids)
            if key in self._subscriptions:
                del self._subscriptions[key]
            return True
        except Exception as e:
            print(f"Unsubscription failed: {e}")
            return False

    async def listen(self) -> None:
        """
        Listen for messages and call message handler.
        This is a blocking operation that runs until disconnect().
        """
        if not self._ws:
            return

        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)

                    # Handle PONG responses
                    if data.get("type") == "pong":
                        self._pong_received.set()
                        continue

                    # Call message handler if set
                    if self._message_handler:
                        self._message_handler(data)

                except json.JSONDecodeError:
                    print(f"Failed to parse message: {message}")

        except Exception as e:
            print(f"WebSocket listen error: {e}")
        finally:
            self._running = False

    async def send_ping(self) -> bool:
        """
        Send PING to server.

        Returns:
            True if PING sent successfully
        """
        if not self._ws:
            return False

        try:
            await self._ws.send(json.dumps({"type": "ping"}))
            return True
        except Exception:
            return False

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._ws is not None and self._running


class MarketDataStreamer:
    """
    High-level API for streaming market data.
    Manages WebSocket connection lifecycle and message parsing.
    """

    def __init__(self):
        self._ws: Optional[PolymarketWebSocket] = None
        self._handlers: dict[str, Callable] = {}

    def register_handler(self, event_type: str, handler: Callable[[dict], None]) -> None:
        """
        Register handler for specific event type.

        Args:
            event_type: Event type (book, price_change, last_trade_price, etc.)
            handler: Function to call with event data
        """
        self._handlers[event_type] = handler

    def _default_handler(self, data: dict) -> None:
        """Default message handler that routes to specific handlers."""
        event_type = data.get("type", "unknown")
        if event_type in self._handlers:
            self._handlers[event_type](data)

    async def connect_and_subscribe(
        self,
        asset_ids: list[str],
        level: int = 2,
    ) -> bool:
        """
        Connect to market WebSocket and subscribe to assets.

        Args:
            asset_ids: List of asset IDs to subscribe to
            level: Orderbook depth level

        Returns:
            True if connection and subscription successful
        """
        self._ws = PolymarketWebSocket(WebSocketChannel.MARKET)
        self._ws.set_message_handler(self._default_handler)

        if not await self._ws.connect():
            return False

        # Start listener in background
        asyncio.create_task(self._ws.listen())

        # Subscribe to assets
        return await self._ws.subscribe(asset_ids, level=level)

    async def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        if self._ws:
            await self._ws.disconnect()
            self._ws = None

    def is_connected(self) -> bool:
        """Check if connected."""
        return self._ws is not None and self._ws.is_connected
