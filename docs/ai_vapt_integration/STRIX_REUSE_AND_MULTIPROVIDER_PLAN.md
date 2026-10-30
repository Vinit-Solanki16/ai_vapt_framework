# Plan: Reusing AI_VAPT on Strix + Multi-Provider AI Support

## 1. Project Overview

### Strix (`/home/vinit/STRIX/strix`)
- **CLI pentesting tool** (Python 3.12+, `uv`-managed). Entry: `strix.interface.main:main`
- **AI via LiteLLM / OpenAI Agents SDK** — already supports any LiteLLM model id (OpenAI, Anthropic, Google, OpenRouter, Ollama, etc.) via `STRIX_LLM` + `LLM_API_KEY`/`LLM_API_BASE`
- **Two UIs**: (a) Go/Bubble Tea TUI (needs Go compiler or packaged `strix-tui` binary — absent here), (b) React/Vite viewer SPA served by `strix view <run>` (stdlib HTTP, token-authed)
- **Output**: `strix_runs/<run>/` with `run.json`, `vulnerabilities.json`, SARIF, Markdown report
- **Sandbox**: Docker image `ghcr.io/usestrix/strix-sandbox:1.3.0` (Kali-based, 5.9 GB)

### AI_VAPT (`/home/vinit/AI_VAPT`)
- **Research framework** (Python 3.10, FastAPI + Streamlit + vanilla JS SPA)
- **GAP-1**: AI-informed candidate ranking — assess exploit quality *before* ranking (`assess → rank → decide`)
- **GAP-2**: Bounded failure-threshold pivoting — per-candidate attempt counters, pivot after N failures (`T ≤ N·|C|`)
- **Multi-provider**: ollama, openrouter, openai, google (via `vapt_platform/model_config.py` + `core/exploit_assessor.py`)
- **Runtime key setup**: In-memory only, header-based (`X-OpenRouter-API-Key`, `X-Google-API-Key`), validate-then-use flow
- **Modular validators**: 5 non-destructive validators (phpinfo, headers, cookies, files, technology) with `ValidatorRegistry`
- **Controlled web executor**: `web_executor.py` maps validators → decision engine `Executor` contract
- **Multi-format reporting**: JSON/HTML/Markdown/TXT + cryptographic manifest
- **Frontend**: Vanilla JS SPA (`frontend/web/index.html` + `app.js`) served by FastAPI; Streamlit dashboard (`frontend/app.py`)

## 2. GAP-1 & GAP-2: Current State and Improvements

### GAP-1: AI-Informed Candidate Ranking (Current)
**What it does**: Assesses exploit quality via LLM *before* ranking, so `P(Action) × Q(Usability)` prioritizes high-quality exploits.

**Current limitation**: Only scores candidates that already exist from scanners; doesn't generate new candidates from AI reasoning.

**Improvement ideas**:
- Add **AI-suggested attack paths**: LLM proposes candidate mutations (e.g., "try CVE-2021-44228 with JNDI variant") that enter the candidate queue with lower initial probability
- **Cross-model consensus**: Run 2-3 providers in parallel, average quality ranks, flag disagreements as "needs human review"
- **Feedback loop**: After execution, feed outcome back into a fine-tuning dataset so future assessments improve
- **Explainability**: Store `reasoning` + `confidence` per candidate in the report; add a "why this rank?" expandable in the UI
- **Adaptive thresholds**: If GAP-1 consistently over-ranks a candidate type, auto-adjust the assessor prompt

### GAP-2: Bounded Failure-Threshold Pivoting (Current)
**What it does**: Per-candidate attempt counter; when `attempts ≥ N`, pivot to next candidate. Prevents infinite loops.

**Current limitation**: Only pivots linearly (candidate i → i+1); doesn't learn from failure patterns.

**Improvement ideas**:
- **Smart pivot ordering**: Instead of sequential, pivot to the candidate most *similar* to the failed one (same service/CVE family) but with a different exploit technique
- **Failure classification**: Distinguish `FAIL_TIMEOUT` (retry with longer timeout) vs `FAIL_SYNTAX` (abandon) vs `FAIL_DEPENDENCY` (try alternative payload) — currently all increment the same counter
- **Pivot budget visualization**: Show remaining attempts and pivot count in real-time in the UI dashboard
- **Adaptive N**: Start with N=2, increase to N=3 if early candidates all fail (exploratory mode), decrease to N=1 in time-constrained mode
- **Pivot history in reports**: Include a decision-trace table showing each pivot, reason, and candidate transition

