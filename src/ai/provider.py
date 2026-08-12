"""Provider contract shared by local and future hosted model adapters."""

from typing import Any, Protocol

from src.ai.models import ProviderResponse


class AIProviderError(RuntimeError):
    """A recoverable provider, transport, or structured-output failure."""


class AIProvider(Protocol):
    """A provider that returns one schema-constrained response."""

    name: str

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
    ) -> ProviderResponse:
        """Generate a response matching ``response_schema`` or raise AIProviderError."""
