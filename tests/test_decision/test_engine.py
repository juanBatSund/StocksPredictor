"""
Tests for src/decision/engine.py.

Factories build minimal but valid module result objects.
No test makes a network call or touches the file system.
"""

import pytest

from src.decision.engine import (
    ConfidenceBreakdown,
    DecisionResult,
    Gate,
    _compute_confidence,
    _macro_agreement,
    _sentiment_agreement,
    decide,
)
from src.fundamentals.dividend import DividendScore
from src.fundamentals.growth import GrowthScore
from src.fundamentals.quality import QualityScore
from src.fundamentals.scorer import FundamentalResult
from src.macro.tagger import MacroTag, SectorTag
from src.sentiment.scorer import SentimentResult
from src.valuation.scorer import ValuationScore


# ── Factories ──────────────────────────────────────────────────────────────────

def _fr(
    total: float = 80.0,
    val_status: str = "undervalued",
    quality: float = 80.0,
    growth: float = 80.0,
    dividend: float = 80.0,
    val_total: float = 80.0,
) -> FundamentalResult:
    q = QualityScore(total=quality, roe=quality, debt_to_equity=quality, fcf=quality, notes=["t"])
    g = GrowthScore(total=growth, revenue=growth, earnings=growth, notes=["t"])
    d = DividendScore(total=dividend, yield_score=dividend, payout=dividend, streak=dividend, notes=["t"])
    v = ValuationScore(
        total=val_total, pe_score=val_total, dividend_score=val_total,
        status=val_status, pe_deviation_pct=None, dividend_deviation_pct=None,
        notes=["t", "t"],
    )
    return FundamentalResult(ticker="TEST", total=total, quality=q, growth=g, dividend=d, valuation=v)


def _sent(
    score: float = -0.30,
    status: str = "negative",
    trend: float = 0.05,
    confidence: float = 0.70,
) -> SentimentResult:
    return SentimentResult(
        ticker="TEST", score=score, confidence=confidence,
        status=status, trend=trend,
        headline_scores=[], daily_scores=[],
        notes=["t", "t", "t"],
    )


def _macro(
    category: str = "geopolitical_conflict",
    sector: str = "defense",
    direction: str = "bullish",
    strength: float = 0.80,
    confidence: float = 0.85,
    low_confidence: bool = False,
) -> MacroTag:
    from src.macro.rules import CATEGORY_LABELS
    return MacroTag(
        description="test event",
        category=category,
        category_label=CATEGORY_LABELS.get(category, category),
        secondary_category=None, secondary_label=None,
        affected_sectors=[SectorTag(sector=sector, direction=direction, strength=strength, reasoning="test")],
        confidence=confidence, low_confidence=low_confidence,
        triggered_rules=["test"], competing_categories=[],
        category_scores={category: 2},
        strength_modifier=1.0,
        notes=["t", "t", "t"],
    )


# ── BUY decision ───────────────────────────────────────────────────────────────

