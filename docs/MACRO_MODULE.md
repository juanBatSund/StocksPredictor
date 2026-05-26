# Macro Event Tagging Module

## What it does

Takes a free-text macro event description (and optional supporting headlines) and asks:
**"What type of macro event is this, which sectors does it affect, in which direction, and how strongly?"**

It answers by matching the text against a curated rule table: no machine learning, no embeddings, no probabilistic models. Every output — the category, each sector impact, the confidence score, the strength modifier — traces directly to a row in `rules.py`.

The module produces:
- An **event category** (geopolitical conflict, monetary policy tightening, inflation, etc.)
- A **secondary category** when the description matches two distinct macro types
- A **list of affected sectors** with direction (bullish/bearish/mixed) and strength (0.0–1.0)
- A **confidence score** based on keyword match count, category specificity, and headline corroboration
- A complete **audit trail**: which keywords fired, what each category scored, why sectors were mapped

This module does **not** fetch news. It receives `(description: str, headlines: list[str])` and returns a `MacroTag`.

---

## Files

```
src/
└── macro/
    ├── rules.py    — CATEGORY_KEYWORDS, SECTOR_IMPACTS, STRENGTH_MODIFIERS, thresholds
    └── tagger.py   — SectorTag, MacroTag, tag()

tests/
└── test_macro/
    └── test_tagger.py   — 60 tests
```

Note: `src/data/macro.py` is a separate module — a static curated event store. The new tagger
classifies *new* descriptions; `data/macro.py` stores *historical* events. They are complementary.

---

## Quant / macro analyst critique — read this first

This section is written by a sceptical senior macro analyst and quant. If you are tempted to
mechanically apply these tags to trading decisions, read these points first.

---

### Weaknesses

**The sector impact table is the model, and it was built by hand.**
`"geopolitical_conflict → defense: bullish 0.80"` is a calibrated judgement, not a regression
coefficient derived from event studies. The actual defence stock alpha from a surprise invasion
depends on: which country is invaded, the duration of the conflict, existing positioning, and
whether the market already priced the risk. The rule table knows none of these things.

**Category boundaries are artificial.**
Real macro events are rarely single-category. The 2022 Russia-Ukraine invasion was simultaneously
geopolitical conflict, an energy shock, an inflation accelerant, and a trade disruption. The tagger
picks one primary and one secondary. The remaining categories are suppressed even though they may
matter just as much for specific sectors.

**Direction is unconditional.**
`"energy: bullish"` during a geopolitical conflict assumes a long energy position. A short-seller
in energy futures sees the opposite sign. A company with energy as an *input cost* sees the
bearish side of the same event. The tagger has no concept of portfolio position or cost-vs-revenue exposure.

**"Mixed" is honest but not actionable.**
Nine of the twelve categories produce at least one "mixed" sector. "Mixed" correctly signals that
the direction is regime-dependent, but the decision engine cannot act on it without further analysis.
The tagger exposes this limitation — it does not hide it behind a false number.

**Confidence is a proxy, not a probability.**
High confidence means the description contained many category keywords with few competing signals.
It does not mean the category assignment is correct. A description engineered to contain many
geopolitical keywords would score 1.0 confidence even if the underlying event is economic.

**Keyword matching is substring-based with no semantic understanding.**
`"regulation"` in a description about financial regulation matches the `regulatory` category.
`"regulation"` in the phrase `"Fed's new deregulation push"` also matches `regulatory` — but the
event direction is opposite (deregulation is typically bullish for the regulated sector, whereas
the `regulatory` category defaults to bearish). Context reversal is invisible to the tagger.

**The keyword list is closed.**
Novel event types — a central bank digital currency launch, a large-scale AI-driven market
disruption, sovereign debt restructuring in an emerging market — will not match any category and
will return `category="unknown"`. That is the correct behaviour, but it silently says nothing
when it should say "this is a new event type that needs a new rule."

**Temporal decay is absent.**
A geopolitical event from two years ago applies the same sector impact strengths as one from
yesterday. The existing `data/macro.py` module has the same limitation: events accumulate with
no decay. The decision engine must apply its own recency weighting.

---

### Hidden assumptions

**Assumes English.**
Non-English event descriptions produce zero keyword matches and return `category="unknown"`.
A Swedish-language headline about Riksbank rate policy would not trigger `monetary_policy_tightening`.

