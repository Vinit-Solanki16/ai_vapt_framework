# AI-VAPT — Mentor Demonstration Runbook (5-Minute Live Execution)

This guide provides the exact click-by-click sequence to demonstrate the **AI-VAPT Autonomous Decision Engine** to your mentor, covering real AI assessment, scanner integration, GAP-1 quality ranking, GAP-2 failure-recovery pivoting, and fail-closed safety controls.

---

## 1. Quick Verification & Services Status

All required components are pre-verified and active:
- **API Server / Web Console**: `http://127.0.0.1:8000` (FastAPI / Uvicorn active)
- **Local AI Provider**: Ollama active on `http://127.0.0.1:11434` with model `qwen2.5:1.5b` (verified response received, `fallback: false`)
- **Docker Controlled Lab**: Containers `vuln-executor` (port 9090) and `vuln-emulator` (`172.28.0.2:8080`) active
- **Scanners**: Nmap 7.80 and Nuclei v3.11.1 installed and operational

If you ever need to start them from scratch:
```bash
# Terminal 1: Start API server
cd ~/AI_VAPT
uv run uvicorn services.api:app --host 127.0.0.1 --port 8000

# Terminal 2: Ensure Ollama is running with qwen2.5:1.5b
ollama run qwen2.5:1.5b ""
```

---

## 2. Browser Entry Point

Open in Google Chrome or Firefox:
👉 **`http://127.0.0.1:8000/`**

*(Note: If you visited earlier, press `Ctrl + F5` or `Shift + F5` to ensure fresh script cache `?v=20261027_v2`).*

---

## 3. Step-by-Step Live Demo Sequence

### Demo Part 1: System Health & Provenance (30 Seconds)
1. In the left navigation sidebar, click **System Health** (`#/system/health`).
2. Show your mentor the live operational status cards:
   - **Backend Application**: `READY`
   - **Ollama**: `READY` with `qwen2.5:1.5b` installed and reachable
   - **Docker Lab**: `AVAILABLE` — `Docker lab executor healthy (localhost:9090)`
   - **Nmap**: `READY`
   - **Nuclei**: `READY`
   - **Persistence & Research Core**: `PROTECTED`

---

### Demo Part 2: GAP-2 Failure-Recovery Pivoting & Local AI (2 Minutes)
Demonstrates: **Local Ollama inference (`qwen2.5:1.5b`) + GAP-2 Dynamic Decision-Pivoting in the controlled Docker Lab**.

1. In the sidebar, click **New Assessment** (`#/assessment/new`).
2. Keep Assessment Type as: **Scenario Benchmark (Deterministic / Controlled)**.
3. Select Scenario: **Docker lab scenario: failure then pivot to success (`docker_pivot`)**.
4. In **Assessment Configuration**:
   - Assessor: **AI assessment (local Ollama or hosted API)**
   - AI Provider: **Ollama (local, offline default)**
   - Model: **`qwen2.5:1.5b`**
   - Pivot Threshold ($k$): **`2`**
5. Click **START ASSESSMENT**.
6. Observe live execution in the console:
   - **Assessor Stage**: Local Ollama evaluates exploit usability for candidates `docker-vuln-success` and `docker-fail-pivot`.
   - **Executor Stage**:
     - Candidate 1 (`docker-vuln-success`): Hits `/vuln` endpoint $\to$ **SUCCESS** (Attempt 1).
     - Candidate 2 (`docker-fail-pivot`): Hits `/fail` endpoint $\to$ **FAIL_TIMEOUT** (Attempt 1/2).
     - Engine retries candidate 2 $\to$ **FAIL_TIMEOUT** (Attempt 2/2).
     - **GAP-2 Pivot Triggered**: Threshold $k=2$ reached $\to$ Route abandoned $\to$ Safe completion.
7. Click **VIEW RUN** or navigate to **Decision Paths / Pivot Analysis** to inspect the full interactive DAG tree and event trace.

> **Pre-verified Run ID for instant review**: `1c984340-caf2-4793-9e73-6e1503980d7e`

---

### Demo Part 3: Real Web VAPT Assessment & Active Evidence (2 Minutes)
Demonstrates: **Nmap + Nuclei scan + OWASP mapping + Active Non-Destructive Validation + Cryptographic Proof of Concept**.

