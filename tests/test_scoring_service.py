"""
Pytest tests for Scoring Service (10-dimension trader scoring).

Tests cover:
- Each dimension score calculation
- Bot detection logic
- Risk flag generation
- Composite score calculation
"""
import pytest
from decimal import Decimal
from app.services.scoring_service import (
    AddressScorer,
    AddressScores,
    DEFAULT_WEIGHTS,
)


class TestWinRate:
    """Tests for Win Rate dimension."""

    def test_win_rate_100_percent(self):
        """All winning positions = 100% win rate."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"realizedPnl": 10, "avgPrice": 0.5, "totalBought": 20},
            {"realizedPnl": 5, "avgPrice": 0.5, "totalBought": 20},
        ]
        trades = []

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        assert scores.win_rate == 10.0  # 100% -> 10/10
        assert scores.win_rate_raw == 100.0

    def test_win_rate_50_percent(self):
        """Half winning positions = 50% win rate."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"realizedPnl": 10, "avgPrice": 0.5, "totalBought": 20},
            {"realizedPnl": -5, "avgPrice": 0.5, "totalBought": 20},
        ]
        trades = []

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        assert scores.win_rate == 5.0  # 50% -> 5/10
        assert scores.win_rate_raw == 50.0

    def test_win_rate_0_percent(self):
        """All losing positions = 0% win rate."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"realizedPnl": -10, "avgPrice": 0.5, "totalBought": 20},
            {"realizedPnl": -5, "avgPrice": 0.5, "totalBought": 20},
        ]
        trades = []

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        assert scores.win_rate == 0.0
        assert scores.win_rate_raw == 0.0

    def test_win_rate_filters_micro_positions(self):
        """Positions below MIN_TRADE_VALUE ($0.1) should be filtered."""
        scorer = AddressScorer()
        positions = []
        # 1 winning with $10 value, 1 losing with $0.05 value (filtered)
        closed_positions = [
            {"realizedPnl": 8, "avgPrice": 0.4, "totalBought": 25},  # $10, wins
            {"realizedPnl": -0.03, "avgPrice": 0.05, "totalBought": 1},  # $0.05, loses (filtered)
        ]
        trades = []

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        # Only 1 valid position (winning), so 100% win rate
        assert scores.win_rate == 10.0
        assert scores.win_rate_raw == 100.0


class TestProfitFactor:
    """Tests for Profit Factor dimension."""

    def test_profit_factor_normal(self):
        """Normal profit factor calculation."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"realizedPnl": 20, "avgPrice": 0.5, "totalBought": 40},  # profit
            {"realizedPnl": -10, "avgPrice": 0.5, "totalBought": 20},  # loss
        ]
        trades = []

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        # PF = 20/10 = 2.0, mapped to 10 = (2.0/5.0)*10 = 4.0
        assert scores.profit_factor == 4.0
        assert scores.profit_factor_raw == 2.0

    def test_profit_factor_perfect(self):
        """No losses = max profit factor (99)."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"realizedPnl": 20, "avgPrice": 0.5, "totalBought": 40},
            {"realizedPnl": 10, "avgPrice": 0.5, "totalBought": 20},
        ]
        trades = []

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        assert scores.profit_factor_raw == 99.0  # Capped at 99

    def test_profit_factor_zero(self):
        """No profits = 0 profit factor."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"realizedPnl": -20, "avgPrice": 0.5, "totalBought": 40},
            {"realizedPnl": -10, "avgPrice": 0.5, "totalBought": 20},
        ]
        trades = []

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        assert scores.profit_factor_raw == 0.0


