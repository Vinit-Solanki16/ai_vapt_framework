# AI-VAPT Overnight Readiness Report: Preparing for Genuine Autonomous Execution

**Date:** 2026-11-10  
**Branch:** `ai-vapt-full-application`  
**Working Directory:** `/workspaces/ai_vapt_framework`  
**Execution Objective:** Transition AI-VAPT from simulated/fallback behavior to genuine, evidence-based autonomous multi-agent penetration testing, enforce execution transparency, integrate preflight diagnostics, synchronize CLI/Web API execution, and deliver verified readiness documentation.

---

## 1. Executive Summary

During previous assessment phases (Phases 6 and 7), the core autonomous execution engine (`strix/core/runner.py`) was integrated with GAP-1 candidate queues, GAP-2 bounded pivots, and an evidence-based finding verification lifecycle. However, when executed from the Web application in an environment lacking Docker virtualization, the application silently fell back to an in-process active probe loop while reporting simulated agent turns, LLM costs, and "Autonomous VAPT Engine" execution.

This overnight readiness implementation resolves these architectural discrepancies:
1. **Total Execution Transparency:** Eliminated silent fallback. When `mode="autonomous"` is requested and Docker is unavailable, the API returns a clear HTTP 400 with actionable guidance. It never records simulated turns or synthetic LLM costs.
2. **Explicit Execution Modes:** Added explicit `execution_mode` metadata across schemas, web frontend, and report builders:
   - `autonomous_multi_agent` (Docker sandbox, multi-agent core, GAP-1/GAP-2)
   - `lightweight_active_scanner` (direct benign HTTP probing, no Docker)
   - `simulation` (offline benchmark harness)
   - `blocked` (runtime prerequisites unavailable)
3. **Comprehensive Runtime Diagnostics:** Implemented five-category preflight diagnostic engines exposed via `GET /system/readiness` and `GET /diagnostics/readiness` without exposing credentials or tokens.
4. **CLI & Web API Synchronization:** Added `--run-name` / `--name` CLI flags and eliminated output directory guessing, ensuring that Web API and CLI share the exact same run identifier and directory structure (`strix_runs/<run-id>`).
5. **Verified Test Suite:** Created `tests/test_overnight_autonomous_readiness.py` with 10 comprehensive tests covering all readiness criteria; 100% passing alongside existing 87 integration and lifecycle tests.

---

## 2. Detailed Summary of Changes Made

### 2.1 Backend Core & Diagnostics
- **`strix/core/diagnostics.py`:** Created runtime preflight diagnostic engine evaluating Python 3.12+, Docker CLI, Docker daemon connectivity, sandbox image presence (`strix-sandbox:latest`), AI model selection, provider credential connectivity/quota status, and storage directory permissions. Returns structured `RuntimeReadinessReport` classified into `ready`, `missing_dependency`, `configuration_required`, `provider_unavailable`, or `runtime_unavailable`.
- **`strix/interface/readiness.py`:** Added `check_runtime_readiness()` and `RuntimeReadinessResponse` with component status details, safe credential validation via `validate_openrouter_credential`, and actionable remediation recommendations.
- **`strix/interface/schemas.py`:** Updated `RunRequest` to accept `mode="lightweight"` and `mode="in_process"`; added `execution_mode` to `RunStatus` and `RunResponse`; added `status="blocked"` enum value.

### 2.2 CLI Flags & Parameter Alignment
- **`strix/interface/cli_args.py`:** Added `--run-name` and `--name` options to `parse_arguments()`. Falls back gracefully to `STRIX_RUN_NAME` environment variable when specified.
- **`strix/interface/scan_setup.py`:** Updated `prepare_run()` to prioritize `args.resume`, `args.run_name`, and `os.environ["STRIX_RUN_NAME"]` before falling back to automatic random name generation.

