import os
import time
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

from config.markets import MARKETS
from src.data.cache import _load, _path, _save, get, invalidate
from src.data.models import Fundamentals, PriceRecord, StockData

US = MARKETS["US"]
SE = MARKETS["SE"]


def _make_stock_data(ticker="AAPL", market_code="US", missing=None) -> StockData:
    return StockData(
        ticker=ticker,
        market_code=market_code,
        fetched_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        as_of_date=None,
        prices=[
            PriceRecord(date=date(2024, 1, 10), open=183.92, high=185.15,
                        low=182.73, close=184.40, volume=53234100),
        ],
        fundamentals=Fundamentals(
            roe=0.17, debt_to_equity=0.80, free_cash_flow=89_900_000_000,
            revenue_growth_5y=0.092, earnings_growth_5y=0.11,
            dividend_yield=0.0051, payout_ratio=0.158,
            dividend_growth_streak_years=None, pe_ratio=30.4, pe_5y_avg=28.1,
        ),
        missing_fields=missing or [],
    )


class TestSaveLoad:
    def test_round_trip(self, tmp_path):
        original = _make_stock_data()
        cache_file = tmp_path / "AAPL.json"
        _save(cache_file, original)
        loaded = _load(cache_file)

        assert loaded.ticker == original.ticker
        assert loaded.market_code == "US"
        assert loaded.fetched_at == original.fetched_at
        assert loaded.prices[0].close == pytest.approx(184.40)
        assert loaded.fundamentals.roe == pytest.approx(0.17)

    def test_missing_fields_preserved(self, tmp_path):
        original = _make_stock_data(missing=["returnOnEquity", "freeCashflow"])
        cache_file = tmp_path / "AAPL.json"
        _save(cache_file, original)
        loaded = _load(cache_file)

        assert loaded.missing_fields == ["returnOnEquity", "freeCashflow"]

    def test_as_of_date_preserved(self, tmp_path):
        original = _make_stock_data()
        original.as_of_date = date(2023, 6, 1)
        cache_file = tmp_path / "AAPL_2023-06-01.json"
        _save(cache_file, original)
        loaded = _load(cache_file)

        assert loaded.as_of_date == date(2023, 6, 1)

    def test_old_cache_without_market_code_defaults_to_us(self, tmp_path):
        # Simulate a pre-market cache file that has no market_code field
        import json
        data = _make_stock_data()
        cache_file = tmp_path / "AAPL.json"
        _save(cache_file, data)
        raw = json.loads(cache_file.read_text())
        del raw["market_code"]
        cache_file.write_text(json.dumps(raw))

        loaded = _load(cache_file)
        assert loaded.market_code == "US"


class TestCachePath:
    def test_us_ticker_has_no_suffix(self, tmp_path):
        with patch("src.data.cache.CACHE_DIR", tmp_path):
            p = _path("AAPL", US, None)
        assert p.name == "AAPL.json"

    def test_swedish_ticker_includes_exchange(self, tmp_path):
        with patch("src.data.cache.CACHE_DIR", tmp_path):
            p = _path("VOLV-B", SE, None)
        assert p.name == "VOLV-B_ST.json"

    def test_date_appended_to_filename(self, tmp_path):
        with patch("src.data.cache.CACHE_DIR", tmp_path):
            p = _path("AAPL", US, date(2023, 6, 1))
        assert p.name == "AAPL_2023-06-01.json"


class TestGetWithCache:
    def test_returns_cached_data_when_fresh(self, tmp_path):
        data = _make_stock_data()
        cache_file = tmp_path / "AAPL.json"
        _save(cache_file, data)

        with patch("src.data.cache.CACHE_DIR", tmp_path), \
             patch("src.data.cache.fetch") as mock_fetch:
            result = get("AAPL", US)
            mock_fetch.assert_not_called()

        assert result.ticker == "AAPL"

    def test_fetches_when_cache_missing(self, tmp_path):
        fresh_data = _make_stock_data()

        with patch("src.data.cache.CACHE_DIR", tmp_path), \
             patch("src.data.cache.fetch", return_value=fresh_data) as mock_fetch:
            result = get("AAPL", US)
            mock_fetch.assert_called_once_with("AAPL", US, None)

        assert result.ticker == "AAPL"

    def test_fetches_when_cache_stale(self, tmp_path):
        data = _make_stock_data()
        cache_file = tmp_path / "AAPL.json"
        _save(cache_file, data)
        stale_time = time.time() - 90_000
        os.utime(cache_file, (stale_time, stale_time))

        fresh_data = _make_stock_data()
        with patch("src.data.cache.CACHE_DIR", tmp_path), \
             patch("src.data.cache.fetch", return_value=fresh_data) as mock_fetch:
            get("AAPL", US)
            mock_fetch.assert_called_once()

    def test_swedish_and_us_tickers_use_separate_cache_files(self, tmp_path):
        us_data = _make_stock_data("AAPL", "US")
        se_data = _make_stock_data("AAPL", "SE")
        _save(tmp_path / "AAPL.json", us_data)
        _save(tmp_path / "AAPL_ST.json", se_data)

        with patch("src.data.cache.CACHE_DIR", tmp_path), \
             patch("src.data.cache.fetch") as mock_fetch:
            get("AAPL", US)
            get("AAPL", SE)
            mock_fetch.assert_not_called()


class TestInvalidate:
    def test_removes_cache_file(self, tmp_path):
        data = _make_stock_data()
        cache_file = tmp_path / "AAPL.json"
        _save(cache_file, data)

        with patch("src.data.cache.CACHE_DIR", tmp_path):
            invalidate("AAPL", US)

        assert not cache_file.exists()

    def test_noop_when_file_absent(self, tmp_path):
        with patch("src.data.cache.CACHE_DIR", tmp_path):
            invalidate("NONEXISTENT", US)  # must not raise
