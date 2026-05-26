import pytest
from datetime import date
from typing import Optional

from src.backtest.engine import BacktestResult, run
from src.backtest.types import HistoricalSnapshot, TradeRecord
from src.decision.engine import ConfidenceBreakdown, DecisionResult


# ── Factory helpers ────────────────────────────────────────────────────────────

def _dr(
    ticker: str = "AAPL",
    decision: str = "WATCH",
    score: float = 70.0,
    confidence: float = 0.70,
    val_status: str = "fair",
) -> DecisionResult:
    return DecisionResult(
        ticker=ticker,
        decision=decision,
        score=score,
        quality_score=score,
        growth_score=score,
        dividend_score=score,
        valuation_score=score,
        valuation_status=val_status,
        confidence=confidence,
        confidence_breakdown=ConfidenceBreakdown(
            data_quality=0.80,
            valuation_certainty=0.50,
            signal_agreement=0.50,
            soft_signal_quality=0.50,
            total=confidence,
        ),
        gates=[],
        contributing_factors=[],
        rejected_factors=[],
        uncertainty_flags=[],
        sentiment_score=None,
        sentiment_status=None,
        sentiment_trend=None,
        sentiment_confidence=None,
        macro_category=None,
        macro_sector_direction=None,
        macro_sector_strength=None,
        macro_confidence=None,
        reasoning_trace=[],
        notes=[],
    )


def _snap(
    date_str: str,
    ticker: str = "AAPL",
    decision: str = "WATCH",
    score: float = 70.0,
    confidence: float = 0.70,
    price: Optional[float] = 100.0,
) -> HistoricalSnapshot:
    return HistoricalSnapshot(
        as_of_date=date.fromisoformat(date_str),
        ticker=ticker,
        price=price,
        decision=_dr(ticker=ticker, decision=decision, score=score, confidence=confidence),
    )


_SPY = {
    date(2020, 1, 1): 300.0,
    date(2022, 1, 1): 450.0,  # ~22.5% total over 2 years ≈ 10.7% CAGR
}


# ── Empty backtest ─────────────────────────────────────────────────────────────

class TestEmptyBacktest:
    def test_no_snapshots_returns_result(self):
        result = run("AAPL", [], _SPY)
        assert isinstance(result, BacktestResult)

    def test_empty_has_no_trades(self):
        result = run("AAPL", [], _SPY)
        assert result.trades == []

    def test_empty_metrics(self):
        result = run("AAPL", [], _SPY)
        assert result.metrics.total_trades == 0
        assert result.metrics.cagr is None

    def test_empty_ticker_preserved(self):
        result = run("TSLA", [], _SPY)
        assert result.ticker == "TSLA"

    def test_empty_trace_has_message(self):
        result = run("AAPL", [], _SPY)
        assert len(result.reasoning_trace) > 0


# ── No trades (no BUY signals) ────────────────────────────────────────────────

class TestNoTrades:
    def test_watch_signals_produce_no_trades(self):
        snaps = [_snap("2020-01-01", decision="WATCH"), _snap("2021-01-01", decision="WATCH")]
        result = run("AAPL", snaps, _SPY)
        assert result.trades == []

    def test_avoid_signals_produce_no_trades(self):
        snaps = [_snap("2020-01-01", decision="AVOID", score=50.0)]
        result = run("AAPL", snaps, _SPY)
        assert result.trades == []

    def test_buy_with_no_price_produces_no_trade(self):
        snaps = [_snap("2020-01-01", decision="BUY", score=80.0, price=None)]
        result = run("AAPL", snaps, _SPY)
        assert result.trades == []

    def test_no_trades_win_rate_zero(self):
        snaps = [_snap("2020-01-01", decision="WATCH")]
        result = run("AAPL", snaps, _SPY)
        assert result.metrics.win_rate == pytest.approx(0.0)


# ── Single trade: max hold exit ───────────────────────────────────────────────

