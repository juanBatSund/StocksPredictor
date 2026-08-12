import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Scoring weights (must sum to 1.0)
WEIGHTS = {
    "quality": 0.40,
    "growth": 0.25,
    "dividend": 0.20,
    "valuation": 0.15,
}

# Decision thresholds
SCORE_BUY = 75
SCORE_WATCH_MIN = 60

# Fundamental thresholds
MIN_ROE = 0.12
MAX_DEBT_EQUITY = 1.0
DIVIDEND_YIELD_MIN = 0.02
DIVIDEND_YIELD_MAX = 0.05
MAX_PAYOUT_RATIO = 0.60

# Cache
CACHE_DIR = ROOT / "cache"
CACHE_TTL_SECONDS = 86400  # 24 hours

# Logging
LOG_DIR = ROOT / "logs"

# Optional local AI news analysis. This is off by default and has no effect on
# the deterministic BUY/WATCH/AVOID engine. Configure a local Ollama model only
# when intentionally enabling the advisory sidecar.
AI_AUDIT_DIR = ROOT / "audit" / "ai"
AI_NEWS_ANALYSIS_ENABLED = os.getenv("AI_NEWS_ANALYSIS_ENABLED", "false").lower() in {
    "1", "true", "yes", "on",
}
AI_OLLAMA_BASE_URL = os.getenv("AI_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
AI_OLLAMA_MODEL = os.getenv("AI_OLLAMA_MODEL", "").strip()
AI_OLLAMA_TIMEOUT_SECONDS = float(os.getenv("AI_OLLAMA_TIMEOUT_SECONDS", "60"))

# Data fetcher
YFINANCE_PRICE_PERIOD = "5y"
YFINANCE_PRICE_INTERVAL = "1d"

# Backtest exit
BACKTEST_MIN_HOLD_YEARS = 1
BACKTEST_MAX_HOLD_YEARS = 2
BACKTEST_EXIT_SCORE = 60
