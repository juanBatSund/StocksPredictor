"""Immutable, integrity-verifiable storage for AI analysis records."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from src.ai.models import NewsAnalysis, NewsAnalysisRequest, ProviderResponse


class AuditIntegrityError(ValueError):
    """Raised when an audit record no longer matches its recorded content hash."""


class AnalysisAuditRecord(BaseModel):
    """The complete frozen payload for a single AI analysis invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = Field(min_length=64, max_length=64)
    created_at: datetime
    prompt_version: str = Field(min_length=1)
    request: NewsAnalysisRequest
    response: ProviderResponse
    analysis: NewsAnalysis
    record_sha256: str = Field(min_length=64, max_length=64)


def _canonical_json(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: dict) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class AuditStore:
    """One content-addressed JSON file per result; existing records never overwrite."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def write(
        self,
        *,
        request: NewsAnalysisRequest,
        response: ProviderResponse,
        analysis: NewsAnalysis,
        prompt_version: str,
    ) -> AnalysisAuditRecord:
        content = {
            "prompt_version": prompt_version,
            "request": request.model_dump(mode="json"),
            "response": response.model_dump(mode="json"),
            "analysis": analysis.model_dump(mode="json"),
        }
        record_id = _digest(content)
        path = self.path_for(record_id)
        if path.exists():
            return self.load(record_id)

        created_at = datetime.now(timezone.utc)
        unsigned = {
            "record_id": record_id,
            "created_at": created_at.isoformat(),
            **content,
        }
        record = AnalysisAuditRecord(
            **unsigned,
            record_sha256=_digest(unsigned),
        )

        self.root.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(path)
        return record

    def path_for(self, record_id: str) -> Path:
        return self.root / f"{record_id}.json"

    def load(self, record_id: str) -> AnalysisAuditRecord:
        raw = json.loads(self.path_for(record_id).read_text(encoding="utf-8"))
        record = AnalysisAuditRecord.model_validate(raw)
        self.verify(record)
        return record

    @staticmethod
    def verify(record: AnalysisAuditRecord) -> None:
        unsigned = record.model_dump(mode="json", exclude={"record_sha256"})
        if record.record_sha256 != _digest(unsigned):
            raise AuditIntegrityError(
                f"AI audit record {record.record_id} failed integrity verification"
            )
