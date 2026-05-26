"""
Period splitter for train / validation / test isolation.

Splits a date range into three non-overlapping, contiguous windows used to:
  - train   : in-sample fitting of any heuristic thresholds
  - validation : tuning / sanity checks without touching test data
  - test    : true out-of-sample evaluation — must not influence design choices

Known limitation: financial time series have strong autocorrelation and regime
dependence.  A fixed 60/20/20 calendar split assigns more recent data to the
test period, which typically has fewer observations and may reflect a different
market regime from the training period.  This is the standard walk-forward
split; k-fold cross-validation is NOT used because it would allow future data
to inform past decisions.
"""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class PeriodSplit:
    """Non-overlapping, contiguous train / validation / test date boundaries."""
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    test_start: date
    test_end: date

    @property
    def train_years(self) -> float:
        return (self.train_end - self.train_start).days / 365.25

    @property
    def validation_years(self) -> float:
        return (self.validation_end - self.validation_start).days / 365.25

    @property
    def test_years(self) -> float:
        return (self.test_end - self.test_start).days / 365.25

    @property
    def full_start(self) -> date:
        return self.train_start

    @property
    def full_end(self) -> date:
        return self.test_end

    def in_period(self, period: str, d: date) -> bool:
        """Return True if date d falls within the named period."""
        if period == "train":
            return self.train_start <= d <= self.train_end
        if period == "validation":
            return self.validation_start <= d <= self.validation_end
        if period == "test":
            return self.test_start <= d <= self.test_end
        return self.train_start <= d <= self.test_end  # "full"


def split_periods(
    start: date,
    end: date,
    train_pct: float = 0.60,
    validation_pct: float = 0.20,
) -> PeriodSplit:
    """
    Split [start, end] into contiguous, non-overlapping train / validation / test windows.

    test_pct = 1 − train_pct − validation_pct (implicitly).

    Parameters
    ----------
    start          : First date of the full simulation window.
    end            : Last date of the full simulation window.
    train_pct      : Fraction of total days assigned to training. Default 0.60.
    validation_pct : Fraction of total days assigned to validation. Default 0.20.

    Raises
    ------
    ValueError if start >= end or if the proportions leave no test period.
    """
    if start >= end:
        raise ValueError(f"start ({start}) must be before end ({end})")
    if train_pct <= 0 or validation_pct <= 0 or train_pct + validation_pct >= 1.0:
        raise ValueError(
            f"train_pct ({train_pct}) and validation_pct ({validation_pct}) must each be "
            f"> 0 and sum to < 1.0"
        )

    total_days = (end - start).days
    train_days = int(total_days * train_pct)
    val_days = int(total_days * validation_pct)

    train_end = start + timedelta(days=train_days)
    val_start = train_end + timedelta(days=1)
    val_end = val_start + timedelta(days=val_days - 1)
    test_start = val_end + timedelta(days=1)

    return PeriodSplit(
        train_start=start,
        train_end=train_end,
        validation_start=val_start,
        validation_end=val_end,
        test_start=test_start,
        test_end=end,
    )
