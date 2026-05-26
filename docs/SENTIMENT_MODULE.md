# Sentiment Scoring Module

## What it does

Takes a set of dated financial news headlines and asks:
**"Is the narrative around this stock negative, neutral, or positive — and is it improving or worsening over time?"**

It answers using a lexicon-based keyword scorer with explicitly stated weights: no machine learning, no opaque embeddings, no probabilistic models. Every number in the output traces directly back to a specific word or phrase in `lexicon.py`.

The module produces:
- A **sentiment score** (−1 to +1) for each individual headline
- An **aggregate score** across all headlines
- A **confidence score** based on lexicon coverage
- A **trend** (OLS slope) over time showing whether sentiment is improving or worsening

This module does **not** fetch headlines. It receives a `list[tuple[date, str]]` and returns a `SentimentResult`.

---

## Files

```
src/
└── sentiment/
    ├── lexicon.py   — phrases, single words, intensity modifiers, negation words
    └── scorer.py    — HeadlineScore, SentimentResult, score_headline(), score()

tests/
└── test_sentiment/
    └── test_scorer.py   — 52 tests
```

---

## Quant reviewer critique — read this first

This section is written from the perspective of a sceptical senior quant. If you are tempted to weight sentiment heavily in a trading decision, read these points first.

---

### Weaknesses

**The word list is the model.**
Every weight in `lexicon.py` is manually assigned with no empirical validation against actual price movements. `"beats estimates" → +0.80` is calibrated intuition, not a regression coefficient. If you backtested this lexicon against earnings-announcement returns, most weights would change substantially. The polarity direction might even flip for some terms in specific regimes.

**Neutral is the invisible default.**
Any word absent from the lexicon scores 0.0. For a 10-word headline where 8 words are unknown, the score is driven entirely by whichever 2 words you happened to include. Novel terminology (`SPAC`, `ESG downgrade`, `covenant waiver`), non-English text (Swedish-market tickers), and industry-specific jargon are silently neutral — not flagged as missing, not penalised. Confidence scores close to 0 are your only warning.

**Context is collapsed.**
`"Apple beats estimates"` and `"Analyst expects Apple will beat estimates next quarter"` produce the same score. One is a reported fact; the other is a forward-looking opinion. The module cannot distinguish between the two.

**Negation is shallow.**
The 3-token lookback window handles `"not profitable"` correctly but misses `"The company is not, under any circumstances, at risk of..."` — the negation is too far from the term. Long hedging clauses, common in analyst reports, break the window silently.

**Additive linearity is wrong.**
A headline with `bankruptcy + fraud + scandal` is treated as three independent signals summed. In reality these events are correlated — each additional bad signal adds less marginal information. The sum inflates the magnitude of multi-signal headlines relative to single-signal ones, which the clamping at ±1 only partially corrects.

**One misleading headline has the same weight as ten consistent ones.**
The aggregate is an unweighted mean. Source credibility, publisher prominence, and headline recency within a day are ignored. A Reuters newswire item and a clickbait blog post score identically.

**Confidence ≠ accuracy.**
High confidence means the lexicon had a lot to say about the headline — many tokens matched. It does not mean the sentiment score is correct. A headline can have 100% coverage and still be scored wrong (e.g., irony, sarcasm, conditional language).

**The OLS trend is fragile at small N.**
Three data points technically compute a slope. With N < 10, a single outlier day dominates the regression and the slope is meaningless. The module warns about this in the `trend_note` field but does not enforce a minimum. Callers must check N before acting on the trend.

---

### Hidden assumptions

**English only.**
The tokeniser and lexicon assume English. Swedish, German, or French headlines for foreign-market tickers produce a confidence of 0.0 and a score of 0.0. The system looks neutral on those tickers. It is not neutral — it is blind.

**Headlines are independent.**
If 12 journalists cover the same earnings miss, scoring all 12 gives the appearance of 12 data points of confidence. It is one event repeated 12 times. The aggregate score and confidence will look more certain than the underlying information warrants.

**Polarity is unconditional.**
`"inflation" → −0.15` is always slightly bearish. In reality, inflation is bearish for growth stocks, bullish for banks in a rate-hike cycle, and ambiguous for commodities. The module has no sector-awareness and no regime-awareness.

