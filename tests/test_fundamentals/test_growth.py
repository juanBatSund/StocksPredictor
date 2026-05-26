import pytest

from src.data.models import Fundamentals
from src.fundamentals.growth import score


def _fund(**kwargs) -> Fundamentals:
    base = dict(
        roe=None, debt_to_equity=None, free_cash_flow=None,
        revenue_growth_5y=None, earnings_growth_5y=None,
        dividend_yield=None, payout_ratio=None,
        dividend_growth_streak_years=None, pe_ratio=None, pe_5y_avg=None,
    )
    return Fundamentals(**{**base, **kwargs})


class TestRevenueGrowth:
    def test_none_scores_zero(self):
        assert score(_fund()).revenue == 0.0

    def test_negative_scores_zero(self):
        assert score(_fund(revenue_growth_5y=-0.05)).revenue == 0.0

    def test_zero_scores_zero(self):
        assert score(_fund(revenue_growth_5y=0.0)).revenue == 0.0

    def test_low_positive_is_partial(self):
        # 2.5% is halfway to 5% → 25
        assert score(_fund(revenue_growth_5y=0.025)).revenue == pytest.approx(25.0)

    def test_at_5pct_scores_50(self):
        assert score(_fund(revenue_growth_5y=0.05)).revenue == pytest.approx(50.0)

    def test_moderate_growth_between_50_and_75(self):
        result = score(_fund(revenue_growth_5y=0.10))
        assert 50.0 < result.revenue < 75.0

    def test_at_15pct_scores_75(self):
        assert score(_fund(revenue_growth_5y=0.15)).revenue == pytest.approx(75.0)

    def test_strong_growth_above_75(self):
        assert score(_fund(revenue_growth_5y=0.25)).revenue > 75.0

    def test_extreme_growth_caps_at_100(self):
        assert score(_fund(revenue_growth_5y=1.0)).revenue == 100.0


class TestEarningsGrowth:
    def test_none_scores_zero(self):
        assert score(_fund()).earnings == 0.0

    def test_negative_scores_zero(self):
        assert score(_fund(earnings_growth_5y=-0.10)).earnings == 0.0

    def test_at_5pct_scores_50(self):
        assert score(_fund(earnings_growth_5y=0.05)).earnings == pytest.approx(50.0)


class TestGrowthTotal:
    def test_all_missing_scores_zero(self):
        assert score(_fund()).total == 0.0

    def test_total_is_average_of_revenue_and_earnings(self):
        result = score(_fund(revenue_growth_5y=0.05, earnings_growth_5y=0.15))
        expected = round((50.0 + 75.0) / 2, 2)
        assert result.total == pytest.approx(expected)

    def test_one_missing_halves_score(self):
        only_revenue = score(_fund(revenue_growth_5y=0.15))
        both = score(_fund(revenue_growth_5y=0.15, earnings_growth_5y=0.15))
        assert only_revenue.total == pytest.approx(both.total / 2)

    def test_always_two_notes(self):
        assert len(score(_fund()).notes) == 2

    def test_score_bounded_0_to_100(self):
        result = score(_fund(revenue_growth_5y=999, earnings_growth_5y=999))
        assert 0.0 <= result.total <= 100.0
