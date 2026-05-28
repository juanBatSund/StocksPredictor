"""
Manually curated macro event registry.

This module maintains a chronological list of significant macro events that
the pipeline uses to provide context for investment decisions. The events feed
into macro.tagger.tag(), which classifies each description into a category,
maps it to sector-level impacts, and produces a MacroTag used by the decision
engine.

Curation guidelines
-------------------
- Add an event when it materially changes the investment backdrop for one or
  more sectors (central bank pivots, major conflicts, trade policy shifts,
  financial crises, pandemics).
- Use the description field as a concise free-text summary (1–2 sentences).
  macro.tagger.tag() uses keyword matching against this text, so include
  the key nouns and verbs — e.g. "rate hike", "tariff", "invasion".
- affected_sectors lists the broad sectors most directly impacted. This is
  used by get_active_events() callers that want a quick sector filter without
  running the full tagger.
- polarity is a rough directional signal for the sector list: positive = net
  bullish for the listed sectors, negative = net bearish. It is not used by
  the tagger (which computes its own per-sector direction/strength from the
  description text).
- Keep events ordered by event_date ascending.
- Do not delete past events — they are used by the backtest engine for
  point-in-time analysis.

Known limitations
-----------------
1. This list is manually maintained. Events will become stale unless someone
   adds new entries as the macro environment evolves.
2. polarity is a single scalar applied to all affected_sectors. It does not
   capture the mixed or sector-specific direction that macro.tagger produces.
   Use tagger.tag(description) when you need sector-level directionality.
3. Only the most recent event is used for live pipeline analysis. If the
   current environment is better described by multiple concurrent events
   (e.g. trade war + recession risk simultaneously), the single-event
   approach understates complexity. Extend ui/pipeline.py to pass the most
   relevant event description to tagger.tag() as warranted.
"""

from datetime import date

from src.data.models import MacroEvent
from src.logging.logger import log_input, log_result

_MODULE = "data.macro"


_EVENTS: list[MacroEvent] = [
    # ── 2022 ──────────────────────────────────────────────────────────────────
    MacroEvent(
        event_date=date(2022, 2, 24),
        description="Russia invades Ukraine; NATO nations impose broad sanctions and supply military aid",
        affected_sectors=["defense", "energy", "agriculture"],
        polarity=0.7,
    ),
    MacroEvent(
        event_date=date(2022, 3, 16),
        description="Fed begins aggressive rate hike cycle; 11 consecutive increases totalling 525 bps",
        affected_sectors=["financials", "utilities", "real_estate", "technology"],
        polarity=0.5,
    ),

    # ── 2023 ──────────────────────────────────────────────────────────────────
    MacroEvent(
        event_date=date(2023, 10, 7),
        description="Hamas attacks Israel; Middle East conflict escalation raises energy and defense uncertainty",
        affected_sectors=["defense", "energy"],
        polarity=0.6,
    ),

    # ── 2024 ──────────────────────────────────────────────────────────────────
    MacroEvent(
        event_date=date(2024, 1, 1),
        description="Elevated global inflation persists; central banks maintain restrictive rates",
        affected_sectors=["consumer_staples", "energy", "materials"],
        polarity=0.3,
    ),
    MacroEvent(
        event_date=date(2024, 9, 18),
        description=(
            "Fed begins monetary policy easing cycle with 50 bps rate cut; "
            "signals further cuts as inflation moderates toward 2% target"
        ),
        affected_sectors=["real_estate", "technology", "consumer_discretionary", "utilities"],
        polarity=0.7,
    ),
    MacroEvent(
        event_date=date(2024, 11, 5),
        description=(
            "US presidential election: Trump wins; market expectations shift toward "
            "deregulation, corporate tax cuts, and increased trade protectionism"
        ),
        affected_sectors=["financials", "energy", "defense", "technology"],
        polarity=0.5,
    ),

    # ── 2025 ──────────────────────────────────────────────────────────────────
    MacroEvent(
        event_date=date(2025, 1, 20),
        description=(
            "Trump administration inaugurated; executive orders signal aggressive "
            "tariff policy, deregulation of energy sector, and reduced climate commitments"
        ),
        affected_sectors=["energy", "financials", "technology", "materials"],
        polarity=0.4,
    ),
    MacroEvent(
        event_date=date(2025, 4, 2),
        description=(
            "Trump announces sweeping 'Liberation Day' tariffs: universal 10% baseline "
            "plus targeted duties up to 145% on Chinese goods; trade war escalation "
            "raises recession risk and disrupts global supply chains"
        ),
        affected_sectors=["technology", "consumer_discretionary", "materials", "industrials"],
        polarity=-0.6,
    ),
    MacroEvent(
        event_date=date(2025, 5, 12),
        description=(
            "US-China trade truce: 90-day tariff pause reduces duties from 145% to 30% "
            "on Chinese goods; partial relief for technology and consumer supply chains "
            "but structural trade tensions remain elevated"
        ),
        affected_sectors=["technology", "consumer_discretionary", "materials"],
        polarity=0.4,
    ),
]


def get_active_events(as_of_date: date) -> list[MacroEvent]:
    """
    Return all macro events that occurred on or before as_of_date, oldest-first.

    Used by the backtest engine for point-in-time isolation: passing the
    snapshot date ensures only historically available events influence the
    decision at that point in time.
    """
    log_input(_MODULE, {"as_of_date": str(as_of_date)})
    active = [e for e in _EVENTS if e.event_date <= as_of_date]
    log_result(_MODULE, {"as_of_date": str(as_of_date), "active_events": len(active)})
    return active


def get_latest_event(as_of_date: date) -> MacroEvent | None:
    """
    Return the single most recent macro event on or before as_of_date.

    Convenience accessor for the live pipeline, which uses one dominant
    macro context rather than a full historical sequence.
    Returns None if no events exist on or before as_of_date.
    """
    active = get_active_events(as_of_date)
    return active[-1] if active else None


def sector_polarity(sector: str, as_of_date: date) -> float:
    """
    Net polarity for a sector from all active events.
    Returns a float in [-1, +1], clamped.

    Note: this is a coarse signal. Use macro.tagger.tag() for sector-level
    directionality with full category classification and confidence scores.
    """
    events = get_active_events(as_of_date)
    total = sum(e.polarity for e in events if sector in e.affected_sectors)
    return max(-1.0, min(1.0, total))
