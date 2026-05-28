"""
News headline fetcher for the sentiment module.

Retrieves recent financial news for a ticker from Yahoo Finance via yfinance
and converts it into the (date, headline) format expected by sentiment.scorer.

Public API
----------
fetch(ticker, market_suffix="", limit=50) -> list[tuple[date, str]]

yfinance API compatibility
--------------------------
yfinance ≥ 1.4.0 changed the news response structure. The old flat format:
    {"title": "...", "providerPublishTime": <unix_ts>, ...}
was replaced with a nested format:
    {"id": "...", "content": {"title": "...", "pubDate": "2024-03-01T10:05:00Z", ...}}

This module handles both shapes so it works across yfinance versions:
  - title   : item["content"]["title"]  (new) → item["title"]  (old fallback)
  - pub_date: item["content"]["pubDate"] (new ISO string) →
              item["providerPublishTime"] (old Unix timestamp fallback)

Design decisions
----------------
- yfinance is already a project dependency, so no new package is required.
- Items are returned sorted oldest-first so the scorer's OLS trend slope is
  computed in chronological order.
- The `limit` parameter caps the number of articles consumed. Yahoo Finance
  typically returns 8–25 items; the cap guards against edge-case responses.

Known limitations
-----------------
1. Yahoo Finance only exposes recent headlines (typically the last 7–30 days).
   This is sufficient for a current sentiment snapshot but not for point-in-time
   backtesting; use frozen fixture data for that.
2. The title field is not cleaned beyond what the sentiment tokeniser handles
   (lowercase, punctuation stripped).
3. Coverage is uneven — some tickers have many headlines, others have none.
   Low headline count flows through to low scorer confidence.
4. Duplicate headlines on the same date (wire service syndication) are not
   deduplicated; the scorer's daily-average aggregation reduces their net impact.
"""

from datetime import date, datetime, timezone
from typing import Optional

import yfinance as yf

from src.logging.logger import log_input, log_result, log_warning

_MODULE = "sentiment.news"


def fetch(
    ticker: str,
    market_suffix: str = "",
    limit: int = 50,
) -> list[tuple[date, str]]:
    """
    Fetch recent news headlines for a ticker from Yahoo Finance.

    Parameters
    ----------
    ticker        : Bare ticker symbol, e.g. "MSFT".
    market_suffix : Exchange suffix appended to the ticker (from MarketProfile),
                    e.g. ".ST" for Stockholm. Empty string for US markets.
    limit         : Maximum number of articles to process (cap on raw list).

    Returns
    -------
    List of (publication_date, headline_text) tuples, sorted oldest-first.
    Empty list if no data is available or the fetch fails.
    """
    full_ticker = ticker + market_suffix
    log_input(_MODULE, {"ticker": ticker, "full_ticker": full_ticker, "limit": limit})

    try:
        raw = yf.Ticker(full_ticker).news or []
    except Exception as exc:
        log_warning(_MODULE, "news_fetch_failed", {
            "ticker": full_ticker,
            "error": str(exc),
        })
        return []

    if not raw:
        log_warning(_MODULE, "no_news_returned", {"ticker": full_ticker})
        return []

    results: list[tuple[date, str]] = []
    skipped = 0

    for item in raw[:limit]:
        title = _extract_title(item)
        pub_date = _extract_date(item)

        if not title or pub_date is None:
            skipped += 1
            continue

        results.append((pub_date, title))

    # Oldest-first so the scorer's OLS slope runs in chronological order
    results.sort(key=lambda x: x[0])

    log_result(_MODULE, {
        "ticker": ticker,
        "raw_count": len(raw),
        "returned_count": len(results),
        "skipped_count": skipped,
        "date_range": (
            f"{results[0][0]} → {results[-1][0]}" if results else "none"
        ),
    })

    return results


# ── Internal helpers ───────────────────────────────────────────────────────────

def _extract_title(item: dict) -> str:
    """
    Extract the headline text from a yfinance news item.

    Supports both the new nested format (yfinance ≥ 1.4.0) and the legacy
    flat format. Returns an empty string if no title can be found.
    """
    # New format: item["content"]["title"]
    content = item.get("content")
    if isinstance(content, dict):
        title = (content.get("title") or "").strip()
        if title:
            return title

    # Legacy format: item["title"]
    return (item.get("title") or "").strip()


def _extract_date(item: dict) -> Optional[date]:
    """
    Extract the publication date from a yfinance news item.

    Supports both the new ISO-string format (yfinance ≥ 1.4.0) and the
    legacy Unix-timestamp format. Returns None if no valid date is found.
    """
    # New format: item["content"]["pubDate"] as ISO 8601 string
    content = item.get("content")
    if isinstance(content, dict):
        pub_date_str = content.get("pubDate") or content.get("displayTime")
        if pub_date_str:
            parsed = _parse_iso(pub_date_str)
            if parsed:
                return parsed

    # Legacy format: item["providerPublishTime"] as Unix timestamp
    ts = item.get("providerPublishTime")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
        except (ValueError, OSError, TypeError):
            pass

    return None


def _parse_iso(date_str: str) -> Optional[date]:
    """
    Parse an ISO 8601 datetime string to a date object.

    Handles strings ending in 'Z' and '+00:00' offsets. Takes only the
    first 19 characters (YYYY-MM-DDTHH:MM:SS) to avoid timezone suffix
    issues across Python versions.
    """
    try:
        return datetime.strptime(date_str[:19], "%Y-%m-%dT%H:%M:%S").date()
    except (ValueError, TypeError):
        return None
