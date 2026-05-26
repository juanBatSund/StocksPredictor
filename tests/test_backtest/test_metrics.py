import math
import pytest
from datetime import date

from src.backtest.metrics import (
    PerformanceMetrics,
    build_metrics,
    compute_cagr,
    compute_max_drawdown,
    compute_volatility,
    compute_win_rate,
)

_START = date(2020, 1, 1)
_END = date(2022, 1, 1)   # 2-year window


# ── CAGR ──────────────────────────────────────────────────────────────────────

class TestComputeCAGR:
    def test_positive_return(self):
        # 100 → 121 over 2 years ≈ 10% CAGR
        cagr = compute_cagr(100.0, 121.0, 2.0)
        assert cagr == pytest.approx(0.10, abs=0.001)

    def test_negative_return(self):
        # 100 → 64 over 2 years = -20% CAGR
        cagr = compute_cagr(100.0, 64.0, 2.0)
        assert cagr == pytest.approx(-0.20, abs=0.001)

    def test_one_year_doubling(self):
        cagr = compute_cagr(1.0, 2.0, 1.0)
        assert cagr == pytest.approx(1.0)

    def test_zero_years_returns_none(self):
        assert compute_cagr(100.0, 120.0, 0.0) is None

    def test_negative_years_returns_none(self):
        assert compute_cagr(100.0, 120.0, -1.0) is None

    def test_period_under_one_month_returns_none(self):
        assert compute_cagr(100.0, 110.0, 0.05) is None

    def test_zero_initial_returns_none(self):
        assert compute_cagr(0.0, 100.0, 1.0) is None

    def test_zero_final_returns_none(self):
        assert compute_cagr(100.0, 0.0, 1.0) is None

    def test_flat_returns_zero(self):
        cagr = compute_cagr(100.0, 100.0, 1.0)
        assert cagr == pytest.approx(0.0)

    def test_result_is_rounded(self):
        cagr = compute_cagr(100.0, 121.0, 2.0)
        assert cagr is not None
        # Should have at most 6 decimal places
        assert round(cagr, 6) == cagr


# ── Max Drawdown ───────────────────────────────────────────────────────────────

class TestComputeMaxDrawdown:
    def test_flat_curve_no_drawdown(self):
        assert compute_max_drawdown([1.0, 1.0, 1.0]) == pytest.approx(0.0)

    def test_monotonic_up_no_drawdown(self):
        assert compute_max_drawdown([1.0, 1.1, 1.2, 1.5]) == pytest.approx(0.0)

    def test_monotonic_down_full_drawdown(self):
        dd = compute_max_drawdown([1.0, 0.8, 0.6, 0.4])
        assert dd == pytest.approx(0.60, abs=0.001)

    def test_peak_then_valley_then_recovery(self):
        # peak 1.5, valley 0.75 → drawdown 50%
        dd = compute_max_drawdown([1.0, 1.5, 0.75, 1.2])
        assert dd == pytest.approx(0.50, abs=0.001)

    def test_single_element(self):
        assert compute_max_drawdown([1.0]) == pytest.approx(0.0)

    def test_two_elements_up(self):
        assert compute_max_drawdown([1.0, 1.1]) == pytest.approx(0.0)

    def test_two_elements_down(self):
        dd = compute_max_drawdown([1.0, 0.9])
        assert dd == pytest.approx(0.10, abs=0.001)

    def test_multiple_peaks_uses_global(self):
        # [1.0, 2.0, 1.0, 3.0, 1.5] → biggest dd is from 3.0 to 1.5 = 50%
        dd = compute_max_drawdown([1.0, 2.0, 1.0, 3.0, 1.5])
        assert dd == pytest.approx(0.50, abs=0.001)

    def test_empty_returns_zero(self):
        assert compute_max_drawdown([]) == pytest.approx(0.0)


# ── Win Rate ───────────────────────────────────────────────────────────────────

