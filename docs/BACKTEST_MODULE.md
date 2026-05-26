# Backtest Module

**Location:** `src/backtest/`  
**Tests:** `tests/test_backtest/` (120 tests)  
**Depends on:** `src/decision/engine.py`, `src/sentiment/scorer.py`, `src/macro/tagger.py`, `src/backtest/metrics.py`, `src/backtest/benchmark.py`, `src/backtest/audit.py`

---

## Purpose

Replay pre-computed historical decision snapshots and simulate portfolio entry/exit
according to the system's trading rules.  Report performance metrics, benchmark
comparison, data leakage audit, and a full reasoning trace.

**What this module is NOT:**
- It does not re-run the decision engine on historical data.
- It does not fetch prices or fundamentals from external sources.
- It does not guarantee that upstream data was truly point-in-time.

The caller constructs `HistoricalSnapshot` objects using only data available at
`as_of_date`; this module replays those stored decisions.

---

## Architecture

```
CALLER
  → constructs HistoricalSnapshot objects (one per date, per ticker)
  → provides benchmark price series (e.g. SPY)

backtest.engine.run()
  1. Sort snapshots chronologically
  2. Run structural leakage audit
  3. Simulate trade entry/exit
  4. Compute performance metrics
  5. Compare to benchmark
  6. Build confidence evolution and decision timeline
  7. Return BacktestResult (complete audit trail)
```

---

## Files

| File | Responsibility |
|------|----------------|
| `types.py` | `HistoricalSnapshot`, `TradeRecord` dataclasses |
| `metrics.py` | Pure metric functions: CAGR, drawdown, win rate, volatility |
| `benchmark.py` | Benchmark price lookup and CAGR comparison |
| `audit.py` | Structural data leakage audit |
| `engine.py` | Main `run()` entry point, simulation loop, `BacktestResult` |

---

## Input

```python
from src.backtest.engine import run
from src.backtest.types import HistoricalSnapshot

result = run(
    ticker="AAPL",
    snapshots=[
        HistoricalSnapshot(
            as_of_date=date(2020, 1, 1),
            ticker="AAPL",
            price=295.0,
            decision=decide("AAPL", fundamental, ...),
        ),
        HistoricalSnapshot(
            as_of_date=date(2022, 1, 1),
            ticker="AAPL",
            price=182.0,
            decision=decide("AAPL", fundamental_2022, ...),
        ),
    ],
    benchmark_prices={
        date(2020, 1, 1): 324.87,
        date(2022, 1, 1): 454.68,
    },
    benchmark_label="SPY",
)
```

---

## Output: `BacktestResult`

```python
@dataclass
class BacktestResult:
    ticker: str
    start_date: date
    end_date: date
    snapshots: list[HistoricalSnapshot]              # original input unchanged
    trades: list[TradeRecord]                        # one per completed trade
    metrics: PerformanceMetrics
    benchmark: BenchmarkComparison
    leakage_audit: LeakageAudit
    confidence_evolution: list[tuple[date, float]]   # (date, confidence) per snapshot
    decisions_over_time: list[tuple[date, str]]      # (date, decision) per snapshot
    reasoning_trace: list[str]                       # step-by-step simulation log
    notes: list[str]                                 # [summary, metrics, benchmark, audit]
```

### `TradeRecord`

```python
@dataclass
class TradeRecord:
    ticker: str
    entry_date: date; exit_date: date
    entry_price: float; exit_price: float
    exit_reason: str        # "score_drop" | "max_hold" | "end_of_simulation"
    entry_score: float; exit_score: Optional[float]
    entry_confidence: float
    hold_days: int; hold_years: float
    return_pct: float       # (exit_price − entry_price) / entry_price
    annualized_return: Optional[float]  # None if hold < 1 month
```

### `PerformanceMetrics`

```python
@dataclass
class PerformanceMetrics:
    total_trades: int
    winning_trades: int; losing_trades: int
    win_rate: float
    avg_return_pct: float
    cagr: Optional[float]       # calendar-period CAGR over simulation window
    max_drawdown: float         # peak-to-trough on per-trade equity curve
    volatility: Optional[float] # std of trade returns (NOT annualized daily vol)
    avg_hold_years: float
```

### `BenchmarkComparison`

```python
@dataclass
class BenchmarkComparison:
    benchmark_label: str
    start_date: date; end_date: date
    strategy_cagr: Optional[float]
    benchmark_cagr: Optional[float]
    alpha: Optional[float]      # strategy_cagr − benchmark_cagr
    outperforms: Optional[bool]
```

### `LeakageAudit`

```python
@dataclass
class LeakageAudit:
    passed: bool
    violations: list[str]
    snapshots_checked: int
    notes: list[str]
```

---

## Trading Rules

Defined in `system.md` and `config/settings.py`:

| Parameter | Value | Source |
|-----------|-------|--------|
| Entry condition | `decision == "BUY"` and price available | system.md |
| Exit: score drop | `score < BACKTEST_EXIT_SCORE (60)` | settings.py |
| Exit: max hold | `hold_years >= BACKTEST_MAX_HOLD_YEARS (2)` | settings.py |
| Exit: end of simulation | last snapshot reached, position still open | engine.py |
| Simultaneous positions | one at a time | engine.py |

