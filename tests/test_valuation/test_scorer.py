import pytest

from config.markets import MARKETS
from src.data.models import Fundamentals
from src.valuation.scorer import FAIR, OVERVALUED, UNDERVALUED, UNKNOWN, score

US = MARKETS["US"]
SE = MARKETS["SE"]


def _fund(**kwargs) -> Fundamentals:
    base = dict(
        roe=None, debt_to_equity=None, free_cash_flow=None,
        revenue_growth_5y=None, earnings_growth_5y=None,
        dividend_yield=None, payout_ratio=None,
        dividend_growth_streak_years=None,
        pe_ratio=None, pe_5y_avg=None, dividend_yield_5y_avg=None,
    )
    return Fundamentals(**{**base, **kwargs})


# ── P/E status ─────────────────────────────────────────────────────────────────

class TestValuationStatus:
    def test_missing_pe_and_yield_is_unknown(self):
        result = score(_fund(), US)
        assert result.total == pytest.approx(50.0)
        assert result.status == UNKNOWN

    def test_missing_avg_uses_market_typical_pe(self):
        # pe_5y_avg missing → falls back to US typical_pe (20.0)
        # pe=20 vs avg=20 → ratio 1.0 → score 60, fair
        result = score(_fund(pe_ratio=20.0), US)
        assert result.status == FAIR
        assert result.total == pytest.approx(60.0)

    def test_zero_avg_is_unknown(self):
        result = score(_fund(pe_ratio=20.0, pe_5y_avg=0.0), US)
        assert result.total == pytest.approx(50.0)
        assert result.status == UNKNOWN

    def test_pe_at_par_is_fair(self):
        result = score(_fund(pe_ratio=20.0, pe_5y_avg=20.0), US)
        assert result.status == FAIR

    def test_pe_much_below_avg_is_undervalued(self):
        result = score(_fund(pe_ratio=12.0, pe_5y_avg=20.0), US)
        assert result.status == UNDERVALUED
        assert result.total == pytest.approx(100.0)

    def test_pe_below_avg_is_undervalued(self):
        result = score(_fund(pe_ratio=16.0, pe_5y_avg=20.0), US)
        assert result.status == UNDERVALUED

    def test_pe_above_avg_is_overvalued(self):
        result = score(_fund(pe_ratio=28.0, pe_5y_avg=20.0), US)
        assert result.status == OVERVALUED
        assert result.total == pytest.approx(0.0)

    def test_pe_slightly_above_avg_is_fair(self):
        result = score(_fund(pe_ratio=21.6, pe_5y_avg=20.0), US)
        assert result.status == FAIR


# ── market P/E fallback ────────────────────────────────────────────────────────

class TestMarketTypicalPEFallback:
    def test_us_typical_pe_used_when_avg_missing(self):
        # US typical PE = 20. PE 14 → ratio 0.7 → undervalued (100)
        result = score(_fund(pe_ratio=14.0), US)
        assert result.status == UNDERVALUED
        assert result.total == pytest.approx(100.0)

    def test_swedish_typical_pe_used_when_avg_missing(self):
        # SE typical PE = 16. PE 14 → ratio 0.875 → fair
        result = score(_fund(pe_ratio=14.0), SE)
        assert result.status == FAIR

    def test_same_pe_scores_differently_by_market(self):
        # PE 10 vs US typical (20) → ratio 0.5 → 100
        # PE 10 vs SE typical (16) → ratio 0.625 → also ≤0.70 → 100
        us_score = score(_fund(pe_ratio=10.0), US).total
        se_score = score(_fund(pe_ratio=10.0), SE).total
        assert us_score == se_score == 100.0

    def test_note_indicates_fallback_source(self):
        result = score(_fund(pe_ratio=20.0), US)
        assert "market avg" in result.notes[0]

    def test_note_indicates_5y_avg_when_available(self):
        result = score(_fund(pe_ratio=20.0, pe_5y_avg=20.0), US)
        assert "5Y avg" in result.notes[0]


# ── P/E score values ───────────────────────────────────────────────────────────