## 3. How to Reuse AI_VAPT on Strix

### 3.1 Architecture: Strix as Engine, AI_VAPT as Control Plane

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI_VAPT Control Plane                        │
│  (FastAPI + vanilla JS SPA + Streamlit)                         │
│                                                                 │
│  • Scope authorization (web_target.py, engagements.py)          │
│  • Multi-provider AI setup (model_config.py, assessment.py)     │
│  • Modular validators (validators/)                             │
│  • GAP-1/GAP-2 decision engine (decision_engine/)               │
│  • Multi-format reporting (reporting/)                          │
│  • Event bus + persistence (events/, persistence/)              │
└──────────────────────┬──────────────────────────────────────────┘
                       │  StrixWorkerAdapter
                       │  invokes: strix -t <target> -n -m quick
                       │          --max-turns 3 --max-budget 0.50
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Strix Worker (Docker)                         │
│  • Autonomous multi-agent pentest (recon, exploit, validate)     │
│  • Docker sandbox (Kali, Caido proxy)                           │
│  • Output: vulnerabilities.json, SARIF, Markdown report         │
└──────────────────────┬──────────────────────────────────────────┘
                       │  retrieve_findings() → NormalizedExternalFinding
                       │  tagged as SCANNER_DETECTED_CANDIDATE
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│              AI_VAPT Candidate Pipeline                         │
│  • Strix findings → normalize → enrich (EPSS/CVSS/KEV)         │
│  • GAP-1: assess quality → rank by priority                     │
│  • GAP-2: validate with modular validators → pivot on failure    │
│  • Report with evidence tier OBSERVED_EXTERNAL                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Reuse Points

| AI_VAPT Component | How to Reuse in Strix Context |
|---|---|
| `vapt_platform/model_config.py` | Add as Strix plugin for provider/model management; Strix already supports LiteLLM but lacks runtime key UI |
| `vapt_platform/assessment.py` | Wrap Strix's LLM calls with GAP-1 assessment layer; Strix has no pre-execution quality scoring |
| `vapt_platform/validators/` | Use as Strix's validation layer instead of Strix's built-in (which is prompt-based only) |
| `vapt_platform/web_executor.py` | Map Strix findings to decision engine candidates for GAP-2 pivoting |
| `vapt_platform/reporting/` | Replace Strix's Markdown-only report with multi-format (JSON/HTML/MD/TXT/manifest) |
| `vapt_platform/web_target.py` | Use as Strix's scope enforcement (Strix has NO programmatic scope filter) |
| `frontend/web/` (vanilla JS SPA) | Embed in Strix viewer or replace Strix's React viewer |
| `services/api.py` | Add Strix adapter endpoints (`/adapters/strix/status`, `/adapters/strix/run`) |
| `decision_engine/` | Wrap Strix's agent loop with GAP-1/GAP-2 for bounded, explainable execution |

### 3.3 Key Integration: Strix Scope Enforcement

Strix's critical weakness: scope is enforced **only via system prompts** (no programmatic filter). AI_VAPT's `web_target.py` provides:
- DNS resolution + IP validation
- Allowlist enforcement (host:port exact match)
- External target acknowledgement
- Redirect blocking outside scope

**Action**: Wrap every Strix invocation with AI_VAPT's `validate_web_target()` before launching.

## 4. Multi-Provider AI Model Support

### Current State
- **Strix**: Uses LiteLLM via OpenAI Agents SDK. Supports any model via `STRIX_LLM` env var (e.g., `openrouter/...`, `anthropic/...`, `openai/...`, `gemini/...`, `ollama/...`). No runtime key UI.
- **AI_VAPT**: Supports ollama, openrouter, openai, google. Has runtime key setup for OpenRouter and Google. Missing: **Anthropic** as a direct provider.

### Required Changes