### 2.3 Web API Execution Pipeline (`strix/interface/api.py`)
- **Fast-Fail on Missing Docker:** In `create_run()`, requests with `mode="autonomous"` when `_is_docker_available()` is `False` immediately raise `HTTPException(400)` with a clear explanation that Docker is required and recommending `mode="lightweight"`.
- **Worker Transparency:** In `_execute_run_worker()`, if autonomous mode lacks Docker, the run entry status is marked `status="blocked"`, `execution_mode="blocked"`, and terminated immediately.
- **Subprocess Argument Synchronization:** Passes `--run-name {run_id}` and sets `STRIX_RUN_NAME={run_id}` in `sub_env`, eliminating timestamp-based directory guessing in `_sync_telemetry()`.
- **Diagnostic Endpoints:** Exposed `@app.get("/system/readiness")` and `@app.get("/diagnostics/readiness")`.
- **Truthful Report Branding:** `_generate_markdown_report()` labels the execution engine as `AI-VAPT Autonomous Multi-Agent Core (Docker Sandbox)` for autonomous mode and `AI-VAPT Lightweight In-Process Active Scanner (No Docker)` for lightweight mode.

### 2.4 Web Dashboard & UI Updates
- **`strix/interface/web/index.html`:** Added `⚡ Lightweight In-Process Scanner (Direct Active Probing, No Docker)` option to the Execution Engine dropdown.
- **`strix/interface/web/js/app.js`:** Added runtime readiness check on dashboard initialization; displays warning banner when Docker is unavailable; renders actual `execution_mode` in the active run dashboard; handles `BLOCKED` status cleanly.

### 2.5 Report Builder (`strix/report/builder.py`)
- Configured `render_html_report()` to display accurate execution mode (`Autonomous Multi-Agent Core (Docker)` vs `Lightweight Active Scanner (In-Process)`) in the executive meta-grid.

---

## 3. Architectural Comparison: Before vs. After Execution Paths

```
========================================================================================
BEFORE: Silent Fallback & Conflated Execution
========================================================================================

User Request: mode="autonomous"
      │
      ▼
Docker Available? ─── NO ───► In-Process HTTP Probe Loop
                              ├── active_agent = "Autonomous VAPT Engine" (MISLEADING)
                              ├── Reports simulated agent turns (MISLEADING)
                              ├── Reports fake LLM token usage (MISLEADING)
                              └── Report Claim: "Autonomous Multi-Agent Core" (FABRICATED)

========================================================================================
AFTER: Transparent, Explicit, and Partitioned Execution Paths
========================================================================================

User Request: mode="autonomous"
      │
      ├─► Docker Available? ─── YES ──► Subprocess: strix.interface.main
      │                                 ├── Passed: --run-name {run_id} (No guessing)
      │                                 ├── Docker sandbox: strix-sandbox:latest
      │                                 ├── Multi-agent LLM reasoning (Genuine)
      │                                 ├── GAP-1 candidate triage + GAP-2 pivots
      │                                 └── Artifacts: strix_runs/{run_id}/
      │
      └─► Docker Available? ─── NO  ──► HTTP 400 Bad Request
                                        ├── Error: "Autonomous execution requires Docker"
                                        ├── Suggestion: "Select mode='lightweight'"
                                        └── Zero fake artifacts or simulated LLM calls

User Request: mode="lightweight"
      │
      ▼
In-Process Active Scanner (Direct HTTP)
      ├── active_agent = "Lightweight Active Scanner" (TRUTHFUL)
      ├── execution_mode = "lightweight_active_scanner" (EXPLICIT)
      ├── No synthetic LLM turns or simulated costs
      └── Report Claim: "AI-VAPT Lightweight In-Process Active Scanner (No Docker)"
```

---

## 4. Current Environment Diagnostic Results

Running `evaluate_runtime_readiness()` on the current development environment:

