"""
Pytest tests for PositionEnricher service.

Uses respx to mock Gamma API responses.
"""
import pytest
import respx
from httpx import Response
from datetime import datetime, timedelta

from app.services.gamma import GammaClient
from app.services.position_enricher import PositionEnricher, EnrichedPosition


@pytest.fixture
def gamma_client():
    """Create a GammaClient instance."""
    return GammaClient()


@pytest.fixture
def enricher(gamma_client):
    """Create a PositionEnricher instance."""
    return PositionEnricher(gamma_client)


class TestEnrichSinglePosition:
    """Tests for _enrich_single_position method."""

    def test_active_market(self, enricher):
        """Should mark position as active when market is open."""
        position = {
            "slug": "bitcoin-100k-2024",
            "redeemable": False,
            "cashPnl": 10.0,
        }
        market_info = {
            "closed": False,
            "active": True,
            "accepting_orders": True,
            "end_date": (datetime.now() + timedelta(days=7)).isoformat(),
            "last_trade_price": 0.55,
        }

        result = enricher._enrich_single_position(position, market_info)

        assert result.market_status == "active"
        assert result.market_closed is False
        assert result.market_resolved is False
        assert result.is_redeemable is False
        assert result.display_status == "Active"

    def test_closed_market_already_redeemed(self, enricher):
        """Should mark as closed when market ended and user redeemed."""
        position = {
            "slug": "bitcoin-100k-2024",
            "redeemable": False,
            "cashPnl": 0,
        }
        market_info = {
            "closed": True,
            "active": True,
            "accepting_orders": False,
            "end_date": (datetime.now() - timedelta(days=1)).isoformat(),
            "last_trade_price": 0.75,
        }

        result = enricher._enrich_single_position(position, market_info)

        assert result.market_status == "closed"
        assert result.market_closed is True
        assert result.market_resolved is True
        assert result.is_redeemable is False
        assert result.display_status == "Redeemed"

    def test_closed_market_pending_redeem(self, enricher):
        """Should mark as pending_redeem when market ended but user hasn't redeemed."""
        position = {
            "slug": "bitcoin-100k-2024",
            "redeemable": True,
            "cashPnl": 25.0,
        }
        market_info = {
            "closed": True,
            "active": True,
            "accepting_orders": False,
            "end_date": (datetime.now() - timedelta(days=1)).isoformat(),
            "last_trade_price": 0.75,
        }

        result = enricher._enrich_single_position(position, market_info)

        assert result.market_status == "pending_redeem"
        assert result.market_closed is True
        assert result.market_resolved is True
        assert result.is_redeemable is True
        assert result.display_status == "Pending Redeem"

    def test_market_with_no_end_date(self, enricher):
        """Should handle missing end date gracefully."""
        position = {
            "slug": "bitcoin-100k-2024",
            "redeemable": False,
        }
        market_info = {
            "closed": False,
            "active": True,
            "accepting_orders": True,
            "end_date": None,
        }

        result = enricher._enrich_single_position(position, market_info)

        assert result.market_status == "active"
        assert result.days_until_end is None

    def test_market_with_invalid_end_date(self, enricher):
        """Should handle invalid end date format gracefully."""
        position = {
            "slug": "bitcoin-100k-2024",
            "redeemable": False,
        }
        market_info = {
            "closed": False,
            "active": True,
            "end_date": "invalid-date-format",
        }

        result = enricher._enrich_single_position(position, market_info)

        assert result.market_status == "active"
        assert result.days_until_end is None


class TestFilterByStatus:
    """Tests for filter_by_status method."""

    def test_filter_all(self, enricher):
        """Should return all positions when status is 'all'."""
        positions = [
            _make_enriched_position("active"),
            _make_enriched_position("closed"),
            _make_enriched_position("pending_redeem"),
        ]

        result = enricher.filter_by_status(positions, "all")

        assert len(result) == 3

    def test_filter_active(self, enricher):
        """Should return only active positions."""
        positions = [
            _make_enriched_position("active"),
            _make_enriched_position("closed"),
            _make_enriched_position("pending_redeem"),
            _make_enriched_position("active"),
        ]

        result = enricher.filter_by_status(positions, "active")

        assert len(result) == 2
        assert all(p.market_status == "active" for p in result)

    def test_filter_closed(self, enricher):
        """Should return only closed positions."""
        positions = [
            _make_enriched_position("active"),
            _make_enriched_position("closed"),
            _make_enriched_position("pending_redeem"),
        ]

        result = enricher.filter_by_status(positions, "closed")

        assert len(result) == 1
        assert result[0].market_status == "closed"

    def test_filter_pending_redeem(self, enricher):
        """Should return only pending_redeem positions."""
        positions = [
            _make_enriched_position("active"),
            _make_enriched_position("pending_redeem"),
            _make_enriched_position("pending_redeem"),
        ]

        result = enricher.filter_by_status(positions, "pending_redeem")

        assert len(result) == 2
        assert all(p.market_status == "pending_redeem" for p in result)


