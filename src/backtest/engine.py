"""
Deterministic historical backtesting engine.

Replays pre-computed HistoricalSnapshot objects and simulates portfolio
entry/exit according to the system's trading rules.  No decision-engine
code runs here — this module is a pure replay mechanism.

Data leakage contract
---------------------
The CALLER is responsible for constructing HistoricalSnapshot objects using
only information available at `as_of_date`.  The engine audits structural
integrity (chronological order, duplicate dates, missing as_of_date) but
cannot verify that upstream data fetching was truly point-in-time.

Trading rules (system.md / settings.py)
----------------------------------------
Entry  : decision == "BUY" and a price is available on that date.
Exit   : score < BACKTEST_EXIT_SCORE (60)
         OR hold_years >= BACKTEST_MAX_HOLD_YEARS (2)
         OR end of simulation (position still open after last snapshot).

One position at a time — new BUY signals while already invested are ignored.

Known limitations are documented in docs/BACKTEST_MODULE.md.

Public API
----------
run(ticker, snapshots, benchmark_prices, benchmark_label) → BacktestResult
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from config.settings import BACKTEST_EXIT_SCORE, BACKTEST_MAX_HOLD_YEARS
from src.backtest.audit import LeakageAudit, audit
from src.backtest.benchmark import BenchmarkComparison, compare
from src.backtest.metrics import PerformanceMetrics, build_metrics, compute_cagr
from src.backtest.types import HistoricalSnapshot, TradeRecord
from src.logging.logger import log_input, log_result, log_warning

_MODULE = "backtest.engine"


# ── Output type ────────────────────────────────────────────────────────────────

@dataclass
class BacktestResult:
    """Complete, auditable output of the backtesting engine — nothing is hidden."""
    ticker: str
    start_date: date
    end_date: date
    snapshots: list[HistoricalSnapshot]              # original input, unchanged
    trades: list[TradeRecord]                        # one record per completed trade
    metrics: PerformanceMetrics
    benchmark: BenchmarkComparison
    leakage_audit: LeakageAudit
    confidence_evolution: list[tuple[date, float]]  # (date, decision.confidence) per snapshot
    decisions_over_time: list[tuple[date, str]]     # (date, decision.decision) per snapshot
    reasoning_trace: list[str]                      # step-by-step simulation log
    notes: list[str]                                # [summary, metrics, benchmark, audit]


# ── Public entry point ─────────────────────────────────────────────────────────

def run(
    ticker: str,
    snapshots: list[HistoricalSnapshot],
    benchmark_prices: dict[date, float],
    benchmark_label: str = "SPY",
) -> BacktestResult:
    """
    Replay stored historical decision snapshots and simulate portfolio performance.

    Parameters
    ----------
    ticker            : Stock ticker symbol (for logging and output identification).
    snapshots         : HistoricalSnapshot objects, one per decision date.
                        Will be sorted ascending by as_of_date internally.
    benchmark_prices  : Historical closing prices for the benchmark (e.g. SPY).
                        Keys: date, values: closing price.
    benchmark_label   : Human-readable label for the benchmark (default "SPY").

    Returns
    -------
    BacktestResult with full audit trail, performance metrics, and benchmark comparison.
    """
    log_input(_MODULE, {
        "ticker": ticker,
        "snapshot_count": len(snapshots),
        "benchmark_label": benchmark_label,
    })

    if not snapshots:
        return _empty_result(ticker, benchmark_label)

    # Sort chronologically — None as_of_date snapshots go to the end
    snapshots = sorted(
        snapshots,
        key=lambda s: s.as_of_date if s.as_of_date is not None else date.max,
    )

    # ── Leakage audit (always runs, even on malformed snapshots) ──────────────
    leakage = audit(snapshots)
    if not leakage.passed:
        log_warning(_MODULE, "leakage_audit_violation", {"violations": leakage.violations})

    valid_dates = [s.as_of_date for s in snapshots if s.as_of_date is not None]
    if not valid_dates:
        today = date.today()
        return BacktestResult(
            ticker=ticker,
            start_date=today,
            end_date=today,
            snapshots=snapshots,
            trades=[],
            metrics=build_metrics([], [], today, today),
            benchmark=compare(None, benchmark_prices, today, today, benchmark_label),
            leakage_audit=leakage,
            confidence_evolution=[],
            decisions_over_time=[],
            reasoning_trace=["No snapshot has a valid as_of_date — nothing to simulate."],
            notes=[f"{ticker}: 0 valid snapshots, 0 trades."],
        )
    start_date = valid_dates[0]
    end_date = valid_dates[-1]

    # ── Simulation ────────────────────────────────────────────────────────────
    trades, trace = _simulate(ticker, snapshots)

    # ── Metrics ───────────────────────────────────────────────────────────────
    metrics = build_metrics(
        trade_returns=[t.return_pct for t in trades],
        hold_years_list=[t.hold_years for t in trades],
        simulation_start=start_date,
        simulation_end=end_date,
    )

    # ── Benchmark ─────────────────────────────────────────────────────────────
    benchmark = compare(
        strategy_cagr=metrics.cagr,
        benchmark_prices=benchmark_prices,
        start_date=start_date,
        end_date=end_date,
        benchmark_label=benchmark_label,
    )

    # ── Evolution series ──────────────────────────────────────────────────────
    confidence_evolution = [(s.as_of_date, s.decision.confidence) for s in snapshots]
    decisions_over_time = [(s.as_of_date, s.decision.decision) for s in snapshots]

    # ── Notes ─────────────────────────────────────────────────────────────────
    cagr_str = f"{metrics.cagr:.2%}" if metrics.cagr is not None else "N/A"
    alpha_str = f"{benchmark.alpha:+.2%}" if benchmark.alpha is not None else "N/A"
    outperform_str = (
        "outperforms" if benchmark.outperforms
        else "underperforms" if benchmark.outperforms is False
        else "N/A"
    )
    notes = [
        f"{ticker}: {len(trades)} trade(s) simulated from {start_date} to {end_date}",
        (
            f"CAGR {cagr_str} | Win rate {metrics.win_rate:.0%} "
            f"| Max drawdown {metrics.max_drawdown:.2%}"
        ),
        f"vs {benchmark_label}: alpha {alpha_str} ({outperform_str})",
        (
            f"Leakage audit: {'PASSED' if leakage.passed else 'FAILED'}"
            + (f" — {len(leakage.violations)} violation(s)" if not leakage.passed else "")
        ),
    ]

    result = BacktestResult(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        snapshots=snapshots,
        trades=trades,
        metrics=metrics,
        benchmark=benchmark,
        leakage_audit=leakage,
        confidence_evolution=confidence_evolution,
        decisions_over_time=decisions_over_time,
        reasoning_trace=trace,
        notes=notes,
    )

    log_result(_MODULE, {
        "ticker": ticker,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "total_trades": len(trades),
        "win_rate": metrics.win_rate,
        "cagr": metrics.cagr,
        "max_drawdown": metrics.max_drawdown,
        "leakage_passed": leakage.passed,
        "benchmark_alpha": benchmark.alpha,
    })

    return result


# ── Simulation ─────────────────────────────────────────────────────────────────

def _simulate(
    ticker: str,
    snapshots: list[HistoricalSnapshot],
) -> tuple[list[TradeRecord], list[str]]:
    """
    Walk the snapshot sequence and simulate entry/exit.

    Entry condition : decision == "BUY" and price is not None.
    Exit conditions : score < BACKTEST_EXIT_SCORE (hard)
                      OR hold_years >= BACKTEST_MAX_HOLD_YEARS (hard)
                      OR last snapshot reached (soft — end_of_simulation).

    One position at a time: new BUY signals while invested are ignored.
    If an exit is triggered but price is None, the position is held until
    the next available price.  This is logged in the trace.

    Returns (trades, reasoning_trace).
    """
    trades: list[TradeRecord] = []
    trace: list[str] = []
    position: Optional[HistoricalSnapshot] = None

    for snap in snapshots:
        if snap.as_of_date is None:
            trace.append(f"{snap.ticker}: snapshot has no as_of_date — skipped")
            continue

        if position is None:
            # ── Look for entry ────────────────────────────────────────────────
            if snap.decision.decision == "BUY" and snap.price is not None:
                position = snap
                trace.append(
                    f"{snap.as_of_date}: ENTER — BUY signal | "
                    f"price={snap.price:.2f} | score={snap.decision.score:.1f} | "
                    f"confidence={snap.decision.confidence:.2f}"
                )
            else:
                price_str = f"{snap.price:.2f}" if snap.price is not None else "no price"
                trace.append(
                    f"{snap.as_of_date}: no entry "
                    f"(decision={snap.decision.decision}, {price_str})"
                )

        else:
            # ── In position — check exit conditions ───────────────────────────
            hold_days = (snap.as_of_date - position.as_of_date).days
            hold_years = hold_days / 365.25
            score_drop = snap.decision.score < BACKTEST_EXIT_SCORE
            max_hold = hold_years >= BACKTEST_MAX_HOLD_YEARS
            exit_triggered = score_drop or max_hold

            if exit_triggered:
                if snap.price is not None:
                    reason = "score_drop" if score_drop else "max_hold"
                    trade = _make_trade(position, snap, reason)
                    trades.append(trade)
                    position = None
                    trace.append(
                        f"{snap.as_of_date}: EXIT ({reason}) | "
                        f"price={snap.price:.2f} | return={trade.return_pct:+.2%} | "
                        f"hold={hold_years:.2f}y | score={snap.decision.score:.1f}"
                    )
                else:
                    reason = "score_drop" if score_drop else "max_hold"
                    trace.append(
                        f"{snap.as_of_date}: EXIT TRIGGERED ({reason}) but price unavailable "
                        f"— holding until next available price"
                    )
            else:
                price_str = f"{snap.price:.2f}" if snap.price is not None else "no price"
                trace.append(
                    f"{snap.as_of_date}: hold | "
                    f"score={snap.decision.score:.1f} | "
                    f"hold={hold_years:.2f}y | {price_str}"
                )

    # ── Close open position at end of simulation ───────────────────────────────
    if position is not None:
        last = snapshots[-1]
        if last.as_of_date == position.as_of_date:
            trace.append(
                f"{last.as_of_date}: position opened on last snapshot — "
                f"no subsequent date available for exit, trade not recorded"
            )
        elif last.price is not None:
            trade = _make_trade(position, last, "end_of_simulation")
            trades.append(trade)
            trace.append(
                f"{last.as_of_date}: END-OF-SIMULATION exit | "
                f"price={last.price:.2f} | return={trade.return_pct:+.2%}"
            )
        else:
            trace.append(
                f"{last.as_of_date}: END-OF-SIMULATION — position open but no exit price, "
                f"trade not recorded"
            )

    return trades, trace


def _make_trade(
    entry: HistoricalSnapshot,
    exit_snap: HistoricalSnapshot,
    exit_reason: str,
) -> TradeRecord:
    assert entry.price is not None   # guarded by simulation logic
    assert exit_snap.price is not None

    hold_days = (exit_snap.as_of_date - entry.as_of_date).days
    hold_years = hold_days / 365.25
    ret = (exit_snap.price - entry.price) / entry.price
    ann_ret = compute_cagr(entry.price, exit_snap.price, hold_years)

    return TradeRecord(
        ticker=entry.ticker,
        entry_date=entry.as_of_date,
        exit_date=exit_snap.as_of_date,
        entry_price=entry.price,
        exit_price=exit_snap.price,
        exit_reason=exit_reason,
        entry_score=entry.decision.score,
        exit_score=exit_snap.decision.score,
        entry_confidence=entry.decision.confidence,
        hold_days=hold_days,
        hold_years=round(hold_years, 4),
        return_pct=round(ret, 6),
        annualized_return=ann_ret,
    )


def _empty_result(ticker: str, benchmark_label: str) -> BacktestResult:
    today = date.today()
    empty_metrics = build_metrics([], [], today, today)
    empty_benchmark = compare(None, {}, today, today, benchmark_label)
    empty_audit = LeakageAudit(
        passed=True,
        violations=[],
        snapshots_checked=0,
        notes=["No snapshots provided."],
    )
    return BacktestResult(
        ticker=ticker,
        start_date=today,
        end_date=today,
        snapshots=[],
        trades=[],
        metrics=empty_metrics,
        benchmark=empty_benchmark,
        leakage_audit=empty_audit,
        confidence_evolution=[],
        decisions_over_time=[],
        reasoning_trace=["No snapshots provided — nothing to simulate."],
        notes=[f"{ticker}: 0 snapshots, 0 trades."],
    )
