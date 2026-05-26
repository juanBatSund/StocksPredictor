# Decision Engine Module

## What it does

Takes the pre-computed results from all upstream modules and asks:
**"Should we BUY, WATCH, or AVOID this stock — and how confident are we?"**

It answers through an explicit rule chain: hard gates first, soft gates second, macro context last. Every rule that fired is recorded. Every rule that failed is also recorded. The final decision is the mechanical consequence of those recorded evaluations — not the output of any opaque scoring formula.

The module produces:
- A **decision**: `BUY` / `WATCH` / `AVOID`
- A **confidence score** (0.0–1.0) broken down into four explicit components
- A complete **gate evaluation** (pass/fail/unknown for each criterion)
- **Contributing factors** and **rejected factors** (which signals pushed which way)
- **Uncertainty flags** (explicit reasons to distrust the decision)
- A step-by-step **reasoning trace** (ordered list of every decision step)

This module does **not** fetch data, compute scores, or classify events. It receives `FundamentalResult`, `SentimentResult`, and `MacroTag` and returns a `DecisionResult`.

---

## Files

```
src/
└── decision/
    └── engine.py   — Gate, Factor, ConfidenceBreakdown, DecisionResult, decide()

tests/
└── test_decision/
    └── test_engine.py   — 92 tests
```

---

## Multi-perspective critique — read this first

Three reviewers. None of them is satisfied.

---

### Sceptical quant

**The component weights (40/25/20/15) are not validated.**
Quality × 40%, Growth × 25%, Dividend × 20%, Valuation × 15% come from `system.md` and have not been backtested. There is no evidence that this weighting outperforms an equal-weight alternative, a market-cap-weighted benchmark, or a random assignment. Until a backtest validates them, these are opinions masquerading as a model.

**The BUY threshold (score > 75) is arbitrary.**
The decision boundary is a round number with no statistical justification. If the distribution of fundamental scores peaks at 68, a threshold of 75 is extremely selective. If it peaks at 80, the threshold is nearly useless. The right threshold should be derived from the empirical distribution of scores against forward returns — and we have no such calibration.

**Missing data scores 0, creating a systematic bias against data-sparse stocks.**
A company with no dividend (0 yield → 0 dividend score) and no 5Y P/E average (falls back to market proxy) is penalised in the composite score even if it is fundamentally excellent. Growth companies and international stocks with sparse Yahoo Finance coverage are systematically underscored. This is a design choice — but it is not neutral.

**The sentiment gate forces a specific investment philosophy.**
Requiring `sentiment = negative but improving` for BUY is a contrarian filter. It is correct for value investors buying temporarily out-of-favour stocks. It is wrong for momentum investors, growth investors, and any strategy that buys when sentiment is already positive. This gate bakes in a philosophical assumption that is never surfaced as such in the output.

**Confidence is a proxy, not a probability.**
A confidence of 0.80 does not mean an 80% probability of the BUY decision being correct. It means the signals are internally consistent, the data is reasonably complete, and the soft signals agree with the decision. None of these correlates with actual return outcomes without a backtest.

**The decision is binary, not sized.**
BUY recommends buying. It says nothing about how much. A stock scoring 76 with confidence 0.45 gets the same BUY signal as a stock scoring 98 with confidence 0.95. Position sizing — the most important risk management lever — is entirely outside this module.

---

### Macro analyst

**Macro only downgrades, never upgrades.**
The design explicitly prevents macro from upgrading WATCH→BUY. This is conservative and defensible, but it means a fundamentally weak stock with a strong macro tailwind cannot be surfaced by this engine. War starting and defense stocks being cheap might be the clearest investable thesis available, but if the fundamental score is 62 (WATCH territory), the engine will not produce a BUY.

**Macro adjustment fires on current event data, not forward expectations.**
The macro tagger reads today's event description. Markets price forward 6–12 months. "Geopolitical conflict bearish for consumer discretionary" is true today — it may be fully priced in and irrelevant to forward returns in 3 months. The engine has no way to determine whether the macro event is already reflected in prices.

**Sector labels are uncontrolled.**
The `sector` parameter is a free string passed by the caller. Nothing verifies that a company categorised as `"technology"` by Yahoo Finance matches the `"technology"` key in the macro impact table. A mismatch silently produces no macro adjustment.

