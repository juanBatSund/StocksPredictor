import pytest
from datetime import date
from typing import Optional

from src.backtest.metrics import compute_cagr
from src.backtest.types import TradeRecord
from src.validation.comparison import (
    ComparisonRow,
    StrategyMetrics,
    WeaknessAnalysis,
    analyze_weaknesses,
    build_comparison_row,
    strategy_metrics_for_period,
)


# ── Factory helpers ────────────────────────────────────────────────────────────

def _trade(
    entry_str: str,
    exit_str: str,
    entry_price: float = 100.0,
    exit_price: float = 110.0,
    confidence: float = 0.75,
) -> TradeRecord:
    entry = date.fromisoformat(entry_str)
    exit_ = date.fromisoformat(exit_str)
    hold_days = (exit_ - entry).days
    hold_years = hold_days / 365.25
    ret = (exit_price - entry_price) / entry_price
    return TradeRecord(
        ticker="AAPL",
        entry_date=entry,
        exit_date=exit_,
        entry_price=entry_price,
        exit_price=exit_price,
        exit_reason="max_hold",
        entry_score=80.0,
        exit_score=70.0,
        entry_confidence=confidence,
        hold_days=hold_days,
        hold_years=round(hold_years, 4),
        return_pct=round(ret, 6),
        annualized_return=compute_cagr(entry_price, exit_price, hold_years),
    )


def _row(
    period: str = "test",
    strategy_cagr: Optional[float] = 0.10,
    spy_cagr: Optional[float] = 0.08,
    random_cagr: Optional[float] = 0.05,
    stock_bnh_cagr: Optional[float] = 0.07,
    trades: int = 3,
) -> ComparisonRow:
    return ComparisonRow(
        period=period,
        start_date=date(2022, 1, 1),
        end_date=date(2024, 1, 1),
        strategy_cagr=strategy_cagr,
        spy_cagr=spy_cagr,
        random_cagr=random_cagr,
        stock_bnh_cagr=stock_bnh_cagr,
        alpha_vs_spy=(
            round(strategy_cagr - spy_cagr, 6)
            if strategy_cagr is not None and spy_cagr is not None else None
        ),
        alpha_vs_random=(
            round(strategy_cagr - random_cagr, 6)
            if strategy_cagr is not None and random_cagr is not None else None
        ),
        alpha_vs_stock_bnh=(
            round(strategy_cagr - stock_bnh_cagr, 6)
            if strategy_cagr is not None and stock_bnh_cagr is not None else None
        ),
        strategy_drawdown=0.05,
        strategy_win_rate=0.67,
        strategy_trades=trades,
    )


# ── strategy_metrics_for_period ────────────────────────────────────────────────

class TestStrategyMetricsForPeriod:
    _START = date(2020, 1, 1)
    _END = date(2022, 1, 1)

    def test_empty_trades_zero_count(self):
        m = strategy_metrics_for_period([], self._START, self._END, "test")
        assert m.trade_count == 0

    def test_filters_by_entry_date(self):
        trades = [
            _trade("2019-06-01", "2020-06-01"),  # before period
            _trade("2020-06-01", "2021-06-01"),  # in period
            _trade("2022-06-01", "2023-06-01"),  # after period
        ]
        m = strategy_metrics_for_period(trades, self._START, self._END, "train")
        assert m.trade_count == 1

    def test_period_field_set(self):
        m = strategy_metrics_for_period([], self._START, self._END, "validation")
        assert m.period == "validation"

    def test_avg_confidence_computed(self):
        trades = [
            _trade("2020-06-01", "2021-06-01", confidence=0.60),
            _trade("2021-01-01", "2022-01-01", confidence=0.80),
        ]
        m = strategy_metrics_for_period(trades, self._START, self._END, "train")
        assert m.avg_confidence == pytest.approx(0.70, abs=0.001)

    def test_zero_confidence_when_no_trades(self):
        m = strategy_metrics_for_period([], self._START, self._END, "test")
        assert m.avg_confidence == pytest.approx(0.0)

    def test_total_return_is_compound(self):
        # +10% then +10% = +21% compound, not +20%
        trades = [
            _trade("2020-01-01", "2021-01-01", entry_price=100.0, exit_price=110.0),
            _trade("2021-01-01", "2022-01-01", entry_price=100.0, exit_price=110.0),
        ]
        m = strategy_metrics_for_period(trades, self._START, self._END, "train")
        assert m.total_return == pytest.approx(0.21, abs=0.001)


# ── build_comparison_row ───────────────────────────────────────────────────────

