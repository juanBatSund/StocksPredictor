"""
Curated ticker lists for the screener.

Each list contains tickers as they appear on their home exchange, without
the exchange suffix (that is appended by MarketProfile.ticker_suffix).

MARKET_TICKERS maps market_code → list of (ticker, market_code) pairs so
that screener.py can iterate over a single flat sequence per region.

Maintenance notes
-----------------
- These lists reflect approximate market-cap rankings as of mid-2025.
- Some tickers may return incomplete data from Yahoo Finance. The screener
  handles this gracefully — it logs an error result and continues.
- To add a ticker: append it to the appropriate list and re-run the screener.
- European tickers use the dominant home-exchange listing:
    DE  → Frankfurt Xetra  (.DE)
    GB  → London Stock Exchange  (.L)
    FR  → Euronext Paris  (.PA)
"""

# ── United States — S&P 500 top ~100 by market cap ───────────────────────────

US: list[str] = [
    # Mega-cap technology
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "LLY", "BRK-B",
    # Financials
    "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "BLK", "SCHW",
    # Healthcare
    "UNH", "JNJ", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR", "AMGN", "ISRG",
    # Consumer staples & discretionary
    "PG", "KO", "PEP", "WMT", "COST", "HD", "MCD", "NKE", "SBUX", "TGT",
    # Energy
    "XOM", "CVX", "COP", "EOG", "SLB",
    # Industrials
    "CAT", "BA", "HON", "GE", "RTX", "LMT", "UPS", "DE", "ETN", "ITW",
    # Communication services
    "VZ", "T", "DIS", "NFLX", "CMCSA",
    # Technology (continued)
    "CRM", "ADBE", "CSCO", "AMD", "QCOM", "TXN", "INTU", "IBM", "ACN", "ORCL",
    # Pharma / biotech
    "GILD", "VRTX", "REGN", "BMY", "CI", "ELV", "ABBV",
    # Materials & chemicals
    "LIN", "SHW", "ECL", "APD",
    # Real estate & infrastructure
    "PLD", "EQIX",
    # Diversified & financial services
    "SPGI", "MCO", "CME", "FI", "MMC", "AON",
    # Medtech
    "SYK", "MDT", "BSX", "EW", "ZTS",
    # Semiconductors
    "LRCX", "KLAC", "ADI", "PANW",
    # Misc large-cap
    "NOW", "BKNG", "GD", "USB", "PNC", "TFC", "AFL", "MMM", "LOW",
]

# ── Sweden — OMX Stockholm top ~50 ───────────────────────────────────────────

SE: list[str] = [
    # Large caps (OMXS30)
    "VOLV-B", "ERIC-B", "ATCO-A", "ATCO-B", "SEB-A",
    "SWED-A", "HM-B", "SAND", "SHB-A", "HEXA-B",
    "INVE-B", "SKF-B", "ABB", "NIBE-B", "ESSITY-B",
    "ALFA", "ASSA-B", "NDA-SE", "EVO", "TELIA",
    # Mid-large caps
    "SCA-B", "EPI-B", "SAAB-B", "ICA", "AXFO",
    "THULE", "LOOMIS", "CAST", "SWECO-B", "LIFCO-B",
    "HUSQ-B", "BRAV", "INDT", "KINV-B", "SINCH",
    "SECU-B", "ADDT-B", "LATO-B", "FABG", "BALD-B",
    # Smaller large-caps
    "HMS", "BOL", "GETI-B", "DIOS", "COOR",
    "VITR", "BEIJ-B", "SWOL-B", "ADDLIFE-B", "NEVI",
]

# ── Europe — top companies by country ────────────────────────────────────────

# Germany — DAX 40 + selected MDAX
_EU_DE: list[tuple[str, str]] = [
    ("SAP",   "DE"),  # SAP SE
    ("SIE",   "DE"),  # Siemens AG
    ("ALV",   "DE"),  # Allianz SE
    ("MUV2",  "DE"),  # Munich Re
    ("MBG",   "DE"),  # Mercedes-Benz Group
    ("BMW",   "DE"),  # BMW AG
    ("BAS",   "DE"),  # BASF SE
    ("BAYN",  "DE"),  # Bayer AG
    ("DTE",   "DE"),  # Deutsche Telekom
    ("DBK",   "DE"),  # Deutsche Bank
    ("ADS",   "DE"),  # Adidas AG
    ("RWE",   "DE"),  # RWE AG
    ("EOAN",  "DE"),  # E.ON SE
    ("VOW3",  "DE"),  # Volkswagen AG (preferred)
    ("CON",   "DE"),  # Continental AG
    ("HEN3",  "DE"),  # Henkel AG (preferred)
    ("FRE",   "DE"),  # Fresenius SE
    ("DHL",   "DE"),  # DHL Group
    ("DB1",   "DE"),  # Deutsche Börse
    ("SHL",   "DE"),  # Siemens Healthineers
    ("IFX",   "DE"),  # Infineon Technologies
    ("VNA",   "DE"),  # Vonovia SE
    ("MTX",   "DE"),  # MTU Aero Engines
    ("RHM",   "DE"),  # Rheinmetall AG
    ("ENR",   "DE"),  # Siemens Energy
    ("ZAL",   "DE"),  # Zalando SE
    ("MRK",   "DE"),  # Merck KGaA (note: different from US MRK)
    ("HNR1",  "DE"),  # Hannover Rück
    ("QIA",   "DE"),  # Qiagen NV
    ("SRT3",  "DE"),  # Sartorius AG (preferred)
]