class TestValuationScore:
    def test_score_at_exactly_par(self):
        result = score(_fund(pe_ratio=20.0, pe_5y_avg=20.0), US)
        assert result.total == pytest.approx(60.0)

    def test_score_at_0_70_ratio(self):
        result = score(_fund(pe_ratio=14.0, pe_5y_avg=20.0), US)
        assert result.total == pytest.approx(100.0)

    def test_score_bounded_0_to_100(self):
        result = score(_fund(pe_ratio=500.0, pe_5y_avg=10.0), US)
        assert 0.0 <= result.total <= 100.0

    def test_notes_always_has_two_entries(self):
        result = score(_fund(pe_ratio=20.0, pe_5y_avg=20.0), US)
        assert len(result.notes) == 2
        assert result.notes[0]
        assert result.notes[1]


# ── P/E % deviation ───────────────────────────────────────────────────────────

class TestPEDeviation:
    def test_pe_at_par_deviation_is_zero(self):
        result = score(_fund(pe_ratio=20.0, pe_5y_avg=20.0), US)
        assert result.pe_deviation_pct == pytest.approx(0.0)

    def test_pe_below_avg_deviation_is_negative(self):
        # (16 − 20) / 20 × 100 = −20.0 %
        result = score(_fund(pe_ratio=16.0, pe_5y_avg=20.0), US)
        assert result.pe_deviation_pct == pytest.approx(-20.0)

    def test_pe_above_avg_deviation_is_positive(self):
        # (24 − 20) / 20 × 100 = +20.0 %
        result = score(_fund(pe_ratio=24.0, pe_5y_avg=20.0), US)
        assert result.pe_deviation_pct == pytest.approx(20.0)

    def test_pe_missing_deviation_is_none(self):
        result = score(_fund(), US)
        assert result.pe_deviation_pct is None

    def test_zero_avg_deviation_is_none(self):
        result = score(_fund(pe_ratio=20.0, pe_5y_avg=0.0), US)
        assert result.pe_deviation_pct is None

    def test_deviation_sign_matches_valuation_direction(self):
        # Negative deviation (pe < avg) → undervalued; positive → overvalued
        cheap = score(_fund(pe_ratio=10.0, pe_5y_avg=20.0), US)
        expensive = score(_fund(pe_ratio=30.0, pe_5y_avg=20.0), US)
        assert cheap.pe_deviation_pct < 0
        assert expensive.pe_deviation_pct > 0
        assert cheap.status == UNDERVALUED
        assert expensive.status == OVERVALUED


# ── Dividend yield scoring ────────────────────────────────────────────────────

class TestDividendYieldScoring:
    def test_no_yield_history_is_neutral(self):
        # Without a 5Y average there is nothing to compare against
        result = score(_fund(dividend_yield=0.04), US)
        assert result.dividend_score == pytest.approx(50.0)

    def test_missing_yield_is_neutral(self):
        result = score(_fund(), US)
        assert result.dividend_score == pytest.approx(50.0)

    def test_yield_at_par_scores_60(self):
        # ratio = 1.0 → lerp(1.0, 1.00, 1.15, 60, 80) = 60
        result = score(_fund(dividend_yield=0.03, dividend_yield_5y_avg=0.03), US)
        assert result.dividend_score == pytest.approx(60.0)

    def test_yield_30pct_above_history_scores_100(self):
        # ratio = 0.04 / 0.03 = 1.333 ≥ 1.30 → 100
        result = score(_fund(dividend_yield=0.04, dividend_yield_5y_avg=0.03), US)
        assert result.dividend_score == pytest.approx(100.0)

    def test_yield_below_history_scores_zero(self):
        # ratio = 0.02 / 0.03 = 0.667 < 0.70 → 0
        result = score(_fund(dividend_yield=0.02, dividend_yield_5y_avg=0.03), US)
        assert result.dividend_score == pytest.approx(0.0)

    def test_yield_slightly_above_history_is_fair(self):
        # ratio = 1.1 → in fair band (60–80), status fair
        result = score(_fund(dividend_yield=0.033, dividend_yield_5y_avg=0.03), US)
        assert FAIR == result.status

    def test_yield_well_above_history_is_undervalued(self):
        result = score(_fund(dividend_yield=0.05, dividend_yield_5y_avg=0.03), US)
        assert result.status == UNDERVALUED

    def test_yield_well_below_history_is_overvalued(self):
        result = score(_fund(dividend_yield=0.015, dividend_yield_5y_avg=0.03), US)
        assert result.status == OVERVALUED


# ── Dividend yield % deviation ────────────────────────────────────────────────

