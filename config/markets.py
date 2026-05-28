from dataclasses import dataclass


@dataclass(frozen=True)
class MarketProfile:
    code: str                     # ISO country code, e.g. "SE"
    name: str                     # Human-readable, e.g. "Sweden"
    ticker_suffix: str            # Appended to ticker for Yahoo Finance, e.g. ".ST"
    currency: str                 # ISO currency code, e.g. "SEK"

    # Dividend yield sweet spot — varies by market dividend culture
    dividend_yield_min: float     # Below this → building toward sweet spot
    dividend_yield_peak: float    # Ideal midpoint — scores 100
    dividend_yield_max: float     # Above this → caution begins
    dividend_yield_trap: float    # Above this → likely dividend trap, scores 0

    # Used as pe_5y_avg fallback when Yahoo Finance does not return it
    typical_pe: float


MARKETS: dict[str, MarketProfile] = {
    "US": MarketProfile(
        code="US", name="United States", ticker_suffix="", currency="USD",
        dividend_yield_min=0.02, dividend_yield_peak=0.035,
        dividend_yield_max=0.05, dividend_yield_trap=0.08,
        typical_pe=20.0,
    ),
    "SE": MarketProfile(
        code="SE", name="Sweden", ticker_suffix=".ST", currency="SEK",
        dividend_yield_min=0.03, dividend_yield_peak=0.05,
        dividend_yield_max=0.07, dividend_yield_trap=0.10,
        typical_pe=16.0,
    ),
    "GB": MarketProfile(
        code="GB", name="United Kingdom", ticker_suffix=".L", currency="GBP",
        dividend_yield_min=0.03, dividend_yield_peak=0.045,
        dividend_yield_max=0.06, dividend_yield_trap=0.09,
        typical_pe=14.0,
    ),
    "DE": MarketProfile(
        code="DE", name="Germany", ticker_suffix=".DE", currency="EUR",
        dividend_yield_min=0.02, dividend_yield_peak=0.04,
        dividend_yield_max=0.06, dividend_yield_trap=0.09,
        typical_pe=15.0,
    ),
    "FR": MarketProfile(
        code="FR", name="France", ticker_suffix=".PA", currency="EUR",
        dividend_yield_min=0.02, dividend_yield_peak=0.04,
        dividend_yield_max=0.065, dividend_yield_trap=0.10,
        typical_pe=14.0,
    ),
}


def get_market(code: str) -> MarketProfile:
    key = code.upper()
    if key not in MARKETS:
        raise ValueError(f"Unknown market '{code}'. Supported: {sorted(MARKETS)}")
    return MARKETS[key]
