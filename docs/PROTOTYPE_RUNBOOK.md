# AI-VAPT Prototype Runbook & Operational Guide

**Framework:** Autonomous AI Framework for Vulnerability Assessment: Integrating Exploit Quality Scoring and Dynamic Decision-Pivoting  
**Repository:** `Vinit-Solanki16/ai_vapt_framework`  
**Last Verified:** 2026-10-25  
**Baseline Test Status:** 1036 passed, 0 failed  

---

## 1. Prerequisites

- **OS:** Linux (Ubuntu 22.04+ or WSL2)
- **Python:** Python 3.10+ (tested on Python 3.10 and Python 3.14)
- **Nmap:** Installed on system PATH (`sudo apt install nmap`)
- **Nuclei:** (Optional) Installed on system PATH (`go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest`)
- **Docker:** (Optional, for Docker Lab mode) Docker daemon active with permissions (`docker compose`)
- **Ollama:** (Optional, for offline AI assessment) Ollama daemon installed (`/usr/local/bin/ollama`)

---

## 2. Environment Setup

Clone the repository and enter the workspace:

```bash
git clone https://github.com/Vinit-Solanki16/ai_vapt_framework.git
cd ai_vapt_framework
python3 -m venv .venv
source .venv/bin/activate
```

---

## 3. Dependency Installation

Install pinned dependencies and register project packages in editable mode:

```bash
pip install -r requirements.txt
pip install -e .
```

> [!IMPORTANT]
> Running `pip install -e .` is required to ensure packages (`vapt_platform`, `services`, `decision_engine`, `prototype`, `frontend`, `core`) are discoverable by both Streamlit and Uvicorn across all working directories.

---

## 4. Ollama Setup (Local Offline AI Mode)

1. Start Ollama daemon:
   ```bash
   ollama serve &
   ```

2. Verify reachability:
   ```bash
   curl -s http://127.0.0.1:11434/api/tags
   ```

3. Thesis baseline model (optional):
   ```bash
   ollama pull llama3.2:3b
   ```

4. Configurable local model (already installed in lab environment):
   ```bash
   ollama pull qwen3.5:4b
   ```

---

## 5. Model Configuration

- **Default Baseline:** `llama3.2:3b` (the official M.Tech thesis baseline).
- **Environment Override:** Set `OLLAMA_MODEL` in `.env` or shell to select another local model:
  ```bash
  export OLLAMA_MODEL=qwen3.5:4b
  ```
- **Inference Timeouts:** Bounded via `OLLAMA_TIMEOUT_S` (default 60s, evaluation defaults to 12s).
- **Graceful Fallback:** If Ollama is offline, unreachable, or times out, the framework automatically uses deterministic evaluation and logs exact fallback provenance.

---

## 6. API Startup Command

Run the FastAPI backend:

```bash
source .venv/bin/activate
uvicorn services.api:app --host 0.0.0.0 --port 8000 --reload
```

Or execute the canonical startup script:

```bash
./scripts/start_demo.sh
```

---

## 7. Frontend Startup Command

Run the Streamlit Operations Console:

```bash
source .venv/bin/activate
streamlit run frontend/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
```

---

## 8. Port and URL Information

| Service | Port | URL | Description |
|---|---|---|---|
| FastAPI Backend | `8000` | `http://localhost:8000` | REST API, OpenAPI docs, and Web Console |
| API Docs | `8000` | `http://localhost:8000/docs` | Swagger / OpenAPI UI |
| API OpenAPI JSON | `8000` | `http://localhost:8000/openapi.json` | OpenAPI 3.1 specification |
| Streamlit Operations Console | `8501` | `http://localhost:8501` | Interactive SOC security dashboard |
| Ollama HTTP API | `11434` | `http://localhost:11434` | Local LLM inference engine |
| Docker Lab Executor | `9090` | `http://localhost:9090` | Docker container execution bridge |
| Docker Lab Emulator | `8080` | `172.28.0.2:8080` | Isolated target container |

---

## 9. How to Run Local Simulation

### Via API:

```bash
curl -s -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"scenario": "failure_pivot", "mode": "simulation", "assessor": "deterministic", "max_attempts": 2}'
```

Returns:
```json
{"run_id":"<UUID>","status":"queued","message":"Run accepted and queued for asynchronous processing."}
```

### Via CLI:

```bash
python -m prototype.cli run --scenario failure_pivot --mode simulation
```

---

## 10. How to Perform a Permitted Assessment

### Permitted Local Target Assessment:

