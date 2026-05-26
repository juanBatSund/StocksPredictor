import pytest

from config.markets import MARKETS
from src.data.models import Fundamentals
from src.fundamentals.dividend import score

US = MARKETS["US"]
SE = MARKETS["SE"]


def _fund(**kwargs) -> Fundamentals:
    base = dict(
        roe=None, debt_to_equity=None, free_cash_flow=None,
        revenue_growth_5y=None, earnings_growth_5y=None,
        dividend_yield=None, payout_ratio=None,
        dividend_growth_streak_years=None, pe_ratio=None, pe_5y_avg=None,
    )
    return Fundamentals(**{**base, **kwargs})


class TestDividendYield:
    def test_none_scores_zero(self):
        assert score(_fund(), US).yield_score == 0.0

    def test_no_dividend_scores_zero(self):
        assert score(_fund(dividend_yield=0.0), US).yield_score == 0.0

    def test_below_minimum_is_partial(self):
        # US: 1% is halfway to 2% minimum → lerp(0, 75) = 37.5
        assert score(_fund(dividend_yield=0.01), US).yield_score == pytest.approx(37.5)

    def test_at_minimum_scores_75(self):
        assert score(_fund(dividend_yield=0.02), US).yield_score == pytest.approx(75.0)

    def test_peak_at_midpoint(self):
        assert score(_fund(dividend_yield=0.035), US).yield_score == pytest.approx(100.0)

    def test_at_maximum_scores_75(self):
        assert score(_fund(dividend_yield=0.05), US).yield_score == pytest.approx(75.0)

    def test_above_maximum_penalised(self):
        result = score(_fund(dividend_yield=0.065), US)
        assert result.yield_score < 75.0
        assert result.yield_score > 0.0

    def test_very_high_yield_scores_zero(self):
        assert score(_fund(dividend_yield=0.10), US).yield_score == 0.0


class TestSwedishDividendYield:
    """Swedish market has a wider sweet spot (3–7%) reflecting local dividend culture."""

    def test_us_penalises_6pct_yield(self):
        # 6% is above US max (5%) — penalised
        result = score(_fund(dividend_yield=0.06), US)
        assert result.yield_score < 75.0

    def test_sweden_rewards_6pct_yield(self):
        # 6% sits within SE sweet spot (3–7%) — near peak
        result = score(_fund(dividend_yield=0.06), SE)
        assert result.yield_score >= 75.0

    def test_sweden_peak_at_5pct(self):
        assert score(_fund(dividend_yield=0.05), SE).yield_score == pytest.approx(100.0)

    def test_sweden_at_minimum_scores_75(self):
        assert score(_fund(dividend_yield=0.03), SE).yield_score == pytest.approx(75.0)

    def test_sweden_at_maximum_scores_75(self):
        assert score(_fund(dividend_yield=0.07), SE).yield_score == pytest.approx(75.0)

    def test_sweden_above_trap_scores_zero(self):
        assert score(_fund(dividend_yield=0.11), SE).yield_score == 0.0

    def test_note_includes_market_code(self):
        result = score(_fund(dividend_yield=0.06), SE)
        assert "SE" in result.notes[0]


class TestPayoutRatio:
    def test_none_scores_zero(self):
        assert score(_fund(), US).payout == 0.0

    def test_conservative_scores_100(self):
        assert score(_fund(payout_ratio=0.25), US).payout == 100.0

    def test_at_threshold_scores_50(self):
        assert score(_fund(payout_ratio=0.60), US).payout == pytest.approx(50.0)

    def test_above_threshold_below_50(self):
        assert score(_fund(payout_ratio=0.80), US).payout < 50.0

    def test_unsustainable_scores_zero(self):
        assert score(_fund(payout_ratio=1.20), US).payout == 0.0


class TestDividendStreak:
    def test_none_scores_zero(self):
        assert score(_fund(), US).streak == 0.0

    def test_short_streak_scores_25(self):
        assert score(_fund(dividend_growth_streak_years=3), US).streak == 25.0

    def test_established_streak_scores_50(self):
        assert score(_fund(dividend_growth_streak_years=7), US).streak == 50.0

    def test_strong_history_scores_75(self):
        assert score(_fund(dividend_growth_streak_years=15), US).streak == 75.0

    def test_aristocrat_scores_100(self):
        assert score(_fund(dividend_growth_streak_years=25), US).streak == 100.0

    def test_streak_scoring_is_market_agnostic(self):
        # Same streak should score identically regardless of market
        f = _fund(dividend_growth_streak_years=15)
        assert score(f, US).streak == score(f, SE).streak


class TestDividendTotal:
    def test_all_missing_scores_zero(self):
        assert score(_fund(), US).total == 0.0

    def test_total_is_average_of_three_components(self):
        result = score(_fund(dividend_yield=0.035, payout_ratio=0.25, dividend_growth_streak_years=25), US)
        assert result.total == pytest.approx(100.0)

    def test_always_three_notes(self):
        assert len(score(_fund(), US).notes) == 3

    def test_score_bounded_0_to_100(self):
        result = score(_fund(dividend_yield=0.035, payout_ratio=0.10, dividend_growth_streak_years=30), US)
        assert 0.0 <= result.total <= 100.0
