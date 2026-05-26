import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Optional

from src.logging.logger import log_input, log_result, log_warning
from src.sentiment.lexicon import INTENSITY_MODIFIERS, NEGATION_WORDS, PHRASES, TERMS

_MODULE = "sentiment.scorer"

# Status thresholds — explicit, not opaque
_POSITIVE_THRESHOLD = 0.10
_NEGATIVE_THRESHOLD = -0.10

# Context window size for negation and intensity lookback (in tokens)
_NEGATION_WINDOW = 3
_INTENSITY_WINDOW = 3

# Coverage below this threshold indicates the module had very little to say
_LOW_COVERAGE_THRESHOLD = 0.15


@dataclass
class MatchedTerm:
    term: str
    base_weight: float        # weight from lexicon, before modifiers
    applied_weight: float     # after negation and intensity
    negated: bool
    intensity: Optional[float]  # multiplier applied, or None if none found


@dataclass
class HeadlineScore:
    headline: str
    score: float              # clamped to [-1.0, +1.0]
    confidence: float         # 0–1; lexicon coverage of tokens
    low_coverage: bool        # True when confidence < _LOW_COVERAGE_THRESHOLD
    matched: list[MatchedTerm]
    note: str


@dataclass
class SentimentResult:
    ticker: str
    score: float                          # mean of headline scores, -1 to +1
    confidence: float                     # mean headline confidence, 0 to 1
    status: str                           # "positive" | "negative" | "neutral"
    trend: float                          # OLS slope of daily avg scores; + = improving
    headline_scores: list[HeadlineScore]  # one per input headline, in input order
    daily_scores: list[tuple[str, float]] # (ISO date, avg score) — trend inputs
    notes: list[str]                      # [score_note, confidence_note, trend_note]


# ── Public API ─────────────────────────────────────────────────────────────────

def score_headline(headline: str) -> HeadlineScore:
    """
    Score a single financial news headline.

    Pipeline:
      1. Tokenise: lowercase, strip punctuation, split on whitespace.
      2. Match phrases (longest first, no overlap).
      3. Match individual words at remaining token positions.
      4. Apply negation (3-token lookback) and intensity (3-token lookback).
      5. Sum applied weights, clamp to [-1, +1].
      6. Compute coverage-based confidence.
    """
    tokens = _tokenize(headline)

    if not tokens:
        return HeadlineScore(
            headline=headline,
            score=0.0,
            confidence=0.0,
            low_coverage=True,
            matched=[],
            note="empty headline — neutral 0.0",
        )

    phrase_hits, consumed = _match_phrases(tokens)
    word_hits = _match_words(tokens, consumed)

    all_hits = phrase_hits + word_hits  # (position, term, base_weight)

    if not all_hits:
        return HeadlineScore(
            headline=headline,
            score=0.0,
            confidence=0.0,
            low_coverage=True,
            matched=[],
            note=f"no lexicon matches in {len(tokens)} tokens — neutral 0.0",
        )

    matched_terms: list[MatchedTerm] = []
    raw_total = 0.0
    for pos, term, base_weight in sorted(all_hits, key=lambda x: x[0]):
        applied, negated, intensity = _apply_context(pos, base_weight, tokens)
        matched_terms.append(MatchedTerm(
            term=term,
            base_weight=round(base_weight, 4),
            applied_weight=round(applied, 4),
            negated=negated,
            intensity=intensity,
        ))
        raw_total += applied

    final_score = round(max(-1.0, min(1.0, raw_total)), 4)

    # Confidence: tokens matched as a fraction of total tokens
    # 25 %+ coverage → confidence 1.0 (reasonable for a 10-word financial headline)
    matched_token_count = sum(len(m.term.split()) for m in matched_terms)
    confidence = round(min(1.0, (matched_token_count / len(tokens)) * 4.0), 4)
    low_coverage = confidence < _LOW_COVERAGE_THRESHOLD

    direction = "positive" if final_score > 0 else ("negative" if final_score < 0 else "neutral")
    note = (
        f"{len(matched_terms)} match(es): score {final_score:+.3f} ({direction}), "
        f"confidence {confidence:.2f}"
        + (" [low coverage]" if low_coverage else "")
    )

    return HeadlineScore(
        headline=headline,
        score=final_score,
        confidence=confidence,
        low_coverage=low_coverage,
        matched=matched_terms,
        note=note,
    )