# United Kingdom — FTSE 100 top companies
_EU_GB: list[tuple[str, str]] = [
    ("AZN",   "GB"),  # AstraZeneca
    ("SHEL",  "GB"),  # Shell
    ("HSBA",  "GB"),  # HSBC Holdings
    ("ULVR",  "GB"),  # Unilever
    ("GSK",   "GB"),  # GSK
    ("BP",    "GB"),  # BP
    ("RIO",   "GB"),  # Rio Tinto
    ("LLOY",  "GB"),  # Lloyds Banking Group
    ("BARC",  "GB"),  # Barclays
    ("BATS",  "GB"),  # British American Tobacco
    ("REL",   "GB"),  # RELX
    ("DGE",   "GB"),  # Diageo
    ("CPG",   "GB"),  # Compass Group
    ("GLEN",  "GB"),  # Glencore
    ("RR",    "GB"),  # Rolls-Royce Holdings
    ("IMB",   "GB"),  # Imperial Brands
    ("SSE",   "GB"),  # SSE
    ("NG",    "GB"),  # National Grid
    ("TSCO",  "GB"),  # Tesco
    ("WPP",   "GB"),  # WPP
    ("BHP",   "GB"),  # BHP Group
    ("AAL",   "GB"),  # Anglo American
    ("EXPN",  "GB"),  # Experian
    ("ABF",   "GB"),  # Associated British Foods
    ("SBRY",  "GB"),  # J Sainsbury
    ("MKS",   "GB"),  # Marks & Spencer
    ("AUTO",  "GB"),  # Auto Trader Group
    ("CRDA",  "GB"),  # Croda International
    ("LGEN",  "GB"),  # Legal & General
    ("NXT",   "GB"),  # Next
    ("BT-A",  "GB"),  # BT Group
    ("NWG",   "GB"),  # NatWest Group
    ("STAN",  "GB"),  # Standard Chartered
    ("PRU",   "GB"),  # Prudential
    ("LSEG",  "GB"),  # London Stock Exchange Group
    ("III",   "GB"),  # 3i Group
    ("WTB",   "GB"),  # Whitbread
    ("HLMA",  "GB"),  # Halma
    ("MNDI",  "GB"),  # Mondi
    ("LAND",  "GB"),  # Land Securities
]

# France — CAC 40 + selected SBF 120
_EU_FR: list[tuple[str, str]] = [
    ("MC",    "FR"),  # LVMH
    ("TTE",   "FR"),  # TotalEnergies
    ("SAN",   "FR"),  # Sanofi
    ("BNP",   "FR"),  # BNP Paribas
    ("SU",    "FR"),  # Schneider Electric
    ("AI",    "FR"),  # Air Liquide
    ("OR",    "FR"),  # L'Oréal
    ("DG",    "FR"),  # Vinci
    ("ORA",   "FR"),  # Orange
    ("GLE",   "FR"),  # Société Générale
    ("KER",   "FR"),  # Kering
    ("CAP",   "FR"),  # Capgemini
    ("RI",    "FR"),  # Pernod Ricard
    ("VIE",   "FR"),  # Veolia Environnement
    ("EN",    "FR"),  # Bouygues
    ("SGO",   "FR"),  # Saint-Gobain
    ("ACA",   "FR"),  # Crédit Agricole
    ("RNO",   "FR"),  # Renault
    ("DSY",   "FR"),  # Dassault Systèmes
    ("AIR",   "FR"),  # Airbus SE
    ("ENGI",  "FR"),  # Engie
    ("ML",    "FR"),  # Michelin
    ("CA",    "FR"),  # Carrefour
    ("BVI",   "FR"),  # Bureau Veritas
    ("STM",   "FR"),  # STMicroelectronics
]

EU: list[tuple[str, str]] = _EU_DE + _EU_GB + _EU_FR

# ── Screener index ────────────────────────────────────────────────────────────

# Each value is a list of (ticker, market_code) pairs
MARKET_TICKERS: dict[str, list[tuple[str, str]]] = {
    "US": [(t, "US") for t in US],
    "SE": [(t, "SE") for t in SE],
    "EU": EU,
}

MARKET_LABELS: dict[str, str] = {
    "US": "United States",
    "SE": "Sweden",
    "EU": "Europe (DE / GB / FR)",
}