class TestDecisionBUY:
    def test_all_gates_pass_gives_buy(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        assert r.decision == "BUY"

    def test_score_exactly_at_threshold_is_not_buy(self):
        # Must be > 75, so 75.0 exactly is WATCH
        r = decide("TEST", _fr(75.0, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        assert r.decision != "BUY"

    def test_score_one_above_threshold_with_all_gates_is_buy(self):
        r = decide("TEST", _fr(75.01, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        assert r.decision == "BUY"

    def test_buy_requires_undervalued(self):
        r = decide("TEST", _fr(80, "fair"), sentiment=_sent(-0.3, "negative", 0.05))
        assert r.decision != "BUY"

    def test_buy_requires_negative_sentiment_status(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(0.3, "positive", 0.0))
        assert r.decision != "BUY"

    def test_buy_requires_positive_sentiment_trend(self):
        # Negative status but trend is negative (worsening) → not the contrarian entry
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", -0.05))
        assert r.decision != "BUY"

    def test_buy_with_macro_bullish_tailwind(self):
        # Bullish macro does NOT upgrade, but should not block BUY
        r = decide(
            "TEST", _fr(80, "undervalued"),
            sector="defense",
            sentiment=_sent(-0.3, "negative", 0.05),
            macro=_macro("geopolitical_conflict", "defense", "bullish", 0.80),
        )
        assert r.decision == "BUY"


# ── WATCH decision ─────────────────────────────────────────────────────────────

class TestDecisionWATCH:
    def test_score_in_watch_range_no_sentiment(self):
        r = decide("TEST", _fr(65, "fair"))
        assert r.decision == "WATCH"

    def test_high_score_fair_valuation_downgrade_to_watch(self):
        r = decide("TEST", _fr(80, "fair"), sentiment=_sent(-0.3, "negative", 0.05))
        assert r.decision == "WATCH"

    def test_high_score_undervalued_positive_sentiment(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(0.3, "positive", 0.0))
        assert r.decision == "WATCH"

    def test_high_score_undervalued_neutral_sentiment(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(0.0, "neutral", 0.0))
        assert r.decision == "WATCH"

    def test_high_score_undervalued_no_sentiment(self):
        r = decide("TEST", _fr(80, "undervalued"))
        assert r.decision == "WATCH"  # sentiment unknown → cannot confirm BUY

    def test_macro_headwind_downgrades_buy_to_watch(self):
        r = decide(
            "TEST", _fr(80, "undervalued"),
            sector="technology",
            sentiment=_sent(-0.3, "negative", 0.05),
            macro=_macro("financial_crisis", "technology", "bearish", 0.80),
        )
        assert r.decision == "WATCH"

    def test_watch_score_lower_boundary(self):
        r = decide("TEST", _fr(60.0, "fair"))
        assert r.decision == "WATCH"


# ── AVOID decision ─────────────────────────────────────────────────────────────

class TestDecisionAVOID:
    def test_score_below_60_is_avoid(self):
        r = decide("TEST", _fr(59.9, "fair"))
        assert r.decision == "AVOID"

    def test_score_zero_is_avoid(self):
        r = decide("TEST", _fr(0.0, "overvalued"))
        assert r.decision == "AVOID"

    def test_perfect_sentiment_cannot_rescue_low_score(self):
        r = decide("TEST", _fr(40, "undervalued"), sentiment=_sent(-0.9, "negative", 1.0))
        assert r.decision == "AVOID"


# ── Sentiment gate ─────────────────────────────────────────────────────────────

class TestSentimentGate:
    def _gate(self, r: DecisionResult) -> Gate:
        return next(g for g in r.gates if g.name == "sentiment")

    def test_negative_improving_passes(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        assert self._gate(r).passed is True

    def test_negative_worsening_fails(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", -0.05))
        assert self._gate(r).passed is False

    def test_positive_fails(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(0.3, "positive", 0.1))
        assert self._gate(r).passed is False

    def test_neutral_fails(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(0.0, "neutral", 0.1))
        assert self._gate(r).passed is False

    def test_zero_trend_fails(self):
        # Exactly zero trend — not improving
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.0))
        assert self._gate(r).passed is False

    def test_no_sentiment_gate_is_none(self):
        r = decide("TEST", _fr(80, "undervalued"))
        assert self._gate(r).passed is None


# ── Macro adjustment ──────────────────────────────────────────────────────────

class TestMacroAdjustment:
    def test_strong_bearish_macro_downgrades_buy(self):
        r = decide(
            "TEST", _fr(80, "undervalued"),
            sector="technology",
            sentiment=_sent(-0.3, "negative", 0.05),
            macro=_macro("financial_crisis", "technology", "bearish", 0.90),
        )
        assert r.decision == "WATCH"

    def test_bearish_at_threshold_downgrades_buy(self):
        # Exactly at threshold (0.60) → downgrade
        r = decide(
            "TEST", _fr(80, "undervalued"),
            sector="technology",
            sentiment=_sent(-0.3, "negative", 0.05),
            macro=_macro("regulatory", "technology", "bearish", 0.60),
        )
        assert r.decision == "WATCH"

    def test_bearish_below_threshold_no_downgrade(self):
        # 0.59 < 0.60 → no downgrade
        r = decide(
            "TEST", _fr(80, "undervalued"),
            sector="technology",
            sentiment=_sent(-0.3, "negative", 0.05),
            macro=_macro("regulatory", "technology", "bearish", 0.59),
        )
        assert r.decision == "BUY"

    def test_bullish_macro_does_not_upgrade_watch(self):
        # WATCH due to score; bullish macro should not change it
        r = decide(
            "TEST", _fr(65, "fair"),
            sector="defense",
            macro=_macro("geopolitical_conflict", "defense", "bullish", 0.80),
        )
        assert r.decision == "WATCH"

    def test_no_sector_macro_no_adjustment(self):
        # Without sector, macro impact cannot be determined
        r = decide(
            "TEST", _fr(80, "undervalued"),
            sentiment=_sent(-0.3, "negative", 0.05),
            macro=_macro("financial_crisis", "technology", "bearish", 0.90),
        )
        assert r.decision == "BUY"

    def test_sector_not_in_macro_table_no_adjustment(self):
        # Macro tags technology, but we're in healthcare → no impact
        r = decide(
            "TEST", _fr(80, "undervalued"),
            sector="healthcare",
            sentiment=_sent(-0.3, "negative", 0.05),
            macro=_macro("financial_crisis", "technology", "bearish", 0.90),
        )
        assert r.decision == "BUY"

    def test_macro_avoid_not_watched_does_not_become_avoid(self):
        # Engine only downgrades BUY→WATCH, not WATCH→AVOID
        r = decide(
            "TEST", _fr(65, "fair"),
            sector="technology",
            macro=_macro("financial_crisis", "technology", "bearish", 0.90),
        )
        assert r.decision == "WATCH"


# ── Gate structure ─────────────────────────────────────────────────────────────

class TestGates:
    def test_exactly_three_gates_evaluated(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        assert len(r.gates) == 3

    def test_gate_names_present(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        names = {g.name for g in r.gates}
        assert "fundamental_score" in names
        assert "valuation_status" in names
        assert "sentiment" in names

    def test_score_gate_observed_value(self):
        r = decide("TEST", _fr(76.5, "fair"))
        g = next(g for g in r.gates if g.name == "fundamental_score")
        assert "76.5" in g.observed

    def test_valuation_gate_observed_matches_status(self):
        r = decide("TEST", _fr(80, "fair"))
        g = next(g for g in r.gates if g.name == "valuation_status")
        assert g.observed == "fair"
        assert g.passed is False

    def test_gate_required_field_present(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        for g in r.gates:
            assert isinstance(g.required, str) and len(g.required) > 0

    def test_gate_note_is_nonempty(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        for g in r.gates:
            assert isinstance(g.note, str) and len(g.note) > 0


# ── Confidence ────────────────────────────────────────────────────────────────

class TestConfidence:
    def test_confidence_bounded(self):
        r = decide("TEST", _fr(0, "unknown"))
        assert 0.0 <= r.confidence <= 1.0

    def test_unknown_valuation_lowers_confidence(self):
        r_good = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        r_unknown = decide("TEST", _fr(80, "unknown"), sentiment=_sent(-0.3, "negative", 0.05))
        assert r_unknown.confidence < r_good.confidence

    def test_missing_fields_lower_confidence(self):
        r_full = decide("TEST", _fr(80, "undervalued"), missing_fields=[])
        r_missing = decide("TEST", _fr(80, "undervalued"), missing_fields=["roe", "fcf", "dividendYield"])
        assert r_missing.confidence <= r_full.confidence

    def test_aligned_signals_raise_confidence(self):
        # BUY decision + negative improving sentiment + bullish macro = all aligned
        r = decide(
            "TEST", _fr(80, "undervalued"),
            sector="defense",
            sentiment=_sent(-0.5, "negative", 0.1, confidence=0.9),
            macro=_macro("geopolitical_conflict", "defense", "bullish", 0.80, confidence=0.9),
        )
        assert r.confidence > 0.65

    def test_conflicting_signals_lower_confidence(self):
        # BUY decision but macro is bearish → signal_agreement lower
        r_aligned = decide(
            "TEST", _fr(80, "undervalued"),
            sector="defense",
            sentiment=_sent(-0.3, "negative", 0.05),
            macro=_macro("geopolitical_conflict", "defense", "bullish", 0.80),
        )
        r_conflicting = decide(
            "TEST", _fr(80, "undervalued"),
            sector="defense",
            sentiment=_sent(-0.3, "negative", 0.05),
            macro=_macro("financial_crisis", "defense", "bearish", 0.40),
        )
        assert r_conflicting.confidence < r_aligned.confidence

    def test_confidence_breakdown_has_four_fields(self):
        r = decide("TEST", _fr(80, "undervalued"))
        cb = r.confidence_breakdown
        assert hasattr(cb, "data_quality")
        assert hasattr(cb, "valuation_certainty")
        assert hasattr(cb, "signal_agreement")
        assert hasattr(cb, "soft_signal_quality")
        assert hasattr(cb, "total")

    def test_confidence_breakdown_components_bounded(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        cb = r.confidence_breakdown
        for val in [cb.data_quality, cb.valuation_certainty, cb.signal_agreement, cb.soft_signal_quality]:
            assert 0.0 <= val <= 1.0


# ── Confidence formula unit tests ─────────────────────────────────────────────

class TestComputeConfidence:
    def test_no_missing_fields_no_unknowns_high_conf(self):
        c = _compute_confidence(
            score=80, val_status="undervalued", missing_fields=[],
            sentiment=_sent(-0.3, "negative", 0.05, 0.9),
            macro_sector_direction="bullish", macro_sector_strength=0.8,
            macro_confidence=0.9, decision="BUY",
        )
        assert c.total > 0.70

    def test_unknown_valuation_zeroes_certainty_component(self):
        c = _compute_confidence(
            score=80, val_status="unknown", missing_fields=[],
            sentiment=None, macro_sector_direction=None,
            macro_sector_strength=None, macro_confidence=None, decision="WATCH",
        )
        assert c.valuation_certainty == 0.0

    def test_undervalued_sets_certainty_to_one(self):
        c = _compute_confidence(
            score=80, val_status="undervalued", missing_fields=[],
            sentiment=None, macro_sector_direction=None,
            macro_sector_strength=None, macro_confidence=None, decision="WATCH",
        )
        assert c.valuation_certainty == 1.0

    def test_many_missing_fields_reduces_data_quality(self):
        c_full = _compute_confidence(
            score=80, val_status="fair", missing_fields=[],
            sentiment=None, macro_sector_direction=None,
            macro_sector_strength=None, macro_confidence=None, decision="WATCH",
        )
        c_missing = _compute_confidence(
            score=80, val_status="fair", missing_fields=["a", "b", "c", "d", "e"],
            sentiment=None, macro_sector_direction=None,
            macro_sector_strength=None, macro_confidence=None, decision="WATCH",
        )
        assert c_missing.data_quality < c_full.data_quality


# ── Signal agreement helpers ──────────────────────────────────────────────────

class TestSentimentAgreement:
    def test_negative_improving_agrees_with_buy(self):
        assert _sentiment_agreement(_sent(-0.3, "negative", 0.05), "BUY") == pytest.approx(1.0)

    def test_positive_disagrees_with_buy(self):
        assert _sentiment_agreement(_sent(0.3, "positive", 0.0), "BUY") == pytest.approx(0.0)

    def test_neutral_is_half_for_buy(self):
        assert _sentiment_agreement(_sent(0.0, "neutral", 0.0), "BUY") == pytest.approx(0.5)

    def test_positive_agrees_with_avoid(self):
        assert _sentiment_agreement(_sent(0.3, "positive", 0.0), "AVOID") == pytest.approx(0.80)

    def test_none_sentiment_returns_half(self):
        assert _sentiment_agreement(None, "BUY") == pytest.approx(0.5)

    def test_watch_always_half(self):
        assert _sentiment_agreement(_sent(-0.3, "negative", 0.05), "WATCH") == pytest.approx(0.5)
        assert _sentiment_agreement(_sent(0.3, "positive", 0.0), "WATCH") == pytest.approx(0.5)


class TestMacroAgreement:
    def test_bullish_agrees_with_buy(self):
        assert _macro_agreement("bullish", "BUY") == pytest.approx(1.0)

    def test_bearish_disagrees_with_buy(self):
        assert _macro_agreement("bearish", "BUY") == pytest.approx(0.0)

    def test_mixed_is_half(self):
        assert _macro_agreement("mixed", "BUY") == pytest.approx(0.5)
        assert _macro_agreement("mixed", "AVOID") == pytest.approx(0.5)

    def test_none_direction_returns_half(self):
        assert _macro_agreement(None, "BUY") == pytest.approx(0.5)

    def test_bearish_agrees_with_avoid(self):
        assert _macro_agreement("bearish", "AVOID") == pytest.approx(1.0)

    def test_watch_always_half(self):
        assert _macro_agreement("bullish", "WATCH") == pytest.approx(0.5)
        assert _macro_agreement("bearish", "WATCH") == pytest.approx(0.5)


# ── Uncertainty flags ─────────────────────────────────────────────────────────

class TestUncertaintyFlags:
    def test_no_sentiment_flags_uncertainty(self):
        r = decide("TEST", _fr(80, "undervalued"))
        assert any("Sentiment" in f and "no" in f.lower() for f in r.uncertainty_flags)

    def test_no_macro_flags_uncertainty(self):
        r = decide("TEST", _fr(80, "undervalued"))
        assert any("Macro" in f and "no" in f.lower() for f in r.uncertainty_flags)

    def test_unknown_valuation_flags_uncertainty(self):
        r = decide("TEST", _fr(80, "unknown"))
        assert any("Valuation" in f and "unknown" in f.lower() for f in r.uncertainty_flags)

    def test_low_sentiment_confidence_flags_uncertainty(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05, confidence=0.05))
        assert any("Sentiment" in f and "low" in f.lower() for f in r.uncertainty_flags)

    def test_no_sector_with_macro_flags_uncertainty(self):
        r = decide("TEST", _fr(80, "undervalued"), macro=_macro())
        assert any("Macro" in f and "sector" in f.lower() for f in r.uncertainty_flags)

    def test_low_confidence_macro_flags_uncertainty(self):
        r = decide(
            "TEST", _fr(80, "undervalued"),
            sector="defense",
            macro=_macro(confidence=0.20, low_confidence=True),
        )
        assert any("Macro" in f and "low confidence" in f.lower() for f in r.uncertainty_flags)


# ── Contributing and rejected factors ─────────────────────────────────────────

class TestFactors:
    def test_passing_score_gate_is_contributing(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        names = [f.name for f in r.contributing_factors]
        assert any("score" in n.lower() or "Fundamental" in n for n in names)

    def test_failing_valuation_gate_is_rejected(self):
        r = decide("TEST", _fr(80, "fair"))
        names = [f.name for f in r.rejected_factors]
        assert any("Valuation" in n for n in names)

    def test_positive_sentiment_gate_in_contributing_for_buy(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        names = [f.name for f in r.contributing_factors]
        assert any("Sentiment" in n for n in names)

    def test_bullish_macro_in_contributing(self):
        r = decide(
            "TEST", _fr(80, "undervalued"),
            sector="defense",
            sentiment=_sent(-0.3, "negative", 0.05),
            macro=_macro("geopolitical_conflict", "defense", "bullish", 0.80),
        )
        names = [f.name for f in r.contributing_factors]
        assert any("Macro tailwind" in n for n in names)

    def test_bearish_macro_in_rejected(self):
        r = decide(
            "TEST", _fr(80, "undervalued"),
            sector="technology",
            sentiment=_sent(-0.3, "negative", 0.05),
            macro=_macro("financial_crisis", "technology", "bearish", 0.80),
        )
        names = [f.name for f in r.rejected_factors]
        assert any("Macro headwind" in n for n in names)

    def test_factor_direction_is_valid(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        valid = {"supporting", "opposing", "neutral"}
        for f in r.contributing_factors + r.rejected_factors:
            assert f.direction in valid


# ── Reasoning trace ───────────────────────────────────────────────────────────

class TestReasoningTrace:
    def test_trace_is_nonempty_list(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        assert isinstance(r.reasoning_trace, list)
        assert len(r.reasoning_trace) >= 5

    def test_trace_contains_decision(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        assert any("BUY" in step for step in r.reasoning_trace)

    def test_trace_mentions_all_gates(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        trace = " ".join(r.reasoning_trace)
        assert "Gate 1" in trace
        assert "Gate 2" in trace
        assert "Gate 3" in trace

    def test_trace_mentions_confidence(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        assert any("Confidence" in step for step in r.reasoning_trace)

    def test_trace_mentions_macro_when_provided(self):
        r = decide(
            "TEST", _fr(80, "undervalued"),
            sector="defense",
            sentiment=_sent(-0.3, "negative", 0.05),
            macro=_macro("geopolitical_conflict", "defense", "bullish", 0.80),
        )
        assert any("Macro" in step or "macro" in step for step in r.reasoning_trace)


# ── Output structure ──────────────────────────────────────────────────────────

class TestOutputStructure:
    def test_notes_has_three_entries(self):
        r = decide("TEST", _fr(80, "undervalued"))
        assert len(r.notes) == 3

    def test_ticker_preserved(self):
        r = decide("MSFT", _fr(80, "undervalued"))
        assert r.ticker == "MSFT"

    def test_score_preserved(self):
        r = decide("TEST", _fr(76.5, "fair"))
        assert r.score == pytest.approx(76.5)

    def test_component_scores_preserved(self):
        r = decide("TEST", _fr(80, "undervalued", quality=70, growth=60, dividend=50, val_total=90))
        assert r.quality_score == pytest.approx(70.0)
        assert r.growth_score == pytest.approx(60.0)
        assert r.dividend_score == pytest.approx(50.0)
        assert r.valuation_score == pytest.approx(90.0)

    def test_sentiment_fields_none_when_absent(self):
        r = decide("TEST", _fr(80, "undervalued"))
        assert r.sentiment_score is None
        assert r.sentiment_status is None
        assert r.sentiment_trend is None

    def test_sentiment_fields_populated_when_present(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.05))
        assert r.sentiment_score == pytest.approx(-0.30)
        assert r.sentiment_status == "negative"
        assert r.sentiment_trend == pytest.approx(0.05)

    def test_macro_fields_none_when_absent(self):
        r = decide("TEST", _fr(80, "undervalued"))
        assert r.macro_category is None
        assert r.macro_sector_direction is None

    def test_macro_fields_populated_when_present(self):
        r = decide(
            "TEST", _fr(80, "undervalued"),
            sector="defense",
            macro=_macro("geopolitical_conflict", "defense", "bullish", 0.80),
        )
        assert r.macro_category == "geopolitical_conflict"
        assert r.macro_sector_direction == "bullish"
        assert r.macro_sector_strength == pytest.approx(0.80)


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_perfect_stock_all_100_is_buy(self):
        r = decide(
            "PERFECT",
            _fr(100, "undervalued", quality=100, growth=100, dividend=100, val_total=100),
            sentiment=_sent(-0.9, "negative", 1.0, confidence=1.0),
        )
        assert r.decision == "BUY"

    def test_worst_stock_all_zero_is_avoid(self):
        r = decide(
            "WORST",
            _fr(0.0, "overvalued", quality=0, growth=0, dividend=0, val_total=0),
        )
        assert r.decision == "AVOID"

    def test_macro_with_empty_sector_list(self):
        from src.macro.rules import CATEGORY_LABELS
        m = MacroTag(
            description="test", category="pandemic",
            category_label=CATEGORY_LABELS["pandemic"],
            secondary_category=None, secondary_label=None,
            affected_sectors=[],   # no sectors
            confidence=0.8, low_confidence=False,
            triggered_rules=["pandemic"], competing_categories=[],
            category_scores={"pandemic": 1}, strength_modifier=1.0,
            notes=["", "", ""],
        )
        r = decide(
            "TEST", _fr(80, "undervalued"),
            sector="technology",
            sentiment=_sent(-0.3, "negative", 0.05),
            macro=m,
        )
        assert r.decision == "BUY"  # no matching sector, no downgrade

    def test_sentiment_trend_exactly_zero_fails_gate(self):
        r = decide("TEST", _fr(80, "undervalued"), sentiment=_sent(-0.3, "negative", 0.0))
        g = next(g for g in r.gates if g.name == "sentiment")
        assert g.passed is False

    def test_avoid_not_rescued_by_good_macro(self):
        r = decide(
            "TEST", _fr(50, "undervalued"),
            sector="defense",
            macro=_macro("geopolitical_conflict", "defense", "bullish", 0.80),
        )
        assert r.decision == "AVOID"


# ── Determinism ───────────────────────────────────────────────────────────────

class TestDeterminism:
    def test_same_inputs_produce_same_decision(self):
        fr = _fr(80, "undervalued")
        sent = _sent(-0.3, "negative", 0.05)
        r1 = decide("AAPL", fr, sentiment=sent)
        r2 = decide("AAPL", fr, sentiment=sent)
        assert r1.decision == r2.decision

    def test_same_inputs_produce_same_confidence(self):
        fr = _fr(80, "undervalued")
        sent = _sent(-0.3, "negative", 0.05)
        r1 = decide("AAPL", fr, sentiment=sent)
        r2 = decide("AAPL", fr, sentiment=sent)
        assert r1.confidence == r2.confidence

    def test_same_inputs_produce_same_trace_length(self):
        fr = _fr(80, "undervalued")
        sent = _sent(-0.3, "negative", 0.05)
        r1 = decide("AAPL", fr, sentiment=sent)
        r2 = decide("AAPL", fr, sentiment=sent)
        assert len(r1.reasoning_trace) == len(r2.reasoning_trace)
