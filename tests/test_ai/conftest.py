from datetime import datetime, timezone

import pytest

from src.ai.models import (
    ArticleAnalysis,
    NewsAnalysis,
    NewsAnalysisRequest,
    NewsArticle,
    ProviderResponse,
)


@pytest.fixture
def decision_at() -> datetime:
    return datetime(2025, 1, 2, 14, 0, tzinfo=timezone.utc)


@pytest.fixture
def article(decision_at: datetime) -> NewsArticle:
    return NewsArticle(
        article_id="news-1",
        ticker="TEST",
        headline="Test Company raises full-year guidance",
        publisher="Example Wire",
        url="https://example.test/news-1",
        published_at=datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc),
        available_at=decision_at,
    )


@pytest.fixture
def analysis_request(article: NewsArticle, decision_at: datetime) -> NewsAnalysisRequest:
    return NewsAnalysisRequest(
        ticker="test",
        decision_at=decision_at,
        articles=[article],
    )


@pytest.fixture
def analysis() -> NewsAnalysis:
    return NewsAnalysis(
        ticker="TEST",
        overall_direction="positive",
        sentiment_score=0.35,
        event_types=["guidance"],
        affected_sectors=["technology"],
        article_analyses=[ArticleAnalysis(
            article_id="news-1",
            factual_summary="The supplied headline says that guidance was raised.",
            direction="positive",
            relevance=0.9,
            horizon="short_term",
            rationale="Raised guidance is generally supportive, subject to the missing details.",
            uncertainty_flags=["Headline contains no numeric guidance details"],
        )],
        analysis_confidence=0.6,
        uncertainty_flags=["Only one supplied article"],
        limitations=["Analysis is evidence interpretation, not a return prediction"],
    )


@pytest.fixture
def provider_response(analysis: NewsAnalysis) -> ProviderResponse:
    return ProviderResponse(
        provider="fake",
        model="fake-model",
        content=analysis.model_dump_json(),
        received_at=datetime(2025, 1, 2, 14, 1, tzinfo=timezone.utc),
        request_id="fake-request-1",
    )