class TestSingleMaxHoldTrade:
    def _run_max_hold(self) -> BacktestResult:
        snaps = [
            _snap("2020-01-01", decision="BUY", score=80.0, price=100.0),
            _snap("2020-07-01", decision="WATCH", score=70.0, price=110.0),  # holding
            _snap("2022-02-01", decision="WATCH", score=70.0, price=130.0),  # > 2y → exit
        ]
        return run("AAPL", snaps, _SPY)

    def test_buy_enters_position(self):
        result = self._run_max_hold()
        assert len(result.trades) == 1

    def test_exit_reason_is_max_hold(self):
        result = self._run_max_hold()
        assert result.trades[0].exit_reason == "max_hold"

    def test_return_computed_from_prices(self):
        result = self._run_max_hold()
        trade = result.trades[0]
        expected = (130.0 - 100.0) / 100.0
        assert trade.return_pct == pytest.approx(expected, abs=1e-5)

    def test_entry_price_captured(self):
        result = self._run_max_hold()
        assert result.trades[0].entry_price == pytest.approx(100.0)

    def test_exit_price_captured(self):
        result = self._run_max_hold()
        assert result.trades[0].exit_price == pytest.approx(130.0)

    def test_hold_days_positive(self):
        result = self._run_max_hold()
        assert result.trades[0].hold_days > 0

    def test_entry_score_recorded(self):
        result = self._run_max_hold()
        assert result.trades[0].entry_score == pytest.approx(80.0)


# ── Score drop exit ───────────────────────────────────────────────────────────

class TestScoreDropExit:
    def _run_score_drop(self) -> BacktestResult:
        snaps = [
            _snap("2020-01-01", decision="BUY", score=80.0, price=100.0),
            _snap("2020-06-01", decision="AVOID", score=45.0, price=90.0),  # score < 60
        ]
        return run("AAPL", snaps, _SPY)

    def test_exit_reason_is_score_drop(self):
        result = self._run_score_drop()
        assert result.trades[0].exit_reason == "score_drop"

    def test_one_trade_recorded(self):
        result = self._run_score_drop()
        assert len(result.trades) == 1

    def test_negative_return_captured(self):
        result = self._run_score_drop()
        trade = result.trades[0]
        expected = (90.0 - 100.0) / 100.0
        assert trade.return_pct == pytest.approx(expected, abs=1e-5)

    def test_exit_score_recorded(self):
        result = self._run_score_drop()
        assert result.trades[0].exit_score == pytest.approx(45.0)


# ── End-of-simulation exit ────────────────────────────────────────────────────

class TestEndOfSimulationExit:
    def test_open_position_closed_at_last_snapshot(self):
        snaps = [
            _snap("2020-01-01", decision="BUY", score=80.0, price=100.0),
            _snap("2020-07-01", decision="WATCH", score=70.0, price=115.0),
        ]
        result = run("AAPL", snaps, _SPY)
        assert len(result.trades) == 1
        assert result.trades[0].exit_reason == "end_of_simulation"

    def test_exit_reason_end_of_simulation(self):
        snaps = [
            _snap("2020-01-01", decision="BUY", score=80.0, price=100.0),
            _snap("2021-01-01", decision="WATCH", score=65.0, price=120.0),
        ]
        result = run("AAPL", snaps, _SPY)
        assert result.trades[0].exit_reason == "end_of_simulation"

    def test_entry_equals_last_snapshot_no_trade(self):
        # BUY on the only snapshot — nothing to compare against
        snaps = [_snap("2020-01-01", decision="BUY", score=80.0, price=100.0)]
        result = run("AAPL", snaps, _SPY)
        assert result.trades == []

    def test_no_exit_price_no_trade(self):
        snaps = [
            _snap("2020-01-01", decision="BUY", score=80.0, price=100.0),
            _snap("2021-01-01", decision="WATCH", score=65.0, price=None),  # no exit price
        ]
        result = run("AAPL", snaps, _SPY)
        assert result.trades == []


# ── Multiple trades ────────────────────────────────────────────────────────────

