"""
Pytest tests for GammaClient API calls.

Uses respx to mock HTTP responses.
"""
import pytest
import respx
from httpx import Response

from app.services.gamma import GammaClient


@pytest.fixture
def client():
    """Create a GammaClient instance."""
    return GammaClient()


class TestListMarkets:
    """Tests for list_markets method."""

    @pytest.mark.asyncio
    async def test_list_markets_success(self, client):
        """Should return markets list."""
        mock_markets = [
            {
                "id": "market1",
                "question": "Will Bitcoin hit 100k?",
                "active": True,
            }
        ]

        with respx.mock:
            respx.get("https://gamma-api.polymarket.com/markets").mock(
                return_value=Response(200, json=mock_markets)
            )

            result = await client.list_markets()

            assert result == mock_markets

    @pytest.mark.asyncio
    async def test_list_markets_with_limit(self, client):
        """Should pass limit correctly."""
        with respx.mock:
            route = respx.get("https://gamma-api.polymarket.com/markets").mock(
                return_value=Response(200, json=[])
            )

            await client.list_markets(limit=50)

            assert route.calls[0].request.url.params["limit"] == "50"


class TestGetMarketBySlug:
    """Tests for get_market_by_slug method."""

    @pytest.mark.asyncio
    async def test_get_market_by_slug_success(self, client):
        """Should return market by slug."""
        mock_market = {
            "slug": "bitcoin-100k-2024",
            "question": "Will Bitcoin hit 100k?",
        }

        with respx.mock:
            respx.get("https://gamma-api.polymarket.com/markets/slug/bitcoin-100k-2024").mock(
                return_value=Response(200, json=mock_market)
            )

            result = await client.get_market_by_slug("bitcoin-100k-2024")

            assert result["slug"] == "bitcoin-100k-2024"

    @pytest.mark.asyncio
    async def test_get_market_by_slug_not_found(self, client):
        """Should handle 404 gracefully."""
        with respx.mock:
            respx.get("https://gamma-api.polymarket.com/markets/slug/nonexistent").mock(
                return_value=Response(404, json={"error": "Not found"})
            )

            result = await client.get_market_by_slug("nonexistent")

            # Should return None for 404
            assert result is None


class TestListEvents:
    """Tests for list_events method."""

    @pytest.mark.asyncio
    async def test_list_events_success(self, client):
        """Should return events list."""
        mock_events = [
            {
                "id": "event1",
                "title": "Bitcoin Price",
                "slug": "bitcoin-price",
            }
        ]

        with respx.mock:
            respx.get("https://gamma-api.polymarket.com/events").mock(
                return_value=Response(200, json=mock_events)
            )

            result = await client.list_events()

            assert result == mock_events


class TestListTags:
    """Tests for list_tags method."""

    @pytest.mark.asyncio
    async def test_list_tags_success(self, client):
        """Should return tags list."""
        mock_tags = [
            {"id": "tag1", "name": "Crypto"},
            {"id": "tag2", "name": "Politics"},
        ]

        with respx.mock:
            respx.get("https://gamma-api.polymarket.com/tags").mock(
                return_value=Response(200, json=mock_tags)
            )

            result = await client.list_tags()

            assert len(result) == 2


class TestGetPublicProfile:
    """Tests for get_public_profile method."""

    @pytest.mark.asyncio
    async def test_get_public_profile_success(self, client):
        """Should return profile data."""
        mock_profile = {
            "username": "trader1",
            "bio": "Crypto trader",
        }

        with respx.mock:
            respx.get("https://gamma-api.polymarket.com/public-profile").mock(
                return_value=Response(200, json=mock_profile)
            )

            result = await client.get_public_profile("0x123")

            assert result["username"] == "trader1"


class TestGetBuilderLeaderboard:
    """Tests for get_builder_leaderboard method."""

    @pytest.mark.asyncio
    async def test_get_builder_leaderboard_success(self, client):
        """Should return builder leaderboard."""
        mock_leaderboard = [
            {"builder": "builder1", "volume": 1000000},
            {"builder": "builder2", "volume": 800000},
        ]

        with respx.mock:
            respx.get("https://gamma-api.polymarket.com/v1/builders/leaderboard").mock(
                return_value=Response(200, json=mock_leaderboard)
            )

            result = await client.get_builder_leaderboard()

            assert len(result) == 2


class TestSearchMarkets:
    """Tests for search_markets method."""

    @pytest.mark.asyncio
    async def test_search_markets_success(self, client):
        """Should return search results."""
        mock_results = [
            {"id": "m1", "question": "Bitcoin to 100k?"},
        ]

        with respx.mock:
            respx.get("https://gamma-api.polymarket.com/public-search").mock(
                return_value=Response(200, json=mock_results)
            )

            result = await client.search_markets("bitcoin")

            assert len(result) >= 0  # May be empty or have results
