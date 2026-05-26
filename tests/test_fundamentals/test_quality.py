import pytest

from src.data.models import Fundamentals
from src.fundamentals.quality import score


def _fund(**kwargs) -> Fundamentals:
    base = dict(
        roe=None, debt_to_equity=None, free_cash_flow=None,
        revenue_growth_5y=None, earnings_growth_5y=None,
        dividend_yield=None, payout_ratio=None,
        dividend_growth_streak_years=None, pe_ratio=None, pe_5y_avg=None,
    )
    return Fundamentals(**{**base, **kwargs})


class TestROE:
    def test_none_scores_zero(self):
        assert score(_fund()).roe == 0.0

    def test_negative_scores_zero(self):
        assert score(_fund(roe=-0.05)).roe == 0.0

    def test_at_threshold_scores_50(self):
        assert score(_fund(roe=0.12)).roe == pytest.approx(50.0)

    def test_halfway_to_threshold_scores_25(self):
        assert score(_fund(roe=0.06)).roe == pytest.approx(25.0)

    def test_above_threshold_exceeds_50(self):
        assert score(_fund(roe=0.20)).roe > 50.0

    def test_excellent_caps_at_100(self):
        assert score(_fund(roe=0.30)).roe == 100.0

    def test_note_is_populated(self):
        result = score(_fund(roe=0.15))
        assert any("ROE" in n for n in result.notes)


class TestDebtToEquity:
    def test_none_scores_zero(self):
        assert score(_fund()).debt_to_equity == 0.0

    def test_negative_equity_scores_zero(self):
        assert score(_fund(debt_to_equity=-0.1)).debt_to_equity == 0.0

    def test_zero_debt_scores_100(self):
        assert score(_fund(debt_to_equity=0.0)).debt_to_equity == 100.0

    def test_at_threshold_scores_50(self):
        assert score(_fund(debt_to_equity=1.0)).debt_to_equity == pytest.approx(50.0)

    def test_above_threshold_below_50(self):
        result = score(_fund(debt_to_equity=1.5))
        assert result.debt_to_equity == pytest.approx(25.0)

    def test_very_high_scores_zero(self):
        assert score(_fund(debt_to_equity=2.0)).debt_to_equity == 0.0


class TestFCF:
    def test_none_scores_zero(self):
        assert score(_fund()).fcf == 0.0

    def test_negative_scores_zero(self):
        assert score(_fund(free_cash_flow=-1)).fcf == 0.0

    def test_zero_scores_zero(self):
        assert score(_fund(free_cash_flow=0)).fcf == 0.0

    def test_positive_scores_100(self):
        assert score(_fund(free_cash_flow=1)).fcf == 100.0

    def test_large_positive_scores_100(self):
        assert score(_fund(free_cash_flow=89_900_000_000)).fcf == 100.0


class TestQualityTotal:
    def test_all_missing_scores_zero(self):
        assert score(_fund()).total == 0.0

    def test_perfect_inputs_score_100(self):
        result = score(_fund(roe=0.30, debt_to_equity=0.0, free_cash_flow=1))
        assert result.total == 100.0

    def test_total_is_average_of_three_components(self):
        result = score(_fund(roe=0.12, debt_to_equity=1.0, free_cash_flow=1))
        expected = round((50.0 + 50.0 + 100.0) / 3, 2)
        assert result.total == pytest.approx(expected)

    def test_always_three_notes(self):
        assert len(score(_fund()).notes) == 3

    def test_score_bounded_0_to_100(self):
        result = score(_fund(roe=999, debt_to_equity=-999, free_cash_flow=999))
        assert 0.0 <= result.total <= 100.0
