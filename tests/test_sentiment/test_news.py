"""
Tests for src/sentiment/news.py

All yfinance calls are mocked — no network access required.

Two item-format helpers are provided:
  _item_new()  — yfinance ≥ 1.4.0 nested structure
  _item_old()  — legacy flat structure (providerPublishTime + title)
Both are tested to ensure cross-version compatibility.
"""

import pytest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

from src.sentiment.news import fetch, _extract_title, _extract_date, _parse_iso


# ── Item format helpers ────────────────────────────────────────────────────────

def _ts(d: date) -> int:
    """Convert a date to a UTC Unix timestamp (midnight)."""
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def _iso(d: date) -> str:
    """Format a date as an ISO 8601 UTC string."""
    return f"{d.isoformat()}T12:00:00Z"


def _item_new(title: str, d: date) -> dict:
    """yfinance ≥ 1.4.0 nested format."""
    return {
        "id": "test-id",
        "content": {
            "title": title,
            "pubDate": _iso(d),
            "displayTime": _iso(d),
        },
    }


def _item_old(title: str, d: date) -> dict:
    """Legacy flat format (yfinance < 1.4.0)."""
    return {"title": title, "providerPublishTime": _ts(d)}


# ── _extract_title ─────────────────────────────────────────────────────────────

class TestExtractTitle:
    def test_new_format_reads_content_title(self):
        item = _item_new("Earnings beat expectations", date(2024, 1, 1))
        assert _extract_title(item) == "Earnings beat expectations"

    def test_old_format_reads_top_level_title(self):
        item = _item_old("Revenue growth strong", date(2024, 1, 1))
        assert _extract_title(item) == "Revenue growth strong"

    def test_strips_whitespace(self):
        item = {"content": {"title": "  Dividend raised  "}}
        assert _extract_title(item) == "Dividend raised"

    def test_missing_title_returns_empty_string(self):
        assert _extract_title({}) == ""

    def test_content_dict_missing_title_falls_back_to_top_level(self):
        item = {"content": {}, "title": "Fallback title"}
        assert _extract_title(item) == "Fallback title"

    def test_content_is_not_dict_falls_back_to_top_level(self):
        item = {"content": None, "title": "Top level title"}
        assert _extract_title(item) == "Top level title"


# ── _extract_date ──────────────────────────────────────────────────────────────

class TestExtractDate:
    def test_new_format_parses_pub_date(self):
        item = _item_new("Any title", date(2024, 6, 15))
        result = _extract_date(item)
        assert result == date(2024, 6, 15)

    def test_new_format_uses_display_time_as_fallback(self):
        item = {
            "content": {
                "displayTime": "2024-09-20T08:30:00Z",
            }
        }
        result = _extract_date(item)
        assert result == date(2024, 9, 20)

    def test_old_format_parses_unix_timestamp(self):
        item = _item_old("Any title", date(2024, 3, 10))
        result = _extract_date(item)
        assert result == date(2024, 3, 10)

    def test_missing_date_returns_none(self):
        assert _extract_date({}) is None

    def test_invalid_timestamp_returns_none(self):
        item = {"providerPublishTime": "not-a-number"}
        assert _extract_date(item) is None

    def test_invalid_iso_string_returns_none(self):
        item = {"content": {"pubDate": "not-a-date"}}
        assert _extract_date(item) is None

    def test_content_not_dict_falls_back_to_old_format(self):
        item = {"content": None, "providerPublishTime": _ts(date(2024, 5, 1))}
        assert _extract_date(item) == date(2024, 5, 1)


# ── _parse_iso ─────────────────────────────────────────────────────────────────

class TestParseIso:
    def test_z_suffix(self):
        assert _parse_iso("2024-03-15T10:05:00Z") == date(2024, 3, 15)

    def test_no_suffix(self):
        assert _parse_iso("2024-03-15T10:05:00") == date(2024, 3, 15)

    def test_offset_suffix_truncated_correctly(self):
        assert _parse_iso("2024-03-15T10:05:00+05:30") == date(2024, 3, 15)

    def test_invalid_string_returns_none(self):
        assert _parse_iso("not-a-date") is None

    def test_empty_string_returns_none(self):
        assert _parse_iso("") is None

    def test_none_returns_none(self):
        assert _parse_iso(None) is None


# ── Happy path (new format) ────────────────────────────────────────────────────

class TestFetchNewFormat:
    def test_returns_list_of_tuples(self):
        items = [_item_new("Company beats earnings", date(2024, 3, 1))]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            result = fetch("TEST")
        assert len(result) == 1
        pub_date, headline = result[0]
        assert isinstance(pub_date, date)
        assert headline == "Company beats earnings"

    def test_multiple_items(self):
        items = [_item_new(f"Headline {i}", date(2024, 1, i + 1)) for i in range(5)]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            result = fetch("TEST")
        assert len(result) == 5

    def test_appends_market_suffix(self):
        items = [_item_new("Strong results", date(2024, 1, 1))]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            fetch("VOLV_B", market_suffix=".ST")
            mock_ticker.assert_called_once_with("VOLV_B.ST")

    def test_no_suffix_for_us(self):
        items = [_item_new("Beats estimates", date(2024, 2, 1))]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            fetch("AAPL", market_suffix="")
            mock_ticker.assert_called_once_with("AAPL")


