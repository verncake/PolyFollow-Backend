"""
Pytest tests for PnL History resampling logic.

Tests the Simplified Cash Flow Method for PnL calculation:
- PnL = cumulative withdrawals (SELL proceeds) - cumulative deposits (BUY costs)
"""
import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

from app.api.routes.pnl import (
    get_bucket_seconds,
    get_start_timestamp,
    resample_pnl_data,
    TIMEFRAME_CONFIG,
    VALID_TIMEFRAMES,
)


class TestTimeframeConfig:
    """Tests for timeframe configuration."""

    def test_valid_timeframes(self):
        """All expected timeframes are valid."""
        expected = ["1D", "1W", "1M", "6M", "1Y", "ALL"]
        assert set(VALID_TIMEFRAMES) == set(expected)

    def test_1d_config(self):
        """1D timeframe should have 1-hour buckets."""
        config = TIMEFRAME_CONFIG["1D"]
        assert config["days"] == 1
        assert config["bucket_hours"] == 1

    def test_1w_config(self):
        """1W timeframe should have 3-hour buckets."""
        config = TIMEFRAME_CONFIG["1W"]
        assert config["days"] == 7
        assert config["bucket_hours"] == 3

    def test_1m_config(self):
        """1M timeframe should have 24-hour buckets (1 day)."""
        config = TIMEFRAME_CONFIG["1M"]
        assert config["days"] == 30
        assert config["bucket_hours"] == 24

    def test_6m_config(self):
        """6M timeframe should have weekly buckets."""
        config = TIMEFRAME_CONFIG["6M"]
        assert config["days"] == 180
        assert config["bucket_hours"] == 168  # 1 week in hours

    def test_1y_config(self):
        """1Y timeframe should have weekly buckets."""
        config = TIMEFRAME_CONFIG["1Y"]
        assert config["days"] == 365
        assert config["bucket_hours"] == 168  # 1 week in hours

    def test_all_config(self):
        """ALL timeframe should have no fixed days or bucket."""
        config = TIMEFRAME_CONFIG["ALL"]
        assert config["days"] is None
        assert config["bucket_hours"] is None


class TestGetBucketSeconds:
    """Tests for bucket size calculation."""

    def test_1d_bucket(self):
        """1D should return 1 hour in seconds."""
        result = get_bucket_seconds("1D")
        assert result == 3600  # 1 hour = 3600 seconds

    def test_1w_bucket(self):
        """1W should return 3 hours in seconds."""
        result = get_bucket_seconds("1W")
        assert result == 10800  # 3 hours = 10800 seconds

    def test_1m_bucket(self):
        """1M should return 24 hours (1 day) in seconds."""
        result = get_bucket_seconds("1M")
        assert result == 86400  # 24 hours = 86400 seconds

    def test_6m_bucket(self):
        """6M should return 1 week in seconds."""
        result = get_bucket_seconds("6M")
        assert result == 604800  # 1 week = 604800 seconds

    def test_1y_bucket(self):
        """1Y should return 1 week in seconds."""
        result = get_bucket_seconds("1Y")
        assert result == 604800  # 1 week = 604800 seconds

    def test_all_bucket_low_activity(self):
        """ALL with low activity should return daily buckets."""
        result = get_bucket_seconds("ALL", user_trade_count=100)
        assert result == 86400  # 1 day

    def test_all_bucket_medium_activity(self):
        """ALL with medium activity should return weekly buckets."""
        result = get_bucket_seconds("ALL", user_trade_count=2000)
        assert result == 604800  # 1 week

    def test_all_bucket_high_activity(self):
        """ALL with high activity should return half-month buckets."""
        result = get_bucket_seconds("ALL", user_trade_count=10000)
        assert result == 1555200  # ~18 days = 432 hours * 3600


