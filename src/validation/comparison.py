"""
Comparison table, weakness analysis, and reproducibility audit.

Pure computation functions — no I/O, no external calls.

Design notes
------------
- Alpha is computed arithmetically (strategy_cagr − baseline_cagr), not via
  factor regression.  This is a simplification: arithmetic alpha double-counts
  compounding effects over long periods.
- Overfitting threshold (5% default) and degradation threshold (3% default)
  are heuristics, not statistically calibrated values.
- "Low sample" cutoff (3 trades default) is far below the statistical minimum
  for reliable inference but is a practical safeguard against drawing conclusions
  from 0–2 trades.
- Trades are assigned to periods by entry_date; an exit that falls in a later
  period still attributes its return to the entry period.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from src.backtest.metrics import build_metrics
from src.backtest.types import TradeRecord


# ── Output types ───────────────────────────────────────────────────────────────

@dataclass
class StrategyMetrics:
    """Strategy performance within a single period."""
    period: str
    start_date: date
    end_date: date
    cagr: Optional[float]
    max_drawdown: float
    volatility: Optional[float]
    win_rate: float
    total_return: float          # compound equity return over period trades
    trade_count: int
    avg_confidence: float        # mean entry confidence across period trades


@dataclass
class ComparisonRow:
    """One row of the comparison table — strategy vs all baselines for one period."""
    period: str
    start_date: date
    end_date: date
    strategy_cagr: Optional[float]
    spy_cagr: Optional[float]
    random_cagr: Optional[float]
    stock_bnh_cagr: Optional[float]
    alpha_vs_spy: Optional[float]        # strategy_cagr − spy_cagr
    alpha_vs_random: Optional[float]     # strategy_cagr − random_cagr
    alpha_vs_stock_bnh: Optional[float]  # strategy_cagr − stock_bnh_cagr
    strategy_drawdown: float
    strategy_win_rate: float
    strategy_trades: int


@dataclass
class WeaknessAnalysis:
    """Structural weaknesses in strategy performance on the test period."""
    underperforms_spy: bool
    underperforms_random: bool
    underperforms_stock_bnh: bool
    overfitting_flag: bool         # train CAGR >> test CAGR by overfitting_threshold
    low_sample_flag: bool          # total trades < min_trades
    test_period_degradation: bool  # performance drops from validation to test by > threshold
    notes: list[str]              # human-readable summary; always at least one entry


@dataclass
class ReproducibilityAudit:
    """Confirms that benchmarks are deterministically replayable."""
    seed_used: int
    random_baseline_reproducible: bool   # same seed → identical results on two runs
    identical_time_windows: bool         # all baselines use non-overlapping contiguous periods
    violations: list[str]
    notes: list[str]


# ── Computation functions ──────────────────────────────────────────────────────

def strategy_metrics_for_period(
    trades: list[TradeRecord],
    start: date,
    end: date,
    period: str,
) -> StrategyMetrics:
    """
    Compute strategy metrics for trades whose entry_date falls within [start, end].

    Trade assignment: a trade belongs to the period in which it was entered, even
    if the exit date is in a later period.  This is the simplest unambiguous rule.
    """
    period_trades = [t for t in trades if start <= t.entry_date <= end]
    trade_returns = [t.return_pct for t in period_trades]
    hold_years = [t.hold_years for t in period_trades]

    metrics = build_metrics(trade_returns, hold_years, start, end)

    # Compound equity return for the period
    equity = 1.0
    for r in trade_returns:
        equity *= (1.0 + r)
    total_return = round(equity - 1.0, 6)

    avg_conf = (
        sum(t.entry_confidence for t in period_trades) / len(period_trades)
        if period_trades else 0.0
    )

    return StrategyMetrics(
        period=period,
        start_date=start,
        end_date=end,
        cagr=metrics.cagr,
        max_drawdown=metrics.max_drawdown,
        volatility=metrics.volatility,
        win_rate=metrics.win_rate,
        total_return=total_return,
        trade_count=len(period_trades),
        avg_confidence=round(avg_conf, 4),
    )


def _alpha(strategy: Optional[float], baseline: Optional[float]) -> Optional[float]:
    if strategy is None or baseline is None:
        return None
    return round(strategy - baseline, 6)


def build_comparison_row(
    period: str,
    start: date,
    end: date,
    strategy: StrategyMetrics,
    spy_cagr: Optional[float],
    random_cagr: Optional[float],
    stock_bnh_cagr: Optional[float],
) -> ComparisonRow:
    return ComparisonRow(
        period=period,
        start_date=start,
        end_date=end,
        strategy_cagr=strategy.cagr,
        spy_cagr=spy_cagr,
        random_cagr=random_cagr,
        stock_bnh_cagr=stock_bnh_cagr,
        alpha_vs_spy=_alpha(strategy.cagr, spy_cagr),
        alpha_vs_random=_alpha(strategy.cagr, random_cagr),
        alpha_vs_stock_bnh=_alpha(strategy.cagr, stock_bnh_cagr),
        strategy_drawdown=strategy.max_drawdown,
        strategy_win_rate=strategy.win_rate,
        strategy_trades=strategy.trade_count,
    )


def analyze_weaknesses(
    rows: list[ComparisonRow],
    total_trades: int,
    overfitting_threshold: float = 0.05,
    min_trades: int = 3,
    degradation_threshold: float = 0.03,
) -> WeaknessAnalysis:
    """
    Identify structural weaknesses from the comparison table.

    Parameters
    ----------
    rows                    : ComparisonRow list (one per period).
    total_trades            : Total trades across all periods.
    overfitting_threshold   : CAGR gap (train − test) that triggers overfitting flag. Default 5%.
    min_trades              : Minimum trades for conclusions to be reliable. Default 3.
    degradation_threshold   : Validation→test CAGR drop that triggers degradation flag. Default 3%.

    Known limitations
    -----------------
    - All thresholds are heuristics, not statistically calibrated values.
    - Overfitting is detected by a simple CAGR gap, not by hypothesis testing.
    """
    test_row = next((r for r in rows if r.period == "test"), None)
    val_row = next((r for r in rows if r.period == "validation"), None)
    train_row = next((r for r in rows if r.period == "train"), None)

    underperforms_spy = bool(
        test_row
        and test_row.alpha_vs_spy is not None
        and test_row.alpha_vs_spy < 0
    )
    underperforms_random = bool(
        test_row
        and test_row.alpha_vs_random is not None
        and test_row.alpha_vs_random < 0
    )
    underperforms_stock_bnh = bool(
        test_row
        and test_row.alpha_vs_stock_bnh is not None
        and test_row.alpha_vs_stock_bnh < 0
    )

    overfitting = bool(
        train_row and test_row
        and train_row.strategy_cagr is not None
        and test_row.strategy_cagr is not None
        and (train_row.strategy_cagr - test_row.strategy_cagr) > overfitting_threshold
    )

    test_degradation = bool(
        val_row and test_row
        and val_row.strategy_cagr is not None
        and test_row.strategy_cagr is not None
        and (val_row.strategy_cagr - test_row.strategy_cagr) > degradation_threshold
    )

    notes: list[str] = []
    if overfitting:
        notes.append(
            f"Overfitting: train CAGR {train_row.strategy_cagr:.2%} >> "  # type: ignore[union-attr]
            f"test CAGR {test_row.strategy_cagr:.2%} "  # type: ignore[union-attr]
            f"(threshold {overfitting_threshold:.0%})"
        )
    if underperforms_spy:
        notes.append(
            f"Underperforms SPY on test period "
            f"(alpha {test_row.alpha_vs_spy:.2%})"  # type: ignore[union-attr]
        )
    if underperforms_random:
        notes.append(
            "Underperforms random baseline on test period — "
            "scoring system may not add value over random entry/exit"
        )
    if underperforms_stock_bnh:
        notes.append(
            "Underperforms passive stock buy-and-hold — "
            "active management is destroying value on this ticker"
        )
    if total_trades < min_trades:
        notes.append(
            f"Low sample: {total_trades} trades total "
            f"(minimum recommended: {min_trades}) — conclusions unreliable"
        )
    if test_degradation:
        notes.append(
            f"Performance degrades validation→test by > {degradation_threshold:.0%} — "
            "possible overfitting or regime change"
        )
    if not notes:
        notes.append("No critical weaknesses detected in this backtest")

    return WeaknessAnalysis(
        underperforms_spy=underperforms_spy,
        underperforms_random=underperforms_random,
        underperforms_stock_bnh=underperforms_stock_bnh,
        overfitting_flag=overfitting,
        low_sample_flag=total_trades < min_trades,
        test_period_degradation=test_degradation,
        notes=notes,
    )