**All active macro events have equal weight.**
The existing `data/macro.py` accumulates all historical events. A Ukraine invasion from 2022 and a new sanctions round from last week both affect the `energy` sector polarity equally. The decision engine receives a single macro tag — the most recent event — but the sector polarity from `data/macro.py` is cumulative with no decay. This inconsistency is inherited from the upstream data module.

**Macro impact applies uniformly to all stocks in a sector.**
`"geopolitical_conflict → defense: bullish 0.80"` is applied equally to a large defense prime contractor and a small maintenance supplier. The underlying exposure is completely different. Sub-sector resolution is not available.

---

### Risk manager

**No position sizing or concentration limits.**
BUY is binary. Ten BUY signals across ten correlated stocks in one sector would be indistinguishable from ten BUY signals across ten uncorrelated sectors. The engine has no portfolio view.

**No maximum drawdown assessment.**
The engine can recommend BUY on a stock that previously lost 70% of its value (a high P/E decline → now undervalued) without any awareness of the drawdown path that created the current undervaluation. "Cheap" is not the same as "safe."

**Uncertainty flags are advisory, not blocking.**
A decision can be BUY with five uncertainty flags. Nothing in the engine forces a downgrade when uncertainty is high. The caller must implement their own uncertainty threshold, and the engine provides no guidance on what threshold is appropriate.

**The macro downgrade threshold (0.60) is arbitrary.**
A sector impact strength of 0.60 triggers a downgrade; 0.59 does not. This is a hard cliff with no empirical basis. The threshold should be calibrated to the actual distribution of macro impact strengths and their correlation with adverse outcomes.

**No correlated event risk.**
A pandemic, a recession, and a financial crisis can all occur simultaneously (2020). The engine takes a single `MacroTag` as input. Multiple concurrent macro events, each bearish for different reasons, cannot be combined — the caller must decide which event to pass, introducing discretionary choice at the worst possible moment.

**No exit criteria.**
The engine recommends BUY. `system.md` defines exit as "after 1–2 years OR score drops below 60." The engine cannot evaluate this — it has no historical context and no position tracking. The BUY recommendation is for entry only.

---

## Improvements applied after critique

| Problem identified | Fix applied |
|---|---|
| Decision is opaque (no trace) | `reasoning_trace` records every step in order |
| No way to see which gates fired | `gates: list[Gate]` exposes all three gates with observed/required/passed |
| Confidence is a single number with no explanation | `ConfidenceBreakdown` exposes all four components with weights |
| Uncertainty is hidden | `uncertainty_flags: list[str]` explicitly names every reason to distrust the output |
| Contributing signals not separated from opposing | Separate `contributing_factors` and `rejected_factors` lists |
| Macro silently no-ops when sector is absent | Explicit uncertainty flag: "Macro: sector not specified" |
| Sentiment gate failure reason was opaque | Gate note field explains WHY it failed (positive sentiment / wrong direction / missing) |
| Soft signal confidence ignored in decision | `soft_signal_quality` component in confidence formula uses module-level confidence |

**Remaining hard limits — not fixable without more infrastructure:**

| Limitation | Why it remains |
|---|---|
| Weights (40/25/20/15) are unvalidated | Requires backtest against forward returns — no return data exists |
| Threshold (75) is arbitrary | Same: needs calibration against empirical score distribution |
| Confidence is not a probability | Would require a labelled historical dataset to calibrate |
| No position sizing | Out of scope for a classification module |
| Macro cannot upgrade decisions | Deliberate conservatism — macro signal quality is too uncertain to be a positive gate |

---

## Decision flow