**Assumes the causal chain is stable.**
`"inflation → consumer discretionary: bearish"` assumes inflation erodes real incomes in
the standard way. In a supply-side inflation driven by energy, luxury goods companies with
pricing power may actually outperform while discount retailers suffer more. The rule table
cannot distinguish supply-side from demand-side inflation.

**Assumes macro events affect sectors uniformly within the category.**
`"defense: bullish"` during geopolitical conflict applies to all defence companies. In reality,
missile systems manufacturers benefit differently from logistics contractors, which benefit
differently from cybersecurity firms. Sub-sector resolution is outside the scope of this module.

**Assumes sector labels match portfolio holdings.**
The tagger outputs sector names like `"technology"` and `"real_estate"`. Whether a specific
ticker belongs to that sector — and how much — is not checked here. The decision engine must
map sectors to holdings.

---

### Overengineering concerns

**The strength modifier is marginal.**
Applying `"severe" → 1.30×` to all sectors when the word "severe" appears in the description
adds complexity. In practice, the word "severe" rarely appears in structured event descriptions
and the multiplier rarely fires. Its value is low relative to its implementation surface.

**The secondary category adds merging complexity.**
When primary and secondary categories both affect the same sector in opposite directions,
the module produces `direction="mixed"` and `strength = |diff|`. This is logically correct but
produces many "mixed" results, reducing the actionability of the secondary category signal.

---

### Potential failure points

| Scenario | What happens | Why it fails |
|---|---|---|
| `"Fed's deregulation push for banks"` | `regulatory` category, bearish | "regulation" substring matches even though the event is deregulatory (bullish) |
| `"Central bank digital currency launch"` | `unknown` | No CBDC keywords in rule table |
| `"War on inflation"` | `geopolitical_conflict` **and** `inflation` | "War" matches geopolitical; "inflation" matches inflation — may produce wrong primary |
| `"Stagflation"` | `recession_risk` (single word trigger) | Stagflation is simultaneously inflation + recession; only one wins |
| Non-English description | `unknown` | No multilingual keyword lists |
| Sarcastic / ironic text | Wrong category | Negation not handled (no negation layer as in the sentiment module) |

---

### Benchmarking limitations

1. **No ground truth.** There is no labelled corpus of `(event_description → category)` pairs
   to measure classification accuracy. Whether the tagger classifies 80% of events correctly
   or 50% is unknown.

2. **No return-impact validation.** The sector impact strengths (e.g., `defense: 0.80`) have
   not been validated against actual sector returns following macro events of each type. They
   are educated guesses.

3. **No random baseline comparison.** `evaluation.md` requires benchmarking against a random
   baseline. A random classifier assigns a random category. If the tagger barely outperforms
   random across a historical event set, the keyword lists are adding no meaningful signal
   over chance.

---

### Improvements applied after critique

| Problem identified | Fix applied |
|---|---|
| Single-category collapse for compound events | Added `secondary_category` with full sector merging; conflicting directions become `"mixed"` |
| No way to handle unknown events | `category="unknown"` returned when keyword matches = 0; explicitly not forced into closest bucket |
| Confidence not explained | `confidence_note` in `notes[1]` breaks down the formula components and explicitly states "not a probability" |
| Severity ignored | `STRENGTH_MODIFIERS` applies a global multiplier from words like "massive", "severe", "minor" |
| All sectors equally affected | Sorted by strength descending so strongest impacts are visible first |
| No audit trail | `triggered_rules`, `category_scores`, `competing_categories`, `strength_modifier` all exposed on `MacroTag` |
| "regulation" matches deregulation | Documented as known failure; cannot be fixed without semantic understanding |
| Temporal decay absent | Documented as limitation; left to decision engine to apply recency weighting |

---

## Categories

| Category key | Label | Typical trigger |
|---|---|---|
| `geopolitical_conflict` | Geopolitical Conflict | Wars, invasions, military actions, terrorism |
| `monetary_policy_tightening` | Monetary Policy Tightening | Rate hikes, QT, hawkish central banks |
| `monetary_policy_easing` | Monetary Policy Easing | Rate cuts, QE, dovish central banks |
| `inflation` | Inflation / Price Pressure | CPI/PPI releases, price surge reports |
| `recession_risk` | Recession Risk | GDP contraction, unemployment, credit tightening |
| `trade_policy` | Trade Policy | Tariffs, trade wars, export controls |
| `energy_shock` | Energy Shock | OPEC cuts, oil price spikes, gas crises |
| `pandemic` | Pandemic / Health Crisis | Disease outbreaks, lockdowns |
| `financial_crisis` | Financial Crisis | Bank failures, systemic risk, bailouts |
| `regulatory` | Regulatory / Policy Change | New laws, antitrust actions, carbon taxes |
| `natural_disaster` | Natural Disaster | Earthquakes, hurricanes, floods |
| `election_political` | Election / Political Transition | Elections, government changes |
| `unknown` | Unknown / Unclassified | No keyword matches — extend the rule table |

