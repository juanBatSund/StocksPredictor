"""
Benchmark comparison for the backtesting engine.

Computes buy-and-hold CAGR for an external price series (e.g. SPY) over the
same calendar window as the backtest, then computes alpha vs the strategy.

Known limitations
-----------------
- Alpha is not risk-adjusted (no Sharpe ratio vs benchmark).
- Benchmark prices are accepted without provenance verification — the caller
  must ensure they do not contain future data relative to the simulation end.
- Price lookup uses the nearest date ≤ target, so a benchmark that starts
  after the simulation start will silently use its first available price.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from src.backtest.metrics import compute_cagr


@dataclass
class BenchmarkComparison:
    """Strategy CAGR vs a buy-and-hold benchmark over the same period."""
    benchmark_label: str
    start_date: date
    end_date: date
    strategy_cagr: Optional[float]
    benchmark_cagr: Optional[float]
    alpha: Optional[float]       # strategy_cagr − benchmark_cagr; None if either is unavailable
    outperforms: Optional[bool]  # True when alpha > 0; None when alpha unavailable


def nearest_price(prices: dict[date, float], target: date) -> Optional[float]:
    """
    Return the price for the nearest date ≤ target.

    Falls back to the earliest available date if no price precedes target.
    Returns None for an empty dict.
    """
    if not prices:
        return None
    if target in prices:
        return prices[target]
    before = sorted(d for d in prices if d <= target)
    if before:
        return prices[before[-1]]
    return prices[min(prices)]


def compute_benchmark_cagr(
    prices: dict[date, float],
    start_date: date,
    end_date: date,
) -> Optional[float]:
    """Buy-and-hold CAGR for the benchmark over [start_date, end_date]."""
    if not prices or start_date >= end_date:
        return None
    start_p = nearest_price(prices, start_date)
    end_p = nearest_price(prices, end_date)
    if start_p is None or end_p is None or start_p <= 0:
        return None
    years = (end_date - start_date).days / 365.25
    return compute_cagr(start_p, end_p, years)


def compare(
    strategy_cagr: Optional[float],
    benchmark_prices: dict[date, float],
    start_date: date,
    end_date: date,
    benchmark_label: str = "SPY",
) -> BenchmarkComparison:
    """Produce a BenchmarkComparison for the given strategy CAGR and benchmark data."""
    bm_cagr = compute_benchmark_cagr(benchmark_prices, start_date, end_date)

    if strategy_cagr is not None and bm_cagr is not None:
        alpha = round(strategy_cagr - bm_cagr, 6)
        outperforms: Optional[bool] = alpha > 0
    else:
        alpha = None
        outperforms = None

    return BenchmarkComparison(
        benchmark_label=benchmark_label,
        start_date=start_date,
        end_date=end_date,
        strategy_cagr=strategy_cagr,
        benchmark_cagr=bm_cagr,
        alpha=alpha,
        outperforms=outperforms,
    )
