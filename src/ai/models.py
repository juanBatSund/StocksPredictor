"""Strict provider-neutral contracts for evidence-grounded news analysis."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCHEMA_VERSION = "1.0"


class _StrictModel(BaseModel):
    """Reject unreviewed provider fields and make instances immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _require_timezone(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


class NewsArticle(_StrictModel):
    """A provenance-rich news item supplied to an AI provider as untrusted data."""

    article_id: str = Field(min_length=1, max_length=128)
    ticker: str = Field(min_length=1, max_length=24)
    headline: str = Field(min_length=1, max_length=2_000)
    publisher: str = Field(min_length=1, max_length=256)
    url: str | None = Field(default=None, max_length=2_048)
    published_at: datetime
    available_at: datetime
    body: str | None = Field(default=None, max_length=20_000)

    @field_validator("ticker")
    @classmethod
    def _normalise_ticker(cls, value: str) -> str:
        return value.upper().strip()

    @field_validator("published_at", "available_at")
    @classmethod
    def _validate_timezones(cls, value: datetime, info) -> datetime:
        return _require_timezone(value, info.field_name)

    @model_validator(mode="after")
    def _availability_cannot_precede_publication(self) -> "NewsArticle":
        if self.available_at < self.published_at:
            raise ValueError("available_at cannot be earlier than published_at")
        return self


class NewsAnalysisRequest(_StrictModel):
    """A bounded packet that was actually available at the decision time."""

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    ticker: str = Field(min_length=1, max_length=24)
    decision_at: datetime
    articles: list[NewsArticle] = Field(min_length=1, max_length=100)

    @field_validator("ticker")
    @classmethod
    def _normalise_ticker(cls, value: str) -> str:
        return value.upper().strip()

    @field_validator("decision_at")
    @classmethod
    def _decision_time_is_aware(cls, value: datetime) -> datetime:
        return _require_timezone(value, "decision_at")

    @model_validator(mode="after")
    def _validate_point_in_time_packet(self) -> "NewsAnalysisRequest":
        ids = [article.article_id for article in self.articles]
        if len(ids) != len(set(ids)):
            raise ValueError("articles must have unique article_id values")
        wrong_ticker = [article.article_id for article in self.articles if article.ticker != self.ticker]
        if wrong_ticker:
            raise ValueError("all articles must have the request ticker")
        future_articles = [
            article.article_id for article in self.articles
            if article.available_at > self.decision_at
        ]
        if future_articles:
            raise ValueError("articles available after decision_at are not allowed")
        return self


class ArticleAnalysis(_StrictModel):
    """A concise, source-linked inference about one supplied article."""

    article_id: str = Field(min_length=1, max_length=128)
    factual_summary: str = Field(min_length=1, max_length=1_500)
    direction: Literal["positive", "negative", "neutral", "mixed", "unknown"]
    relevance: float = Field(ge=0.0, le=1.0)
    horizon: Literal["immediate", "short_term", "medium_term", "long_term", "unknown"]
    rationale: str = Field(min_length=1, max_length=1_500)
    uncertainty_flags: list[str] = Field(default_factory=list, max_length=12)


class NewsAnalysis(_StrictModel):
    """Validated output from an AI provider; not a return forecast."""

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    ticker: str = Field(min_length=1, max_length=24)
    overall_direction: Literal["positive", "negative", "neutral", "mixed", "unknown"]
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    event_types: list[str] = Field(default_factory=list, max_length=12)
    affected_sectors: list[str] = Field(default_factory=list, max_length=20)
    article_analyses: list[ArticleAnalysis] = Field(min_length=1, max_length=100)
    analysis_confidence: float = Field(ge=0.0, le=1.0)
    uncertainty_flags: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("ticker")
    @classmethod
    def _normalise_ticker(cls, value: str) -> str:
        return value.upper().strip()

    @model_validator(mode="after")
    def _article_ids_are_unique(self) -> "NewsAnalysis":
        ids = [item.article_id for item in self.article_analyses]
        if len(ids) != len(set(ids)):
            raise ValueError("article_analyses must have unique article_id values")
        return self


class ProviderResponse(_StrictModel):
    """The provider response retained before structured-output validation."""

    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1)
    received_at: datetime
    request_id: str | None = Field(default=None, max_length=256)

    @field_validator("received_at")
    @classmethod
    def _received_at_is_aware(cls, value: datetime) -> datetime:
        return _require_timezone(value, "received_at")


class AuditedNewsAnalysis(_StrictModel):
    """Validated analysis and immutable audit identity safe for UI/API output."""

    analysis: NewsAnalysis
    audit_record_id: str = Field(min_length=64, max_length=64)
    audit_path: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
