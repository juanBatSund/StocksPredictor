from dataclasses import dataclass

from config.markets import MarketProfile
from src.data.models import Fundamentals


@dataclass
class DividendScore:
    total: float        # 0–100
    yield_score: float  # 0–100
    payout: float       # 0–100
    streak: float       # 0–100
    notes: list[str]


def score(f: Fundamentals, market: MarketProfile) -> DividendScore:
    yield_s, yield_note = _score_yield(f.dividend_yield, market)
    payout_s, payout_note = _score_payout(f.payout_ratio)
    streak_s, streak_note = _score_streak(f.dividend_growth_streak_years)
    total = round((yield_s + payout_s + streak_s) / 3, 2)
    return DividendScore(
        total=total,
        yield_score=round(yield_s, 2),
        payout=round(payout_s, 2),
        streak=round(streak_s, 2),
        notes=[yield_note, payout_note, streak_note],
    )


# ── metric scorers ────────────────────────────────────────────────────────────

def _score_yield(y: float | None, market: MarketProfile) -> tuple[float, str]:
    """
    Sweet spot and trap ceiling come from the market profile.
    Peaks at market.dividend_yield_peak (scores 100).
    Above market.dividend_yield_trap → likely dividend trap (scores 0).
    """
    if y is None:
        return 0.0, "Dividend yield missing → 0"
    if y <= 0:
        return 0.0, "No dividend paid → 0"

    ymin  = market.dividend_yield_min
    ypeak = market.dividend_yield_peak
    ymax  = market.dividend_yield_max
    ytrap = market.dividend_yield_trap

    if y < ymin:
        s = _lerp(y, 0, ymin, 0, 75)
        return s, f"Yield {y:.2%} below {ymin:.0%} minimum ({market.code}) → {s:.1f}"
    if y <= ypeak:
        s = _lerp(y, ymin, ypeak, 75, 100)
        return s, f"Yield {y:.2%} in sweet spot (rising, {market.code}) → {s:.1f}"
    if y <= ymax:
        s = _lerp(y, ypeak, ymax, 100, 75)
        return s, f"Yield {y:.2%} in sweet spot (high end, {market.code}) → {s:.1f}"
    if y <= ytrap:
        s = _lerp(y, ymax, ytrap, 75, 25)
        return s, f"Yield {y:.2%} above {ymax:.0%} max ({market.code}) — caution → {s:.1f}"
    return 0.0, f"Yield {y:.2%} above {ytrap:.0%} trap ceiling ({market.code}) → 0"


def _score_payout(payout: float | None) -> tuple[float, str]:
    """
    Threshold: payout < 60% (system.md). This is universal across markets.
    """
    if payout is None:
        return 0.0, "Payout ratio missing → 0"
    if payout <= 0:
        return 0.0, "Payout ratio zero → 0"
    if payout <= 0.30:
        return 100.0, f"Payout {payout:.1%} very conservative → 100"
    if payout <= 0.60:
        s = _lerp(payout, 0.30, 0.60, 100, 50)
        return s, f"Payout {payout:.1%} acceptable (below 60% threshold) → {s:.1f}"
    if payout <= 1.00:
        s = _lerp(payout, 0.60, 1.00, 50, 0)
        return s, f"Payout {payout:.1%} above 60% threshold → {s:.1f}"
    return 0.0, f"Payout {payout:.1%} >100% — unsustainable → 0"


def _score_streak(streak: int | None) -> tuple[float, str]:
    """
    Stable or growing dividend (system.md).
    Streak is computed from Ticker.dividends history — market-agnostic.
    """
    if streak is None or streak <= 0:
        return 0.0, "Dividend streak unknown or none → 0"
    if streak < 5:
        return 25.0, f"{streak}Y streak — short track record → 25"
    if streak < 10:
        return 50.0, f"{streak}Y streak — established → 50"
    if streak < 25:
        return 75.0, f"{streak}Y streak — strong history → 75"
    return 100.0, f"{streak}Y streak — Dividend Aristocrat → 100"


def _lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
