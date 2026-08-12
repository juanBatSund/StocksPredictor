from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.ai.models import NewsAnalysisRequest, NewsArticle


class TestNewsArticle:
    def test_normalises_ticker(self, article):
        assert article.ticker == "TEST"

    def test_rejects_naive_timestamp(self):
        with pytest.raises(ValidationError, match="timezone-aware"):
            NewsArticle(
                article_id="x",
                ticker="TEST",
                headline="Headline",
                publisher="Source",
                published_at=datetime(2025, 1, 1),
                available_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            )

    def test_rejects_availability_before_publication(self):
        with pytest.raises(ValidationError, match="available_at"):
            NewsArticle(
                article_id="x",
                ticker="TEST",
                headline="Headline",
                publisher="Source",
                published_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
                available_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            )


class TestNewsAnalysisRequest:
    def test_rejects_future_article(self, article, decision_at):
        future_article = article.model_copy(
            update={"available_at": decision_at + timedelta(seconds=1)}
        )
        with pytest.raises(ValidationError, match="after decision_at"):
            NewsAnalysisRequest(
                ticker="TEST",
                decision_at=decision_at,
                articles=[future_article],
            )

    def test_rejects_wrong_ticker(self, article, decision_at):
        other_article = article.model_copy(update={"ticker": "OTHER"})
        with pytest.raises(ValidationError, match="request ticker"):
            NewsAnalysisRequest(
                ticker="TEST",
                decision_at=decision_at,
                articles=[other_article],
            )

    def test_rejects_duplicate_article_ids(self, article, decision_at):
        with pytest.raises(ValidationError, match="unique article_id"):
            NewsAnalysisRequest(
                ticker="TEST",
                decision_at=decision_at,
                articles=[article, article],
            )