BUY signals while already invested are silently ignored (logged in trace).

---

## Algorithms

### Simulation Loop

```
sort snapshots by as_of_date ascending
position = None

for each snapshot:
    if as_of_date is None → skip (leakage audit violation)
    if position is None:
        if decision == "BUY" and price is not None → enter position
    else:
        hold_years = (snapshot.date - entry.date).days / 365.25
        score_drop = snapshot.score < 60
        max_hold   = hold_years >= 2.0
        if (score_drop or max_hold) and price is not None → record trade, exit
        else if exit triggered but price is None → hold (logged as warning)

if position still open at end:
    if last snapshot is not entry snapshot and price available → end_of_simulation trade
    else → no trade recorded (logged in trace)
```

### CAGR (Calendar-Period)

```
equity_curve = [1.0]
for each trade return r:
    equity_curve.append(equity_curve[-1] × (1 + r))

total_years = (end_date − start_date).days / 365.25
CAGR = (equity_curve[-1])^(1 / total_years) − 1
```

Using the full simulation period (not trading time) ensures the metric is
comparable to a buy-and-hold benchmark over the same window.  Idle cash periods
drag down the CAGR, which is the correct behaviour.

Returns `None` when:
- No trades recorded
- Period is ≤ 0 or < 1 month (≈ 0.083 years)

### Max Drawdown (Per-Trade Equity Curve)

```
peak = equity_curve[0]
max_dd = 0.0
for v in equity_curve:
    peak = max(peak, v)
    dd = (peak − v) / peak
    max_dd = max(max_dd, dd)
```

**Limitation:** only captures drawdown between trade endpoints, not intra-trade.

### Annualized Trade Return

```
annualized_return = (exit_price / entry_price)^(1 / hold_years) − 1
```

Returns `None` if `hold_years < 1/12` (too short to be meaningful).

### Benchmark CAGR

```
start_price = nearest price ≤ start_date in benchmark_prices
end_price   = nearest price ≤ end_date   in benchmark_prices
CAGR_bm = (end_price / start_price)^(1 / years) − 1
alpha   = strategy_CAGR − CAGR_bm
```

Price lookup falls back to the earliest available date if no price precedes the target.

### Structural Leakage Audit

Three violation categories:

| Category | Condition | Consequence |
|----------|-----------|-------------|
| Missing date | `as_of_date is None` | Cannot verify isolation — snapshot skipped in simulation |
| Out-of-order | `as_of_date < previous.as_of_date` | Temporal ordering violated |
| Duplicate date | Two snapshots share a date | Ambiguous point-in-time state |

The engine sorts snapshots before simulation, so out-of-order input does not crash
the run — but the violation is still recorded because out-of-order input is a data
integrity signal.

---

## Leakage Prevention Contract

The engine cannot verify that upstream data sources (yfinance, news APIs, macro
feeds) were queried with point-in-time constraints.  The full contract is:

| Layer | Responsibility | What engine checks |
|-------|---------------|-------------------|
| Caller | Construct snapshots with only as_of_date data | Cannot verify |
| Engine | Replay stored decisions; never re-query data | Structural audit |
| Audit | Check chronological order, no Nones, no duplicates | Yes |
| Price sources | No survivorship bias in price data | Cannot verify |

**The most common real-world leakage vectors (not caught by this audit):**

1. yfinance returns adjusted prices that reflect subsequent stock splits
2. Earnings revisions retroactively change reported fundamentals
3. Sector/company reclassifications change macro impact tables
4. Index composition changes affect benchmark comparisons

---

## What Is Not in This Module

| Feature | Reason Not Included |
|---------|---------------------|
| Multi-ticker portfolio | Requires correlation, allocation, and rebalancing logic |
| Transaction costs (commissions, spread) | Requires broker model — would add assumptions |
| Stop-loss rules | Requires intra-period price data not present in snapshots |
| Daily mark-to-market | Snapshots are point-in-time, not daily bars |
| Intra-trade drawdown | Same reason as daily mark-to-market |
| Random portfolio baseline | `system.md` specifies this; not yet implemented |
| Position sizing by confidence | Module does not validate this assumption empirically |
| Survivorship bias correction | Requires a delisted-ticker registry (external data) |
| Out-of-sample split | Requires the caller to partition data before building snapshots |

---

## Logging

Every `run()` call logs two structured JSON records to the system log:

```json
// Entry
{
  "module": "backtest.engine",
  "event": "input_received",
  "payload": { "ticker": "AAPL", "snapshot_count": 24, "benchmark_label": "SPY" }
}

// Exit
{
  "module": "backtest.engine",
  "event": "result_produced",
  "payload": {
    "ticker": "AAPL",
    "start_date": "2020-01-01",
    "end_date": "2024-01-01",
    "total_trades": 3,
    "win_rate": 0.667,
    "cagr": 0.072,
    "max_drawdown": 0.12,
    "leakage_passed": true,
    "benchmark_alpha": -0.023
  }
}

// Warning (if leakage violations found)
{
  "module": "backtest.engine",
  "event": "leakage_audit_violation",
  "payload": { "violations": ["AAPL: as_of_date is None — cannot verify data isolation"] }
}
```

