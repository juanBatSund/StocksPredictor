"""
Mock data for the inspectable UI.

Every field mirrors the real DecisionResult / HistoricalSnapshot types so
the UI can be wired to live data by swapping this module.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.decision.engine import DecisionResult, Gate, Factor, ConfidenceBreakdown

# ── Stock metadata (not part of DecisionResult) ────────────────────────────────

STOCK_META = {
    "MSFT": {
        "name": "Microsoft Corporation",
        "sector": "technology",
        "price": 428.50,
        "hi_52w": 468.35,
        "lo_52w": 309.45,
        "missing_fields": [],
    },
    "JNJ": {
        "name": "Johnson & Johnson",
        "sector": "healthcare",
        "price": 156.80,
        "hi_52w": 168.15,
        "lo_52w": 143.22,
        "missing_fields": [],
    },
    "AAPL": {
        "name": "Apple Inc.",
        "sector": "technology",
        "price": 192.35,
        "hi_52w": 237.23,
        "lo_52w": 164.08,
        "missing_fields": ["dividend_yield_5y_avg"],
    },
    "NVDA": {
        "name": "NVIDIA Corporation",
        "sector": "technology",
        "price": 875.45,
        "hi_52w": 974.00,
        "lo_52w": 394.10,
        "missing_fields": [],
    },
    "XOM": {
        "name": "Exxon Mobil Corporation",
        "sector": "energy",
        "price": 118.20,
        "hi_52w": 123.75,
        "lo_52w": 95.77,
        "missing_fields": ["pe_5y_avg", "revenue_growth_5y"],
    },
}

MODEL_VERSION = "v1.0.0"
ANALYSIS_DATE = "2026-05-26"

# ── Helper ─────────────────────────────────────────────────────────────────────

def _conf(dq, vc, sa, sq):
    total = round(dq * 0.30 + vc * 0.25 + sa * 0.30 + sq * 0.15, 4)
    return ConfidenceBreakdown(
        data_quality=dq,
        valuation_certainty=vc,
        signal_agreement=sa,
        soft_signal_quality=sq,
        total=total,
    )


# ── MSFT — BUY (all gates pass) ────────────────────────────────────────────────

_msft = DecisionResult(
    ticker="MSFT",
    decision="BUY",
    score=82.3,
    quality_score=88.0,
    growth_score=79.0,
    dividend_score=71.0,
    valuation_score=82.0,
    valuation_status="undervalued",
    confidence=0.81,
    confidence_breakdown=_conf(1.00, 1.00, 0.87, 0.76),
    gates=[
        Gate("fundamental_score", True,  "82.3",  "> 75",
             "Score 82.3 exceeds BUY threshold of 75"),
        Gate("valuation_status",  True,  "undervalued", "undervalued",
             "P/E 24.1 is below 5-year avg 29.4 — trading at a discount"),
        Gate("sentiment",         True,  "status=negative, trend=+0.0120",
             "status=negative AND trend > 0",
             "Contrarian signal: market pessimism present but receding"),
    ],
    contributing_factors=[
        Factor("Fundamental score",              "supporting", "82.3/100 exceeds BUY threshold (75)"),
        Factor("Valuation",                      "supporting", "Status: undervalued — P/E below 5-year average"),
        Factor("Sentiment: negative but improving", "supporting",
               "Score −0.241, trend +0.0120/day — contrarian opportunity"),
        Factor("Macro tailwind: interest_rate_hike", "supporting",
               "Sector 'technology': mixed impact; rate hikes reduce growth multiples but cloud demand stable"),
    ],
    rejected_factors=[],
    uncertainty_flags=[
        "Sentiment: low lexicon coverage (confidence 0.18) — few headlines matched the financial lexicon",
        "Macro: sector impact classified as 'mixed' — direction not definitively bullish or bearish",
    ],
    sentiment_score=-0.241,
    sentiment_status="negative",
    sentiment_trend=0.0120,
    sentiment_confidence=0.18,
    macro_category="interest_rate_hike",
    macro_sector_direction="mixed",
    macro_sector_strength=0.45,
    macro_confidence=0.72,
    reasoning_trace=[
        "Core score: 82.3/100 (quality 88.0×40% + growth 79.0×25% + dividend 71.0×20% + valuation 82.0×15%)",
        "Gate 1 (score > 75): PASS — 82.3 exceeds threshold",
        "Gate 2 (valuation = undervalued): PASS — P/E 24.1 vs 5Y avg 29.4",
        "Hard gates produce base: BUY_CANDIDATE",
        "Gate 3 (sentiment negative+improving): PASS — status=negative, trend=+0.0120/day",
        "BUY: all three gates passed",
        "Macro: interest_rate_hike → technology: mixed impact, strength 0.45 — below downgrade threshold 0.60; no downgrade",
        "Confidence: 0.81 (data_quality=1.00×30% + val_certainty=1.00×25% + signal_agreement=0.87×30% + soft_quality=0.76×15%)",
    ],
    notes=[
        "BUY: score 82.3/100 | valuation undervalued | confidence 0.81",
        "Components: quality 88.0×40% + growth 79.0×25% + dividend 71.0×20% + valuation 82.0×15%",
        "Uncertainty: 2 flag(s) — low sentiment coverage; macro direction mixed",
    ],
)


# ── JNJ — BUY (all gates pass, dividend-heavy) ────────────────────────────────

_jnj = DecisionResult(
    ticker="JNJ",
    decision="BUY",
    score=78.5,
    quality_score=85.0,
    growth_score=65.0,
    dividend_score=88.0,
    valuation_score=76.0,
    valuation_status="undervalued",
    confidence=0.76,
    confidence_breakdown=_conf(1.00, 1.00, 0.74, 0.68),
    gates=[
        Gate("fundamental_score", True,  "78.5",  "> 75",
             "Score 78.5 exceeds BUY threshold of 75"),
        Gate("valuation_status",  True,  "undervalued", "undervalued",
             "Dividend yield 3.4% is above 5Y average 2.9% — historically cheap on yield basis"),
        Gate("sentiment",         True,  "status=negative, trend=+0.0082",
             "status=negative AND trend > 0",
             "Contrarian signal: litigation headlines fading, sentiment recovering"),
    ],
    contributing_factors=[
        Factor("Fundamental score",                 "supporting", "78.5/100 exceeds BUY threshold (75)"),
        Factor("Valuation",                         "supporting", "Dividend yield 3.4% above 5Y avg 2.9%"),
        Factor("Sentiment: negative but improving", "supporting",
               "Score −0.189, trend +0.0082/day — litigation concerns receding"),
        Factor("Dividend quality",                  "supporting",
               "61-year dividend growth streak; payout ratio 43% (well below 60% threshold)"),
    ],
    rejected_factors=[
        Factor("Growth",  "opposing",
               "5Y revenue growth 4.2% is positive but modest — pharmaceutical pipeline risk"),
    ],
    uncertainty_flags=[
        "Macro: inflation classified as 'mixed' for healthcare — input cost pressure vs pricing power",
        "Sentiment: moderate confidence (0.34) — limited recent headlines",
    ],
    sentiment_score=-0.189,
    sentiment_status="negative",
    sentiment_trend=0.0082,
    sentiment_confidence=0.34,
    macro_category="inflation",
    macro_sector_direction="mixed",
    macro_sector_strength=0.38,
    macro_confidence=0.68,
    reasoning_trace=[
        "Core score: 78.5/100 (quality 85.0×40% + growth 65.0×25% + dividend 88.0×20% + valuation 76.0×15%)",
        "Gate 1 (score > 75): PASS — 78.5 exceeds threshold",
        "Gate 2 (valuation = undervalued): PASS — yield 3.4% above 5Y avg 2.9%",
        "Hard gates produce base: BUY_CANDIDATE",
        "Gate 3 (sentiment negative+improving): PASS — status=negative, trend=+0.0082/day",
        "BUY: all three gates passed",
        "Macro: inflation → healthcare: mixed impact, strength 0.38 — below downgrade threshold 0.60; no downgrade",
        "Confidence: 0.76 (data_quality=1.00×30% + val_certainty=1.00×25% + signal_agreement=0.74×30% + soft_quality=0.68×15%)",
    ],
    notes=[
        "BUY: score 78.5/100 | valuation undervalued | confidence 0.76",
        "Components: quality 85.0×40% + growth 65.0×25% + dividend 88.0×20% + valuation 76.0×15%",
        "Uncertainty: 2 flag(s) — macro mixed; limited recent sentiment data",
    ],
)


# ── AAPL — WATCH (Gate 1 FAIL: score 74.1 < 75, near-miss) ───────────────────

_aapl = DecisionResult(
    ticker="AAPL",
    decision="WATCH",
    score=74.1,
    quality_score=82.0,
    growth_score=76.0,
    dividend_score=45.0,
    valuation_score=71.0,
    valuation_status="fair",
    confidence=0.61,
    confidence_breakdown=_conf(0.93, 0.50, 0.50, 0.62),
    gates=[
        Gate("fundamental_score", False, "74.1",  "> 75",
             "Score 74.1 does not exceed BUY threshold of 75 — 0.9 points short"),
        Gate("valuation_status",  False, "fair",  "undervalued",
             "P/E 28.8 is near 5-year avg 29.1 — no meaningful discount"),
        Gate("sentiment",         False, "status=positive, trend=+0.0031",
             "status=negative AND trend > 0",
             "Positive sentiment may indicate upside is already priced in"),
    ],
    contributing_factors=[
        Factor("Quality",  "supporting", "ROE 31.2%, FCF positive, Debt/Equity 1.8 — strong balance sheet"),
        Factor("Growth",   "supporting", "5Y revenue CAGR 8.4%, earnings growth positive"),
    ],
    rejected_factors=[
        Factor("Fundamental score", "opposing",
               "74.1/100 — 0.9 points below BUY threshold (75)"),
        Factor("Valuation",         "opposing",
               "Status: fair — 'undervalued' required for BUY"),
        Factor("Sentiment gate",    "opposing",
               "Status=positive — contrarian entry signal not present"),
        Factor("Dividend",          "opposing",
               "Yield 0.6% below minimum threshold 2%; payout ratio 16%"),
    ],
    uncertainty_flags=[
        "Missing field: dividend_yield_5y_avg — yield comparison uses market average fallback",
        "Valuation: P/E near historical average — small data revisions could shift status to undervalued",
        "Sentiment: positive sentiment at 0.312 — may indicate momentum risk reversal",
    ],
    sentiment_score=0.312,
    sentiment_status="positive",
    sentiment_trend=0.0031,
    sentiment_confidence=0.62,
    macro_category="interest_rate_hike",
    macro_sector_direction="mixed",
    macro_sector_strength=0.45,
    macro_confidence=0.72,
    reasoning_trace=[
        "Core score: 74.1/100 (quality 82.0×40% + growth 76.0×25% + dividend 45.0×20% + valuation 71.0×15%)",
        "Gate 1 (score > 75): FAIL — 74.1 does not exceed threshold (0.9 points short)",
        "Gate 2 (valuation = undervalued): FAIL — status is 'fair', not 'undervalued'",
        "Hard gates produce base: WATCH (score 74.1 ≥ 60)",
        "Gate 3 (sentiment negative+improving): FAIL — status=positive, trend=+0.0031",
        "Decision stays WATCH (Gate 3 outcome irrelevant when base is already WATCH)",
        "Macro: interest_rate_hike → technology: mixed, strength 0.45 — noted but no change to WATCH",
        "Confidence: 0.61 (data_quality=0.93×30% + val_certainty=0.50×25% + signal_agreement=0.50×30% + soft_quality=0.62×15%)",
    ],
    notes=[
        "WATCH: score 74.1/100 | valuation fair | confidence 0.61",
        "Components: quality 82.0×40% + growth 76.0×25% + dividend 45.0×20% + valuation 71.0×15%",
        "Uncertainty: 3 flag(s) — missing field; near-threshold valuation; positive sentiment",
    ],
)


# ── NVDA — WATCH (BUY_CANDIDATE → macro downgrade) ───────────────────────────

_nvda = DecisionResult(
    ticker="NVDA",
    decision="WATCH",
    score=85.6,
    quality_score=91.0,
    growth_score=94.0,
    dividend_score=22.0,
    valuation_score=81.0,
    valuation_status="undervalued",
    confidence=0.58,
    confidence_breakdown=_conf(1.00, 1.00, 0.25, 0.57),
    gates=[
        Gate("fundamental_score", True,  "85.6",  "> 75",
             "Score 85.6 exceeds BUY threshold of 75"),
        Gate("valuation_status",  True,  "undervalued", "undervalued",
             "P/E 38.2 below 5Y avg 51.7 — significant discount to historical norm"),
        Gate("sentiment",         True,  "status=negative, trend=+0.0092",
             "status=negative AND trend > 0",
             "AI investment thesis doubted; pessimism receding as earnings beat"),
    ],
    contributing_factors=[
        Factor("Fundamental score",                 "supporting", "85.6/100 exceeds BUY threshold (75)"),
        Factor("Valuation",                         "supporting", "P/E 38.2 vs 5Y avg 51.7 — trading at meaningful discount"),
        Factor("Sentiment: negative but improving", "supporting",
               "Score −0.315, trend +0.0092/day — market reassessing AI capex fears"),
        Factor("Growth",                            "supporting",
               "5Y revenue CAGR 41.2%, earnings growth accelerating"),
    ],
    rejected_factors=[
        Factor("Macro headwind: trade_war_tariffs", "opposing",
               "Sector 'technology': bearish, strength 0.74 (≥ 0.60) — export controls on advanced chips; BUY downgraded to WATCH"),
        Factor("Dividend",                          "opposing",
               "Yield 0.04% far below 2% minimum; not a dividend investment"),
    ],
    uncertainty_flags=[
        "Macro: trade_war_tariffs is bearish for technology (strength 0.74) — export controls create revenue uncertainty",
        "Macro: low confidence in 'trade_war_tariffs' category (0.57) — geopolitical situation evolving rapidly",
        "Sentiment confidence moderate (0.46) — AI narrative creates unusual volatility in headline sentiment",
    ],
    sentiment_score=-0.315,
    sentiment_status="negative",
    sentiment_trend=0.0092,
    sentiment_confidence=0.46,
    macro_category="trade_war_tariffs",
    macro_sector_direction="bearish",
    macro_sector_strength=0.74,
    macro_confidence=0.57,
    reasoning_trace=[
        "Core score: 85.6/100 (quality 91.0×40% + growth 94.0×25% + dividend 22.0×20% + valuation 81.0×15%)",
        "Gate 1 (score > 75): PASS — 85.6 exceeds threshold",
        "Gate 2 (valuation = undervalued): PASS — P/E 38.2 vs 5Y avg 51.7",
        "Hard gates produce base: BUY_CANDIDATE",
        "Gate 3 (sentiment negative+improving): PASS — status=negative, trend=+0.0092/day",
        "BUY: all three gates passed → preliminary BUY_CANDIDATE",
        "Macro: trade_war_tariffs → technology: bearish, strength 0.74 (≥ downgrade threshold 0.60)",
        "BUY→WATCH: macro headwind — trade_war_tariffs is bearish for 'technology' (strength 0.74)",
        "Confidence: 0.58 (data_quality=1.00×30% + val_certainty=1.00×25% + signal_agreement=0.25×30% + soft_quality=0.57×15%)",
    ],
    notes=[
        "WATCH: score 85.6/100 | valuation undervalued | confidence 0.58",
        "NOTE: This stock passed all three fundamental gates. Decision downgraded from BUY by macro headwind.",
        "Uncertainty: 3 flag(s) — macro bearish with moderate confidence; sentiment volatility",
    ],
)


# ── XOM — AVOID (score 54.2 < 60) ─────────────────────────────────────────────

_xom = DecisionResult(
    ticker="XOM",
    decision="AVOID",
    score=54.2,
    quality_score=61.0,
    growth_score=48.0,
    dividend_score=72.0,
    valuation_score=38.0,
    valuation_status="overvalued",
    confidence=0.39,
    confidence_breakdown=_conf(0.86, 0.50, 0.61, 0.44),
    gates=[
        Gate("fundamental_score", False, "54.2",  "> 75",
             "Score 54.2 does not exceed BUY threshold of 75"),
        Gate("valuation_status",  False, "overvalued", "undervalued",
             "P/E 14.8 above 5Y avg 11.2 — trading at premium to historical norm"),
        Gate("sentiment",         False, "status=positive, trend=+0.0210",
             "status=negative AND trend > 0",
             "Strong positive sentiment — possible momentum; contrarian signal absent"),
    ],
    contributing_factors=[
        Factor("Dividend quality", "supporting",
               "Yield 3.8% within 2–5% range; 41-year dividend growth streak"),
    ],
    rejected_factors=[
        Factor("Fundamental score", "opposing",
               "54.2/100 — below AVOID threshold (60); does not qualify for WATCH"),
        Factor("Valuation",         "opposing",
               "Status: overvalued — P/E above 5Y average; no valuation margin of safety"),
        Factor("Growth",            "opposing",
               "Missing field revenue_growth_5y — scored 0; actual growth unknown"),
        Factor("Sentiment gate",    "opposing",
               "Positive sentiment (0.481) — upside may already be reflected in price"),
    ],
    uncertainty_flags=[
        "Missing fields: pe_5y_avg, revenue_growth_5y — growth score may be understated; 2 fields missing",
        "Valuation: overvalued status based on available P/E; missing pe_5y_avg reduces certainty",
        "Sentiment: strong positive (0.481) with accelerating trend — momentum risk",
        "Data quality reduced: 2 of 8 fundamental fields unavailable (penalty −0.14)",
    ],
    sentiment_score=0.481,
    sentiment_status="positive",
    sentiment_trend=0.0210,
    sentiment_confidence=0.44,
    macro_category="geopolitical_conflict",
    macro_sector_direction="bullish",
    macro_sector_strength=0.68,
    macro_confidence=0.81,
    reasoning_trace=[
        "Core score: 54.2/100 (quality 61.0×40% + growth 48.0×25% + dividend 72.0×20% + valuation 38.0×15%)",
        "NOTE: growth_score 48.0 reflects missing revenue_growth_5y field (scored 0) — may understate true growth",
        "Gate 1 (score > 75): FAIL — 54.2 does not exceed threshold",
        "Gate 2 (valuation = undervalued): FAIL — status is 'overvalued'",
        "Hard gates produce base: AVOID (score 54.2 < 60)",
        "Gate 3 (sentiment negative+improving): FAIL — status=positive; not contrarian signal",
        "Decision: AVOID (score below WATCH floor of 60)",
        "Macro: geopolitical_conflict → energy: bullish, strength 0.68 — noted but decision already AVOID; soft signals cannot upgrade",
        "Confidence: 0.39 (data_quality=0.86×30% + val_certainty=0.50×25% + signal_agreement=0.61×30% + soft_quality=0.44×15%)",
    ],
    notes=[
        "AVOID: score 54.2/100 | valuation overvalued | confidence 0.39",
        "Components: quality 61.0×40% + growth 48.0×25% (data incomplete) + dividend 72.0×20% + valuation 38.0×15%",
        "Uncertainty: 4 flag(s) — missing fields; overvalued; positive momentum sentiment",
    ],
)


# ── Public registry ────────────────────────────────────────────────────────────

_DECISIONS: dict[str, DecisionResult] = {
    "MSFT": _msft,
    "JNJ":  _jnj,
    "AAPL": _aapl,
    "NVDA": _nvda,
    "XOM":  _xom,
}

_DECISION_ORDER = ["MSFT", "JNJ", "AAPL", "NVDA", "XOM"]


def _enrich(ticker: str, dr: DecisionResult) -> dict:
    meta = STOCK_META[ticker]
    return {
        "ticker":          ticker,
        "name":            meta["name"],
        "sector":          meta["sector"],
        "price":           meta["price"],
        "hi_52w":          meta["hi_52w"],
        "lo_52w":          meta["lo_52w"],
        "missing_fields":  meta["missing_fields"],
        "decision":        dr.decision,
        "score":           dr.score,
        "quality_score":   dr.quality_score,
        "growth_score":    dr.growth_score,
        "dividend_score":  dr.dividend_score,
        "valuation_score": dr.valuation_score,
        "valuation_status":       dr.valuation_status,
        "confidence":             dr.confidence,
        "confidence_breakdown":   dr.confidence_breakdown,
        "gates":                  dr.gates,
        "contributing_factors":   dr.contributing_factors,
        "rejected_factors":       dr.rejected_factors,
        "uncertainty_flags":      dr.uncertainty_flags,
        "sentiment_score":        dr.sentiment_score,
        "sentiment_status":       dr.sentiment_status,
        "sentiment_trend":        dr.sentiment_trend,
        "sentiment_confidence":   dr.sentiment_confidence,
        "macro_category":         dr.macro_category,
        "macro_sector_direction": dr.macro_sector_direction,
        "macro_sector_strength":  dr.macro_sector_strength,
        "macro_confidence":       dr.macro_confidence,
        "reasoning_trace":        dr.reasoning_trace,
        "notes":                  dr.notes,
    }


def get_all_stocks() -> list[dict]:
    return [_enrich(t, _DECISIONS[t]) for t in _DECISION_ORDER]


def get_stock(ticker: str) -> dict | None:
    dr = _DECISIONS.get(ticker)
    if dr is None:
        return None
    return _enrich(ticker, dr)


# ── Benchmark data ─────────────────────────────────────────────────────────────

def get_benchmark() -> dict:
    return {
        "period_start": "2021-01-01",
        "period_end":   "2024-12-31",
        "strategy_cagr":    0.1418,
        "spy_cagr":         0.1183,
        "random_cagr":      0.0731,
        "equal_weight_cagr":0.0914,
        "alpha_vs_spy":     0.0235,
        "outperforms_spy":  True,
        "max_drawdown_strategy": -0.184,
        "max_drawdown_spy":      -0.245,
        "max_drawdown_random":   -0.312,
        "win_rate":    0.684,
        "total_trades": 19,
        "profitable_trades": 13,
        "avg_hold_months": 14.2,
        "exit_reasons": {
            "score_drop":       5,
            "max_hold":        11,
            "end_of_simulation": 3,
        },
        "limitations": [
            "Alpha is not risk-adjusted — no Sharpe ratio vs benchmark",
            "Does not account for survivorship bias in stock selection universe",
            "No transaction costs, slippage, or tax modeled",
            "Benchmark period uses identical calendar window to strategy (no look-ahead)",
            "Random baseline uses equal-weight random selection, not market-cap weighted",
        ],
        "trade_log": [
            {"ticker":"MSFT", "entry":"2021-03-15","exit":"2023-02-10","return_pct":0.312,"exit_reason":"max_hold","entry_score":82.3,"exit_score":78.1},
            {"ticker":"JNJ",  "entry":"2021-04-20","exit":"2022-08-05","return_pct":0.081,"exit_reason":"score_drop","entry_score":79.2,"exit_score":58.4},
            {"ticker":"NVDA", "entry":"2021-07-01","exit":"2022-11-30","return_pct":-0.142,"exit_reason":"score_drop","entry_score":84.1,"exit_score":55.2},
            {"ticker":"AAPL", "entry":"2022-01-10","exit":"2024-01-09","return_pct":0.258,"exit_reason":"max_hold","entry_score":76.8,"exit_score":74.1},
            {"ticker":"MSFT", "entry":"2022-06-15","exit":"2024-05-20","return_pct":0.401,"exit_reason":"max_hold","entry_score":81.9,"exit_score":82.3},
            {"ticker":"JNJ",  "entry":"2023-01-05","exit":"2024-08-12","return_pct":0.062,"exit_reason":"max_hold","entry_score":78.5,"exit_score":76.2},
        ],
    }


# ── Historical replay data ─────────────────────────────────────────────────────

_REPLAY_SNAPSHOTS = {
    "MSFT": [
        {
            "date": "2022-01-03",
            "decision": "WATCH",
            "score": 71.2,
            "quality_score": 84.0, "growth_score": 75.0, "dividend_score": 68.0, "valuation_score": 44.0,
            "valuation_status": "overvalued",
            "confidence": 0.51,
            "sentiment_score": 0.182, "sentiment_status": "positive", "sentiment_trend": 0.0041,
            "macro_category": "covid_recovery",
            "macro_sector_direction": "bullish", "macro_sector_strength": 0.71,
            "uncertainty_flags": ["Valuation overvalued — premium to 5Y avg", "Macro: covid_recovery bullish for tech but already priced in"],
            "gates_summary": "G1: FAIL (71.2 < 75) | G2: FAIL (overvalued) | G3: FAIL (positive sentiment)",
            "change_note": None,
        },
        {
            "date": "2022-06-15",
            "decision": "WATCH",
            "score": 76.8,
            "quality_score": 86.0, "growth_score": 77.0, "dividend_score": 69.0, "valuation_score": 62.0,
            "valuation_status": "fair",
            "confidence": 0.59,
            "sentiment_score": -0.089, "sentiment_status": "negative", "sentiment_trend": -0.0031,
            "macro_category": "interest_rate_hike",
            "macro_sector_direction": "mixed", "macro_sector_strength": 0.48,
            "uncertainty_flags": ["Valuation: fair — not yet undervalued", "Sentiment: negative but worsening (trend −0.0031)"],
            "gates_summary": "G1: PASS (76.8 > 75) | G2: FAIL (fair) | G3: FAIL (negative but not improving)",
            "change_note": "Score crossed 75 threshold. Gate 1 now passes. Awaiting valuation discount.",
        },
        {
            "date": "2022-12-01",
            "decision": "BUY",
            "score": 81.1,
            "quality_score": 87.0, "growth_score": 78.0, "dividend_score": 70.0, "valuation_score": 79.0,
            "valuation_status": "undervalued",
            "confidence": 0.78,
            "sentiment_score": -0.218, "sentiment_status": "negative", "sentiment_trend": 0.0094,
            "macro_category": "interest_rate_hike",
            "macro_sector_direction": "mixed", "macro_sector_strength": 0.43,
            "uncertainty_flags": ["Macro: mixed impact — below downgrade threshold"],
            "gates_summary": "G1: PASS (81.1 > 75) | G2: PASS (undervalued) | G3: PASS (negative+improving)",
            "change_note": "P/E compressed to below 5Y average. Sentiment turned negative-but-improving. All three gates now pass → BUY.",
        },
        {
            "date": "2023-06-15",
            "decision": "BUY",
            "score": 82.3,
            "quality_score": 88.0, "growth_score": 79.0, "dividend_score": 71.0, "valuation_score": 82.0,
            "valuation_status": "undervalued",
            "confidence": 0.81,
            "sentiment_score": -0.241, "sentiment_status": "negative", "sentiment_trend": 0.0120,
            "macro_category": "interest_rate_hike",
            "macro_sector_direction": "mixed", "macro_sector_strength": 0.45,
            "uncertainty_flags": ["Sentiment: low lexicon coverage (0.18)", "Macro: mixed impact"],
            "gates_summary": "G1: PASS (82.3 > 75) | G2: PASS (undervalued) | G3: PASS (negative+improving)",
            "change_note": "Decision unchanged. Score strengthened slightly. Confidence improved.",
        },
        {
            "date": "2024-01-10",
            "decision": "WATCH",
            "score": 77.4,
            "quality_score": 87.0, "growth_score": 78.0, "dividend_score": 71.0, "valuation_score": 58.0,
            "valuation_status": "fair",
            "confidence": 0.62,
            "sentiment_score": 0.341, "sentiment_status": "positive", "sentiment_trend": 0.0180,
            "macro_category": "interest_rate_hike",
            "macro_sector_direction": "mixed", "macro_sector_strength": 0.40,
            "uncertainty_flags": ["Valuation reverted to fair — P/E expanded", "Positive sentiment — upside already priced in"],
            "gates_summary": "G1: PASS (77.4 > 75) | G2: FAIL (fair) | G3: FAIL (positive sentiment)",
            "change_note": "Valuation no longer undervalued as price rallied. Gate 2 fails. Decision reverts to WATCH.",
        },
        {
            "date": "2024-12-01",
            "decision": "WATCH",
            "score": 75.9,
            "quality_score": 88.0, "growth_score": 78.0, "dividend_score": 71.0, "valuation_score": 52.0,
            "valuation_status": "fair",
            "confidence": 0.58,
            "sentiment_score": 0.289, "sentiment_status": "positive", "sentiment_trend": -0.0050,
            "macro_category": "interest_rate_cut",
            "macro_sector_direction": "bullish", "macro_sector_strength": 0.55,
            "uncertainty_flags": ["Valuation: fair — P/E at historical average", "Macro: rate cuts emerging — bullish for growth stocks"],
            "gates_summary": "G1: PASS (75.9 > 75) | G2: FAIL (fair) | G3: FAIL (positive not improving)",
            "change_note": "Macro shifted to rate_cut cycle — bullish tailwind. Sentiment still positive. Watching for valuation reset.",
        },
    ]
}

_REPLAY_TICKERS = list(_REPLAY_SNAPSHOTS.keys())


def get_replay_data(ticker: str = "MSFT") -> dict:
    if ticker not in _REPLAY_SNAPSHOTS:
        ticker = "MSFT"
    snapshots = _REPLAY_SNAPSHOTS[ticker]
    meta = STOCK_META.get(ticker, {})
    return {
        "ticker":       ticker,
        "name":         meta.get("name", ticker),
        "sector":       meta.get("sector", "unknown"),
        "snapshots":    snapshots,
        "all_tickers":  _REPLAY_TICKERS,
        "model_version": MODEL_VERSION,
    }