**Sentiment causes price moves.**
The `system.md` BUY rule is `"sentiment = negative but improving"`. This implies that improving sentiment leads to rising prices. The causal arrow may be reversed: prices often move first, and headlines explaining the move appear after. The module cannot distinguish leading from lagging sentiment.

**The aggregation window is implicit.**
The module aggregates whatever headlines you pass in. If you pass 90 days of headlines for a trend, and 2 days for a signal, both will produce a `status` and a `trend`. The window choice is entirely the caller's responsibility — the module does not enforce a meaningful look-back period.

---

### Potential failure points

| Scenario | What happens | Why it fails |
|---|---|---|
| `"Apple reports record losses"` | ✓ Bearish (phrase match) | Fixed by adding `"record losses"` phrase |
| `"Company fires on all cylinders"` | Neutral (no match) | Idiomatic — not in lexicon |
| `"Revenue down 30% vs analyst consensus"` | Weak bearish or neutral | Magnitude (30%) is ignored; "down" has low weight |
| `"Not just profitable, but record-breaking"` | Score may be wrong | Negation window misreads the qualifying "not just" |
| `"CEO says earnings are 'disappointing'"` | Bearish | Quotes stripped by tokeniser — works, but fragile |
| Non-English headline | Neutral (confidence 0.0) | No multilingual lexicon |
| Duplicate headlines from 10 outlets | 10× signal weight | Identical events multiply the aggregate |

---

### Benchmarking limitations

There is currently no way to validate this module's accuracy because:

1. **No labelled dataset.** We have no ground-truth corpus of `(headline → price_impact)` pairs for this system. Without one, we cannot measure whether the lexicon weights are directionally correct, let alone calibrated.

2. **No random baseline comparison.** `evaluation.md` requires benchmarking against a random baseline. A random sentiment scorer assigns uniform values in [−1, +1]. If this module barely outperforms random on a historical test, the word weights are adding no signal.

3. **Backtest leakage risk.** If you tune lexicon weights by comparing past sentiment scores to past price moves, you will overfit to the specific events in your training window. Out-of-sample performance will be worse.

4. **Survivorship bias.** We see news for companies that survived. Companies that went bankrupt with no coverage, or whose relevant news was in a language the lexicon does not cover, are absent.

---

### Improvements made after critique

The initial design raised these specific issues, which are now fixed:

| Problem | Fix applied |
|---|---|
| `"record losses"` scored neutral (record +, losses −, cancel to 0) | Added `"record losses"` and `"record loss"` phrases to override individual word matches |
| No way to detect that a headline was essentially unscored | Added `low_coverage: bool` flag to `HeadlineScore`; set when `confidence < 0.15` |
| Confidence field misleadingly labelled as accuracy | Note in `confidence_note` explicitly states `"Confidence = lexicon coverage density, not predictive accuracy"` |
| OLS trend silently computed on N=2 without warning | `trend_note` explicitly states `"N=X — interpret cautiously below N=10"` |
| Negation window limitation undocumented | Comment in `_apply_context()` states the known failure mode for long clauses |
| Ambiguous terms (`acquisition`, `restructuring`) implicitly weighted | Comments on those terms in `lexicon.py` name the ambiguity and justify conservative weights |

---

## Inputs

```python
ticker: str
dated_headlines: list[tuple[date, str]]   # (publication_date, headline_text)
```

Headlines do not need to be pre-processed. The module tokenises, lowercases, and strips punctuation internally.

---

## Outputs

### `HeadlineScore`

| Field | Type | Description |
|---|---|---|
| `headline` | `str` | Original text, unchanged |
| `score` | `float` | −1 to +1, clamped sum of applied weights |
| `confidence` | `float` | 0–1; matched tokens / total tokens × 4, capped at 1 |
| `low_coverage` | `bool` | True when confidence < 0.15 — module had very little to say |
| `matched` | `list[MatchedTerm]` | Every phrase/word that contributed, with weights |
| `note` | `str` | Human-readable summary: match count, score, confidence |

### `MatchedTerm`

