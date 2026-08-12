"""Frozen replay of archived AI analyses without a model or network call."""

from src.ai.audit import AnalysisAuditRecord, AuditStore


def replay(store: AuditStore, record_id: str) -> AnalysisAuditRecord:
    """Load and integrity-check the original analysis; never re-runs a provider."""
    return store.load(record_id)