```
FundamentalResult (required)
SentimentResult   (optional)
MacroTag          (optional)
sector            (optional — needed for macro impact lookup)
missing_fields    (optional — from StockData.missing_fields)
        │
        ▼
Step 1: Core score from fundamentals
  score = fundamental.total   (0–100, already weighted across quality/growth/dividend/valuation)

Step 2: Gate 1 — Fundamental score threshold
  PASS if score > 75  →  BUY candidate
  FAIL              →  WATCH or AVOID (from score range)

Step 3: Gate 2 — Valuation status
  PASS if valuation.status == "undervalued"
  FAIL              →  downgrade BUY candidate to WATCH

Step 4: Gate 3 — Sentiment (soft gate)
  PASS if sentiment.status == "negative" AND sentiment.trend > 0
  FAIL              →  downgrade BUY candidate to WATCH
  UNKNOWN           →  downgrade BUY candidate to WATCH (cannot confirm)

Step 5: Macro context (downgrade only)
  If sector_impact.direction == "bearish" AND strength ≥ 0.60:
    BUY → WATCH
  Bullish / mixed / strength < 0.60:
    no change to decision

Step 6: Confidence computation (four explicit components)

Step 7: Uncertainty flags, contributing and rejected factors

Step 8: Reasoning trace, notes, log, return DecisionResult
```

---

## Gate rules

### Gate 1: Fundamental score

| Score | Result |
|---|---|
| > 75 | PASS — BUY candidate |
| 60–75 | FAIL (score gate fails; base decision = WATCH) |
| < 60 | FAIL (score gate fails; base decision = AVOID) |

**Why > 75 (not ≥ 75):** The score must strictly exceed the threshold. A score of exactly 75.0 is WATCH, not BUY candidate. This matches the boundary semantics in `system.md`.

### Gate 2: Valuation status

| Status | Result |
|---|---|
| `undervalued` | PASS |
| `fair` | FAIL |
| `overvalued` | FAIL |
| `unknown` | FAIL + uncertainty flag |

The BUY thesis requires a stock to be trading below its historical norm. A fair or overvalued stock does not offer a margin of safety.

### Gate 3: Sentiment (soft gate)

| Condition | Result |
|---|---|
| `status == "negative"` AND `trend > 0` | PASS — contrarian entry signal |
| `status == "negative"` AND `trend ≤ 0` | FAIL — sentiment negative but worsening |
| `status == "positive"` | FAIL — upside may already be priced in |
| `status == "neutral"` | FAIL — no contrarian opportunity identified |
| No sentiment data | UNKNOWN — gate treated as failed; BUY → WATCH |

This gate encodes the investment philosophy from `system.md`: buy when market pessimism is present but beginning to recede. It is explicitly a contrarian filter, not a momentum filter.

### Macro context (not a gate — a conditional downgrade)

The macro check only fires when:
1. A `MacroTag` is provided.
2. A `sector` string is provided.
3. The stock's sector appears in the macro tag's impact table.
4. The sector impact is `"bearish"` with strength ≥ 0.60.

If all four conditions are met: `BUY → WATCH`.
The macro context **never** upgrades a decision.

---

## Confidence formula

```
confidence = (
    data_quality       × 0.30
  + valuation_certainty × 0.25
  + signal_agreement    × 0.30
  + soft_signal_quality × 0.15
)
```

Clamped to [0.0, 1.0].

### Component 1 — Data quality (30%)

```
data_quality = max(0.0, 1.0 − len(missing_fields) × 0.07)
```

Each missing fundamental field reduces confidence by 7%. 15 missing fields → 0.0. Rationale: scores on missing data (which produce 0.0) are less trustworthy than scores on present data.

### Component 2 — Valuation certainty (25%)

| Valuation status | Component score |
|---|---|
| `undervalued` | 1.0 |
| `fair` / `overvalued` | 0.5 |
| `unknown` | 0.0 |

Rationale: a clear pricing signal (undervalued or overvalued) is more informative than an unknown.

### Component 3 — Signal agreement (30%)

Measures whether soft signals (sentiment + macro) agree with the decision direction.

| Decision | Sentiment | Agreement |
|---|---|---|
| BUY | Negative + improving | 1.0 |
| BUY | Neutral | 0.5 |
| BUY | Other | 0.0 |
| AVOID | Positive | 0.8 |
| AVOID | Neutral | 0.5 |
| AVOID | Other | 0.2 |
| WATCH | Any | 0.5 |

| Decision | Macro sector | Agreement |
|---|---|---|
| BUY | Bullish | 1.0 |
| BUY | Mixed | 0.5 |
| BUY | Bearish | 0.0 |
| AVOID | Bearish | 1.0 |
| AVOID | Mixed | 0.5 |
| AVOID | Bullish | 0.0 |
| WATCH | Any | 0.5 |