#### A. Add Anthropic Provider to AI_VAPT

**Files to modify**:
1. `vapt_platform/model_config.py`: Add `DEFAULT_ANTHROPIC_MODEL`, `ANTHROPIC_MODELS`, `"anthropic"` to `KNOWN_PROVIDERS`, `PROVIDER_LABELS`, `PROVIDER_API_KEY_ENV` (`ANTHROPIC_API_KEY`), `default_anthropic_model_from_env()`, update `models_for_provider()`, `default_model_for()`, `api_key_env_for()`
2. `core/exploit_assessor.py`: Add `from langchain_anthropic import ChatAnthropic` (guarded import), add `elif provider == "anthropic":` branch in `get_llm()`
3. `vapt_platform/assessment.py`: Add `_try_anthropic_assess()`, add `elif provider == "anthropic":` in `create_assessor()`, add Anthropic to fail-fast key check
4. `services/api.py`: Add `X-Anthropic-API-Key` header to `start_run()`, add `/providers/anthropic/validate` endpoint, add `AnthropicValidateResponse` schema
5. `services/schemas.py`: Add `"anthropic"` to `assessor_provider` Literal, add `AnthropicValidateResponse` model
6. `frontend/web/js/app.js`: Add `anthropic` to `PROVIDER_MODELS`, `PROVIDER_NOTES`, add Anthropic setup panel
7. `frontend/app.py` (Streamlit): Add Anthropic to provider selectbox, add Anthropic setup panel
8. `.env.example`: Add `ANTHROPIC_API_KEY` section

#### B. Strix Multi-Provider Runtime Key UI

Strix currently has no runtime key UI. To support runtime keys (like AI_VAPT):
- Add a `/providers/{provider}/validate` endpoint to Strix's viewer server or a new management API
- Add provider setup panel to Strix's viewer SPA
- Store runtime keys in-memory (session-scoped, never persisted)

#### C. Unified Provider Registry

```python
# vapt_platform/model_config.py (extend existing)
KNOWN_PROVIDERS = ("ollama", "openrouter", "openai", "google", "anthropic", "local")

PROVIDER_API_KEY_ENV = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
```

## 5. Implementation Plan (Phased)

### Phase 0: Baseline (DONE)
- Strix installed and running (v1.7.0)
- Docker sandbox image pulled
- AI_VAPT tests passing (1057)
- Ollama available with qwen2.5:1.5b

### Phase 1: Add Anthropic Provider to AI_VAPT
- **Files**: model_config.py, core/exploit_assessor.py, assessment.py, services/api.py, services/schemas.py, frontend (JS + Streamlit)
- **Tests**: Add `test_anthropic_provider.py`
- **Effort**: 8 hours

### Phase 2: Strix Scope Enforcement Wrapper
- **New file**: `vapt_platform/adapters/strix_scope_wrapper.py`
- **Purpose**: Wrap Strix CLI invocations with AI_VAPT's `validate_web_target()`
- **Tests**: `test_strix_scope_wrapper.py`

### Phase 3: Strix Worker Adapter (Phase 4 from External Plan)
- **New files**: `vapt_platform/adapters/strix_adapter.py`, `vapt_platform/adapters/base.py`, `vapt_platform/adapters/registry.py`
- **Purpose**: Invoke Strix headless, parse `vulnerabilities.json`, normalize to `NormalizedExternalFinding`
- **Tests**: `test_strix_adapter.py`

### Phase 4: Strix Findings → AI_VAPT Candidate Pipeline
- **Modify**: `vapt_platform/application.py` to accept Strix findings as candidates
- **Purpose**: Strix findings flow through GAP-1 (assess) → GAP-2 (validate/pivot)
- **Tests**: `test_strix_candidate_integration.py`

### Phase 5: Strix Viewer Enhancement with AI_VAPT Frontend
- **Option A**: Embed AI_VAPT's vanilla JS SPA into Strix's viewer as a separate tab/panel (recommended)
- **Option B**: Replace Strix's React viewer with AI_VAPT's SPA (more work, better integration)

### Phase 6: Strix Multi-Provider Runtime Key UI
- **Modify**: Strix's viewer server + SPA
- **Purpose**: Allow runtime API key entry (like AI_VAPT) instead of env-only

