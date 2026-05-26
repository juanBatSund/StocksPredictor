"""
Rule tables for the macro event tagger.

KNOWN LIMITATIONS — read before extending this file:

  1. Sector impact strengths are empirically uncalibrated. Values such as
     "defense: strength 0.80 during geopolitical conflict" are informed
     judgements, not regression-derived coefficients from event studies.

  2. Direction ("bullish" / "bearish") is unconditional. It assumes a long
     position in the sector. Context such as time-horizon, country exposure,
     or existing portfolio hedges is ignored.

  3. "mixed" is used when the impact direction is genuinely contested
     across sub-types of the event (e.g. inflation is bullish for energy
     but bearish for consumer discretionary). It is not a cop-out — it is
     a signal that the sector requires deeper analysis.

  4. Category keyword lists are closed. Novel events that do not map to
     any category will produce category="unknown". Extend CATEGORY_KEYWORDS
     when new event types are encountered.

  5. Keyword matching is substring-based after tokenisation. Longer phrases
     are listed first in each category list so they match before their
     component words create spurious shorter-match noise.
"""

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Category keywords — matched against (description + headlines) token string
# Keys must be lowercase; no punctuation (tokeniser strips it).
# List each phrase BEFORE its component words to avoid partial-match noise.
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "geopolitical_conflict": [
        # Phrases first
        "military action", "drone strike", "ground offensive", "air strike",
        "cease fire", "ceasefire", "arms shipment", "nuclear threat",
        "naval blockade", "troop deployment",
        # Words
        "invasion", "invades", "invaded", "war", "warfare", "conflict",
        "military", "troops", "missile", "bombing", "bombed", "bomb",
        "terrorism", "terrorist", "hostilities", "siege", "battle",
        "coup", "insurgency", "nato", "escalation", "weapons", "sanctions",
        "occupation",
    ],
    "monetary_policy_tightening": [
        # Phrases first
        "rate hike", "rate hikes", "interest rate increase", "interest rate rises",
        "basis points higher", "basis points increase", "quantitative tightening",
        "fed funds rate increase", "policy rate increase", "tightening cycle",
        "fed hikes", "ecb hikes", "boe hikes",
        # Words
        "tightening", "hawkish", "hawkishness",
    ],
    "monetary_policy_easing": [
        # Phrases first
        "rate cut", "rate cuts", "interest rate cut", "interest rate falls",
        "basis points lower", "basis points cut", "quantitative easing",
        "fed funds rate cut", "policy rate cut", "easing cycle",
        "fed cuts", "ecb cuts", "boe cuts", "rate reduction",
        # Words
        "easing", "dovish", "dovishness", "stimulus", "accommodation",
    ],
    "inflation": [
        # Phrases first
        "consumer price index", "producer price index", "cost of living",
        "price pressures", "price surge", "inflation data", "inflation report",
        "core inflation", "headline inflation", "inflationary pressure",
        # Words
        "inflation", "inflationary", "cpi", "pce", "ppi",
    ],
    "recession_risk": [
        # Phrases first
        "gdp contraction", "gdp shrinks", "gdp falls", "economic slowdown",
        "economic contraction", "negative growth", "unemployment rises",
        "job losses", "credit contraction",
        # Words
        "recession", "depression", "downturn", "stagflation",
    ],
    "trade_policy": [
        # Phrases first
        "trade war", "import duty", "import tariff", "export controls",
        "trade sanctions", "trade deal", "trade agreement", "trade restrictions",
        "supply chain disruption", "trade deficit", "trade surplus",
        # Words
        "tariff", "tariffs", "protectionism", "wto", "dumping",
    ],
    "energy_shock": [
        # Phrases first
        "oil price", "crude oil", "oil supply", "oil embargo", "gas price",
        "energy prices", "energy crisis", "natural gas", "oil shock",
        "opec cut", "opec increase",
        # Words
        "opec", "lng", "pipeline", "brent", "wti",
    ],
    "pandemic": [
        # Phrases first
        "public health emergency", "disease outbreak", "new variant",
        "health crisis",
        # Words
        "pandemic", "epidemic", "virus", "covid", "outbreak",
        "lockdown", "quarantine", "pathogen",
    ],
    "financial_crisis": [
        # Phrases first
        "bank failure", "bank run", "bank collapse", "credit crisis",
        "banking crisis", "systemic risk", "liquidity crunch",
        "financial contagion", "bank bailout",
        # Words
        "contagion", "bailout", "insolvency", "solvency",
    ],
    "regulatory": [
        # Phrases first
        "antitrust investigation", "executive order", "government policy",
        "policy change", "new regulation", "new law", "regulatory action",
        "carbon tax", "windfall tax",
        # Words
        "regulation", "legislation", "antitrust", "regulatory", "compliance",
    ],
    "natural_disaster": [
        # Phrases first
        "natural disaster", "category 5", "7 magnitude",
        # Words
        "earthquake", "hurricane", "typhoon", "flood", "flooding",
        "tornado", "tsunami", "wildfire", "drought",
    ],
    "election_political": [
        # Phrases first
        "election results", "government change", "political transition",
        "new government", "snap election", "coalition government",
        "political uncertainty",
        # Words
        "election", "referendum", "impeachment", "inaugurated",
    ],
}