class TestProfitability:
    """Tests for Profitability dimension."""

    def test_profitability_positive(self):
        """Positive P/L gets positive score."""
        scorer = AddressScorer()
        positions = [{"cashPnl": 5}]  # unrealized
        closed_positions = [
            {"realizedPnl": 10, "avgPrice": 0.5, "totalBought": 20},
        ]
        trades = []

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        assert scores.profitability_raw == 15.0  # 10 + 5
        assert scores.profitability > 0

    def test_profitability_negative(self):
        """Negative P/L gets lower score."""
        scorer = AddressScorer()
        positions = [{"cashPnl": -10}]  # unrealized loss
        closed_positions = [
            {"realizedPnl": -5, "avgPrice": 0.5, "totalBought": 10},
        ]
        trades = []

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        assert scores.profitability_raw == -15.0  # -5 + (-10)
        # Negative gets base 5.0 + (pnl/10) = 5.0 + (-1.5) = 3.5
        assert scores.profitability == pytest.approx(3.5, rel=0.1)


class TestRiskManagement:
    """Tests for Risk Management dimension."""

    def test_risk_mgmt_good(self):
        """Good risk management: wins larger than losses."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"realizedPnl": 20, "avgPrice": 0.5, "totalBought": 40},  # $20, avg=$0.5*40
            {"realizedPnl": -10, "avgPrice": 0.5, "totalBought": 20},  # $10, avg=$0.5*20
        ]
        trades = []

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        # avg_winning = $20, avg_losing = $10, ratio = 2.0
        # risk_mgmt_raw = 2.0, mapped = min(2.0/2.0*10, 10) = 10
        assert scores.risk_mgmt == 10.0


class TestPositionControl:
    """Tests for Position Control dimension."""

    def test_position_control_good(self):
        """Small max position relative to capital = good control."""
        scorer = AddressScorer()
        positions = [{"currentValue": 10}]  # $10 position
        closed_positions = []
        trades = []

        # total_capital = 10 + 100 (default) = $110
        # max_position = $10
        # ratio = 10/110 = 0.09 < 0.15 -> perfect score
        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        assert scores.pos_control == 10.0
        assert scores.pos_control_raw == pytest.approx(0.09, rel=0.1)

    def test_position_control_danger(self):
        """Large position relative to capital = poor control."""
        scorer = AddressScorer()
        positions = [{"currentValue": 90}]
        closed_positions = []
        trades = []

        # total_capital = 90 + 100 = $190
        # max_position = $90
        # ratio = 90/190 = 0.47 > 0.30 -> lower score
        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        # 0.47 is between 0.30 and 0.50 -> score 4
        assert scores.pos_control == 4.0


class TestAntiBot:
    """Tests for Anti-Bot dimension."""

    def test_anti_bot_human_pattern(self):
        """Human trading pattern gets high score."""
        scorer = AddressScorer()
        positions = []
        closed_positions = []
        # Simulate human: trades at different hours with variance
        trades = [
            {"timestamp": 1700000000 + i * 3600, "size": 10, "price": 0.5, "side": "BUY"}
            for i in range(20)  # 20 trades
        ]
        # Add some variance in timing (not 24/7 constant)
        trades[0]["timestamp"] = 1700000000  # 0:00
        trades[1]["timestamp"] = 1700036000  # 1:00
        # ... gaps for sleep

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        # Should get reasonable human-like score
        assert scores.anti_bot > 0
        assert scores.anti_bot <= 10.0

    def test_anti_bot_data_insufficient(self):
        """Too few trades = neutral score (5.0)."""
        scorer = AddressScorer()
        positions = []
        closed_positions = []
        trades = [
            {"timestamp": 1700000000, "size": 10, "price": 0.5, "side": "BUY"},
        ]

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        # Less than 10 trades -> default 5.0
        assert scores.anti_bot == 5.0


class TestExperience:
    """Tests for Experience dimension."""

    def test_experience_many_trades(self):
        """Many trades over time = high experience."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"realizedPnl": 5, "avgPrice": 0.5, "totalBought": 10}
            for _ in range(100)  # 100 closed positions
        ]
        # Simulate trades over 365 days
        trades = [
            {"timestamp": 1700000000 + i * 86400, "size": 10, "price": 0.5, "side": "BUY"}
            for i in range(100)  # 100 trades over 100 days
        ]

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        # sqrt(100 * 100) = 100, log(101)/log(601)*10 should be high
        assert scores.experience > 5.0

    def test_experience_few_trades(self):
        """Few trades = low experience."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"realizedPnl": 5, "avgPrice": 0.5, "totalBought": 10},
        ]
        trades = [
            {"timestamp": 1700000000, "size": 10, "price": 0.5, "side": "BUY"},
        ]

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        assert scores.experience < 5.0


class TestFocus:
    """Tests for Focus (concentration) dimension."""

    def test_focus_concentrated(self):
        """Trades in same category = high focus (HHI close to 1)."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"eventSlug": "bitcoin", "realizedPnl": 5, "avgPrice": 0.5, "totalBought": 10},
            {"eventSlug": "bitcoin", "realizedPnl": 3, "avgPrice": 0.5, "totalBought": 10},
            {"eventSlug": "bitcoin", "realizedPnl": 2, "avgPrice": 0.5, "totalBought": 10},
        ]
        trades = []

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        # All same category -> HHI = 1.0 -> focus = 10.0
        assert scores.focus == 10.0

    def test_focus_diversified(self):
        """Trades in different categories = low focus."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"eventSlug": "bitcoin", "realizedPnl": 5, "avgPrice": 0.5, "totalBought": 10},
            {"eventSlug": "sports", "realizedPnl": 3, "avgPrice": 0.5, "totalBought": 10},
            {"eventSlug": "politics", "realizedPnl": 2, "avgPrice": 0.5, "totalBought": 10},
            {"eventSlug": "crypto", "realizedPnl": 4, "avgPrice": 0.5, "totalBought": 10},
        ]
        trades = []

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        # 4 categories equally -> HHI = 4 * (0.25)^2 = 0.25 -> focus = 2.5
        assert scores.focus < 5.0


class TestBotDetection:
    """Tests for Bot detection and risk flags."""

    def test_bot_scraper_detection(self):
        """High micro-win ratio should trigger BOT_SCRAPER flag."""
        scorer = AddressScorer()
        positions = []
        # 6 micro wins (profit $0.1-$1), only 4 normal wins
        # micro ratio = 6/10 = 60% > 50% -> BOT_SCRAPER
        closed_positions = [
            {"realizedPnl": 0.5, "avgPrice": 0.5, "totalBought": 1},  # micro
            {"realizedPnl": 0.8, "avgPrice": 0.8, "totalBought": 1},  # micro
            {"realizedPnl": 0.3, "avgPrice": 0.3, "totalBought": 1},  # micro
            {"realizedPnl": 0.9, "avgPrice": 0.9, "totalBought": 1},  # micro
            {"realizedPnl": 0.4, "avgPrice": 0.4, "totalBought": 1},  # micro
            {"realizedPnl": 0.6, "avgPrice": 0.6, "totalBought": 1},  # micro
            {"realizedPnl": 10, "avgPrice": 0.5, "totalBought": 20},  # normal
            {"realizedPnl": 15, "avgPrice": 0.5, "totalBought": 30},  # normal
            {"realizedPnl": 8, "avgPrice": 0.4, "totalBought": 20},  # normal
            {"realizedPnl": 12, "avgPrice": 0.6, "totalBought": 20},  # normal
        ]
        trades = []

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        assert "BOT_SCRAPER" in scores.risk_flags
        assert scores.micro_win_count == 6
        assert scores.micro_win_ratio == 0.6

    def test_low_experience_flag(self):
        """Few trades should trigger LOW_EXPERIENCE flag."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"realizedPnl": 5, "avgPrice": 0.5, "totalBought": 10},
        ]
        trades = [
            {"timestamp": 1700000000, "size": 10, "price": 0.5, "side": "BUY"},
        ]

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        assert "LOW_EXPERIENCE" in scores.risk_flags

    def test_bot_score_penalty(self):
        """BOT_SCRAPER should reduce total score by 50%."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"realizedPnl": 0.5, "avgPrice": 0.5, "totalBought": 1},
            {"realizedPnl": 0.8, "avgPrice": 0.8, "totalBought": 1},
            {"realizedPnl": 0.3, "avgPrice": 0.3, "totalBought": 1},
            {"realizedPnl": 0.9, "avgPrice": 0.9, "totalBought": 1},
            {"realizedPnl": 0.4, "avgPrice": 0.4, "totalBought": 1},
            {"realizedPnl": 0.6, "avgPrice": 0.6, "totalBought": 1},
            {"realizedPnl": 10, "avgPrice": 0.5, "totalBought": 20},
        ]
        trades = [
            {"timestamp": 1700000000 + i * 3600, "size": 10, "price": 0.5, "side": "BUY"}
            for i in range(20)
        ]

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        # Score should be halved due to BOT_SCRAPER
        assert scores.total_score < 50  # Halved from what it would be


class TestDataQuality:
    """Tests for data quality assessment."""

    def test_data_quality_insufficient(self):
        """Very few positions/trades = insufficient data."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"realizedPnl": 5, "avgPrice": 0.5, "totalBought": 10},
        ]
        trades = [
            {"timestamp": 1700000000, "size": 10, "price": 0.5, "side": "BUY"},
        ]

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        assert scores.data_quality == "insufficient"

    def test_data_quality_partial(self):
        """Some data but not a lot = partial quality."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"realizedPnl": 5, "avgPrice": 0.5, "totalBought": 10}
            for _ in range(5)
        ]
        trades = [
            {"timestamp": 1700000000 + i * 3600, "size": 10, "price": 0.5, "side": "BUY"}
            for i in range(10)
        ]

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        assert scores.data_quality == "partial"

    def test_data_quality_full(self):
        """Many positions and trades = full quality."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"realizedPnl": 5, "avgPrice": 0.5, "totalBought": 10}
            for _ in range(15)
        ]
        trades = [
            {"timestamp": 1700000000 + i * 3600, "size": 10, "price": 0.5, "side": "BUY"}
            for i in range(25)
        ]

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        assert scores.data_quality == "full"


