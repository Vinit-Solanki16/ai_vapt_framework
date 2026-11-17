# AI-VAPT — Final Demonstration Checklist & Operator Guide

This checklist provides an exact, step-by-step operational protocol for conducting an authoritative, evidence-backed evaluation and demonstration of the AI-VAPT autonomous security assessment platform for academic evaluation (M.Tech Defense / Technical Demonstration).

---

## 1. System Pre-Flight & Environment Verification

Before launching the user interface or executing scans, confirm host daemon readiness and target authorization.

### 1.1 Verify Authorized Target Reachability
The demonstration supports two authorized target environments:

#### Target A: Local Vulnerable Lab (OWASP Juice Shop — Recommended for Phase D Evaluation)
* **Target URL**: `http://127.0.0.1:3000/` (Host) / `http://host.docker.internal:3000/` (Sandbox)
* **Launcher**: `./juice-shop.sh start`
* **Verification**:
  ```bash
  ./juice-shop.sh start
  ./juice-shop.sh status
  ```
  *(Manual alternative: `docker run -d --name juice-shop -p 127.0.0.1:3000:3000 -p 172.17.0.1:3000:3000 bkimminich/juice-shop:latest`)*

#### Target B: Remote Authorized Lab (DVWA on pentest-ground)
* **Target URL**: `https://pentest-ground.com:4280/`
* **Target IP**: `178.79.134.182`
* **Authorized Ports**: TCP 80, 443, 4280, 6379 (Redis)
* **Verification**:
  ```bash
  curl -k -I https://pentest-ground.com:4280/
  ```
  *Expected*: HTTP 200/302 response with headers `Server: nginx/1.31.8` and `X-Powered-By: PHP/8.5.12`.

### 1.2 Verify Docker Daemon & Sandbox Image
Confirm Docker runtime availability (required for Mode A: Autonomous Multi-Agent Core):
```bash
docker info > /dev/null && echo "Docker Daemon Active"
docker image inspect ghcr.io/usestrix/strix-sandbox:1.3.0 > /dev/null && echo "Sandbox Image Ready"
```

### 1.3 Verify Cloud Hosted AI Model Tunnel & Endpoint
The platform connects to the user-managed Cloud Hosted Qwen3-Coder model via an OpenAI-compatible endpoint:
* **Model Alias**: `kaggle-model-deep`
* **Context Window**: 131,072 tokens
* **Dynamic Tunnel Endpoint**: `[temporary Cloudflare tunnel endpoint]/v1`

Configuration by installation state:
* **Fresh Installation (No registered profile):**
  1. Start the server (`./ai-vapt.sh start`).
  2. Navigate to **AI Models** (`#/settings`).
  3. Under Cloud Hosted, click **Add Profile**, enter your active session tunnel URL, model `kaggle-model-deep`, context `131072`, and click **Activate**.
* **Existing Installation (Pre-registered profile):**
  1. In **AI Models** (`#/settings`), verify the profile is marked `Active`.
  2. If the tunnel URL has rotated since last run, update the endpoint base URL.

Test endpoint directly (replace with your active session tunnel URL):
```bash
ACTIVE_TUNNEL_URL="[temporary Cloudflare tunnel endpoint]/v1"
curl -s "${ACTIVE_TUNNEL_URL}/models" | grep -q "kaggle-model" && echo "Model Endpoint Active"
```

> [!NOTE]
> Cloudflare Quick Tunnels are ephemeral. Before initiating a scan, enter the active tunnel URL in **AI Models** (`#/settings`) or update the profile via API.

---

## 2. Platform Startup & Service Verification

Start the AI-VAPT backend and frontend interface using the unified launcher:
```bash
cd ~/AI_VAPT/ai_vapt_framework
./ai-vapt.sh start    # or ./start.sh
./ai-vapt.sh status
```
Or start the FastAPI ASGI service directly:
```bash
uv run uvicorn strix.interface.api:app --host 127.0.0.1 --port 8000 --log-level info
```

