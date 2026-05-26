# Data Ingestion Module

## What it does

Fetches stock price history and fundamental financials from Yahoo Finance, stores them on disk with a 24-hour cache, and tracks macro events (wars, rate hikes, etc.) that affect sectors. Every operation is logged as structured JSON.

This module is the **entry point for all data** in the system. No other module touches Yahoo Finance directly.

---

## Files

```
src/
├── data/
│   ├── models.py     — data schemas (what data looks like)
│   ├── fetcher.py    — fetches from Yahoo Finance
│   ├── cache.py      — stores fetched data on disk; reuses if fresh
│   └── macro.py      — curated macro events; sector polarity lookup
└── logging/
    └── logger.py     — writes structured JSON logs to stdout and logs/system.log

config/
├── settings.py       — all thresholds, paths, and TTLs in one place
└── model_version.py  — version string stamped on every log line

tests/
├── fixtures/
│   ├── AAPL_raw.json     — frozen complete data (all fields present)
│   └── MISSING_raw.json  — frozen partial data (several fields null)
└── test_data/
    ├── test_fetcher.py   — 5 tests for fetcher behaviour
    └── test_cache.py     — 8 tests for cache hit, miss, staleness, roundtrip
```

---

## Data flow

```
cache.get("AAPL")
    │
    ├── cache fresh? ──yes──→ load from disk → return StockData
    │
    └── no → fetcher.fetch("AAPL")
                │
                ├── yf.Ticker("AAPL").info        → raw fundamentals dict
                ├── yf.Ticker("AAPL").history()   → price DataFrame
                │
                ├── _build_fundamentals()  → Fundamentals + missing_fields[]
                ├── _fetch_prices()        → [PriceRecord, ...]
                │
                └── StockData assembled → saved to disk → returned

logging/logger.py  ←── called at every module boundary (input + result)
```

---

## Schemas (`src/data/models.py`)

### `PriceRecord`
One row of daily OHLCV data. Frozen (immutable).

| Field | Type | Example |
|---|---|---|
| `date` | `date` | `2024-01-10` |
| `open` | `float` | `183.92` |
| `high` | `float` | `185.15` |
| `low` | `float` | `182.73` |
| `close` | `float` | `184.40` |
| `volume` | `int` | `53234100` |

---

### `Fundamentals`
All metrics used by downstream scoring modules. Frozen. Any field can be `None` if Yahoo Finance did not return it.

| Field | Type | Threshold used by system |
|---|---|---|
| `roe` | `float \| None` | Quality: must be > 12% |
| `debt_to_equity` | `float \| None` | Quality: must be < 1.0 |
| `free_cash_flow` | `float \| None` | Quality: must be positive |
| `revenue_growth_5y` | `float \| None` | Growth: must be positive |
| `earnings_growth_5y` | `float \| None` | Growth: must be positive |
| `dividend_yield` | `float \| None` | Dividend: 2–5% range |
| `payout_ratio` | `float \| None` | Dividend: must be < 60% |
| `dividend_growth_streak_years` | `int \| None` | Dividend: not from yfinance; set externally |
| `pe_ratio` | `float \| None` | Valuation: vs 5Y average |
| `pe_5y_avg` | `float \| None` | Valuation: benchmark |

---

### `MacroEvent`
A single global event and its sector impact.

| Field | Type | Example |
|---|---|---|
| `event_date` | `date` | `2022-02-24` |
| `description` | `str` | `"Russia invades Ukraine"` |
| `affected_sectors` | `list[str]` | `["defense", "energy"]` |
| `polarity` | `float` | `0.7` (positive = bullish for those sectors) |

---

### `StockData`
The top-level object returned by the cache and fetcher.

| Field | Type | Notes |
|---|---|---|
| `ticker` | `str` | e.g. `"AAPL"` |
| `fetched_at` | `datetime` | UTC timestamp of ingestion |
| `as_of_date` | `date \| None` | Set during backtest to prevent lookahead |
| `prices` | `list[PriceRecord]` | Chronological, oldest first |
| `fundamentals` | `Fundamentals` | May contain `None` fields |
| `missing_fields` | `list[str]` | Names of fields Yahoo Finance did not return |
| `latest_price` | `float \| None` | Property: `prices[-1].close` |
| `has_complete_fundamentals` | `bool` | Property: `len(missing_fields) == 0` |

---

## Module responsibilities

### `fetcher.py` — fetch from Yahoo Finance

The only file that calls `yf.Ticker`. Never call it from other modules.

**Key behaviours:**
- If `as_of_date` is set, prices after that date are dropped. This enforces no-lookahead for backtesting.
- If a fundamental field is absent or `"N/A"`, it is recorded in `missing_fields` and set to `None`. The fetch does **not** raise — partial data is valid.
- If the price history call raises an exception (network failure, bad ticker), prices return as `[]`.
- `debtToEquity` from yfinance is a percentage (e.g. `80.0`). The fetcher divides by 100 to normalise to a ratio (e.g. `0.80`).

---

### `cache.py` — disk cache with TTL

Wraps `fetcher.fetch()`. All other modules should call `cache.get()`, never `fetcher.fetch()` directly.

**Key behaviours:**
- Cache files live in `cache/` at the project root (configured in `settings.py`).
- A file is considered fresh if it was written less than 24 hours ago (`CACHE_TTL_SECONDS = 86400`).
- If stale or absent, it fetches and overwrites the file.
- Cache filename includes the `as_of_date` when set (e.g. `AAPL_2023-06-01.json`), so different backtest dates get separate files.
- `invalidate(ticker)` deletes the file, forcing a fresh fetch on the next `get()`.