class TestGetStartTimestamp:
    """Tests for start timestamp calculation."""

    def test_1d_start(self):
        """1D should return timestamp ~24 hours ago."""
        now = datetime.utcnow()
        result = get_start_timestamp("1D")
        expected_min = int((now - timedelta(hours=25)).timestamp())
        expected_max = int((now - timedelta(hours=23)).timestamp())
        # Allow some tolerance for test execution time
        assert expected_min <= result <= expected_max

    def test_1w_start(self):
        """1W should return timestamp ~7 days ago."""
        now = datetime.utcnow()
        result = get_start_timestamp("1W")
        expected_min = int((now - timedelta(days=8)).timestamp())
        expected_max = int((now - timedelta(days=6)).timestamp())
        assert expected_min <= result <= expected_max

    def test_1m_start(self):
        """1M should return timestamp ~30 days ago."""
        now = datetime.utcnow()
        result = get_start_timestamp("1M")
        expected_min = int((now - timedelta(days=31)).timestamp())
        expected_max = int((now - timedelta(days=29)).timestamp())
        assert expected_min <= result <= expected_max

    def test_all_start(self):
        """ALL should return 0 (beginning of time)."""
        result = get_start_timestamp("ALL")
        assert result == 0


class TestResamplePnLData:
    """Tests for the full PnL resampling calculation."""

    @pytest.mark.asyncio
    async def test_empty_trades(self):
        """Empty position list should return empty data points."""
        mock_db = MagicMock()
        mock_db.get_user_positions = AsyncMock(return_value=[])
        mock_db.get_activity_for_condition = AsyncMock(return_value=None)

        with patch('app.api.routes.pnl.get_db_service', return_value=mock_db):
            result = await resample_pnl_data("0x123", "1W")

        assert result["timeframe"] == "1W"
        assert result["current_pnl"] == 0.0
        assert result["data"] == []

    @pytest.mark.asyncio
    async def test_single_pending_redeem_position(self):
        """Single pending_redeem position should result in PnL based on realized_pnl."""
        now_ts = int(datetime.utcnow().timestamp())
        now_dt = datetime.utcnow()
        positions = [{
            "condition_id": "cond1",
            "asset_id": "asset1",
            "status": "pending_redeem",
            "realized_pnl": -5.0,
            "closed_at": None,  # No closed_at, will use activity proxy
            "updated_at": (now_dt.replace(tzinfo=None)).isoformat(),
        }]

        mock_db = MagicMock()
        mock_db.get_user_positions = AsyncMock(return_value=positions)
        mock_db.get_activities_for_conditions = AsyncMock(return_value={})  # No activity found

        with patch('app.api.routes.pnl.get_db_service', return_value=mock_db):
            result = await resample_pnl_data("0x123", "1W")

        assert result["timeframe"] == "1W"
        assert result["current_pnl"] == -5.0
        assert len(result["data"]) > 0

    @pytest.mark.asyncio
    async def test_single_closed_position(self):
        """Single closed position should result in PnL based on realized_pnl."""
        now_ts = int(datetime.utcnow().timestamp())
        positions = [{
            "condition_id": "cond1",
            "asset_id": "asset1",
            "status": "closed",
            "realized_pnl": 10.0,
            "closed_at": datetime.utcnow().isoformat(),
        }]

        mock_db = MagicMock()
        mock_db.get_user_positions = AsyncMock(return_value=positions)
        mock_db.get_activity_for_condition = AsyncMock(return_value=None)

        with patch('app.api.routes.pnl.get_db_service', return_value=mock_db):
            result = await resample_pnl_data("0x123", "1W")

        assert result["timeframe"] == "1W"
        assert result["current_pnl"] == 10.0
        assert len(result["data"]) > 0

    @pytest.mark.asyncio
    async def test_pending_redeem_with_activity_proxy(self):
        """pending_redeem position without closed_at should use activity timestamp as proxy."""
        now_ts = int(datetime.utcnow().timestamp())
        now_dt = datetime.utcnow()
        positions = [{
            "condition_id": "cond1",
            "asset_id": "asset1",
            "status": "pending_redeem",
            "realized_pnl": 5.0,
            "closed_at": None,
            "updated_at": (now_dt.replace(tzinfo=None)).isoformat(),
        }]

        # Activity has a REDEEM with a timestamp we can use as proxy
        activity = {
            "condition_id": "cond1",
            "asset_id": "asset1",
            "activity_type": "REDEEM",
            "timestamp": now_ts - 7200,  # 2 hours ago
        }

        mock_db = MagicMock()
        mock_db.get_user_positions = AsyncMock(return_value=positions)
        mock_db.get_activities_for_conditions = AsyncMock(return_value={("cond1", "asset1"): activity})

        with patch('app.api.routes.pnl.get_db_service', return_value=mock_db):
            result = await resample_pnl_data("0x123", "1W")

        assert result["timeframe"] == "1W"
        assert result["current_pnl"] == 5.0
        assert len(result["data"]) > 0

    @pytest.mark.asyncio
    async def test_invalid_timeframe_raises_error(self):
        """Invalid timeframe should raise ValueError."""
        mock_db = MagicMock()
        mock_db.get_user_positions = AsyncMock(return_value=[])
        mock_db.get_activity_for_condition = AsyncMock(return_value=None)

        with patch('app.api.routes.pnl.get_db_service', return_value=mock_db):
            with pytest.raises(ValueError) as exc_info:
                await resample_pnl_data("0x123", "INVALID")
            assert "Invalid timeframe" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_case_insensitive_timeframe(self):
        """Timeframe should be case insensitive."""
        mock_db = MagicMock()
        mock_db.get_user_positions = AsyncMock(return_value=[])
        mock_db.get_activity_for_condition = AsyncMock(return_value=None)

        with patch('app.api.routes.pnl.get_db_service', return_value=mock_db):
            # Should not raise error with lowercase
            result = await resample_pnl_data("0x123", "1w")
            assert result["timeframe"] == "1W"  # Normalized to uppercase