Confirm health endpoints:
* **Web UI Dashboard**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
* **System Health Endpoint**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
* **Active Cloud Profiles**: [http://127.0.0.1:8000/providers/cloud_hosted/profiles](http://127.0.0.1:8000/providers/cloud_hosted/profiles)

---

## 3. Two Demonstration Modes: Understanding the Engine

To ensure scientific honesty during evaluation, understand the two distinct operational execution engines available:

| Feature / Dimension | Mode A: Autonomous Multi-Agent Core | Mode B: Lightweight Active Scanner |
|---|---|---|
| **Execution Runtime** | Isolated Docker Container (`strix-sandbox:1.3.0`) | In-Process Python Asynchronous Scanner |
| **Reasoning Driver** | Cloud Hosted LLM (`kaggle-model-deep`) | Rule-based triage & probe state machine |
| **Tool Execution** | Dynamic tool calling (`exec_command`, `curl`, `nmap`) | Programmatic HTTP/socket probe routines |
| **Turn Model** | Multi-turn reasoning loops with context tracking | Finite queue traversal over GAP-1 candidates |
| **GAP-2 Pivoting** | Dynamic pivots when LLM probes encounter failure | Bounded confirmation retries ($k=2$) with auto-redirect |
| **Execution Speed** | Latency-bound by remote inference (~15–30s/turn) | Rapid deterministic execution (~15s total) |
| **Authoritative Runs** | • **Phase D (Juice Shop)**: `run-9542b3d7` (41 turns, 6 tested, 5 validated, 0 pivots)<br>• **Remote Pentest-Ground**: `run-16c49dbc` (8 turns, 8 tool calls, `paused_execution_limit`) | • **Remote Pentest-Ground**: `run-767ba9da` (15 evaluated, 4 failure pivots, 14.8s) |

---

## 4. Step-by-Step Operator Demonstration Script

Follow this script to demonstrate the core architecture: Model Selection, GAP-1 Attack Surface Triage, GAP-2 Bounded Dynamic Pivoting, Real-Time Telemetry, Authentic Evidence Extraction, and Audit Report Generation.

### Step 1: Provider & Model Configuration
1. Navigate to the **AI Models** tab (`#/settings` or `#/models`).
2. Select **Cloud Hosted (Custom OpenAI API / Remote)**.
3. Verify that the profile `Cloud Hosted Qwen3-Coder 30B (kaggle-model-deep)` is active.
4. Click **Test & Fetch Models** to demonstrate dynamic model catalog discovery from the remote OpenAI-compatible endpoint.

### Step 2: Target Scope & Scan Configuration
1. Navigate to **New Assessment** (`#/new-assessment`).
2. Input Target URL: `https://pentest-ground.com:4280/`.
3. Click **Preflight**: Verify DNS resolution, public IP check (`178.79.134.182`), and loopback protection.
4. Execution Engine: Select either:
   - **Autonomous Multi-Agent Core** (for demonstrating authentic LLM reasoning inside Docker).
   - **Lightweight Active Scanner** (for rapid deterministic review of GAP-1 and GAP-2 DAG).
5. Depth Mode: Select **Quick** (30 turns) or custom budget (e.g. 8–10 turns for quick live demo).
6. GAP-2 Pivot Threshold ($k$): Confirm default bound $k=2$ (bounds non-viable routes to 2 attempts before redirecting).
7. Operator Scope Confirmation: Check the mandatory authorization checkbox.
8. Click **Launch Autonomous VAPT Assessment**.

### Step 3: Monitoring Active Assessment & Live Telemetry
Once launched, the UI automatically transitions to the **Active Assessment** view (`#/active-assessment`):
1. **Header Attribution**: Verify active badges: `RUNNING` / `COMPLETED` / `PAUSED_EXECUTION_LIMIT`, `CLOUD_HOSTED`, `KAGGLE-MODEL-DEEP`.
2. **KPI Counters**:
   * **GAP-1 Candidates**: Observe prioritized candidates dynamically categorized from preflight recon.
   * **GAP-2 Dynamic Pivots**: Observe the pivot counter incrementing when non-viable vectors encounter $k=2$ failures.
   * **Exploit Attempts**: Track monotonically increasing attempt count.
   * **Confirmed Findings**: Track validated vulnerabilities.
3. **Telemetry Cards**:
   * **Elapsed Timer**: Confirms non-drifting timer that freezes exactly upon completion or turn-limit pause.
   * **Active Agent & Task**: Real-time display of active tool/phase (`Target reconnaissance`, `GAP2 adaptive pivoting`).
   * **Live Verification Matrix**: Confirms categorization across Discovered, Candidate, Under Investigation, Verified, and Unconfirmed.
4. **GAP-1 Prioritization Queue (Pre-Execution Matrix)**: Inspect dynamic vector ordering, severity, usability rank, and candidate state.
5. **GAP-2 Decision-Pivoting Graph (DAG)**: Click through the visual DAG showing candidate states (`VALIDATED`, `ABANDONED`, `ATTEMPTING`) and redirect arrows.

### Step 4: Demonstrating GAP-2 Bounded Dynamic Pivoting ($k=2$)
To demonstrate adaptive intelligence to evaluators:
1. Explain the GAP-2 Principle: Rather than looping indefinitely on unresponsive or hardened attack vectors, the engine tracks attempt count $c_i$. Once $c_i \ge k$ (where $k=2$), the candidate is marked `ABANDONED` and execution pivots to the next highest-priority vector.
2. Discuss Vector Behavior:
   - **Port 6379 (Redis)**: In network enumeration, the port is open and answers `+PONG` via raw RESP. In scanner triage, port reachability is classified as metadata, triggering retry bound $k=2$ and pivoting to web exploit paths.
   - **Non-viable Web Vectors**: Unauthenticated LFI access on `/vulnerabilities/fi/` without session tokens or hardened CSP policies fail initial probes, causing the agent to pivot to alternative parameters or recon paths.
3. Highlight Outcome: Candidate is marked `ABANDONED`; engine logs `GAP2_PIVOT`, redirects execution to next candidate, avoiding wasted turns.

### Step 5: Audit Report Verification & Evidence Authenticity
1. In the completed assessment card, click **View Audit Report** (`#/reports`).
2. Verify **Assessment Attribution**: `PROVIDER: CLOUD_HOSTED`, `MODEL: KAGGLE-MODEL-DEEP`, `EVIDENCE TIER: OBSERVED_EXTERNAL`.
3. Inspect **Vulnerability Findings Table**:
   * Distinguish verified exploits from passive configuration observations:
     - **Verified (High Severity)**: Local File Inclusion (`find-lfi-traversal` on `/vulnerabilities/fi/?page=../../../../../../etc/passwd`) with extracted `/etc/passwd` text and authentic SHA-256 hash.
     - **Unconfirmed (Low/Info)**: Passive observations (missing security headers, cookie flags, server banner disclosure).
   * Cryptographic SHA-256 Proof Hash: Show that each finding contains an authentic SHA-256 hash computed over observed HTTP exchanges or command outputs.
4. Export Reports: Click **HTML**, **PDF**, **JSON**, and **SARIF 2.1.0** to demonstrate multi-format standards compliance.

---

## 5. Emergency Fallback & Recovery Procedures

If unforeseen connectivity issues arise during the live demonstration:

| Symptom | Root Cause | Operator Action |
|---|---|---|
| Cloudflare tunnel returns HTTP 530 / Connection Refused | Quick tunnel expired | In Settings > AI Models, update the Cloud Hosted profile API Base with the newly active tunnel URL. |
| Docker daemon unavailable warning in UI | Host Docker service stopped | Run `sudo systemctl start docker` in WSL2 terminal; UI auto-detects recovery on next refresh. |
| Browser UI displays previous run on refresh | LocalStorage retained older run ID | Click **New Assessment** in navigation or append `?run_id=<desired-run-id>` to the URL. |
| Live cloud LLM latency exceeds 30s | Model inference queue load | Select **Lightweight Active Scanner** mode for instant deterministic verification. |
| Run stops at turn budget with status `paused_execution_limit` | Max turn limit reached | Explain to evaluators that this is the safety boundary preventing runaway token spend; show `agents.db` for tool-call trace. |

---

## 6. Authoritative Demonstration Runs Reference

To maintain strict scientific and evaluation integrity, authoritative runs are grouped by target application:

### Target A: Local Vulnerable Lab (OWASP Juice Shop — Phase D Benchmark)
* **Authoritative Autonomous Run**: [`strix_runs/run-9542b3d7/run.json`](file:///home/vinit/AI_VAPT/ai_vapt_framework/strix_runs/run-9542b3d7/run.json)
  - Target: `http://127.0.0.1:3000` (OWASP Juice Shop v17.1.1/v20.3.0, managed via `./juice-shop.sh`)
  - Engine: Autonomous Multi-Agent Core (Docker sandbox `ghcr.io/usestrix/strix-sandbox:1.3.0`, Cloud Hosted Qwen3-Coder `kaggle-model-deep`)
  - Execution Profile: 41 turns, active runtime 1,100.5s, 6 GAP-1 candidates evaluated (5 validated, 1 negative, 0 pivots because all targeted endpoints responded deterministically)
  - Findings: CORS wildcard origin, missing security headers, robots.txt disclosure, sensitive directory access

### Target B: Remote Authorized Lab (DVWA on pentest-ground)
* **Authoritative Autonomous Docker Run**: [`strix_runs/run-16c49dbc/run.json`](file:///home/vinit/AI_VAPT/ai_vapt_framework/strix_runs/run-16c49dbc/run.json)
  - Target: `https://pentest-ground.com:4280/`
  - Engine: Autonomous Multi-Agent Core (Docker sandbox `47f0a143d814`, Qwen3-Coder via Cloudflare tunnel)
  - Tool Calls: 8 authentic model-generated command executions recorded in `strix_runs/run-16c49dbc/.state/agents.db`
  - Status: `paused_execution_limit` (Clean pause upon reaching turn budget)
* **Authoritative Lightweight Scanner Run**: [`strix_runs/run-767ba9da/run.json`](file:///home/vinit/AI_VAPT/ai_vapt_framework/strix_runs/run-767ba9da/run.json)
  - Target: `https://pentest-ground.com:4280/`
  - Engine: Lightweight Active Scanner (Deterministic in-process Python probe)
  - Features: GAP-1 priority queue traversal, 4 GAP-2 failure pivots ($k=2$), verified LFI finding with authentic `/etc/passwd` hash
  - Runtime: 14.8s total duration

### Captured Demonstration Screenshots
* Active Assessment: [`screenshots/active_assessment.png`](file:///home/vinit/AI_VAPT/ai_vapt_framework/screenshots/active_assessment.png)
* New Assessment: [`screenshots/new_assessment.png`](file:///home/vinit/AI_VAPT/ai_vapt_framework/screenshots/new_assessment.png)
* Run History: [`screenshots/history.png`](file:///home/vinit/AI_VAPT/ai_vapt_framework/screenshots/history.png)
* Audit Report: [`screenshots/reports.png`](file:///home/vinit/AI_VAPT/ai_vapt_framework/screenshots/reports.png)
* Model Settings: [`screenshots/settings.png`](file:///home/vinit/AI_VAPT/ai_vapt_framework/screenshots/settings.png)
