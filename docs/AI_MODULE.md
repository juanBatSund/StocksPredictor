# AI Evidence Module

## What it does

Takes a set of news articles for a ticker and asks:
**"What factual evidence exists in these articles — and does it point bullish, bearish, or neutral?"**

It answers using a configurable AI provider (currently Ollama with local models; Claude and OpenAI are stubbed). Every call is stored as an immutable SHA-256-keyed audit record. The output is an evidence packet — not a recommendation. The decision engine receives it and may use it to downgrade a BUY to WATCH, but it can never upgrade a decision or override hard gates.

The module produces:
- An **overall direction** (`"positive"` / `"negative"` / `"neutral"`)
- A **sentiment score** (−1 to +1)
- An **analysis confidence** (0.0–1.0)
- A list of **event types** detected (e.g. `["earnings_beat", "guidance_raise"]`)
- Per-article **factual summaries** with horizon and relevance
- **Uncertainty flags** from the AI itself

This module does **not** fetch news, score fundamentals, or decide BUY/WATCH/AVOID. It receives `list[NewsArticle]` and returns `AuditedNewsAnalysis | AnalysisUnavailable`.

---

## Files

```
src/
└── ai/
    ├── models.py     — Pydantic strict models: NewsArticle, NewsAnalysisRequest,
    │                   NewsAnalysis, AuditedNewsAnalysis, ArticleAnalysis,
    │                   ProviderResponse; AIProvider protocol
    ├── service.py    — NewsAnalysisService, analyze_if_available(),
    │                   AnalysisUnavailable sentinel
    ├── ollama.py     — OllamaProvider (AIProvider implementation)
    ├── factory.py    — (legacy) configured_news_analysis_service() via env vars
    ├── audit.py      — AuditStore: SHA-256 content-addressed immutable JSON records
    └── prompt.py     — System prompt and structured JSON output schema

ui/
├── ai_settings.py   — Persistent provider config; load/save/get_service/cache_key_suffix
├── ai_settings.json — Runtime config file (provider, model, base_url, timeout)
└── templates/
    └── ai_settings.html — Provider selection UI

tests/
└── test_ai/
    ├── conftest.py
    └── test_service.py
```

---

## Reviewer critique — read this first

---

### On the AI output itself

**The AI is not calibrated.**
`analysis_confidence = 0.85` from a local qwen3 model does not mean 85% of news analysed this way leads to the correct directional call. It is the model's self-reported confidence in its own classification. There is no labelled dataset, no backtest of AI calls against price outcomes, and no baseline comparison against the lexicon scorer.

**The AI's training data includes our company.**
If you ask qwen3 about AAPL, it already knows AAPL's history up to its training cutoff. Its "confidence" may reflect memorised information rather than reasoning about the articles provided. This is especially relevant for well-known stocks.

**The AI can hallucinate event types.**
`event_types` is a list of strings from the AI. It is not constrained to a closed vocabulary at the prompt level. "earnings_beat" and "quarterly_beat" and "Q3 beat" can all appear for the same event across different calls. The schema validates the structure, not the content.

**Advisory-only is a design constraint, not a limitation.**
The AI is intentionally blocked from upgrading decisions. This is not because the AI is wrong — it's because the system has no way to validate AI accuracy in this context. Any upgrade path would require the same empirical calibration that the lexicon scorer also lacks.

---

### On the provider architecture

**Local models are slow.**
qwen3:8b running on CPU via Ollama takes 60–180 seconds per analysis call. This blocks the HTTP request thread. The analysis runs as a sidecar in `pipeline.py` but there is no async path — it blocks synchronously before `decide()` is called.

**No retry logic.**
If the Ollama process is running but the model call times out (e.g. first load of a large model), the analysis returns `AnalysisUnavailable`. There is no retry; the pipeline continues without AI evidence.

**Claude and OpenAI are stubs.**
The provider cards exist in the UI and `PROVIDERS` dict. The `AnthropicProvider` class does not yet exist. Selecting Claude in the UI has no effect beyond storing the setting — `get_service()` returns `None` for any provider that is not `"ollama"`.

**The audit store is append-only but not indexed.**
`AuditStore` writes one JSON file per call, keyed by SHA-256 of the request content. There is no index, no expiry, and no query capability. Over time, `logs/ai_audit/` will accumulate unboundedly.

