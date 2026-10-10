# Autonomous AI VAPT Framework

State-aware Vulnerability Assessment & Penetration Testing with **Exploit Quality
Scoring** and **Dynamic Decision-Pivoting** (LangGraph). Built for an M.Tech
cybersecurity thesis. Runs fully offline via local Ollama (no API cost).

## Research Contributions

### GAP-1: AI-Informed Candidate Ranking
AI/LLM assessment of exploit quality occurs BEFORE candidate ranking and
influences attack-path prioritization.

### GAP-2: Bounded Failure-Threshold Pivoting
The system maintains per-candidate attempt state, detects repeated failures,
and dynamically pivots after a configurable failure threshold.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INTERFACES                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  Streamlit   │  │   FastAPI    │  │     CLI      │              │
│  │  frontend/   │  │  services/   │  │  prototype/  │              │
│  │  app.py      │  │  api.py      │  │  cli.py      │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         └─────────────────┼─────────────────┘                       │
│                           ▼                                         │
│              ┌─────────────────────────┐                            │
│              │    VAPTApplication      │                            │
│              │  vapt_platform/         │                            │
│              │  application.py         │                            │
│              └───────────┬─────────────┘                            │
│                          │                                          │
│  ┌───────────────────────┼───────────────────────┐                  │
│  │                       ▼                       │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │         DECISION ENGINE (FROZEN)        │  │                  │
│  │  │  decision_engine/core/                  │  │                  │
│  │  │  GAP-1: assess → rank → decide         │  │                  │
│  │  │  GAP-2: attempt → count → pivot        │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  │                                               │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │      VAPT RESEARCH CORE (FROZEN)        │  │                  │
│  │  │  core/                                  │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  │                                               │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │           PLATFORM SERVICES             │  │                  │
│  │  │  vapt_platform/                         │  │                  │
│  │  │  enrichment, normalization, scanners    │  │                  │
│  │  │  authorization, pipeline, persistence  │  │                  │
│  │  │  events, reporting                      │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  │                                               │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │         PROTOTYPE LAYER                 │  │                  │
│  │  │  prototype/                             │  │                  │
│  │  │  execution_layer, lab_runner, demo_data │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  │                                               │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │         DOCKER LAB                      │  │                  │
│  │  │  lab/                                   │  │                  │
│  │  │  docker-compose.yml, emulator, executor │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  └───────────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Setup

```bash
cd ~/ai_vapt_framework
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Optional: Start Ollama for AI assessment
ollama serve &
ollama pull llama3.2:3b
```

### Run

```bash
# 1) CLI — run a scenario
python -m prototype.cli run --scenario failure_pivot --mode simulation

# 2) Web dashboard
streamlit run frontend/app.py

# 3) API
uvicorn services.api:app --reload --port 8000

# 4) Run tests
python -m pytest tests/ -q
```

## Assessment Providers

Provider and model selection is explicit and lives in one place —
`vapt_platform/model_config.py`. Nothing here is ever chosen implicitly.

| Provider | Type | Default model | Key env var |
|----------|------|---------------|-------------|
| `ollama` (default) | local / offline | `llama3.2:3b` (thesis baseline) | none |
| `openrouter` | hosted API, **opt-in** | `meta-llama/llama-3.3-70b-instruct` | `OPENROUTER_API_KEY` |
| `openai` | hosted API, **opt-in** | `gpt-4o-mini` | `OPENAI_API_KEY` |

```bash
export OPENROUTER_API_KEY=sk-or-...          # opt in to the hosted arm
export OPENROUTER_MODEL=vendor/custom-model  # optional override
streamlit run frontend/app.py
```

### Runtime key setup — configure OpenRouter from the GUI

You do **not** have to create a Codespaces secret, edit `.env`, or restart
either frontend. Both UIs accept the key at runtime:

- **Web UI** — select `openrouter` as the provider; the *OpenRouter Setup*
  panel appears with a masked key field, a model selector, and
  **Validate Connection** / **Use OpenRouter** / **Forget Key**.
- **Streamlit** — select `openrouter` in the sidebar; the same controls appear
  under *OpenRouter Setup*.

Validation issues a single **authenticated model-catalogue request**
(`GET /api/v1/models/user`, falling back to `GET /api/v1/auth/key` +
`GET /api/v1/models` when a non-management key is rejected with 403). It never
sends a completion, so checking a credential costs nothing and cannot spend
credit. The same round trip returns the live model catalogue, sorted
free-first, so availability is never guessed.

| Status | Meaning |
|--------|---------|
| `not_configured` | No key in this session yet |
| `configured` | Validated for this session |
| `invalid_credentials` | OpenRouter returned 401 (or the pasted key has stray whitespace) |
| `model_unavailable` | The selected model is not in the current catalogue |
| `rate_limited` | 429 — wait and retry |
| `unreachable` | Network/timeout/server error — **not** a bad key |
| `validating` | Transient, client-side |

**Security properties**

- The key is held **in memory only**: module/session scope in the web UI,
  `st.session_state` in Streamlit. It is never written to
  `localStorage` / `sessionStorage` / IndexedDB / cookies / the URL, never to
  `.env`, never to `os.environ`, and never to a run record, report, health
  response, event or log.
