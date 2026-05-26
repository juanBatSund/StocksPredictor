# Benchmarking and Validation Module

**Location:** `src/validation/`  
**Tests:** `tests/test_validation/` (89 tests)  
**Depends on:** `src/backtest/`, `src/logging/logger.py`

---

## Purpose

Compare the strategy's performance against three baselines across train, validation,
and test periods to determine whether it adds value over passive alternatives.

**Core questions this module answers:**

1. Does the strategy outperform SPY buy-and-hold? → *alpha_vs_spy*
2. Does the strategy outperform random entry/exit on the same stock? → *alpha_vs_random*
3. Does the strategy outperform just holding the stock passively? → *alpha_vs_stock_bnh*
4. Are results consistent across periods, or is there overfitting? → *WeaknessAnalysis*
5. Are the baselines deterministically replayable? → *ReproducibilityAudit*

---

## Architecture

```
src/validation/
  splitter.py    — PeriodSplit, split_periods()
  baselines.py   — BaselineResult, buy_and_hold_baseline(), random_baseline()
  comparison.py  — StrategyMetrics, ComparisonRow, WeaknessAnalysis,
                   ReproducibilityAudit, strategy_metrics_for_period(),
                   build_comparison_row(), analyze_weaknesses()
  validator.py   — ValidationResult, validate()
```

---

## Input

```python
from src.validation.validator import validate

result = validate(
    ticker="AAPL",
    backtest=backtest_result,          # BacktestResult from backtest.engine.run()
    benchmark_prices={                 # SPY or other benchmark
        date(2018, 1, 1): 268.0,
        date(2024, 1, 1): 472.0,
        ...
    },
    period_split=None,                 # auto-split 60/20/20 if None
    random_seed=42,                    # deterministic baseline
    benchmark_label="SPY",
)
```

**Stock prices are derived from `backtest.snapshots`** — no additional price data
required for the stock itself.  This enforces the same data isolation contract as
the backtest module.

---

## Output: `ValidationResult`

```python
@dataclass
class ValidationResult:
    ticker: str
    period_split: PeriodSplit
    strategy_metrics: dict[str, StrategyMetrics]  # "train" | "validation" | "test"
    baseline_results: list[BaselineResult]         # 3 baselines × 3 periods = 9 entries
    comparison_table: list[ComparisonRow]          # one per period
    weakness_analysis: WeaknessAnalysis
    reproducibility_audit: ReproducibilityAudit
    notes: list[str]
```

### `PeriodSplit`

```python
@dataclass
class PeriodSplit:
    train_start: date;  train_end: date
    validation_start: date;  validation_end: date
    test_start: date;  test_end: date
    # Properties: train_years, validation_years, test_years, full_start, full_end
    # Method: in_period(period, date) → bool
```

### `ComparisonRow` (one per period)

```
period            | train         | validation    | test
strategy_cagr     | 0.142         | 0.112         | 0.084
spy_cagr          | 0.098         | 0.093         | 0.107
random_cagr       | 0.071         | 0.053         | 0.049
stock_bnh_cagr    | 0.118         | 0.101         | 0.093
alpha_vs_spy      | +0.044        | +0.019        | -0.023   ← underperforms
alpha_vs_random   | +0.071        | +0.059        | +0.035
alpha_vs_stock_bnh| +0.024        | +0.011        | -0.009   ← underperforms
strategy_drawdown | 0.08          | 0.05          | 0.11
strategy_win_rate | 0.75          | 0.67          | 0.50
strategy_trades   | 4             | 2             | 2
```

### `WeaknessAnalysis`

```python
@dataclass
class WeaknessAnalysis:
    underperforms_spy: bool          # test-period alpha_vs_spy < 0
    underperforms_random: bool       # test-period alpha_vs_random < 0
    underperforms_stock_bnh: bool    # test-period alpha_vs_stock_bnh < 0
    overfitting_flag: bool           # (train_cagr − test_cagr) > 5%
    low_sample_flag: bool            # total_trades < 3
    test_period_degradation: bool    # (val_cagr − test_cagr) > 3%
    notes: list[str]                 # human-readable; always ≥ 1 entry
```

### `ReproducibilityAudit`

```python
@dataclass
class ReproducibilityAudit:
    seed_used: int
    random_baseline_reproducible: bool  # two runs with same seed → identical output
    identical_time_windows: bool        # all periods non-overlapping and chronological
    violations: list[str]
    notes: list[str]
```

---

## Baselines

### 1. SPY Buy-and-Hold (external benchmark)

Buy at the nearest price ≤ period start; sell at the nearest price ≤ period end.  
One trade per period.  No transaction costs.

```
cagr = (end_price / start_price)^(1 / years) − 1
alpha_vs_spy = strategy_cagr − benchmark_cagr
```

