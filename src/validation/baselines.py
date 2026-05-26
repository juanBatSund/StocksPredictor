"""
Baseline strategies for benchmarking.

Three deterministic baselines are provided:

1. buy_and_hold_baseline()
   Buy at start of period, sell at end.  Used for both the external benchmark
   (e.g. SPY) and the stock itself (passive hold).

2. random_baseline()
   Randomly select n_trades entry dates from the available snapshot dates,
   hold for avg_hold_years, sell.  Deterministic via seed.
   Answers: "is the scoring system better than random entry/exit on this stock?"

Known limitations
-----------------
- Buy-and-hold volatility is None (one trade — undefined).
- Random baseline uses snapshot dates, not a continuous price series; it only
  captures the same calendar dates the strategy considered, not arbitrary intraday.
- Random baseline trade count is capped at available snapshot dates — if n_trades
  exceeds available dates, some iterations will repeat the same entry date.
- All baselines assume no transaction costs.
"""

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from src.backtest.benchmark import nearest_price
from src.backtest.metrics import (
    compute_cagr,
    compute_max_drawdown,
    compute_volatility,
    compute_win_rate,
)


@dataclass
class BaselineResult:
    """Performance of a single baseline strategy over one period."""
    label: str
    period: str                  # "train" | "validation" | "test"
    start_date: date
    end_date: date
    cagr: Optional[float]
    max_drawdown: float
    volatility: Optional[float]
    win_rate: float
    total_return: float
    trade_count: int
    notes: list[str]


def buy_and_hold_baseline(
    prices: dict[date, float],
    start: date,
    end: date,
    period: str,
    label: str,
) -> BaselineResult:
    """
    Buy at the nearest price on or before `start`; sell at the nearest on or before `end`.

    Returns a BaselineResult with trade_count=0 and all metrics None/0 if price data
    is unavailable for either boundary.
    """
    start_p = nearest_price(prices, start)
    end_p = nearest_price(prices, end)

    if start_p is None or end_p is None or start_p <= 0:
        return BaselineResult(
            label=label, period=period, start_date=start, end_date=end,
            cagr=None, max_drawdown=0.0, volatility=None, win_rate=0.0,
            total_return=0.0, trade_count=0,
            notes=["Price data unavailable for this period"],
        )

    total_return = (end_p - start_p) / start_p
    years = (end - start).days / 365.25
    cagr = compute_cagr(start_p, end_p, years)
    max_dd = compute_max_drawdown([1.0, 1.0 + total_return])

    return BaselineResult(
        label=label,
        period=period,
        start_date=start,
        end_date=end,
        cagr=cagr,
        max_drawdown=max_dd,
        volatility=None,   # single trade — undefined
        win_rate=1.0 if total_return > 0 else 0.0,
        total_return=round(total_return, 6),
        trade_count=1,
        notes=[
            f"Entry: {start_p:.2f} (on/before {start})",
            f"Exit:  {end_p:.2f} (on/before {end})",
        ],
    )


def random_baseline(
    snapshot_dates: list[date],
    snapshot_prices: dict[date, float],
    start: date,
    end: date,
    period: str,
    n_trades: int,
    avg_hold_years: float,
    seed: int,
    label: str = "Random strategy",
) -> BaselineResult:
    """
    Simulate n_trades random BUY/exit cycles using the strategy's snapshot dates.

    Entry dates are drawn uniformly at random from dates in [start, end] that
    have a known price.  Exit date = entry + avg_hold_years (clamped to end and
    rounded to the nearest available snapshot date).

    Deterministic: two calls with the same seed and inputs always return
    identical results.

    Parameters
    ----------
    snapshot_dates   : Sorted list of dates with available prices.
    snapshot_prices  : Price at each snapshot date.
    start / end      : Period boundaries (inclusive).
    n_trades         : Number of random trades to simulate.
    avg_hold_years   : Hold duration in years.
    seed             : RNG seed for reproducibility.
    """
    rng = random.Random(seed)
    available = sorted(
        d for d in snapshot_dates if start <= d <= end and d in snapshot_prices
    )

    if not available or n_trades == 0:
        return BaselineResult(
            label=label, period=period, start_date=start, end_date=end,
            cagr=None, max_drawdown=0.0, volatility=None, win_rate=0.0,
            total_return=0.0, trade_count=0,
            notes=[f"No available dates or n_trades=0 (seed={seed})"],
        )

    hold_days = int(avg_hold_years * 365.25)
    trade_returns: list[float] = []

    for _ in range(n_trades):
        entry_date = rng.choice(available)
        entry_p = snapshot_prices[entry_date]

        # Find the nearest available date at or after the intended exit
        ideal_exit = min(entry_date + timedelta(days=hold_days), end)
        after = [d for d in available if d >= ideal_exit]
        before = [d for d in available if entry_date < d <= ideal_exit]

        if after:
            exit_date = after[0]
        elif before:
            exit_date = before[-1]
        else:
            continue  # no valid exit date

        exit_p = snapshot_prices[exit_date]
        if entry_p > 0 and exit_date > entry_date:
            trade_returns.append((exit_p - entry_p) / entry_p)

    if not trade_returns:
        return BaselineResult(
            label=label, period=period, start_date=start, end_date=end,
            cagr=None, max_drawdown=0.0, volatility=None, win_rate=0.0,
            total_return=0.0, trade_count=0,
            notes=[f"No valid trades (seed={seed}, avg_hold={avg_hold_years:.1f}y)"],
        )

    equity = [1.0]
    for r in trade_returns:
        equity.append(equity[-1] * (1.0 + r))

    years = (end - start).days / 365.25
    cagr = compute_cagr(1.0, equity[-1], years)
    max_dd = compute_max_drawdown(equity)
    vol = compute_volatility(trade_returns) if len(trade_returns) >= 2 else None
    total_return = round(equity[-1] - 1.0, 6)

    return BaselineResult(
        label=label,
        period=period,
        start_date=start,
        end_date=end,
        cagr=cagr,
        max_drawdown=max_dd,
        volatility=vol,
        win_rate=compute_win_rate(trade_returns),
        total_return=total_return,
        trade_count=len(trade_returns),
        notes=[
            f"seed={seed} | requested={n_trades} | completed={len(trade_returns)}",
            f"avg_hold={avg_hold_years:.2f}y",
        ],
    )