class TestDividendDeviation:
    def test_yield_at_par_deviation_is_zero(self):
        result = score(_fund(dividend_yield=0.03, dividend_yield_5y_avg=0.03), US)
        assert result.dividend_deviation_pct == pytest.approx(0.0)

    def test_yield_above_avg_deviation_is_positive(self):
        # (0.04 − 0.03) / 0.03 × 100 = +33.3 %
        result = score(_fund(dividend_yield=0.04, dividend_yield_5y_avg=0.03), US)
        assert result.dividend_deviation_pct == pytest.approx(33.3, abs=0.1)

    def test_yield_below_avg_deviation_is_negative(self):
        # (0.02 − 0.03) / 0.03 × 100 = −33.3 %
        result = score(_fund(dividend_yield=0.02, dividend_yield_5y_avg=0.03), US)
        assert result.dividend_deviation_pct == pytest.approx(-33.3, abs=0.1)

    def test_yield_missing_deviation_is_none(self):
        result = score(_fund(), US)
        assert result.dividend_deviation_pct is None

    def test_no_history_deviation_is_none(self):
        # yield present but no historical avg → cannot compute deviation
        result = score(_fund(dividend_yield=0.04), US)
        assert result.dividend_deviation_pct is None

    def test_positive_deviation_correlates_with_undervalued_direction(self):
        # Higher yield than history means price fell → undervalued signal → positive deviation
        result = score(_fund(dividend_yield=0.04, dividend_yield_5y_avg=0.03), US)
        assert result.dividend_deviation_pct > 0
        assert result.dividend_score == pytest.approx(100.0)


# ── Composite (P/E + yield) ───────────────────────────────────────────────────

class TestCompositeValuation:
    def test_both_undervalued_gives_undervalued(self):
        # pe: 14/20 = 0.70 → 100; yield: 0.04/0.03 = 1.33 → 100; total = 100
        result = score(
            _fund(pe_ratio=14.0, pe_5y_avg=20.0, dividend_yield=0.04, dividend_yield_5y_avg=0.03),
            US,
        )
        assert result.status == UNDERVALUED
        assert result.total == pytest.approx(100.0)

    def test_both_overvalued_gives_overvalued(self):
        # pe: 30/20 = 1.5 → 0; yield: 0.015/0.03 = 0.5 → 0; total = 0
        result = score(
            _fund(pe_ratio=30.0, pe_5y_avg=20.0, dividend_yield=0.015, dividend_yield_5y_avg=0.03),
            US,
        )
        assert result.status == OVERVALUED
        assert result.total == pytest.approx(0.0)

    def test_mixed_signals_weighted_60_40(self):
        # pe: 20/20 = 1.0 → pe_score=60; yield: 0.04/0.03 = 1.33 → div_score=100
        # total = 60×0.60 + 100×0.40 = 36 + 40 = 76 → fair (40 ≤ 76 < 80)
        result = score(
            _fund(pe_ratio=20.0, pe_5y_avg=20.0, dividend_yield=0.04, dividend_yield_5y_avg=0.03),
            US,
        )
        assert result.total == pytest.approx(76.0)
        assert result.status == FAIR

    def test_pe_only_when_no_yield_history(self):
        # No dividend_yield_5y_avg → div_real=False → total = pe_score only
        result = score(_fund(pe_ratio=14.0, pe_5y_avg=20.0), US)
        assert result.total == pytest.approx(100.0)

    def test_yield_only_when_pe_missing(self):
        # No pe_ratio → pe_real=False → total = div_score only
        result = score(_fund(dividend_yield=0.04, dividend_yield_5y_avg=0.03), US)
        assert result.total == pytest.approx(100.0)

    def test_all_fields_present_in_result(self):
        result = score(
            _fund(pe_ratio=20.0, pe_5y_avg=20.0, dividend_yield=0.03, dividend_yield_5y_avg=0.03),
            US,
        )
        assert result.pe_score == pytest.approx(60.0)
        assert result.dividend_score == pytest.approx(60.0)
        assert result.pe_deviation_pct == pytest.approx(0.0)
        assert result.dividend_deviation_pct == pytest.approx(0.0)
        assert result.total == pytest.approx(60.0)

    def test_both_missing_is_unknown_not_fair(self):
        result = score(_fund(), US)
        assert result.status == UNKNOWN

    def test_score_bounded_0_to_100_when_composite(self):
        result = score(
            _fund(pe_ratio=500.0, pe_5y_avg=10.0, dividend_yield=0.001, dividend_yield_5y_avg=0.05),
            US,
        )
        assert 0.0 <= result.total <= 100.0
