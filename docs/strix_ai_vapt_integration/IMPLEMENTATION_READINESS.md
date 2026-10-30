# STRIX + AI-VAPT — Implementation Readiness & Gap Analysis

**Prepared:** 2026-10-29  
**Workspace:** `/home/vinit/STRIX/strix` (only writable scope)  
**Reference:** `/home/vinit/AI_VAPT` (read-only)  
**Baseline commit:** `ef5d8100`  
**Authoritative plan:** `MASTER_INTEGRATED_PLAN.md` (this directory)

This document is the pre-implementation checkpoint. It records what already
exists, what is missing, which integration seams are safe, and which decisions
must be fixed before Phase 1 starts.

---

## 1. Verified Baseline

| Check | Result |
| :--- | :--- |
| Python (project venv) | `3.14.7`; `pyproject.toml` supports 3.12–3.14 |
| Docker daemon | Running, server `29.9.2` |
| Ollama | Running at `127.0.0.1:11434`; `qwen2.5:1.5b` installed |
| `pydantic` | `2.13.4` |
| `uvicorn` | `0.49.0` present |
| `starlette` | `1.3.1` present |
| `fastapi` | **Not installed** |
| Existing GAP bridge tests | `12 passed` (`tests/test_gap_bridge.py`) |

Git working tree is not clean. The following integration artifacts are
uncommitted/untracked and must be preserved:

- `strix/core/gap_bridge.py`
- `tests/test_gap_bridge.py`
- modifications to `strix/core/inputs.py` and `strix/tools/reporting/tool.py`
- `docs/strix_ai_vapt_integration/` (authoritative plan)
- `docs/ai_vapt_integration/` and `docs/AI_VAPT_STRIX_INTEGRATION_PLAN.md`
  (earlier, superseded planning artifacts)

---

## 2. Phase Readiness Matrix

| Phase | Status | Existing assets | Missing deliverables |
| :--- | :--- | :--- | :--- |
| **1 — Web console + FastAPI** | Not started | `uvicorn`, `starlette`, CLI dispatch seam, stdlib viewer | `strix/interface/api.py`, `schemas.py`, `web/` assets, `strix web` command, `fastapi` dependency |
| **2 — Multi-model routing** | Not started | LiteLLM + openai-agents stack, Ollama live | `strix/llm/router.py`, `ollama_service.py`, `provider_validation.py`, provider routes |
| **3 — GAP-1 triage** | Partial (bridge only) | Prompt queue injection + report-outcome hook | `strix/core/triage/` package, OWASP mapper, exploit assessor, native scoring, ingestion |
| **4 — GAP-2 pivoting** | Partial (bridge only) | Attempt counter, threshold, pivot guidance in tool result, JSONL trace | `strix/core/decision_engine/` package, explicit state machine, API trace exposure, loop interception |
| **5 — Scope + audit report** | Not started | `url_safety.py` (display safety only), strong report/SARIF pipeline | `strix/core/safety/`, validators, SHA-256 evidence envelope, audit HTML/JSON renderer, scope enforcement |
| **6 — End-to-end verification** | Not started | 12 bridge tests passing | Full smoke test across web → triage → pivot → report |

---

## 3. Integration Seams (verified)

