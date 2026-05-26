import pytest
from datetime import date, timedelta

from src.validation.splitter import PeriodSplit, split_periods


# ── split_periods() ────────────────────────────────────────────────────────────

class TestSplitPeriods:
    _START = date(2018, 1, 1)
    _END = date(2024, 1, 1)

    def test_returns_period_split(self):
        result = split_periods(self._START, self._END)
        assert isinstance(result, PeriodSplit)

    def test_train_starts_at_start(self):
        r = split_periods(self._START, self._END)
        assert r.train_start == self._START

    def test_test_ends_at_end(self):
        r = split_periods(self._START, self._END)
        assert r.test_end == self._END

    def test_periods_are_contiguous(self):
        r = split_periods(self._START, self._END)
        assert r.validation_start == r.train_end + timedelta(days=1)
        assert r.test_start == r.validation_end + timedelta(days=1)

    def test_periods_are_non_overlapping(self):
        r = split_periods(self._START, self._END)
        assert r.train_end < r.validation_start
        assert r.validation_end < r.test_start

    def test_default_split_60_20_20(self):
        r = split_periods(self._START, self._END)
        total = (self._END - self._START).days
        train = (r.train_end - r.train_start).days
        val = (r.validation_end - r.validation_start).days
        # Train ≈ 60%, validation ≈ 20% (integer days, so ±1)
        assert abs(train / total - 0.60) < 0.01
        assert abs(val / total - 0.20) < 0.01

    def test_custom_split(self):
        r = split_periods(self._START, self._END, train_pct=0.50, validation_pct=0.25)
        total = (self._END - self._START).days
        train = (r.train_end - r.train_start).days
        assert abs(train / total - 0.50) < 0.01

    def test_start_equals_end_raises(self):
        with pytest.raises(ValueError):
            split_periods(date(2021, 1, 1), date(2021, 1, 1))

    def test_start_after_end_raises(self):
        with pytest.raises(ValueError):
            split_periods(date(2022, 1, 1), date(2020, 1, 1))

    def test_train_pct_zero_raises(self):
        with pytest.raises(ValueError):
            split_periods(self._START, self._END, train_pct=0.0)

    def test_sum_equals_one_raises(self):
        with pytest.raises(ValueError):
            split_periods(self._START, self._END, train_pct=0.80, validation_pct=0.20)

    def test_test_period_has_remaining_days(self):
        r = split_periods(self._START, self._END)
        test_days = (r.test_end - r.test_start).days
        assert test_days > 0


# ── PeriodSplit properties ─────────────────────────────────────────────────────

class TestPeriodSplitProperties:
    def _split(self) -> PeriodSplit:
        return split_periods(date(2018, 1, 1), date(2024, 1, 1))

    def test_train_years_positive(self):
        assert self._split().train_years > 0

    def test_validation_years_positive(self):
        assert self._split().validation_years > 0

    def test_test_years_positive(self):
        assert self._split().test_years > 0

    def test_full_start_equals_train_start(self):
        s = self._split()
        assert s.full_start == s.train_start

    def test_full_end_equals_test_end(self):
        s = self._split()
        assert s.full_end == s.test_end

    def test_in_period_train(self):
        s = self._split()
        assert s.in_period("train", s.train_start) is True
        assert s.in_period("train", s.train_end) is True
        assert s.in_period("train", s.validation_start) is False

    def test_in_period_validation(self):
        s = self._split()
        assert s.in_period("validation", s.validation_start) is True
        assert s.in_period("validation", s.train_end) is False

    def test_in_period_test(self):
        s = self._split()
        assert s.in_period("test", s.test_end) is True
        assert s.in_period("test", s.validation_end) is False

    def test_in_period_full_spans_all(self):
        s = self._split()
        assert s.in_period("full", s.train_start) is True
        assert s.in_period("full", s.test_end) is True