---

## Sector impact table (summary)

All sector impacts are ordered by strength within each category, strongest first. Direction is
unconditional (assumes long position). Strengths are **empirically uncalibrated**.

### Geopolitical Conflict
| Sector | Direction | Strength |
|---|---|---|
| defense | bullish | 0.80 |
| energy | bullish | 0.60 |
| travel | bearish | 0.60 |
| consumer_discretionary | bearish | 0.40 |
| agriculture | mixed | 0.40 |
| technology | bearish | 0.30 |
| financials | bearish | 0.30 |
| materials | bullish | 0.30 |

### Monetary Policy Tightening
| Sector | Direction | Strength |
|---|---|---|
| real_estate | bearish | 0.70 |
| financials | bullish | 0.60 |
| utilities | bearish | 0.60 |
| technology | bearish | 0.55 |
| consumer_discretionary | bearish | 0.40 |

### Energy Shock
| Sector | Direction | Strength |
|---|---|---|
| energy | bullish | 0.85 |
| consumer_discretionary | bearish | 0.65 |
| industrials | bearish | 0.55 |
| consumer_staples | bearish | 0.40 |
| materials | bullish | 0.40 |
| utilities | mixed | 0.40 |
| agriculture | bearish | 0.35 |

*(see `rules.py` for all twelve categories in full)*

---

## Inputs

```python
description: str          # Short event description
headlines:   list[str]    # Optional supporting headlines (confidence boost only)
```

The description and headlines are processed identically: tokenised to lowercase, punctuation
stripped, and then scanned for keyword phrases. Headlines do not override the category derived
from the description — they only add a corroboration bonus to confidence.

---

## Output: `MacroTag`

| Field | Type | Description |
|---|---|---|
| `description` | `str` | Original input text, unchanged |
| `category` | `str` | Primary category key (or `"unknown"`) |
| `category_label` | `str` | Human-readable label |
| `secondary_category` | `str \| None` | Second-ranked category with ≥1 match |
| `secondary_label` | `str \| None` | Human-readable secondary label |
| `affected_sectors` | `list[SectorTag]` | Merged from primary + secondary; strength-sorted |
| `confidence` | `float` | 0.0–1.0; higher = stronger keyword evidence and lower ambiguity |
| `low_confidence` | `bool` | True when confidence < 0.40 — treat with caution |
| `triggered_rules` | `list[str]` | Keywords that matched the primary category |
| `competing_categories` | `list[str]` | Other categories with ≥1 match (beyond secondary) |
| `category_scores` | `dict[str, int]` | Full audit: keyword match count per category |
| `strength_modifier` | `float` | Global strength multiplier from intensity words |
| `notes` | `list[str]` | `[category_note, confidence_note, sector_note]` |

### `SectorTag`

| Field | Type | Description |
|---|---|---|
| `sector` | `str` | e.g. `"defense"`, `"technology"`, `"real_estate"` |
| `direction` | `str` | `"bullish"` / `"bearish"` / `"mixed"` |
| `strength` | `float` | 0.0–1.0; clamped after strength modifier applied |
| `reasoning` | `str` | One-line causal explanation |

---

## Classification pipeline

### Step 1 — Tokenise

```python
re.sub(r"[^\w\s]", " ", text.lower()).split()
```

All punctuation stripped. `"50bps (basis points)"` → `["50bps", "basis", "points"]`.

### Step 2 — Score every category

For each of the 12 categories, count how many keywords from `CATEGORY_KEYWORDS[cat]` appear
as substrings in the joined token string. This handles multi-word phrases automatically:
`"rate hike"` is found in `"rate hike cycle"` without needing a separate phrase-matching engine.

### Step 3 — Rank and select

Categories are ranked by match count, descending. The category with the most matches is the
primary. The next category with ≥1 match is the secondary. All others with ≥1 match are
`competing_categories`.

If the primary category scored 0 matches → `category = "unknown"`.

### Step 4 — Compute confidence

