import json
from urllib.error import URLError

import pytest

from src.ai.ollama import OllamaProvider
from src.ai.provider import AIProviderError


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class TestOllamaProvider:
    def test_constructs_local_schema_constrained_request(self, monkeypatch):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _Response({
                "model": "local-model",
                "created_at": "2025-01-01T00:00:00Z",
                "message": {"content": '{"ok": true}'},
            })

        monkeypatch.setattr("src.ai.ollama.urlopen", fake_urlopen)
        provider = OllamaProvider("local-model", "http://127.0.0.1:11434", 12)
        response = provider.generate(
            system_prompt="system",
            user_prompt="user",
            response_schema={"type": "object"},
        )

        assert captured["url"] == "http://127.0.0.1:11434/api/chat"
        assert captured["timeout"] == 12
        assert captured["payload"]["model"] == "local-model"
        assert captured["payload"]["stream"] is False
        assert captured["payload"]["format"] == {"type": "object"}
        assert captured["payload"]["options"]["temperature"] == 0
        assert response.provider == "ollama"
        assert response.model == "local-model"

    def test_unavailable_ollama_is_typed_error(self, monkeypatch):
        def unavailable(*_args, **_kwargs):
            raise URLError("connection refused")

        monkeypatch.setattr("src.ai.ollama.urlopen", unavailable)
        provider = OllamaProvider("local-model")
        with pytest.raises(AIProviderError, match="Cannot reach Ollama"):
            provider.generate(
                system_prompt="system",
                user_prompt="user",
                response_schema={"type": "object"},
            )