- It travels **browser → your own backend → OpenRouter** as the
  `X-OpenRouter-API-Key` request header — never inside the JSON body, so a
  logged or replayed request payload contains no secret.
- **Forget key** drops it from the session outright. A page reload starts a
  fresh session, so the key is asked for again — by design.
- A run will not start on an unvalidated credential: the setup panel is
  revealed with an actionable message instead. Providers are never switched
  silently.
- No CORS, authentication or network-exposure behaviour was changed to make
  this work.

**Free models.** A model counts as free only when the catalogue's
`pricing.prompt` and `pricing.completion` are both `"0"` — never inferred from
a `:free` name suffix. Free entries are listed first and the default is
`openrouter/free` (the Free Models Router) when present, otherwise the first
free model. **A paid model is never selected implicitly**; picking one shows an
explicit pricing warning. Free availability and quotas change without notice.

`OPENROUTER_API_KEY` remains supported as a server-wide fallback for shared or
headless deployments. When a session key is present it takes precedence for
that run only.

**Missing-key behaviour differs by provider — this difference is intentional.**

- `openrouter` raises `RuntimeError` at construction time, naming the missing
  variable and the offline alternative. An explicit opt-in choice must fail
  loudly rather than silently produce deterministic results.
- `openai` keeps its **legacy** semantics: a missing key does not raise here.
  The client build fails, the assessor catches it, and the result is an
  explicitly tagged deterministic fallback (`fallback=True`, provider
  `openai`). Changing this would alter pre-existing behaviour.
- `ollama` is local and needs no key.

**A hosted failure never dispatches to a different provider.** The selected
provider is always the one named in the result provenance.

**Reports distinguish success from fallback.** Web-assessment provenance
records an `ai.outcome` of `MODEL ASSESSED`, `DETERMINISTIC FALLBACK`,
`PARTIAL (n of m fell back)` or `NOT RECORDED`, so an exported report never
implies the model answered when the deterministic assessor produced the rank.

**Tuning knobs are bounded.** `OPENROUTER_TIMEOUT_S` clamps to `1..600`
seconds and `OPENROUTER_MAX_RETRIES` to `0..5`, so a typo cannot create an
unbounded retry loop or a multi-hour hang. Values outside the range fall back
to the default.

**Model names are validated, not allowlisted.** Any well-formed
`vendor/model` slug is accepted so `OPENROUTER_MODEL` stays configurable; a
name containing whitespace or control characters (or longer than 200
characters) raises `ValueError`. The provider itself is the authority on
whether a slug exists, and answers with a classified `not_found`.

OpenRouter runs are a separate, clearly-labelled arm. They are never merged
into, compared against, or substituted for the historical Ollama/`llama3.2:3b`
baseline experiments.

## Evidence Tiers

| Tier | Description |
|------|-------------|
| **SIMULATED** | Outcomes from ground-truth labels (`labels.json`) |
| **OBSERVED_LOCAL** | Real HTTP to loopback (127.0.0.1) |
| **DOCKER_OBSERVED** | Real HTTP to isolated Docker emulator |
| **CONTROLLED_VALIDATION** | Real execution against live targets |

## Research Integrity

### GAP-1: Assessment Before Ranking

```python
# decision_engine/core/engine.py:initial_state()
if assess_fn:
    assess_candidates(raw_candidates, assess_fn=assess_fn)  # Assess FIRST
cs = rank_candidates(raw_candidates)  # THEN rank
```

### GAP-2: Bounded Pivot

```python
# decision_engine/core/engine.py:_evaluate()
if state["attempt_count"] >= state["max_attempts"]:
    return "pivot"  # Threshold reached → pivot
```

## Project Structure

```
ai_vapt_framework/
├── core/                    # VAPT research core (FROZEN)
├── decision_engine/         # Domain-independent engine (FROZEN)
├── vapt_platform/           # Platform services
├── prototype/               # Prototype layer (executors, demo data)
├── frontend/                # Streamlit dashboard
├── services/                # FastAPI backend
├── lab/                     # Docker lab
├── tests/                   # Test suite (545 tests)
├── data/                    # Datasets and PoC corpus
├── docs/                    # Documentation
└── experiments/             # Research experiments
```

## Honest Limitations

- **SIMULATION mode** uses ground-truth labels, not live exploitation
- **DOCKER_OBSERVED** requires Docker Desktop (not available in all environments)
- **AI assessment** requires local Ollama (deterministic fallback available)
- **No external targets** — only allowlisted lab targets are permitted

## Documentation

- [Current State Audit](docs/project_management/CURRENT_STATE_AUDIT.md)
- [Research Core Protection](docs/project_management/RESEARCH_CORE_PROTECTION.md)
- [Mentor Demo](docs/project_management/MENTOR_DEMO.md)
- [Current Architecture](docs/architecture/CURRENT_ARCHITECTURE.md)
- [Known Limitations](docs/project_management/KNOWN_LIMITATIONS.md)