### 2. Stock Buy-and-Hold (passive hold)

Identical algorithm, but applied to the ticker's own price series (derived from
snapshots).  Answers: "does active management add value over just holding the stock?"

### 3. Random Strategy (chance baseline)

```
rng = random.Random(seed)
for _ in range(n_trades):
    entry_date = rng.choice(available_snapshot_dates_in_period)
    exit_date  = nearest snapshot date after (entry + avg_hold_years)
    return     = (exit_price − entry_price) / entry_price
CAGR computed over full period (calendar time, not trading time)
```

`n_trades` is set to the strategy's actual trade count for that period (minimum 1).
This makes the comparison fair: both the strategy and the random baseline make the
same number of trades.

---

## Period Split Algorithm

```
total_days = (end − start).days
train_end  = start + int(total_days × train_pct) days
val_start  = train_end + 1 day
val_end    = val_start + int(total_days × val_pct) − 1 days
test_start = val_end + 1 day
test_end   = end
```

Periods are contiguous and non-overlapping.  Integer day rounding means the sum
of period lengths is ≤ total days (typically 0–2 days lost at boundaries).

---

## No-Leakage Invariants

| Invariant | How enforced |
|-----------|-------------|
| Stock prices from snapshots only | `stock_prices` dict derived from `backtest.snapshots` |
| No re-fetching or re-scoring | Validator is read-only on `BacktestResult` |
| Test data not used for thresholds | Thresholds are constants, not fitted to data |
| Identical time windows | Same `(start, end)` passed to all baselines per period |
| Deterministic baselines | `random.Random(seed)` seeded before each call |

---

## Weakness Detection Rules

| Flag | Condition | Default Threshold | Limitation |
|------|-----------|-------------------|------------|
| `overfitting_flag` | train_cagr − test_cagr > threshold | 5% | Heuristic; no p-value |
| `low_sample_flag` | total_trades < min_trades | 3 | Far below statistical minimum |
| `underperforms_spy` | test alpha_vs_spy < 0 | — | Single period; no significance test |
| `underperforms_random` | test alpha_vs_random < 0 | — | Random baseline has its own noise |
| `underperforms_stock_bnh` | test alpha_vs_stock_bnh < 0 | — | Same |
| `test_period_degradation` | val_cagr − test_cagr > threshold | 3% | Heuristic |

---

## Reproducibility Verification

Two independent calls to `random_baseline()` with the same seed are made on the
test period.  The audit passes if and only if both calls produce identical `cagr`
and `trade_count`.

```python
r1 = random_baseline(..., seed=42)
r2 = random_baseline(..., seed=42)
assert r1.cagr == r2.cagr
assert r1.trade_count == r2.trade_count
```

---

## What Is Not in This Module

| Feature | Reason Not Included |
|---------|---------------------|
| Multi-ticker portfolio | Requires correlation and allocation model |
| Sharpe ratio | Requires risk-free rate and daily return series |
| Information ratio | Requires daily benchmark series |
| Calmar ratio (return/drawdown) | Deferred; straightforward addition |
| k-fold cross-validation | Violates no-leakage rule for time series |
| Statistical significance testing | Requires minimum N >> available trades |
| Bootstrap confidence intervals | Deferred; depends on trade sample size |
| Regime detection | Requires labeled market regime data |
| Transaction cost adjustment | Would require broker model inputs |

---

## Logging

Every `validate()` call emits two structured JSON records:

```json
// Entry
{ "module": "validation.validator", "event": "input_received",
  "payload": { "ticker": "AAPL", "snapshot_count": 24, "trade_count": 5, "random_seed": 42 } }

// Exit
{ "module": "validation.validator", "event": "result_produced",
  "payload": {
    "ticker": "AAPL", "total_trades": 5,
    "test_alpha_vs_spy": -0.023,
    "overfitting": false,
    "underperforms_spy": true,
    "reproducible": true
  }
}

// Warning (if reproducibility violation)
{ "module": "validation.validator", "event": "reproducibility_violation",
  "payload": { "violations": ["..."] } }
```

---

## Critique and Limitations

### As a Skeptical Quant Researcher

**1. The 60/20/20 split is arbitrary.**  
No principled reason justifies this ratio for financial time series.  The test
period inherits the most recent market regime, which may have higher volatility,
interest-rate sensitivity, or geopolitical risk than the training period.  A single
train/test split cannot isolate regime effects.

**2. The random baseline is anchored to snapshot dates.**  
The random baseline draws entry dates from the same set of dates the strategy
evaluated.  A truly random baseline should draw from a continuous daily price
series.  Using snapshot dates means the random baseline is inadvertently limited
to the same evaluation frequency as the strategy — which may flatter the random
baseline if snapshots coincide with news-driven mispricings.

