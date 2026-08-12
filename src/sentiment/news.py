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
- ``fetch_articles`` retains provenance required by the AI audit layer; legacy
  ``fetch`` returns date/headline tuples for the deterministic lexicon scorer.
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

import hashlib
from datetime import date, datetime, timezone
from typing import Optional

import yfinance as yf

from src.ai.models import NewsArticle
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
    articles = fetch_articles(ticker, market_suffix, limit)
    return [(article.published_at.date(), article.headline) for article in articles]


def fetch_articles(
    ticker: str,
    market_suffix: str = "",
    limit: int = 50,
    *,
    fetched_at: datetime | None = None,
) -> list[NewsArticle]:
    """Fetch provenance-rich articles for AI analysis and immutable audit.

    ``available_at`` is the UTC time this system observed the article. It is
    sufficient for live audit records but does not make Yahoo Finance news
    point-in-time historical data; historical analysis must supply archived
    ``NewsArticle`` fixtures or another timestamped source.
    """
    full_ticker = ticker + market_suffix
    observed_at = fetched_at or datetime.now(timezone.utc)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("fetched_at must be timezone-aware")
    log_input(_MODULE, {
        "ticker": ticker,
        "full_ticker": full_ticker,
        "limit": limit,
        "fetched_at": observed_at.isoformat(),
    })

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

    results: list[NewsArticle] = []
    skipped = 0
    for index, item in enumerate(raw[:limit], start=1):
        title = _extract_title(item)
        published_at = _extract_datetime(item)
        if not title or published_at is None or published_at > observed_at:
            skipped += 1
            continue
        results.append(NewsArticle(
            article_id=_extract_article_id(item, ticker, published_at, title, index),
            ticker=ticker,
            headline=title,
            publisher=_extract_publisher(item),
            url=_extract_url(item),
            published_at=published_at,
            available_at=observed_at,
        ))

    results.sort(key=lambda article: article.published_at)
    log_result(_MODULE, {
        "ticker": ticker,
        "raw_count": len(raw),
        "returned_count": len(results),
        "skipped_count": skipped,
        "date_range": (
            f"{results[0].published_at.date()} → {results[-1].published_at.date()}"
            if results else "none"
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
    published_at = _extract_datetime(item)
    return published_at.date() if published_at else None


def _extract_datetime(item: dict) -> Optional[datetime]:
    """Extract a timezone-aware publication timestamp from either Yahoo shape."""
    # New format: item["content"]["pubDate"] as ISO 8601 string
    content = item.get("content")
    if isinstance(content, dict):
        pub_date_str = content.get("pubDate") or content.get("displayTime")
        if pub_date_str:
            parsed = _parse_iso_datetime(pub_date_str)
            if parsed:
                return parsed

    # Legacy format: item["providerPublishTime"] as Unix timestamp
    ts = item.get("providerPublishTime")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
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
    parsed = _parse_iso_datetime(date_str)
    return parsed.date() if parsed else None


def _parse_iso_datetime(date_str: str) -> Optional[datetime]:
    """Parse an ISO string to an aware UTC timestamp, defaulting naive input to UTC."""
    if not isinstance(date_str, str):
        return None
    try:
        parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_publisher(item: dict) -> str:
    """Best-effort publisher retention; Yahoo's exact shape varies by version."""
    content = item.get("content")
    if isinstance(content, dict):
        provider = content.get("provider")
        if isinstance(provider, dict):
            value = provider.get("displayName") or provider.get("name")
            if isinstance(value, str) and value.strip():
                return value.strip()
        if isinstance(provider, str) and provider.strip():
            return provider.strip()
        value = content.get("publisher")
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("publisher", "provider"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Yahoo Finance"


def _extract_url(item: dict) -> Optional[str]:
    """Best-effort canonical article URL extraction without manufacturing links."""
    content = item.get("content")
    candidates: list[object] = []
    if isinstance(content, dict):
        candidates.extend([
            content.get("canonicalUrl"),
            content.get("clickThroughUrl"),
            content.get("url"),
        ])
    candidates.extend([item.get("link"), item.get("url")])
    for candidate in candidates:
        if isinstance(candidate, dict):
            candidate = candidate.get("url")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _extract_article_id(
    item: dict,
    ticker: str,
    published_at: datetime,
    title: str,
    index: int,
) -> str:
    """Use Yahoo's ID when present, otherwise create a stable provenance key."""
    raw_id = item.get("id")
    if isinstance(raw_id, str) and raw_id.strip():
        return raw_id.strip()
    fingerprint = f"{ticker}|{published_at.isoformat()}|{title}|{index}"
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
