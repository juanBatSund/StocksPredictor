import pytest
from datetime import date

from src.validation.baselines import BaselineResult, buy_and_hold_baseline, random_baseline


_START = date(2020, 1, 1)
_END = date(2022, 1, 1)

_PRICES = {
    date(2020, 1, 1): 100.0,
    date(2020, 7, 1): 110.0,
    date(2021, 1, 1): 115.0,
    date(2021, 7, 1): 120.0,
    date(2022, 1, 1): 130.0,
}
_DATES = sorted(_PRICES.keys())


# ── buy_and_hold_baseline ─────────────────────────────────────────────────────

class TestBuyAndHoldBaseline:
    def test_returns_baseline_result(self):
        r = buy_and_hold_baseline(_PRICES, _START, _END, "train", "SPY")
        assert isinstance(r, BaselineResult)

    def test_label_preserved(self):
        r = buy_and_hold_baseline(_PRICES, _START, _END, "train", "Custom Label")
        assert r.label == "Custom Label"

    def test_period_preserved(self):
        r = buy_and_hold_baseline(_PRICES, _START, _END, "validation", "SPY")
        assert r.period == "validation"

    def test_positive_return(self):
        r = buy_and_hold_baseline(_PRICES, _START, _END, "test", "SPY")
        # 100 → 130: +30%
        assert r.total_return == pytest.approx(0.30, abs=0.001)

    def test_negative_return(self):
        prices = {date(2020, 1, 1): 130.0, date(2022, 1, 1): 100.0}
        r = buy_and_hold_baseline(prices, _START, _END, "test", "SPY")
        assert r.total_return < 0

    def test_win_rate_one_for_positive(self):
        r = buy_and_hold_baseline(_PRICES, _START, _END, "test", "SPY")
        assert r.win_rate == pytest.approx(1.0)

    def test_win_rate_zero_for_negative(self):
        prices = {date(2020, 1, 1): 130.0, date(2022, 1, 1): 100.0}
        r = buy_and_hold_baseline(prices, _START, _END, "test", "SPY")
        assert r.win_rate == pytest.approx(0.0)

    def test_trade_count_is_one(self):
        r = buy_and_hold_baseline(_PRICES, _START, _END, "test", "SPY")
        assert r.trade_count == 1

    def test_missing_prices_returns_zero(self):
        r = buy_and_hold_baseline({}, _START, _END, "test", "SPY")
        assert r.cagr is None
        assert r.trade_count == 0

    def test_volatility_is_none(self):
        r = buy_and_hold_baseline(_PRICES, _START, _END, "test", "SPY")
        assert r.volatility is None

    def test_cagr_positive_for_positive_return(self):
        r = buy_and_hold_baseline(_PRICES, _START, _END, "test", "SPY")
        assert r.cagr is not None
        assert r.cagr > 0

    def test_uses_nearest_price_when_exact_missing(self):
        prices = {date(2020, 1, 3): 100.0, date(2021, 12, 31): 120.0}
        r = buy_and_hold_baseline(prices, _START, _END, "test", "SPY")
        # Should still compute a return using nearest available prices
        assert r.trade_count == 1


# ── random_baseline ────────────────────────────────────────────────────────────

class TestRandomBaseline:
    def test_deterministic_same_seed(self):
        r1 = random_baseline(_DATES, _PRICES, _START, _END, "test", 3, 1.0, seed=42)
        r2 = random_baseline(_DATES, _PRICES, _START, _END, "test", 3, 1.0, seed=42)
        assert r1.cagr == r2.cagr
        assert r1.trade_count == r2.trade_count
        assert r1.total_return == r2.total_return

    def test_different_seed_may_differ(self):
        r1 = random_baseline(_DATES, _PRICES, _START, _END, "test", 3, 1.0, seed=1)
        r2 = random_baseline(_DATES, _PRICES, _START, _END, "test", 3, 1.0, seed=999)
        # With very few unique dates, results might coincidentally match — just check structure
        assert isinstance(r1.cagr, (float, type(None)))
        assert isinstance(r2.cagr, (float, type(None)))

    def test_zero_trades_returns_empty(self):
        r = random_baseline(_DATES, _PRICES, _START, _END, "test", 0, 1.0, seed=42)
        assert r.trade_count == 0
        assert r.cagr is None

    def test_empty_dates_returns_empty(self):
        r = random_baseline([], {}, _START, _END, "test", 3, 1.0, seed=42)
        assert r.trade_count == 0
        assert r.cagr is None

    def test_period_preserved(self):
        r = random_baseline(_DATES, _PRICES, _START, _END, "validation", 2, 1.0, seed=42)
        assert r.period == "validation"

    def test_label_preserved(self):
        r = random_baseline(_DATES, _PRICES, _START, _END, "test", 2, 1.0, seed=42,
                            label="My Random")
        assert r.label == "My Random"

    def test_notes_contain_seed(self):
        r = random_baseline(_DATES, _PRICES, _START, _END, "test", 2, 1.0, seed=77)
        assert any("77" in n for n in r.notes)

    def test_cagr_not_none_when_trades_exist(self):
        r = random_baseline(_DATES, _PRICES, _START, _END, "test", 2, 0.5, seed=42)
        # 5 dates over 2 years — should be able to find trades
        if r.trade_count > 0:
            assert r.cagr is not None

    def test_win_rate_bounded(self):
        r = random_baseline(_DATES, _PRICES, _START, _END, "test", 3, 1.0, seed=42)
        assert 0.0 <= r.win_rate <= 1.0

    def test_max_drawdown_non_negative(self):
        r = random_baseline(_DATES, _PRICES, _START, _END, "test", 3, 1.0, seed=42)
        assert r.max_drawdown >= 0.0

    def test_volatility_none_for_single_completed_trade(self):
        r = random_baseline(_DATES, _PRICES, _START, _END, "test", 1, 1.0, seed=42)
        if r.trade_count <= 1:
            assert r.volatility is None