```json
{
  "status": "provider_unavailable",
  "ready_for_autonomous": false,
  "ready_for_lightweight": false,
  "timestamp": "2026-11-10T19:11:22.393384+00:00",
  "checks": [
    {
      "id": "python_environment",
      "name": "Python Environment",
      "category": "environment",
      "status": "ready",
      "passed": true,
      "details": "Python 3.12.11 with all core dependencies installed."
    },
    {
      "id": "docker_cli",
      "name": "Docker CLI Executable",
      "category": "runtime",
      "status": "runtime_unavailable",
      "passed": false,
      "details": "Docker CLI ('docker') was not found in system PATH.",
      "remediation": "Install Docker Engine or Docker Desktop and ensure 'docker' is in PATH."
    },
    {
      "id": "docker_daemon",
      "name": "Docker Daemon Connectivity",
      "category": "runtime",
      "status": "runtime_unavailable",
      "passed": false,
      "details": "Docker daemon cannot be contacted: Docker CLI is absent.",
      "remediation": "Install Docker and start the Docker daemon ('sudo systemctl start docker')."
    },
    {
      "id": "sandbox_image",
      "name": "Sandbox Container Image",
      "category": "runtime",
      "status": "runtime_unavailable",
      "passed": false,
      "details": "Cannot verify image 'ghcr.io/usestrix/strix-sandbox:1.3.0': Docker daemon is disconnected.",
      "remediation": "Ensure Docker daemon is running, then pull or build the sandbox image."
    },
    {
      "id": "model_configuration",
      "name": "AI Model Selection",
      "category": "model",
      "status": "ready",
      "passed": true,
      "details": "Configured model: 'openrouter/meta-llama/llama-3.3-70b-instruct' (Provider: OPENROUTER)."
    },
    {
      "id": "provider_credential",
      "name": "AI Provider Credentials",
      "category": "provider",
      "status": "provider_unavailable",
      "passed": false,
      "details": "OpenRouter credential validation failed: Invalid OpenRouter API key (Unauthorized)",
      "remediation": "Update your API key with active credits or switch to a different provider."
    },
    {
      "id": "storage_permissions",
      "name": "Assessment Runs Directory",
      "category": "storage",
      "status": "ready",
      "passed": true,
      "details": "Runs artifact directory '/workspaces/ai_vapt_framework/strix_runs' is writable."
    }
  ],
  "recommendations": [
    "Install Docker Engine and add the 'docker' command to PATH to enable autonomous multi-agent execution.",
    "AI Provider error: OpenRouter credential validation failed: Invalid OpenRouter API key (Unauthorized)"
  ],
  "environment_info": {
    "python_version": "3.12.11",
    "docker_cli": "None",
    "docker_version": "Unavailable",
    "docker_daemon_connected": false,
    "sandbox_image": "ghcr.io/usestrix/strix-sandbox:1.3.0",
    "sandbox_image_present": false,
    "provider": "openrouter",
    "model": "openrouter/meta-llama/llama-3.3-70b-instruct",
    "credentials_configured": true,
    "runs_directory": "/workspaces/ai_vapt_framework/strix_runs"
  }
}
```

---

## 5. Test Suite Verification Results

### 5.1 Overnight Readiness Tests (`tests/test_overnight_autonomous_readiness.py`)