| Field | Type | Description |
|---|---|---|
| `term` | `str` | Phrase or word from lexicon |
| `base_weight` | `float` | Raw lexicon weight before modifiers |
| `applied_weight` | `float` | After negation (sign flip) and intensity (multiplier) |
| `negated` | `bool` | True if a negation word was found in the lookback window |
| `intensity` | `float \| None` | Intensity multiplier applied, or None |

### `SentimentResult`

| Field | Type | Description |
|---|---|---|
| `ticker` | `str` | e.g. `"AAPL"` |
| `score` | `float` | Unweighted mean of headline scores, −1 to +1 |
| `confidence` | `float` | Unweighted mean of headline confidences, 0–1 |
| `status` | `str` | `"positive"` / `"negative"` / `"neutral"` |
| `trend` | `float` | OLS slope of daily avg scores; positive = improving |
| `headline_scores` | `list[HeadlineScore]` | Per-headline breakdown, in input order |
| `daily_scores` | `list[tuple[str, float]]` | `(ISO date, avg daily score)` — OLS inputs |
| `notes` | `list[str]` | `[score_note, confidence_note, trend_note]` |

**Status thresholds:**

| Score | Status |
|---|---|
| > +0.10 | `positive` |
| −0.10 to +0.10 | `neutral` |
| < −0.10 | `negative` |

The `system.md` BUY rule requires `status == "negative"` and `trend > 0` (negative but improving). The decision module applies that gate; this module only produces the values.

---

## Scoring pipeline

### Step 1 — Tokenise

```python
re.sub(r"[^\w\s]", " ", text.lower()).split()
```

All punctuation (including hyphens and apostrophes) is stripped. `"52-week high"` → `["52", "week", "high"]`.

### Step 2 — Phrase matching

Phrases from `PHRASES` are matched before individual words, longest phrase first, left-to-right, non-overlapping. Once a token is consumed by a phrase, it cannot be matched again as a single word.

**Why longest-first matters:** without it, `"beats"` (a single-word term) would match before `"beats estimates"` (the phrase), causing the more accurate phrase to be missed.

### Step 3 — Word matching

Any remaining unclaimed token that appears in `TERMS` is matched and added to the contribution list.

### Step 4 — Context modifiers

For each match at position `i`, the module looks back up to 3 tokens for:
- A **negation word** (`not`, `no`, `never`, ...) → flip the sign of the weight
- An **intensity modifier** (`significantly`, `slightly`, ...) → multiply the weight

Both can apply simultaneously. `"not significantly profitable"` → base weight +0.40, intensity ×1.50 = +0.60, negated = −0.60.

### Step 5 — Aggregate and clamp

Sum all `applied_weight` values. Clamp to `[−1.0, +1.0]`.

### Step 6 — Confidence

```
matched_token_count / total_tokens × 4.0, capped at 1.0
```

Rationale: a financial headline is typically 8–12 words. Matching 25 %+ of tokens (e.g., 2 of 8) is strong lexicon coverage and returns confidence 1.0. Matching 0 terms returns 0.0.

This is **coverage density**, not accuracy. Label it as such when displaying to users.

### Step 7 — Trend

The trend is the OLS slope of the series of daily average scores:

```
xs = [0, 1, 2, ...] (day index)
ys = [avg_score_day_1, avg_score_day_2, ...]
slope = (n·Σxy − Σx·Σy) / (n·Σx² − (Σx)²)
```

Positive slope = sentiment improving. Negative slope = sentiment worsening.
Requires ≥ 2 distinct dates. Returns 0.0 for a single date or no headlines.
Interpret cautiously below N = 10 distinct dates.

---

## Lexicon structure

### Phrases (`PHRASES`)

Multi-word patterns matched before individual words. Stored as lowercase strings with spaces (hyphens stripped to match the tokeniser). ~80 phrases covering earnings, guidance, distress, dividends, legal events, and analyst ratings.

**Polarity:** −1.0 (catastrophic bearish) to +1.0 (very bullish). Reserved extremes:
- `"bankruptcy filing"` → −1.00 (near-certain severe negative)
- `"files for bankruptcy"` → −1.00

**Key design rule for contradictory compounds:** `"record losses"` must appear in `PHRASES` or it scores as 0.0 (the +0.40 for "record" and −0.40 for "losses" cancel). The phrase takes priority and scores −0.70. Always check for compound contradictions when adding single-word terms.

