"""
Batch screener for the Investment Decision System.

Runs fundamentals + macro analysis across the top companies in a given market
and surfaces BUY candidates. Sentiment (per-ticker news) is skipped to keep
runtime reasonable — the screener is designed to give a quick first pass, and
any BUY candidate can be clicked through to the full detail page.

Public API
----------
run_market(market_code)         Start a background screener run (no-op if already running).
get_state(market_code)          Return current run metadata + counts.
load_results(market_code)       Return the last saved result list, or [].
MARKET_LABELS                   Re-exported for convenience (same as config.tickers).

Architecture
------------
Each market runs in a daemon thread. Progress and results are flushed to a JSON
file under ui/screener_cache/<market>.json every FLUSH_EVERY tickers, plus at
completion. Reads use atomic rename so the reader never sees a partial write.

The macro context is computed once per run and reused for every ticker in the
batch. Only the most recent macro event is used; see src/data/macro.py for the
event registry.

Results dict shape (one entry per processed ticker)
----------------------------------------------------
{
    "ticker":           str,
    "name":             str,
    "sector":           str,
    "price":            float | None,
    "decision":         "BUY" | "WATCH" | "AVOID",
    "score":            float,
    "quality_score":    float,
    "growth_score":     float,
    "dividend_score":   float,
    "valuation_score":  float,
    "valuation_status": str,
    "confidence":       float,
    "flag_count":       int,
    "market_code":      str,
}
"""

import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date

import yfinance as yf

from config.markets import MARKETS
from config.tickers import MARKET_TICKERS, MARKET_LABELS
from src.data.fetcher import fetch
from src.data.macro import get_latest_event
from src.fundamentals.scorer import score as fund_score
from src.macro.tagger import tag as tag_macro
from src.decision.engine import decide

# ── Constants ─────────────────────────────────────────────────────────────────

_CACHE_DIR = os.path.join(os.path.dirname(__file__), "screener_cache")
_SLEEP_BETWEEN = 0.3   # seconds between tickers (Yahoo Finance rate limit)
FLUSH_EVERY    = 5     # flush results to disk after this many tickers

# ── In-memory state ───────────────────────────────────────────────────────────

_state: dict[str, dict] = {}
# Shape of each entry:
# {
#   "status":    "idle" | "running" | "done" | "error",
#   "total":     int,
#   "processed": int,
#   "results":   list[dict],   # volatile in-progress list
#   "started_at": str,
# }

_locks: dict[str, threading.Lock] = {}


def _lock(market_code: str) -> threading.Lock:
    if market_code not in _locks:
        _locks[market_code] = threading.Lock()
    return _locks[market_code]


# ── Public API ────────────────────────────────────────────────────────────────

def run_market(market_code: str) -> None:
    """
    Start a background screener run for market_code.

    Does nothing if a run is already in progress. A new run overwrites the
    previous cache file when complete.
    """
    with _lock(market_code):
        state = _state.get(market_code, {})
        if state.get("status") == "running":
            return

        tickers = MARKET_TICKERS.get(market_code, [])
        _state[market_code] = {
            "status":     "running",
            "total":      len(tickers),
            "processed":  0,
            "results":    [],
            "started_at": date.today().isoformat(),
        }

    t = threading.Thread(target=_worker, args=(market_code,), daemon=True)
    t.start()


def get_state(market_code: str) -> dict:
    """
    Return a JSON-serialisable snapshot of the current run state.

    Fields: status, total, processed, started_at, buy_count, watch_count,
    avoid_count, error_count (for tickers that failed).
    """
    with _lock(market_code):
        state = dict(_state.get(market_code, {}))

    if not state:
        # No in-memory state — check if we have a cache file from a prior run
        results = load_results(market_code)
        if results:
            buys = sum(1 for r in results if r["decision"] == "BUY")
            return {
                "status":      "done",
                "total":       len(results),
                "processed":   len(results),
                "buy_count":   buys,
                "watch_count": sum(1 for r in results if r["decision"] == "WATCH"),
                "avoid_count": sum(1 for r in results if r["decision"] == "AVOID"),
                "error_count": 0,
                "started_at":  "",
            }
        return {"status": "idle", "total": 0, "processed": 0}

    results = state.get("results", [])
    return {
        "status":      state["status"],
        "total":       state["total"],
        "processed":   state["processed"],
        "started_at":  state.get("started_at", ""),
        "buy_count":   sum(1 for r in results if r.get("decision") == "BUY"),
        "watch_count": sum(1 for r in results if r.get("decision") == "WATCH"),
        "avoid_count": sum(1 for r in results if r.get("decision") == "AVOID"),
        "error_count": sum(1 for r in results if r.get("decision") == "ERROR"),
    }


