import pytest

from config.markets import MARKETS
from src.data.models import Fundamentals
from src.fundamentals.scorer import FundamentalResult, score

US = MARKETS["US"]
SE = MARKETS["SE"]


def _aapl_fundamentals() -> Fundamentals:
    return Fundamentals(
        roe=0.17, debt_to_equity=0.80, free_cash_flow=89_900_000_000,
        revenue_growth_5y=0.092, earnings_growth_5y=0.11,
        dividend_yield=0.0051, payout_ratio=0.158,
        dividend_growth_streak_years=None, pe_ratio=30.4, pe_5y_avg=28.1,
    )


def _empty_fundamentals() -> Fundamentals:
    return Fundamentals(
        roe=None, debt_to_equity=None, free_cash_flow=None,
        revenue_growth_5y=None, earnings_growth_5y=None,
        dividend_yield=None, payout_ratio=None,
        dividend_growth_streak_years=None, pe_ratio=None, pe_5y_avg=None,
    )


def _ideal_fundamentals() -> Fundamentals:
    return Fundamentals(
        roe=0.30, debt_to_equity=0.0, free_cash_flow=1_000_000_000,
        revenue_growth_5y=0.30, earnings_growth_5y=0.30,
        dividend_yield=0.035, payout_ratio=0.25,
        dividend_growth_streak_years=25,
        pe_ratio=10.0, pe_5y_avg=20.0,
        dividend_yield_5y_avg=0.025,  # 5Y avg was 2.5%; current 3.5% → yield risen → undervalued
    )


def _swedish_stock() -> Fundamentals:
    """Realistic Swedish blue chip: healthy fundamentals, 6% yield."""
    return Fundamentals(
        roe=0.15, debt_to_equity=0.60, free_cash_flow=5_000_000_000,
        revenue_growth_5y=0.05, earnings_growth_5y=0.06,
        dividend_yield=0.06, payout_ratio=0.50,
        dividend_growth_streak_years=12,
        pe_ratio=14.0, pe_5y_avg=None,  # pe_5y_avg often missing for SE stocks
    )


class TestFundamentalScorer:
    def test_returns_fundamental_result(self):
        result = score("AAPL", _aapl_fundamentals(), US)
        assert isinstance(result, FundamentalResult)
        assert result.ticker == "AAPL"

    def test_total_in_valid_range(self):
        result = score("AAPL", _aapl_fundamentals(), US)
        assert 0.0 <= result.total <= 100.0

    def test_all_missing_scores_near_zero(self):
        result = score("EMPTY", _empty_fundamentals(), US)
        # pe and yield both missing → valuation neutral 50, contributes 50 * 0.15 = 7.5
        assert result.total == pytest.approx(7.5)

    def test_ideal_stock_scores_100(self):
        result = score("IDEAL", _ideal_fundamentals(), US)
        assert result.total == pytest.approx(100.0)

    def test_deterministic(self):
        f = _aapl_fundamentals()
        assert score("AAPL", f, US).total == score("AAPL", f, US).total

    def test_weighted_sum_is_correct(self):
        result = score("AAPL", _aapl_fundamentals(), US)
        expected = round(
            result.quality.total * 0.40
            + result.growth.total * 0.25
            + result.dividend.total * 0.20
            + result.valuation.total * 0.15,
            2,
        )
        assert result.total == pytest.approx(expected)

    def test_breakdown_has_all_four_components(self):
        bd = score("AAPL", _aapl_fundamentals(), US).breakdown()
        assert set(bd["components"].keys()) == {"quality", "growth", "dividend", "valuation"}

    def test_breakdown_weights_sum_to_one(self):
        bd = score("AAPL", _aapl_fundamentals(), US).breakdown()
        assert sum(c["weight"] for c in bd["components"].values()) == pytest.approx(1.0)


class TestAAPLExample:
    def test_quality_above_70(self):
        assert score("AAPL", _aapl_fundamentals(), US).quality.total > 70.0

    def test_growth_above_55(self):
        assert score("AAPL", _aapl_fundamentals(), US).growth.total > 55.0

    def test_dividend_penalised_for_low_yield(self):
        assert score("AAPL", _aapl_fundamentals(), US).dividend.total < 50.0

    def test_valuation_is_fair(self):
        assert score("AAPL", _aapl_fundamentals(), US).valuation.status == "fair"

    def test_decision_hint_is_watch(self):
        assert score("AAPL", _aapl_fundamentals(), US).decision_hint == "WATCH"


class TestSwedishMarket:
    def test_6pct_yield_rewarded_in_sweden(self):
        us_result = score("VOLVO", _swedish_stock(), US)
        se_result = score("VOLVO", _swedish_stock(), SE)
        assert se_result.dividend.yield_score > us_result.dividend.yield_score

    def test_missing_pe_avg_uses_market_typical(self):
        # pe_5y_avg is None → falls back to SE typical_pe (16)
        # pe_ratio=14 vs SE typical 16 → ratio 0.875 → fair (not unknown)
        result = score("VOLVO", _swedish_stock(), SE)
        assert result.valuation.status != "unknown"

    def test_dividend_component_scores_higher_in_sweden(self):
        # Market selection only directly affects dividend yield scoring and
        # valuation fallback — test the dividend component in isolation.
        us_div = score("VOLVO", _swedish_stock(), US).dividend.total
        se_div = score("VOLVO", _swedish_stock(), SE).dividend.total
        assert se_div > us_div


class TestDecisionHint:
    def test_buy_above_75(self):
        assert score("IDEAL", _ideal_fundamentals(), US).decision_hint == "BUY candidate"

    def test_avoid_all_missing(self):
        assert score("EMPTY", _empty_fundamentals(), US).decision_hint == "AVOID"
