# AI-VAPT Autonomous Runtime Setup & Operator Runbook

This guide documents the technical prerequisites, environment configuration, container build steps, preflight diagnostics, and execution instructions required to perform a genuine end-to-end autonomous penetration test with the **AI-VAPT Multi-Agent Autonomous Core Engine**.

---

## 1. Architecture Overview

AI-VAPT supports two distinct execution paths:

| Mode | Execution Engine | Requirements | Primary Use Case |
| :--- | :--- | :--- | :--- |
| **Autonomous Multi-Agent Core** (`mode="autonomous"`) | Sandboxed Docker container running root multi-agent graph with dynamic tool calling (GAP-1 triage queue, GAP-2 bounded failure pivots). | Docker Engine/Desktop (`/var/run/docker.sock`), built `strix-sandbox:latest` image, active LLM API key with credits. | Comprehensive autonomous penetration testing, real exploit verification, and end-to-end multi-agent assessment. |
| **Lightweight In-Process Active Scanner** (`mode="lightweight"`) | In-process asynchronous HTTP probing engine with deterministic category checks and regex payload validation. | Python 3.12+ (no Docker required). Zero LLM credit consumption. | Rapid surface auditing, environments without Docker socket access, or quick pre-assessment connectivity testing. |

---

## 2. Docker Runtime Setup

Autonomous multi-agent execution isolates penetration testing tools inside a dedicated sandbox container.

### 2.1 Docker Engine / Desktop Prerequisites
- **Docker Engine**: Version 24.0+ or **Docker Desktop**: Version 4.25+
- **Host Socket Access**: The AI-VAPT process must communicate with the Docker daemon via standard Unix socket or TCP host:
  ```bash
  # Verify Docker CLI and daemon connectivity
  docker --version
  docker info
  ```
  If permission is denied:
  ```bash
  sudo usermod -aG docker $USER
  newgrp docker
  ```

### 2.2 Sandbox Image Build
Build the official AI-VAPT sandbox container from the repository root:
```bash
cd /workspaces/ai_vapt_framework
docker build -t strix-sandbox:latest -f containers/sandbox.Dockerfile .
```
Verify the image is present:
```bash
docker image inspect strix-sandbox:latest --format '{{.Id}} (Built: {{.Created}})'
```

### 2.3 Container Networking & Host Reachability
When testing targets running locally on the host machine (e.g., DVWA running at `http://127.0.0.1:4280` or `http://localhost:8080`):
- Inside the Docker sandbox container, `127.0.0.1` refers to the container itself.
- **AI-VAPT automatically rewrites loopback targets** (`localhost` / `127.0.0.1` / `::1`) to `host.docker.internal` so the containerized tools can reach services exposed on the host.
- On Linux hosts where `host.docker.internal` is not configured by default, ensure Docker daemon configuration contains `host-gateway`:
  ```bash
  # Run check to confirm host.docker.internal resolves to host IP:
  docker run --rm --add-host=host.docker.internal:host-gateway strix-sandbox:latest curl -s -I http://host.docker.internal:4280/ || true
  ```

---

## 3. LLM Provider Configuration

The autonomous multi-agent core requires a capable reasoning model for reconnaissance, candidate identification (GAP-1), and exploit strategy formulation (GAP-2).

### 3.1 Supported Providers
1. **OpenRouter** (Recommended for multi-model access)
2. **Google Gemini** (`gemini-2.5-flash`, `gemini-1.5-pro`)
3. **OpenAI / Custom OpenAI-Compatible Endpoints** (vLLM, Ollama, LiteLLM)

### 3.2 Environment Variables & Config File Paths
You can configure credentials via environment variables or persistent CLI configuration:

#### Option A: Persistent CLI Config
AI-VAPT reads `~/.strix/cli-config.json` on startup:
```json
{
  "STRIX_LLM": "openrouter/nvidia/nemotron-3.5-lightning:free",
  "OPENROUTER_API_KEY": "sk-or-v1-YOUR_ACTUAL_OPENROUTER_KEY",
  "OPENROUTER_API_BASE": "https://openrouter.ai/api/v1"
}
```

#### Option B: Environment Variables
Export variables before starting the AI-VAPT server or CLI:
```bash
export STRIX_LLM="openrouter/google/gemini-2.5-flash"
export OPENROUTER_API_KEY="sk-or-v1-YOUR_ACTUAL_OPENROUTER_KEY"
# Or for Google Gemini:
# export STRIX_LLM="google/gemini-2.5-flash"
# export GEMINI_API_KEY="AIzaSyYOUR_ACTUAL_GEMINI_KEY"
```

### 3.3 Verified Working Model Identifiers
- **Recommended Default**: `openrouter/google/gemini-2.5-flash` or `openrouter/anthropic/claude-3.5-sonnet`
- **Free Quota Option**: `openrouter/nvidia/nemotron-3.5-lightning:free`
- **Gemini Direct**: `google/gemini-2.5-flash`

### 3.4 Key Redaction & Security
AI-VAPT strictly enforces zero credential leakage. Diagnostics, logs, Markdown reports, and HTML artifacts always display masked keys (e.g. `sk-or-v1-****************34ab`).

---

## 4. Target Accessibility & DVWA Authorization

### 4.1 Target URL Format
Provide full protocol and port:
- Web target: `http://127.0.0.1:4280` or `http://host.docker.internal:4280`
- Domain target: `https://authorized-staging.example.com`

