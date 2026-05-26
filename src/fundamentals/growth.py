from dataclasses import dataclass

from src.data.models import Fundamentals


@dataclass
class GrowthScore:
    total: float    # 0–100
    revenue: float  # 0–100
    earnings: float # 0–100
    notes: list[str]


def score(f: Fundamentals) -> GrowthScore:
    rev_s, rev_note = _score_growth(f.revenue_growth_5y, "Revenue")
    earn_s, earn_note = _score_growth(f.earnings_growth_5y, "Earnings")
    total = round((rev_s + earn_s) / 2, 2)
    return GrowthScore(
        total=total,
        revenue=round(rev_s, 2),
        earnings=round(earn_s, 2),
        notes=[rev_note, earn_note],
    )


# ── metric scorer ─────────────────────────────────────────────────────────────

def _score_growth(growth: float | None, label: str) -> tuple[float, str]:
    """
    Threshold: positive 5Y growth (system.md).
    Gradient: 0→5% maps 0→50, 5%→15% maps 50→75, >15% maps 75→100.
    """
    if growth is None:
        return 0.0, f"{label} 5Y growth missing → 0"
    if growth <= 0:
        return 0.0, f"{label} 5Y growth {growth:.1%} ≤ 0 → 0"
    if growth <= 0.05:
        s = _lerp(growth, 0, 0.05, 0, 50)
        return s, f"{label} 5Y growth {growth:.1%} low positive → {s:.1f}"
    if growth <= 0.15:
        s = _lerp(growth, 0.05, 0.15, 50, 75)
        return s, f"{label} 5Y growth {growth:.1%} moderate → {s:.1f}"
    s = min(100.0, _lerp(growth, 0.15, 0.30, 75, 100))
    return s, f"{label} 5Y growth {growth:.1%} strong → {s:.1f}"


def _lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