### Phase 7: Enhanced GAP-1 & GAP-2 (Make More Useful)
- **GAP-1 enhancements**: AI-suggested attack paths, cross-model consensus, feedback loop, explainability, adaptive thresholds
- **GAP-2 enhancements**: Smart pivot ordering, failure classification, adaptive N, pivot visualization, pivot history in reports
- **Files**: `decision_engine/core/assessor.py`, `decision_engine/core/engine.py`, `vapt_platform/decision_intelligence.py`

## 6. File Change Summary

### New Files
| File | Purpose |
|---|---|
| `vapt_platform/adapters/base.py` | `ExternalEngineAdapter` ABC, `ResultSemantic`, `NormalizedExternalFinding` |
| `vapt_platform/adapters/registry.py` | Adapter manager singleton |
| `vapt_platform/adapters/strix_adapter.py` | Strix worker adapter |
| `vapt_platform/adapters/strix_scope_wrapper.py` | Scope enforcement wrapper |
| `vapt_platform/security/prompt_shield.py` | Prompt injection defense |
| `tests/test_strix_adapter.py` | Strix adapter tests |
| `tests/test_anthropic_provider.py` | Anthropic provider tests |

### Modified Files
| File | Change |
|---|---|
| `vapt_platform/model_config.py` | Add Anthropic provider |
| `core/exploit_assessor.py` | Add Anthropic LLM construction |
| `vapt_platform/assessment.py` | Add `_try_anthropic_assess()`, fail-fast check |
| `services/api.py` | Add Anthropic header + validate endpoint |
| `services/schemas.py` | Add Anthropic to Literal, `AnthropicValidateResponse` |
| `frontend/web/js/app.js` | Add Anthropic provider UI |
| `frontend/app.py` | Add Anthropic to Streamlit |
| `.env.example` | Add `ANTHROPIC_API_KEY` |
| `vapt_platform/application.py` | Integrate Strix findings into candidate pipeline |

## 7. Commands to Run

### Start AI_VAPT (existing)
```bash
cd /home/vinit/AI_VAPT
source .venv/bin/activate
VAPT_AUTHORIZED_WEB_SCOPES=pentest-ground.com:4280 uvicorn services.api:app --reload --port 8000
# Open http://localhost:8000
```

### Start Strix (existing)
```bash
cd /home/vinit/STRIX/strix
export STRIX_LLM="ollama/qwen2.5:1.5b"
export LLM_API_BASE="http://127.0.0.1:11434"
export LLM_API_KEY="ollama"
uv run strix -n -t http://127.0.0.1:9191 --scan-mode quick --max-budget 5
```

### After Integration (future)
```bash
# Run Strix as AI_VAPT worker
cd /home/vinit/AI_VAPT
python -m vapt_cli run --target-url http://127.0.0.1:9191 --engine strix --max-budget 0.50

# View Strix findings in AI_VAPT dashboard
# Open http://localhost:8000 → Findings → filter by source: strix
```

## 8. Testing Strategy

- **Frozen core**: `decision_engine/core/` must never be modified; tests must pass
- **Provider tests**: Mock HTTP transport for all providers (no real API calls)
- **Scope tests**: Verify Strix can't scan out-of-scope targets
- **Provenance tests**: Verify Strix findings are tagged `SCANNER_DETECTED_CANDIDATE` / `OBSERVED_EXTERNAL`
- **Secret tests**: Verify API keys never appear in logs/reports/persistence

## 9. Risk Mitigations

| Risk | Mitigation |
|---|---|
| Strix dependency conflicts (pydantic, langchain) | Run Strix in Docker container only; never install in AI_VAPT venv |
| Strix scope bypass (prompt-only enforcement) | Wrap with AI_VAPT's `validate_web_target()` before launch |
| OOM in Codespace (Strix Kali image 5-15 GB) | Use `--scan-mode quick`, `--max-turns 3`, `--max-budget 0.50` |
| AGPL contamination (Shannon) | Never copy Shannon code; use REST boundary |
| Research integrity (GAP-1/GAP-2) | Freeze `decision_engine/core/`; CI checks for zero diffs |