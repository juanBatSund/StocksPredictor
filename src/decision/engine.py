"""
Deterministic investment decision engine.

Integrates hard signals (fundamentals, valuation) with soft signals
(sentiment, macro) to produce a final BUY / WATCH / AVOID suggestion
with a complete reasoning trace.

Design philosophy
-----------------
Hard signals gate the decision — they can PREVENT BUY but cannot
FORCE it.  Soft signals can only downgrade (BUY→WATCH), never upgrade
(WATCH→BUY).  Every rule that fired is recorded; every rule that
failed is also recorded.  Nothing is hidden.

Known limitations are documented in docs/DECISION_MODULE.md.

Public API
----------
decide(ticker, fundamental, sector, sentiment, macro, missing_fields)
    → DecisionResult
"""

from dataclasses import dataclass, field
from typing import Optional

from config.settings import SCORE_BUY, SCORE_WATCH_MIN
from src.fundamentals.scorer import FundamentalResult
from src.logging.logger import log_input, log_result
from src.macro.tagger import MacroTag
from src.sentiment.scorer import SentimentResult
from src.valuation.scorer import UNDERVALUED, UNKNOWN

_MODULE = "decision.engine"

# Macro sector impact strength required to trigger a BUY→WATCH downgrade
_MACRO_DOWNGRADE_THRESHOLD = 0.60

# Sentiment confidence below this triggers an uncertainty flag
_SENTIMENT_LOW_CONFIDENCE = 0.20

# One missing fundamental field reduces data quality by this amount
_MISSING_FIELD_PENALTY = 0.07


# ── Output types ───────────────────────────────────────────────────────────────

@dataclass
class Gate:
    """One pass/fail decision criterion evaluated during the decision."""
    name: str
    passed: Optional[bool]   # None = no data available to evaluate
    observed: str            # actual value seen
    required: str            # what was required to pass
    note: str                # plain-English explanation


@dataclass
class Factor:
    """A single named input that supported or opposed the decision."""
    name: str
    direction: str           # "supporting" | "opposing" | "neutral"
    note: str


@dataclass
class ConfidenceBreakdown:
    """Four explicit components that sum (weighted) to the confidence score."""
    data_quality: float       # based on missing fundamental fields (weight 30%)
    valuation_certainty: float  # based on valuation.status clarity (weight 25%)
    signal_agreement: float   # do soft signals agree with the decision? (weight 30%)
    soft_signal_quality: float  # confidence in the soft signal modules (weight 15%)
    total: float              # weighted sum, clamped [0.0, 1.0]


@dataclass
class DecisionResult:
    """Complete output of the decision engine — nothing is hidden."""
    ticker: str
    decision: str                        # "BUY" | "WATCH" | "AVOID"

    # Core score (from fundamentals module — not modified by soft signals)
    score: float                         # 0–100 composite
    quality_score: float
    growth_score: float
    dividend_score: float
    valuation_score: float
    valuation_status: str

    # Confidence (separate from the investment score)
    confidence: float                    # 0.0–1.0
    confidence_breakdown: ConfidenceBreakdown

    # Gate evaluation (one entry per gate checked)
    gates: list[Gate]

    # Signal contributions
    contributing_factors: list[Factor]
    rejected_factors: list[Factor]

    # Uncertainty — reasons to distrust this decision
    uncertainty_flags: list[str]

    # Soft signal context (raw values passed through for the caller)
    sentiment_score: Optional[float]
    sentiment_status: Optional[str]
    sentiment_trend: Optional[float]
    sentiment_confidence: Optional[float]
    macro_category: Optional[str]
    macro_sector_direction: Optional[str]
    macro_sector_strength: Optional[float]
    macro_confidence: Optional[float]

    # Full step-by-step reasoning
    reasoning_trace: list[str]
    notes: list[str]                     # summary notes [decision, score, uncertainty]


# ── Public entry point ─────────────────────────────────────────────────────────

