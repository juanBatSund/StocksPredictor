from dataclasses import dataclass

from src.data.models import Fundamentals


@dataclass
class QualityScore:
    total: float          # 0–100
    roe: float            # 0–100
    debt_to_equity: float # 0–100
    fcf: float            # 0–100
    notes: list[str]


def score(f: Fundamentals) -> QualityScore:
    roe_s, roe_note = _score_roe(f.roe)
    de_s, de_note = _score_de(f.debt_to_equity)
    fcf_s, fcf_note = _score_fcf(f.free_cash_flow)
    total = round((roe_s + de_s + fcf_s) / 3, 2)
    return QualityScore(
        total=total,
        roe=round(roe_s, 2),
        debt_to_equity=round(de_s, 2),
        fcf=round(fcf_s, 2),
        notes=[roe_note, de_note, fcf_note],
    )


# ── metric scorers ────────────────────────────────────────────────────────────

def _score_roe(roe: float | None) -> tuple[float, str]:
    """
    Threshold: ROE > 12% (system.md).
    Gradient: 0→50 below threshold, 50→100 from 12%→25%.
    """
    if roe is None:
        return 0.0, "ROE missing → 0"
    if roe <= 0:
        return 0.0, f"ROE {roe:.1%} negative → 0"
    if roe <= 0.12:
        s = _lerp(roe, 0, 0.12, 0, 50)
        return s, f"ROE {roe:.1%} below 12% threshold → {s:.1f}"
    if roe <= 0.25:
        s = _lerp(roe, 0.12, 0.25, 50, 100)
        return s, f"ROE {roe:.1%} above threshold → {s:.1f}"
    return 100.0, f"ROE {roe:.1%} excellent → 100"


def _score_de(de: float | None) -> tuple[float, str]:
    """
    Threshold: D/E < 1.0 (system.md). Lower is better.
    Gradient: 0→0.5 maps 100→75, 0.5→1.0 maps 75→50, 1.0→2.0 maps 50→0.
    """
    if de is None:
        return 0.0, "D/E missing → 0"
    if de < 0:
        return 0.0, f"D/E {de:.2f} negative equity → 0"
    if de < 0.5:
        s = _lerp(de, 0, 0.5, 100, 75)
        return s, f"D/E {de:.2f} low leverage → {s:.1f}"
    if de < 1.0:
        s = _lerp(de, 0.5, 1.0, 75, 50)
        return s, f"D/E {de:.2f} acceptable → {s:.1f}"
    if de < 2.0:
        s = _lerp(de, 1.0, 2.0, 50, 0)
        return s, f"D/E {de:.2f} above threshold → {s:.1f}"
    return 0.0, f"D/E {de:.2f} very high leverage → 0"


def _score_fcf(fcf: float | None) -> tuple[float, str]:
    """
    Threshold: positive FCF (system.md). Binary.
    """
    if fcf is None:
        return 0.0, "FCF missing → 0"
    if fcf <= 0:
        return 0.0, f"FCF {fcf:,.0f} negative → 0"
    return 100.0, f"FCF {fcf:,.0f} positive → 100"


def _lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
