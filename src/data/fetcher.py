from datetime import date, datetime, timezone
from typing import Optional

import yfinance as yf

from config.markets import MarketProfile
from config.settings import YFINANCE_PRICE_INTERVAL, YFINANCE_PRICE_PERIOD
from src.data.models import Fundamentals, PriceRecord, StockData
from src.logging.logger import log_error, log_input, log_result, log_warning

_MODULE = "data.fetcher"


def fetch(ticker: str, market: MarketProfile, as_of_date: Optional[date] = None) -> StockData:
    """
    Fetch price history and fundamentals for a ticker from Yahoo Finance.

    market:      determines the exchange suffix appended to the ticker and
                 which thresholds are market-appropriate.
    as_of_date:  when set, prices are truncated to that date (backtest isolation).
    """
    full_ticker = ticker + market.ticker_suffix
    log_input(_MODULE, {"ticker": ticker, "market": market.code, "full_ticker": full_ticker, "as_of_date": str(as_of_date)})

    info = _fetch_info(full_ticker)
    prices = _fetch_prices(full_ticker, as_of_date)
    streak = _compute_dividend_streak(full_ticker)
    fundamentals, missing = _build_fundamentals(full_ticker, info, streak)

    result = StockData(
        ticker=ticker,
        market_code=market.code,
        fetched_at=datetime.now(timezone.utc),
        as_of_date=as_of_date,
        prices=prices,
        fundamentals=fundamentals,
        missing_fields=missing,
    )

    log_result(_MODULE, {
        "ticker": ticker,
        "market": market.code,
        "price_records": len(prices),
        "latest_price": result.latest_price,
        "missing_fields": missing,
        "dividend_streak_years": streak,
    })

    return result


# ── internal helpers ──────────────────────────────────────────────────────────

def _fetch_info(full_ticker: str) -> dict:
    try:
        return yf.Ticker(full_ticker).info or {}
    except Exception as exc:
        log_error(_MODULE, "info_fetch_failed", {"ticker": full_ticker, "error": str(exc)})
        return {}


def _fetch_prices(full_ticker: str, as_of_date: Optional[date]) -> list[PriceRecord]:
    try:
        df = yf.Ticker(full_ticker).history(
            period=YFINANCE_PRICE_PERIOD,
            interval=YFINANCE_PRICE_INTERVAL,
            auto_adjust=True,
        )
    except Exception as exc:
        log_error(_MODULE, "price_fetch_failed", {"ticker": full_ticker, "error": str(exc)})
        return []

    if df.empty:
        log_warning(_MODULE, "empty_price_history", {"ticker": full_ticker})
        return []

    records = []
    for ts, row in df.iterrows():
        row_date = ts.date() if hasattr(ts, "date") else ts
        if as_of_date and row_date > as_of_date:
            continue
        records.append(PriceRecord(
            date=row_date,
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=int(row["Volume"]),
        ))

    return records


def _compute_dividend_streak(full_ticker: str) -> int:
    """
    Count consecutive years of non-decreasing annual dividends, walking back
    from the most recently completed year.

    A gap in years (suspended dividend) resets the count to zero.
    Returns 0 when no dividend history exists or on fetch failure.
    """
    try:
        divs = yf.Ticker(full_ticker).dividends
    except Exception as exc:
        log_warning(_MODULE, "dividend_streak_fetch_failed", {"ticker": full_ticker, "error": str(exc)})
        return 0

    import pandas as pd
    if not isinstance(divs, pd.Series) or divs.empty:
        return 0

    # Sum all payments within each calendar year.
    # groupby(index.year) works correctly for both tz-aware and tz-naive indices.
    annual = divs.groupby(divs.index.year).sum()

    # Exclude the current year — it is incomplete and would understate the total.
    current_year = datetime.now().year
    annual = annual[annual.index < current_year]

    if len(annual) < 2:
        return 0

    years = sorted(annual.index)  # ascending
    streak = 0

    for i in range(len(years) - 1, 0, -1):
        if years[i] - years[i - 1] > 1:
            # Gap: dividend was suspended for at least one year
            break
        if annual[years[i]] >= annual[years[i - 1]]:
            streak += 1
        else:
            break

    return streak


def _build_fundamentals(full_ticker: str, info: dict, streak: int) -> tuple[Fundamentals, list[str]]:
    missing: list[str] = []

    def get(key: str, transform=None):
        val = info.get(key)
        if val is None or val == "N/A":
            missing.append(key)
            return None
        return transform(val) if transform else val

    roe = get("returnOnEquity")
    debt_to_equity = get("debtToEquity", lambda v: v / 100)  # yfinance returns as percentage
    free_cash_flow = get("freeCashflow")
    revenue_growth_5y = get("revenueGrowth")
    earnings_growth_5y = get("earningsGrowth")
    dividend_yield = get("dividendYield")
    payout_ratio = get("payoutRatio")
    pe_ratio = get("trailingPE")
    pe_5y_avg = get("fiveYearAvgDividendYield")

    if missing:
        log_warning(_MODULE, "missing_fundamental_fields", {"ticker": full_ticker, "fields": missing})

    return (
        Fundamentals(
            roe=roe,
            debt_to_equity=debt_to_equity,
            free_cash_flow=free_cash_flow,
            revenue_growth_5y=revenue_growth_5y,
            earnings_growth_5y=earnings_growth_5y,
            dividend_yield=dividend_yield,
            payout_ratio=payout_ratio,
            dividend_growth_streak_years=streak,
            pe_ratio=pe_ratio,
            pe_5y_avg=pe_5y_avg,
        ),
        missing,
    )