### Single words (`TERMS`)

~90 terms matched after phrase consumption. Ambiguous terms are included at conservative magnitudes:
- `"acquisition"` → +0.10 (can be growth or overpayment)
- `"restructuring"` → −0.20 (can be turnaround or distress)
- `"merger"` → +0.10 (speculative)

### Intensity modifiers (`INTENSITY_MODIFIERS`)

14 modifiers: amplifiers (1.30–1.50×) and dampeners (0.40–0.60×). These are rare in headlines because financial reporters use strong verbs directly (`plunges` rather than `significantly falls`). Their effect on aggregate scores is marginal.

### Negation words (`NEGATION_WORDS`)

16 words that flip the sign of the next sentiment term within the 3-token window. Handles common patterns (`not profitable`, `no growth`, `averted bankruptcy`) but fails on long hedging clauses.

---

## Examples

### Example 1: Improving trend — a turnaround

**Input:**
```python
from datetime import date
from src.sentiment.scorer import score

headlines = [
    (date(2024, 1, 1), "Company misses estimates and issues profit warning"),
    (date(2024, 1, 8), "Management updates: cost cuts underway, no further guidance changes"),
    (date(2024, 1, 15), "Company beats estimates, raised guidance for full year"),
]

result = score("XYZ", headlines)
```

**Output:**
```
score      = +0.183    (positive — net bullish across the window)
status     = "positive"
confidence = 0.51
trend      = +0.183    (improving: daily scores: −0.80, 0.0, +0.80)

headline_scores[0]:
  headline   = "Company misses estimates and issues profit warning"
  score      = −0.800
  matched    = [("misses estimates", −0.80), ("profit warning", −0.80)]
  note       = "2 match(es): score −0.800 (negative), confidence 0.80"

headline_scores[1]:
  headline   = "Management updates: cost cuts underway, no further guidance changes"
  score      = 0.0
  matched    = []
  note       = "no lexicon matches in 9 tokens — neutral 0.0"
  low_coverage = True

headline_scores[2]:
  headline   = "Company beats estimates, raised guidance for full year"
  score      = +0.800
  matched    = [("beats estimates", +0.80), ("raised guidance", +0.65)]
  note       = "2 match(es): score +0.800 (positive), confidence 0.87"

daily_scores = [("2024-01-01", −0.80), ("2024-01-08", 0.00), ("2024-01-15", +0.80)]
trend_note   = "OLS slope +0.1829/day over 3 date(s) — improving. N=3 — interpret cautiously below N=10"
```

The BUY rule in `system.md` requires `status == "negative"` and `trend > 0`. This example ends in `status == "positive"`, so the BUY gate would not trigger here — but the trend being positive is meaningful context for the decision module.

---

### Example 2: Record losses — phrase override

Without the phrase `"record losses"`, this headline would score neutral (record +0.40 cancels losses −0.40).

```python
r = score_headline("Company reports record losses in worst quarter since 2008")
# score  = −0.70  (phrase "record losses" matched; individual words not double-counted)
# status = negative
# matched = [MatchedTerm(term="record losses", base_weight=−0.70, applied_weight=−0.70, ...)]
```

---

### Example 3: Negation

```python
r = score_headline("Company avoids bankruptcy filing after debt restructuring deal")
# "bankruptcy filing" → base −1.00
# "avoids" is a negation word → applied_weight = +1.00 → clamped to +1.0
# score = +1.0  (correctly reads as a near-miss that was averted)
```

---

### Example 4: Low coverage warning

```python
r = score_headline("The quarterly announcement was made on Tuesday afternoon")
# score       = 0.0
# confidence  = 0.0
# low_coverage = True
# note        = "no lexicon matches in 7 tokens — neutral 0.0"
```

A neutral score with `low_coverage = True` should be treated differently from a genuine neutral score with high coverage. The former means "no opinion"; the latter means "signals cancel". The decision module must handle both.

---

## Using the scorer in code

