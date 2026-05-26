# Valuation Scoring Module

## What it does

Takes a stock's current pricing data and asks:
**"Is this stock cheap, fairly priced, or expensive right now — compared to its own history?"**

It scores that question using up to two signals:

1. **P/E ratio** — is the stock's price-to-earnings multiple higher or lower than its own 5-year average?
2. **Dividend yield** — is the current yield higher or lower than the stock's own historical average? (A higher yield means the price has fallen, which is an undervalued signal.)

Each signal scores 0–100. They combine into a single `total` (0–100) and a `status`: **undervalued**, **fair**, **overvalued**, or **unknown**.

The module also produces a signed **% deviation** for each signal — a concrete number that tells you *by how much* the stock deviates from its historical norm.

This module does **not** fetch data. It receives a `Fundamentals` object and a `MarketProfile` and returns a `ValuationScore`.

---

## Files

```
src/
└── valuation/
    └── scorer.py    — both P/E and yield scoring → ValuationScore

tests/
└── test_valuation/
    └── test_scorer.py    — 45 tests
```

---

## Inputs

The module reads two groups of fields from `Fundamentals`:

| Field | Type | Used for |
|---|---|---|
| `pe_ratio` | `Optional[float]` | Current P/E (e.g. `30.4`) |
| `pe_5y_avg` | `Optional[float]` | Stock's own 5-year average P/E. Falls back to `market.typical_pe` when absent |
| `dividend_yield` | `Optional[float]` | Current yield, e.g. `0.035` = 3.5% |
| `dividend_yield_5y_avg` | `Optional[float]` | Stock's own 5-year average yield. **No market fallback** — if absent, yield is not scored |

It also receives a `MarketProfile` (from `config/markets.py`), used only as a P/E fallback when `pe_5y_avg` is missing.

---

## Signal 1: P/E ratio vs historical average

**ratio** = `pe_ratio` ÷ `pe_5y_avg`

A ratio below 1.0 means the stock's P/E is lower than its historical norm — it's trading cheaper than usual. A ratio above 1.0 means the opposite.

| Ratio | Score | Status |
|---|---|---|
| P/E missing | 50 (neutral) | unknown |
| avg ≤ 0 | 50 (neutral) | unknown |
| ≤ 0.70 | 100 | undervalued |
| 0.70 → 0.85 | 100 → 80 | undervalued |
| 0.85 → 1.00 | 80 → 60 | fair |
| 1.00 → 1.15 | 60 → 40 | fair |
| 1.15 → 1.30 | 40 → 20 | overvalued |
| > 1.30 | 0 | overvalued |

All transitions are linear interpolations — no hard cliffs between bands.

