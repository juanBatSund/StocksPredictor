from dataclasses import dataclass

from config.markets import MarketProfile
from config.settings import SCORE_BUY, SCORE_WATCH_MIN, WEIGHTS
from src.data.models import Fundamentals
from src.fundamentals import dividend, growth, quality
from src.fundamentals.dividend import DividendScore
from src.fundamentals.growth import GrowthScore
from src.fundamentals.quality import QualityScore
from src.logging.logger import log_input, log_result
from src.valuation import scorer as valuation
from src.valuation.scorer import ValuationScore

_MODULE = "fundamentals.scorer"


@dataclass
class FundamentalResult:
    ticker: str
    total: float              # 0–100 weighted
    quality: QualityScore
    growth: GrowthScore
    dividend: DividendScore
    valuation: ValuationScore

    @property
    def decision_hint(self) -> str:
        if self.total > SCORE_BUY:
            return "BUY candidate"
        if self.total >= SCORE_WATCH_MIN:
            return "WATCH"
        return "AVOID"

    def breakdown(self) -> dict:
        return {
            "ticker": self.ticker,
            "total": self.total,
            "decision_hint": self.decision_hint,
            "components": {
                "quality": {
                    "score": self.quality.total,
                    "weight": WEIGHTS["quality"],
                    "weighted": round(self.quality.total * WEIGHTS["quality"], 2),
                    "detail": {"roe": self.quality.roe, "debt_to_equity": self.quality.debt_to_equity, "fcf": self.quality.fcf},
                    "notes": self.quality.notes,
                },
                "growth": {
                    "score": self.growth.total,
                    "weight": WEIGHTS["growth"],
                    "weighted": round(self.growth.total * WEIGHTS["growth"], 2),
                    "detail": {"revenue": self.growth.revenue, "earnings": self.growth.earnings},
                    "notes": self.growth.notes,
                },
                "dividend": {
                    "score": self.dividend.total,
                    "weight": WEIGHTS["dividend"],
                    "weighted": round(self.dividend.total * WEIGHTS["dividend"], 2),
                    "detail": {"yield_score": self.dividend.yield_score, "payout": self.dividend.payout, "streak": self.dividend.streak},
                    "notes": self.dividend.notes,
                },
                "valuation": {
                    "score": self.valuation.total,
                    "weight": WEIGHTS["valuation"],
                    "weighted": round(self.valuation.total * WEIGHTS["valuation"], 2),
                    "status": self.valuation.status,
                    "notes": self.valuation.notes,
                },
            },
        }


def score(ticker: str, f: Fundamentals, market: MarketProfile) -> FundamentalResult:
    log_input(_MODULE, {"ticker": ticker, "market": market.code})

    q = quality.score(f)
    g = growth.score(f)
    d = dividend.score(f, market)
    v = valuation.score(f, market)

    total = round(
        q.total * WEIGHTS["quality"]
        + g.total * WEIGHTS["growth"]
        + d.total * WEIGHTS["dividend"]
        + v.total * WEIGHTS["valuation"],
        2,
    )

    result = FundamentalResult(
        ticker=ticker,
        total=total,
        quality=q,
        growth=g,
        dividend=d,
        valuation=v,
    )

    log_result(_MODULE, {
        "ticker": ticker,
        "market": market.code,
        "total": total,
        "quality": q.total,
        "growth": g.total,
        "dividend": d.total,
        "valuation": v.total,
        "valuation_status": v.status,
        "decision_hint": result.decision_hint,
    })

    return result
