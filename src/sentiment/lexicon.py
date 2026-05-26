"""
Explicit keyword lexicon for financial news sentiment scoring.

KNOWN LIMITATIONS — read before extending this file:

  1. All weights are hand-assigned. There is no regression against actual
     price movements and no calibration against a labelled dataset.
     "beats estimates → +0.80" is calibrated intuition, not a measured signal.

  2. Terms absent from this file score as neutral (0.0). Any novel jargon,
     non-English text, or domain-specific vocabulary is silently neutral —
     not missing, not low-confidence: just invisible.

  3. Polarity is context-free. The same word scores identically whether it
     appears in a fact, a forward-looking prediction, or an analyst denial.

  4. Ambiguous single-word terms are included with conservative weights.
     "acquisition" → +0.10, "restructuring" → -0.20. These are weak signals
     because the true polarity depends on context this module cannot read.

Adding new terms: match the sign convention (-1.0 bearish, +1.0 bullish),
keep weights proportional to historical severity, and prefer phrases over
single words wherever both would apply.
"""

# ---------------------------------------------------------------------------
# Phrases  (matched before individual words; longer phrases have priority)
# Key: lowercase, spaces only — the tokeniser strips all punctuation.
# ---------------------------------------------------------------------------
PHRASES: dict[str, float] = {
    # ── Earnings / guidance ────────────────────────────────────────────────
    "beats estimates":            +0.80,
    "beat estimates":             +0.80,
    "beats expectations":         +0.80,
    "beat expectations":          +0.80,
    "exceeds estimates":          +0.75,
    "exceeded estimates":         +0.75,
    "exceeds expectations":       +0.75,
    "misses estimates":           -0.80,
    "missed estimates":           -0.80,
    "misses expectations":        -0.80,
    "missed expectations":        -0.80,
    "below expectations":         -0.70,
    "profit warning":             -0.80,
    "revenue miss":               -0.70,
    "earnings miss":              -0.75,
    "raised guidance":            +0.65,
    "raises guidance":            +0.65,
    "lowered guidance":           -0.65,
    "lowers guidance":            -0.65,
    "raised outlook":             +0.60,
    "lowered outlook":            -0.60,
    "strong results":             +0.60,
    "strong earnings":            +0.65,
    "disappointing results":      -0.70,
    "disappointing earnings":     -0.70,

    # ── Records — both directions (fixes the "record losses" failure case) ─
    "record revenue":             +0.70,
    "record earnings":            +0.70,
    "record profit":              +0.70,
    "record sales":               +0.65,
    "record losses":              -0.70,  # must appear before single "record"
    "record loss":                -0.70,
    "record writedown":           -0.65,

    # ── Highs / lows ───────────────────────────────────────────────────────
    "all time high":              +0.60,
    "all time low":               -0.60,
    "52 week high":               +0.45,
    "52 week low":                -0.45,
    "multi year high":            +0.50,
    "multi year low":             -0.50,

    # ── Dividends / capital returns ────────────────────────────────────────
    "dividend increase":          +0.50,
    "dividend raised":            +0.50,
    "dividend cut":               -0.70,
    "dividend suspended":         -0.75,
    "dividend eliminated":        -0.80,
    "share buyback":              +0.40,
    "stock buyback":              +0.40,
    "stock repurchase":           +0.35,

    # ── Distress / solvency ────────────────────────────────────────────────
    "bankruptcy filing":          -1.00,
    "files for bankruptcy":       -1.00,
    "chapter 11":                 -0.90,
    "going concern":              -0.85,
    "liquidity crisis":           -0.80,
    "debt default":               -0.90,
    "covenant breach":            -0.75,
    "credit downgrade":           -0.65,

    # ── Fraud / legal / regulatory ─────────────────────────────────────────
    "accounting fraud":           -0.90,
    "accounting irregularities":  -0.85,
    "sec investigation":          -0.75,
    "sec charges":                -0.80,
    "class action":               -0.55,
    "antitrust probe":            -0.55,
    "product recall":             -0.60,
    "data breach":                -0.60,
    "criminal charges":           -0.80,

    # ── Management ────────────────────────────────────────────────────────
    "ceo resigns":                -0.40,
    "ceo fired":                  -0.50,
    "cfo resigns":                -0.35,
    "management change":          -0.15,

    # ── Workforce ──────────────────────────────────────────────────────────
    "mass layoffs":               -0.60,
    "workforce reduction":        -0.50,
    "job cuts":                   -0.45,
    "hiring freeze":              -0.35,

    # ── Analyst / ratings ──────────────────────────────────────────────────
    "upgraded to buy":            +0.70,
    "initiated buy":              +0.60,
    "downgraded to sell":         -0.70,
    "price target raised":        +0.50,
    "price target lowered":       -0.50,

    # ── Regulatory / approval ──────────────────────────────────────────────
    "fda approval":               +0.80,
    "fda approved":               +0.80,
    "regulatory approval":        +0.70,
    "regulatory rejection":       -0.75,
    "fda rejection":              -0.80,

    # ── Margin / cash ──────────────────────────────────────────────────────
    "margin expansion":           +0.50,
    "margin compression":         -0.50,
    "cash flow positive":         +0.55,
    "supply chain disruption":    -0.45,
    "higher than expected costs": -0.50,
    "cost overruns":              -0.45,
}

