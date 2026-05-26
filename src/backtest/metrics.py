"""
Performance metric computations for the backtesting engine.

All functions are pure (no side effects, no I/O).  Callers pass primitive
lists rather than domain objects to keep this module dependency-free.

Known limitations
-----------------
- `compute_volatility` uses per-trade returns, NOT daily returns.
  Standard market volatility (daily std × √252) requires a continuous
  price series that this engine does not maintain.  Treat the output
  as "cross-trade return dispersion" rather than annualized volatility.
- CAGR is computed over the full simulation period (calendar time), so
  idle cash periods between trades drag it down.  This is intentional —
  it makes the metric comparable to a buy-and-hold benchmark over the
  same window.
- Max drawdown is measured on the per-trade equity curve (trade 0, trade 1, …),
  not on a daily mark-to-market.  Intra-trade drawdowns are invisible.
"""

import math
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class PerformanceMetrics:
    """Aggregated performance summary for a backtest run."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float                  # winning_trades / total_trades; 0.0 when no trades
    avg_return_pct: float            # mean trade return
    cagr: Optional[float]            # calendar-period CAGR; None when period ≤ 0
    max_drawdown: float              # peak-to-trough on equity curve [0.0, 1.0]
    volatility: Optional[float]      # std of trade returns; None when trades < 2
    avg_hold_years: float            # mean hold duration per trade


def compute_cagr(initial: float, final: float, years: float) -> Optional[float]:
    """
    Compound Annual Growth Rate.

    Returns None if inputs are non-positive or the period is too short to be
    meaningful (< 1 month ≈ 0.083 years).
    """
    if initial <= 0 or final <= 0 or years < 1 / 12:
        return None
    return round((final / initial) ** (1.0 / years) - 1.0, 6)


def compute_max_drawdown(equity_curve: list[float]) -> float:
    """
    Maximum peak-to-trough drawdown on a sequential equity curve.

    Returns a positive fraction (0.20 = −20% drawdown).  Returns 0.0 for
    curves with fewer than 2 data points or no decline.
    """
    if len(equity_curve) < 2:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
    return round(max_dd, 6)


def compute_win_rate(trade_returns: list[float]) -> float:
    """Fraction of trades with a positive return.  Returns 0.0 for empty input."""
    if not trade_returns:
        return 0.0
    wins = sum(1 for r in trade_returns if r > 0)
    return round(wins / len(trade_returns), 4)


def compute_volatility(trade_returns: list[float]) -> Optional[float]:
    """
    Standard deviation of per-trade returns.

    NOT equivalent to annualized daily volatility.  Returns None for fewer
    than 2 observations.
    """
    n = len(trade_returns)
    if n < 2:
        return None
    mean = sum(trade_returns) / n
    variance = sum((r - mean) ** 2 for r in trade_returns) / (n - 1)
    return round(math.sqrt(variance), 6)


def build_metrics(
    trade_returns: list[float],
    hold_years_list: list[float],
    simulation_start: date,
    simulation_end: date,
) -> PerformanceMetrics:
    """
    Aggregate all trades into a PerformanceMetrics summary.

    CAGR is computed over the full simulation window (start → end) so that
    idle cash periods between trades are reflected in the return.  This
    matches the time window used for benchmark comparison.
    """
    n = len(trade_returns)
    winning = sum(1 for r in trade_returns if r > 0)
    losing = n - winning

    # Sequential equity curve: each trade multiplies the portfolio
    equity_curve = [1.0]
    for r in trade_returns:
        equity_curve.append(equity_curve[-1] * (1.0 + r))

    max_dd = compute_max_drawdown(equity_curve)

    total_period_years = (simulation_end - simulation_start).days / 365.25
    cagr = compute_cagr(1.0, equity_curve[-1], total_period_years) if n > 0 else None

    vol = compute_volatility(trade_returns) if n >= 2 else None

    avg_ret = round(sum(trade_returns) / n, 6) if n > 0 else 0.0
    avg_hold = round(sum(hold_years_list) / n, 4) if n > 0 else 0.0

    return PerformanceMetrics(
        total_trades=n,
        winning_trades=winning,
        losing_trades=losing,
        win_rate=compute_win_rate(trade_returns),
        avg_return_pct=avg_ret,
        cagr=cagr,
        max_drawdown=max_dd,
        volatility=vol,
        avg_hold_years=avg_hold,
    )