class TestCompositeScore:
    """Tests for composite score calculation."""

    def test_composite_score_range(self):
        """Total score should be between 0 and 100."""
        scorer = AddressScorer()

        # Perfect trader
        positions = []
        closed_positions = [
            {"realizedPnl": 100, "avgPrice": 0.5, "totalBought": 200},
            {"realizedPnl": 80, "avgPrice": 0.5, "totalBought": 160},
            {"realizedPnl": 60, "avgPrice": 0.5, "totalBought": 120},
        ]
        trades = [
            {"timestamp": 1700000000 + i * 86400, "size": 50, "price": 0.5, "side": "BUY"}
            for i in range(50)
        ]

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        assert 0 <= scores.total_score <= 100

    def test_weights_sum_to_1(self):
        """Weights should sum to 1.0 (100%)."""
        total = sum(DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_data(self):
        """Empty positions and trades should not crash."""
        scorer = AddressScorer()
        positions = []
        closed_positions = []
        trades = []

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        assert scores.total_score >= 0
        assert scores.total_score <= 100

    def test_zero_pnl(self):
        """Zero P/L should give reasonable score."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"realizedPnl": 0, "avgPrice": 0.5, "totalBought": 10},
        ]
        trades = []

        scores = scorer.score_address("0x123", positions, closed_positions, trades)

        # Should not crash, score depends on other factors
        assert scores.total_score >= 0

    def test_address_normalization(self):
        """Address should be preserved as-is."""
        scorer = AddressScorer()
        positions = []
        closed_positions = []
        trades = []

        scores = scorer.score_address("0xABCdef123", positions, closed_positions, trades)

        assert scores.address == "0xABCdef123"

    def test_to_dict_output(self):
        """to_dict() should return complete structure."""
        scorer = AddressScorer()
        positions = []
        closed_positions = [
            {"realizedPnl": 5, "avgPrice": 0.5, "totalBought": 10},
        ]
        trades = []

        scores = scorer.score_address("0x123", positions, closed_positions, trades)
        result = scores.to_dict()

        assert "address" in result
        assert "total_score" in result
        assert "data_quality" in result
        assert "dimensions" in result
        assert "risk_flags" in result
        assert "risk_level" in result