# ---------------------------------------------------------------------------
# Single-word terms  (matched after phrases; consume unclaimed tokens only)
# ---------------------------------------------------------------------------
TERMS: dict[str, float] = {
    # Bullish
    "profit":           +0.30,
    "profitable":       +0.40,
    "profitability":    +0.40,
    "growth":           +0.25,
    "beats":            +0.50,
    "beat":             +0.45,
    "exceeds":          +0.40,
    "exceeded":         +0.40,
    "surpasses":        +0.50,
    "surpassed":        +0.45,
    "upgrade":          +0.40,
    "upgraded":         +0.40,
    "outperform":       +0.50,
    "outperforms":      +0.50,
    "outperformed":     +0.45,
    "approval":         +0.45,
    "approved":         +0.45,
    "bullish":          +0.45,
    "rally":            +0.35,
    "rallies":          +0.35,
    "buyback":          +0.35,
    "repurchase":       +0.30,
    "recovery":         +0.35,
    "recovering":       +0.30,
    "rebound":          +0.35,
    "resilient":        +0.30,
    "breakthrough":     +0.40,
    "milestone":        +0.25,
    "dividend":         +0.15,
    "partnership":      +0.20,
    "acquisition":      +0.10,   # ambiguous — could be overpayment
    "merger":           +0.10,   # ambiguous

    # Bearish
    "loss":             -0.40,
    "losses":           -0.40,
    "decline":          -0.35,
    "declines":         -0.35,
    "declined":         -0.35,
    "fell":             -0.30,
    "falls":            -0.30,
    "missed":           -0.50,
    "misses":           -0.50,
    "miss":             -0.45,
    "warning":          -0.45,
    "bankruptcy":       -0.90,
    "bankrupt":         -0.90,
    "lawsuit":          -0.40,
    "litigation":       -0.35,
    "fraud":            -0.75,
    "scandal":          -0.65,
    "layoffs":          -0.50,
    "layoff":           -0.50,
    "downgrade":        -0.50,
    "downgraded":       -0.50,
    "bearish":          -0.45,
    "crash":            -0.70,
    "crashed":          -0.70,
    "plunges":          -0.65,
    "plunged":          -0.60,
    "plummets":         -0.65,
    "halted":           -0.50,
    "suspended":        -0.35,
    "default":          -0.75,
    "investigation":    -0.50,
    "probe":            -0.40,
    "recall":           -0.55,
    "fine":             -0.30,
    "fined":            -0.40,
    "penalty":          -0.35,
    "penalties":        -0.35,
    "struggling":       -0.40,
    "disappointing":    -0.55,
    "disappoints":      -0.55,
    "concerns":         -0.25,
    "headwinds":        -0.30,
    "downturn":         -0.40,
    "recession":        -0.50,
    "slowdown":         -0.35,
    "writedown":        -0.60,
    "writeoff":         -0.55,
    "impairment":       -0.55,
    "dilution":         -0.40,
    "dilutive":         -0.45,
    "restructuring":    -0.20,   # ambiguous: turnaround or distress
    "challenging":      -0.25,
    "uncertainty":      -0.25,
    "volatility":       -0.15,
}

# ---------------------------------------------------------------------------
# Intensity modifiers  (multiply adjacent term weight; looked up within
# INTENSITY_WINDOW tokens *before* the matched term)
# ---------------------------------------------------------------------------
INTENSITY_MODIFIERS: dict[str, float] = {
    "significantly":    1.50,
    "substantially":    1.50,
    "sharply":          1.40,
    "massively":        1.50,
    "dramatically":     1.50,
    "unexpectedly":     1.30,
    "severely":         1.40,
    "steeply":          1.30,
    "slightly":         0.50,
    "modestly":         0.50,
    "marginally":       0.40,
    "narrowly":         0.50,
    "somewhat":         0.60,
    "mildly":           0.50,
}

# ---------------------------------------------------------------------------
# Negation words  (flip sign of next matched term within NEGATION_WINDOW)
# ---------------------------------------------------------------------------
NEGATION_WORDS: frozenset[str] = frozenset({
    "not", "no", "never", "without", "avoids", "averted",
    "prevents", "reversed", "denies", "denying", "rejects",
    "rejected", "dismisses", "dismissed", "rebuffs", "rebuffed",
})
