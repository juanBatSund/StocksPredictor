"""
Full replay test suite.

Covers every gap not addressed by test_engine.py:

  1.  Decision state-machine transitions (WATCH→BUY, double-BUY, AVOID→BUY …)
  2.  Hold-period exact boundary (2-year max)
  3.  Score-at-threshold boundary (exit requires score STRICTLY < 60)
  4.  Exit-condition priority (score_drop beats max_hold at the same snapshot)
  5.  No-position-overlap (second BUY while invested is ignored)
  6.  Re-entry after exit
  7.  Missing price at exit trigger (position held until next price)
  8.  Trace integrity (date labels, ENTER/EXIT content, skipped-snapshot note)
  9.  Determinism at trace level (identical strings on repeated runs)
  10. Non-monotonic confidence evolution
  11. Multi-ticker independence
  12. Decisions-over-time ordering
  13. Full MSFT scenario (6 snapshots, BUY→hold through WATCH, max_hold exit)
  14. Full NVDA scenario (WATCH throughout — macro downgrade stored in decision)
  15. Full XOM scenario (AVOID throughout — no trades)
  16. Leakage audit end-to-end (duplicates, None dates, sort order)
"""

import pytest
from datetime import date
from typing import Optional

from config.settings import BACKTEST_EXIT_SCORE, BACKTEST_MAX_HOLD_YEARS
from src.backtest.engine import BacktestResult, run
from src.backtest.types import HistoricalSnapshot, TradeRecord
from src.decision.engine import ConfidenceBreakdown, DecisionResult


# ── Shared factory helpers ─────────────────────────────────────────────────────

def _dr(
    ticker: str = "TEST",
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
    ticker: str = "TEST",
    decision: str = "WATCH",
    score: float = 70.0,
    confidence: float = 0.70,
    price: Optional[float] = 100.0,
    val_status: str = "fair",
) -> HistoricalSnapshot:
    return HistoricalSnapshot(
        as_of_date=date.fromisoformat(date_str),
        ticker=ticker,
        price=price,
        decision=_dr(
            ticker=ticker,
            decision=decision,
            score=score,
            confidence=confidence,
            val_status=val_status,
        ),
    )


_SPY = {
    date(2020, 1, 1):  324.0,
    date(2021, 1, 4):  368.0,
    date(2022, 1, 3):  476.0,
    date(2022, 12, 1): 394.0,
    date(2023, 6, 15): 445.0,
    date(2024, 1, 10): 469.0,
    date(2024, 12, 1): 598.0,
}


# ── 1. Decision state-machine transitions ──────────────────────────────────────