# Human-readable labels for each category
CATEGORY_LABELS: dict[str, str] = {
    "geopolitical_conflict":      "Geopolitical Conflict",
    "monetary_policy_tightening": "Monetary Policy Tightening",
    "monetary_policy_easing":     "Monetary Policy Easing",
    "inflation":                  "Inflation / Price Pressure",
    "recession_risk":             "Recession Risk",
    "trade_policy":               "Trade Policy",
    "energy_shock":               "Energy Shock",
    "pandemic":                   "Pandemic / Health Crisis",
    "financial_crisis":           "Financial Crisis",
    "regulatory":                 "Regulatory / Policy Change",
    "natural_disaster":           "Natural Disaster",
    "election_political":         "Election / Political Transition",
    "unknown":                    "Unknown / Unclassified",
}


# ---------------------------------------------------------------------------
# Sector impact table
# direction: "bullish" | "bearish" | "mixed"
# strength:  0.0–1.0 — impact magnitude. EMPIRICALLY UNCALIBRATED.
# reasoning: one-line explanation of the causal link.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SectorImpactRule:
    direction: str
    strength: float
    reasoning: str


# Each category maps to a dict of {sector: SectorImpactRule}
SECTOR_IMPACTS: dict[str, dict[str, SectorImpactRule]] = {
    "geopolitical_conflict": {
        "defense":                SectorImpactRule("bullish", 0.80, "Increased defence spending and procurement"),
        "energy":                 SectorImpactRule("bullish", 0.60, "Supply disruption risk raises commodity prices"),
        "agriculture":            SectorImpactRule("mixed",   0.40, "Disrupted trade routes; depends on geography"),
        "technology":             SectorImpactRule("bearish", 0.30, "Risk-off rotation; supply chain exposure"),
        "consumer_discretionary": SectorImpactRule("bearish", 0.40, "Consumer uncertainty and risk aversion"),
        "travel":                 SectorImpactRule("bearish", 0.60, "Route closures and demand destruction"),
        "financials":             SectorImpactRule("bearish", 0.30, "Sanctions exposure and credit risk"),
        "materials":              SectorImpactRule("bullish", 0.30, "Commodities bid up by supply uncertainty"),
    },
    "monetary_policy_tightening": {
        "financials":             SectorImpactRule("bullish", 0.60, "Net interest margin expansion benefits banks"),
        "utilities":              SectorImpactRule("bearish", 0.60, "High debt loads become more expensive"),
        "real_estate":            SectorImpactRule("bearish", 0.70, "Mortgage rates rise, reducing affordability"),
        "technology":             SectorImpactRule("bearish", 0.55, "Higher discount rate compresses growth multiples"),
        "consumer_discretionary": SectorImpactRule("bearish", 0.40, "Higher borrowing costs reduce spending"),
        "materials":              SectorImpactRule("bearish", 0.25, "Tighter credit dampens capex and demand"),
        "consumer_staples":       SectorImpactRule("bearish", 0.20, "Mild drag from slowing economy"),
        "healthcare":             SectorImpactRule("mixed",   0.15, "Largely defensive; some debt sensitivity"),
    },
    "monetary_policy_easing": {
        "real_estate":            SectorImpactRule("bullish", 0.70, "Lower mortgage rates stimulate demand"),
        "technology":             SectorImpactRule("bullish", 0.60, "Lower discount rate re-rates growth stocks"),
        "consumer_discretionary": SectorImpactRule("bullish", 0.45, "Cheaper credit stimulates spending"),
        "utilities":              SectorImpactRule("bullish", 0.50, "Debt refinancing relief; yield-spread narrows"),
        "materials":              SectorImpactRule("bullish", 0.35, "Capex and construction activity pick up"),
        "financials":             SectorImpactRule("bearish", 0.35, "Net interest margin compression"),
        "consumer_staples":       SectorImpactRule("bullish", 0.20, "Mild tailwind from improved confidence"),
    },
    "inflation": {
        "energy":                 SectorImpactRule("bullish", 0.55, "Rising commodity prices directly benefit producers"),
        "materials":              SectorImpactRule("bullish", 0.50, "Input commodity prices rise with CPI"),
        "consumer_staples":       SectorImpactRule("mixed",   0.40, "Pass-through ability varies; volumes at risk"),
        "real_estate":            SectorImpactRule("mixed",   0.35, "Property as inflation hedge vs higher rates headwind"),
        "consumer_discretionary": SectorImpactRule("bearish", 0.55, "Real income erosion reduces discretionary spend"),
        "technology":             SectorImpactRule("bearish", 0.30, "Rate-hike expectations compress multiples"),
        "utilities":              SectorImpactRule("bearish", 0.30, "Cost pressures without instant tariff pass-through"),
        "financials":             SectorImpactRule("mixed",   0.25, "Benefits from higher rates; credit quality risk"),
    },
    "recession_risk": {
        "consumer_discretionary": SectorImpactRule("bearish", 0.75, "Spending cut sharply in downturns"),
        "financials":             SectorImpactRule("bearish", 0.65, "Loan losses rise and credit tightens"),
        "materials":              SectorImpactRule("bearish", 0.60, "Industrial demand collapses"),
        "technology":             SectorImpactRule("bearish", 0.50, "Enterprise spend cut; valuations decompressed"),
        "industrials":            SectorImpactRule("bearish", 0.60, "Capex deferred; order books weaken"),
        "consumer_staples":       SectorImpactRule("bullish", 0.35, "Defensive rotation; inelastic demand"),
        "healthcare":             SectorImpactRule("bullish", 0.30, "Defensive; demand largely inelastic"),
        "utilities":              SectorImpactRule("bullish", 0.25, "Defensive; regulated revenues"),
    },
    "trade_policy": {
        "technology":             SectorImpactRule("bearish", 0.55, "Export controls and supply chain fragmentation"),
        "materials":              SectorImpactRule("bearish", 0.45, "Disrupted input supply chains"),
        "consumer_discretionary": SectorImpactRule("bearish", 0.45, "Higher import costs on finished goods"),
        "consumer_staples":       SectorImpactRule("bearish", 0.30, "Food and goods import costs rise"),
        "agriculture":            SectorImpactRule("mixed",   0.50, "May gain from protection or lose from retaliation"),
        "industrials":            SectorImpactRule("mixed",   0.40, "Equipment supply chains disrupted; reshoring possible"),
        "financials":             SectorImpactRule("bearish", 0.25, "Trade finance volumes at risk"),
    },
    "energy_shock": {
        "energy":                 SectorImpactRule("bullish", 0.85, "Direct revenue and margin uplift from higher prices"),
        "materials":              SectorImpactRule("bullish", 0.40, "Related commodity prices bid higher"),
        "consumer_discretionary": SectorImpactRule("bearish", 0.65, "Fuel costs squeeze consumer budgets"),
        "industrials":            SectorImpactRule("bearish", 0.55, "Energy-intensive production costs rise sharply"),
        "consumer_staples":       SectorImpactRule("bearish", 0.40, "Transport and logistics cost increases"),
        "utilities":              SectorImpactRule("mixed",   0.40, "Fuel-based utilities hurt; renewables may benefit"),
        "technology":             SectorImpactRule("bearish", 0.20, "Data centre energy costs rise"),
        "agriculture":            SectorImpactRule("bearish", 0.35, "Fertiliser and machinery fuel costs rise"),
    },
    "pandemic": {
        "healthcare":             SectorImpactRule("bullish", 0.70, "Demand for diagnostics, treatments, and vaccines"),
        "technology":             SectorImpactRule("bullish", 0.55, "Remote work, e-commerce, and cloud adoption"),
        "consumer_staples":       SectorImpactRule("bullish", 0.35, "Pantry-loading and essential goods demand"),
        "travel":                 SectorImpactRule("bearish", 0.90, "Border closures and demand destruction"),
        "consumer_discretionary": SectorImpactRule("bearish", 0.75, "Leisure, hospitality, and retail shutdowns"),
        "real_estate":            SectorImpactRule("bearish", 0.45, "Commercial property vacated; residential mixed"),
        "financials":             SectorImpactRule("bearish", 0.40, "Loan forbearance and credit loss provisions"),
        "industrials":            SectorImpactRule("bearish", 0.45, "Supply chain disruptions and factory closures"),
    },
    "financial_crisis": {
        "financials":             SectorImpactRule("bearish", 0.90, "Epicentre of credit losses and capital constraints"),
        "real_estate":            SectorImpactRule("bearish", 0.75, "Credit dries up; forced selling and price declines"),
        "consumer_discretionary": SectorImpactRule("bearish", 0.65, "Credit access tightens; confidence collapses"),
        "materials":              SectorImpactRule("bearish", 0.55, "Industrial demand and credit disappear together"),
        "industrials":            SectorImpactRule("bearish", 0.55, "Capex freezes; order books collapse"),
        "technology":             SectorImpactRule("bearish", 0.45, "Risk-off and funding markets seize"),
        "consumer_staples":       SectorImpactRule("bullish", 0.25, "Defensive inflows during risk-off"),
        "utilities":              SectorImpactRule("bullish", 0.25, "Defensive inflows during risk-off"),
        "healthcare":             SectorImpactRule("bullish", 0.20, "Defensive inflows during risk-off"),
    },
    "regulatory": {
        "technology":             SectorImpactRule("bearish", 0.45, "Antitrust enforcement and data regulation risk"),
        "financials":             SectorImpactRule("bearish", 0.35, "Compliance costs and activity restrictions"),
        "healthcare":             SectorImpactRule("mixed",   0.35, "Drug approvals and pricing rules cut both ways"),
        "energy":                 SectorImpactRule("mixed",   0.35, "Environmental rules vs subsidies for transition"),
        "consumer_discretionary": SectorImpactRule("mixed",   0.20, "Consumer protection rules; varies by sub-sector"),
    },
    "natural_disaster": {
        "insurance":              SectorImpactRule("bearish", 0.65, "Large claims and reserve drawdowns"),
        "agriculture":            SectorImpactRule("bearish", 0.65, "Crop and livestock losses"),
        "real_estate":            SectorImpactRule("bearish", 0.50, "Property destruction and insurance gaps"),
        "energy":                 SectorImpactRule("mixed",   0.35, "Infrastructure damage vs price spike opportunity"),
        "materials":              SectorImpactRule("bullish", 0.40, "Reconstruction demand for building materials"),
        "industrials":            SectorImpactRule("bullish", 0.30, "Rebuilding activity and equipment demand"),
    },
    "election_political": {
        "defense":                SectorImpactRule("mixed",   0.35, "Spending outlook depends on winner's platform"),
        "energy":                 SectorImpactRule("mixed",   0.40, "Policy on fossil fuels and renewables may reverse"),
        "healthcare":             SectorImpactRule("mixed",   0.40, "Pricing reform and coverage rules are contested"),
        "financials":             SectorImpactRule("mixed",   0.30, "Regulatory stance uncertain until platform clear"),
        "technology":             SectorImpactRule("mixed",   0.30, "Antitrust and data policy under new administration"),
    },
}

# ---------------------------------------------------------------------------
# Strength modifiers — words in the description that scale sector strengths
# Applied uniformly across all sectors in the result.
# ---------------------------------------------------------------------------
STRENGTH_MODIFIERS: dict[str, float] = {
    "unprecedented": 1.40,
    "catastrophic":  1.40,
    "massive":       1.30,
    "severe":        1.30,
    "major":         1.20,
    "significant":   1.15,
    "aggressive":    1.15,
    "sharp":         1.10,
    "moderate":      0.85,
    "limited":       0.70,
    "minor":         0.65,
    "slight":        0.60,
    "small":         0.60,
    "modest":        0.65,
}

# Confidence threshold below which `low_confidence` is flagged
LOW_CONFIDENCE_THRESHOLD = 0.40

# Minimum keyword matches required to classify (below this → "unknown")
MIN_MATCHES_TO_CLASSIFY = 1
