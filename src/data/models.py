from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass(frozen=True)
class PriceRecord:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class Fundamentals:
    # Quality
    roe: Optional[float]                  # Return on equity (e.g. 0.15 = 15%)
    debt_to_equity: Optional[float]
    free_cash_flow: Optional[float]       # USD

    # Growth
    revenue_growth_5y: Optional[float]    # Annualised (e.g. 0.08 = 8%)
    earnings_growth_5y: Optional[float]

    # Dividend
    dividend_yield: Optional[float]       # (e.g. 0.03 = 3%)
    payout_ratio: Optional[float]
    dividend_growth_streak_years: Optional[int]

    # Valuation
    pe_ratio: Optional[float]
    pe_5y_avg: Optional[float]
    dividend_yield_5y_avg: Optional[float] = None  # stock-specific historical avg


@dataclass(frozen=True)
class MacroEvent:
    event_date: date
    description: str
    affected_sectors: list[str]           # e.g. ["defense", "energy"]
    polarity: float                       # -1.0 to +1.0 per sector


@dataclass
class StockData:
    ticker: str
    market_code: str                      # e.g. "US", "SE" — determines exchange and thresholds
    fetched_at: datetime                  # UTC timestamp of ingestion
    as_of_date: Optional[date]           # Point-in-time date for backtest isolation
    prices: list[PriceRecord]
    fundamentals: Fundamentals
    missing_fields: list[str] = field(default_factory=list)  # Fields that could not be fetched

    @property
    def latest_price(self) -> Optional[float]:
        return self.prices[-1].close if self.prices else None

    @property
    def has_complete_fundamentals(self) -> bool:
        return len(self.missing_fields) == 0
