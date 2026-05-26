# Fundamentals Scoring Module

## What it does

Takes a stock's financial data and produces a single score from 0 to 100 that answers:
**"How good is this company on paper?"**

It breaks that question into four components — quality, growth, dividend, and valuation — scores each one independently, then combines them using fixed weights into a final score. Every number is explainable: the module tells you exactly why a stock scored what it did.

This module does **not** fetch data. It receives a `Fundamentals` object (produced by the data module) and returns a `FundamentalResult`.

---

## Files

```
src/
├── fundamentals/
│   ├── quality.py     — ROE, Debt/Equity, Free Cash Flow (weight: 40%)
│   ├── growth.py      — 5Y revenue and earnings growth (weight: 25%)
│   ├── dividend.py    — Yield, payout ratio, streak (weight: 20%)
│   └── scorer.py      — Combines all four → FundamentalResult (0–100)
└── valuation/
    └── scorer.py      — P/E + dividend yield vs historical averages (weight: 15%)

tests/
├── test_fundamentals/
│   ├── test_quality.py    — 20 tests
│   ├── test_growth.py     — 18 tests
│   ├── test_dividend.py   — 20 tests
│   └── test_scorer.py     — 17 integration tests
└── test_valuation/
    └── test_scorer.py     — 45 tests
```

---

## Scoring weights

These come directly from `system.md` and live in `config/settings.py`.

| Component | Weight | What it measures |
|---|---|---|
| Quality | **40%** | Is this a financially healthy company? |
| Growth | **25%** | Is the company getting bigger over time? |
| Dividend | **20%** | Does it pay a reliable, well-sized dividend? |
| Valuation | **15%** | Is the stock cheap or expensive right now? |

The total is always between 0 and 100:
```
total = quality × 0.40 + growth × 0.25 + dividend × 0.20 + valuation × 0.15
```

---

## Decision thresholds

| Score | Decision hint |
|---|---|
| > 75 | BUY candidate |
| 60 – 75 | WATCH |
| < 60 | AVOID |

These match the BUY/WATCH/AVOID rules in `system.md`. The hint is advisory — the `decision` module applies the full set of rules before making a final call.

---

## How each component is scored

Every metric uses linear interpolation between breakpoints. If a field is `None` (missing from Yahoo Finance), it scores 0 — the system penalises unknown data rather than ignoring it.

---

### Quality (`src/fundamentals/quality.py`)

Three metrics, each scored 0–100, then averaged.

**ROE — Return on Equity**
Measures how efficiently management uses shareholder money.
Threshold from `system.md`: ROE > 12%.

| ROE | Score |
|---|---|
| Missing or ≤ 0% | 0 |
| 0% → 12% | 0 → 50 (below threshold, partial credit) |
| 12% → 25% | 50 → 100 (above threshold) |
| > 25% | 100 (excellent) |

**Debt/Equity — Leverage ratio**
Lower is better. Threshold from `system.md`: D/E < 1.0.

| D/E | Score |
|---|---|
| Missing or negative equity | 0 |
| 0.0 → 0.5 | 100 → 75 (low leverage) |
| 0.5 → 1.0 | 75 → 50 (acceptable) |
| 1.0 → 2.0 | 50 → 0 (above threshold) |
| ≥ 2.0 | 0 (very high leverage) |

**Free Cash Flow**
Binary: positive cash flow passes, negative fails. Threshold from `system.md`: positive FCF.

| FCF | Score |
|---|---|
| Missing or ≤ 0 | 0 |
| > 0 | 100 |

**Quality total** = (ROE score + D/E score + FCF score) / 3

---

### Growth (`src/fundamentals/growth.py`)

Two metrics, each scored 0–100, then averaged. Both use the same scale.

**5Y Revenue Growth** and **5Y Earnings Growth**
Threshold from `system.md`: positive growth over 5 years.