class TestBuildComparisonRow:
    def _strat(self, cagr=0.12) -> StrategyMetrics:
        return StrategyMetrics(
            period="test",
            start_date=date(2022, 1, 1),
            end_date=date(2024, 1, 1),
            cagr=cagr, max_drawdown=0.05,
            volatility=None, win_rate=0.67,
            total_return=0.24, trade_count=2,
            avg_confidence=0.75,
        )

    def test_alpha_vs_spy_computed(self):
        row = build_comparison_row("test", date(2022, 1, 1), date(2024, 1, 1),
                                   self._strat(0.12), spy_cagr=0.08,
                                   random_cagr=0.05, stock_bnh_cagr=0.09)
        assert row.alpha_vs_spy == pytest.approx(0.04, abs=1e-5)

    def test_alpha_none_when_spy_cagr_none(self):
        row = build_comparison_row("test", date(2022, 1, 1), date(2024, 1, 1),
                                   self._strat(0.12), spy_cagr=None,
                                   random_cagr=0.05, stock_bnh_cagr=0.09)
        assert row.alpha_vs_spy is None

    def test_alpha_none_when_strategy_cagr_none(self):
        row = build_comparison_row("test", date(2022, 1, 1), date(2024, 1, 1),
                                   self._strat(None), spy_cagr=0.08,
                                   random_cagr=0.05, stock_bnh_cagr=0.09)
        assert row.alpha_vs_spy is None

    def test_all_fields_present(self):
        row = build_comparison_row("train", date(2018, 1, 1), date(2021, 1, 1),
                                   self._strat(0.10), spy_cagr=0.09,
                                   random_cagr=0.06, stock_bnh_cagr=0.08)
        assert row.period == "train"
        assert row.strategy_cagr is not None
        assert row.strategy_trades == 2


# ── analyze_weaknesses ─────────────────────────────────────────────────────────

class TestAnalyzeWeaknesses:
    def _rows(self, train_cagr=0.10, val_cagr=0.09, test_cagr=0.08,
              spy_cagr=0.06, random_cagr=0.04) -> list[ComparisonRow]:
        return [
            _row("train",      strategy_cagr=train_cagr, spy_cagr=spy_cagr, random_cagr=random_cagr),
            _row("validation", strategy_cagr=val_cagr,   spy_cagr=spy_cagr, random_cagr=random_cagr),
            _row("test",       strategy_cagr=test_cagr,  spy_cagr=spy_cagr, random_cagr=random_cagr),
        ]

    def test_no_weaknesses_detected(self):
        rows = self._rows()
        w = analyze_weaknesses(rows, total_trades=10)
        assert w.underperforms_spy is False
        assert w.underperforms_random is False
        assert w.overfitting_flag is False
        assert "No critical weaknesses" in w.notes[0]

    def test_overfitting_detected(self):
        rows = self._rows(train_cagr=0.20, test_cagr=0.05)  # gap = 15% > 5%
        w = analyze_weaknesses(rows, total_trades=10)
        assert w.overfitting_flag is True

    def test_overfitting_not_flagged_below_threshold(self):
        rows = self._rows(train_cagr=0.12, test_cagr=0.10)  # gap = 2% < 5%
        w = analyze_weaknesses(rows, total_trades=10)
        assert w.overfitting_flag is False

    def test_underperforms_spy(self):
        rows = self._rows(test_cagr=0.04, spy_cagr=0.10)
        w = analyze_weaknesses(rows, total_trades=10)
        assert w.underperforms_spy is True

    def test_underperforms_random(self):
        rows = self._rows(test_cagr=0.02, random_cagr=0.07)
        w = analyze_weaknesses(rows, total_trades=10)
        assert w.underperforms_random is True

    def test_low_sample_flag(self):
        rows = self._rows()
        w = analyze_weaknesses(rows, total_trades=2, min_trades=3)
        assert w.low_sample_flag is True

    def test_low_sample_not_flagged_above_threshold(self):
        rows = self._rows()
        w = analyze_weaknesses(rows, total_trades=5, min_trades=3)
        assert w.low_sample_flag is False

    def test_notes_always_has_content(self):
        rows = self._rows()
        w = analyze_weaknesses(rows, total_trades=10)
        assert len(w.notes) >= 1

    def test_test_period_degradation(self):
        rows = self._rows(val_cagr=0.15, test_cagr=0.05)  # drop 10% > 3% threshold
        w = analyze_weaknesses(rows, total_trades=10)
        assert w.test_period_degradation is True

    def test_no_degradation_small_drop(self):
        rows = self._rows(val_cagr=0.10, test_cagr=0.09)  # drop 1% < 3%
        w = analyze_weaknesses(rows, total_trades=10)
        assert w.test_period_degradation is False

    def test_no_test_row_no_underperforms(self):
        rows = [_row("train"), _row("validation")]
        w = analyze_weaknesses(rows, total_trades=10)
        assert w.underperforms_spy is False

    def test_none_strategy_cagr_no_overfitting(self):
        rows = [
            _row("train", strategy_cagr=None),
            _row("validation", strategy_cagr=None),
            _row("test", strategy_cagr=None),
        ]
        w = analyze_weaknesses(rows, total_trades=0)
        assert w.overfitting_flag is False
