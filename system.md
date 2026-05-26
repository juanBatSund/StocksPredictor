# Investment Decision System v1

## Purpose
Build a transparent system to identify long-term (1–5 years) stock investment opportunities based on:
- Fundamentals (quality, growth, dividends)
- Valuation
- Sentiment
- Macro/geopolitical context

---

## Principles
- No black box decisions
- All outputs must be explainable
- Deterministic outputs (same input = same output)
- No data leakage in backtesting
- Benchmarking is mandatory

---

## Architecture

GLOBAL EVENTS
→ SECTOR IMPACT
→ FUNDAMENTALS
→ VALUATION
→ SENTIMENT
→ DECISION
→ BACKTEST

---

## Scoring System

Weights:
- Quality: 40%
- Growth: 25%
- Dividend: 20%
- Valuation: 15%

Score Range:
0–100

---

## Fundamental Definitions

Quality:
- ROE > 12%
- Debt/Equity < 1
- Positive free cash flow

Growth:
- Positive 5Y revenue growth
- Positive 5Y earnings growth

Dividend:
- Yield: 2–5%
- Payout ratio < 60%
- Stable or growing dividend

Valuation:
- P/E compared to 5-year average
- Dividend yield vs historical

---

## Decision Rules

BUY:
- Score > 75
- Valuation = undervalued
- Sentiment = negative but improving

WATCH:
- Score 60–75

AVOID:
- Score < 60

---

## Sentiment

Score:
- Range: -1 to +1

Interpretation:
- Negative improving = potential opportunity
- Positive extreme = possible overpricing

---

## Macro Logic

Examples:
- War → defense sector positive
- High interest rates → banks positive
- Inflation → mixed impact

---

## Backtesting Rules

- Time-based simulation only
- No future data
- Entry: BUY condition
- Exit:
  - After 1–2 years OR
  - Score drops below 60

---

## Benchmarking

Compare against:
- S&P 500 (SPY)
- Random portfolio

Metrics:
- CAGR
- Max drawdown
- Win rate

---

## Output Format

Each stock must include:

- Total Score
- Score breakdown
- Valuation status
- Sentiment score
- Macro context
- Final decision (BUY / WATCH / AVOID)
- Explanation (human-readable)

---

## Logging

System must log:
- Inputs
- Calculations
- Decisions
- Model version

----
## Macro and Sentiment Constraints

Macro and sentiment modules:
- cannot directly issue BUY/SELL decisions
- can only influence confidence and opportunity ranking
- must remain explainable and benchmarkable

-----
## Decision Engine Constraints

The decision engine:
- must expose all contributing factors
- must not hide weighting logic
- must separate:
  - hard signals (fundamentals, valuation)
  - soft signals (sentiment, macro)
- must output confidence and uncertainty
- must allow replay of historical decisions

## Confidence Disclaimer

Confidence scores are heuristic indicators only.
They are not probabilities of future returns.


-----

## UI Principles

The UI must prioritize:
- explainability
- traceability
- benchmarking
- historical replay
- inspection of reasoning

The UI must NOT:
- hide uncertainty
- hide failed gates
- present scores without explanations
- imply certainty about future returns

## Debug and Inspection Mode

The UI must expose:
- score breakdowns
- triggered rules
- failed gates
- uncertainty flags
- reasoning traces
- benchmark comparisons