| Growth rate | Score |
|---|---|
| Missing or ≤ 0% | 0 |
| 0% → 5% | 0 → 50 (low positive) |
| 5% → 15% | 50 → 75 (moderate) |
| 15% → 30% | 75 → 100 (strong) |
| > 30% | 100 (capped) |

**Growth total** = (revenue score + earnings score) / 2

---

### Dividend (`src/fundamentals/dividend.py`)

Three metrics, each scored 0–100, then averaged.

**Dividend Yield**
Sweet spot from `system.md`: 2–5%. Peaks at the midpoint (3.5%). Penalises very high yields as a possible dividend trap.

| Yield | Score |
|---|---|
| Missing or 0% | 0 (no dividend) |
| 0% → 2% | 0 → 75 (below minimum) |
| 2% → 3.5% | 75 → 100 (rising into sweet spot) |
| 3.5% → 5% | 100 → 75 (high end of sweet spot) |
| 5% → 8% | 75 → 25 (above max, caution) |
| > 8% | 0 (likely dividend trap) |

**Payout Ratio**
Threshold from `system.md`: payout < 60%.

| Payout | Score |
|---|---|
| Missing or 0% | 0 |
| 0% → 30% | 100 (very conservative, sustainable) |
| 30% → 60% | 100 → 50 (acceptable) |
| 60% → 100% | 50 → 0 (above threshold) |
| > 100% | 0 (paying out more than it earns — unsustainable) |

**Dividend Growth Streak**
Proxy for stability from `system.md`: "stable or growing dividend".

| Streak | Score |
|---|---|
| 0 or unknown | 0 |
| 1–4 years | 25 (short track record) |
| 5–9 years | 50 (established) |
| 10–24 years | 75 (strong history) |
| ≥ 25 years | 100 (Dividend Aristocrat) |

Yahoo Finance has no streak field, but it does expose the full payment history via `Ticker.dividends` — a time series of every individual dividend paid with its date. The data module computes the streak from this automatically (`_compute_dividend_streak` in `src/data/fetcher.py`):

1. **Group** all payments by calendar year and sum them (handles quarterly, monthly, and irregular payers equally)
2. **Drop** the current year — it is incomplete and would understate the annual total
3. **Walk backwards** year-by-year from the most recent complete year, counting consecutive pairs where `this_year >= prior_year`
4. **Stop** immediately on a decrease (cut) or a gap (suspended dividend — missing year in the series)

**Example — dividend cut in the middle:**

| Year | Annual total | vs prior year | Streak action |
|---|---|---|---|
| 2019 | $1.00 | — | — |
| 2020 | $1.20 | ↑ | — |
| 2021 | $0.80 | ↓ cut | — |
| 2022 | $1.00 | ↑ from cut level | +1 |
| 2023 | $1.10 | ↑ | +1, then stop at 2021 cut |

→ `streak = 2` — correctly counts only the clean run since the cut, not the years before it.

Returns `0` on any fetch failure (conservative, not `None`) so the scorer can always proceed.

**Dividend total** = (yield score + payout score + streak score) / 3

---

### Valuation (`src/valuation/scorer.py`)

Two signals, each scored 0–100, combined into a single `total`. See [VALUATION_MODULE.md](VALUATION_MODULE.md) for full detail.

**Signal 1 — P/E ratio vs 5-year average.**
`ratio = pe_ratio / pe_5y_avg`. Falls back to `market.typical_pe` when the stock's own 5Y average is absent.
Low ratio → undervalued (score 100). High ratio → overvalued (score 0). Missing P/E → neutral 50.

**Signal 2 — Dividend yield vs historical average.**
`ratio = dividend_yield / dividend_yield_5y_avg`. Higher yield vs historical means the price has fallen — an undervalued signal. Only fires when `dividend_yield_5y_avg` is present; no market proxy is used.

**Composite:** when both signals are real, `total = pe_score × 0.60 + div_score × 0.40`. When only one signal is real, that signal carries 100% of the weight. When neither is real, `total = 50` (neutral) and `status = "unknown"`.

**Status thresholds:** total ≥ 80 → `undervalued`; total < 40 → `overvalued`; otherwise `fair`.

