"""
Tests for src/data/macro.py

Verifies the event registry, get_active_events(), get_latest_event(),
and sector_polarity() without making any external calls.
"""

import pytest
from datetime import date

from src.data.macro import (
    _EVENTS,
    get_active_events,
    get_latest_event,
    sector_polarity,
)


# ── Registry invariants ────────────────────────────────────────────────────────

class TestRegistry:
    def test_events_list_is_nonempty(self):
        assert len(_EVENTS) > 0

    def test_events_sorted_chronologically(self):
        dates = [e.event_date for e in _EVENTS]
        assert dates == sorted(dates), "Events must be ordered by event_date ascending"

    def test_all_events_have_description(self):
        for e in _EVENTS:
            assert e.description.strip(), f"Empty description for event on {e.event_date}"

    def test_all_events_have_affected_sectors(self):
        for e in _EVENTS:
            assert len(e.affected_sectors) > 0, f"No sectors for event on {e.event_date}"

    def test_all_polarities_in_range(self):
        for e in _EVENTS:
            assert -1.0 <= e.polarity <= 1.0, (
                f"Polarity {e.polarity} out of range for event on {e.event_date}"
            )

    def test_covers_2022_through_2025(self):
        years = {e.event_date.year for e in _EVENTS}
        for y in (2022, 2023, 2024, 2025):
            assert y in years, f"No events for year {y}"

    def test_no_future_events_beyond_knowledge_cutoff(self):
        # Events should not be dated beyond the model's knowledge (Aug 2025)
        cutoff = date(2025, 8, 31)
        for e in _EVENTS:
            assert e.event_date <= cutoff, (
                f"Event dated {e.event_date} is beyond knowledge cutoff"
            )


# ── get_active_events ──────────────────────────────────────────────────────────

class TestGetActiveEvents:
    def test_returns_only_events_on_or_before_date(self):
        # Use the date of the first event to get just that one
        first = _EVENTS[0]
        result = get_active_events(first.event_date)
        assert all(e.event_date <= first.event_date for e in result)
        assert first in result

    def test_returns_empty_before_all_events(self):
        result = get_active_events(date(2000, 1, 1))
        assert result == []

    def test_returns_all_events_at_far_future_date(self):
        result = get_active_events(date(2099, 12, 31))
        assert len(result) == len(_EVENTS)

    def test_includes_event_on_exact_date(self):
        first = _EVENTS[0]
        result = get_active_events(first.event_date)
        assert first in result

    def test_excludes_event_one_day_before(self):
        first = _EVENTS[0]
        day_before = date(first.event_date.year,
                          first.event_date.month,
                          first.event_date.day - 1)
        result = get_active_events(day_before)
        assert first not in result

    def test_result_is_ordered_oldest_first(self):
        result = get_active_events(date(2099, 12, 31))
        dates = [e.event_date for e in result]
        assert dates == sorted(dates)

    def test_count_increases_with_later_date(self):
        early = get_active_events(date(2022, 12, 31))
        late  = get_active_events(date(2025, 12, 31))
        assert len(late) >= len(early)


# ── get_latest_event ──────────────────────────────────────────────────────────

class TestGetLatestEvent:
    def test_returns_most_recent_event(self):
        result = get_latest_event(date(2099, 12, 31))
        assert result == _EVENTS[-1]

    def test_returns_none_before_any_event(self):
        result = get_latest_event(date(2000, 1, 1))
        assert result is None

    def test_returns_event_on_exact_date(self):
        first = _EVENTS[0]
        result = get_latest_event(first.event_date)
        assert result is not None
        assert result.event_date <= first.event_date

    def test_returns_correct_event_at_boundary(self):
        # At the date of the second event, latest should be the second
        if len(_EVENTS) >= 2:
            second = _EVENTS[1]
            result = get_latest_event(second.event_date)
            assert result.event_date <= second.event_date
            # and it should be at least as recent as the second event's date
            assert result.event_date == second.event_date or result == _EVENTS[1]

    def test_description_is_nonempty_string(self):
        result = get_latest_event(date(2099, 1, 1))
        assert result is not None
        assert isinstance(result.description, str)
        assert len(result.description) > 0


# ── sector_polarity ───────────────────────────────────────────────────────────

class TestSectorPolarity:
    def test_returns_float(self):
        val = sector_polarity("energy", date(2099, 12, 31))
        assert isinstance(val, float)

    def test_clamped_to_minus_one_plus_one(self):
        val = sector_polarity("energy", date(2099, 12, 31))
        assert -1.0 <= val <= 1.0

    def test_sector_with_no_events_returns_zero(self):
        val = sector_polarity("nonexistent_sector_xyz", date(2099, 12, 31))
        assert val == 0.0

    def test_no_active_events_returns_zero(self):
        val = sector_polarity("energy", date(2000, 1, 1))
        assert val == 0.0

    def test_known_sector_has_nonzero_polarity(self):
        # Energy appears in multiple events — polarity should be non-zero
        val = sector_polarity("energy", date(2099, 12, 31))
        assert val != 0.0


# ── Integration: latest event description feeds the macro tagger ──────────────

class TestIntegrationWithTagger:
    def test_latest_description_is_classifiable(self):
        """The most recent event's description should produce a non-unknown MacroTag."""
        from src.macro.tagger import tag

        latest = get_latest_event(date(2099, 12, 31))
        assert latest is not None

        result = tag(latest.description)
        assert result.category != "unknown", (
            f"Latest macro event description '{latest.description}' "
            f"could not be classified by the tagger"
        )

    def test_all_event_descriptions_are_classifiable(self):
        """Every event in the registry should map to a known macro category."""
        from src.macro.tagger import tag

        unclassified = []
        for event in _EVENTS:
            result = tag(event.description)
            if result.category == "unknown":
                unclassified.append((event.event_date, event.description))

        assert not unclassified, (
            f"{len(unclassified)} event(s) could not be classified:\n"
            + "\n".join(f"  {d}: {desc}" for d, desc in unclassified)
        )
