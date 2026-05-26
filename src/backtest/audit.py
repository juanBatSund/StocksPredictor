"""
Data leakage structural audit for the backtesting engine.

Checks that the snapshot sequence is internally consistent:
  - every snapshot has an as_of_date
  - snapshots are in non-decreasing chronological order
  - no duplicate dates exist for the same ticker

IMPORTANT LIMITATION: this is a structural audit only.  It cannot verify
that the upstream data sources (yfinance, news APIs, macro feeds) were queried
with point-in-time constraints.  External data provenance verification requires
an audit trail outside this system.
"""

from dataclasses import dataclass

from src.backtest.types import HistoricalSnapshot


@dataclass
class LeakageAudit:
    passed: bool
    violations: list[str]
    snapshots_checked: int
    notes: list[str]


def audit(snapshots: list[HistoricalSnapshot]) -> LeakageAudit:
    """
    Structural leakage audit on a list of HistoricalSnapshot objects.

    Violations detected:
      1. Snapshot with as_of_date = None — isolation cannot be verified.
      2. Out-of-order snapshot — as_of_date precedes the previous snapshot's date.
      3. Duplicate as_of_date — ambiguous point-in-time state.
    """
    violations: list[str] = []
    prev_date = None

    for snap in snapshots:
        if snap.as_of_date is None:
            violations.append(
                f"{snap.ticker}: as_of_date is None — cannot verify data isolation"
            )
            continue

        if prev_date is not None and snap.as_of_date < prev_date:
            violations.append(
                f"{snap.ticker}: snapshot {snap.as_of_date} precedes previous "
                f"snapshot {prev_date} — out-of-order input"
            )

        prev_date = snap.as_of_date

    # Duplicate date check (after the loop to catch all dates first)
    valid_dates = [s.as_of_date for s in snapshots if s.as_of_date is not None]
    seen: set = set()
    for d in valid_dates:
        if d in seen:
            violations.append(
                f"Duplicate snapshot date {d} — ambiguous point-in-time state"
            )
        seen.add(d)

    notes = [
        "Structural audit only: cannot verify that upstream data sources "
        "were queried with point-in-time constraints.",
        f"Checked {len(snapshots)} snapshot(s); found {len(violations)} violation(s).",
    ]

    return LeakageAudit(
        passed=len(violations) == 0,
        violations=violations,
        snapshots_checked=len(snapshots),
        notes=notes,
    )
