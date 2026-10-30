# Phase 2: Multi-Model Configuration & Runtime Provider Routing

## 1. Objective

Enable dynamic, zero-restart configuration of **Local Models (Ollama)** and **Hosted Cloud APIs (Google Gemini, OpenRouter, OpenAI)** directly from the Strix Web Console.

> **CRITICAL RULE:** All modifications and new files are created **strictly inside `/home/vinit/STRIX/strix`**. The code in `/home/vinit/AI_VAPT` is only copied and adapted.

---

## 2. Target File Structure in STRIX

```
/home/vinit/STRIX/strix/
├── strix/
│   ├── llm/
│   │   ├── router.py                 # NEW: Dynamic multi-provider model router
│   │   ├── ollama_service.py         # NEW: Local Ollama probe and structured query helper
│   │   ├── openrouter_service.py     # NEW: OpenRouter catalogue validation & key testing
│   │   └── google_service.py         # NEW: Gemini API key validation & model resolution
│   ├── config/
│   │   └── models.py                 # UPDATED: Bridge runtime context to LiteLLM / openai-agents
│   └── interface/
│       └── api.py                    # UPDATED: Validation routes for Google, OpenRouter, and Ollama
```

---

## 3. Technical Implementation Specification

### Step 2.1: Implement Local Ollama Prober (`strix/llm/ollama_service.py`)
Port and adapt from `AI_VAPT/vapt_platform/ollama_service.py`:
- `probe_ollama(model_name: str) -> dict`: Probes `http://127.0.0.1:11434/api/tags` to check if Ollama is reachable and returns the list of installed models (`ollama_models`).
- `query_ollama_structured(...) -> dict`: Issues synchronous or asynchronous completions to Ollama with structured JSON outputs.

### Step 2.2: Implement Hosted Provider Services (`google_service.py`, `openrouter_service.py`)
- **Google Gemini Validator**:
  - Endpoint: `POST /providers/google/validate` (reads `X-Google-API-Key` header).
  - Tests credential against Google Gemini's `https://generativelanguage.googleapis.com/v1beta/models?key=...`.
  - Confirms key validity and returns active models (`gemini-2.0-flash`, `gemini-flash-lite-latest`).
- **OpenRouter Validator**:
  - Endpoint: `POST /providers/openrouter/validate` (reads `X-OpenRouter-API-Key` header).
  - Issues an authenticated request to `https://openrouter.ai/api/v1/models` (costs zero credits).
  - Validates key and returns compatible model ids.

### Step 2.3: Ephemeral In-Memory Credential Bridge (`strix/llm/router.py`)
In Strix, `litellm` is used for LLM completions. We create a dynamic runtime wrapper:
```python
class RuntimeLLMConfig:
    provider: Literal["ollama", "google", "openrouter", "openai"]
    model_name: str
    runtime_api_key: Optional[str] = None  # Ephemeral: lives only for the assessment run

def get_litellm_kwargs(config: RuntimeLLMConfig) -> dict:
    """Translate UI model selection to LiteLLM parameters."""
    if config.provider == "ollama":
        return {
            "model": f"ollama/{config.model_name}",
            "api_base": os.environ.get("OLLAMA_API_BASE", "http://127.0.0.1:11434"),
        }
    elif config.provider == "google":
        return {
            "model": f"gemini/{config.model_name}",
            "api_key": config.runtime_api_key or os.environ.get("GEMINI_API_KEY"),
        }
    elif config.provider == "openrouter":
        return {
            "model": f"openrouter/{config.model_name}",
            "api_key": config.runtime_api_key or os.environ.get("OPENROUTER_API_KEY"),
        }
    ...
```

### Step 2.4: Update Frontend Model Selector (`strix/interface/web/js/app.js`)
- The UI contains dropdowns for:
  - **Provider**: `Local Ollama`, `Google Gemini`, `OpenRouter`, `OpenAI`.
  - **Model Dropdown**: Populated dynamically with supported models for that provider.
  - **In-Memory Setup Panels**: Google and OpenRouter setup cards appear when selected, allowing the user to paste their key, click "Validate Connection", and run without saving to `.env`.

---

## 4. Agent Development Prompt for Phase 2

```markdown
# TASK: Phase 2 — Multi-Model Configuration & Runtime Provider Routing in STRIX

## Strict Boundaries
- Work EXCLUSIVELY inside `/home/vinit/STRIX/strix`.
- DO NOT edit any files in `/home/vinit/AI_VAPT`. Read files from `/home/vinit/AI_VAPT` as read-only reference.

## Objective
Implement dynamic model routing inside STRIX so that operators can select Local Ollama (`qwen2.5:1.5b`), Google Gemini, or OpenRouter from the web interface, validate their credentials in real-time, and execute runs without restarting Strix or editing `.env`.

## Detailed Tasks
1. Port `/home/vinit/AI_VAPT/vapt_platform/ollama_service.py` into `/home/vinit/STRIX/strix/strix/llm/ollama_service.py`.
   - Ensure `probe_ollama()` checks `http://127.0.0.1:11434/api/tags` and lists installed models.
2. Port OpenRouter and Google validation logic from `/home/vinit/AI_VAPT/vapt_platform/openrouter_setup.py` and `services/api.py` into `/home/vinit/STRIX/strix/strix/llm/provider_validation.py`.
3. Create `/home/vinit/STRIX/strix/strix/llm/router.py`:
   - Map `(provider, model_name, runtime_key)` into LiteLLM call arguments.
   - For `ollama`: point to `http://127.0.0.1:11434`.
   - For `google`: map to `gemini/<model>` with the ephemeral `X-Google-API-Key`.
   - For `openrouter`: map to `openrouter/<model>` with `X-OpenRouter-API-Key`.
4. Update `strix/interface/api.py`:
   - Add route `POST /providers/google/validate`: accepts `X-Google-API-Key` header, tests against Gemini API, returns status.
   - Add route `POST /providers/openrouter/validate`: accepts `X-OpenRouter-API-Key` header, tests against OpenRouter models endpoint, returns status.
   - Update `GET /system/health` to query `probe_ollama()` and report real-time Ollama status and installed models.
5. In `strix/interface/web/js/app.js`: Ensure the frontend Google Gemini setup panel and OpenRouter setup panel dispatch to these endpoints.
6. Verify live inference using a test script for both Ollama (`qwen2.5:1.5b`) and hosted APIs.
```

---

## 5. Verification & Testing Commands

```bash
# 1. Start the Strix Web Gateway
cd /home/vinit/STRIX/strix
uv run uvicorn strix.interface.api:app --host 127.0.0.1 --port 8000

# 2. Test Ollama Model Auto-Detection via /system/health
curl -s http://127.0.0.1:8000/system/health | grep -o '"ollama":"READY"'
# Expected: "ollama":"READY"

# 3. Test Google Gemini Key Validation
curl -s -X POST http://127.0.0.1:8000/providers/google/validate \
  -H "X-Google-API-Key: YOUR_TEST_KEY"
# Expected: {"valid":true,"status":"configured",...}

# 4. Test OpenRouter Key Validation
curl -s -X POST http://127.0.0.1:8000/providers/openrouter/validate \
  -H "X-OpenRouter-API-Key: YOUR_TEST_KEY"
# Expected: {"valid":true,"status":"configured",...}

# 5. Test Live Local Inference through Strix Router
uv run python -c "
from strix.llm.router import run_completion
res = run_completion('qwen2.5:1.5b', provider='ollama', prompt='Explain SQL injection in one sentence.')
print('Completion:', res)
"
# Expected: Genuine completion from local qwen2.5:1.5b
```

