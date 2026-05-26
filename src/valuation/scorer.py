from dataclasses import dataclass
from typing import Optional

from config.markets import MarketProfile
from src.data.models import Fundamentals

UNDERVALUED = "undervalued"
FAIR = "fair"
OVERVALUED = "overvalued"
UNKNOWN = "unknown"

# Within-valuation component weights
_PE_WEIGHT = 0.60
_YIELD_WEIGHT = 0.40

# Score thresholds for status
_UNDERVALUED_THRESHOLD = 80.0
_OVERVALUED_THRESHOLD = 40.0


@dataclass
class ValuationScore:
    total: float                            # 0–100, weighted composite
    pe_score: float                         # 0–100
    dividend_score: float                   # 0–100
    status: str                             # undervalued | fair | overvalued | unknown
    pe_deviation_pct: Optional[float]       # (pe − avg) / avg × 100; negative = cheaper than avg
    dividend_deviation_pct: Optional[float] # (yield − avg) / avg × 100; positive = higher yield = cheaper
    notes: list[str]                        # always 2 entries: [pe_note, yield_note]


def score(f: Fundamentals, market: MarketProfile) -> ValuationScore:
    # P/E: fall back to market typical when stock history is absent
    pe_avg = f.pe_5y_avg if f.pe_5y_avg is not None else market.typical_pe
    pe_fallback = f.pe_5y_avg is None
    pe_s, pe_dev, pe_note = _score_pe(f.pe_ratio, pe_avg, pe_fallback)
    pe_real = f.pe_ratio is not None and pe_avg > 0

    # Dividend yield: only compare against the stock's own history — no market proxy
    div_s, div_dev, div_note = _score_yield(f.dividend_yield, f.dividend_yield_5y_avg)
    div_real = (
        f.dividend_yield is not None
        and f.dividend_yield_5y_avg is not None
        and f.dividend_yield_5y_avg > 0
    )

    # Use only the signals that are real; neutral 50 when both are absent
    if pe_real and div_real:
        total = pe_s * _PE_WEIGHT + div_s * _YIELD_WEIGHT
    elif pe_real:
        total = pe_s
    elif div_real:
        total = div_s
    else:
        total = 50.0

    if not pe_real and not div_real:
        status = UNKNOWN
    elif total >= _UNDERVALUED_THRESHOLD:
        status = UNDERVALUED
    elif total < _OVERVALUED_THRESHOLD:
        status = OVERVALUED
    else:
        status = FAIR

    return ValuationScore(
        total=round(total, 2),
        pe_score=round(pe_s, 2),
        dividend_score=round(div_s, 2),
        status=status,
        pe_deviation_pct=pe_dev,
        dividend_deviation_pct=div_dev,
        notes=[pe_note, div_note],
    )


# ── metric scorers ─────────────────────────────────────────────────────────────

def _score_pe(
    pe: float | None,
    avg: float,
    using_fallback: bool,
) -> tuple[float, Optional[float], str]:
    """
    Returns (score 0-100, deviation_pct or None, note).
    Deviation = (pe − avg) / avg × 100; negative means stock is cheaper than average.
    Bands: ratio ≤0.70 → 100, ≤0.85 → 80-100, ≤1.00 → 60-80,
           ≤1.15 → 40-60, ≤1.30 → 20-40, >1.30 → 0.
    """
    avg_label = f"market avg {avg:.1f}" if using_fallback else f"5Y avg {avg:.1f}"

    if pe is None:
        return 50.0, None, "P/E missing — neutral 50"
    if avg <= 0:
        return 50.0, None, f"{avg_label} not meaningful — neutral 50"

    ratio = pe / avg
    dev = round((pe - avg) / avg * 100, 1)

    if ratio <= 0.70:
        return 100.0, dev, f"P/E {pe:.1f} vs {avg_label} ({dev:+.1f}%) → 100"
    if ratio <= 0.85:
        s = _lerp(ratio, 0.70, 0.85, 100, 80)
        return s, dev, f"P/E {pe:.1f} vs {avg_label} ({dev:+.1f}%) → {s:.1f}"
    if ratio <= 1.00:
        s = _lerp(ratio, 0.85, 1.00, 80, 60)
        return s, dev, f"P/E {pe:.1f} vs {avg_label} ({dev:+.1f}%) → {s:.1f}"
    if ratio <= 1.15:
        s = _lerp(ratio, 1.00, 1.15, 60, 40)
        return s, dev, f"P/E {pe:.1f} vs {avg_label} ({dev:+.1f}%) → {s:.1f}"
    if ratio <= 1.30:
        s = _lerp(ratio, 1.15, 1.30, 40, 20)
        return s, dev, f"P/E {pe:.1f} vs {avg_label} ({dev:+.1f}%) → {s:.1f}"
    return 0.0, dev, f"P/E {pe:.1f} vs {avg_label} ({dev:+.1f}%) → 0"


def _score_yield(
    yield_: float | None,
    avg: float | None,
) -> tuple[float, Optional[float], str]:
    """
    Returns (score 0-100, deviation_pct or None, note).
    Higher yield vs historical avg signals lower price → undervalued.
    Deviation = (yield − avg) / avg × 100; positive means yield is above historical (stock is cheaper).
    Bands: ratio ≥1.30 → 100, ≥1.15 → 80-100, ≥1.00 → 60-80,
           ≥0.85 → 40-60, ≥0.70 → 20-40, <0.70 → 0.
    """
    if yield_ is None:
        return 50.0, None, "Dividend yield missing — neutral 50"
    if avg is None or avg <= 0:
        return 50.0, None, "No yield history — neutral 50"

    ratio = yield_ / avg
    dev = round((yield_ - avg) / avg * 100, 1)

    if ratio >= 1.30:
        return 100.0, dev, f"Yield {yield_:.2%} vs 5Y avg {avg:.2%} ({dev:+.1f}%) → 100"
    if ratio >= 1.15:
        s = _lerp(ratio, 1.15, 1.30, 80, 100)
        return s, dev, f"Yield {yield_:.2%} vs 5Y avg {avg:.2%} ({dev:+.1f}%) → {s:.1f}"
    if ratio >= 1.00:
        s = _lerp(ratio, 1.00, 1.15, 60, 80)
        return s, dev, f"Yield {yield_:.2%} vs 5Y avg {avg:.2%} ({dev:+.1f}%) → {s:.1f}"
    if ratio >= 0.85:
        s = _lerp(ratio, 0.85, 1.00, 40, 60)
        return s, dev, f"Yield {yield_:.2%} vs 5Y avg {avg:.2%} ({dev:+.1f}%) → {s:.1f}"
    if ratio >= 0.70:
        s = _lerp(ratio, 0.70, 0.85, 20, 40)
        return s, dev, f"Yield {yield_:.2%} vs 5Y avg {avg:.2%} ({dev:+.1f}%) → {s:.1f}"
    return 0.0, dev, f"Yield {yield_:.2%} vs 5Y avg {avg:.2%} ({dev:+.1f}%) → 0"


def _lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