# ── Happy path (old format) ────────────────────────────────────────────────────

class TestFetchOldFormat:
    def test_returns_list_of_tuples(self):
        items = [_item_old("Dividend raised", date(2023, 6, 1))]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            result = fetch("TEST")
        assert len(result) == 1
        assert result[0][1] == "Dividend raised"
        assert result[0][0] == date(2023, 6, 1)

    def test_multiple_items(self):
        items = [_item_old(f"Old headline {i}", date(2023, 1, i + 1)) for i in range(3)]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            result = fetch("TEST")
        assert len(result) == 3


# ── Ordering ───────────────────────────────────────────────────────────────────

class TestOrdering:
    def test_sorted_oldest_first_new_format(self):
        items = [
            _item_new("Newest", date(2024, 12, 1)),
            _item_new("Oldest", date(2024, 1, 1)),
            _item_new("Middle", date(2024, 6, 1)),
        ]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            result = fetch("TEST")
        dates = [r[0] for r in result]
        assert dates == sorted(dates)

    def test_sorted_oldest_first_old_format(self):
        items = [
            _item_old("Newest", date(2024, 12, 1)),
            _item_old("Oldest", date(2024, 1, 1)),
        ]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            result = fetch("TEST")
        assert result[0][0] < result[1][0]

    def test_mixed_formats_sorted_correctly(self):
        items = [
            _item_new("New format", date(2024, 6, 1)),
            _item_old("Old format", date(2024, 3, 1)),
        ]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            result = fetch("TEST")
        assert result[0][0] == date(2024, 3, 1)
        assert result[1][0] == date(2024, 6, 1)


# ── Empty / missing data ───────────────────────────────────────────────────────

class TestEmptyAndMissingData:
    def test_empty_news_list_returns_empty(self):
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = []
            assert fetch("TEST") == []

    def test_none_news_returns_empty(self):
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = None
            assert fetch("TEST") == []

    def test_item_missing_title_skipped(self):
        items = [
            {"content": {"pubDate": _iso(date(2024, 1, 1))}},  # no title
            _item_new("Valid headline", date(2024, 1, 2)),
        ]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            result = fetch("TEST")
        assert len(result) == 1
        assert result[0][1] == "Valid headline"

    def test_item_missing_date_skipped(self):
        items = [
            {"content": {"title": "No date"}},
            _item_new("Has date", date(2024, 3, 1)),
        ]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            result = fetch("TEST")
        assert len(result) == 1
        assert result[0][1] == "Has date"

    def test_all_items_malformed_returns_empty(self):
        items = [{"unexpected": "structure"}, {}]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            assert fetch("TEST") == []


# ── Error handling ─────────────────────────────────────────────────────────────

class TestErrorHandling:
    def test_yfinance_exception_returns_empty(self):
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.side_effect = Exception("network error")
            assert fetch("TEST") == []

    def test_invalid_iso_string_item_skipped(self):
        items = [
            {"content": {"title": "Bad date", "pubDate": "not-a-date"}},
            _item_new("Good headline", date(2024, 6, 1)),
        ]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            result = fetch("TEST")
        assert len(result) == 1
        assert result[0][1] == "Good headline"

    def test_invalid_timestamp_item_skipped(self):
        items = [
            {"title": "Bad timestamp", "providerPublishTime": "not-a-number"},
            _item_new("Good headline", date(2024, 6, 1)),
        ]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            result = fetch("TEST")
        assert len(result) == 1


# ── Limit parameter ────────────────────────────────────────────────────────────

class TestLimit:
    def test_limit_caps_items_processed(self):
        items = [_item_new(f"H{i}", date(2024, 1, 1)) for i in range(20)]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            result = fetch("TEST", limit=5)
        assert len(result) <= 5

    def test_limit_zero_returns_empty(self):
        items = [_item_new("Some headline", date(2024, 1, 1))]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            assert fetch("TEST", limit=0) == []

    def test_default_limit_of_50(self):
        items = [_item_new(f"H{i}", date(2024, 1, 1)) for i in range(60)]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            result = fetch("TEST")
        assert len(result) <= 50


# ── Integration: output feeds scorer ──────────────────────────────────────────

class TestIntegrationWithScorer:
    def test_new_format_output_accepted_by_scorer(self):
        from src.sentiment.scorer import score as score_sentiment
        items = [
            _item_new("Revenue beats estimates strongly", date(2024, 3, 1)),
            _item_new("Dividend cut announced due to losses", date(2024, 3, 5)),
            _item_new("Management guidance raised for next quarter", date(2024, 3, 10)),
        ]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            headlines = fetch("TEST")

        result = score_sentiment("TEST", headlines)
        assert result.ticker == "TEST"
        assert -1.0 <= result.score <= 1.0
        assert result.status in {"positive", "negative", "neutral"}

    def test_old_format_output_accepted_by_scorer(self):
        from src.sentiment.scorer import score as score_sentiment
        items = [
            _item_old("Strong earnings growth reported", date(2023, 6, 1)),
            _item_old("Acquisition announced at premium", date(2023, 6, 5)),
        ]
        with patch("src.sentiment.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = items
            headlines = fetch("TEST")

        result = score_sentiment("TEST", headlines)
        assert isinstance(result.score, float)