1. In the sidebar, click **Runs** (`#/runs`).
2. Click on Run ID **`34066064-9dad-4543-bd0e-52598388239b`** (completed live on `https://pentest-ground.com:4280/`).
3. Point out to your mentor:
   - **Asset & Service Discovery**: Real Nmap port 4280 detection.
   - **Vulnerability Ingestion**: Real Nuclei finding `/phpinfo.php`.
   - **OWASP Mapping**: Categorized under **`A01:2021 - Broken Access Control`**.
   - **Active Controlled Validation**: Non-destructive `phpinfo_validator` executed against the target, confirming HTTP 200 and matching 3 server signatures.
   - **Cryptographic Evidence**: SHA-256 evidence hash recorded:
     `a56cbe33fb4f7ea072c5824b6518bc3752bf0b7e5c30df2cbdda179a46267def`.
   - **Remediation & Retest**: Actionable nginx/php configuration fixes generated automatically.

---

### Demo Part 4: Fail-Closed Scope Authorization Rejection (30 Seconds)
Demonstrates: **Strict ethical security controls rejecting unauthorized targets**.

1. In the sidebar, click **New Assessment** (`#/assessment/new`).
2. Switch Assessment Type to: **Web Application (configured authorized scope)**.
3. In the **Target URL** field, enter an unauthorized private/external IP:
   `http://192.168.1.1/` (or `http://unauthorized-target.org/`)
4. Click **Validate**.
5. The UI immediately displays:
   - `❌ REJECTED — TARGET OUT OF SCOPE`
   - Scope Safety: `REJECTED`
   - The "Start Assessment" button is completely disabled.
   - Explains: *External targets require explicit administrative authorization in compliance with strict ethical boundaries.*

---

### Demo Part 5: Audit-Ready Report Download (30 Seconds)
1. On any completed run, click **View Report** (or go to `#/reports`).
2. Show the mentor both the **Structured JSON Artifact** and the **Formatted HTML Security Report**.
3. Point out the **Provable Evidence Tier**, execution trace, and explicit safety disclosures.

---

## 4. Key Pre-Verified Run Reference Table

| Metric | Docker GAP-2 Pivot Run | Live Web VAPT Run |
| :--- | :--- | :--- |
| **Run ID** | `1c984340-caf2-4793-9e73-6e1503980d7e` | `34066064-9dad-4543-bd0e-52598388239b` |
| **Scenario / Mode** | `docker_pivot` / `lab` | `web_target` / `web_controlled` |
| **Target** | `172.28.0.2:8080` (Docker isolated) | `https://pentest-ground.com:4280/` |
| **Assessor** | Local Ollama (`qwen2.5:1.5b`) | Hosted AI (Google Gemini) |
| **Fallback Used?** | **No** (`fallback: false`) | **No** (`fallback: false`) |
| **GAP-1 Assessed** | Yes (Structured reasoning) | Yes (Exploit quality scored) |
| **GAP-2 Pivoted** | **Yes** (2 fails $\to$ pivot $\to$ complete) | Bounded single candidate |
| **Validation Status**| `DOCKER_OBSERVED` | `CONFIRMED` |
| **Evidence Hash** | Verified in execution results | `a56cbe33fb4f7ea0...` |

---

## 5. What This Demonstration Proves vs. Limitations

### What it proves:
1. **Dynamic Bounded Pivoting (GAP-2)**: The engine avoids endless retries on failing candidates by bounding attempts to threshold $k$ and gracefully pivoting to alternative candidates.
2. **Local AI Model Integration (GAP-1)**: Offline local LLMs (`qwen2.5:1.5b`) assess candidate exploitability with genuine rationale without external data leaks.
3. **Safe Real-World VAPT Pipeline**: Scanners (Nmap, Nuclei) interface with active validators and generate cryptographic proof without executing weaponized payloads.
4. **Fail-Closed Target Scoping**: Unauthorized hosts, internal subnets, and private IP ranges cannot be scanned or targeted.

### What is acknowledged as current research boundaries:
- Complex multi-step credential chaining (e.g., privilege escalation from low-privilege user to root across diverse services) is simulated or bounded to isolated container labs.
- Local inference latency with 1.5B/3B models on CPU takes 3–15 seconds per candidate.