| Test Case | Description | Result |
| :--- | :--- | :--- |
| `test_readiness_detects_missing_docker_runtime_unavailable` | Detects missing Docker CLI and reports `runtime_unavailable` | **PASSED** |
| `test_readiness_detects_available_docker_ready` | Mocked Docker CLI, daemon, and image reports `ready` | **PASSED** |
| `test_post_runs_autonomous_without_docker_returns_400` | Autonomous run request without Docker returns HTTP 400 | **PASSED** |
| `test_post_runs_lightweight_execution_mode` | Lightweight run records `execution_mode: "lightweight_active_scanner"` | **PASSED** |
| `test_lightweight_scan_reports_no_simulated_agent_turns_or_llm_costs` | Ensures no fake agent turns or simulated LLM costs in report | **PASSED** |
| `test_cli_run_name_controls_output_directory` | `--run-name` and `--name` set exact output directory | **PASSED** |
| `test_web_api_passes_run_id_to_subprocess_and_monitors_dir` | Web API spawns CLI with `--run-name {run_id}` | **PASSED** |
| `test_finding_verification_lifecycle_enforces_genuine_evidence` | Enforces 5-point contract before marking finding `Verified` | **PASSED** |
| `test_provider_connectivity_identifies_quota_exhaustion_without_leaking_key` | Identifies quota exhaustion and strictly masks secrets | **PASSED** |
| `test_reports_accurately_reflect_execution_engine` | HTML/Markdown reports reflect truthful execution branding | **PASSED** |

### 5.2 Combined Test Suite Status

```
tests/test_overnight_autonomous_readiness.py ..........                  [10/10 PASSED]
tests/test_phase6_core_runner_gap_integration.py ......                  [ 6/6  PASSED]
tests/test_phase7_e2e_validation.py ........                             [ 8/8  PASSED]
tests/test_vapt_lifecycle_verification.py .........................      [25/25 PASSED]
tests/test_gap_render_report.py ........                                 [ 8/8  PASSED]
tests/test_verification_lifecycle.py ..............................      [30/30 PASSED]

Total: 87 passed, 0 failed in 15.59s
Ruff format: 317 files checked, formatted
Ruff linter: All checks passed!
Mypy: Success: no issues found in 176 source files
Bandit: 0 issues identified across 53,918 lines scanned
```

---

## 6. Operator Instructions for Enabling Genuine Autonomous Execution

To run the first genuine autonomous multi-agent security assessment:

### Step 1: Provide Docker Access
On a host with Docker installed:
```bash
# If using devcontainer, bind-mount the Docker socket in devcontainer.json:
# "mounts": ["source=/var/run/docker.sock,target=/var/run/docker.sock,type=bind"]
docker info
```

### Step 2: Build the Sandbox Container Image
```bash
docker build -t strix-sandbox:latest -f containers/sandbox.Dockerfile .
```

### Step 3: Configure Live AI Provider Credentials
```bash
export STRIX_LLM_PROVIDER="openrouter"
export STRIX_LLM="openrouter/meta-llama/llama-3.3-70b-instruct"
export OPENROUTER_API_KEY="<your-active-api-key>"
```

### Step 4: Verify Preflight Readiness
```bash
uv run python -c "
from strix.core.diagnostics import evaluate_runtime_readiness
rep = evaluate_runtime_readiness()
print('Readiness Status:', rep.status.value)
assert rep.ready_for_autonomous, 'Autonomous mode not ready'
"
```

### Step 5: Execute Genuine Autonomous Pentest
```bash
# CLI direct execution
uv run strix -t "http://127.0.0.1:4280" -m quick --max-turns 50 --run-name "dvwa-autonomous-01"

# Or via Web API
curl -X POST http://127.0.0.1:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "target_url": "http://127.0.0.1:4280",
    "mode": "autonomous",
    "scan_mode": "quick",
    "max_turns": 50,
    "target_scope_acknowledged": true
  }'
```

---

## 7. Resumption Instructions for Next Agent Session

1. **Working Branch:** `ai-vapt-full-application`.
2. **Current State:**
   - Full execution transparency is enforced.
   - All 87 integration, verification lifecycle, and overnight readiness tests are passing.
   - Zero lint, type, or security findings (Ruff, Mypy, Bandit).
3. **Next Milestone:**
   - Run the first live autonomous scan once the host environment provides Docker daemon socket access (`/var/run/docker.sock`) and an active LLM credential.
   - Confirm candidate queue generation, GAP-2 dynamic failure pivots, and evidence-backed finding confirmation against an authorized live DVWA target.
