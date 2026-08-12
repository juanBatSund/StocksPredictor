"""Local Ollama adapter using its schema-constrained chat endpoint.

The adapter has no tool definitions, broker credentials, or order-execution
path. It only submits bounded research text to a configured local model.
"""

import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.ai.models import ProviderResponse
from src.ai.provider import AIProviderError


class OllamaProvider:
    """Call a locally hosted Ollama model and require JSON-schema output."""

    name = "ollama"

    def __init__(
        self,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 60.0,
    ) -> None:
        if not model.strip():
            raise ValueError("Ollama model must be configured")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
    ) -> ProviderResponse:
        payload = {
            "model": self.model,
            "stream": False,
            "format": response_schema,
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        request = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise AIProviderError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise AIProviderError(
                f"Cannot reach Ollama at {self.base_url}: {exc.reason}"
            ) from exc
        except OSError as exc:
            raise AIProviderError(f"Ollama request failed: {exc}") from exc

        try:
            parsed: dict[str, Any] = json.loads(raw)
            content = parsed["message"]["content"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise AIProviderError("Ollama returned an invalid chat response") from exc

        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("Ollama returned an empty analysis")

        return ProviderResponse(
            provider=self.name,
            model=str(parsed.get("model") or self.model),
            content=content,
            received_at=datetime.now(timezone.utc),
            request_id=str(parsed["created_at"]) if parsed.get("created_at") else None,
        )