`signal_agreement = (sentiment_agreement + macro_agreement) / 2`

### Component 4 — Soft signal quality (15%)

```
soft_signal_quality = (sentiment.confidence + macro.confidence) / 2
```

Uses the internal confidence values from the sentiment and macro modules themselves. Defaults to 0.5 when a module's output is not provided (uncertain, not zero).

---

## Outputs: `DecisionResult`

| Field | Type | Description |
|---|---|---|
| `ticker` | `str` | e.g. `"AAPL"` |
| `decision` | `str` | `"BUY"` / `"WATCH"` / `"AVOID"` |
| `score` | `float` | 0–100 fundamental composite |
| `quality_score` | `float` | Component sub-score |
| `growth_score` | `float` | Component sub-score |
| `dividend_score` | `float` | Component sub-score |
| `valuation_score` | `float` | Component sub-score |
| `valuation_status` | `str` | `"undervalued"` / `"fair"` / `"overvalued"` / `"unknown"` |
| `confidence` | `float` | 0.0–1.0 — proxy metric, not a probability |
| `confidence_breakdown` | `ConfidenceBreakdown` | Four explicit components |
| `gates` | `list[Gate]` | All three gate evaluations |
| `contributing_factors` | `list[Factor]` | Signals that supported the decision |
| `rejected_factors` | `list[Factor]` | Signals that opposed or failed |
| `uncertainty_flags` | `list[str]` | Named reasons to distrust this output |
| `sentiment_score` | `float \| None` | Raw sentiment score (-1 to +1) |
| `sentiment_status` | `str \| None` | `"positive"` / `"negative"` / `"neutral"` |
| `sentiment_trend` | `float \| None` | OLS slope of daily sentiment |
| `sentiment_confidence` | `float \| None` | Lexicon coverage confidence |
| `macro_category` | `str \| None` | e.g. `"monetary_policy_tightening"` |
| `macro_sector_direction` | `str \| None` | `"bullish"` / `"bearish"` / `"mixed"` |
| `macro_sector_strength` | `float \| None` | 0.0–1.0 impact strength |
| `macro_confidence` | `float \| None` | Macro tagger's own confidence |
| `reasoning_trace` | `list[str]` | Ordered steps: every decision that was made |
| `notes` | `list[str]` | `[decision_note, score_note, uncertainty_note]` |

---

## Examples

### Example 1: Clean BUY — all gates pass

```python
from src.decision.engine import decide
from src.fundamentals.scorer import score as fund_score
from src.sentiment.scorer import score as sent_score
from src.macro.tagger import tag as macro_tag
from datetime import date

# Already-computed module results (from upstream)
fundamental = fund_score("JNJ", fundamentals_obj, MARKETS["US"])
sentiment   = sent_score("JNJ", [(date(2024,1,1), "JNJ misses estimates"), (date(2024,1,8), "JNJ beats estimates strongly, raises guidance")])
macro       = macro_tag("Elevated inflation persists; Fed hike cycle underway")

result = decide("JNJ", fundamental, sector="healthcare", sentiment=sentiment, macro=macro)

result.decision       # "BUY"
result.score          # e.g. 78.3
result.confidence     # e.g. 0.74
result.valuation_status  # "undervalued"

# Gate evaluation
for gate in result.gates:
    status = "✓" if gate.passed else ("?" if gate.passed is None else "✗")
    print(f"{status} {gate.name}: observed={gate.observed} required={gate.required}")
# ✓ fundamental_score: observed=78.3 required=> 75
# ✓ valuation_status:  observed=undervalued required=undervalued
# ✓ sentiment:         observed=status=negative, trend=+0.0831 required=status=negative AND trend > 0

# Reasoning trace
for step in result.reasoning_trace:
    print(step)
# Core score: 78.3/100 (quality 82.1×40% + growth 71.4×25% + dividend 79.5×20% + valuation 81.0×15%)
# Gate 1 (score > 75): PASS
# Gate 2 (valuation = undervalued): PASS (undervalued)
# Hard gates produce base: BUY_CANDIDATE
# Gate 3 (sentiment negative+improving): PASS (status=negative, trend=+0.0831)
# BUY: all three gates passed
# Macro tailwind: inflation → healthcare mixed 0.35 (some benefit from pricing power)
# Confidence: 0.74 (data_quality=0.86×30% + val_certainty=1.00×25% + signal_agreement=0.75×30% + soft_quality=0.70×15%)
```