def decide(
    ticker: str,
    fundamental: FundamentalResult,
    sector: str | None = None,
    sentiment: SentimentResult | None = None,
    macro: MacroTag | None = None,
    missing_fields: list[str] | None = None,
) -> DecisionResult:
    """
    Produce a BUY / WATCH / AVOID decision from pre-computed module results.

    Parameters
    ----------
    ticker          : Stock ticker symbol (for logging and output).
    fundamental     : Result from src.fundamentals.scorer.score().
    sector          : Stock's sector string (e.g. "technology"). Required for
                      macro impact lookup; ignored if macro is None.
    sentiment       : Result from src.sentiment.scorer.score(). Optional.
    macro           : Result from src.macro.tagger.tag(). Optional.
    missing_fields  : Fields that were absent from Yahoo Finance (from
                      StockData.missing_fields). Used in confidence calculation.
    """
    missing_fields = missing_fields or []

    log_input(_MODULE, {
        "ticker": ticker,
        "score": fundamental.total,
        "valuation_status": fundamental.valuation.status,
        "has_sentiment": sentiment is not None,
        "has_macro": macro is not None,
        "sector": sector,
        "missing_field_count": len(missing_fields),
    })

    trace: list[str] = []
    contributing: list[Factor] = []
    rejected: list[Factor] = []
    uncertainty: list[str] = []
    gates: list[Gate] = []

    score = fundamental.total
    val_status = fundamental.valuation.status

    trace.append(
        f"Core score: {score:.1f}/100 "
        f"(quality {fundamental.quality.total:.1f}×40% "
        f"+ growth {fundamental.growth.total:.1f}×25% "
        f"+ dividend {fundamental.dividend.total:.1f}×20% "
        f"+ valuation {fundamental.valuation.total:.1f}×15%)"
    )

    # ── Gate 1: Fundamental score threshold ───────────────────────────────────
    g1_passed = score > SCORE_BUY
    gates.append(Gate(
        name="fundamental_score",
        passed=g1_passed,
        observed=f"{score:.1f}",
        required=f"> {SCORE_BUY}",
        note=f"Score {score:.1f} {'exceeds' if g1_passed else 'does not exceed'} BUY threshold of {SCORE_BUY}",
    ))
    if g1_passed:
        contributing.append(Factor(
            "Fundamental score",
            "supporting",
            f"{score:.1f}/100 exceeds BUY threshold ({SCORE_BUY})",
        ))
    else:
        rejected.append(Factor(
            "Fundamental score",
            "opposing",
            f"{score:.1f}/100 does not reach BUY threshold ({SCORE_BUY})",
        ))
    trace.append(f"Gate 1 (score > {SCORE_BUY}): {'PASS' if g1_passed else 'FAIL'}")

    # ── Gate 2: Valuation status ───────────────────────────────────────────────
    g2_passed = val_status == UNDERVALUED
    gates.append(Gate(
        name="valuation_status",
        passed=g2_passed,
        observed=val_status,
        required=UNDERVALUED,
        note=(
            f"Valuation is '{val_status}'"
            + (" — no P/E or yield history to determine status" if val_status == UNKNOWN else "")
        ),
    ))
    if g2_passed:
        contributing.append(Factor(
            "Valuation",
            "supporting",
            f"Status: {val_status} — stock is trading below its historical norm",
        ))
    else:
        rejected.append(Factor(
            "Valuation",
            "opposing",
            f"Status: {val_status} — 'undervalued' required for BUY",
        ))
    if val_status == UNKNOWN:
        uncertainty.append(
            "Valuation: status unknown — no P/E or dividend yield history available"
        )
    trace.append(f"Gate 2 (valuation = undervalued): {'PASS' if g2_passed else 'FAIL'} ({val_status})")

    # ── Base decision from hard gates ──────────────────────────────────────────
    if g1_passed and g2_passed:
        _base = "BUY_CANDIDATE"
    elif score >= SCORE_WATCH_MIN:
        _base = "WATCH"
    else:
        _base = "AVOID"
    trace.append(f"Hard gates produce base: {_base}")

    # ── Gate 3: Sentiment (soft gate — can prevent BUY, not force it) ─────────
    if sentiment is not None:
        sent_negative = sentiment.status == "negative"
        sent_improving = sentiment.trend > 0
        g3_passed = sent_negative and sent_improving

        gates.append(Gate(
            name="sentiment",
            passed=g3_passed,
            observed=f"status={sentiment.status}, trend={sentiment.trend:+.4f}",
            required="status=negative AND trend > 0",
            note=(
                "Contrarian signal: market pessimism is present but receding — preferred entry timing"
                if g3_passed
                else (
                    f"Sentiment is {sentiment.status} (trend {sentiment.trend:+.4f}/day) "
                    f"— not negative-but-improving"
                )
            ),
        ))

        if g3_passed:
            contributing.append(Factor(
                "Sentiment: negative but improving",
                "supporting",
                f"Score {sentiment.score:+.3f}, trend {sentiment.trend:+.4f}/day — "
                f"contrarian opportunity (market pessimism receding)",
            ))
        elif sentiment.status == "positive" and sentiment.score > 0.30:
            rejected.append(Factor(
                "Sentiment: positive",
                "opposing",
                f"Score {sentiment.score:+.3f} — positive sentiment may indicate "
                f"the upside is already priced in",
            ))
        else:
            rejected.append(Factor(
                "Sentiment gate",
                "opposing",
                f"status={sentiment.status}, trend={sentiment.trend:+.4f} "
                f"— not negative-but-improving",
            ))

        if sentiment.confidence < _SENTIMENT_LOW_CONFIDENCE:
            uncertainty.append(
                f"Sentiment: low lexicon coverage (confidence {sentiment.confidence:.2f}) "
                f"— few headlines matched the financial lexicon"
            )

        trace.append(
            f"Gate 3 (sentiment negative+improving): {'PASS' if g3_passed else 'FAIL'} "
            f"(status={sentiment.status}, trend={sentiment.trend:+.4f})"
        )
    else:
        g3_passed = None
        gates.append(Gate(
            name="sentiment",
            passed=None,
            observed="no data",
            required="status=negative AND trend > 0",
            note="No sentiment data provided — gate not evaluated",
        ))
        uncertainty.append("Sentiment: no headline data — gate cannot be evaluated")
        trace.append("Gate 3 (sentiment): NOT EVALUATED — no data provided")

    # ── Resolve decision after soft gate ──────────────────────────────────────
    if _base == "BUY_CANDIDATE":
        if g3_passed is True:
            decision = "BUY"
            trace.append("BUY: all three gates passed")
        else:
            decision = "WATCH"
            reason = (
                "sentiment gate failed (not negative-but-improving)"
                if g3_passed is False
                else "sentiment data absent — cannot confirm contrarian timing"
            )
            trace.append(f"BUY→WATCH: {reason}")
    else:
        decision = _base

    # ── Macro context — can only downgrade, never upgrade ─────────────────────
    macro_category_val: Optional[str] = None
    macro_sector_direction: Optional[str] = None
    macro_sector_strength: Optional[float] = None
    macro_confidence_val: Optional[float] = None

    if macro is not None:
        macro_category_val = macro.category
        macro_confidence_val = macro.confidence

        if macro.low_confidence:
            uncertainty.append(
                f"Macro: low confidence classification (confidence {macro.confidence:.2f}) "
                f"— '{macro.category}' assignment is uncertain"
            )

        if sector is not None:
            sector_tag = next(
                (s for s in macro.affected_sectors if s.sector == sector), None
            )
            if sector_tag:
                macro_sector_direction = sector_tag.direction
                macro_sector_strength = sector_tag.strength

                if (
                    sector_tag.direction == "bearish"
                    and sector_tag.strength >= _MACRO_DOWNGRADE_THRESHOLD
                ):
                    if decision == "BUY":
                        decision = "WATCH"
                        rejected.append(Factor(
                            f"Macro headwind: {macro.category}",
                            "opposing",
                            f"Sector '{sector}': bearish, strength {sector_tag.strength:.2f} "
                            f"(≥ {_MACRO_DOWNGRADE_THRESHOLD}) — BUY downgraded to WATCH. "
                            f"Reason: {sector_tag.reasoning}",
                        ))
                        trace.append(
                            f"BUY→WATCH: macro headwind — {macro.category} "
                            f"is bearish for '{sector}' (strength {sector_tag.strength:.2f})"
                        )
                    else:
                        rejected.append(Factor(
                            f"Macro headwind: {macro.category}",
                            "opposing",
                            f"Sector '{sector}': bearish, strength {sector_tag.strength:.2f} "
                            f"— {sector_tag.reasoning}",
                        ))
                        uncertainty.append(
                            f"Macro: '{macro.category}' is bearish for '{sector}' "
                            f"(strength {sector_tag.strength:.2f})"
                        )
                        trace.append(
                            f"Macro headwind noted: {macro.category} → {sector} "
                            f"bearish {sector_tag.strength:.2f} (decision already {decision})"
                        )

                elif sector_tag.direction == "bullish":
                    contributing.append(Factor(
                        f"Macro tailwind: {macro.category}",
                        "supporting",
                        f"Sector '{sector}': bullish, strength {sector_tag.strength:.2f} "
                        f"— {sector_tag.reasoning}",
                    ))
                    trace.append(
                        f"Macro tailwind: {macro.category} → {sector} "
                        f"bullish {sector_tag.strength:.2f}"
                    )

                elif sector_tag.direction == "mixed":
                    uncertainty.append(
                        f"Macro: '{macro.category}' has mixed impact for '{sector}' "
                        f"(strength {sector_tag.strength:.2f}) — direction uncertain"
                    )
                    trace.append(
                        f"Macro mixed: {macro.category} → {sector} "
                        f"mixed {sector_tag.strength:.2f}"
                    )
            else:
                trace.append(
                    f"Macro: sector '{sector}' not in '{macro.category}' impact table — no adjustment"
                )
        else:
            uncertainty.append(
                "Macro: sector not specified — directional impact cannot be determined"
            )
            trace.append("Macro: sector not provided — impact lookup skipped")
    else:
        uncertainty.append("Macro: no macro context provided")
        trace.append("Macro: not provided")

    # ── Confidence ────────────────────────────────────────────────────────────
    conf = _compute_confidence(
        score=score,
        val_status=val_status,
        missing_fields=missing_fields,
        sentiment=sentiment,
        macro_sector_direction=macro_sector_direction,
        macro_sector_strength=macro_sector_strength,
        macro_confidence=macro_confidence_val,
        decision=decision,
    )
    trace.append(
        f"Confidence: {conf.total:.2f} "
        f"(data_quality={conf.data_quality:.2f}×30% "
        f"+ val_certainty={conf.valuation_certainty:.2f}×25% "
        f"+ signal_agreement={conf.signal_agreement:.2f}×30% "
        f"+ soft_quality={conf.soft_signal_quality:.2f}×15%)"
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    flag_summary = (
        ", ".join(uncertainty[:2]) + (f" (+{len(uncertainty)-2} more)" if len(uncertainty) > 2 else "")
        if uncertainty else "none"
    )
    notes = [
        (
            f"{decision}: score {score:.1f}/100 | valuation {val_status} | "
            f"confidence {conf.total:.2f}"
        ),
        (
            f"Components: quality {fundamental.quality.total:.1f}×40% + "
            f"growth {fundamental.growth.total:.1f}×25% + "
            f"dividend {fundamental.dividend.total:.1f}×20% + "
            f"valuation {fundamental.valuation.total:.1f}×15%"
        ),
        f"Uncertainty: {len(uncertainty)} flag(s) — {flag_summary}",
    ]

    result = DecisionResult(
        ticker=ticker,
        decision=decision,
        score=score,
        quality_score=fundamental.quality.total,
        growth_score=fundamental.growth.total,
        dividend_score=fundamental.dividend.total,
        valuation_score=fundamental.valuation.total,
        valuation_status=val_status,
        confidence=conf.total,
        confidence_breakdown=conf,
        gates=gates,
        contributing_factors=contributing,
        rejected_factors=rejected,
        uncertainty_flags=uncertainty,
        sentiment_score=sentiment.score if sentiment else None,
        sentiment_status=sentiment.status if sentiment else None,
        sentiment_trend=sentiment.trend if sentiment else None,
        sentiment_confidence=sentiment.confidence if sentiment else None,
        macro_category=macro_category_val,
        macro_sector_direction=macro_sector_direction,
        macro_sector_strength=macro_sector_strength,
        macro_confidence=macro_confidence_val,
        reasoning_trace=trace,
        notes=notes,
    )

    log_result(_MODULE, {
        "ticker": ticker,
        "decision": decision,
        "score": score,
        "confidence": conf.total,
        "gates_passed": sum(1 for g in gates if g.passed is True),
        "gates_failed": sum(1 for g in gates if g.passed is False),
        "gates_unknown": sum(1 for g in gates if g.passed is None),
        "contributing_count": len(contributing),
        "rejected_count": len(rejected),
        "uncertainty_count": len(uncertainty),
    })

    return result


# ── Confidence computation ─────────────────────────────────────────────────────

def _compute_confidence(
    score: float,
    val_status: str,
    missing_fields: list[str],
    sentiment: Optional[SentimentResult],
    macro_sector_direction: Optional[str],
    macro_sector_strength: Optional[float],
    macro_confidence: Optional[float],
    decision: str,
) -> ConfidenceBreakdown:
    """
    Four-component confidence model.

    Component 1 — Data quality (weight 30%)
      Each missing fundamental field reduces confidence by _MISSING_FIELD_PENALTY.
      Rationale: scoring on None fields produces 0s that pull the score down but
      are not informative; more missing fields means less certainty.

    Component 2 — Valuation certainty (weight 25%)
      'undervalued' → 1.0 (clear, positive signal)
      'fair'/'overvalued' → 0.5 (status is known, but not the ideal entry signal)
      'unknown' → 0.0 (cannot determine status)

    Component 3 — Signal agreement (weight 30%)
      Do soft signals (sentiment + macro) agree with the decision direction?
      Agreement raises confidence; conflict lowers it.

    Component 4 — Soft signal quality (weight 15%)
      Internal confidence of the sentiment and macro modules themselves.

    KNOWN LIMITATION: this is a proxy metric, not a calibrated probability.
    A confidence of 0.8 does NOT mean an 80% hit rate.
    """

    # ── Component 1: Data quality ─────────────────────────────────────────────
    data_quality = round(
        max(0.0, 1.0 - len(missing_fields) * _MISSING_FIELD_PENALTY), 4
    )

    # ── Component 2: Valuation certainty ─────────────────────────────────────
    if val_status == UNDERVALUED:
        valuation_certainty = 1.0
    elif val_status == UNKNOWN:
        valuation_certainty = 0.0
    else:  # fair or overvalued — status is known, signal is clear
        valuation_certainty = 0.5

    # ── Component 3: Signal agreement ────────────────────────────────────────
    sent_agree = _sentiment_agreement(sentiment, decision)
    macro_agree = _macro_agreement(macro_sector_direction, decision)
    signal_agreement = round((sent_agree + macro_agree) / 2, 4)

    # ── Component 4: Soft signal quality ─────────────────────────────────────
    sent_conf = sentiment.confidence if sentiment is not None else 0.50
    mac_conf = macro_confidence if macro_confidence is not None else 0.50
    soft_signal_quality = round((sent_conf + mac_conf) / 2, 4)

    # ── Weighted total ────────────────────────────────────────────────────────
    raw = (
        data_quality       * 0.30
        + valuation_certainty * 0.25
        + signal_agreement    * 0.30
        + soft_signal_quality * 0.15
    )
    total = round(max(0.0, min(1.0, raw)), 4)

    return ConfidenceBreakdown(
        data_quality=data_quality,
        valuation_certainty=valuation_certainty,
        signal_agreement=signal_agreement,
        soft_signal_quality=soft_signal_quality,
        total=total,
    )


def _sentiment_agreement(sentiment: Optional[SentimentResult], decision: str) -> float:
    """
    How well does the sentiment signal agree with the decision direction?
    Returns 0.0 (full disagreement) to 1.0 (full agreement); 0.5 = unknown/neutral.

    BUY  : negative-but-improving sentiment is the ideal contrarian signal → 1.0
    AVOID: positive or worsening sentiment corroborates → high agreement
    WATCH: no strong directional expectation → 0.5
    """
    if sentiment is None:
        return 0.50

    if decision == "BUY":
        if sentiment.status == "negative" and sentiment.trend > 0:
            return 1.0
        if sentiment.status == "neutral":
            return 0.50
        return 0.0   # positive sentiment, or negative but worsening

    if decision == "AVOID":
        if sentiment.status == "positive":
            return 0.80   # confirms overpricing / momentum reversal risk
        if sentiment.status == "neutral":
            return 0.50
        return 0.20   # negative sentiment disagrees with AVOID (contrarian opportunity missed)

    return 0.50   # WATCH — no clear directional expectation


def _macro_agreement(direction: Optional[str], decision: str) -> float:
    """
    How well does the macro sector impact agree with the decision?
    Returns 0.0 to 1.0; 0.5 = no sector data.
    """
    if direction is None:
        return 0.50
    if decision == "BUY":
        return 1.0 if direction == "bullish" else (0.50 if direction == "mixed" else 0.0)
    if decision == "AVOID":
        return 1.0 if direction == "bearish" else (0.50 if direction == "mixed" else 0.0)
    return 0.50   # WATCH
