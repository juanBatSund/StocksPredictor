# Architecture: Investment Decision System v1

## Overview

A transparent, deterministic system for identifying long-term (1–5 year) stock investment opportunities. Every output is explainable. Same input always produces the same output. Backtesting enforces strict no-lookahead rules.

Pipeline:

```
GLOBAL EVENTS → SECTOR IMPACT → FUNDAMENTALS → VALUATION → SENTIMENT → DECISION → BACKTEST
```

---

## Folder Structure

```
stocks_predictor/
├── src/
│   ├── data/
│   │   ├── __init__.py
│   │   ├── fetcher.py          # Raw data from APIs (yfinance, financial APIs)
│   │   ├── cache.py            # Local disk cache with TTL to avoid repeat fetches
│   │   ├── models.py           # Pydantic/dataclass schemas: StockData, MacroEvent
│   │   └── macro.py            # Macro/geopolitical event ingestion
│   │
│   ├── fundamentals/
│   │   ├── __init__.py
│   │   ├── quality.py          # ROE, Debt/Equity, FCF → quality sub-score
│   │   ├── growth.py           # 5Y revenue & earnings growth → growth sub-score
│   │   ├── dividend.py         # Yield, payout ratio, stability → dividend sub-score
│   │   └── scorer.py           # Aggregates: quality×0.40 + growth×0.25 + dividend×0.20
│   │
│   ├── valuation/
│   │   ├── __init__.py
│   │   ├── pe_analysis.py      # P/E vs 5-year average
│   │   ├── yield_analysis.py   # Dividend yield vs historical average
│   │   └── scorer.py           # Returns: undervalued | fair | overvalued + sub-score ×0.15
│   │
│   ├── sentiment/
│   │   ├── __init__.py
│   │   ├── news.py             # News fetch + NLP scoring → float in [-1, +1]
│   │   ├── macro_events.py     # War/rates/inflation → sector impact mapping
│   │   └── scorer.py           # Combines news + macro; detects trend direction
│   │
│   ├── decision/
│   │   ├── __init__.py
│   │   ├── aggregator.py       # Sums all weighted scores → total 0–100
│   │   ├── engine.py           # BUY / WATCH / AVOID rules applied to aggregated output
│   │   └── report.py           # Renders human-readable StockReport with full breakdown
│   │
│   ├── backtest/
│   │   ├── __init__.py
│   │   ├── simulator.py        # Time-stepped replay; enforces no lookahead (point-in-time data)
│   │   ├── portfolio.py        # Tracks holdings, entry dates, exit conditions
│   │   ├── benchmark.py        # Runs SPY and random portfolio in parallel
│   │   └── metrics.py          # CAGR, max drawdown, win rate calculations
│   │
│   └── logging/
│       ├── __init__.py
│       └── logger.py           # Structured JSON logger: inputs, calculations, decisions, model_version
│
├── tests/
│   ├── fixtures/               # Static test data (frozen API responses, mock fundamentals)
│   ├── test_data/
│   │   ├── test_fetcher.py
│   │   └── test_cache.py
│   ├── test_fundamentals/
│   │   ├── test_quality.py
│   │   ├── test_growth.py
│   │   ├── test_dividend.py
│   │   └── test_scorer.py
│   ├── test_valuation/
│   │   ├── test_pe_analysis.py
│   │   └── test_scorer.py
│   ├── test_sentiment/
│   │   ├── test_news.py
│   │   └── test_scorer.py
│   ├── test_decision/
│   │   ├── test_aggregator.py
│   │   ├── test_engine.py
│   │   └── test_report.py
│   └── test_backtest/
│       ├── test_simulator.py
│       ├── test_benchmark.py
│       └── test_metrics.py
│
├── config/
│   ├── settings.py             # Weights, thresholds, API keys, cache TTL
│   └── model_version.py        # Semantic version string logged with every run
│
├── logs/                       # Runtime log output (gitignored)
├── cache/                      # Fetched data cache (gitignored)
├── main.py                     # CLI entry: accepts ticker list, date range, mode (analyze|backtest)
├── requirements.txt
└── pyproject.toml
```

---

## File Responsibilities

| File | Single Responsibility |
|---|---|
| `data/fetcher.py` | Calls external APIs; returns raw dicts; raises on missing data |
| `data/cache.py` | Wraps fetcher with TTL-based disk cache; ensures reproducibility |
| `data/models.py` | Defines `StockData`, `MacroEvent`, `SentimentResult` schemas |
| `data/macro.py` | Maps current events to sector polarity (e.g., war → defense +) |
| `fundamentals/quality.py` | Scores ROE, D/E, FCF; each metric returns 0–100 |
| `fundamentals/growth.py` | Scores 5Y revenue and earnings trend |
| `fundamentals/dividend.py` | Scores yield, payout ratio, growth streak |
| `fundamentals/scorer.py` | Weighted sum of quality/growth/dividend sub-scores |
| `valuation/pe_analysis.py` | Compares current P/E to 5Y trailing average |
| `valuation/yield_analysis.py` | Compares current yield to historical mean |
| `valuation/scorer.py` | Returns `ValuationResult(status, sub_score)` |
| `sentiment/news.py` | Fetches headlines, runs NLP, returns float in [-1, +1] |
| `sentiment/macro_events.py` | Translates macro events to sector sentiment deltas |
| `sentiment/scorer.py` | Merges news + macro; flags negative-improving trend |
| `decision/aggregator.py` | Single function: all module outputs → `total_score: float` |
| `decision/engine.py` | Applies BUY/WATCH/AVOID rules deterministically |
| `decision/report.py` | Formats `StockReport` with all fields required by spec |
| `backtest/simulator.py` | Iterates time steps; calls the full pipeline per step with point-in-time data |
| `backtest/portfolio.py` | Tracks entry/exit per ticker; enforces 1–2yr or score-drop-below-60 exit |
| `backtest/benchmark.py` | Runs SPY buy-and-hold and random-equal-weight portfolio |
| `backtest/metrics.py` | Pure functions: `cagr()`, `max_drawdown()`, `win_rate()` |
| `logging/logger.py` | Emits structured JSON events with `model_version`, `timestamp`, `module`, `payload` |
| `config/settings.py` | Single source of truth for all weights, thresholds, API endpoints |