The `status` field is used by the decision engine: the BUY rule requires `status == "undervalued"`.

Each signal also exposes a signed **% deviation** (`pe_deviation_pct`, `dividend_deviation_pct`) — the concrete number behind the score.

---

## Data flow

```
Fundamentals (from data module)
    │
    ├──→ quality.score(f)     → QualityScore  (total, roe, debt_to_equity, fcf, notes)
    ├──→ growth.score(f)      → GrowthScore   (total, revenue, earnings, notes)
    ├──→ dividend.score(f)    → DividendScore (total, yield_score, payout, streak, notes)
    └──→ valuation.score(f)   → ValuationScore(total, pe_score, dividend_score, status, pe_deviation_pct, dividend_deviation_pct, notes)
                │
                ▼
        fundamentals/scorer.py
                │
                ▼
        FundamentalResult
            ├── ticker
            ├── total          ← weighted sum, 0–100
            ├── quality        ← QualityScore
            ├── growth         ← GrowthScore
            ├── dividend       ← DividendScore
            ├── valuation      ← ValuationScore
            ├── decision_hint  ← BUY candidate | WATCH | AVOID
            └── breakdown()    ← full dict with weights, scores, notes per component
```

---

## Result object: `FundamentalResult`

| Field | Type | Description |
|---|---|---|
| `ticker` | `str` | e.g. `"AAPL"` |
| `total` | `float` | 0–100 weighted score |
| `quality` | `QualityScore` | sub-scores + notes |
| `growth` | `GrowthScore` | sub-scores + notes |
| `dividend` | `DividendScore` | sub-scores + notes |
| `valuation` | `ValuationScore` | P/E + yield scores, status, deviations, notes |
| `decision_hint` | `str` (property) | `"BUY candidate"` / `"WATCH"` / `"AVOID"` |
| `breakdown()` | `dict` | Full explainability dump |

---

## Example: AAPL

**Input** (`Fundamentals`):
```
roe                  = 0.17   (17%)
debt_to_equity       = 0.80
free_cash_flow       = 89,900,000,000
revenue_growth_5y    = 0.092  (9.2%)
earnings_growth_5y   = 0.11   (11%)
dividend_yield       = 0.0051 (0.51%)
payout_ratio         = 0.158  (15.8%)
dividend_growth_streak_years = 4     ← computed from Ticker.dividends history
pe_ratio             = 30.4
pe_5y_avg            = 28.1
```

**Output** (`FundamentalResult`):
```
total        = 63.22   → WATCH

quality      = 76.41   (weight 40% → contributes 30.56)
  roe              = 69.23   ROE 17% above 12% threshold
  debt_to_equity   = 60.00   D/E 0.80 acceptable
  fcf              = 100.00  FCF 89.9B positive

growth       = 62.75   (weight 25% → contributes 15.69)
  revenue          = 60.50   9.2% moderate
  earnings         = 65.00   11% moderate

dividend     = 48.04   (weight 20% → contributes 9.61)
  yield_score      = 19.13   0.51% — far below 2% minimum
  payout           = 100.00  15.8% very conservative
  streak           = 25.00   4Y streak — short track record → 25

valuation    = 49.07   (weight 15% → contributes 7.36)
  pe_score         = 49.07   P/E 30.4 vs 5Y avg 28.1 (+8.2%) → fair
  dividend_score   = 50.00   no yield history — neutral
  status           = fair
  pe_deviation     = +8.2%   (P/E is 8% above its own 5-year average)
```

**Why AAPL scores in WATCH and not BUY:**
- Its dividend yield (0.51%) is far below the 2–5% sweet spot, which is the dominant drag on the dividend component even with a clean payout ratio and a real streak.
- Its P/E is slightly above its 5Y average, giving a `fair` valuation status. BUY requires `undervalued`.

---

## Example: ideal dividend stock