```bash
curl -s -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"assessment_type": "web", "mode": "web", "target_url": "http://127.0.0.1:9191", "use_nmap": true}'
```

### Permitted Authorized External Scope Assessment:

```bash
curl -s -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "assessment_type": "web",
    "mode": "web",
    "target_url": "http://pentest-ground.com:4280",
    "target_scope_acknowledged": true,
    "use_nmap": true
  }'
```

---

## 11. How to Retrieve Run Status

Poll the run status endpoint:

```bash
curl -s http://localhost:8000/runs/<RUN_ID>
```

Response fields include:
- `status`: `queued`, `running`, `completed`, `failed`
- `final_status`: `COMPLETED`, `SUCCESS`, `FAILED`
- `total_attempts`: Number of executed candidates
- `pivot_count`: Number of decision pivots
- `evidence_tier`: `SIMULATED`, `DOCKER_OBSERVED`, or `INDEPENDENTLY_VALIDATED`
- `decision_trace`: Step-by-step trace of candidate evaluation and pivots

---

## 12. How to Inspect Findings and Provenance

Inspect findings and AI provenance:

```bash
# Findings details
curl -s http://localhost:8000/runs/<RUN_ID>/findings

# AI Assessment provenance and model details
curl -s http://localhost:8000/runs/<RUN_ID>/assessment

# Complete execution trace
curl -s http://localhost:8000/runs/<RUN_ID>/trace
```

---

## 13. How to Generate a Report

Generate reports in multiple formats:

```bash
# JSON report
curl -s "http://localhost:8000/runs/<RUN_ID>/report?format=json"

# Markdown report
curl -s "http://localhost:8000/runs/<RUN_ID>/report?format=markdown"

# Plain text report
curl -s "http://localhost:8000/runs/<RUN_ID>/report?format=txt"

# HTML report
curl -s "http://localhost:8000/runs/<RUN_ID>/report?format=html"
```

---

## 14. How to Run Focused Tests

```bash
# Async runs & API queue
pytest services/tests/test_async_runs.py -v

# API safety and target validation
pytest services/tests/test_safety.py -v

# Finding reliability evaluator suite
pytest tests/test_finding_reliability_evaluator.py -v

# GAP-1 and GAP-2 research tests
pytest tests/test_ttests_gaps.py tests/test_provider_integration_gaps.py -v

# Docker lab integration
pytest prototype/tests/test_docker_lab.py -v
```

---

## 15. How to Run the Full Test Suite

Run all 1,036 unit, integration, and security tests:

```bash
pytest -q
```

Expected output:
```text
1036 passed in ~8s
```

---

## 16. How to Run the Reliability Evaluation

Run ground-truth multi-layer reliability evaluation:

```bash
timeout 60s env PYTHONPATH=. python -u scripts/run_reliability_evaluation.py
```

Outputs:
- Multi-layer metric comparison table (Scanner vs Active Validation)
- Ground-truth test case outcomes (10/10 PASS)
- AI Assessor model comparison and fallback metrics
- GAP-2 dynamic pivoting validation

---

## 17. Known Limitations

1. **CPU LLM Latency:** Running 4B+ parameter models on 2-vCPU environments takes 20-40 seconds per candidate. Use bounded `OLLAMA_TIMEOUT_S=12` or deterministic fallback for quick demonstrations.
2. **In-Memory Job Storage:** Async jobs are retained in an in-memory queue and repository with persistent JSON run storage in `data/runs/`.
3. **Target Allowlist:** Target hosts are strictly limited to `127.0.0.1`, `localhost`, and explicitly configured external scopes in `VAPT_AUTHORIZED_WEB_SCOPES`.

---

## 18. Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'vapt_platform'` | Package not installed in venv | Run `pip install -e .` |
| `Ollama HTTP API not reachable` | Daemon not running | Run `ollama serve &` |
| `Ollama model not installed` | Model not pulled | Run `ollama pull qwen3.5:4b` |
| Docker lab connection timeout | Legacy iptables drop | Run `./scripts/start_lab.sh` (auto-configures bridge forwarding) |
| `Target not authorized` | Target URL outside allowlist | Add host:port to `VAPT_AUTHORIZED_WEB_SCOPES` |

---

## 19. Security Warnings & Authorization Requirements

> [!CAUTION]
> Never scan public or third-party targets without explicit authorization and defined scope.
> The framework enforces fail-closed behavior: unauthorized targets are rejected with HTTP 400.
> External targets require operator acknowledgement (`target_scope_acknowledged=true`).