---

## Architecture

```
NewsArticle list (from sentiment.news.fetch_articles)
        │
        ▼
NewsAnalysisRequest  (ticker, decision_at, articles)
        │
        ▼
analyze_if_available(service, request)
  │
  ├─ service is None → AnalysisUnavailable("No AI provider configured")
  │
  └─ AIProvider.analyse(request) → ProviderResponse
       ├─ OllamaProvider: POST /api/generate (structured JSON prompt)
       └─ (future) AnthropicProvider: POST messages API
        │
        ▼
AuditStore.record(request, response)  [SHA-256 keyed JSON file]
        │
        ▼
AuditedNewsAnalysis (audit_record_id, provider, model, prompt_version, analysis)
        │
        ▼
pipeline.py: ai_analysis_obj = outcome.analysis
        │
        ▼
decide(..., ai_analysis=ai_analysis_obj)
  → AI advisory block (see DECISION_MODULE.md — "AI advisory step")
```

---

## Provider configuration

Provider selection is stored in `ui/ai_settings.json` and loaded at runtime. The file is created with defaults on first save.

### `ui/ai_settings.json` schema

```json
{
  "provider": "ollama",
  "ollama_model": "qwen3:latest",
  "ollama_base_url": "http://127.0.0.1:11434",
  "ollama_timeout": 120
}
```

| Field | Default | Description |
|---|---|---|
| `provider` | `"none"` | `"none"` / `"ollama"` / `"claude"` / `"openai"` |
| `ollama_model` | `""` | Ollama model tag (e.g. `"qwen3:latest"`) |
| `ollama_base_url` | `"http://127.0.0.1:11434"` | Ollama server address |
| `ollama_timeout` | `120` | HTTP timeout in seconds — increase for large models |

### `ui/ai_settings.py` API

```python
load() -> dict                             # read json, merge with defaults
save(updates: dict) -> None                # write merged settings
get_service() -> NewsAnalysisService | None  # build provider from settings
cache_key_suffix() -> str                  # "ollama:modelname" or "none"
list_ollama_models(base_url: str) -> list[dict]  # [{name, size_gb}, ...]
```

`cache_key_suffix()` is embedded in the pipeline cache key so switching models automatically busts the cache. Changing from `qwen3:latest` to `llama3.2:latest` produces a different key → cache miss → fresh analysis.

---

## Ollama provider

`OllamaProvider` sends a single `POST /api/generate` request with:
- `stream: false` — waits for the complete response
- A structured JSON schema prompt (from `src/ai/prompt.py`)
- Temperature 0 for deterministic output

**Model detection:** `list_ollama_models()` queries `GET /api/tags` with a 5-second timeout. Returns `[]` if Ollama is not running.

**Why the timeout matters:** Large models (qwen3:8b+) may not be loaded into VRAM on first call. The default 120-second timeout should accommodate first-load latency. Increase to 180–300 for 14B+ models.

---

## AI advisory rules in the decision engine

The decision engine receives the `NewsAnalysis` object (typed, not a dict) and applies these rules **after** all lexicon-based gates:

### Rule 1 — Uncertainty propagation
Up to 5 uncertainty flags from `ai_analysis.uncertainty_flags` are surfixed with `"AI evidence: "` and appended to `uncertainty_flags` in `DecisionResult`.

### Rule 2 — AI/lexicon conflict detection
If the AI direction and the lexicon sentiment status disagree (e.g. AI says `"negative"`, lexicon says `"positive"`), an additional uncertainty flag is added:
```
AI/lexicon conflict: AI direction 'negative' vs lexicon 'positive' — signals disagree, treat with caution
```

### Rule 3 — Downgrade (BUY→WATCH)
**Condition:** `overall_direction == "negative"` AND `analysis_confidence >= 0.70`
**If current decision is BUY:** downgrades to WATCH, adds rejected Factor, appends trace step.
**If current decision is not BUY:** adds rejected Factor and notes it in trace; no change.

The threshold `_AI_DOWNGRADE_CONFIDENCE = 0.70` is defined in `src/decision/engine.py:42`.

