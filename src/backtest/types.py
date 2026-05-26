from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from src.decision.engine import DecisionResult
from src.macro.tagger import MacroTag
from src.sentiment.scorer import SentimentResult


@dataclass
class HistoricalSnapshot:
    """
    Point-in-time view of a ticker at a single historical date.

    The caller guarantees that all fields reflect only information available
    at `as_of_date`.  The backtest engine audits structural integrity but
    cannot verify the upstream data provenance.
    """
    as_of_date: date
    ticker: str
    price: Optional[float]               # closing price on as_of_date; None if unavailable
    decision: DecisionResult             # pre-computed from decision.engine.decide()
    missing_fields: list[str] = field(default_factory=list)
    sentiment: Optional[SentimentResult] = None
    macro: Optional[MacroTag] = None


@dataclass
class TradeRecord:
    """A single completed trade: entry on BUY → exit on score drop, max hold, or end of simulation."""
    ticker: str
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    exit_reason: str           # "score_drop" | "max_hold" | "end_of_simulation"
    entry_score: float
    exit_score: Optional[float]
    entry_confidence: float
    hold_days: int
    hold_years: float
    return_pct: float          # (exit_price − entry_price) / entry_price
    annualized_return: Optional[float]  # None when hold < 1 month
