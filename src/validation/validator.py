"""
Benchmarking and validation orchestrator.

Compares the strategy from a completed BacktestResult against three baselines
across train / validation / test periods, then produces a structured report
including weakness analysis and reproducibility audit.

Data leakage contract
---------------------
Stock prices are derived from the snapshots stored in BacktestResult — these
were already constructed at their as_of_date by the backtest module.  The
validator never re-fetches or re-scores data.  Baseline computations use the
same stock price series, ensuring the baselines do not have access to more data
than the strategy did.

No-leakage invariants
---------------------
1. Period boundaries are computed before any baseline calculation begins.
2. Test period data is never used to set thresholds or tune parameters.
3. All baselines use identical time windows to the strategy.
4. Random baseline is seeded before each period to guarantee reproducibility.

Known limitations are documented in docs/BENCHMARKING_MODULE.md.

Public API
----------
validate(ticker, backtest, benchmark_prices, period_split, random_seed,
         benchmark_label) → ValidationResult
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from src.backtest.engine import BacktestResult
from src.logging.logger import log_input, log_result, log_warning
from src.validation.baselines import BaselineResult, buy_and_hold_baseline, random_baseline
from src.validation.comparison import (
    ComparisonRow,
    ReproducibilityAudit,
    StrategyMetrics,
    WeaknessAnalysis,
    analyze_weaknesses,
    build_comparison_row,
    strategy_metrics_for_period,
)
from src.validation.splitter import PeriodSplit, split_periods

_MODULE = "validation.validator"
_PERIODS = ("train", "validation", "test")


# ── Output type ────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """Complete benchmarking and validation output."""
    ticker: str
    period_split: PeriodSplit
    strategy_metrics: dict[str, StrategyMetrics]  # keyed by "train" | "validation" | "test"
    baseline_results: list[BaselineResult]         # 3 baselines × 3 periods = 9 entries
    comparison_table: list[ComparisonRow]          # one per period
    weakness_analysis: WeaknessAnalysis
    reproducibility_audit: ReproducibilityAudit
    notes: list[str]                               # [summary, split, alpha, repro, weakness]


# ── Public entry point ─────────────────────────────────────────────────────────

def validate(
    ticker: str,
    backtest: BacktestResult,
    benchmark_prices: dict[date, float],
    period_split: Optional[PeriodSplit] = None,
    random_seed: int = 42,
    benchmark_label: str = "SPY",
) -> ValidationResult:
    """
    Compare strategy against SPY buy-and-hold, random, and stock buy-and-hold
    baselines across train / validation / test periods.

    Parameters
    ----------
    ticker           : Ticker symbol (for logging and output).
    backtest         : Completed BacktestResult from backtest.engine.run().
    benchmark_prices : SPY (or other benchmark) closing prices by date.
    period_split     : Optional custom split.  If None, auto-splits the backtest
                       window 60% train / 20% validation / 20% test.
    random_seed      : Seed for deterministic random baseline.  Same seed always
                       produces the same baseline results.
    benchmark_label  : Human-readable label for the external benchmark (default "SPY").

    Returns
    -------
    ValidationResult with comparison table, weakness analysis, and reproducibility audit.
    """
    log_input(_MODULE, {
        "ticker": ticker,
        "snapshot_count": len(backtest.snapshots),
        "trade_count": len(backtest.trades),
        "random_seed": random_seed,
        "benchmark_label": benchmark_label,
    })

    # ── Period split ──────────────────────────────────────────────────────────
    if period_split is None:
        period_split = split_periods(backtest.start_date, backtest.end_date)

    # ── Stock prices from snapshots ───────────────────────────────────────────
    # Derived from stored snapshot data — no new fetching
    stock_prices: dict[date, float] = {
        s.as_of_date: s.price
        for s in backtest.snapshots
        if s.as_of_date is not None and s.price is not None
    }
    snapshot_dates = sorted(stock_prices.keys())

    # ── Period definitions ────────────────────────────────────────────────────
    period_bounds = {
        "train":      (period_split.train_start,      period_split.train_end),
        "validation": (period_split.validation_start, period_split.validation_end),
        "test":       (period_split.test_start,        period_split.test_end),
    }

    # ── Average hold years (for sizing random baseline trades) ────────────────
    avg_hold = (
        sum(t.hold_years for t in backtest.trades) / len(backtest.trades)
        if backtest.trades else 1.0
    )
    avg_hold = max(avg_hold, 1.0 / 12)  # floor at 1 month

    # ── Strategy metrics and baselines per period ─────────────────────────────
    strategy_by_period: dict[str, StrategyMetrics] = {}
    baselines: list[BaselineResult] = []
    rows: list[ComparisonRow] = []

    for period in _PERIODS:
        start, end = period_bounds[period]
        strat = strategy_metrics_for_period(backtest.trades, start, end, period)
        strategy_by_period[period] = strat

        # At least 1 random trade per period, matching strategy trade count when possible
        n_random = max(strat.trade_count, 1)

        spy = buy_and_hold_baseline(benchmark_prices, start, end, period, label=benchmark_label)
        stock_bnh = buy_and_hold_baseline(
            stock_prices, start, end, period, label="stock buy-and-hold"
        )
        rnd = random_baseline(
            snapshot_dates, stock_prices, start, end, period,
            n_trades=n_random,
            avg_hold_years=avg_hold,
            seed=random_seed,
        )

        baselines.extend([spy, stock_bnh, rnd])
        rows.append(build_comparison_row(
            period=period, start=start, end=end,
            strategy=strat,
            spy_cagr=spy.cagr,
            random_cagr=rnd.cagr,
            stock_bnh_cagr=stock_bnh.cagr,
        ))

    # ── Reproducibility audit ─────────────────────────────────────────────────
    repro = _reproducibility_audit(
        snapshot_dates=snapshot_dates,
        stock_prices=stock_prices,
        period_split=period_split,
        avg_hold=avg_hold,
        seed=random_seed,
        period_bounds=period_bounds,
    )
    if repro.violations:
        log_warning(_MODULE, "reproducibility_violation", {"violations": repro.violations})

    # ── Weakness analysis ─────────────────────────────────────────────────────
    weaknesses = analyze_weaknesses(rows, total_trades=len(backtest.trades))

    # ── Notes ─────────────────────────────────────────────────────────────────
    test_row = next((r for r in rows if r.period == "test"), None)
    spy_alpha_str = (
        f"{test_row.alpha_vs_spy:+.2%}"
        if test_row and test_row.alpha_vs_spy is not None
        else "N/A"
    )
    notes = [
        f"{ticker}: validated over {backtest.start_date} → {backtest.end_date}",
        (
            f"Split: train {period_split.train_years:.1f}y | "
            f"validation {period_split.validation_years:.1f}y | "
            f"test {period_split.test_years:.1f}y"
        ),
        f"Test-period alpha vs {benchmark_label}: {spy_alpha_str}",
        f"Reproducibility: {'PASSED' if repro.random_baseline_reproducible else 'FAILED'}",
        f"Weaknesses: {weaknesses.notes[0]}",
    ]

    result = ValidationResult(
        ticker=ticker,
        period_split=period_split,
        strategy_metrics=strategy_by_period,
        baseline_results=baselines,
        comparison_table=rows,
        weakness_analysis=weaknesses,
        reproducibility_audit=repro,
        notes=notes,
    )

    log_result(_MODULE, {
        "ticker": ticker,
        "total_trades": len(backtest.trades),
        "test_alpha_vs_spy": test_row.alpha_vs_spy if test_row else None,
        "overfitting": weaknesses.overfitting_flag,
        "underperforms_spy": weaknesses.underperforms_spy,
        "reproducible": repro.random_baseline_reproducible,
    })

    return result


# ── Reproducibility audit ──────────────────────────────────────────────────────

def _reproducibility_audit(
    snapshot_dates: list[date],
    stock_prices: dict[date, float],
    period_split: PeriodSplit,
    avg_hold: float,
    seed: int,
    period_bounds: dict[str, tuple[date, date]],
) -> ReproducibilityAudit:
    """
    Verify that random baseline results are deterministic and period windows are
    non-overlapping.

    Reproducibility check: run the test-period random baseline twice with the
    same seed.  The results must be bit-identical.

    Time-window check: verify train_end < validation_start and
    validation_end < test_start (non-overlapping by construction from split_periods,
    but worth auditing when custom splits are provided).
    """
    test_start, test_end = period_bounds["test"]

    r1 = random_baseline(snapshot_dates, stock_prices, test_start, test_end, "test",
                         n_trades=1, avg_hold_years=avg_hold, seed=seed)
    r2 = random_baseline(snapshot_dates, stock_prices, test_start, test_end, "test",
                         n_trades=1, avg_hold_years=avg_hold, seed=seed)

    reproducible = r1.cagr == r2.cagr and r1.trade_count == r2.trade_count

    # Periods must be non-overlapping and in chronological order
    identical_windows = (
        period_split.train_end < period_split.validation_start
        and period_split.validation_end < period_split.test_start
    )

    violations: list[str] = []
    if not reproducible:
        violations.append(
            "Random baseline non-deterministic: two runs with the same seed "
            "produced different results"
        )
    if not identical_windows:
        violations.append(
            "Period boundaries overlap or are out of order — train/validation/test "
            "windows must be non-overlapping and chronological"
        )

    return ReproducibilityAudit(
        seed_used=seed,
        random_baseline_reproducible=reproducible,
        identical_time_windows=identical_windows,
        violations=violations,
        notes=[
            "Reproducibility verified by two independent runs of random baseline with same seed.",
            "Time-window integrity verified: periods are non-overlapping and chronological.",
        ],
    )