---

### Example 2: WATCH — valuation gate fails

```python
result = decide("AAPL", fundamental, sentiment=sentiment)
# fundamental.total = 63.2
# fundamental.valuation.status = "fair"

result.decision  # "WATCH"

# AAPL's classic position: great company, fair price
# Gate 1 PASS (63.2 < 75 — actually WATCH from score alone)
# Gate 2 FAIL (fair, not undervalued)
# BUY was never on the table; WATCH from score range

for f in result.rejected_factors:
    print(f.name, ":", f.note)
# Fundamental score : 63.2/100 does not reach BUY threshold (75)
# Valuation         : Status: fair — 'undervalued' required for BUY
```

---

### Example 3: BUY downgraded by macro

```python
# Bank stock during financial crisis
result = decide(
    "BAC",
    fundamental,  # strong fundamentals, undervalued
    sector="financials",
    sentiment=sentiment,  # negative but improving
    macro=macro_tag("Regional bank failure triggers systemic risk concerns"),
)

result.decision  # "WATCH"
# → Hard gates all passed → BUY_CANDIDATE
# → Sentiment gate passed
# → Macro: "financial_crisis" → financials bearish 0.90 (≥ 0.60 threshold) → BUY→WATCH

for f in result.rejected_factors:
    print(f.name)
# Macro headwind: financial_crisis

result.uncertainty_flags
# ['Macro: financial_crisis is bearish for financials (strength 0.90)']
```

---

### Example 4: Full output with uncertainty

```python
result = decide("NEWCO", fundamental)
# Score: 71.0 (WATCH range)
# Valuation: unknown (no P/E or yield history)
# No sentiment provided
# No macro provided

result.decision          # "WATCH"
result.confidence        # low (~0.35)
result.uncertainty_flags
# ['Valuation: status unknown — no P/E or dividend yield history available',
#  'Sentiment: no headline data — gate cannot be evaluated',
#  'Macro: no macro context provided']

result.notes[2]  # "Uncertainty: 3 flag(s) — Valuation: status unknown..., Sentiment: no headline data..."
```

---

## Using the engine in code

```python
from src.decision.engine import decide
from src.fundamentals.scorer import score as fund_score
from src.sentiment.scorer import score as sent_score
from src.macro.tagger import tag as macro_tag
from src.data.cache import get
from config.markets import MARKETS
from datetime import date

# Fetch (cached)
data = get("JNJ")

# Score upstream modules
fundamental = fund_score("JNJ", data.fundamentals, MARKETS["US"])
sentiment   = sent_score("JNJ", [(date(2024,1,1), "JNJ reports solid earnings")])
macro       = macro_tag("Elevated inflation and rate hike cycle persist")

# Decide
result = decide(
    "JNJ",
    fundamental,
    sector="healthcare",
    sentiment=sentiment,
    macro=macro,
    missing_fields=data.missing_fields,
)

print(result.decision)           # "BUY" | "WATCH" | "AVOID"
print(result.score)              # 0–100
print(result.confidence)         # 0.0–1.0
print(result.valuation_status)   # undervalued | fair | overvalued | unknown

# Gates
for g in result.gates:
    print(f"{'PASS' if g.passed else 'FAIL':4s} | {g.name:20s} | {g.note}")

# Confidence breakdown
cb = result.confidence_breakdown
print(f"Data quality:      {cb.data_quality:.2f}  × 30% = {cb.data_quality * 0.30:.3f}")
print(f"Val certainty:     {cb.valuation_certainty:.2f}  × 25% = {cb.valuation_certainty * 0.25:.3f}")
print(f"Signal agreement:  {cb.signal_agreement:.2f}  × 30% = {cb.signal_agreement * 0.30:.3f}")
print(f"Soft quality:      {cb.soft_signal_quality:.2f}  × 15% = {cb.soft_signal_quality * 0.15:.3f}")
print(f"Total confidence:  {cb.total:.2f}")

# Full trace
for step in result.reasoning_trace:
    print(f"  → {step}")
```