```
keyword_score   = min(1.0, primary_count / 3.0)
specificity     = max(0.50, 1.0 - (secondary_count / primary_count) × 0.40)
competing_pen   = min(0.30, competing_count × 0.08)
headline_bonus  = hl_corroboration × 0.20  (only when headlines provided)

confidence = keyword_score × specificity − competing_pen + headline_bonus
           = clamped to [0.0, 1.0]
```

This is a proxy, not a calibrated probability. It measures: how strongly does the text point
to one category vs alternatives?

### Step 5 — Strength modifier

The tagger scans for intensity words (`"massive"`, `"severe"`, `"minor"`, etc.) and applies
the most extreme multiplier found to all sector impact strengths. The most extreme modifier
wins (furthest from 1.0).

### Step 6 — Build sector list

1. Start with all sectors from the primary category impact table.
2. Add sectors from the secondary category impact table.
3. For sectors appearing in both:
   - Same direction → keep direction, take max strength.
   - Opposite directions → `"mixed"`, strength = `|primary_strength − secondary_strength|`.
4. Apply strength modifier to all strengths; clamp to [0.0, 1.0].
5. Sort descending by strength.

### Step 7 — Log and return

Inputs and results are logged as structured JSON via `src/logging/logger.py`.

---

## Confidence formula — component breakdown

| Component | Formula | Effect |
|---|---|---|
| keyword_score | `min(1.0, primary_matches / 3)` | Saturates at 3+ matches |
| specificity | `max(0.50, 1 − (secondary/primary) × 0.40)` | Penalises near-tie with secondary |
| competing_penalty | `min(0.30, n_competing × 0.08)` | Each competing category reduces score |
| headline_bonus | `corroboration × 0.20` | Only applies when headlines are passed |

A description with 5 primary matches, 0 secondary, no competing categories, and 100% headline
corroboration → `confidence = 1.0 × 1.0 − 0 + 0.20 = 1.0` (clamped).

A description with 1 match, 1 competing category → `confidence = 0.33 × 1.0 − 0.08 = 0.25`
→ `low_confidence = True`.

---

## Examples

### Example 1: Clean geopolitical event

```python
from src.macro.tagger import tag

result = tag(
    "Russia invades Ukraine with massive military offensive",
    headlines=[
        "Russian troops cross Ukrainian border",
        "NATO activates defence protocols",
    ]
)

result.category           # "geopolitical_conflict"
result.category_label     # "Geopolitical Conflict"
result.confidence         # 0.89  (5 keywords + 2/2 headlines corroborate)
result.low_confidence     # False
result.strength_modifier  # 1.30  ("massive" → 1.30×)
result.triggered_rules    # ["invasion", "military", "troops"]

# Sectors (strength-sorted, with modifier applied)
for s in result.affected_sectors:
    print(f"{s.sector:30s} {s.direction:8s} {s.strength:.2f}  {s.reasoning}")

# defense                        bullish  1.00  Increased defence spending and procurement
# energy                         bullish  0.78  Supply disruption risk raises commodity prices
# travel                         bearish  0.78  Route closures and demand destruction
# consumer_discretionary         bearish  0.52  Consumer uncertainty and risk aversion
# ...

result.notes[0]  # "Category: Geopolitical Conflict — 3 keyword(s) matched"
result.notes[1]  # "Confidence: 0.89 | 2/2 headline(s) corroborate"
result.notes[2]  # "8 sector(s) affected | strength modifier 1.30× | strengths are empirically uncalibrated"
```

---

### Example 2: Multi-category event — stagflationary rate hike

```python
result = tag("Fed rate hike cycle as recession risk deepens with GDP contraction")

result.category            # "recession_risk"    (2 matches: recession, gdp contraction)
result.secondary_category  # "monetary_policy_tightening"  (1 match: rate hike)

# Technology sector: tightening says bearish 0.55, recession says bearish 0.50 → bearish max(0.55, 0.50) = 0.55
# Consumer staples: tightening says bearish 0.20, recession says bullish 0.35 → mixed |0.35 − 0.20| = 0.15
```

---

### Example 3: Unknown event type

```python
result = tag("Company launches new subscription pricing model")

result.category       # "unknown"
result.confidence     # 0.0
result.low_confidence # True
result.affected_sectors  # []
result.notes[0]       # "Category: Unknown — no keywords matched any category"
result.notes[2]       # "0 sectors affected — extend CATEGORY_KEYWORDS to handle this event type"
```

---

### Example 4: Energy shock with corroborating headlines