def load_results(market_code: str) -> list[dict]:
    """Load the last completed screener results from disk. Returns [] on miss."""
    path = _cache_path(market_code)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


# ── Background worker ─────────────────────────────────────────────────────────

def _worker(market_code: str) -> None:
    tickers = MARKET_TICKERS.get(market_code, [])

    # Pre-compute macro context once — same for every ticker
    latest_event = get_latest_event(date.today())
    macro = tag_macro(latest_event.description) if latest_event else None

    pending: list[dict] = []

    try:
        for idx, (ticker, ticker_market) in enumerate(tickers):
            result = _analyze_one(ticker, ticker_market, macro)
            pending.append(result)

            with _lock(market_code):
                _state[market_code]["processed"] = idx + 1
                _state[market_code]["results"].append(result)

            if len(pending) >= FLUSH_EVERY:
                _flush(market_code)
                pending.clear()

            time.sleep(_SLEEP_BETWEEN)

        # Final flush
        _flush(market_code)

        with _lock(market_code):
            _state[market_code]["status"] = "done"

    except Exception as exc:
        with _lock(market_code):
            _state[market_code]["status"] = "error"
            _state[market_code]["error"] = str(exc)
        # Still flush whatever was collected so partial results are available
        _flush(market_code)


def _analyze_one(ticker: str, market_code: str, macro) -> dict:
    """
    Run fundamentals + macro analysis for a single ticker.

    Sentiment is intentionally skipped — fetching news per ticker would add
    8–25 seconds per ticker and make the screener impractically slow.
    """
    market = MARKETS.get(market_code)
    if market is None:
        return _error_row(ticker, market_code, f"unknown market '{market_code}'")

    full_ticker = ticker + market.ticker_suffix

    try:
        info: dict = {}
        try:
            info = yf.Ticker(full_ticker).info or {}
        except Exception:
            pass

        stock_data = fetch(ticker, market)

        if not info and not stock_data.prices:
            return _error_row(ticker, market_code, "no data")

        fundamental = fund_score(ticker, stock_data.fundamentals, market)
        sector = (info.get("sector") or "").lower() or None

        dr = decide(
            ticker=ticker,
            fundamental=fundamental,
            sector=sector,
            sentiment=None,
            macro=macro,
            missing_fields=stock_data.missing_fields,
        )

        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if price is None and stock_data.prices:
            price = stock_data.latest_price

        return {
            "ticker":           ticker,
            "name":             info.get("longName") or info.get("shortName") or ticker,
            "sector":           sector or "",
            "price":            round(float(price), 2) if price else None,
            "decision":         dr.decision,
            "score":            round(dr.score, 1),
            "quality_score":    round(dr.quality_score, 1),
            "growth_score":     round(dr.growth_score, 1),
            "dividend_score":   round(dr.dividend_score, 1),
            "valuation_score":  round(dr.valuation_score, 1),
            "valuation_status": dr.valuation_status,
            "confidence":       round(dr.confidence, 2),
            "flag_count":       len(dr.uncertainty_flags),
            "market_code":      market_code,
        }

    except Exception as exc:
        return _error_row(ticker, market_code, str(exc))


def _error_row(ticker: str, market_code: str, reason: str) -> dict:
    return {
        "ticker":           ticker,
        "name":             ticker,
        "sector":           "",
        "price":            None,
        "decision":         "ERROR",
        "score":            0.0,
        "quality_score":    0.0,
        "growth_score":     0.0,
        "dividend_score":   0.0,
        "valuation_score":  0.0,
        "valuation_status": "unknown",
        "confidence":       0.0,
        "flag_count":       0,
        "market_code":      market_code,
        "error":            reason,
    }


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_path(market_code: str) -> str:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return os.path.join(_CACHE_DIR, f"{market_code.lower()}.json")


def _flush(market_code: str) -> None:
    """Atomically write current results to disk (write tmp, then rename)."""
    with _lock(market_code):
        results = list(_state.get(market_code, {}).get("results", []))

    path = _cache_path(market_code)
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        os.replace(tmp_path, path)
    except OSError:
        pass