**3. Alpha is arithmetic, not risk-adjusted.**  
`alpha = strategy_cagr − benchmark_cagr` does not account for the strategy's
systematic risk (beta).  A strategy with beta > 1 will naturally show positive
arithmetic alpha in bull markets without generating any skill.  Jensen's alpha
(regression-based) or the Information Ratio would be more appropriate.

**4. Overfitting detection has no statistical test.**  
A 5% CAGR gap between train and test is a heuristic, not a p-value.  With only
3–10 trades, the noise around any CAGR estimate far exceeds 5%.  The flag may fire
on random variation and miss genuine overfitting at lower magnitudes.

**5. No bootstrap or permutation testing.**  
The key question — "could these results have occurred by chance?" — is not answered.
With fewer than ~30 trades, permutation tests would show that almost any observed
alpha is within noise bounds.

**6. CAGR is period-sensitive.**  
A backtest that ends one month before a crash will look dramatically better than one
that ends one month after.  No sensitivity analysis or rolling-end-date robustness
check is performed.

---

### As a Hedge Fund Allocator

**7. No Sharpe ratio.**  
The risk-adjusted return metric of record in institutional finance is the Sharpe
ratio (excess return / volatility).  Without a risk-free rate and daily return
series, this module cannot compute it.  Reporting only CAGR misleads because high
CAGR accompanied by high drawdown is not an acceptable investment profile.

**8. No Information Ratio.**  
The Information Ratio (IR = alpha / tracking error) measures skill per unit of
active risk taken.  An IR ≥ 0.5 is considered acceptable.  Without this metric,
there is no way to evaluate whether the alpha justifies the active exposure.

**9. Calmar Ratio absent.**  
Allocators often size positions based on Calmar Ratio (CAGR / max drawdown).
The raw drawdown is present, but the ratio is not computed or compared across
strategies.

**10. No multi-ticker aggregation.**  
Real fund validation compares a portfolio of signals, not individual tickers in
isolation.  A strategy that generates positive alpha on one ticker but negative on
five others is net-negative — this module cannot measure that.

**11. No capacity or liquidity analysis.**  
Backtested returns are always higher at smaller scale.  Without market-cap or
volume constraints, results cannot be extrapolated to any real position size.

---

### As a Risk Manager

**12. Weakness flags are advisory, not blocking.**  
`overfitting_flag=True` and `underperforms_spy=True` appear in the output but do not
prevent the system from issuing a BUY on the same ticker.  There is no feedback
loop from validation findings to decision thresholds.

**13. Low sample threshold is too low.**  
`min_trades=3` as the default for the `low_sample_flag` is far below any reasonable
statistical minimum.  For CAGR estimates to be within ±5% of the true value at 80%
confidence requires ~25+ independent trades.  Three trades should always set the
flag.

**14. Random baseline noise is unquantified.**  
The random baseline output varies with the number of available snapshot dates and
the hold duration.  No confidence interval around the random baseline CAGR is
provided.  A single draw from `random.Random(seed)` is not a distribution — it is
one sample.  The `alpha_vs_random` could be positive or negative with equal
probability just from the luck of that particular random sequence.

**15. No tail risk analysis.**  
Max drawdown is the peak-to-trough on the per-trade equity curve, not the
worst-case tail loss.  Conditional Value at Risk (CVaR) or Worst Expected Shortfall
would provide a better estimate of catastrophic downside risk.

**16. End-of-period boundary effects.**  
A trade entered in the train period but exiting in the validation period is
attributed to train.  This means train metrics incorporate returns generated
during validation dates — a subtle form of boundary leakage in the attribution
model (not in the decision itself, but in how performance is credited).

---

## Improvements Applied (vs First Draft Critique)

| Issue | Response |
|-------|----------|
| Random baseline non-deterministic | `random.Random(seed)` seeded per call; reproducibility audit verifies two-run identity |
| No out-of-sample isolation | Explicit train/validation/test split with non-overlapping windows |
| Baselines use different periods | All baselines share identical `(start, end)` per period — verified in audit |
| No weakness summary | `WeaknessAnalysis` with 6 flags and human-readable notes |
| Overfitting undetected | `overfitting_flag` with configurable threshold (documented as heuristic) |
| No sample-size guard | `low_sample_flag` with configurable `min_trades` |
| Degradation across periods invisible | `test_period_degradation` flag |
| Alpha arithmetic vs risk-adjusted | Documented as known limitation; `alpha_vs_spy`, `alpha_vs_random`, `alpha_vs_stock_bnh` all present |
| No per-period confidence tracking | `avg_confidence` field in `StrategyMetrics` per period |
| Stock prices hard to provide | Derived automatically from `backtest.snapshots` — caller provides only benchmark prices |