### 4.2 DVWA Target Setup
For testing against Damn Vulnerable Web Application (DVWA):
```bash
# If using Docker for DVWA:
docker run -d --name dvwa -p 4280:80 vulnerables/web-dvwa

# Initialize database:
curl -s "http://127.0.0.1:4280/setup.php" -X POST -d "create_db=Create+%2F+Reset+Database"
```

### 4.3 Authentication Configuration
To test authenticated surfaces in DVWA (security level: `low`):
```json
{
  "auth_type": "cookie",
  "headers": {
    "Cookie": "PHPSESSID=YOUR_SESSION_ID; security=low"
  }
}
```

---

## 5. Runtime Preflight Diagnostic Verification

Before launching an assessment, verify system readiness using the built-in diagnostic endpoint.

### 5.1 CLI / API Preflight Check
```bash
curl -s http://127.0.0.1:8080/system/readiness | jq .
```

### 5.2 Expected Output Schema
```json
{
  "overall_status": "ready",
  "autonomous_ready": true,
  "lightweight_ready": true,
  "timestamp": "2026-11-10T19:10:00Z",
  "components": {
    "python_environment": {
      "name": "python_environment",
      "status": "ready",
      "available": true,
      "actionable_message": "Python environment (v3.12.11) and packages are ready.",
      "details": { "python_version": "3.12.11" }
    },
    "docker_runtime": {
      "name": "docker_runtime",
      "status": "ready",
      "available": true,
      "actionable_message": "Docker runtime and sandbox image are ready for autonomous execution.",
      "details": {
        "docker_bin": "/usr/bin/docker",
        "daemon_connected": true,
        "image_present": true
      }
    },
    "llm_provider": {
      "name": "llm_provider",
      "status": "ready",
      "available": true,
      "actionable_message": "Provider 'openrouter' configured with active credentials.",
      "details": {
        "provider": "openrouter",
        "model": "openrouter/google/gemini-2.5-flash",
        "credential_configured": true
      }
    },
    "application_storage": {
      "name": "application_storage",
      "status": "ready",
      "available": true,
      "actionable_message": "Storage paths are accessible with write permissions.",
      "details": { "strix_runs_dir": "/workspaces/ai_vapt_framework/strix_runs" }
    }
  },
  "actionable_recommendations": []
}
```

### 5.3 Diagnostic Status Resolution Matrix

| Status | Component | Cause | Resolution |
| :--- | :--- | :--- | :--- |
| `runtime_unavailable` | `docker_runtime` | Docker daemon is stopped or CLI is missing. | Start Docker (`sudo systemctl start docker`) or launch Docker Desktop. |
| `missing_dependency` | `docker_runtime` | `strix-sandbox:latest` image not built. | Run `docker build -t strix-sandbox:latest -f containers/sandbox.Dockerfile .` |
| `configuration_required`| `llm_provider` | No API key or placeholder key detected. | Set `OPENROUTER_API_KEY` or `GEMINI_API_KEY` in environment or Web Settings. |
| `provider_unavailable` | `llm_provider` | Upstream provider reported quota exhaustion. | Replenish credits or switch provider model in Settings. |

---

## 6. Operator Run Instructions

### 6.1 CLI Execution (Autonomous Headless Scan)
Launch an autonomous scan directly from the terminal:
```bash
# Quick assessment against DVWA (50 turns limit)
uv run strix -n -t http://127.0.0.1:4280 -m quick --max-turns 50 --run-name dvwa-autonomous-run-01

# Deep assessment against DVWA (250 turns limit)
uv run strix -n -t http://127.0.0.1:4280 -m deep --max-turns 250 --run-name dvwa-autonomous-run-02
```

### 6.2 Web UI Execution
1. Open web browser to `http://127.0.0.1:8080/`.
2. In **Target URL**, enter `http://127.0.0.1:4280`.
3. Check the **Target Authorization Acknowledgment** checkbox.
4. Select **Execution Engine**:
   - `🤖 Autonomous Multi-Agent Core (Docker Sandbox)` for genuine multi-agent execution.
   - `⚡ Lightweight In-Process Scanner (Direct Active Probing, No Docker)` if Docker is absent.
5. Select **Scan Depth** (`Quick (50 turns)`, `Standard (100 turns)`, or `Deep (250 turns)`).
6. Click **Launch Assessment**.

### 6.3 Monitoring Execution
- **Real-Time Terminal**: Monitor live turns, candidate dispatch (GAP-1), and failure pivots (GAP-2).
- **Control Artifacts**: Track progress in `strix_runs/<run-id>/control/`:
  - `gap_state.json`: Active candidates, status, and probe counts.
  - `decision_trace.jsonl`: GAP-2 decision pivots (`INIT`, `ADVANCE`, `REDIRECT`, `ABANDON`, `COMPLETE`).

### 6.4 Artifacts & Reports Location
At scan completion, reports are written to `strix_runs/<run-id>/`:
- **Markdown Report**: `strix_runs/<run-id>/penetration_test_report.md`
- **HTML Executive Report**: `strix_runs/<run-id>/report.html`
- **Vulnerabilities JSON**: `strix_runs/<run-id>/vulnerabilities.json`
- **Findings SARIF 2.1.0**: `strix_runs/<run-id>/findings.sarif`
- **Run Telemetry**: `strix_runs/<run-id>/run.json`