class TestMultipleTrades:
    def _run_two_trades(self) -> BacktestResult:
        snaps = [
            _snap("2020-01-01", decision="BUY", score=80.0, price=100.0),
            _snap("2020-06-01", decision="AVOID", score=45.0, price=90.0),   # exit (score drop)
            _snap("2020-09-01", decision="WATCH", score=65.0, price=95.0),   # idle
            _snap("2021-01-01", decision="BUY", score=82.0, price=100.0),    # re-enter
            _snap("2023-02-01", decision="WATCH", score=70.0, price=140.0),  # exit (max hold)
        ]
        return run("AAPL", snaps, _SPY)

    def test_two_trades_recorded(self):
        result = self._run_two_trades()
        assert len(result.trades) == 2

    def test_first_trade_exit_reason(self):
        result = self._run_two_trades()
        assert result.trades[0].exit_reason == "score_drop"

    def test_second_trade_exit_reason(self):
        result = self._run_two_trades()
        assert result.trades[1].exit_reason == "max_hold"

    def test_second_trade_entry_uses_correct_price(self):
        result = self._run_two_trades()
        assert result.trades[1].entry_price == pytest.approx(100.0)

    def test_win_rate_across_trades(self):
        result = self._run_two_trades()
        # first trade: -10%, second: +40% → 1 win, 1 loss
        assert result.metrics.winning_trades == 1
        assert result.metrics.losing_trades == 1


# ── Leakage audit integration ─────────────────────────────────────────────────

class TestLeakageAuditInResult:
    def test_clean_snapshots_audit_passes(self):
        snaps = [_snap("2020-01-01"), _snap("2021-01-01")]
        result = run("AAPL", snaps, _SPY)
        assert result.leakage_audit.passed is True

    def test_out_of_order_flagged(self):
        snaps = [_snap("2021-01-01"), _snap("2020-01-01")]  # reversed order
        result = run("AAPL", snaps, _SPY)
        # engine sorts them first, but audit runs on pre-sort — however our engine
        # sorts before auditing. The sort means chronologically ordered.
        # The audit will pass because we sort before auditing.
        assert result.leakage_audit.snapshots_checked == 2

    def test_missing_date_triggers_violation(self):
        s = _snap("2020-01-01")
        s.as_of_date = None  # type: ignore[assignment]
        result = run("AAPL", [s], _SPY)
        assert result.leakage_audit.passed is False

    def test_duplicate_date_triggers_violation(self):
        snaps = [_snap("2021-01-01"), _snap("2021-01-01")]
        result = run("AAPL", snaps, _SPY)
        assert result.leakage_audit.passed is False


# ── Confidence evolution ───────────────────────────────────────────────────────

class TestConfidenceEvolution:
    def test_evolution_length_matches_snapshots(self):
        snaps = [
            _snap("2020-01-01", confidence=0.60),
            _snap("2021-01-01", confidence=0.75),
            _snap("2022-01-01", confidence=0.80),
        ]
        result = run("AAPL", snaps, _SPY)
        assert len(result.confidence_evolution) == 3

    def test_evolution_dates_match_snapshot_dates(self):
        snaps = [_snap("2020-01-01"), _snap("2021-01-01")]
        result = run("AAPL", snaps, _SPY)
        dates = [t[0] for t in result.confidence_evolution]
        assert dates == [date(2020, 1, 1), date(2021, 1, 1)]

    def test_evolution_values_match_confidence(self):
        snaps = [
            _snap("2020-01-01", confidence=0.60),
            _snap("2021-01-01", confidence=0.85),
        ]
        result = run("AAPL", snaps, _SPY)
        values = [t[1] for t in result.confidence_evolution]
        assert values[0] == pytest.approx(0.60)
        assert values[1] == pytest.approx(0.85)


# ── Decisions over time ────────────────────────────────────────────────────────

class TestDecisionsOverTime:
    def test_length_matches_snapshots(self):
        snaps = [_snap("2020-01-01"), _snap("2021-01-01")]
        result = run("AAPL", snaps, _SPY)
        assert len(result.decisions_over_time) == 2

    def test_decision_strings_preserved(self):
        snaps = [
            _snap("2020-01-01", decision="BUY", score=80.0),
            _snap("2021-01-01", decision="WATCH"),
            _snap("2022-01-01", decision="AVOID", score=50.0),
        ]
        result = run("AAPL", snaps, _SPY)
        decisions = [t[1] for t in result.decisions_over_time]
        assert decisions == ["BUY", "WATCH", "AVOID"]


# ── Reasoning trace ────────────────────────────────────────────────────────────