def score(
    ticker: str,
    dated_headlines: list[tuple[date, str]],
) -> SentimentResult:
    """
    Score a collection of dated headlines for a ticker.

    Input:  list of (publication_date, headline_text) pairs.
    Output: aggregate score, confidence, trend, and full breakdown.

    Aggregation:
      - Score: unweighted mean of individual headline scores.
      - Confidence: unweighted mean of individual headline confidences.
      - Trend: OLS slope of daily-average scores (units: score/day).
        Requires ≥ 2 distinct dates; returns 0.0 otherwise.
    """
    log_input(_MODULE, {"ticker": ticker, "headline_count": len(dated_headlines)})

    if not dated_headlines:
        result = _empty_result(ticker)
        log_warning(_MODULE, "no_headlines", {"ticker": ticker})
        return result

    headline_scores = [score_headline(h) for _, h in dated_headlines]

    agg_score = round(sum(h.score for h in headline_scores) / len(headline_scores), 4)
    agg_confidence = round(
        sum(h.confidence for h in headline_scores) / len(headline_scores), 4
    )

    if agg_score > _POSITIVE_THRESHOLD:
        status = "positive"
    elif agg_score < _NEGATIVE_THRESHOLD:
        status = "negative"
    else:
        status = "neutral"

    daily = _daily_averages(dated_headlines, headline_scores)
    daily_str = [(d.isoformat(), round(s, 4)) for d, s in daily]

    if len(daily) >= 2:
        xs = [float(i) for i in range(len(daily))]
        ys = [s for _, s in daily]
        trend_slope = round(_ols_slope(xs, ys), 6)
        direction = "improving" if trend_slope > 0 else ("worsening" if trend_slope < 0 else "flat")
        trend_note = (
            f"OLS slope {trend_slope:+.4f}/day over {len(daily)} date(s) — {direction}. "
            f"N={len(daily)} — interpret cautiously below N=10"
        )
    else:
        trend_slope = 0.0
        trend_note = f"Not computed — only {len(daily)} date(s); need ≥ 2"

    low_coverage_count = sum(1 for h in headline_scores if h.low_coverage)
    score_note = (
        f"Aggregate score {agg_score:+.3f} ({status}) "
        f"from {len(headline_scores)} headline(s)"
    )
    conf_note = (
        f"Mean confidence {agg_confidence:.2f} "
        f"({low_coverage_count}/{len(headline_scores)} headline(s) flagged low-coverage). "
        f"Confidence = lexicon coverage density, not predictive accuracy"
    )

    result = SentimentResult(
        ticker=ticker,
        score=agg_score,
        confidence=agg_confidence,
        status=status,
        trend=trend_slope,
        headline_scores=headline_scores,
        daily_scores=daily_str,
        notes=[score_note, conf_note, trend_note],
    )

    log_result(_MODULE, {
        "ticker": ticker,
        "score": result.score,
        "confidence": result.confidence,
        "status": result.status,
        "trend": result.trend,
        "headline_count": len(headline_scores),
        "date_count": len(daily),
        "low_coverage_headlines": low_coverage_count,
    })

    return result


# ── Internal helpers ───────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Lowercase, strip all punctuation (including hyphens), split on whitespace."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return cleaned.split()


def _match_phrases(
    tokens: list[str],
) -> tuple[list[tuple[int, str, float]], set[int]]:
    """
    Scan for phrase matches, longest first, non-overlapping, leftmost wins.
    Returns ([(position, phrase, weight), ...], consumed_positions).
    """
    consumed: set[int] = set()
    matches: list[tuple[int, str, float]] = []

    # Sort by descending phrase length so "beats estimates" beats "beats"
    for phrase, weight in sorted(
        PHRASES.items(), key=lambda kv: len(kv[0].split()), reverse=True
    ):
        phrase_tokens = phrase.split()
        n = len(phrase_tokens)
        for i in range(len(tokens) - n + 1):
            positions = set(range(i, i + n))
            if positions & consumed:
                continue
            if tokens[i : i + n] == phrase_tokens:
                consumed |= positions
                matches.append((i, phrase, weight))
                break  # leftmost match only; each phrase matches at most once

    return matches, consumed


def _match_words(
    tokens: list[str],
    consumed: set[int],
) -> list[tuple[int, str, float]]:
    """Match single TERMS at positions not already consumed by a phrase."""
    return [
        (i, token, TERMS[token])
        for i, token in enumerate(tokens)
        if i not in consumed and token in TERMS
    ]


def _apply_context(
    position: int,
    base_weight: float,
    tokens: list[str],
) -> tuple[float, bool, Optional[float]]:
    """
    Look back up to max(NEGATION_WINDOW, INTENSITY_WINDOW) tokens.
    Returns (applied_weight, is_negated, intensity_multiplier or None).

    Known limitation: a 3-token window misses negation in long clauses
    such as "The company is not in any danger of ..." — "not" is too far
    from the sentiment term for the window to capture it.
    """
    start = max(0, position - max(_NEGATION_WINDOW, _INTENSITY_WINDOW))
    window = tokens[start:position]

    negated = any(t in NEGATION_WORDS for t in window)

    intensity: Optional[float] = None
    for t in reversed(window):
        if t in INTENSITY_MODIFIERS:
            intensity = INTENSITY_MODIFIERS[t]
            break

    applied = base_weight
    if intensity is not None:
        applied *= intensity
    if negated:
        applied = -applied

    return applied, negated, intensity


def _daily_averages(
    dated_headlines: list[tuple[date, str]],
    scores: list[HeadlineScore],
) -> list[tuple[date, float]]:
    """Average scores for each calendar day, sorted ascending."""
    daily: dict[date, list[float]] = defaultdict(list)
    for (d, _), hs in zip(dated_headlines, scores):
        daily[d].append(hs.score)
    return [(d, sum(vs) / len(vs)) for d, vs in sorted(daily.items())]


def _ols_slope(xs: list[float], ys: list[float]) -> float:
    """
    Ordinary least-squares slope. Requires len(xs) == len(ys) >= 2.
    Returns 0.0 when denominator is zero (all x values identical).

    Formula: slope = (n·Σxy − Σx·Σy) / (n·Σx² − (Σx)²)
    """
    n = len(xs)
    sx = sum(xs)
    sy = sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sxx = sum(x * x for x in xs)
    denom = n * sxx - sx * sx
    if denom == 0.0:
        return 0.0
    return (n * sxy - sx * sy) / denom


def _empty_result(ticker: str) -> SentimentResult:
    return SentimentResult(
        ticker=ticker,
        score=0.0,
        confidence=0.0,
        status="neutral",
        trend=0.0,
        headline_scores=[],
        daily_scores=[],
        notes=[
            "No headlines provided — neutral 0.0",
            "Confidence: 0.0 — no data",
            "Trend: not computed — no data",
        ],
    )
