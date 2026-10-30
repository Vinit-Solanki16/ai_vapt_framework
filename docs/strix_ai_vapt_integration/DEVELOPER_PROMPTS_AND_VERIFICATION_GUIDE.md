# Strix AI-VAPT Integration: Developer Prompts & Verification Guide

This document is the execution runbook for implementing the AI-VAPT features inside **STRIX**.  
Each phase below contains a **ready-to-use Agent Prompt** that can be directly passed to an autonomous AI coding assistant, followed by exact **verification commands**.

> **STRICT SCOPE RULE:** All changes occur **EXCLUSIVELY inside `/home/vinit/STRIX/strix`**.  
> The directory `/home/vinit/AI_VAPT` is read-only reference. **Never modify files in `/home/vinit/AI_VAPT`.**

---

## Quick Navigation

1. [Phase 1: Frontend Web Console & FastAPI Gateway](#phase-1-frontend-web-console--fastapi-gateway)
2. [Phase 2: Multi-Model Configuration & Provider Routing](#phase-2-multi-model-configuration--provider-routing)
3. [Phase 3: GAP-1 Exploit Quality Scoring & Prioritization](#phase-3-gap-1-exploit-quality-scoring--prioritization)
4. [Phase 4: GAP-2 Dynamic Decision-Pivoting Engine](#phase-4-gap-2-dynamic-decision-pivoting-engine)
5. [Phase 5: Audit Reporting, Cryptographic Proof & Scope Safeguards](#phase-5-audit-reporting-cryptographic-proof--scope-safeguards)
6. [Master End-to-End Verification](#master-end-to-end-verification)

---

## Phase 1: Frontend Web Console & FastAPI Gateway

### Development Agent Prompt
```markdown
# TASK: Implement Unified Web Frontend & FastAPI Gateway in STRIX

## Execution Rules
- Work EXCLUSIVELY inside `/home/vinit/STRIX/strix`.
- DO NOT edit any files in `/home/vinit/AI_VAPT`. Use it only as a read-only reference to copy code from.

## Goal
Add the AI-VAPT SPA frontend and FastAPI gateway to Strix so that running `uv run uvicorn strix.interface.api:app --host 127.0.0.1 --port 8000` launches a complete interactive web application.

## Step-by-Step Instructions
1. Install `fastapi` in Strix's virtual environment:
   `cd /home/vinit/STRIX/strix && uv pip install fastapi`
2. Create the web directory:
   `mkdir -p /home/vinit/STRIX/strix/strix/interface/web/`
3. Copy static frontend files from AI_VAPT into Strix:
   `cp -r /home/vinit/AI_VAPT/frontend/web/* /home/vinit/STRIX/strix/strix/interface/web/`
4. Create `/home/vinit/STRIX/strix/strix/interface/schemas.py`:
   Define Pydantic models for `RunRequest`, `RunResponse`, `SystemHealthResponse`, `TargetValidationRequest`, `TargetValidationResponse`.
5. Create `/home/vinit/STRIX/strix/strix/interface/api.py`:
   - Initialize FastAPI app.
   - Mount `/css` and `/js` static routes to `/home/vinit/STRIX/strix/strix/interface/web/css` and `.../js`.
   - Add root route `GET /` returning `index.html`.
   - Add routes:
     - `GET /health` -> `{"status": "ok"}`
     - `GET /system/health` -> System health status JSON
     - `GET /scenarios` -> List of test scenarios
     - `POST /targets/validate` -> Basic target validation
     - `POST /runs` and `GET /runs/{run_id}` -> In-memory run tracking
6. Update CLI in `strix/interface/cli.py` or `cli_args.py` to allow launching the web interface via `strix web`.
7. Verify that the server starts and serves the dashboard on http://127.0.0.1:8000/.
```

### Verification Commands
```bash
cd /home/vinit/STRIX/strix
# Start server in background
uv run uvicorn strix.interface.api:app --host 127.0.0.1 --port 8000 &
PID=$!
sleep 2

# Check endpoints
curl -s http://127.0.0.1:8000/health
curl -s -I http://127.0.0.1:8000/ | grep "200 OK"
curl -s -I http://127.0.0.1:8000/js/app.js | grep "200 OK"

# Stop server
kill $PID
```

---

## Phase 2: Multi-Model Configuration & Provider Routing

### Development Agent Prompt
```markdown
# TASK: Implement Multi-Model Configuration & Provider Routing in STRIX

## Execution Rules
- Work EXCLUSIVELY inside `/home/vinit/STRIX/strix`.
- DO NOT edit any files in `/home/vinit/AI_VAPT`. Read files from `/home/vinit/AI_VAPT` as read-only reference.

## Goal
Enable dynamic, zero-restart configuration of Local Ollama (`qwen2.5:1.5b`), Google Gemini, and OpenRouter from Strix's web interface, with in-memory credential safety.

## Step-by-Step Instructions
1. Create `/home/vinit/STRIX/strix/strix/llm/ollama_service.py` (ported from `/home/vinit/AI_VAPT/vapt_platform/ollama_service.py`):
   - Implement `probe_ollama()` checking `http://127.0.0.1:11434/api/tags` and listing installed models.
2. Create `/home/vinit/STRIX/strix/strix/llm/provider_validation.py`:
   - Implement `validate_google_credential(api_key)` checking Gemini models endpoint.
   - Implement `validate_openrouter_credential(api_key)` checking OpenRouter models endpoint.
3. Create `/home/vinit/STRIX/strix/strix/llm/router.py`:
   - Bridge incoming provider requests (`ollama`, `google`, `openrouter`) to LiteLLM parameters.
   - For `google`: inject ephemeral `X-Google-API-Key` without saving to `.env`.
   - For `openrouter`: inject ephemeral `X-OpenRouter-API-Key` without saving to `.env`.
4. Update `strix/interface/api.py`:
   - Add endpoint `POST /providers/google/validate`.
   - Add endpoint `POST /providers/openrouter/validate`.
   - Update `GET /system/health` to include live Ollama reachable status and installed models list.
5. In `strix/interface/web/js/app.js`: Ensure setup panels correctly call these validation endpoints.
6. Test inference using `uv run python` against local Ollama (`qwen2.5:1.5b`).
```

### Verification Commands
```bash
cd /home/vinit/STRIX/strix

# 1. Verify Ollama Auto-Detection
uv run python -c "
from strix.llm.ollama_service import probe_ollama
p = probe_ollama('qwen2.5:1.5b')
print('Ollama available:', p.get('available'))
print('Models found:', p.get('models'))
assert p.get('available') is True, 'Ollama should be available'
"

# 2. Verify LiteLLM Routing
uv run python -c "
from strix.llm.router import resolve_model_kwargs
kwargs = resolve_model_kwargs('ollama', 'qwen2.5:1.5b')
print('Resolved kwargs:', kwargs)
assert 'ollama' in kwargs['model']
"
```

---

## Phase 3: GAP-1 Exploit Quality Scoring & Prioritization

### Development Agent Prompt
```markdown
# TASK: Implement GAP-1 AI Exploit Quality Scoring & Prioritization in STRIX

## Execution Rules
- Work EXCLUSIVELY inside `/home/vinit/STRIX/strix`.
- DO NOT edit any files in `/home/vinit/AI_VAPT`. Read files from `/home/vinit/AI_VAPT` as read-only reference.

## Goal
Implement the GAP-1 Exploit Quality Scoring engine in STRIX so that discovered vulnerabilities are enriched with OWASP Top-10 mappings, evaluated by the LLM for real-world usability (HIGH/MEDIUM/LOW), and sorted into an optimal priority queue before agent dispatch.

## Step-by-Step Instructions
1. Create directory `/home/vinit/STRIX/strix/strix/core/triage/`.
2. Port `/home/vinit/AI_VAPT/vapt_platform/owasp_mapping.py` to `/home/vinit/STRIX/strix/strix/core/triage/owasp_mapping.py`:
   - Maps vulnerabilities to OWASP Top 10 (2021) categories, CWE IDs, and remediation instructions.
3. Port `/home/vinit/AI_VAPT/core/exploit_assessor.py` to `/home/vinit/STRIX/strix/strix/core/triage/exploit_assessor.py`:
   - Queries Ollama or hosted LLM to assess exploit code completeness, syntax, privileges, network noise, and complexity.
   - Outputs structured `ExploitAssessment` with `UsabilityRank` (`HIGH`, `MEDIUM`, `LOW`) and reasoning.
4. Create `/home/vinit/STRIX/strix/strix/core/triage/scoring.py`:
   - Implement composite scoring: `FinalScore = BaseProb + Severity + Exposure + AIQualityBoost`.
   - Implement `rank_action_candidates(candidates, provider, model)`.
5. Connect GAP-1 into Strix's scanner pipeline in `strix/core/inputs.py` and `strix/core/runner.py`.
6. Update `strix/interface/api.py` to return candidate quality assessments in `GET /runs/{run_id}`.
7. Write unit tests in `tests/test_gap1_triage.py`.
```

### Verification Commands
```bash
cd /home/vinit/STRIX/strix

# 1. Run unit tests
uv run pytest tests/test_gap1_triage.py -v

# 2. Test live exploit quality assessment
uv run python -c "
from strix.core.triage.exploit_assessor import assess_exploit_quality
from strix.core.triage.scoring import calculate_composite_score

cand = {'id': 'CVE-2021-44228', 'severity': 'critical', 'title': 'Log4j RCE'}
assess = assess_exploit_quality('CVE-2021-44228', provider='ollama', model_name='qwen2.5:1.5b')
score = calculate_composite_score(cand, assess)
print('Usability Rank:', assess.usability_rank)
print('Composite Score:', score)
assert assess.usability_rank is not None
"
```

---

## Phase 4: GAP-2 Dynamic Decision-Pivoting Engine

### Development Agent Prompt
```markdown
# TASK: Implement GAP-2 Bounded Dynamic Decision-Pivoting in STRIX

## Execution Rules
- Work EXCLUSIVELY inside `/home/vinit/STRIX/strix`.
- DO NOT edit any files in `/home/vinit/AI_VAPT`. Read files from `/home/vinit/AI_VAPT` as read-only reference.

## Goal
Implement the GAP-2 Decision Engine inside STRIX so that agent execution is bounded by failure threshold k (default k=2). When attempts on a candidate fail k times, the engine automatically abandons that candidate, emits a REDIRECT event, and pivots to the next candidate.

## Step-by-Step Instructions
1. Create directory `/home/vinit/STRIX/strix/strix/core/decision_engine/`.
2. Port `/home/vinit/AI_VAPT/decision_engine/core/`:
   - `engine.py`: Bounded state machine managing candidate queues, attempt counts, and pivot decisions.
   - `schemas.py`: `Outcome` (SUCCESS, FAIL_TIMEOUT), `PivotEvent` (INIT, ADVANCE, REDIRECT, ABANDON, COMPLETE).
   - `trace.py`: Chronological decision trace logger.
3. Update `strix/core/execution.py` and `strix/core/agents.py`:
   - When a subagent attempt fails, increment candidate attempt counter.
   - If attempts reach `pivot_threshold`, terminate that subagent, record `ABANDON`, and dynamically dispatch next candidate in queue.
4. Expose `decision_trace`, `pivot_events`, and `pivot_count` in Strix's API (`GET /runs/{run_id}`).
5. In `strix/interface/web/js/app.js`: Ensure the frontend renders the interactive DAG graph and decision trace.
6. Write integration tests in `tests/test_gap2_pivoting.py`.
```

### Verification Commands
```bash
cd /home/vinit/STRIX/strix

# 1. Run Decision-Pivoting Integration Tests
uv run pytest tests/test_gap2_pivoting.py -v

# 2. Simulate Decision Pivoting
uv run python -c "
from strix.core.decision_engine.engine import DecisionEngine
from strix.core.decision_engine.schemas import ActionCandidate, Outcome

engine = DecisionEngine(pivot_threshold=2)
c1 = ActionCandidate(id='c1', probability=0.9)
c2 = ActionCandidate(id='c2', probability=0.8)
engine.initialize([c1, c2])

engine.record_outcome('c1', Outcome.FAIL_TIMEOUT)
action = engine.record_outcome('c1', Outcome.FAIL_TIMEOUT)
print('Action after 2 fails:', action)
assert engine.current_candidate.id == 'c2', 'Should have pivoted to c2'
print('Pivot events:', [e.type for e in engine.pivot_events])
"
```

---

## Phase 5: Audit Reporting, Cryptographic Proof & Scope Safeguards

### Development Agent Prompt
```markdown
# TASK: Implement Audit Reporting, Cryptographic Proof & Scope Safeguards in STRIX

## Execution Rules
- Work EXCLUSIVELY inside `/home/vinit/STRIX/strix`.
- DO NOT edit any files in `/home/vinit/AI_VAPT`. Read files from `/home/vinit/AI_VAPT` as read-only reference.

## Goal
Implement fail-closed target scope enforcement, non-destructive active validators with SHA-256 evidence hashing, and comprehensive HTML/JSON audit reporting inside STRIX.

## Step-by-Step Instructions
1. Create `/home/vinit/STRIX/strix/strix/core/safety/scope_validator.py` (ported from `/home/vinit/AI_VAPT/vapt_platform/web_target.py`):
   - Enforce DNS resolution, NAT64 unwrapping, and unconditional rejection of RFC 1918, CGNAT, link-local, and AWS metadata addresses.
2. Create `/home/vinit/STRIX/strix/strix/tools/validators/` (ported from `/home/vinit/AI_VAPT/vapt_platform/validators/`):
   - Implement non-destructive validators (`phpinfo.py`, `headers.py`, `cookies.py`).
   - Every confirmed validation computes `evidence_hash = hashlib.sha256(content).hexdigest()`.
3. Create `/home/vinit/STRIX/strix/strix/report/builder.py` and `renderers.py` (ported from `/home/vinit/AI_VAPT/vapt_platform/reporting/`):
   - Generate styled HTML and structured JSON reports containing OWASP categories, CVEs, cryptographic proof hashes, decision traces, and Nginx/Apache configuration patches.
4. Update `strix/interface/api.py`:
   - Connect `POST /targets/validate` to the scope validator.
   - Connect `GET /runs/{run_id}/report` to the report builder.
5. Write tests in `tests/test_scope_and_reporting.py`.
```

### Verification Commands
```bash
cd /home/vinit/STRIX/strix

# 1. Run Scope & Reporting Tests
uv run pytest tests/test_scope_and_reporting.py -v

# 2. Verify Private IP Rejection (SSRF Safeguard)
uv run python -c "
from strix.core.safety.scope_validator import validate_web_target
v = validate_web_target('http://192.168.1.1')
print('Authorized:', v.authorized)
assert v.authorized is False, 'Private IP must be rejected'
"

# 3. Verify SHA-256 Evidence Hashing
uv run python -c "
import hashlib
content = b'test response evidence'
h = hashlib.sha256(content).hexdigest()
print('Evidence Hash:', h)
assert len(h) == 64
"
```

---

## Master End-to-End Verification

Once all 5 phases are implemented, execute this complete smoke test to confirm the entire integrated platform functions end-to-end:

```bash
# 1. Start the Unified Strix Platform
cd /home/vinit/STRIX/strix
uv run uvicorn strix.interface.api:app --host 127.0.0.1 --port 8000 &
SERVER_PID=$!
sleep 3

# 2. Validate System Health
curl -s http://127.0.0.1:8000/system/health | grep -E "READY|AVAILABLE"

# 3. Execute a GAP-2 Bounded Pivot Run via API
RUN_RES=$(curl -s -X POST http://127.0.0.1:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "docker_pivot",
    "mode": "simulation",
    "assessor": "llm",
    "assessor_provider": "ollama",
    "assessor_model": "qwen2.5:1.5b",
    "max_attempts": 2
  }')
RUN_ID=$(echo $RUN_RES | grep -oP '(?<="run_id":")[^"]+')
echo "Launched Run ID: $RUN_ID"

# 4. Poll until completion
sleep 15
STATUS=$(curl -s http://127.0.0.1:8000/runs/$RUN_ID)
echo $STATUS | grep -oP '(?<="status":")[^"]+'

# 5. Verify HTML Report Generation
curl -s "http://127.0.0.1:8000/runs/$RUN_ID/report?format=html" | grep -o "<title>AI VAPT Report"

# 6. Stop Server
kill $SERVER_PID
```