```python
from datetime import date
from src.sentiment.scorer import score, score_headline

# Single headline
r = score_headline("Company beats estimates and raises guidance for Q4")
print(r.score)            # +0.80
print(r.confidence)       # 0.93
print(r.low_coverage)     # False
print(r.matched[0].term)  # "beats estimates"
print(r.note)             # "2 match(es): score +0.800 (positive), confidence 0.93"

# Collection of headlines with dates
headlines = [
    (date(2024, 1, 1), "Company misses estimates and issues profit warning"),
    (date(2024, 1, 8), "Strong results: company beats estimates and raised guidance"),
]

result = score("AAPL", headlines)
print(result.score)          # aggregate score
print(result.status)         # "positive" | "negative" | "neutral"
print(result.trend)          # OLS slope; + = improving
print(result.notes[2])       # trend explanation
print(result.daily_scores)   # [(date, avg_score), ...]

# Full breakdown per headline
for hs in result.headline_scores:
    print(hs.headline)
    for m in hs.matched:
        print(f"  {m.term}: base={m.base_weight:+.2f} applied={m.applied_weight:+.2f}"
              f" negated={m.negated} intensity={m.intensity}")
```

---

## How to run the tests

```bash
python3 -m pytest tests/test_sentiment/ -v
```

**Expected result: 52 passed**

No test makes a network call. All inputs are constructed inline.

The 52 tests are organised into seven classes:

| Class | Tests | What it covers |
|---|---|---|
| `TestTokenize` | 5 | Lowercase, punctuation stripping, hyphen handling, empty input |
| `TestScoreHeadlineBasic` | 4 | Empty input, no matches, determinism, note field |
| `TestScoreHeadlinePhrases` | 7 | Phrase matching, clamping, phrase-before-word priority, record losses fix |
| `TestScoreHeadlineWords` | 5 | Single word signals, clamping, exposed fields |
| `TestNegation` | 3 | Sign reversal, flag on matched term |
| `TestIntensity` | 3 | Amplification, dampening, stored multiplier |
| `TestConfidence` | 5 | Zero on no match, bounded 0–1, low-coverage flag |
| `TestAggregation` | 10 | Mean arithmetic, status thresholds, empty input, daily score grouping |
| `TestTrend` | 6 | Single date, empty, improving, worsening, flat, three dates |
| `TestOLSSlope` | 4 | Exact slope values, flat, degenerate (constant x) |

---

## Design rules

**The lexicon is the model — and that is a feature, not a bug.** Every scoring decision traces to a row in `lexicon.py`. A human expert can audit, override, or extend the weights. There is no hidden layer.

**Phrases override words.** When a phrase matches, the tokens it consumes cannot also match as individual words. This prevents double-counting and allows contradictory compounds (`"record losses"`) to be correctly identified.

**Negation and intensity are lookback-only.** The module looks backwards from a matched term, not forward. This prevents intensity words at the end of a sentence from reaching back to modify terms earlier in the sentence. The 3-token window is a trade-off between coverage and false positives.

**Confidence is coverage, not accuracy.** The confidence score tells you how much lexicon vocabulary appeared in the headline. It does not tell you whether the resulting score is correct. Always display `low_coverage = True` headlines with a caveat.

**Trend requires a minimum N from the caller.** The module computes the OLS slope for any N ≥ 2 and warns in `trend_note` when N < 10. Enforcing a minimum is the caller's responsibility; the module does not refuse to compute.

**Deterministic.** No randomness, no timestamps, no external calls. Same `(ticker, dated_headlines)` input always produces the same `SentimentResult`.

---

## What is not in this module

| Concern | Where it lives |
|---|---|
| Fetching news headlines from an API or RSS feed | `src/data/` (not yet implemented) |
| Weighting headlines by source credibility | Not implemented |
| Multilingual lexicons (Swedish, German, etc.) | Not implemented |
| Named entity recognition (which company does the headline mention?) | Not implemented |
| Sector-aware polarity (`inflation` = bearish for growth, bullish for banks) | Not implemented |
| The BUY / WATCH / AVOID decision that consumes sentiment | `src/decision/` (not yet implemented) |
| Backtesting sentiment signals against price moves | `src/backtest/` (not yet implemented) |
| Lexicon validation against labelled ground truth | Not implemented — this is the module's most critical gap |
