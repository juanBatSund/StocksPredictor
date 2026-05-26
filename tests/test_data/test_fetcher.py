from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from config.markets import MARKETS
from src.data.fetcher import _compute_dividend_streak, fetch
from src.data.models import StockData

US = MARKETS["US"]
SE = MARKETS["SE"]


def _make_info() -> dict:
    return {
        "returnOnEquity": 0.17,
        "debtToEquity": 80.0,
        "freeCashflow": 89_900_000_000,
        "revenueGrowth": 0.092,
        "earningsGrowth": 0.11,
        "dividendYield": 0.0051,
        "payoutRatio": 0.158,
        "trailingPE": 30.4,
        "fiveYearAvgDividendYield": 28.1,
    }


def _make_price_df() -> pd.DataFrame:
    data = {
        "Open":   [183.92, 184.35],
        "High":   [185.15, 186.00],
        "Low":    [182.73, 183.62],
        "Close":  [184.40, 185.59],
        "Volume": [53234100, 47547300],
    }
    return pd.DataFrame(data, index=pd.to_datetime(["2024-01-10", "2024-01-11"]))


@patch("src.data.fetcher.yf.Ticker")
def test_fetch_returns_stock_data(mock_ticker):
    mock_instance = MagicMock()
    mock_instance.info = _make_info()
    mock_instance.history.return_value = _make_price_df()
    mock_ticker.return_value = mock_instance

    result = fetch("AAPL", US)

    assert isinstance(result, StockData)
    assert result.ticker == "AAPL"
    assert result.market_code == "US"
    assert len(result.prices) == 2
    assert result.latest_price == pytest.approx(185.59)
    assert result.fundamentals.roe == pytest.approx(0.17)
    assert result.fundamentals.debt_to_equity == pytest.approx(0.80)


@patch("src.data.fetcher.yf.Ticker")
def test_fetch_appends_market_suffix(mock_ticker):
    # Swedish tickers must be fetched with ".ST" suffix
    mock_instance = MagicMock()
    mock_instance.info = _make_info()
    mock_instance.history.return_value = _make_price_df()
    mock_ticker.return_value = mock_instance

    result = fetch("VOLV-B", SE)

    assert result.ticker == "VOLV-B"       # stored without suffix
    assert result.market_code == "SE"
    mock_ticker.assert_any_call("VOLV-B.ST")


@patch("src.data.fetcher.yf.Ticker")
def test_fetch_truncates_prices_by_as_of_date(mock_ticker):
    mock_instance = MagicMock()
    mock_instance.info = _make_info()
    mock_instance.history.return_value = _make_price_df()
    mock_ticker.return_value = mock_instance

    result = fetch("AAPL", US, as_of_date=date(2024, 1, 10))

    assert len(result.prices) == 1
    assert result.prices[0].date == date(2024, 1, 10)


@patch("src.data.fetcher.yf.Ticker")
def test_fetch_records_missing_fields(mock_ticker):
    info = _make_info()
    del info["returnOnEquity"]
    del info["freeCashflow"]

    mock_instance = MagicMock()
    mock_instance.info = info
    mock_instance.history.return_value = _make_price_df()
    mock_ticker.return_value = mock_instance

    result = fetch("AAPL", US)

    assert "returnOnEquity" in result.missing_fields
    assert "freeCashflow" in result.missing_fields
    assert result.fundamentals.roe is None
    assert not result.has_complete_fundamentals


@patch("src.data.fetcher.yf.Ticker")
def test_fetch_handles_empty_price_history(mock_ticker):
    mock_instance = MagicMock()
    mock_instance.info = _make_info()
    mock_instance.history.return_value = pd.DataFrame()
    mock_ticker.return_value = mock_instance

    result = fetch("AAPL", US)

    assert result.prices == []
    assert result.latest_price is None


@patch("src.data.fetcher.yf.Ticker")
def test_fetch_handles_api_exception(mock_ticker):
    mock_instance = MagicMock()
    mock_instance.info = {}
    mock_instance.history.side_effect = Exception("network error")
    mock_ticker.return_value = mock_instance

    result = fetch("AAPL", US)

    assert result.prices == []
    assert result.fundamentals.roe is None


# ── dividend streak tests ─────────────────────────────────────────────────────

def _make_dividends(year_value_pairs: list[tuple[int, float]]) -> pd.Series:
    dates = pd.to_datetime([f"{y}-06-15" for y, _ in year_value_pairs])
    return pd.Series([v for _, v in year_value_pairs], index=dates, name="Dividends")


@patch("src.data.fetcher.yf.Ticker")
def test_streak_consistent_growth(mock_ticker):
    mock_ticker.return_value.dividends = _make_dividends([
        (2019, 1.00), (2020, 1.10), (2021, 1.20), (2022, 1.30), (2023, 1.40),
    ])
    assert _compute_dividend_streak("JNJ") == 4


@patch("src.data.fetcher.yf.Ticker")
def test_streak_resets_after_cut(mock_ticker):
    mock_ticker.return_value.dividends = _make_dividends([
        (2018, 1.00), (2019, 1.10), (2020, 1.20),
        (2021, 0.80),
        (2022, 1.00), (2023, 1.10),
    ])
    assert _compute_dividend_streak("JNJ") == 2


@patch("src.data.fetcher.yf.Ticker")
def test_streak_resets_on_suspended_year(mock_ticker):
    mock_ticker.return_value.dividends = _make_dividends([
        (2018, 1.00), (2019, 1.10),
        (2021, 1.20), (2022, 1.30), (2023, 1.40),
    ])
    assert _compute_dividend_streak("JNJ") == 2


@patch("src.data.fetcher.yf.Ticker")
def test_streak_flat_dividend_counts(mock_ticker):
    mock_ticker.return_value.dividends = _make_dividends([
        (2020, 1.00), (2021, 1.00), (2022, 1.00), (2023, 1.00),
    ])
    assert _compute_dividend_streak("JNJ") == 3


@patch("src.data.fetcher.yf.Ticker")
def test_streak_no_dividends_returns_zero(mock_ticker):
    mock_ticker.return_value.dividends = pd.Series(dtype=float)
    assert _compute_dividend_streak("JNJ") == 0


@patch("src.data.fetcher.yf.Ticker")
def test_streak_single_year_returns_zero(mock_ticker):
    mock_ticker.return_value.dividends = _make_dividends([(2023, 1.00)])
    assert _compute_dividend_streak("JNJ") == 0


@patch("src.data.fetcher.yf.Ticker")
def test_streak_api_exception_returns_zero(mock_ticker):
    with patch("src.data.fetcher.yf.Ticker") as mock_t:
        type(mock_t.return_value).dividends = property(
            lambda self: (_ for _ in ()).throw(Exception("timeout"))
        )
        assert _compute_dividend_streak("JNJ") == 0


@patch("src.data.fetcher.yf.Ticker")
def test_streak_stored_on_fundamentals(mock_ticker):
    mock_instance = MagicMock()
    mock_instance.info = _make_info()
    mock_instance.history.return_value = _make_price_df()
    mock_instance.dividends = _make_dividends([
        (2019, 1.00), (2020, 1.10), (2021, 1.20), (2022, 1.30), (2023, 1.40),
    ])
    mock_ticker.return_value = mock_instance

    result = fetch("JNJ", US)
    assert result.fundamentals.dividend_growth_streak_years == 4
