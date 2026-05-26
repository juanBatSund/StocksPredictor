import pytest
from datetime import date
from typing import Optional

from src.backtest.audit import LeakageAudit
from src.backtest.benchmark import BenchmarkComparison
from src.backtest.engine import BacktestResult
from src.backtest.metrics import build_metrics, compute_cagr
from src.backtest.types import HistoricalSnapshot, TradeRecord
from src.decision.engine import ConfidenceBreakdown, DecisionResult
from src.validation.splitter import PeriodSplit, split_periods
from src.validation.validator import ValidationResult, validate


# ── Factory helpers ────────────────────────────────────────────────────────────

def _dr(score: float = 70.0, decision: str = "WATCH", confidence: float = 0.70) -> DecisionResult:
    return DecisionResult(
        ticker="AAPL", decision=decision, score=score,
        quality_score=score, growth_score=score, dividend_score=score,
        valuation_score=score, valuation_status="fair",
        confidence=confidence,
        confidence_breakdown=ConfidenceBreakdown(0.8, 0.5, 0.5, 0.5, confidence),
        gates=[], contributing_factors=[], rejected_factors=[],
        uncertainty_flags=[], sentiment_score=None, sentiment_status=None,
        sentiment_trend=None, sentiment_confidence=None,
        macro_category=None, macro_sector_direction=None,
        macro_sector_strength=None, macro_confidence=None,
        reasoning_trace=[], notes=[],
    )


def _snap(date_str: str, price: float = 100.0, decision: str = "WATCH",
          score: float = 70.0) -> HistoricalSnapshot:
    return HistoricalSnapshot(
        as_of_date=date.fromisoformat(date_str),
        ticker="AAPL", price=price,
        decision=_dr(score=score, decision=decision),
    )


def _trade(entry_str: str, exit_str: str,
           entry_price: float = 100.0, exit_price: float = 110.0,
           confidence: float = 0.75) -> TradeRecord:
    entry = date.fromisoformat(entry_str)
    exit_ = date.fromisoformat(exit_str)
    hold_days = (exit_ - entry).days
    hold_years = hold_days / 365.25
    ret = (exit_price - entry_price) / entry_price
    return TradeRecord(
        ticker="AAPL", entry_date=entry, exit_date=exit_,
        entry_price=entry_price, exit_price=exit_price,
        exit_reason="max_hold", entry_score=80.0, exit_score=70.0,
        entry_confidence=confidence, hold_days=hold_days,
        hold_years=round(hold_years, 4), return_pct=round(ret, 6),
        annualized_return=compute_cagr(entry_price, exit_price, hold_years),
    )


def _backtest(
    start: date = date(2018, 1, 1),
    end: date = date(2024, 1, 1),
    trades: Optional[list[TradeRecord]] = None,
    snapshots: Optional[list[HistoricalSnapshot]] = None,
) -> BacktestResult:
    trades = trades or []
    snapshots = snapshots or []
    metrics = build_metrics(
        [t.return_pct for t in trades],
        [t.hold_years for t in trades],
        start, end,
    )
    return BacktestResult(
        ticker="AAPL", start_date=start, end_date=end,
        snapshots=snapshots, trades=trades, metrics=metrics,
        benchmark=BenchmarkComparison("SPY", start, end, None, None, None, None),
        leakage_audit=LeakageAudit(True, [], 0, []),
        confidence_evolution=[], decisions_over_time=[],
        reasoning_trace=[], notes=[],
    )


# SPY prices: 6-year window 2018–2024
_SPY = {
    date(2018, 1, 1): 268.0,
    date(2019, 1, 1): 249.0,
    date(2020, 1, 1): 323.0,
    date(2021, 1, 1): 374.0,
    date(2022, 1, 1): 454.0,
    date(2023, 1, 1): 383.0,
    date(2024, 1, 1): 472.0,
}


# ── Basic structure ────────────────────────────────────────────────────────────

class TestValidationResultStructure:
    def _run(self) -> ValidationResult:
        bt = _backtest(
            snapshots=[_snap("2018-01-01", price=100.0), _snap("2024-01-01", price=150.0)],
            trades=[_trade("2018-06-01", "2019-06-01", 100.0, 115.0)],
        )
        return validate("AAPL", bt, _SPY)

    def test_returns_validation_result(self):
        assert isinstance(self._run(), ValidationResult)

    def test_ticker_preserved(self):
        assert self._run().ticker == "AAPL"

    def test_three_comparison_rows(self):
        r = self._run()
        assert len(r.comparison_table) == 3

    def test_periods_in_table(self):
        r = self._run()
        periods = {row.period for row in r.comparison_table}
        assert periods == {"train", "validation", "test"}

    def test_strategy_metrics_has_three_periods(self):
        r = self._run()
        assert set(r.strategy_metrics.keys()) == {"train", "validation", "test"}

    def test_nine_baseline_results(self):
        # 3 baselines × 3 periods
        r = self._run()
        assert len(r.baseline_results) == 9

    def test_notes_has_five_entries(self):
        r = self._run()
        assert len(r.notes) == 5


# ── Period split ───────────────────────────────────────────────────────────────