class TestStateTransitions:
    def test_watch_then_buy_enters_at_buy_date(self):
        snaps = [
            _snap("2020-01-01", decision="WATCH"),
            _snap("2021-01-01", decision="BUY", score=82.0, price=100.0),
            _snap("2023-02-01", decision="WATCH", score=72.0, price=135.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert len(result.trades) == 1
        assert result.trades[0].entry_date == date(2021, 1, 1)

    def test_avoid_then_buy_enters_at_buy_date(self):
        snaps = [
            _snap("2020-01-01", decision="AVOID", score=50.0),
            _snap("2020-07-01", decision="BUY",   score=80.0, price=100.0),
            _snap("2022-09-01", decision="WATCH",  score=68.0, price=130.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert len(result.trades) == 1
        assert result.trades[0].entry_date == date(2020, 7, 1)

    def test_watch_after_buy_does_not_exit_above_score_floor(self):
        # Decision changes to WATCH but score stays ≥ 60 → position must stay open
        snaps = [
            _snap("2020-01-01", decision="BUY",   score=80.0, price=100.0),
            _snap("2020-07-01", decision="WATCH",  score=72.0, price=108.0),
            _snap("2021-01-01", decision="WATCH",  score=68.0, price=112.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert len(result.trades) == 1
        assert result.trades[0].exit_reason == "end_of_simulation"
        assert result.trades[0].exit_price == pytest.approx(112.0)

    def test_avoid_after_buy_exits_on_score_drop(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",   score=80.0, price=100.0),
            _snap("2020-06-01", decision="WATCH",  score=65.0, price=110.0),
            _snap("2020-12-01", decision="AVOID",  score=55.0, price=90.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].exit_reason == "score_drop"
        assert result.trades[0].exit_date == date(2020, 12, 1)

    def test_consecutive_buy_signals_single_entry_only(self):
        snaps = [
            _snap("2020-01-01", decision="BUY", score=82.0, price=100.0),
            _snap("2020-06-01", decision="BUY", score=85.0, price=110.0),
            _snap("2022-02-01", decision="WATCH", score=70.0, price=130.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert len(result.trades) == 1

    def test_second_buy_does_not_replace_entry_price(self):
        snaps = [
            _snap("2020-01-01", decision="BUY", score=82.0, price=100.0),
            _snap("2020-06-01", decision="BUY", score=85.0, price=110.0),
            _snap("2022-02-01", decision="WATCH", score=70.0, price=135.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].entry_price == pytest.approx(100.0)
        assert result.trades[0].entry_score == pytest.approx(82.0)

    def test_watch_only_no_trades(self):
        snaps = [_snap(d) for d in ["2020-01-01", "2021-01-01", "2022-01-01"]]
        result = run("TEST", snaps, _SPY)
        assert result.trades == []
        assert result.metrics.total_trades == 0

    def test_avoid_only_no_trades(self):
        snaps = [_snap(d, decision="AVOID", score=50.0) for d in ["2020-01-01", "2021-01-01"]]
        result = run("TEST", snaps, _SPY)
        assert result.trades == []


# ── 2. Hold-period exact boundary ─────────────────────────────────────────────
#
# Entry 2020-01-01.
# 2021-12-31 = 730 days (2020 is leap: 366 + 364 = 730) → 730/365.25 ≈ 1.9986 < 2 → hold
# 2022-01-01 = 731 days → 731/365.25 ≈ 2.0014 ≥ 2 → max_hold

class TestHoldBoundary:
    def test_just_under_two_years_is_end_of_simulation(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2021-12-31", decision="WATCH", score=72.0, price=120.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].exit_reason == "end_of_simulation"

    def test_exactly_at_two_years_triggers_max_hold(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2021-12-31", decision="WATCH", score=72.0, price=115.0),
            _snap("2022-01-01", decision="WATCH", score=70.0, price=118.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].exit_reason == "max_hold"
        assert result.trades[0].exit_date == date(2022, 1, 1)

    def test_max_hold_captures_correct_exit_price(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2022-01-01", decision="WATCH", score=70.0, price=145.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].exit_price == pytest.approx(145.0)
        assert result.trades[0].return_pct == pytest.approx(0.45, abs=1e-4)

    def test_hold_days_computed_correctly(self):
        # 2020-01-01 to 2022-01-01 = 731 days (2020 is leap)
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2022-01-01", decision="WATCH", score=70.0, price=120.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].hold_days == 731

    def test_hold_years_derived_from_hold_days(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2022-01-01", decision="WATCH", score=70.0, price=120.0),
        ]
        result = run("TEST", snaps, _SPY)
        trade = result.trades[0]
        assert trade.hold_years == pytest.approx(trade.hold_days / 365.25, abs=1e-4)

    def test_annualized_return_none_for_sub_month_hold(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2020-01-15", decision="AVOID", score=55.0, price=90.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].annualized_return is None

    def test_max_hold_years_matches_config(self):
        assert BACKTEST_MAX_HOLD_YEARS == 2


# ── 3. Score-at-threshold boundary ────────────────────────────────────────────

class TestScoreBoundary:
    def test_score_exactly_60_does_not_trigger_exit(self):
        # exit requires score STRICTLY < BACKTEST_EXIT_SCORE
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2021-01-01", decision="WATCH", score=60.0, price=110.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].exit_reason == "end_of_simulation"

    def test_score_59_point_9_triggers_exit(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2021-01-01", decision="AVOID", score=59.9, price=95.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].exit_reason == "score_drop"

    def test_score_drops_to_61_stays_open(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2020-07-01", decision="WATCH", score=61.0, price=105.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].exit_reason == "end_of_simulation"

    def test_score_zero_exits_immediately(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2020-06-01", decision="AVOID", score=0.0,  price=60.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].exit_reason == "score_drop"

    def test_exit_score_threshold_is_60(self):
        assert BACKTEST_EXIT_SCORE == 60


# ── 4. Exit-condition priority ─────────────────────────────────────────────────

class TestExitPriority:
    def test_score_drop_beats_max_hold_at_same_snapshot(self):
        # Entry 2020-01-01; at 2022-01-01: BOTH score<60 AND hold≥2y triggered
        # Per engine: reason = "score_drop" if score_drop else "max_hold"
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2022-01-01", decision="AVOID", score=45.0, price=90.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].exit_reason == "score_drop"

    def test_max_hold_when_score_above_floor(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2022-01-01", decision="WATCH", score=65.0, price=120.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].exit_reason == "max_hold"

    def test_score_drop_exit_does_not_require_max_hold(self):
        # Six-month hold — not near max_hold at all
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2020-07-01", decision="AVOID", score=50.0, price=90.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].exit_reason == "score_drop"
        assert result.trades[0].hold_days < 365


# ── 5. Re-entry after exit ─────────────────────────────────────────────────────

class TestReEntry:
    def test_re_enters_after_score_drop_exit(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2020-06-01", decision="AVOID", score=45.0, price=85.0),   # exit
            _snap("2020-09-01", decision="WATCH", score=63.0, price=90.0),   # idle
            _snap("2021-03-01", decision="BUY",  score=82.0, price=95.0),    # re-enter
            _snap("2023-04-01", decision="WATCH", score=70.0, price=130.0),  # exit (max_hold)
        ]
        result = run("TEST", snaps, _SPY)
        assert len(result.trades) == 2

    def test_re_entry_uses_new_entry_price(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2020-06-01", decision="AVOID", score=45.0, price=85.0),
            _snap("2021-01-01", decision="BUY",  score=82.0, price=110.0),
            _snap("2023-02-01", decision="WATCH", score=68.0, price=150.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[1].entry_price == pytest.approx(110.0)

    def test_re_entry_exit_reasons_independent(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2020-06-01", decision="AVOID", score=45.0, price=88.0),  # score_drop
            _snap("2021-01-01", decision="BUY",  score=82.0, price=95.0),
            _snap("2023-02-01", decision="WATCH", score=70.0, price=130.0), # max_hold
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].exit_reason == "score_drop"
        assert result.trades[1].exit_reason == "max_hold"

    def test_re_entry_returns_computed_from_own_prices(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=200.0),
            _snap("2020-06-01", decision="AVOID", score=45.0, price=160.0),  # -20%
            _snap("2021-01-01", decision="BUY",  score=82.0, price=100.0),
            _snap("2023-02-01", decision="WATCH", score=70.0, price=150.0),  # +50%
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].return_pct == pytest.approx(-0.20, abs=1e-5)
        assert result.trades[1].return_pct == pytest.approx(0.50, abs=1e-5)

    def test_win_loss_metrics_span_both_trades(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=200.0),
            _snap("2020-06-01", decision="AVOID", score=45.0, price=160.0),  # loss
            _snap("2021-01-01", decision="BUY",  score=82.0, price=100.0),
            _snap("2023-02-01", decision="WATCH", score=70.0, price=150.0),  # win
        ]
        result = run("TEST", snaps, _SPY)
        assert result.metrics.winning_trades == 1
        assert result.metrics.losing_trades == 1
        assert result.metrics.win_rate == pytest.approx(0.50)


# ── 6. Missing price at exit trigger ──────────────────────────────────────────

class TestMissingPriceAtExit:
    def test_exit_triggered_no_price_held_until_next(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2020-06-01", decision="AVOID", score=45.0, price=None),   # trigger, no price
            _snap("2020-09-01", decision="AVOID", score=45.0, price=88.0),   # has price
        ]
        result = run("TEST", snaps, _SPY)
        assert len(result.trades) == 1
        assert result.trades[0].exit_price == pytest.approx(88.0)

    def test_missing_price_at_exit_noted_in_trace(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2020-06-01", decision="AVOID", score=45.0, price=None),
            _snap("2020-09-01", decision="AVOID", score=45.0, price=85.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert any(
            "holding until next available price" in line
            for line in result.reasoning_trace
        )

    def test_no_trade_when_exit_price_never_available(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2020-06-01", decision="AVOID", score=45.0, price=None),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades == []

    def test_return_uses_eventual_exit_price(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2020-06-01", decision="AVOID", score=45.0, price=None),   # skipped
            _snap("2020-09-01", decision="AVOID", score=45.0, price=120.0),  # 20% gain
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].return_pct == pytest.approx(0.20, abs=1e-5)

    def test_score_recovers_after_no_price_closes_end_of_sim(self):
        # Score triggered exit but no price; next snapshot score recovers ≥ 60
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2020-06-01", decision="AVOID", score=45.0, price=None),   # trigger, no price
            _snap("2020-09-01", decision="WATCH", score=62.0, price=95.0),   # score ok again
        ]
        result = run("TEST", snaps, _SPY)
        # Exit triggered at June but no price; September score is 62 ≥ 60, no new exit;
        # simulation ends → end_of_simulation
        assert result.trades[0].exit_reason == "end_of_simulation"


# ── 7. Reasoning trace integrity ──────────────────────────────────────────────

class TestTraceIntegrity:
    def test_every_snapshot_produces_at_least_one_trace_line(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2021-01-01", decision="WATCH", score=72.0, price=115.0),
            _snap("2022-02-01", decision="WATCH", score=68.0, price=120.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert len(result.reasoning_trace) >= 3

    def test_trace_contains_snapshot_date(self):
        snaps = [_snap("2020-07-04", decision="BUY", score=80.0, price=100.0)]
        result = run("TEST", snaps, _SPY)
        assert any("2020-07-04" in line for line in result.reasoning_trace)

    def test_enter_line_contains_price(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=123.45),
            _snap("2022-02-01", decision="WATCH", score=70.0, price=150.0),
        ]
        result = run("TEST", snaps, _SPY)
        enter_line = next(l for l in result.reasoning_trace if "ENTER" in l)
        assert "123.45" in enter_line

    def test_exit_line_contains_return(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2022-02-01", decision="WATCH", score=70.0, price=150.0),
        ]
        result = run("TEST", snaps, _SPY)
        exit_line = next(l for l in result.reasoning_trace if "EXIT" in l)
        assert "return" in exit_line.lower() or "%" in exit_line

    def test_no_enter_line_for_watch_only(self):
        snaps = [_snap("2020-01-01", decision="WATCH")]
        result = run("TEST", snaps, _SPY)
        assert not any("ENTER" in l for l in result.reasoning_trace)

    def test_skipped_note_for_none_date_snapshot(self):
        snaps = [_snap("2020-01-01"), _snap("2021-01-01")]
        snaps[1].as_of_date = None  # type: ignore[assignment]
        result = run("TEST", snaps, _SPY)
        assert any(
            "skipped" in l or "no as_of_date" in l
            for l in result.reasoning_trace
        )

    def test_hold_lines_emitted_while_position_open(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2020-07-01", decision="WATCH", score=72.0, price=108.0),
            _snap("2021-01-01", decision="WATCH", score=70.0, price=112.0),
        ]
        result = run("TEST", snaps, _SPY)
        hold_lines = [l for l in result.reasoning_trace if "hold" in l.lower()]
        assert len(hold_lines) >= 2

    def test_exit_reason_in_exit_trace_line(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
            _snap("2020-06-01", decision="AVOID", score=50.0, price=90.0),
        ]
        result = run("TEST", snaps, _SPY)
        exit_line = next(l for l in result.reasoning_trace if "EXIT" in l)
        assert "score_drop" in exit_line


# ── 8. Determinism at trace level ─────────────────────────────────────────────

class TestReplayDeterminism:
    def _snaps(self):
        return [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0, confidence=0.78),
            _snap("2020-07-01", decision="WATCH", score=72.0, price=110.0, confidence=0.65),
            _snap("2021-03-01", decision="WATCH", score=68.0, price=118.0, confidence=0.60),
            _snap("2022-02-01", decision="WATCH", score=70.0, price=130.0, confidence=0.63),
        ]

    def test_metrics_identical_on_repeat(self):
        r1 = run("TEST", self._snaps(), _SPY)
        r2 = run("TEST", self._snaps(), _SPY)
        assert r1.metrics.cagr == r2.metrics.cagr
        assert r1.metrics.win_rate == r2.metrics.win_rate
        assert r1.metrics.max_drawdown == r2.metrics.max_drawdown

    def test_trace_strings_identical_on_repeat(self):
        r1 = run("TEST", self._snaps(), _SPY)
        r2 = run("TEST", self._snaps(), _SPY)
        assert r1.reasoning_trace == r2.reasoning_trace

    def test_confidence_evolution_identical_on_repeat(self):
        r1 = run("TEST", self._snaps(), _SPY)
        r2 = run("TEST", self._snaps(), _SPY)
        assert r1.confidence_evolution == r2.confidence_evolution

    def test_decisions_over_time_identical_on_repeat(self):
        r1 = run("TEST", self._snaps(), _SPY)
        r2 = run("TEST", self._snaps(), _SPY)
        assert r1.decisions_over_time == r2.decisions_over_time

    def test_reversed_input_order_same_trade_outcome(self):
        forward = self._snaps()
        backward = list(reversed(forward))
        r1 = run("TEST", forward,  _SPY)
        r2 = run("TEST", backward, _SPY)
        assert len(r1.trades) == len(r2.trades)
        if r1.trades:
            assert r1.trades[0].entry_date  == r2.trades[0].entry_date
            assert r1.trades[0].return_pct  == r2.trades[0].return_pct
            assert r1.trades[0].exit_reason == r2.trades[0].exit_reason


# ── 9. Non-monotonic confidence evolution ─────────────────────────────────────

class TestConfidenceEvolution:
    def test_rising_then_falling_confidence_preserved(self):
        confs = [0.51, 0.59, 0.78, 0.81, 0.62, 0.58]
        snaps = [
            _snap(f"202{i}-0{i+1}-01", confidence=c)
            for i, c in enumerate(confs)
        ]
        result = run("TEST", snaps, _SPY)
        values = [t[1] for t in result.confidence_evolution]
        assert values == pytest.approx(confs)

    def test_evolution_length_matches_snapshot_count(self):
        snaps = [_snap(f"202{i}-01-01") for i in range(5)]
        result = run("TEST", snaps, _SPY)
        assert len(result.confidence_evolution) == 5

    def test_evolution_dates_are_chronological(self):
        snaps = [_snap("2020-01-01"), _snap("2021-01-01"), _snap("2022-01-01")]
        result = run("TEST", snaps, _SPY)
        dates = [t[0] for t in result.confidence_evolution]
        assert dates == sorted(dates)

    def test_entry_confidence_recorded_in_trade(self):
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0, confidence=0.83),
            _snap("2022-02-01", decision="WATCH", score=70.0, price=130.0),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.trades[0].entry_confidence == pytest.approx(0.83)

    def test_confidence_does_not_affect_entry_or_exit(self):
        # Very low confidence — decision engine already resolved this; replay ignores conf
        snaps = [
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0, confidence=0.10),
            _snap("2022-02-01", decision="WATCH", score=70.0, price=130.0, confidence=0.10),
        ]
        result = run("TEST", snaps, _SPY)
        assert len(result.trades) == 1
        assert result.trades[0].exit_reason == "max_hold"


# ── 10. Multi-ticker independence ─────────────────────────────────────────────

class TestMultiTickerIndependence:
    def test_msft_buy_aapl_watch_independent(self):
        msft = [
            _snap("2020-01-01", ticker="MSFT", decision="BUY",  score=82.0, price=150.0),
            _snap("2022-02-01", ticker="MSFT", decision="WATCH", score=70.0, price=200.0),
        ]
        aapl = [
            _snap("2020-01-01", ticker="AAPL", decision="WATCH", score=70.0, price=75.0),
            _snap("2022-02-01", ticker="AAPL", decision="WATCH", score=68.0, price=85.0),
        ]
        mr = run("MSFT", msft, _SPY)
        ar = run("AAPL", aapl, _SPY)
        assert len(mr.trades) == 1
        assert len(ar.trades) == 0

    def test_ticker_labels_correct_in_results(self):
        msft = [_snap("2020-01-01", ticker="MSFT", decision="BUY", score=82.0, price=100.0),
                _snap("2022-02-01", ticker="MSFT", decision="WATCH", score=70.0, price=130.0)]
        nvda = [_snap("2020-01-01", ticker="NVDA", decision="BUY", score=85.0, price=200.0),
                _snap("2020-06-01", ticker="NVDA", decision="AVOID", score=50.0, price=160.0)]
        mr = run("MSFT", msft, _SPY)
        nr = run("NVDA", nvda, _SPY)
        assert mr.ticker == "MSFT"
        assert nr.ticker == "NVDA"

    def test_returns_independent_per_ticker(self):
        msft = [_snap("2020-01-01", ticker="MSFT", decision="BUY",  score=82.0, price=100.0),
                _snap("2022-02-01", ticker="MSFT", decision="WATCH", score=70.0, price=140.0)]
        xom  = [_snap("2020-01-01", ticker="XOM",  decision="BUY",  score=80.0, price=50.0),
                _snap("2020-06-01", ticker="XOM",  decision="AVOID", score=45.0, price=40.0)]
        mr = run("MSFT", msft, _SPY)
        xr = run("XOM",  xom,  _SPY)
        assert mr.trades[0].return_pct == pytest.approx(0.40, abs=1e-4)
        assert xr.trades[0].return_pct == pytest.approx(-0.20, abs=1e-4)

    def test_trade_ticker_label_matches_snapshot_ticker(self):
        snaps = [
            _snap("2020-01-01", ticker="NVDA", decision="BUY",  score=85.0, price=100.0),
            _snap("2022-02-01", ticker="NVDA", decision="WATCH", score=72.0, price=130.0),
        ]
        result = run("NVDA", snaps, _SPY)
        assert result.trades[0].ticker == "NVDA"


# ── 11. Decisions-over-time ordering ──────────────────────────────────────────

class TestDecisionsOverTime:
    def test_full_decision_sequence_preserved(self):
        seq = [
            ("2020-01-01", "WATCH", 70.0),
            ("2021-01-01", "BUY",   80.0),
            ("2022-01-01", "AVOID", 55.0),
        ]
        snaps = [_snap(d, decision=dec, score=sc) for d, dec, sc in seq]
        result = run("TEST", snaps, _SPY)
        assert [t[1] for t in result.decisions_over_time] == ["WATCH", "BUY", "AVOID"]

    def test_dates_in_decisions_over_time_are_chronological(self):
        snaps = [
            _snap("2022-01-01", decision="WATCH"),
            _snap("2020-01-01", decision="BUY",  score=80.0, price=100.0),
        ]
        result = run("TEST", snaps, _SPY)
        dates = [t[0] for t in result.decisions_over_time]
        assert dates == sorted(dates)

    def test_decisions_dates_match_snapshot_dates_after_sort(self):
        snaps = [
            _snap("2021-03-15", decision="BUY",  score=80.0, price=100.0),
            _snap("2022-09-20", decision="WATCH"),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.decisions_over_time[0][0] == date(2021, 3, 15)
        assert result.decisions_over_time[1][0] == date(2022, 9, 20)

    def test_length_matches_valid_snapshot_count(self):
        snaps = [_snap(f"202{i}-01-01") for i in range(4)]
        result = run("TEST", snaps, _SPY)
        assert len(result.decisions_over_time) == 4


# ── 12. Full MSFT scenario ─────────────────────────────────────────────────────
#
# Mirrors the MSFT replay sequence in ui/mock_data.py:
#   2022-01-03  WATCH 71.2  conf=0.51  — no entry (score 71.2 < 75)
#   2022-06-15  WATCH 76.8  conf=0.59  — no entry (valuation fair)
#   2022-12-01  BUY   81.1  conf=0.78  — ENTER at $255
#   2023-06-15  BUY   82.3  conf=0.81  — hold (196 days, 0.54y)
#   2024-01-10  WATCH 77.4  conf=0.62  — hold (405 days, 1.11y, score>60)
#   2024-12-01  WATCH 75.9  conf=0.58  — EXIT max_hold (731 days, 2.0014y ≥ 2)

class TestMSFTScenario:
    _ROWS = [
        ("2022-01-03", "WATCH", 71.2, 0.51, 295.0),
        ("2022-06-15", "WATCH", 76.8, 0.59, 270.0),
        ("2022-12-01", "BUY",   81.1, 0.78, 255.0),
        ("2023-06-15", "BUY",   82.3, 0.81, 315.0),
        ("2024-01-10", "WATCH", 77.4, 0.62, 385.0),
        ("2024-12-01", "WATCH", 75.9, 0.58, 425.0),
    ]

    def _snaps(self):
        return [
            _snap(d, ticker="MSFT", decision=dec, score=sc, confidence=cf, price=px)
            for d, dec, sc, cf, px in self._ROWS
        ]

    def test_exactly_one_trade(self):
        result = run("MSFT", self._snaps(), _SPY)
        assert len(result.trades) == 1

    def test_entry_at_first_buy_snapshot(self):
        result = run("MSFT", self._snaps(), _SPY)
        assert result.trades[0].entry_date == date(2022, 12, 1)

    def test_entry_price(self):
        result = run("MSFT", self._snaps(), _SPY)
        assert result.trades[0].entry_price == pytest.approx(255.0)

    def test_entry_score(self):
        result = run("MSFT", self._snaps(), _SPY)
        assert result.trades[0].entry_score == pytest.approx(81.1)

    def test_entry_confidence(self):
        result = run("MSFT", self._snaps(), _SPY)
        assert result.trades[0].entry_confidence == pytest.approx(0.78)

    def test_exit_reason_max_hold(self):
        result = run("MSFT", self._snaps(), _SPY)
        assert result.trades[0].exit_reason == "max_hold"

    def test_exit_date(self):
        result = run("MSFT", self._snaps(), _SPY)
        assert result.trades[0].exit_date == date(2024, 12, 1)

    def test_exit_price(self):
        result = run("MSFT", self._snaps(), _SPY)
        assert result.trades[0].exit_price == pytest.approx(425.0)

    def test_return_pct(self):
        result = run("MSFT", self._snaps(), _SPY)
        expected = (425.0 - 255.0) / 255.0
        assert result.trades[0].return_pct == pytest.approx(expected, abs=1e-5)

    def test_hold_days_is_731(self):
        # 2022-12-01 to 2024-12-01 (2024 is a leap year) = 365 + 366 = 731 days
        result = run("MSFT", self._snaps(), _SPY)
        assert result.trades[0].hold_days == 731

    def test_hold_years_exceeds_max_hold(self):
        result = run("MSFT", self._snaps(), _SPY)
        assert result.trades[0].hold_years >= BACKTEST_MAX_HOLD_YEARS

    def test_six_snapshots_in_confidence_evolution(self):
        result = run("MSFT", self._snaps(), _SPY)
        assert len(result.confidence_evolution) == 6

    def test_confidence_peaks_at_snapshot_4(self):
        result = run("MSFT", self._snaps(), _SPY)
        values = [t[1] for t in result.confidence_evolution]
        assert values[3] == pytest.approx(0.81)       # peak
        assert values[4] < values[3]                  # drops after

    def test_decisions_over_time_correct(self):
        result = run("MSFT", self._snaps(), _SPY)
        decisions = [t[1] for t in result.decisions_over_time]
        assert decisions == ["WATCH", "WATCH", "BUY", "BUY", "WATCH", "WATCH"]

    def test_win_rate_is_one(self):
        result = run("MSFT", self._snaps(), _SPY)
        assert result.metrics.win_rate == pytest.approx(1.0)

    def test_leakage_audit_passes(self):
        result = run("MSFT", self._snaps(), _SPY)
        assert result.leakage_audit.passed is True
        assert result.leakage_audit.violations == []

    def test_six_snapshots_checked_in_audit(self):
        result = run("MSFT", self._snaps(), _SPY)
        assert result.leakage_audit.snapshots_checked == 6

    def test_start_and_end_dates(self):
        result = run("MSFT", self._snaps(), _SPY)
        assert result.start_date == date(2022, 1, 3)
        assert result.end_date   == date(2024, 12, 1)

    def test_benchmark_alpha_computed(self):
        result = run("MSFT", self._snaps(), _SPY)
        assert result.benchmark.alpha is not None

    def test_trace_has_enter_at_buy_date(self):
        result = run("MSFT", self._snaps(), _SPY)
        assert any("2022-12-01" in l and "ENTER" in l for l in result.reasoning_trace)

    def test_trace_has_max_hold_exit(self):
        result = run("MSFT", self._snaps(), _SPY)
        assert any("max_hold" in l for l in result.reasoning_trace)

    def test_result_is_deterministic(self):
        r1 = run("MSFT", self._snaps(), _SPY)
        r2 = run("MSFT", self._snaps(), _SPY)
        assert r1.trades[0].return_pct  == r2.trades[0].return_pct
        assert r1.reasoning_trace == r2.reasoning_trace


# ── 13. NVDA scenario (WATCH throughout — no entry) ───────────────────────────
#
# In ui/mock_data.py NVDA passes all three decision gates but the macro
# downgrade stores decision = "WATCH".  The backtest engine sees only the
# stored decision, so no BUY entry should ever occur.

class TestNVDAScenario:
    _ROWS = [
        ("2022-01-01", "WATCH", 79.2, 0.54),
        ("2022-07-01", "WATCH", 82.4, 0.60),
        ("2023-01-01", "WATCH", 85.6, 0.58),
        ("2024-01-01", "WATCH", 83.1, 0.55),
    ]

    def _snaps(self):
        return [
            _snap(d, ticker="NVDA", decision=dec, score=sc,
                  confidence=cf, price=300.0 + 50.0 * i)
            for i, (d, dec, sc, cf) in enumerate(self._ROWS)
        ]

    def test_no_trades(self):
        result = run("NVDA", self._snaps(), _SPY)
        assert result.trades == []

    def test_all_decisions_are_watch(self):
        result = run("NVDA", self._snaps(), _SPY)
        assert all(d == "WATCH" for _, d in result.decisions_over_time)

    def test_cagr_is_none(self):
        result = run("NVDA", self._snaps(), _SPY)
        assert result.metrics.cagr is None

    def test_win_rate_is_zero(self):
        result = run("NVDA", self._snaps(), _SPY)
        assert result.metrics.win_rate == pytest.approx(0.0)

    def test_confidence_evolution_has_four_entries(self):
        result = run("NVDA", self._snaps(), _SPY)
        assert len(result.confidence_evolution) == 4

    def test_audit_passes(self):
        result = run("NVDA", self._snaps(), _SPY)
        assert result.leakage_audit.passed is True

    def test_no_enter_in_trace(self):
        result = run("NVDA", self._snaps(), _SPY)
        assert not any("ENTER" in l for l in result.reasoning_trace)


# ── 14. XOM scenario (AVOID throughout) ───────────────────────────────────────

class TestXOMScenario:
    _ROWS = [
        ("2022-01-01", "AVOID", 54.2, 0.39,  95.0),
        ("2022-07-01", "AVOID", 51.8, 0.35, 105.0),
        ("2023-01-01", "AVOID", 53.1, 0.40, 112.0),
        ("2024-01-01", "AVOID", 56.4, 0.44, 118.0),
    ]

    def _snaps(self):
        return [
            _snap(d, ticker="XOM", decision=dec, score=sc, confidence=cf, price=px)
            for d, dec, sc, cf, px in self._ROWS
        ]

    def test_no_trades(self):
        result = run("XOM", self._snaps(), _SPY)
        assert result.trades == []

    def test_all_decisions_are_avoid(self):
        result = run("XOM", self._snaps(), _SPY)
        assert all(d == "AVOID" for _, d in result.decisions_over_time)

    def test_total_trades_zero(self):
        result = run("XOM", self._snaps(), _SPY)
        assert result.metrics.total_trades == 0

    def test_audit_passes(self):
        result = run("XOM", self._snaps(), _SPY)
        assert result.leakage_audit.passed is True

    def test_ticker_preserved(self):
        result = run("XOM", self._snaps(), _SPY)
        assert result.ticker == "XOM"


# ── 15. Leakage audit end-to-end ──────────────────────────────────────────────

class TestLeakageAuditEndToEnd:
    def test_snapshots_in_result_are_sorted(self):
        snaps = [
            _snap("2022-01-01"),
            _snap("2020-01-01"),
            _snap("2021-01-01"),
        ]
        result = run("TEST", snaps, _SPY)
        dates = [s.as_of_date for s in result.snapshots]
        assert dates == sorted(dates)

    def test_snapshot_count_preserved(self):
        snaps = [_snap(f"202{i}-01-01") for i in range(4)]
        result = run("TEST", snaps, _SPY)
        assert len(result.snapshots) == 4

    def test_duplicate_dates_flagged(self):
        snaps = [_snap("2021-01-01"), _snap("2021-01-01")]
        result = run("TEST", snaps, _SPY)
        assert result.leakage_audit.passed is False

    def test_none_date_flagged(self):
        snaps = [_snap("2020-01-01"), _snap("2021-01-01")]
        snaps[0].as_of_date = None  # type: ignore[assignment]
        result = run("TEST", snaps, _SPY)
        assert result.leakage_audit.passed is False

    def test_clean_sequence_passes_audit(self):
        snaps = [
            _snap("2020-01-01"),
            _snap("2021-06-15"),
            _snap("2022-03-01"),
        ]
        result = run("TEST", snaps, _SPY)
        assert result.leakage_audit.passed is True
        assert result.leakage_audit.violations == []

    def test_audit_violation_count_in_notes(self):
        snaps = [_snap("2021-01-01"), _snap("2021-01-01")]
        result = run("TEST", snaps, _SPY)
        note_text = " ".join(result.leakage_audit.notes)
        assert "1" in note_text
