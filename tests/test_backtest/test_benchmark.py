import pytest
from datetime import date

from src.backtest.benchmark import (
    BenchmarkComparison,
    compare,
    compute_benchmark_cagr,
    nearest_price,
)


# ── Nearest price lookup ───────────────────────────────────────────────────────

class TestNearestPrice:
    def test_exact_date_match(self):
        prices = {date(2021, 1, 1): 100.0, date(2021, 6, 1): 110.0}
        assert nearest_price(prices, date(2021, 6, 1)) == pytest.approx(110.0)

    def test_nearest_before_target(self):
        prices = {date(2021, 1, 1): 100.0, date(2021, 3, 1): 105.0}
        # target is between two available dates — picks the latest before target
        result = nearest_price(prices, date(2021, 4, 1))
        assert result == pytest.approx(105.0)

    def test_no_date_before_uses_earliest(self):
        prices = {date(2021, 6, 1): 110.0, date(2021, 9, 1): 120.0}
        # target is before all prices — falls back to earliest
        result = nearest_price(prices, date(2020, 1, 1))
        assert result == pytest.approx(110.0)

    def test_empty_dict_returns_none(self):
        assert nearest_price({}, date(2021, 1, 1)) is None

    def test_single_date_always_returns(self):
        prices = {date(2021, 1, 1): 100.0}
        assert nearest_price(prices, date(2022, 1, 1)) == pytest.approx(100.0)
        assert nearest_price(prices, date(2019, 1, 1)) == pytest.approx(100.0)


# ── Benchmark CAGR ─────────────────────────────────────────────────────────────

class TestBenchmarkCAGR:
    def test_positive_return(self):
        prices = {
            date(2020, 1, 1): 100.0,
            date(2022, 1, 1): 121.0,  # 10% CAGR over 2 years
        }
        cagr = compute_benchmark_cagr(prices, date(2020, 1, 1), date(2022, 1, 1))
        assert cagr == pytest.approx(0.10, abs=0.001)

    def test_negative_return(self):
        prices = {
            date(2020, 1, 1): 100.0,
            date(2022, 1, 1): 64.0,  # -20% CAGR over 2 years
        }
        cagr = compute_benchmark_cagr(prices, date(2020, 1, 1), date(2022, 1, 1))
        assert cagr == pytest.approx(-0.20, abs=0.001)

    def test_start_equals_end_returns_none(self):
        prices = {date(2021, 1, 1): 100.0}
        cagr = compute_benchmark_cagr(prices, date(2021, 1, 1), date(2021, 1, 1))
        assert cagr is None

    def test_empty_prices_returns_none(self):
        cagr = compute_benchmark_cagr({}, date(2020, 1, 1), date(2022, 1, 1))
        assert cagr is None

    def test_uses_nearest_price_for_missing_dates(self):
        prices = {
            date(2020, 1, 3): 100.0,  # slightly after start
            date(2021, 12, 31): 110.0,  # slightly before end
        }
        cagr = compute_benchmark_cagr(prices, date(2020, 1, 1), date(2022, 1, 1))
        assert cagr is not None


# ── Compare ────────────────────────────────────────────────────────────────────

class TestCompare:
    _PRICES = {date(2020, 1, 1): 100.0, date(2022, 1, 1): 121.0}

    def test_outperforms_when_alpha_positive(self):
        result = compare(0.20, self._PRICES, date(2020, 1, 1), date(2022, 1, 1))
        # benchmark ~10%, strategy 20% → outperforms
        assert result.outperforms is True
        assert result.alpha is not None
        assert result.alpha > 0

    def test_underperforms_when_alpha_negative(self):
        result = compare(0.05, self._PRICES, date(2020, 1, 1), date(2022, 1, 1))
        # benchmark ~10%, strategy 5% → underperforms
        assert result.outperforms is False
        assert result.alpha is not None
        assert result.alpha < 0

    def test_none_strategy_cagr(self):
        result = compare(None, self._PRICES, date(2020, 1, 1), date(2022, 1, 1))
        assert result.alpha is None
        assert result.outperforms is None

    def test_empty_benchmark_prices(self):
        result = compare(0.10, {}, date(2020, 1, 1), date(2022, 1, 1))
        assert result.benchmark_cagr is None
        assert result.alpha is None

    def test_alpha_computed_as_difference(self):
        result = compare(0.15, self._PRICES, date(2020, 1, 1), date(2022, 1, 1))
        assert result.alpha is not None
        assert result.alpha == pytest.approx(
            result.strategy_cagr - result.benchmark_cagr, abs=1e-6
        )

    def test_benchmark_label_preserved(self):
        result = compare(0.10, self._PRICES, date(2020, 1, 1), date(2022, 1, 1), "QQQ")
        assert result.benchmark_label == "QQQ"

    def test_dates_preserved(self):
        start = date(2020, 1, 1)
        end = date(2022, 1, 1)
        result = compare(0.10, self._PRICES, start, end)
        assert result.start_date == start
        assert result.end_date == end

    def test_strategy_cagr_preserved(self):
        result = compare(0.12, self._PRICES, date(2020, 1, 1), date(2022, 1, 1))
        assert result.strategy_cagr == pytest.approx(0.12)
