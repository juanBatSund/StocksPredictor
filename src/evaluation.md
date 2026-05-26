# Evaluation Rules

## Principles
- All outputs must be reproducible
- No hidden reasoning
- All modules must expose intermediate calculations
- All decisions must be explainable

---

## Testing Requirements

Every module must include:
- Unit tests
- Example inputs/outputs
- Edge case handling
- Logging validation

---

## Logging Requirements

Every module must log:
- Input data
- Transformations
- Output values
- Errors
- Timestamp

---

## Benchmarking Rules

Every scoring or decision module must be benchmarkable against:
- Random baseline
- Historical averages
- Existing strategy

---

## Sentiment Rules

Sentiment outputs must include:
- Raw headline
- Score contribution
- Final aggregated score
- Trend calculation explanation

---

## Macro Rules

Macro tagging must include:
- Event category
- Reasoning
- Confidence level
- Affected sectors

---

## Explainability

Every BUY/WATCH/AVOID decision must include:
- Which modules contributed most
- Why decision was made
- Which factors reduced confidence
------------------

## Backtesting Constraints

- No future data leakage
- Decisions must use only information available at that historical date
- Historical replay must be deterministic
- Revised data must not overwrite historical snapshots
- Benchmark comparison must use identical time windows

## Decision Archiving

Every historical decision must store:
- timestamp
- available data at that time
- scores
- macro tags
- sentiment
- final decision

## Investment Philosophy

The system currently follows a contrarian long-term investment philosophy:

- negative but improving sentiment may indicate undervaluation
- excessive positive sentiment may indicate overpricing

This assumption is heuristic and not empirically validated by default.

## Survivorship Bias Protection

Backtests must account for:
- delisted companies
- bankrupt companies
- historical index composition changes

Do not evaluate only surviving winners.

## Historical Validation Rules

Historical evaluation must separate:
- development period
- validation period
- final test period

No strategy adjustments may use the final test period.
## Baseline Comparisons

Benchmarking must include:
- SPY buy-and-hold
- random stock selection baseline
- equal-weight portfolio baseline