"""
Pytest tests for DataClient API calls.

Uses respx to mock HTTP responses without hitting real APIs.
"""
import pytest
import respx
from httpx import Response

from app.services.data import DataClient


@pytest.fixture
def client():
    """Create a DataClient instance."""
    return DataClient()


class TestGetPositions:
    """Tests for get_positions method."""

    @pytest.mark.asyncio
    async def test_get_positions_success(self, client):
        """Should return positions list."""
        mock_positions = [
            {
                "proxyWallet": "0x123",
                "asset": "asset1",
                "size": 100,
                "avgPrice": 0.5,
                "cashPnl": 10.0,
            }
        ]

        with respx.mock:
            respx.get("https://data-api.polymarket.com/positions").mock(
                return_value=Response(200, json=mock_positions)
            )

            result = await client.get_positions(user="0x123")

            assert result == mock_positions
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_positions_with_filters(self, client):
        """Should pass filter params correctly."""
        with respx.mock:
            route = respx.get("https://data-api.polymarket.com/positions").mock(
                return_value=Response(200, json=[])
            )

            await client.get_positions(
                user="0x123",
                market="market1",
                event_id="event1",
                limit=50,
            )

            # Check request was made with correct params
            assert route.calls[0].request.url.params["user"] == "0x123"
            assert route.calls[0].request.url.params["market"] == "market1"
            assert route.calls[0].request.url.params["eventId"] == "event1"

    @pytest.mark.asyncio
    async def test_get_positions_empty(self, client):
        """Should handle empty response."""
        with respx.mock:
            respx.get("https://data-api.polymarket.com/positions").mock(
                return_value=Response(200, json=[])
            )

            result = await client.get_positions(user="0x123")

            assert result == []


class TestGetClosedPositions:
    """Tests for get_closed_positions method."""

    @pytest.mark.asyncio
    async def test_get_closed_positions_success(self, client):
        """Should return closed positions list."""
        mock_positions = [
            {
                "proxyWallet": "0x123",
                "realizedPnl": 5.0,
                "avgPrice": 0.5,
                "totalBought": 10,
            }
        ]

        with respx.mock:
            respx.get("https://data-api.polymarket.com/closed-positions").mock(
                return_value=Response(200, json=mock_positions)
            )

            result = await client.get_closed_positions(user="0x123")

            assert result == mock_positions

    @pytest.mark.asyncio
    async def test_get_closed_positions_with_market_filter(self, client):
        """Should pass market filter correctly."""
        with respx.mock:
            route = respx.get("https://data-api.polymarket.com/closed-positions").mock(
                return_value=Response(200, json=[])
            )

            await client.get_closed_positions(user="0x123", market="condition1")

            assert route.calls[0].request.url.params["market"] == "condition1"


class TestGetTrades:
    """Tests for get_trades method."""

    @pytest.mark.asyncio
    async def test_get_trades_success(self, client):
        """Should return trades list."""
        mock_trades = [
            {
                "proxyWallet": "0x123",
                "side": "BUY",
                "size": 10,
                "price": 0.5,
                "timestamp": 1700000000,
            }
        ]

        with respx.mock:
            respx.get("https://data-api.polymarket.com/trades").mock(
                return_value=Response(200, json=mock_trades)
            )

            result = await client.get_trades(user="0x123")

            assert result == mock_trades

    @pytest.mark.asyncio
    async def test_get_trades_with_side_filter(self, client):
        """Should pass side filter correctly."""
        with respx.mock:
            route = respx.get("https://data-api.polymarket.com/trades").mock(
                return_value=Response(200, json=[])
            )

            await client.get_trades(user="0x123", side="BUY")

            assert route.calls[0].request.url.params["side"] == "BUY"


class TestGetActivity:
    """Tests for get_activity method."""

    @pytest.mark.asyncio
    async def test_get_activity_success(self, client):
        """Should return activity list."""
        mock_activity = [
            {
                "proxyWallet": "0x123",
                "type": "TRADE",
                "size": 10,
                "timestamp": 1700000000,
            }
        ]

        with respx.mock:
            respx.get("https://data-api.polymarket.com/activity").mock(
                return_value=Response(200, json=mock_activity)
            )

            result = await client.get_activity(user="0x123")

            assert result == mock_activity


class TestGetLeaderboard:
    """Tests for get_leaderboard method."""

    @pytest.mark.asyncio
    async def test_get_leaderboard_success(self, client):
        """Should return leaderboard entries."""
        mock_leaderboard = [
            {
                "address": "0x123",
                "rank": 1,
                "volume": 10000,
            },
            {
                "address": "0x456",
                "rank": 2,
                "volume": 8000,
            },
        ]

        with respx.mock:
            respx.get("https://data-api.polymarket.com/v1/leaderboard").mock(
                return_value=Response(200, json=mock_leaderboard)
            )

            result = await client.get_leaderboard()

            assert len(result) == 2
            assert result[0]["rank"] == 1


class TestGetTotalValue:
    """Tests for get_total_value method."""

    @pytest.mark.asyncio
    async def test_get_total_value_success(self, client):
        """Should return total value from nested response."""
        # API returns a list with value inside
        mock_response = [{"value": 1234.56}]

        with respx.mock:
            respx.get("https://data-api.polymarket.com/value").mock(
                return_value=Response(200, json=mock_response)
            )

            result = await client.get_total_value(user="0x123")

            assert result == 1234.56


class TestGetMarketsTradedCount:
    """Tests for get_markets_traded_count method."""

    @pytest.mark.asyncio
    async def test_get_markets_traded_count_success(self, client):
        """Should return count from dict response."""
        # API returns a dict with 'traded' key
        mock_response = {"traded": 42}

        with respx.mock:
            respx.get("https://data-api.polymarket.com/traded").mock(
                return_value=Response(200, json=mock_response)
            )

            result = await client.get_markets_traded_count(user="0x123")

            assert result == 42


class TestClose:
    """Tests for client close method."""

    @pytest.mark.asyncio
    async def test_close_client(self, client):
        """Should close HTTP client."""
        # Get client to initialize it
        await client._get_client()
        assert client._client is not None

        # Close it
        await client.close()
        assert client._client is None