### Rule 4 — Positive evidence (no upgrade)
**Condition:** `overall_direction == "positive"` AND `analysis_confidence >= 0.50`
**Effect:** adds a contributing Factor for the caller to see. **Cannot upgrade WATCH→BUY.**

### Rule 5 — Confidence contribution
When `ai_analysis_confidence` is present, `_compute_confidence()` averages three values for the soft signal quality component:
```python
soft_signal_quality = (sentiment_confidence + macro_confidence + ai_analysis_confidence) / 3
```
Without AI, only the two-value average is used. This means AI presence (at any direction) slightly adjusts the confidence score.

---

## Outputs: `AuditedNewsAnalysis`

| Field | Type | Description |
|---|---|---|
| `audit_record_id` | `str` | SHA-256 of the request content |
| `provider` | `str` | e.g. `"ollama"` |
| `model` | `str` | e.g. `"qwen3:latest"` |
| `prompt_version` | `str` | Prompt schema version for future migrations |
| `analysis` | `NewsAnalysis` | Typed analysis result (see below) |

### `NewsAnalysis`

| Field | Type | Description |
|---|---|---|
| `overall_direction` | `str` | `"positive"` / `"negative"` / `"neutral"` |
| `sentiment_score` | `float` | −1 to +1 |
| `analysis_confidence` | `float` | 0.0–1.0 (AI self-reported) |
| `event_types` | `list[str]` | Detected event labels (open vocabulary) |
| `uncertainty_flags` | `list[str]` | Reasons the AI flagged for lower trust |
| `article_analyses` | `list[ArticleAnalysis]` | Per-article breakdown |

### `ArticleAnalysis`

| Field | Type | Description |
|---|---|---|
| `article_id` | `str` | Matches input `NewsArticle.article_id` |
| `direction` | `str` | Per-article direction |
| `relevance` | `float` | 0.0–1.0; how relevant the article is to the investment thesis |
| `horizon` | `str` | `"short"` / `"medium"` / `"long"` / `"unknown"` |
| `factual_summary` | `str` | One-sentence factual summary of this article |

---

## Serialisation to UI

`pipeline.py._serialise_ai_outcome()` converts the typed result to a UI dict for `stock.html`:

```python
# Status values
{"status": "not_run", "reason": "..."}       # no articles available
{"status": "unavailable", "reason": "..."}   # provider disabled or error
{"status": "available", "record_id": "...",  # successful analysis
 "provider": "...", "model": "...",
 "analysis": { ... }}                        # NewsAnalysis.model_dump(mode="json")
```

The `ai_overall_direction`, `ai_sentiment_score`, `ai_analysis_confidence`, and `ai_event_types` fields are separately surfaced from `DecisionResult` for display in the AI Evidence panel on `stock.html`.

---

## UI: AI Settings page (`/settings`)

The `/settings` route (`ui/app.py:232`) renders a provider selection form.

### Provider cards
Four cards: Disabled, Ollama (active), Claude (disabled — coming soon), ChatGPT (disabled — coming soon).

### Ollama section
- Base URL field (default `http://127.0.0.1:11434`)
- "Detect installed models" button — fetches `/api/ollama/models?base_url=...` → populates dropdown
- Model dropdown
- Timeout field (seconds)
- "Test connection" button — POSTs form to `/settings` then GETs `/api/ai/test`, displays result inline

### Save behaviour
`POST /settings` writes `ui/ai_settings.json` and calls `_CACHE.clear()` to bust the pipeline cache. The next stock lookup will run with the new model.

### API endpoints added to `ui/app.py`
| Endpoint | Method | Returns |
|---|---|---|
| `/settings` | GET | Settings form with current config |
| `/settings` | POST | Save + redirect |
| `/api/ollama/models` | GET | `{"models": [...], "count": N}` |
| `/api/ai/test` | GET | `{"status", "provider", "model", "direction", "confidence"}` |

---

## Examples

### Calling the service directly