class TestPeriodSplitBehavior:
    def _bt(self) -> BacktestResult:
        return _backtest(
            snapshots=[_snap("2018-01-01", price=100.0), _snap("2024-01-01", price=130.0)],
        )

    def test_auto_split_uses_backtest_dates(self):
        r = validate("AAPL", self._bt(), _SPY)
        assert r.period_split.train_start == date(2018, 1, 1)
        assert r.period_split.test_end == date(2024, 1, 1)

    def test_custom_split_respected(self):
        custom = split_periods(date(2018, 1, 1), date(2024, 1, 1), 0.50, 0.25)
        r = validate("AAPL", self._bt(), _SPY, period_split=custom)
        assert r.period_split.train_start == date(2018, 1, 1)
        # 50% train → train roughly 3 years
        assert r.period_split.train_years == pytest.approx(3.0, abs=0.15)

    def test_period_split_stored_in_result(self):
        r = validate("AAPL", self._bt(), _SPY)
        assert isinstance(r.period_split, PeriodSplit)


# ── Baselines ──────────────────────────────────────────────────────────────────

class TestBaselinesInResult:
    def _bt_with_snaps(self) -> BacktestResult:
        snaps = [
            _snap("2018-01-01", price=100.0),
            _snap("2020-01-01", price=120.0),
            _snap("2022-01-01", price=140.0),
            _snap("2024-01-01", price=160.0),
        ]
        return _backtest(snapshots=snaps)

    def test_spy_baselines_present(self):
        r = validate("AAPL", self._bt_with_snaps(), _SPY, benchmark_label="SPY")
        spy_baselines = [b for b in r.baseline_results if b.label == "SPY"]
        assert len(spy_baselines) == 3  # one per period

    def test_stock_bnh_baselines_present(self):
        r = validate("AAPL", self._bt_with_snaps(), _SPY)
        bnh = [b for b in r.baseline_results if b.label == "stock buy-and-hold"]
        assert len(bnh) == 3

    def test_random_baselines_present(self):
        r = validate("AAPL", self._bt_with_snaps(), _SPY)
        rnd = [b for b in r.baseline_results if b.label == "Random strategy"]
        assert len(rnd) == 3

    def test_benchmark_label_used(self):
        r = validate("AAPL", self._bt_with_snaps(), _SPY, benchmark_label="QQQ")
        qqq = [b for b in r.baseline_results if b.label == "QQQ"]
        assert len(qqq) == 3


# ── Reproducibility ────────────────────────────────────────────────────────────

class TestReproducibility:
    def _bt(self) -> BacktestResult:
        return _backtest(
            snapshots=[_snap("2018-01-01", price=100.0), _snap("2024-01-01", price=130.0)],
        )

    def test_same_seed_same_result(self):
        r1 = validate("AAPL", self._bt(), _SPY, random_seed=42)
        r2 = validate("AAPL", self._bt(), _SPY, random_seed=42)
        assert r1.reproducibility_audit.random_baseline_reproducible is True

    def test_reproducibility_audit_passes(self):
        r = validate("AAPL", self._bt(), _SPY)
        assert r.reproducibility_audit.random_baseline_reproducible is True

    def test_seed_recorded_in_audit(self):
        r = validate("AAPL", self._bt(), _SPY, random_seed=123)
        assert r.reproducibility_audit.seed_used == 123

    def test_time_windows_identical(self):
        r = validate("AAPL", self._bt(), _SPY)
        assert r.reproducibility_audit.identical_time_windows is True


# ── Weakness analysis ──────────────────────────────────────────────────────────

class TestWeaknessAnalysis:
    def test_weakness_analysis_present(self):
        bt = _backtest(
            snapshots=[_snap("2018-01-01", price=100.0), _snap("2024-01-01", price=130.0)],
        )
        r = validate("AAPL", bt, _SPY)
        assert isinstance(r.weakness_analysis, WeaknessAnalysis_)

    def test_low_sample_for_no_trades(self):
        bt = _backtest(
            snapshots=[_snap("2018-01-01", price=100.0), _snap("2024-01-01", price=130.0)],
            trades=[],
        )
        r = validate("AAPL", bt, _SPY)
        assert r.weakness_analysis.low_sample_flag is True

    def test_no_weaknesses_message(self):
        bt = _backtest(
            snapshots=[_snap("2018-01-01", price=100.0), _snap("2024-01-01", price=130.0)],
        )
        r = validate("AAPL", bt, _SPY)
        # 0 trades → low sample flag set; notes should mention it
        assert len(r.weakness_analysis.notes) >= 1


# ── Determinism ────────────────────────────────────────────────────────────────

class TestDeterminism:
    def _bt(self) -> BacktestResult:
        return _backtest(
            snapshots=[_snap("2018-01-01", price=100.0),
                       _snap("2021-01-01", price=130.0),
                       _snap("2024-01-01", price=160.0)],
            trades=[_trade("2018-06-01", "2020-06-01", 100.0, 120.0)],
        )

    def test_same_inputs_same_output(self):
        r1 = validate("AAPL", self._bt(), _SPY, random_seed=42)
        r2 = validate("AAPL", self._bt(), _SPY, random_seed=42)
        for row1, row2 in zip(r1.comparison_table, r2.comparison_table):
            assert row1.strategy_cagr == row2.strategy_cagr
            assert row1.alpha_vs_spy == row2.alpha_vs_spy

    def test_notes_ticker_present(self):
        r = validate("AAPL", self._bt(), _SPY)
        assert any("AAPL" in n for n in r.notes)


# Import WeaknessAnalysis for structural check
from src.validation.comparison import WeaknessAnalysis as WeaknessAnalysis_
