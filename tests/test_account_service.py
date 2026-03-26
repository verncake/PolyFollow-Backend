"""
Pytest tests for Account Service P/L calculations.

These tests focus on the mathematical accuracy of P/L calculations.
"""
import pytest
from decimal import Decimal
from app.services.account_service import (
    calculate_unrealized_pnl,
    calculate_realized_pnl,
    calculate_position_pnl,
    calculate_win_rate,
    calculate_profit_factor,
    calculate_account_summary,
    PositionPnL,
    AccountSummary,
    ZERO,
    MONEY_PRECISION,
)


class TestUnrealizedPnL:
    """Tests for unrealized P/L calculation."""

    def test_buy_position_profit(self):
        """BUY position when price goes up should have positive P/L."""
        result = calculate_unrealized_pnl(
            side="BUY",
            size=Decimal("100"),
            entry_price=Decimal("0.50"),
            current_price=Decimal("0.60"),
        )
        assert result == Decimal("10.000000")  # (0.60 - 0.50) * 100 = 10

    def test_buy_position_loss(self):
        """BUY position when price goes down should have negative P/L."""
        result = calculate_unrealized_pnl(
            side="BUY",
            size=Decimal("100"),
            entry_price=Decimal("0.50"),
            current_price=Decimal("0.40"),
        )
        assert result == Decimal("-10.000000")  # (0.40 - 0.50) * 100 = -10

    def test_sell_position_profit(self):
        """SELL position when price goes down should have positive P/L."""
        result = calculate_unrealized_pnl(
            side="SELL",
            size=Decimal("100"),
            entry_price=Decimal("0.50"),
            current_price=Decimal("0.40"),
        )
        assert result == Decimal("10.000000")  # (0.50 - 0.40) * 100 = 10

    def test_sell_position_loss(self):
        """SELL position when price goes up should have negative P/L."""
        result = calculate_unrealized_pnl(
            side="SELL",
            size=Decimal("100"),
            entry_price=Decimal("0.50"),
            current_price=Decimal("0.60"),
        )
        assert result == Decimal("-10.000000")  # (0.50 - 0.60) * 100 = -10

    def test_zero_size(self):
        """Zero size position should return zero P/L."""
        result = calculate_unrealized_pnl(
            side="BUY",
            size=Decimal("0"),
            entry_price=Decimal("0.50"),
            current_price=Decimal("0.60"),
        )
        assert result == ZERO

    def test_invalid_side_raises(self):
        """Invalid side should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid side"):
            calculate_unrealized_pnl(
                side="HOLD",
                size=Decimal("100"),
                entry_price=Decimal("0.50"),
                current_price=Decimal("0.60"),
            )

    def test_precision_six_decimals(self):
        """Result should be quantized to 6 decimal places."""
        result = calculate_unrealized_pnl(
            side="BUY",
            size=Decimal("33.333333"),
            entry_price=Decimal("0.333333333"),
            current_price=Decimal("0.666666666"),
        )
        # Verify it has at most 6 decimal places
        assert result == result.quantize(MONEY_PRECISION)


class TestRealizedPnL:
    """Tests for realized P/L calculation."""

    def test_buy_position_closed_at_profit(self):
        """BUY position closed at higher price has positive realized P/L."""
        result = calculate_realized_pnl(
            side="BUY",
            size=Decimal("100"),
            entry_price=Decimal("0.50"),
            exit_price=Decimal("0.60"),
        )
        assert result == Decimal("10.000000")

    def test_buy_position_closed_at_loss(self):
        """BUY position closed at lower price has negative realized P/L."""
        result = calculate_realized_pnl(
            side="BUY",
            size=Decimal("100"),
            entry_price=Decimal("0.50"),
            exit_price=Decimal("0.40"),
        )
        assert result == Decimal("-10.000000")

    def test_sell_position_closed_at_profit(self):
        """SELL position closed at lower price has positive realized P/L."""
        result = calculate_realized_pnl(
            side="SELL",
            size=Decimal("100"),
            entry_price=Decimal("0.50"),
            exit_price=Decimal("0.40"),
        )
        assert result == Decimal("10.000000")

    def test_sell_position_closed_at_loss(self):
        """SELL position closed at higher price has negative realized P/L."""
        result = calculate_realized_pnl(
            side="SELL",
            size=Decimal("100"),
            entry_price=Decimal("0.50"),
            exit_price=Decimal("0.60"),
        )
        assert result == Decimal("-10.000000")


class TestPositionPnL:
    """Tests for complete position P/L calculation."""

    def test_open_position_only_unrealized(self):
        """Open position should only have unrealized P/L."""
        result = calculate_position_pnl(
            side="BUY",
            size=Decimal("100"),
            entry_price=Decimal("0.50"),
            current_price=Decimal("0.60"),
            exit_price=None,
        )
        assert result.unrealized_pnl == Decimal("10.000000")
        assert result.realized_pnl == ZERO
        assert result.total_pnl == Decimal("10.000000")

    def test_closed_position_has_both(self):
        """Closed position should have both realized and unrealized."""
        result = calculate_position_pnl(
            side="BUY",
            size=Decimal("100"),
            entry_price=Decimal("0.50"),
            current_price=Decimal("0.70"),
            exit_price=Decimal("0.65"),
        )
        # Unrealized based on current price
        assert result.unrealized_pnl == Decimal("20.000000")
        # Realized based on exit price
        assert result.realized_pnl == Decimal("15.000000")
        # Total
        assert result.total_pnl == Decimal("35.000000")

    def test_pnl_percentage_calculation(self):
        """P/L percentage should be calculated correctly."""
        result = calculate_position_pnl(
            side="BUY",
            size=Decimal("100"),
            entry_price=Decimal("0.50"),
            current_price=Decimal("0.55"),
            exit_price=None,
        )
        # Cost basis = 0.50 * 100 = 50
        # P/L = 5, so percentage = 5/50 = 0.10 = 10%
        assert result.pnl_percentage == Decimal("0.100000")


class TestWinRate:
    """Tests for win rate calculation."""

    def test_perfect_win_rate(self):
        """100% win rate when all trades are winners."""
        result = calculate_win_rate(wins=10, total_trades=10)
        assert result == Decimal("1.000000")

    def test_zero_win_rate(self):
        """0% win rate when all trades are losers."""
        result = calculate_win_rate(wins=0, total_trades=10)
        assert result == ZERO

    def test_50_percent_win_rate(self):
        """50% win rate with equal wins and losses."""
        result = calculate_win_rate(wins=5, total_trades=10)
        assert result == Decimal("0.500000")

    def test_zero_trades(self):
        """Zero trades should return zero win rate."""
        result = calculate_win_rate(wins=0, total_trades=0)
        assert result == ZERO

    def test_win_rate_precision(self):
        """Win rate should be quantized to 6 decimal places."""
        result = calculate_win_rate(wins=1, total_trades=3)
        assert result == Decimal("0.333333")


class TestProfitFactor:
    """Tests for profit factor calculation."""

    def test_profitable_strategy(self):
        """Profit factor > 1 for profitable strategy."""
        result = calculate_profit_factor(
            gross_profit=Decimal("1000"),
            gross_loss=Decimal("500"),
        )
        assert result == Decimal("2.000000")

    def test_losing_strategy(self):
        """Profit factor < 1 for losing strategy."""
        result = calculate_profit_factor(
            gross_profit=Decimal("500"),
            gross_loss=Decimal("1000"),
        )
        assert result == Decimal("0.500000")

    def test_no_losses(self):
        """No losses with profits returns max value."""
        result = calculate_profit_factor(
            gross_profit=Decimal("1000"),
            gross_loss=ZERO,
        )
        assert result == Decimal("999.999999")

    def test_no_profits_no_losses(self):
        """No profits and no losses returns zero."""
        result = calculate_profit_factor(
            gross_profit=ZERO,
            gross_loss=ZERO,
        )
        assert result == ZERO


class TestAccountSummary:
    """Tests for complete account summary calculation."""

    def test_single_open_position(self):
        """Account with single open position."""
        positions = [
            {
                "side": "BUY",
                "size": "100",
                "entry_price": "0.50",
                "current_price": "0.60",
                "status": "OPEN",
            }
        ]
        result = calculate_account_summary("0x123", positions)

        assert result.address == "0x123"
        assert result.total_unrealized_pnl == Decimal("10.000000")
        assert result.total_realized_pnl == ZERO
        assert result.open_positions_count == 1
        assert result.closed_positions_count == 0

    def test_mixed_positions(self):
        """Account with mix of open and closed positions."""
        positions = [
            {
                "side": "BUY",
                "size": "100",
                "entry_price": "0.50",
                "current_price": "0.60",
                "status": "OPEN",
            },
            {
                "side": "BUY",
                "size": "50",
                "entry_price": "0.40",
                "current_price": "0.45",
                "status": "CLOSED",
                "realized_pnl": "2.500000",
            },
        ]
        result = calculate_account_summary("0x456", positions)

        assert result.open_positions_count == 1
        assert result.closed_positions_count == 1
        assert result.total_unrealized_pnl == Decimal("10.000000")
        assert result.total_realized_pnl == Decimal("2.500000")

    def test_win_rate_from_positions(self):
        """Win rate calculated from closed positions."""
        positions = [
            {
                "side": "BUY",
                "size": "100",
                "entry_price": "0.50",
                "current_price": "0.55",
                "status": "CLOSED",
                "realized_pnl": "5.000000",  # Win
            },
            {
                "side": "BUY",
                "size": "100",
                "entry_price": "0.50",
                "current_price": "0.45",
                "status": "CLOSED",
                "realized_pnl": "-5.000000",  # Loss
            },
            {
                "side": "BUY",
                "size": "100",
                "entry_price": "0.50",
                "current_price": "0.55",
                "status": "CLOSED",
                "realized_pnl": "5.000000",  # Win
            },
        ]
        result = calculate_account_summary("0x789", positions)

        # 2 wins out of 3 trades = 66.67%
        assert result.win_rate == Decimal("0.666667")

    def test_empty_positions(self):
        """Account with no positions."""
        result = calculate_account_summary("0x000", [])

        assert result.total_unrealized_pnl == ZERO
        assert result.total_realized_pnl == ZERO
        assert result.total_pnl == ZERO
        assert result.open_positions_count == 0
        assert result.closed_positions_count == 0
        assert result.win_rate == ZERO

    def test_profit_factor_calculation(self):
        """Profit factor calculated from gross profit and loss."""
        positions = [
            {
                "side": "BUY",
                "size": "100",
                "entry_price": "0.50",
                "current_price": "0.60",
                "status": "CLOSED",
                "realized_pnl": "10.000000",  # Win
            },
            {
                "side": "BUY",
                "size": "100",
                "entry_price": "0.50",
                "current_price": "0.40",
                "status": "CLOSED",
                "realized_pnl": "-5.000000",  # Loss
            },
        ]
        result = calculate_account_summary("0xabc", positions)

        # Profit factor = 10 / 5 = 2.0
        assert result.profit_factor == Decimal("2.000000")