```python
result = tag(
    "OPEC cuts oil supply; crude oil prices surge to multi-year high",
    headlines=[
        "Brent crude rises 8% on OPEC decision",
        "Energy stocks rally as oil prices jump",
        "Airlines warn of fuel cost impact",
    ]
)

result.category       # "energy_shock"
result.confidence     # ~0.93  (4 description matches + 3/3 headlines)
# energy: bullish 0.85 (direct revenue uplift)
# consumer_discretionary: bearish 0.65 (fuel costs)
# industrials: bearish 0.55
```

---

## Using the tagger in code

```python
from src.macro.tagger import tag

result = tag(
    "Fed begins aggressive rate hike cycle",
    headlines=["Fed hikes by 75 basis points, most since 1994"],
)

print(result.category)          # "monetary_policy_tightening"
print(result.confidence)        # 0.88
print(result.low_confidence)    # False
print(result.triggered_rules)   # ["rate hike", "hawkish"]

for sector in result.affected_sectors:
    print(f"{sector.sector}: {sector.direction} {sector.strength:.2f}")
    print(f"  → {sector.reasoning}")

# Full audit trail
print(result.category_scores)      # {'monetary_policy_tightening': 2, 'recession_risk': 0, ...}
print(result.competing_categories) # []
print(result.strength_modifier)    # 1.15  ("aggressive")
print(result.notes)                # [category_note, confidence_note, sector_note]
```

---

## How to run the tests

```bash
python3 -m pytest tests/test_macro/ -v
```

**Expected result: 60 passed**

No test makes a network call. All inputs are constructed inline.

The 60 tests are organised into nine classes:

| Class | Tests | What it covers |
|---|---|---|
| `TestTokenize` | 3 | Lowercase, punctuation stripping, empty input |
| `TestCountKeywordMatches` | 4 | Single words, phrases, zero matches, multiple matches |
| `TestCategoryClassification` | 10 | The four existing `data/macro.py` events + six other event types |
| `TestUnknownClassification` | 5 | Generic text → unknown; zero confidence; empty sectors |
| `TestSectorImpacts` | 8 | Direction correctness, strength sorting, sector presence, bounded strengths |
| `TestConfidence` | 6 | Single vs multiple matches; competition penalty; headline bonus; flag consistency |
| `TestComputeConfidence` | 5 | Direct formula unit tests |
| `TestStrengthModifier` | 4 | No modifier, amplifier, dampener, applied to output |
| `TestMultiCategory` | 4 | Secondary category present; sector count; direction merging |
| `TestAuditTrail` | 6 | Triggered rules, category scores, notes, determinism, description preservation |
| `TestMergeDirection` | 5 | All direction combination pairs |

---

## Design rules

**Category keywords are listed longest-first within each category.**
`"rate hike"` appears before `"tightening"` so the more specific phrase matches before its
component words can be matched independently. This prevents partial-match noise — the same
principle as the sentiment module's phrase-before-word ordering.

**Unknown is first-class, not a fallback.**
When no keywords match, the module returns `category="unknown"` explicitly. It does not fall
back to the closest category or guess. The correct response to insufficient evidence is
to say so, not to fabricate a category assignment.

**Secondary category is always independent.**
The secondary category is the second-ranked match from the same keyword scan. It is not
derived from the primary. This means both can fire even when they describe the same event
from different angles (e.g., an oil supply shock is both `energy_shock` and `geopolitical_conflict`
if the description contains keywords from both).

**Sector strengths are not normalised across categories.**
`"energy: bullish 0.80"` in geopolitical conflict and `"energy: bullish 0.85"` in energy shock
are independently calibrated. They are not rescaled to be comparable across categories, because
a 0.80 in one event type does not mean the same as a 0.80 in another.

**Deterministic.**
No randomness, no timestamps, no external calls. Same `(description, headlines)` always
produces the same `MacroTag`.

---

## What is not in this module

| Concern | Where it lives |
|---|---|
| Fetching news from external APIs | `src/data/` (not yet implemented) |
| Historical curated event store | `src/data/macro.py` |
| Temporal decay of past events | `src/decision/` (not yet implemented) |
| Sub-sector resolution (e.g., missile vs cyber within defense) | Not implemented |
| Cross-sector portfolio impact (net position weighting) | Not implemented |
| Sector-to-ticker mapping | Not implemented |
| Sentiment scoring of the same headlines | `src/sentiment/scorer.py` |
| Final BUY / WATCH / AVOID decision | `src/decision/` (not yet implemented) |
| Lexicon validation against historical event-return data | Not implemented — most critical gap |