**Input:**
```
roe = 0.30, debt_to_equity = 0.0, free_cash_flow = 1B
revenue_growth_5y = 0.30, earnings_growth_5y = 0.30
dividend_yield = 0.035, payout_ratio = 0.25, streak = 25 years
pe_ratio = 10.0, pe_5y_avg = 20.0          (trading at half its historical P/E)
dividend_yield_5y_avg = 0.025              (current yield 3.5% vs historical avg 2.5%)
```

**Output:**
```
total     = 100.0  → BUY candidate
quality   = 100.0
growth    = 100.0
dividend  = 100.0
valuation = 100.0  (undervalued)
```

---

## Example: using the scorer in code

```python
from src.data.cache import get
from src.fundamentals.scorer import score
from config.markets import MARKETS

# Fetch data (uses 24h cache)
stock_data = get("JNJ")

# Score it
result = score("JNJ", stock_data.fundamentals, MARKETS["US"])

print(result.total)            # e.g. 68.4
print(result.decision_hint)    # "WATCH"
print(result.valuation.status) # "undervalued" | "fair" | "overvalued"

# Full breakdown for explainability
import json
print(json.dumps(result.breakdown(), indent=2))
```

**Sample `breakdown()` output:**
```json
{
  "ticker": "JNJ",
  "total": 68.4,
  "decision_hint": "WATCH",
  "components": {
    "quality": {
      "score": 82.5,
      "weight": 0.4,
      "weighted": 33.0,
      "detail": {"roe": 90.0, "debt_to_equity": 72.5, "fcf": 85.0},
      "notes": [
        "ROE 21.3% above threshold → 90.0",
        "D/E 0.45 low leverage → 72.5",
        "FCF 18,400,000,000 positive → 100"
      ]
    },
    "growth": { ... },
    "dividend": { ... },
    "valuation": {
      "score": 75.0,
      "weight": 0.15,
      "weighted": 11.25,
      "status": "undervalued",
      "notes": ["P/E 18.2 vs avg 22.1 (ratio 0.82) — undervalued → 80.0"]
    }
  }
}
```

---

## How to run the tests

```bash
# Run all scoring tests
python3 -m pytest tests/test_fundamentals/ tests/test_valuation/ -v

# Run a single component
python3 -m pytest tests/test_fundamentals/test_quality.py -v
python3 -m pytest tests/test_fundamentals/test_growth.py -v
python3 -m pytest tests/test_fundamentals/test_dividend.py -v
python3 -m pytest tests/test_valuation/test_scorer.py -v

# Run integration tests only
python3 -m pytest tests/test_fundamentals/test_scorer.py -v
```

**Expected result: 133 passed** (88 fundamentals + 45 valuation)

No test makes a network call. All inputs are constructed inline as `Fundamentals` objects.

> The 8 streak-computation tests live in `tests/test_data/test_fetcher.py` (part of the data module), since the streak is fetched and computed there before being stored on `Fundamentals`.

---

## Design rules

**Pure functions.** `quality.py`, `growth.py`, `dividend.py`, and `valuation/scorer.py` have no side effects. They take a `Fundamentals` and return a score object. Nothing else. This makes them trivially testable and safe to call from anywhere.

**Logging only at the boundary.** `fundamentals/scorer.py` is the only place that calls the logger. It logs inputs when it starts and results when it finishes. The individual scorers know nothing about logging.

**Missing data scores 0.** Any field that is `None` scores 0 on that metric. The system does not skip or rescale around missing data — unknown information is treated as a risk.

**Deterministic.** No randomness, no timestamps, no external calls. Same `Fundamentals` input always produces exactly the same `FundamentalResult`.

**Notes explain every number.** Every scorer returns a `notes` list with one human-readable string per metric. The `breakdown()` method surfaces all of them, satisfying the system's "no black box" principle.

---

## What is not in this module

| Concern | Where it lives |
|---|---|
| Fetching financial data | `src/data/` |
| News and macro sentiment | `src/sentiment/` |
| Final BUY / WATCH / AVOID decision | `src/decision/` |
| Backtesting over time | `src/backtest/` |
