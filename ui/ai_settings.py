"""Persistent AI provider configuration for the UI.

Settings are stored in ui/ai_settings.json and take precedence over
environment variables. Default state is provider="none" (disabled).

Supported providers
-------------------
ollama  — local model via Ollama; pick any installed model
claude  — Anthropic Claude via API key (not yet wired)
openai  — OpenAI ChatGPT via API key (not yet wired)
"""

import json
import urllib.error
import urllib.request
from pathlib import Path

from src.ai.ollama import OllamaProvider
from src.ai.service import NewsAnalysisService

_SETTINGS_FILE = Path(__file__).resolve().parent / "ai_settings.json"

PROVIDERS = {
    "none":   "Disabled",
    "ollama": "Ollama (local)",
    "claude": "Claude — Anthropic",
    "openai": "ChatGPT — OpenAI",
}

_DEFAULTS: dict = {
    "provider": "none",
    "ollama_model": "",
    "ollama_base_url": "http://127.0.0.1:11434",
    "ollama_timeout": 120,
}


def load() -> dict:
    if not _SETTINGS_FILE.exists():
        return dict(_DEFAULTS)
    try:
        data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        return {**_DEFAULTS, **data}
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULTS)


def save(updates: dict) -> None:
    merged = {**_DEFAULTS, **{k: v for k, v in updates.items() if k in _DEFAULTS}}
    _SETTINGS_FILE.write_text(json.dumps(merged, indent=2), encoding="utf-8")


def get_service() -> NewsAnalysisService | None:
    """Return a configured AI service based on saved settings, or None."""
    cfg = load()
    provider = cfg.get("provider", "none")

    if provider == "ollama":
        model = cfg.get("ollama_model", "").strip()
        if not model:
            return None
        return NewsAnalysisService(
            OllamaProvider(
                model=model,
                base_url=cfg.get("ollama_base_url", "http://127.0.0.1:11434"),
                timeout_seconds=float(cfg.get("ollama_timeout", 120)),
            )
        )

    return None


def cache_key_suffix() -> str:
    """String that changes when provider or model changes, so the pipeline cache self-invalidates."""
    cfg = load()
    provider = cfg.get("provider", "none")
    if provider == "ollama":
        return f"ollama:{cfg.get('ollama_model', '')}"
    return "none"


def list_ollama_models(base_url: str = "") -> list[dict]:
    """Query the running Ollama instance and return its installed models.

    Returns list of dicts: [{"name": "qwen3:latest", "size_gb": 4.7}, ...]
    Returns [] if Ollama is unreachable.
    """
    if not base_url:
        base_url = load().get("ollama_base_url", "http://127.0.0.1:11434")
    url = base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return []

    models = []
    for m in data.get("models", []):
        name = m.get("name", "")
        if not name:
            continue
        size_bytes = m.get("size", 0)
        size_gb = round(size_bytes / 1e9, 1) if size_bytes else None
        models.append({"name": name, "size_gb": size_gb})
    models.sort(key=lambda m: m["name"])
    return models