```python
from datetime import datetime, timezone
from src.ai.models import NewsArticle, NewsAnalysisRequest
from src.ai.ollama import OllamaProvider
from src.ai.service import NewsAnalysisService, analyze_if_available

provider = OllamaProvider(model="qwen3:latest", base_url="http://127.0.0.1:11434", timeout_seconds=120)
service  = NewsAnalysisService(provider)

article = NewsArticle(
    article_id="a1",
    ticker="AAPL",
    headline="Apple beats Q3 earnings estimates, raises full-year guidance.",
    publisher="Reuters",
    url=None,
    published_at=datetime.now(timezone.utc),
    available_at=datetime.now(timezone.utc),
)
request = NewsAnalysisRequest(
    ticker="AAPL",
    decision_at=datetime.now(timezone.utc),
    articles=[article],
)

result = analyze_if_available(service, request)
# result is AuditedNewsAnalysis or AnalysisUnavailable

if hasattr(result, "analysis"):
    print(result.analysis.overall_direction)    # "positive"
    print(result.analysis.analysis_confidence)  # e.g. 0.88
    print(result.analysis.event_types)          # ["earnings_beat", "guidance_raise"]
```

### Reading provider settings in code

```python
import ui.ai_settings as ai_cfg

cfg = ai_cfg.load()
# cfg = {"provider": "ollama", "ollama_model": "qwen3:latest", ...}

service = ai_cfg.get_service()  # None if disabled or model not set

models = ai_cfg.list_ollama_models()  # [{"name": "qwen3:latest", "size_gb": 4.7}]

# Cache key includes provider+model so pipeline cache self-invalidates on model change
suffix = ai_cfg.cache_key_suffix()  # "ollama:qwen3:latest"
```

---

## How to run the tests

```bash
python3 -m pytest tests/test_ai/ -v
```

Tests mock the Ollama HTTP call — no running Ollama instance required.

**Note:** `tests/test_ai/conftest.py` had a pre-existing bug where a fixture was named `request`, which conflicts with pytest's built-in `request` fixture. It was renamed to `analysis_request` to fix test suite discovery.

---

## Design rules

**AI is advisory, not autonomous.**
It contributes evidence, not verdicts. The engine can downgrade based on AI evidence, but a human reviewing the `reasoning_trace` can see exactly what the AI said and why it triggered the downgrade.

**Every AI call is audited.**
`AuditStore` writes a SHA-256-keyed JSON file for every call. If a decision is questioned, the exact articles and AI response are retrievable from `logs/ai_audit/`.

**Provider-neutral contract.**
`AIProvider` is a Python `Protocol`. Adding a new provider (Claude, OpenAI) requires implementing `.analyse(request) -> ProviderResponse` — no changes to the engine or service layer.

**Cache invalidation is automatic.**
The pipeline cache key includes `cache_key_suffix()` which embeds `provider:model`. Switching models produces a cache miss immediately.

**Confidence is the AI's self-report, not a validated probability.**
`analysis_confidence` is the model's own estimate. It has not been calibrated against actual outcomes. The `_AI_DOWNGRADE_CONFIDENCE = 0.70` threshold is a starting point, not an empirically derived cutoff.

---

## Pending: Claude Haiku provider

The next planned step is implementing `AnthropicProvider` in `src/ai/anthropic_provider.py`. It mirrors `OllamaProvider` but calls the Anthropic messages API.

**Requirements:**
- `anthropic` Python package (add to `requirements.txt`)
- `ANTHROPIC_API_KEY` environment variable (from `console.anthropic.com`)
- Enable the Claude card in `ai_settings.html` (currently `disabled` with "coming soon")
- Update `ui/ai_settings.py:get_service()` to handle `provider == "claude"`

**Recommended model:** `claude-haiku-4-5-20251001` — fast (~2–5 s/call), low cost (~$0.001–0.003 per analysis), and higher quality than local qwen3 on CPU.

**Why Haiku over larger Claude models:** the analysis task is article classification, not synthesis. Haiku's speed advantage matters more than Opus-level reasoning for this use case.

---

## What is not in this module

| Concern | Where it lives |
|---|---|
| Fetching news articles | `src/sentiment/news.py` |
| Lexicon-based sentiment scoring | `src/sentiment/scorer.py` |
| BUY / WATCH / AVOID decision logic | `src/decision/engine.py` |
| Claude / OpenAI provider implementation | Not yet implemented |
| AI audit record querying or indexing | Not implemented |
| Lexicon vs AI accuracy comparison | Not implemented |
| Backtesting AI signals against price moves | Not implemented |
| Rate limiting / cost tracking for API providers | Not implemented |
