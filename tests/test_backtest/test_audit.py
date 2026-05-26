import pytest
from datetime import date

from src.backtest.audit import LeakageAudit, audit
from src.backtest.types import HistoricalSnapshot
from src.decision.engine import ConfidenceBreakdown, DecisionResult


# ── Factory helpers ────────────────────────────────────────────────────────────

def _dr(decision: str = "WATCH", score: float = 70.0) -> DecisionResult:
    return DecisionResult(
        ticker="TEST",
        decision=decision,
        score=score,
        quality_score=score,
        growth_score=score,
        dividend_score=score,
        valuation_score=score,
        valuation_status="fair",
        confidence=0.70,
        confidence_breakdown=ConfidenceBreakdown(0.8, 0.5, 0.5, 0.5, 0.70),
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


def _snap(date_str: str, ticker: str = "AAPL", price: float = 100.0) -> HistoricalSnapshot:
    return HistoricalSnapshot(
        as_of_date=date.fromisoformat(date_str),
        ticker=ticker,
        price=price,
        decision=_dr(),
    )


def _snap_no_date(ticker: str = "AAPL") -> HistoricalSnapshot:
    s = HistoricalSnapshot(
        as_of_date=date(2021, 1, 1),  # placeholder — overwrite below
        ticker=ticker,
        price=100.0,
        decision=_dr(),
    )
    object.__setattr__(s, "as_of_date", None)  # bypass frozen if needed
    # HistoricalSnapshot is a regular dataclass (not frozen), so direct assignment works
    s.as_of_date = None  # type: ignore[assignment]
    return s


# ── Clean cases ────────────────────────────────────────────────────────────────

class TestCleanAudit:
    def test_empty_snapshots_passes(self):
        result = audit([])
        assert result.passed is True
        assert result.violations == []

    def test_single_snapshot_passes(self):
        result = audit([_snap("2021-01-01")])
        assert result.passed is True

    def test_chronological_order_passes(self):
        snaps = [
            _snap("2021-01-01"),
            _snap("2021-06-01"),
            _snap("2022-01-01"),
        ]
        result = audit(snaps)
        assert result.passed is True
        assert result.violations == []

    def test_notes_always_present(self):
        result = audit([_snap("2021-01-01")])
        assert len(result.notes) == 2

    def test_snapshots_checked_count(self):
        snaps = [_snap("2021-01-01"), _snap("2021-06-01")]
        result = audit(snaps)
        assert result.snapshots_checked == 2


# ── Violations ─────────────────────────────────────────────────────────────────

class TestViolations:
    def test_none_as_of_date_fails(self):
        s = _snap("2021-01-01")
        s.as_of_date = None  # type: ignore[assignment]
        result = audit([s])
        assert result.passed is False
        assert len(result.violations) == 1

    def test_out_of_order_fails(self):
        snaps = [
            _snap("2021-06-01"),
            _snap("2021-01-01"),  # earlier date after a later one
        ]
        result = audit(snaps)
        assert result.passed is False
        assert any("out-of-order" in v for v in result.violations)

    def test_duplicate_date_fails(self):
        snaps = [
            _snap("2021-01-01"),
            _snap("2021-01-01"),  # duplicate
        ]
        result = audit(snaps)
        assert result.passed is False
        assert any("Duplicate" in v for v in result.violations)

    def test_multiple_violations_all_listed(self):
        s1 = _snap("2021-06-01")
        s2 = _snap("2021-01-01")  # out of order
        s3 = _snap("2021-01-01")  # duplicate of s2
        result = audit([s1, s2, s3])
        assert not result.passed
        assert len(result.violations) >= 2


class TestViolationMessages:
    def test_out_of_order_message_contains_dates(self):
        snaps = [_snap("2021-06-01"), _snap("2021-01-01")]
        result = audit(snaps)
        violation_text = " ".join(result.violations)
        assert "2021-01-01" in violation_text or "2021-06-01" in violation_text

    def test_none_date_message_contains_ticker(self):
        s = _snap("2021-01-01", ticker="XYZ")
        s.as_of_date = None  # type: ignore[assignment]
        result = audit([s])
        assert any("XYZ" in v for v in result.violations)

    def test_passed_false_when_violation(self):
        s = _snap("2021-06-01")
        s2 = _snap("2021-01-01")
        result = audit([s, s2])
        assert result.passed is False

    def test_violation_count_in_notes(self):
        snaps = [_snap("2021-06-01"), _snap("2021-01-01")]
        result = audit(snaps)
        note_text = " ".join(result.notes)
        assert "1" in note_text  # at least one violation noted