---

## Data Flow

```
main.py (ticker list, date range, mode)
    │
    ▼
data/fetcher.py ──→ data/cache.py          [raw financials per ticker, per point-in-time]
    │
    ▼
data/models.py                              [StockData validated schema]
    │
    ├──→ fundamentals/quality.py  ─┐
    ├──→ fundamentals/growth.py   ─┼──→ fundamentals/scorer.py   [fundamental_score: 0–85]
    ├──→ fundamentals/dividend.py ─┘
    │
    ├──→ valuation/pe_analysis.py   ─┐
    ├──→ valuation/yield_analysis.py ┼──→ valuation/scorer.py    [valuation_result: status + 0–15]
    │
    ├──→ sentiment/news.py         ─┐
    ├──→ sentiment/macro_events.py  ┼──→ sentiment/scorer.py     [sentiment: -1..+1, trend]
    │
    ▼
decision/aggregator.py                      [total_score: 0–100]
    │
    ▼
decision/engine.py                          [decision: BUY | WATCH | AVOID]
    │
    ▼
decision/report.py                          [StockReport: all fields per spec]
    │
    ├──[mode=analyze]──→ stdout / JSON file
    │
    └──[mode=backtest]──→ backtest/simulator.py
                              │
                              ├──→ backtest/portfolio.py    [holdings state]
                              ├──→ backtest/benchmark.py    [SPY + random]
                              └──→ backtest/metrics.py      [CAGR, drawdown, win rate]
                                        │
                                        ▼
                                   final benchmark report

logging/logger.py  ←──────── injects into every module boundary
```

---

## Scoring System

| Component | Weight | Score Range |
|---|---|---|
| Quality (ROE, D/E, FCF) | 40% | 0–100 |
| Growth (5Y revenue + earnings) | 25% | 0–100 |
| Dividend (yield, payout, stability) | 20% | 0–100 |
| Valuation (P/E + yield vs historical) | 15% | 0–100 |
| **Total** | 100% | **0–100** |

### Decision Rules

| Decision | Conditions |
|---|---|
| BUY | Score > 75 AND valuation = undervalued AND sentiment = negative-but-improving |
| WATCH | Score 60–75 |
| AVOID | Score < 60 |

### Sentiment Scale

| Range | Interpretation |
|---|---|
| Negative and improving | Potential opportunity |
| Neutral | No signal |
| Positive extreme | Possible overpricing |

---

## Backtesting Rules

- **Entry:** BUY condition met at time T
- **Exit:** 1–2 years after entry OR total score drops below 60
- **No lookahead:** `cache.py` accepts `as_of_date`; only data available before that date is returned
- **Benchmarks:** SPY buy-and-hold, random equal-weight portfolio
- **Metrics:** CAGR, max drawdown, win rate

---

## Key Architectural Decisions

**1. Point-in-time isolation in backtest.**
`simulator.py` passes an `as_of_date` to `cache.py` on every step. The cache layer only returns data available before that date. This is the single enforcement point against lookahead bias.

**2. Determinism via config.**
All weights and thresholds live exclusively in `config/settings.py`. No magic numbers in module code. Same config + same cached data = identical output, every time.

**3. Typed module contracts.**
Every scorer returns a typed result object (dataclass), not a bare float. This lets `aggregator.py` validate inputs and prevents silent score composition errors.

**4. Logging at module boundaries, not inside logic.**
`logger.py` is called by orchestrators (`aggregator.py`, `simulator.py`), not inside scoring functions. Keeps business logic pure and independently testable.

**5. Tests use frozen fixtures.**
`tests/fixtures/` holds static, versioned API responses. No live API calls in the test suite — tests are fast, deterministic, and offline-capable.

---

## Output Format (per stock)

Every `StockReport` must include:

- Total score (0–100)
- Score breakdown by component
- Valuation status (undervalued / fair / overvalued)
- Sentiment score (-1 to +1) and trend direction
- Macro context summary
- Final decision (BUY / WATCH / AVOID)
- Human-readable explanation

---

## Logging Schema

Every log event emitted by `logging/logger.py` includes:

```json
{
  "timestamp": "ISO-8601",
  "model_version": "1.0.0",
  "module": "fundamentals.scorer",
  "event": "score_calculated",
  "payload": { ... }
}
```

Fields logged per run: inputs, intermediate calculations, final decisions, model version.