---

## Critique and Limitations

### As a Skeptical Quant Researcher

**1. The leakage audit is structural, not semantic.**  
Checking chronological order and non-null dates does not prevent the most common
real-world leakage: using fundamentals that were revised after the as_of_date.
yfinance regularly corrects historical financial statements.  A system with high
`leakage_audit.passed` may still backtest on forward-revised data.

**2. CAGR over few trades is fragile.**  
With 2–5 trades over a multi-year window, CAGR is sensitive to the timing of a
single trade.  A BUY that coincides with a market crash will dominate the metric.
No confidence interval or bootstrap estimate is provided.

**3. Volatility from per-trade returns is not standard.**  
Industry-standard volatility is annualized daily return standard deviation
(σ × √252).  This module computes std of trade returns (different duration,
different frequency).  Comparing this "volatility" to market vol metrics is
misleading.

**4. Win rate ignores magnitude.**  
A strategy with three 2% wins and one 40% loss has a 75% win rate.  The metric
does not distinguish this from three 20% wins and one 2% loss.  Always read
win rate alongside avg_return_pct.

**5. Max drawdown is understated.**  
Intra-trade drawdowns are invisible.  A stock that dropped 35% and recovered to
+10% by exit will show 0% drawdown on the equity curve, even though the actual
experienced loss was 35%.

**6. No transaction costs.**  
No commissions, spread, or market impact are modeled.  Returns are overstated
relative to any real trading implementation.

**7. Calendar-period CAGR penalizes idle time.**  
A strategy that makes one excellent trade per year and holds cash otherwise will
show a low CAGR because the denominator is the full period.  This is technically
correct (opportunity cost of cash is real) but may obscure the quality of
individual trade selection.

---

### As a Risk Manager

**8. No stop-loss.**  
The system's only exit triggers are score drop and max hold.  In a sharp market
decline (2008, March 2020), a stock can fall 40-60% before a monthly/quarterly
score update catches it.  There is no price-based safety net.

**9. 100% portfolio concentration per trade.**  
The equity curve assumes each trade is the entire portfolio.  Sequential trades
compound, so a -40% trade followed by a +50% trade leaves the portfolio at 0.90
(not 1.10).  Real portfolios spread risk across multiple positions.

**10. End-of-simulation exits may lock in temporary losses.**  
If the simulation ends during a drawdown that would have recovered, the trade
record captures the unrealized loss as final return.  Backtest results are
sensitive to the chosen end date.

**11. Missing prices hold position silently.**  
When an exit is triggered but no price is available, the position continues.  This
is logged in the trace but does not block the run.  In production, missing prices
on an exit date require active intervention, not silent continuation.

**12. Confidence does not affect risk exposure.**  
A BUY with confidence 0.30 is treated identically to a BUY with confidence 0.90.
A risk-aware system would size positions proportionally to confidence.

---

### As a Hedge Fund Auditor

**13. Snapshot mutability breaks audit trail integrity.**  
`HistoricalSnapshot` is a regular (mutable) dataclass.  A caller could modify
snapshot fields after construction and before passing to `run()`, or between
runs.  Frozen dataclasses would provide a stronger immutability guarantee.

**14. No snapshot versioning.**  
Two calls to `run()` with "the same" snapshots may produce different results if
the underlying data source (yfinance) has corrected historical values.  There is
no hash or checksum on snapshot content.

**15. Benchmark prices have no provenance check.**  
The benchmark price dict is accepted without validation.  A caller could
accidentally pass future benchmark prices for the start date, which would
inflate the benchmark CAGR and understate alpha.

**16. No random portfolio baseline.**  
`system.md` requires comparison to a "random portfolio."  Only a single external
benchmark (SPY) is implemented.  Without a random baseline, it is impossible to
determine whether the system outperforms luck.

**17. No out-of-sample partition.**  
The system parameters (score thresholds, keyword lexicons, gate thresholds) were
set by the system designers while observing the same historical period.  All
results should be treated as in-sample until a held-out test period is evaluated.

---

## Improvements Applied (vs First Draft Critique)

| Critique | Response |
|----------|----------|
| Leakage is silent | `LeakageAudit` with 3 violation categories + warning log |
| No audit trail | Full `reasoning_trace` with timestamped steps |
| No confidence tracking | `confidence_evolution` series per snapshot |
| No decision timeline | `decisions_over_time` series per snapshot |
| Exit reason hidden | `exit_reason` field on every `TradeRecord` |
| Missing price crash | Position held, logged in trace — never corrupts trade |
| CAGR vs benchmark time mismatch | Both use calendar period (start_date → end_date) |
| No summary | 4-line `notes` field: trades, metrics, alpha, audit |
| Order-sensitive sorting | Engine sorts before simulation; out-of-order still audited |
| Mutable snapshots | Documented as known limitation |
| No data provenance | Explicitly documented in leakage contract table |