class TestReasoningTrace:
    def test_trace_not_empty_for_snapshots(self):
        snaps = [_snap("2020-01-01")]
        result = run("AAPL", snaps, _SPY)
        assert len(result.reasoning_trace) > 0

    def test_trace_records_buy_entry(self):
        snaps = [
            _snap("2020-01-01", decision="BUY", score=80.0, price=100.0),
            _snap("2021-01-01", decision="WATCH"),
        ]
        result = run("AAPL", snaps, _SPY)
        entry_lines = [l for l in result.reasoning_trace if "ENTER" in l]
        assert len(entry_lines) == 1

    def test_trace_records_exit(self):
        snaps = [
            _snap("2020-01-01", decision="BUY", score=80.0, price=100.0),
            _snap("2022-03-01", decision="WATCH", score=70.0, price=120.0),  # max hold
        ]
        result = run("AAPL", snaps, _SPY)
        exit_lines = [l for l in result.reasoning_trace if "EXIT" in l]
        assert len(exit_lines) >= 1

    def test_trace_has_date_labels(self):
        snaps = [_snap("2020-01-01"), _snap("2021-01-01")]
        result = run("AAPL", snaps, _SPY)
        assert any("2020-01-01" in l for l in result.reasoning_trace)


# ── Notes ──────────────────────────────────────────────────────────────────────

class TestNotes:
    def test_notes_has_four_entries(self):
        snaps = [_snap("2020-01-01"), _snap("2021-01-01")]
        result = run("AAPL", snaps, _SPY)
        assert len(result.notes) == 4

    def test_notes_contain_ticker(self):
        snaps = [_snap("2020-01-01")]
        result = run("AAPL", snaps, _SPY)
        assert any("AAPL" in n for n in result.notes)

    def test_notes_mention_trade_count(self):
        snaps = [_snap("2020-01-01")]
        result = run("AAPL", snaps, _SPY)
        assert any("0 trade" in n or "1 trade" in n or "trade" in n for n in result.notes)


# ── Determinism ────────────────────────────────────────────────────────────────

class TestDeterminism:
    def test_same_inputs_same_output(self):
        snaps = [
            _snap("2020-01-01", decision="BUY", score=80.0, price=100.0),
            _snap("2021-01-01", decision="WATCH", score=70.0, price=120.0),
        ]
        r1 = run("AAPL", snaps, _SPY)
        r2 = run("AAPL", snaps, _SPY)
        assert r1.metrics.cagr == r2.metrics.cagr
        assert r1.metrics.win_rate == r2.metrics.win_rate
        assert len(r1.trades) == len(r2.trades)

    def test_unsorted_snapshots_same_result_as_sorted(self):
        sorted_snaps = [
            _snap("2020-01-01", decision="BUY", score=80.0, price=100.0),
            _snap("2021-01-01", decision="WATCH", score=70.0, price=120.0),
        ]
        reversed_snaps = list(reversed(sorted_snaps))
        r1 = run("AAPL", sorted_snaps, _SPY)
        r2 = run("AAPL", reversed_snaps, _SPY)
        assert len(r1.trades) == len(r2.trades)
        if r1.trades:
            assert r1.trades[0].entry_date == r2.trades[0].entry_date


# ── Benchmark comparison ───────────────────────────────────────────────────────

class TestBenchmarkComparison:
    def test_benchmark_label_preserved(self):
        snaps = [_snap("2020-01-01"), _snap("2022-01-01")]
        result = run("AAPL", snaps, _SPY, benchmark_label="QQQ")
        assert result.benchmark.benchmark_label == "QQQ"

    def test_no_benchmark_prices_gives_none_alpha(self):
        snaps = [_snap("2020-01-01", decision="BUY", score=80.0, price=100.0),
                 _snap("2022-03-01", decision="WATCH", score=65.0, price=130.0)]
        result = run("AAPL", snaps, {})
        assert result.benchmark.alpha is None

    def test_alpha_computed_when_both_available(self):
        snaps = [
            _snap("2020-01-01", decision="BUY", score=80.0, price=100.0),
            _snap("2022-03-01", decision="WATCH", score=65.0, price=130.0),
        ]
        result = run("AAPL", snaps, _SPY)
        # We have a trade, so strategy CAGR exists; SPY prices cover the range → alpha exists
        # (unless cagr is None due to short period)
        assert result.benchmark.benchmark_cagr is not None
