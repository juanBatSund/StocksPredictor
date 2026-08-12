"""Configuration boundary for optional local Ollama analysis."""

from config.settings import (
    AI_NEWS_ANALYSIS_ENABLED,
    AI_OLLAMA_BASE_URL,
    AI_OLLAMA_MODEL,
    AI_OLLAMA_TIMEOUT_SECONDS,
)
from src.ai.ollama import OllamaProvider
from src.ai.service import NewsAnalysisService


def configured_news_analysis_service() -> NewsAnalysisService | None:
    """Enable local AI analysis only after an operator explicitly configures it."""
    if not AI_NEWS_ANALYSIS_ENABLED or not AI_OLLAMA_MODEL:
        return None
    return NewsAnalysisService(
        OllamaProvider(
            model=AI_OLLAMA_MODEL,
            base_url=AI_OLLAMA_BASE_URL,
            timeout_seconds=AI_OLLAMA_TIMEOUT_SECONDS,
        )
    )
