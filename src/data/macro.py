from datetime import date

from src.data.models import MacroEvent
from src.logging.logger import log_input, log_result

_MODULE = "data.macro"

# Manually curated macro events.
# Add entries here as new global events occur.
# polarity is applied to each affected_sector for that event window.
_EVENTS: list[MacroEvent] = [
    MacroEvent(
        event_date=date(2022, 2, 24),
        description="Russia invades Ukraine",
        affected_sectors=["defense", "energy", "agriculture"],
        polarity=0.7,
    ),
    MacroEvent(
        event_date=date(2022, 3, 16),
        description="Fed begins aggressive rate hike cycle",
        affected_sectors=["financials", "utilities", "real_estate"],
        polarity=0.5,
    ),
    MacroEvent(
        event_date=date(2023, 10, 7),
        description="Hamas attacks Israel; Middle East conflict escalation",
        affected_sectors=["defense", "energy"],
        polarity=0.6,
    ),
    MacroEvent(
        event_date=date(2024, 1, 1),
        description="Elevated global inflation persists",
        affected_sectors=["consumer_staples", "energy", "materials"],
        polarity=0.3,
    ),
]


def get_active_events(as_of_date: date) -> list[MacroEvent]:
    """
    Return all macro events that occurred on or before as_of_date.
    Downstream modules apply their own decay / recency weighting.
    """
    log_input(_MODULE, {"as_of_date": str(as_of_date)})

    active = [e for e in _EVENTS if e.event_date <= as_of_date]

    log_result(_MODULE, {"as_of_date": str(as_of_date), "active_events": len(active)})
    return active


def sector_polarity(sector: str, as_of_date: date) -> float:
    """
    Net polarity for a sector from all active events.
    Returns a float in [-1, +1], clamped.
    """
    events = get_active_events(as_of_date)
    total = sum(e.polarity for e in events if sector in e.affected_sectors)
    return max(-1.0, min(1.0, total))