---

## How to run the tests

```bash
python3 -m pytest tests/test_decision/ -v
```

**Expected result: 92 passed**

No test makes a network call. All inputs are constructed inline using factory functions.

The 92 tests are organised into twelve classes:

| Class | Tests | What it covers |
|---|---|---|
| `TestDecisionBUY` | 7 | All three gates, exact threshold boundary, macro tailwind does not block |
| `TestDecisionWATCH` | 7 | Score range, valuation failure, sentiment failure, macro downgrade |
| `TestDecisionAVOID` | 3 | Low score, zero score, strong sentiment cannot rescue |
| `TestSentimentGate` | 6 | Negative+improving, negative+worsening, positive, neutral, zero trend, absent |
| `TestMacroAdjustment` | 7 | Strong/weak bearish, bullish no-upgrade, no sector, sector not in table, WATCH floor |
| `TestGates` | 6 | Count, names, observed values, required values, notes |
| `TestConfidence` | 7 | Bounds, unknown penalty, missing fields, aligned signals, conflicting, breakdown fields |
| `TestComputeConfidence` | 4 | Formula components: certainty zeroed, undervalued set, data quality reduced |
| `TestSentimentAgreement` | 6 | All direction combinations for BUY/AVOID/WATCH |
| `TestMacroAgreement` | 6 | All direction combinations for BUY/AVOID/WATCH |
| `TestUncertaintyFlags` | 6 | No sentiment, no macro, unknown valuation, low confidence |
| `TestFactors` | 6 | Contributing/rejected content, direction validation |
| `TestReasoningTrace` | 5 | Non-empty, mentions decision, mentions all gates, confidence, macro |
| `TestOutputStructure` | 8 | All fields preserved, None when absent, populated when present |
| `TestEdgeCases` | 5 | Perfect stock, worst stock, empty macro sectors, zero trend |
| `TestDeterminism` | 3 | Same inputs → same decision, confidence, trace length |

---

## Design rules

**Hard gates determine the ceiling; soft gates and macro set the floor.**
Fundamentals and valuation can produce a BUY candidate. Sentiment failure and macro headwinds can lower that to WATCH. Nothing can raise WATCH to BUY or AVOID to WATCH — the architecture is strictly downward-only for modifiers.

**Every evaluation is recorded whether it passed or failed.**
The `gates`, `contributing_factors`, and `rejected_factors` lists are populated regardless of outcome. A reviewer should be able to reconstruct the complete decision by reading these lists without re-running the function.

**Uncertainty is named, not hidden in a confidence penalty.**
A low confidence score tells you something is uncertain. The `uncertainty_flags` list tells you what specifically is uncertain. Both are always present.

**Soft signals default to 0.5 (neutral) when absent, not 0.0 (wrong).**
A missing sentiment signal does not mean sentiment is bad — it means sentiment is unknown. Confidence components default to 0.5 in the absence of data.

**Macro only downgrades.**
Allowing macro to upgrade decisions would require the macro signal to be accurate enough to override fundamentals. The macro tagger's limitations (uncalibrated weights, unknown classification accuracy) make it unsuitable as a positive gate.

**Deterministic.**
No randomness, no timestamps, no external calls in the decision logic. Same inputs always produce the same `DecisionResult`.

---

## What is not in this module

| Concern | Where it lives |
|---|---|
| Fetching data, scoring fundamentals, sentiment, macro | Upstream modules (`src/data/`, `src/fundamentals/`, `src/sentiment/`, `src/macro/`) |
| Position sizing | Not implemented |
| Portfolio-level correlation and concentration | Not implemented |
| Exit timing (when to sell) | `src/backtest/` (not yet implemented) |
| Historical backtesting of this decision rule | `src/backtest/` (not yet implemented) |
| Benchmarking against SPY / random portfolio | Not implemented — most critical validation gap |
| Threshold calibration against forward returns | Not implemented — requires a labelled return dataset |
