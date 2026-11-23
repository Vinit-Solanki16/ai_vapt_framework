# AI-VAPT — Agent Guide

AI-VAPT is an autonomous AI-powered vulnerability assessment and penetration testing platform. This guide provides AI coding agents and autonomous tools with instructions on how to **use**, **operate**, and **contribute** to AI-VAPT safely and effectively.

---

## 1. Operating AI-VAPT from an Agent

### 1.1 Architecture & Runtime Components
- **FastAPI Control Gateway & Web Console:** `strix/interface/api.py` and `strix/interface/web/`.
- **Core Orchestrator & Multi-Agent Graph:** `strix/core/runner.py` and `strix/agents/`.
- **GAP-1 Prioritization & Candidate Triage:** `strix/core/decision_engine/engine.py` and `strix/core/gap_bridge.py`.
- **GAP-2 Adaptive Pivoting ($k \le 2$):** `strix/core/gap_run.py`.
- **Docker Sandbox Runtime:** `strix/runtime/` with sandbox container `ghcr.io/usestrix/strix-sandbox:1.3.0`.
- **Docker Cleanup Backstop:** `strix/runtime/docker_cleanup.py` (auto-reaping orphaned containers).
- **Multi-Provider AI Router:** `strix/llm/` supporting Cloud-Hosted (OpenAI-compatible), Ollama, OpenRouter, Anthropic, and Google.

### 1.2 Running an Assessment
To run an authorized assessment programmatically:

1. **Start the Web Operations Console / Gateway:**
   ```bash
   ./ai-vapt.sh start --port 8000
   ```
   Verify health:
   ```bash
   curl -s http://127.0.0.1:8000/health
   # Returns: {"status":"ok","service":"ai-vapt-gateway"}
   ```

2. **Trigger an Assessment via API:**
   ```bash
   curl -X POST http://127.0.0.1:8000/runs \
     -H "Content-Type: application/json" \
     -d '{
       "target": "http://localhost:3000",
       "scan_mode": "quick",
       "assessor_provider": "cloud_hosted",
       "assessor_model": "kaggle-model",
       "target_scope_acknowledged": true
     }'
   ```

3. **Or run headlessly from CLI:**
   ```bash
   uv run strix -n -t http://localhost:3000 --scan-mode quick --max-budget 10
   ```

### 1.3 Interpreting Exit Codes
AI-VAPT uses standard security-scanner exit codes:
- **`0` (Clean):** Scan completed successfully with zero verified vulnerabilities.
- **`1` (Fatal Error):** Unhandled execution error or process failure.
- **`2` (Vulnerabilities Found):** Scan completed successfully and verified security vulnerabilities were identified. This indicates successful finding discovery, **not** a process crash.

### 1.4 Assessment Deliverables
Every completed run generates audit artifacts in `strix_runs/<run-id>/`:
- `penetration_test_report.md` — Human-readable markdown report.
- `vapt_report_<run-id>.html` — Interactive executive HTML report with SHA-256 evidence digests.
- `vapt_report_<run-id>.pdf` — Executive summary PDF report.
- `findings.sarif` — OASIS SARIF v2.1.0 report for CI/CD ingestion.
- `vulnerabilities.json` & `vulnerabilities.csv` — Machine-readable findings.
- `run.json` — Comprehensive execution telemetry and turn accounting.

---

## 2. Docker Sandbox & Cleanup Lifecycle

- Sandbox containers execute inside isolated Docker environments with network capability restrictions.
- Every container created carries explicit AI-VAPT labels:
  - `app: ai-vapt`
  - `ai-vapt-managed: true`
  - `strix-managed: true`
  - `strix-run-id: <run-id>`
- **Cleanup Backstop:** If a process is terminated abruptly (SIGKILL or host shutdown), orphaned containers are safely cleaned up on server restart or via:
  ```bash
  curl -X POST http://127.0.0.1:8000/system/docker/cleanup
  ```
  The cleanup reaper strictly inspects AI-VAPT ownership labels, preserves active assessments, and never touches unrelated host containers (e.g. databases, testbeds).

---

## 3. Contributing to AI-VAPT

### 3.1 Prerequisites & Development Environment
- Python 3.12+ managed with `uv`.
- Docker Engine running locally or via remote TLS socket.
- Setup dependencies:
  ```bash
  uv sync
  ```

### 3.2 Quality Gates & Verification
Before submitting changes or preparing releases, ensure all gates pass:
- **Fast Linting & Formatting:**
  ```bash
  uv run ruff check .
  uv run ruff format --check .
  ```
- **Type Checking:**
  ```bash
  uv run mypy strix/
  ```
- **Security Audit:**
  ```bash
  uv run bandit -r strix/ -c pyproject.toml
  ```
- **Automated Tests:**
  ```bash
  uv run pytest
  ```

### 3.3 Target Authorization Rule
> **MANDATORY SAFETY BOUNDARY:** Never execute scans against unauthorized targets. Only assess systems that you own or have explicit written authorization to test.