| Concern | Seam | Location |
| :--- | :--- | :--- |
| Add `strix web` before scan parsing | `main()` dispatch | `strix/interface/main.py:446` |
| Root help text | `_ROOT_SUBCOMMAND_HELP` | `strix/interface/main.py:62` |
| Run entry point | `run_strix_scan(...)` | `strix/core/runner.py:215` |
| Per-run model override | `model=` argument | `strix/core/runner.py:227` |
| Live events / status | `event_sink`, `status_sink` | `strix/core/runner.py:229-235` |
| Root task construction | `build_root_task(...)` | `strix/core/inputs.py:187` |
| GAP-1 prompt injection (existing) | `gap1_instruction_block()` | `strix/core/inputs.py:190-197` |
| Finding creation / GAP-2 hook (existing) | `_attach_gap2(...)` | `strix/tools/reporting/tool.py:780` |
| Model resolution choke point | `StrixProvider.get_model` | `strix/config/models.py:613` |
| Memoized settings | `load_settings()` | `strix/config/loader.py:37` |
| Global report state | `get/set_global_report_state()` | `strix/report/state.py:186-190` |
| Finding persistence | `add_vulnerability_report(...)` | `strix/report/state.py:332` |
| SARIF export | `build_sarif_report(...)` | `strix/report/sarif.py:201` |
| Existing viewer server | stdlib HTTP server | `strix/interface/viewer/server.py:562` |
| Display-URL safety | `is_safe_web_url(...)` | `strix/interface/url_safety.py:11` |

---

## 4. Critical Findings & Risks

### 4.1 Concurrent web runs are unsafe
`ReportState` is a process-global singleton and `load_settings()` is memoized.
Two simultaneous scans would share findings, artifacts, and provider settings.

**Decision required:** start with a serialized single-worker run queue (one
active scan per console process), then introduce a per-run context object and
remove the globals. Do not advertise parallel scans before that refactor.

### 4.2 GAP-1 has no native candidate source
The existing bridge only consumes an externally produced `gap1_queue.json`.
The plan references `strix/core/triage/ingest.py` (README) but the master file
list omits it. Strix's agents do not expose a discrete vulnerability queue.

**Decision required:** define the queue contract. Recommended hybrid:
1. Native `Candidate` model + optional queue file ingestion.
2. Optional Nmap/Nuclei ingestion inside the sandbox.
3. Prompt injection + report-outcome hooks remain the enforcement points.
This preserves compatibility with the existing bridge and external control
plane while giving the console a typed candidate table.

### 4.3 GAP-2 cannot be enforced by prompt text alone
The current bridge records failures when `create_vulnerability_report` fails
validation and returns `pivot_guidance`. That is observable but advisory.
The plan's "terminate the subagent at k failures" requires a real hook in the
agent loop, which is invasive because Strix's agents act autonomously rather
than through a fixed candidate queue.

**Decision required:** implement a per-run `DecisionEngine` state machine and
emit `INIT/ADVANCE/RETRY/REDIRECT/ABANDON/COMPLETE` events. Enforce at:
- report-validation failures (already available),
- repeated tool failures / timeouts (new execution hook),
- explicit operator cancellation.
Keep prompt guidance as a defense-in-depth signal, not the only mechanism.

### 4.4 Scope gate conflicts with local lab and Docker targets
The README says block RFC 1918, loopback, CGNAT, and link-local unconditionally,
but Phase 5 allows loopback under a local lab profile, and Strix lab scans use
`host.docker.internal` / private container addresses.

**Decision required:** fail-closed default with an explicit engagement profile.
Allow `127.0.0.1`, `::1`, `host.docker.internal`, and configured private CIDRs
only when the profile explicitly authorizes them. Always block link-local
(`169.254.0.0/16`, `fe80::/10`) and cloud metadata endpoints. Persist the
authorized scope snapshot in `run.json`.

### 4.5 Runtime keys vs. memoized settings
Keys supplied in the UI must not touch `.env`, disk, or the memoized global
settings cache. Construct a per-run provider/model object with explicit
`api_key`/`api_base`, and ensure LiteLLM/openai-agents receive those values
per request. Verify that logs and `run.json` redact them.

### 4.6 Report pipeline should be extended, not duplicated
Strix already produces Markdown, JSON, CSV, and SARIF with a mature writer.
Porting AI-VAPT's report model wholesale would create a second source of truth.
Recommended: keep Strix's pipeline authoritative, add an evidence/audit envelope
(SHA-256, authorization snapshot, decision trace, OWASP/CWE) and generate the
AI-VAPT-style HTML audit report as an additional artifact.