**P/E fallback.** When `pe_5y_avg` is absent (common for stocks on non-US exchanges like Sweden's `.ST`), the module uses `market.typical_pe` (e.g. US = 20, SE = 16) as the comparison baseline. The note will say `"market avg X"` instead of `"5Y avg X"` so you know a fallback was used.

**% deviation** = `(pe_ratio − avg) / avg × 100`
- Negative → stock is cheaper than its average (undervalued direction)
- Positive → stock is more expensive than its average (overvalued direction)

---

## Signal 2: Dividend yield vs historical average

**ratio** = `dividend_yield` ÷ `dividend_yield_5y_avg`

Unlike P/E, a *higher* yield vs historical is an undervalued signal: when a stock's price falls, its yield rises. So a ratio above 1.0 is the cheap direction here.

| Ratio | Score | Status |
|---|---|---|
| yield missing | 50 (neutral) | — |
| no 5Y yield history | 50 (neutral) | — |
| ≥ 1.30 | 100 | undervalued |
| 1.15 → 1.30 | 80 → 100 | undervalued |
| 1.00 → 1.15 | 60 → 80 | fair |
| 0.85 → 1.00 | 40 → 60 | fair |
| 0.70 → 0.85 | 20 → 40 | overvalued |
| < 0.70 | 0 | overvalued |

**Important: no market fallback for yield.** P/E ratios are broadly comparable across companies in the same market, so a market average P/E is a reasonable substitute when stock history is missing. Dividend yields are not — a 3.5% yield is normal for a utility and unusual for a growth tech stock. Comparing any stock's current yield against the market average would give meaningless results. The yield signal is only scored when the stock's own 5-year yield history (`dividend_yield_5y_avg`) is available.

**% deviation** = `(dividend_yield − avg) / avg × 100`
- Positive → yield is above historical average (price has fallen → undervalued direction)
- Negative → yield is below historical average (price has risen → overvalued direction)

---

## How the two signals combine

The module uses **dynamic weighting** based on which signals are actually present and meaningful.

| Situation | Formula | Rationale |
|---|---|---|
| Both P/E and yield real | `pe_score × 0.60 + div_score × 0.40` | Two signals, weighted 60/40 |
| P/E only | `total = pe_score` | Yield history absent, don't dilute |
| Yield only | `total = div_score` | P/E missing, don't dilute |
| Neither real | `total = 50` (neutral) | Nothing to compare against |

A signal counts as "real" only if the current value is present *and* the comparison baseline is valid (> 0). If only one signal is real, it carries the full 100% weight rather than being averaged with a neutral placeholder — that would artificially pull the score toward 50 and mask a strong signal.

---

## Status thresholds

Once the composite total is computed:

| Total | Status |
|---|---|
| ≥ 80 | `undervalued` |
| 40 – 79 | `fair` |
| < 40 | `overvalued` |
| Neither signal real | `unknown` |

The `status` field is used by the decision engine. The BUY rule requires `status == "undervalued"`.

---

## Result object: `ValuationScore`

| Field | Type | Description |
|---|---|---|
| `total` | `float` | 0–100 composite score |
| `pe_score` | `float` | P/E component score, 0–100 |
| `dividend_score` | `float` | Yield component score, 0–100 |
| `status` | `str` | `"undervalued"` / `"fair"` / `"overvalued"` / `"unknown"` |
| `pe_deviation_pct` | `Optional[float]` | Signed %, negative = cheaper than average. `None` if P/E or avg missing |
| `dividend_deviation_pct` | `Optional[float]` | Signed %, positive = yield above historical = cheaper. `None` if either missing |
| `notes` | `list[str]` | Always exactly 2 entries: `[pe_note, yield_note]` |

The `notes` list is what makes the score human-readable. Each note is a single line that shows the raw numbers, the comparison, the deviation, and the score — e.g.:
```
"P/E 30.4 vs 5Y avg 28.1 (+8.2%) → 49.1"
"Dividend yield missing — neutral 50"
```

---

## Examples

### Example 1: P/E only — AAPL

AAPL has a dividend yield but no `dividend_yield_5y_avg` stored, so only the P/E signal runs.

**Input:**
```
pe_ratio         = 30.4
pe_5y_avg        = 28.1
dividend_yield   = 0.0051  (0.51%)
dividend_yield_5y_avg = None
```

**Calculation:**
```
ratio            = 30.4 / 28.1 = 1.082
pe_score         = lerp(1.082, 1.00, 1.15, 60, 40) = 49.1
pe_deviation     = (30.4 − 28.1) / 28.1 × 100 = +8.2%

dividend_yield_5y_avg is None → div_score = 50 (neutral), div_real = False

total            = pe_score = 49.1   (div excluded — no history)
status           = fair  (40 ≤ 49.1 < 80)
```

**Output:**
```
total              = 49.07
pe_score           = 49.07
dividend_score     = 50.00
status             = "fair"
pe_deviation_pct   = +8.2   (P/E is 8.2% above its 5-year average)
dividend_deviation = None
notes[0]           = "P/E 30.4 vs 5Y avg 28.1 (+8.2%) → 49.1"
notes[1]           = "No yield history — neutral 50"
```

---

### Example 2: Both signals — dividend stock trading at a discount

A utility-style stock where both P/E and yield history are available.

**Input:**
```
pe_ratio              = 16.0
pe_5y_avg             = 20.0
dividend_yield        = 0.040  (4.0%)
dividend_yield_5y_avg = 0.030  (3.0%)
```

**Calculation:**
```
P/E:
  ratio        = 16.0 / 20.0 = 0.80
  pe_score     = lerp(0.80, 0.70, 0.85, 100, 80) = 86.7
  pe_deviation = (16 − 20) / 20 × 100 = −20.0%   ← cheaper than average

Yield:
  ratio        = 0.04 / 0.03 = 1.333
  div_score    = 100.0  (ratio ≥ 1.30)
  div_deviation= (0.04 − 0.03) / 0.03 × 100 = +33.3%  ← yield above historical

Composite (both real):
  total = 86.7 × 0.60 + 100.0 × 0.40 = 52.0 + 40.0 = 92.0
  status = undervalued  (92.0 ≥ 80)
```

**Output:**
```
total                  = 92.0
pe_score               = 86.67
dividend_score         = 100.0
status                 = "undervalued"
pe_deviation_pct       = −20.0   (P/E 20% below historical)
dividend_deviation_pct = +33.3   (yield 33% above historical)
notes[0]               = "P/E 16.0 vs 5Y avg 20.0 (−20.0%) → 86.7"
notes[1]               = "Yield 4.00% vs 5Y avg 3.00% (+33.3%) → 100"
```

Both signals agree the stock is cheaper than usual. Both the price-to-earnings multiple has compressed and the dividend yield has risen, which typically happen together when a stock's price falls while fundamentals remain stable.

---

### Example 3: No data

```
pe_ratio = None, pe_5y_avg = None, dividend_yield = None
```

```
total    = 50.0
status   = "unknown"
notes[0] = "P/E missing — neutral 50"
notes[1] = "Dividend yield missing — neutral 50"
```

The neutral 50 means the valuation component contributes `50 × 0.15 = 7.5` to the overall fundamental score — a small penalty for the absence of pricing data, rather than a 0.

---

## Using the scorer in code

```python
from config.markets import MARKETS
from src.data.models import Fundamentals
from src.valuation.scorer import score

f = Fundamentals(
    roe=None, debt_to_equity=None, free_cash_flow=None,
    revenue_growth_5y=None, earnings_growth_5y=None,
    dividend_yield=0.04, payout_ratio=None,
    dividend_growth_streak_years=None,
    pe_ratio=16.0, pe_5y_avg=20.0,
    dividend_yield_5y_avg=0.03,
)

result = score(f, MARKETS["US"])

print(result.status)                # "undervalued"
print(result.total)                 # 92.0
print(result.pe_deviation_pct)      # -20.0
print(result.dividend_deviation_pct)# 33.3
print(result.notes[0])              # "P/E 16.0 vs 5Y avg 20.0 (-20.0%) → 86.7"
print(result.notes[1])              # "Yield 4.00% vs 5Y avg 3.00% (+33.3%) → 100"
```

The scorer is called by `src/fundamentals/scorer.py` as one of four components. Its `total` is multiplied by the valuation weight (15%) before being added to the final fundamental score.

---

## How to run the tests

```bash
python3 -m pytest tests/test_valuation/ -v
```

**Expected result: 45 passed**

No test makes a network call. All inputs are `Fundamentals` objects constructed inline.

The 45 tests are organised into seven classes:

| Class | Tests | What it covers |
|---|---|---|
| `TestValuationStatus` | 8 | P/E ratio → undervalued / fair / overvalued / unknown |
| `TestMarketTypicalPEFallback` | 5 | Market average P/E used when 5Y avg is absent; note labels |
| `TestValuationScore` | 4 | Exact score values at key P/E ratios |
| `TestPEDeviation` | 6 | Signed % deviation for P/E; `None` when inputs are missing |
| `TestDividendYieldScoring` | 8 | Yield signal bands; neutral 50 when no history available |
| `TestDividendDeviation` | 6 | Signed % deviation for yield; `None` when inputs are missing |
| `TestCompositeValuation` | 8 | Dynamic weighting; both, one, or zero real signals |

---

## Design rules

**Dynamic weighting, not fixed neutral.** When dividend yield history is absent, the yield signal is excluded entirely — not replaced with a neutral 50 that would drag the score toward the middle. A stock with a very undervalued P/E should read as undervalued even if yield history is unavailable.

**No market proxy for yield.** P/E is broadly comparable across companies (a market-wide P/E average is meaningful). Yield is not — a 3% yield is standard for a utility and unusual for a growth company. Using a market average yield as a proxy would produce misleading comparisons, so the yield signal only fires when the stock's own history is present.

**Signed deviation is the primary human signal.** The score (0–100) feeds the composite. The deviation (e.g. `−20.0%`) is what a human reads to understand why. A reader should be able to look at `pe_deviation_pct = −20.0` and immediately understand "the stock is 20% cheaper than its own historical P/E, which is why it's undervalued."

**Notes explain every number.** Each of the two notes shows the raw inputs, the historical comparison, the signed deviation, and the resulting score — e.g. `"P/E 16.0 vs 5Y avg 20.0 (−20.0%) → 86.7"`. Nothing is implicit.

**Deterministic.** No randomness, no timestamps, no network calls. Same `Fundamentals` + `MarketProfile` always produces exactly the same `ValuationScore`.

---

## What is not in this module

| Concern | Where it lives |
|---|---|
| Fetching P/E ratio and prices | `src/data/fetcher.py` |
| Computing `dividend_yield_5y_avg` | `src/data/fetcher.py` (not yet implemented — field defaults to `None`) |
| Absolute valuation (DCF, book value) | Not implemented |
| Sector-relative valuation (P/E vs sector peers) | Not implemented |
| The decision to BUY / WATCH / AVOID | `src/fundamentals/scorer.py` (decision hint), future `src/decision/` |
| The 15% weight applied to this score | `config/settings.py` → used by `src/fundamentals/scorer.py` |