class TestGetPendingRedeemCount:
    """Tests for get_pending_redeem_count method."""

    def test_count_with_pending(self, enricher):
        """Should count positions pending redeem."""
        positions = [
            _make_enriched_position("active"),
            _make_enriched_position("pending_redeem"),
            _make_enriched_position("closed"),
            _make_enriched_position("pending_redeem"),
        ]

        count = enricher.get_pending_redeem_count(positions)

        assert count == 2

    def test_count_with_no_pending(self, enricher):
        """Should return 0 when no positions pending redeem."""
        positions = [
            _make_enriched_position("active"),
            _make_enriched_position("closed"),
        ]

        count = enricher.get_pending_redeem_count(positions)

        assert count == 0

    def test_empty_list(self, enricher):
        """Should return 0 for empty list."""
        count = enricher.get_pending_redeem_count([])

        assert count == 0


class TestEnrichPositions:
    """Tests for enrich_positions method with mocked Gamma API."""

    @pytest.mark.asyncio
    async def test_enrich_positions_success(self, enricher):
        """Should enrich positions with market status from Gamma API."""
        mock_market = {
            "slug": "bitcoin-100k-2024",
            "closed": False,
            "active": True,
            "acceptingOrders": True,
            "endDate": (datetime.now() + timedelta(days=7)).isoformat(),
        }

        positions = [
            {"slug": "bitcoin-100k-2024", "redeemable": False, "cashPnl": 10.0},
        ]

        with respx.mock:
            respx.get("https://gamma-api.polymarket.com/markets/slug/bitcoin-100k-2024").mock(
                return_value=Response(200, json=mock_market)
            )

            result = await enricher.enrich_positions(positions)

            assert len(result) == 1
            assert result[0].market_status == "active"
            assert result[0].original == positions[0]

    @pytest.mark.asyncio
    async def test_enrich_multiple_positions_different_markets(self, enricher):
        """Should handle multiple positions from different markets."""
        mock_market1 = {"slug": "market1", "closed": False, "active": True}
        mock_market2 = {"slug": "market2", "closed": True, "active": True, "redeemable": True}

        positions = [
            {"slug": "market1", "redeemable": False},
            {"slug": "market2", "redeemable": True},
        ]

        with respx.mock:
            respx.get("https://gamma-api.polymarket.com/markets/slug/market1").mock(
                return_value=Response(200, json=mock_market1)
            )
            respx.get("https://gamma-api.polymarket.com/markets/slug/market2").mock(
                return_value=Response(200, json=mock_market2)
            )

            result = await enricher.enrich_positions(positions)

            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_enrich_empty_positions(self, enricher):
        """Should return empty list when no positions."""
        result = await enricher.enrich_positions([])

        assert result == []

    @pytest.mark.asyncio
    async def test_enrich_with_gamma_error_fallback(self, enricher):
        """Should assume active when Gamma API fails."""
        positions = [
            {"slug": "bitcoin-100k-2024", "redeemable": False},
        ]

        with respx.mock:
            respx.get("https://gamma-api.polymarket.com/markets/slug/bitcoin-100k-2024").mock(
                return_value=Response(500, json={"error": "Server error"})
            )

            result = await enricher.enrich_positions(positions)

            assert len(result) == 1
            # Should fallback to active status
            assert result[0].market_status == "active"
            assert result[0].market_closed is False


class TestDisplayStatus:
    """Tests for display_status property."""

    def test_active_display(self, enricher):
        """Should show 'Active' for active markets."""
        pos = _make_enriched_position("active")
        assert pos.display_status == "Active"

    def test_pending_redeem_display(self, enricher):
        """Should show 'Pending Redeem' for pending redeem."""
        pos = _make_enriched_position("pending_redeem")
        assert pos.display_status == "Pending Redeem"

    def test_closed_with_no_redeemable_display(self, enricher):
        """Should show 'Redeemed' for closed and already redeemed."""
        pos = _make_enriched_position("closed")
        assert pos.display_status == "Redeemed"


def _make_enriched_position(status: str) -> EnrichedPosition:
    """Helper to create EnrichedPosition for testing."""
    return EnrichedPosition(
        original={"slug": "test-market", "redeemable": False},
        market_status=status,
        market_closed=status in ("closed", "pending_redeem"),
        market_resolved=status in ("closed", "pending_redeem"),
        is_redeemable=status == "pending_redeem",
        days_until_end=5 if status == "active" else None,
    )