### 4.7 Frontend surface is large
The AI-VAPT SPA is ~290 KB (`app.js` ~4,900 lines) and expects roughly 40
endpoints across runs, engagements, providers, scanners, reports, and Strix
adapters. Porting it wholesale without a compatibility layer will produce many
broken views.

**Decision required:** either (a) port the full SPA and implement core endpoints
with graceful "not available" responses for out-of-scope sections, or (b) trim
the SPA to the four Strix views (new assessment, live run/DAG, candidates,
reports). Recommended: (a) for visual parity, with a documented endpoint
support matrix, then prune later.

### 4.8 Missing dependency
`fastapi` is not installed. Add it to `pyproject.toml` (runtime dependency or a
`web` extra) and add `httpx` to the dev group for `ASGITransport` API tests.

### 4.9 Scoring formula is inconsistent across documents
Phase 3 specifies a weighted sum
`w1*P_base + w2*S_cvss + w3*E_exposure + w4*Q_ai`.
The AI-VAPT reference implements `probability * (0.5 + 0.5*quality_weight)`.
The README only calls it a "composite priority queue".

**Decision required:** implement the documented weighted sum with configurable
weights as the canonical score, and keep the AI-VAPT `priority_score` as a
secondary compatibility field.

### 4.10 Existing bridge state is process-global
`_attempts`, `_exhausted`, `_completed`, and `_announced` are module globals in
`gap_bridge.py`. This collides across runs. The native engine must be instantiated
per run, or the bridge must be reset at run start (currently no automatic reset).

---

## 5. Recommended Execution Order

1. **Phase 1 (foundation):** dependency + FastAPI app + static SPA + serialized
   run manager + health/validate/run/report endpoints + `strix web`.
2. **Phase 2 (models):** Ollama probe, provider validation, per-run router,
   wire model selection into `run_strix_scan`.
3. **Phase 5a (scope/evidence):** land the scope validator before any web run
   can dispatch. Add SHA-256 evidence envelope and authorization snapshot.
4. **Phase 3 (GAP-1):** typed candidates, OWASP mapping, exploit assessment,
   scoring, queue injection, API exposure.
5. **Phase 4 (GAP-2):** per-run decision engine, event trace, report/loop hooks,
   API/SSE exposure, DAG rendering.
6. **Phase 5b (audit report):** HTML/JSON/Markdown audit renderer and download
   routes on top of the existing report pipeline.
7. **Phase 6:** end-to-end smoke test and regression gate.

Rationale: the web console needs safe run dispatch before it can launch
anything; scope validation and concurrency control are prerequisites, not
polish.

---

## 6. Verification Gates (prepared)

```bash
# Baseline (passes now)
cd /home/vinit/STRIX/strix
.venv/bin/python -m pytest tests/test_gap_bridge.py -q

# Lint / types after each phase
uv run ruff check strix tests
uv run mypy strix

# Phase 1
uv run uvicorn strix.interface.api:app --host 127.0.0.1 --port 8000
curl -s http://127.0.0.1:8000/health
curl -s -I http://127.0.0.1:8000/ | head -1

# Phase 2
curl -s http://127.0.0.1:8000/system/health
curl -s -X POST http://127.0.0.1:8000/providers/google/validate \
  -H "X-Google-API-Key: <key>"

# Phase 3 / 4 / 5
uv run pytest tests/test_gap1_triage.py tests/test_gap2_pivoting.py \
  tests/test_scope_and_reporting.py -v
```

---

## 7. Guardrails for Every Phase

- Work only inside `/home/vinit/STRIX/strix`; never modify `/home/vinit/AI_VAPT`.
- Do not persist UI-supplied API keys to disk, `.env`, logs, or `run.json`.
- Do not allow a run to dispatch before target validation succeeds.
- Do not let a failed candidate exceed the configured threshold.
- Do not fabricate evidence; unfreeze/report only observed responses, and hash
  the raw bytes that were observed.
- Keep CLI-only behavior unchanged when the web console is not used.
- Add tests for every new behavior; keep the 12 existing bridge tests green.
