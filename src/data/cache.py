import json
import time
from datetime import date
from pathlib import Path
from typing import Optional

from config.markets import MarketProfile
from config.settings import CACHE_DIR, CACHE_TTL_SECONDS
from src.data.fetcher import fetch
from src.data.models import Fundamentals, PriceRecord, StockData
from src.logging.logger import log_input, log_result, log_warning

_MODULE = "data.cache"

CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get(ticker: str, market: MarketProfile, as_of_date: Optional[date] = None) -> StockData:
    """
    Return StockData from disk cache if fresh; otherwise fetch and write through.

    The cache key includes the exchange suffix so US and SE tickers never collide.
    """
    log_input(_MODULE, {"ticker": ticker, "market": market.code, "as_of_date": str(as_of_date)})

    cache_path = _path(ticker, market, as_of_date)

    if _is_fresh(cache_path):
        data = _load(cache_path)
        log_result(_MODULE, {"ticker": ticker, "market": market.code, "source": "cache"})
        return data

    data = fetch(ticker, market, as_of_date)
    _save(cache_path, data)
    log_result(_MODULE, {"ticker": ticker, "market": market.code, "source": "fetch"})
    return data


def invalidate(ticker: str, market: MarketProfile, as_of_date: Optional[date] = None) -> None:
    path = _path(ticker, market, as_of_date)
    if path.exists():
        path.unlink()
        log_warning(_MODULE, "cache_invalidated", {"ticker": ticker, "market": market.code})


# ── serialisation ─────────────────────────────────────────────────────────────

def _path(ticker: str, market: MarketProfile, as_of_date: Optional[date]) -> Path:
    # Replace "." in suffix so "VOLV-B.ST" → "VOLV-B_ST" (avoids double extension)
    exchange_key = (ticker.upper() + market.ticker_suffix.replace(".", "_"))
    date_part = f"_{as_of_date}" if as_of_date else ""
    return CACHE_DIR / f"{exchange_key}{date_part}.json"


def _is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < CACHE_TTL_SECONDS


def _save(path: Path, data: StockData) -> None:
    payload = {
        "ticker": data.ticker,
        "market_code": data.market_code,
        "fetched_at": data.fetched_at.isoformat(),
        "as_of_date": str(data.as_of_date) if data.as_of_date else None,
        "missing_fields": data.missing_fields,
        "prices": [
            {
                "date": str(r.date),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in data.prices
        ],
        "fundamentals": {
            "roe": data.fundamentals.roe,
            "debt_to_equity": data.fundamentals.debt_to_equity,
            "free_cash_flow": data.fundamentals.free_cash_flow,
            "revenue_growth_5y": data.fundamentals.revenue_growth_5y,
            "earnings_growth_5y": data.fundamentals.earnings_growth_5y,
            "dividend_yield": data.fundamentals.dividend_yield,
            "payout_ratio": data.fundamentals.payout_ratio,
            "dividend_growth_streak_years": data.fundamentals.dividend_growth_streak_years,
            "pe_ratio": data.fundamentals.pe_ratio,
            "pe_5y_avg": data.fundamentals.pe_5y_avg,
        },
    }
    path.write_text(json.dumps(payload, indent=2))


def _load(path: Path) -> StockData:
    from datetime import datetime, timezone

    raw = json.loads(path.read_text())

    prices = [
        PriceRecord(
            date=date.fromisoformat(r["date"]),
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            volume=r["volume"],
        )
        for r in raw["prices"]
    ]

    f = raw["fundamentals"]
    fundamentals = Fundamentals(
        roe=f["roe"],
        debt_to_equity=f["debt_to_equity"],
        free_cash_flow=f["free_cash_flow"],
        revenue_growth_5y=f["revenue_growth_5y"],
        earnings_growth_5y=f["earnings_growth_5y"],
        dividend_yield=f["dividend_yield"],
        payout_ratio=f["payout_ratio"],
        dividend_growth_streak_years=f["dividend_growth_streak_years"],
        pe_ratio=f["pe_ratio"],
        pe_5y_avg=f["pe_5y_avg"],
    )

    return StockData(
        ticker=raw["ticker"],
        market_code=raw.get("market_code", "US"),  # default for pre-market cache files
        fetched_at=datetime.fromisoformat(raw["fetched_at"]),
        as_of_date=date.fromisoformat(raw["as_of_date"]) if raw["as_of_date"] else None,
        prices=prices,
        fundamentals=fundamentals,
        missing_fields=raw["missing_fields"],
    )