class TestCashFlowMethod:
    """Tests specifically for PnL calculation from positions data."""

    @pytest.mark.asyncio
    async def test_multiple_positions_aggregate_correctly(self):
        """Multiple positions should aggregate their realized_pnl correctly."""
        now_dt = datetime.utcnow().replace(tzinfo=None)
        positions = [
            {
                "condition_id": "cond1",
                "asset_id": "asset1",
                "status": "closed",
                "realized_pnl": 50.0,
                "closed_at": now_dt.isoformat(),
            },
            {
                "condition_id": "cond2",
                "asset_id": "asset2",
                "status": "closed",
                "realized_pnl": -30.0,
                "closed_at": now_dt.isoformat(),
            },
        ]

        mock_db = MagicMock()
        mock_db.get_user_positions = AsyncMock(return_value=positions)
        mock_db.get_activity_for_condition = AsyncMock(return_value=None)

        with patch('app.api.routes.pnl.get_db_service', return_value=mock_db):
            result = await resample_pnl_data("0x123", "1W")

        # Total PnL = 50 + (-30) = 20
        assert result["current_pnl"] == 20.0

    @pytest.mark.asyncio
    async def test_pending_redeem_and_closed_mix(self):
        """Mix of pending_redeem and closed positions should aggregate correctly."""
        now_dt = datetime.utcnow().replace(tzinfo=None)
        positions = [
            {
                "condition_id": "cond1",
                "asset_id": "asset1",
                "status": "closed",
                "realized_pnl": 100.0,
                "closed_at": now_dt.isoformat(),
            },
            {
                "condition_id": "cond2",
                "asset_id": "asset2",
                "status": "pending_redeem",
                "realized_pnl": 50.0,
                "closed_at": None,
                "updated_at": now_dt.isoformat(),
            },
        ]

        mock_db = MagicMock()
        mock_db.get_user_positions = AsyncMock(return_value=positions)
        mock_db.get_activities_for_conditions = AsyncMock(return_value={})

        with patch('app.api.routes.pnl.get_db_service', return_value=mock_db):
            result = await resample_pnl_data("0x123", "1W")

        # Total PnL = 100 + 50 = 150
        assert result["current_pnl"] == 150.0


# Helper to import timedelta for the tests
from datetime import timedelta