---

### `macro.py` — macro events and sector polarity

A curated list of global events hardcoded in the file. Add new entries directly.

**Key behaviours:**
- `get_active_events(as_of_date)` returns only events that occurred on or before that date.
- `sector_polarity(sector, as_of_date)` sums polarity across all active events for that sector and clamps to `[-1.0, +1.0]`.
- The sentiment module uses `sector_polarity()` to adjust its score.

**Adding a new event:**
```python
MacroEvent(
    event_date=date(2025, 1, 20),
    description="US tariffs on China tech imports",
    affected_sectors=["technology", "consumer_electronics"],
    polarity=-0.5,
)
```

---

### `logger.py` — structured JSON logging

Every log line is a JSON object written to both stdout and `logs/system.log`.

**Functions:**

| Function | When to call |
|---|---|
| `log_input(module, payload)` | At the start of a function, before any computation |
| `log_result(module, payload)` | After a function completes successfully |
| `log_warning(module, message, payload)` | Missing data, unexpected but recoverable state |
| `log_error(module, message, payload)` | Exception caught; operation could not complete |

**Log line format:**
```json
{
  "timestamp": "2024-01-15T12:00:00+00:00",
  "model_version": "1.0.0",
  "level": "info",
  "module": "data.fetcher",
  "event": "result_produced",
  "payload": {
    "ticker": "AAPL",
    "price_records": 1258,
    "latest_price": 185.92,
    "missing_fields": []
  }
}
```

---

## Example: normal fetch

```python
from src.data.cache import get

data = get("AAPL")

print(data.ticker)                          # "AAPL"
print(data.latest_price)                    # 185.92
print(data.has_complete_fundamentals)       # True
print(data.fundamentals.roe)                # 0.17
print(data.fundamentals.debt_to_equity)     # 0.80
print(data.fundamentals.dividend_yield)     # 0.0051
print(len(data.prices))                     # ~1258 (5 years of daily bars)
```

---

## Example: backtest fetch (no-lookahead)

```python
from datetime import date
from src.data.cache import get

data = get("AAPL", as_of_date=date(2021, 12, 31))

# prices only go up to 2021-12-31 — future data is invisible
print(data.prices[-1].date)   # 2021-12-31
print(data.as_of_date)        # 2021-12-31
```

---

## Example: handling missing data

```python
from src.data.cache import get

data = get("NEWCO")   # a ticker with sparse financials

print(data.has_complete_fundamentals)   # False
print(data.missing_fields)              # ["returnOnEquity", "freeCashflow", "dividendYield"]
print(data.fundamentals.roe)            # None

# Downstream scorers must check for None before scoring:
if data.fundamentals.roe is not None:
    ...
```

---

## Example: macro sector polarity

```python
from datetime import date
from src.data.macro import sector_polarity, get_active_events

# What events were active in early 2023?
events = get_active_events(date(2023, 1, 1))
for e in events:
    print(e.description, e.polarity)

# Net polarity for defense sector as of that date
score = sector_polarity("defense", date(2023, 1, 1))
print(score)   # 0.7 (Russia/Ukraine event active)
```

---

## How to run the tests

```bash
# Install dependencies (first time only)
python3 -m pip install -r requirements.txt

# Run all data module tests
python3 -m pytest tests/test_data/ -v

# Run only cache tests
python3 -m pytest tests/test_data/test_cache.py -v

# Run only fetcher tests
python3 -m pytest tests/test_data/test_fetcher.py -v
```

**Expected output:**
```
tests/test_data/test_cache.py::TestSaveLoad::test_round_trip                    PASSED
tests/test_data/test_cache.py::TestSaveLoad::test_missing_fields_preserved      PASSED
tests/test_data/test_cache.py::TestSaveLoad::test_as_of_date_preserved          PASSED
tests/test_data/test_cache.py::TestGetWithCache::test_returns_cached_data...    PASSED
tests/test_data/test_cache.py::TestGetWithCache::test_fetches_when_cache_...    PASSED
tests/test_data/test_cache.py::TestGetWithCache::test_fetches_when_cache_stale  PASSED
tests/test_data/test_cache.py::TestInvalidate::test_removes_cache_file          PASSED
tests/test_data/test_cache.py::TestInvalidate::test_noop_when_file_absent       PASSED
tests/test_data/test_fetcher.py::test_fetch_returns_stock_data                  PASSED
tests/test_data/test_fetcher.py::test_fetch_truncates_prices_by_as_of_date      PASSED
tests/test_data/test_fetcher.py::test_fetch_records_missing_fields              PASSED
tests/test_data/test_fetcher.py::test_fetch_handles_empty_price_history         PASSED
tests/test_data/test_fetcher.py::test_fetch_handles_api_exception               PASSED
13 passed in 1.70s
```

**No test makes a live network call.** All tests mock `yf.Ticker` or patch the cache directory with `tmp_path`.

---

## What is not in this module

| Concern | Where it lives |
|---|---|
| Fundamental scoring (ROE > 12%, etc.) | `src/fundamentals/` |
| Valuation scoring (P/E vs 5Y avg) | `src/valuation/` |
| News sentiment | `src/sentiment/` |
| BUY / WATCH / AVOID decision | `src/decision/` |
| Backtest time-stepping | `src/backtest/` |