class TestComputeWinRate:
    def test_all_winners(self):
        assert compute_win_rate([0.10, 0.20, 0.05]) == pytest.approx(1.0)

    def test_all_losers(self):
        assert compute_win_rate([-0.10, -0.05, -0.30]) == pytest.approx(0.0)

    def test_empty_returns_zero(self):
        assert compute_win_rate([]) == pytest.approx(0.0)

    def test_exactly_half(self):
        assert compute_win_rate([0.10, -0.10]) == pytest.approx(0.50)

    def test_mixed(self):
        # 2 of 5 positive
        result = compute_win_rate([0.10, -0.05, 0.20, -0.10, -0.15])
        assert result == pytest.approx(0.40, abs=0.001)

    def test_zero_return_counts_as_loss(self):
        assert compute_win_rate([0.0]) == pytest.approx(0.0)


# ── Volatility ─────────────────────────────────────────────────────────────────

class TestComputeVolatility:
    def test_single_value_returns_none(self):
        assert compute_volatility([0.10]) is None

    def test_empty_returns_none(self):
        assert compute_volatility([]) is None

    def test_zero_variance_returns_zero(self):
        vol = compute_volatility([0.10, 0.10, 0.10])
        assert vol == pytest.approx(0.0)

    def test_positive_for_varied_returns(self):
        vol = compute_volatility([0.10, -0.05, 0.20, -0.15])
        assert vol is not None
        assert vol > 0.0

    def test_higher_dispersion_gives_higher_vol(self):
        low = compute_volatility([0.01, 0.02, 0.01])
        high = compute_volatility([0.50, -0.40, 0.60])
        assert high > low  # type: ignore[operator]


# ── Build Metrics ──────────────────────────────────────────────────────────────

class TestBuildMetrics:
    def test_no_trades(self):
        m = build_metrics([], [], _START, _END)
        assert m.total_trades == 0
        assert m.win_rate == pytest.approx(0.0)
        assert m.cagr is None
        assert m.max_drawdown == pytest.approx(0.0)
        assert m.volatility is None
        assert m.avg_hold_years == pytest.approx(0.0)

    def test_single_winning_trade(self):
        m = build_metrics([0.20], [1.0], _START, _END)
        assert m.total_trades == 1
        assert m.winning_trades == 1
        assert m.losing_trades == 0
        assert m.win_rate == pytest.approx(1.0)
        assert m.avg_return_pct == pytest.approx(0.20)

    def test_single_losing_trade(self):
        m = build_metrics([-0.10], [1.0], _START, _END)
        assert m.winning_trades == 0
        assert m.losing_trades == 1
        assert m.win_rate == pytest.approx(0.0)

    def test_cagr_uses_full_period(self):
        # 2-year window; one trade returning 20% total → CAGR < 20% due to idle time
        m = build_metrics([0.20], [0.5], _START, _END)
        # equity goes 1.0 → 1.20; CAGR over 2 years = 1.20^(1/2) - 1 ≈ 9.5%
        assert m.cagr is not None
        assert m.cagr < 0.20   # less than trade return because idle time dilutes

    def test_multiple_trades_win_rate(self):
        returns = [0.15, -0.05, 0.10, -0.08, 0.20]
        m = build_metrics(returns, [0.4] * 5, _START, _END)
        assert m.winning_trades == 3
        assert m.losing_trades == 2
        assert m.win_rate == pytest.approx(0.60, abs=0.001)

    def test_max_drawdown_captured(self):
        # equity: 1.0 → 1.5 → 0.75 → 1.20 (50% drawdown from peak)
        returns = [0.50, -0.50, 0.60]
        m = build_metrics(returns, [0.5, 0.5, 0.5], _START, _END)
        assert m.max_drawdown == pytest.approx(0.50, abs=0.01)

    def test_volatility_none_for_single_trade(self):
        m = build_metrics([0.10], [1.0], _START, _END)
        assert m.volatility is None

    def test_volatility_present_for_two_trades(self):
        m = build_metrics([0.10, -0.10], [0.5, 0.5], _START, _END)
        assert m.volatility is not None

    def test_avg_hold_computed(self):
        m = build_metrics([0.10, 0.05], [1.0, 2.0], _START, _END)
        assert m.avg_hold_years == pytest.approx(1.5)
