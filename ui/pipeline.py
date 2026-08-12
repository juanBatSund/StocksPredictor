"""
Live analysis pipeline for the UI.

Orchestrates the full fetch → score → decide chain and converts the result
into the same dict shape that mock_data._enrich() produces, so templates and
routes work identically for both mock and live data.

Modules used
------------
data.fetcher        : Fetches fundamentals and price history from yfinance.
fundamentals.scorer : Produces quality/growth/dividend/valuation sub-scores.
sentiment.news      : Fetches recent headlines from yfinance.
sentiment.scorer    : Runs lexicon-based NLP on headlines → SentimentResult.
data.macro          : Returns the most recent curated macro event.
macro.tagger        : Classifies a macro event description → MacroTag with
                      sector-level directional impacts and confidence.
decision.engine     : Applies gate-based rules to produce BUY/WATCH/AVOID.

Sentiment and macro are now active. Both are optional: if news data is
unavailable (empty headline list) or no macro event is on record, the
respective argument is passed as None to decide(). The engine records that
absence as an uncertainty flag — nothing is silently dropped.

Optional local AI news analysis is a sidecar only. It records source-linked
evidence for inspection but never changes the deterministic sentiment score or
BUY/WATCH/AVOID decision in this module.

Known limitations
-----------------
1. Sentiment coverage depends on Yahoo Finance news availability for the
   ticker. Tickers with few or no English-language headlines will produce
   low-confidence or absent sentiment.
2. Only the single most recent macro event is used as the macro context.
   Concurrent macro themes (e.g. trade war + recession risk simultaneously)
   are not combined; extend this module if richer macro context is needed.
3. Results are cached in-memory per (ticker, market) pair for the lifetime
   of the server process to avoid redundant yfinance calls. Call invalidate()
   to force a re-fetch.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime, timezone

import yfinance as yf

from config.markets import MARKETS
from src.ai.models import AuditedNewsAnalysis, NewsAnalysisRequest
from ui.ai_settings import cache_key_suffix, get_service as configured_news_analysis_service
from src.ai.service import AnalysisUnavailable, analyze_if_available
from src.data.fetcher import fetch
from src.data.macro import get_latest_event
from src.fundamentals.scorer import score as fund_score
from src.macro.tagger import tag as tag_macro
from src.sentiment.news import fetch_articles
from src.sentiment.scorer import score as score_sentiment
from src.decision.engine import decide

# In-memory result cache. AI configuration is part of the identity so enabling
# a new local model cannot silently return a deterministic-only cached result.
_CACHE: dict[str, dict] = {}


def analyze(ticker: str, market_code: str = "US") -> dict:
    """
    Run the full pipeline for ticker and return a UI-ready stock dict.

    Raises ValueError if no price or info data can be fetched (invalid ticker).
    Results are cached in-memory until the server restarts.
    """
    ticker = ticker.upper().strip()
    key = _cache_key(ticker, market_code)
    if key in _CACHE:
        return _CACHE[key]

    market = MARKETS[market_code]
    full_ticker = ticker + market.ticker_suffix

    # Fetch display metadata (name, sector, 52w range, current price).
    # This is a separate call from data.fetcher because StockData does not
    # expose display fields — the fetcher's info dict is internal to it.
    info: dict = {}
    try:
        info = yf.Ticker(full_ticker).info or {}
    except Exception:
        pass

    stock_data = fetch(ticker, market)

    if not info and not stock_data.prices:
        raise ValueError(f"No data found for '{ticker}'")

    # ── Fundamentals ──────────────────────────────────────────────────────────
    fundamental = fund_score(ticker, stock_data.fundamentals, market)
    sector = (info.get("sector") or "").lower() or None

    # ── Sentiment ─────────────────────────────────────────────────────────────
    articles = fetch_articles(ticker, market.ticker_suffix)
    dated_headlines = [(article.published_at.date(), article.headline) for article in articles]
    sentiment = (
        score_sentiment(ticker, dated_headlines)
        if dated_headlines
        else None
    )
    ai_outcome = _analyse_news_sidecar(ticker, articles)

    # ── Macro ─────────────────────────────────────────────────────────────────
    latest_event = get_latest_event(date.today())
    macro = tag_macro(latest_event.description) if latest_event else None

    # ── Decision ──────────────────────────────────────────────────────────────
    ai_analysis_obj = ai_outcome.analysis if isinstance(ai_outcome, AuditedNewsAnalysis) else None
    dr = decide(
        ticker=ticker,
        fundamental=fundamental,
        sector=sector,
        sentiment=sentiment,
        macro=macro,
        missing_fields=stock_data.missing_fields,
        ai_analysis=ai_analysis_obj,
    )

    result = _build_dict(ticker, dr, stock_data, info, _serialise_ai_outcome(ai_outcome))
    _CACHE[key] = result
    return result


def invalidate(ticker: str, market_code: str = "US") -> None:
    """Remove a ticker from the in-memory cache to force a re-fetch."""
    prefix = f"{ticker.upper()}:{market_code}:"
    for key in list(_CACHE):
        if key.startswith(prefix):
            _CACHE.pop(key, None)


def _build_dict(ticker: str, dr, stock_data, info: dict, ai_news_analysis: dict) -> dict:
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if price is None and stock_data.prices:
        price = stock_data.latest_price

    return {
        "ticker":          ticker,
        "name":            info.get("longName") or info.get("shortName") or ticker,
        "sector":          (info.get("sector") or "").lower(),
        "price":           round(float(price), 2) if price else None,
        "hi_52w":          info.get("fiftyTwoWeekHigh"),
        "lo_52w":          info.get("fiftyTwoWeekLow"),
        "missing_fields":  stock_data.missing_fields,
        # Decision engine output
        "decision":               dr.decision,
        "score":                  dr.score,
        "quality_score":          dr.quality_score,
        "growth_score":           dr.growth_score,
        "dividend_score":         dr.dividend_score,
        "valuation_score":        dr.valuation_score,
        "valuation_status":       dr.valuation_status,
        "confidence":             dr.confidence,
        "confidence_breakdown":   dr.confidence_breakdown,
        "gates":                  dr.gates,
        "contributing_factors":   dr.contributing_factors,
        "rejected_factors":       dr.rejected_factors,
        "uncertainty_flags":      dr.uncertainty_flags,
        "sentiment_score":        dr.sentiment_score,
        "sentiment_status":       dr.sentiment_status,
        "sentiment_trend":        dr.sentiment_trend,
        "sentiment_confidence":   dr.sentiment_confidence,
        "macro_category":         dr.macro_category,
        "macro_sector_direction": dr.macro_sector_direction,
        "macro_sector_strength":  dr.macro_sector_strength,
        "macro_confidence":       dr.macro_confidence,
        "reasoning_trace":        dr.reasoning_trace,
        "notes":                  dr.notes,
        # AI evidence sidecar — raw analysis dict for the UI inspector panel.
        "ai_news_analysis":       ai_news_analysis,
        # AI decision fields — derived from ai_analysis inside decide().
        "ai_overall_direction":   dr.ai_overall_direction,
        "ai_sentiment_score":     dr.ai_sentiment_score,
        "ai_analysis_confidence": dr.ai_analysis_confidence,
        "ai_event_types":         dr.ai_event_types,
        "is_live":                True,
    }


def _cache_key(ticker: str, market_code: str) -> str:
    return f"{ticker}:{market_code}:{cache_key_suffix()}"


_NO_ARTICLES_REASON = "No provenance-rich news articles available"


def _analyse_news_sidecar(ticker: str, articles) -> AuditedNewsAnalysis | AnalysisUnavailable:
    """Run optional local AI analysis. Returns typed result so decide() can consume it."""
    if not articles:
        return AnalysisUnavailable(_NO_ARTICLES_REASON)
    request = NewsAnalysisRequest(
        ticker=ticker,
        decision_at=datetime.now(timezone.utc),
        articles=articles,
    )
    return analyze_if_available(configured_news_analysis_service(), request)


def _serialise_ai_outcome(outcome: AuditedNewsAnalysis | AnalysisUnavailable) -> dict:
    """Convert AI outcome to a UI-ready dict (separate from the typed object passed to decide())."""
    if isinstance(outcome, AnalysisUnavailable):
        status = "not_run" if outcome.reason == _NO_ARTICLES_REASON else "unavailable"
        return {"status": status, "reason": outcome.reason}
    return {
        "status": "available",
        "record_id": outcome.audit_record_id,
        "provider": outcome.provider,
        "model": outcome.model,
        "prompt_version": outcome.prompt_version,
        "analysis": outcome.analysis.model_dump(mode="json"),
    }
