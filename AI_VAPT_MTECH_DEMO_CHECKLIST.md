# AI-VAPT v1.7.0 RC1 — M.Tech Academic Demonstration Checklist

This step-by-step checklist guides operators through a reproducible live demonstration of the **AI-VAPT (Autonomous AI Vulnerability Assessment & Penetration Testing)** platform for academic defense committees, technical evaluators, and security engineers.

---

## 1. Pre-Demo Environment & System Checks

Before beginning the demonstration, verify host system prerequisites:

```bash
# 1. Verify OS environment (Linux / WSL2)
uname -s -r -m

# 2. Verify Python 3.12+ and virtual environment
python3 --version
.venv/bin/python --version

# 3. Verify Docker engine is running
docker info | grep -E "(Server Version|Containers|Operating System)"

# 4. Verify required local ports (8000 for AI-VAPT, 3000 for Juice Shop) are free or cleanly bound
ss -tulpn | grep -E ":(8000|3000)"
```

- [ ] Linux or WSL2 Ubuntu 22.04+ operational.
- [ ] Python 3.12 virtual environment active.
- [ ] Docker daemon active and accessible without sudo.
- [ ] Network ports 8000 and 3000 available.

---

## 2. Docker Sandbox & Vulnerable Lab Startup

Start the local target application (OWASP Juice Shop) using the managed lab launcher:

```bash
# Start OWASP Juice Shop lab container (automatically establishes dual bindings on 127.0.0.1:3000 and Docker bridge 172.17.0.1:3000)
./juice-shop.sh start

# Verify container status and HTTP responsiveness
./juice-shop.sh status
```

*(Manual alternative without script: `docker run -d --name juice-shop -p 127.0.0.1:3000:3000 -p 172.17.0.1:3000:3000 bkimminich/juice-shop:latest`)*

- [ ] Target container `juice-shop` active on `http://127.0.0.1:3000`.
- [ ] Target bound strictly to loopback (`127.0.0.1`) and Docker bridge (`172.17.0.1`), **not** exposed to external networks.
- [ ] Sandbox base image `ghcr.io/usestrix/strix-sandbox:1.3.0` present in local Docker cache.

---

## 3. AI-VAPT Operations Console Startup

Launch the backend API and single-page web console:

```bash
# Launch via unified application launcher (or ./start.sh)
./ai-vapt.sh start

# Verify service status, listening socket, and runtime readiness
./ai-vapt.sh status
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/system/readiness | jq .status
```

- [ ] `./ai-vapt.sh start` executes cleanly, waits for `/health`, and reports PID.
- [ ] `/health` endpoint returns `{"status": "healthy"}`.
- [ ] Open browser to **`http://localhost:8000`**.

---

## 4. Cloud Hosted Model Endpoint Availability Check

Verify that the remote Qwen3-Coder inference server and Cloudflare Quick Tunnel are online (using your active session tunnel URL):

```bash
# Test remote model server health via API preflight (replace with your active tunnel URL)
ACTIVE_TUNNEL_URL="[temporary Cloudflare tunnel endpoint]/v1"

curl -s -X POST http://127.0.0.1:8000/providers/cloud_hosted/validate \
  -H "Content-Type: application/json" \
  -d "{\"api_base\": \"${ACTIVE_TUNNEL_URL}\", \"model\": \"kaggle-model-deep\"}"
```

- [ ] Remote inference tunnel is reachable (HTTP 200).
- [ ] Model `kaggle-model-deep` (Qwen3-Coder-30B) returns successful validation.

> [!NOTE]
> Cloudflare Quick Tunnel URLs are ephemeral and change each session. If the remote tunnel server is offline or unreachable, immediately switch to **Section 13: Demonstration Fallback Plan**.

---

## 5. Provider & Profile Selection (Web Console)

In the AI-VAPT Web Console (`http://localhost:8000`):

1. Navigate to the **Settings / Providers** tab (`#/settings`).
2. Select **Cloud Hosted** provider.
3. Configure or verify an active profile depending on installation state:
   - **Fresh Installation (No pre-existing profile):**
     1. Click **Add Profile**.
     2. Name: `Cloud Qwen3 Session`
     3. Endpoint Base: `[temporary Cloudflare tunnel endpoint]/v1` (your active session tunnel URL)
     4. Model: `kaggle-model-deep`
     5. Context Window: `131,072` tokens
     6. Click **Save Profile** and select **Activate**.
   - **Existing Installation (Pre-registered profile):**
     1. Verify the listed profile displays `Active`.
     2. If the ephemeral tunnel URL has rotated since the last session, update the **Endpoint Base** to match the current tunnel URL.
4. Click **Validate Credentials** to demonstrate live preflight verification.
5. Highlight to evaluators that API keys entered in the UI are held in memory only (`runtime_credentials.py`) and never written to disk.

---

## 6. Autonomous Scan Creation & Configuration

1. Navigate to the **New Assessment** tab.
2. Enter Target URL: **`http://127.0.0.1:3000`**
3. Select Execution Engine: **Autonomous (Strix Multi-Agent Core)**.
4. Select Provider: **Cloud Hosted** (`kaggle-model-deep`).
5. Select Scan Depth / Mode: **Quick** (`quick`).
6. Set Turn Budget: **25 turns** (demonstrating execution budget control) or **45 turns** (for full queue traversal).
7. Click **Launch Assessment**.

---

## 7. Live Strix Multi-Agent Tool Execution Display

Direct the evaluation committee's attention to the **Active Assessment** monitoring dashboard:

- **SSE Real-Time Stream:** Live streaming turn-by-turn agent reasoning and tool dispatch without page polling.
- **Agent Reasoning:** Show the agent invoking `think` tool to structure hypotheses before running commands.
- **Docker Tool Execution:** Show `exec_command` dispatching `curl` commands inside the isolated Kali sandbox (`ghcr.io/usestrix/strix-sandbox:1.3.0`).
- **Loopback Rewriting:** Note how `http://127.0.0.1:3000` is dynamically rewritten to `http://host.docker.internal:3000` so the sandbox container can safely probe the host-hosted target.

---

## 8. GAP-1 Attack Surface Triage Demonstration

Explain the **Guided Attack Planning (GAP-1)** triage engine:

1. Point to the **Candidate Queue** in the UI.
2. Show that reconnaissance identified the target stack as `GENERIC_WEB` (Node.js Express 4.19.2 / Angular 17.0.0).
3. Walk through the 6 prioritized attack vectors:
   - Priority 1 (0.724): `sensitive-path-robotstxt`
   - Priority 2 (0.720): `robots-txt-exposure`
   - Priority 3 (0.552): `cors-misconfiguration`
   - Priority 4 (0.480): `client-js-attacks`
   - Priority 5 (0.340): `missing-security-headers`
   - Priority 6 (0.264): `csp-bypass`
4. Explain how GAP-1 injects this queue directly into the autonomous coordinator's root task to focus LLM reasoning.

---

## 9. GAP-2 Adaptive Tracking & Assessment Integrity Architecture

Explain the **GAP-2 Adaptive State Machine** and **Empirical Assessment Integrity** to the committee with full academic transparency:

1. **Attempt & Threshold Tracking:** Point to `control/gap_state.json`. Show that each candidate tracks attempts with a bounded threshold ($k \le 2$).
2. **Negative Confirmation:** Highlight Candidate 4 (`client-js-attacks`). Show how the model inspected `main.js` and confirmed the absence of DOM sinks (`innerHTML`, `document.write`, `eval`), recording `no_issue_found` without hallucinating an exploit.
3. **Queue Exhaustion Semantics:** Explain that when an investigation reaches the bounded threshold ($k=2$) and the candidate queue has no further alternative routes, GAP-2 logs `GAP2_ABANDON` with `pivot_executed = False` and 0 pivots, preventing synthetic pivot loops or confusing `pivoted to None` messages.
4. **Completion Guard Enforcement:** Explain that if the agent attempts to call `finish_scan` prematurely, the completion guard rejects termination and returns the remaining uninvestigated candidates (as forensically demonstrated at Turn 25 of `run-9542b3d7`).
5. **Documented Fallback Limitation:** State explicitly to the evaluators:
   > *"In the Phase D autonomous run on Juice Shop, all targeted endpoints responded deterministically on the first probe, so zero alternative-probe fallback pivots were triggered. Bounded fallback pivoting ($k=2$, 4 pivots) was separately validated under the deterministic active scanner engine (`run-767ba9da`)."*

---

## 10. Finding, Evidence & Assessment Integrity Audit

Navigate to the **Findings & Evidence** panel and explain AI-VAPT's strict truth-in-reporting architecture:

- **Observation vs. Vulnerability Distinction:** 
  - Passive reconnaissance discoveries (e.g. `/robots.txt` disclosing `/ftp`, public `/.well-known/security.txt` per RFC 9116, public `/api-docs/` Swagger specification, `Access-Control-Allow-Origin: *` without credentials, missing CSP) are classified as **`VALIDATED_OBSERVATION`** with cyan badges (`ℹ OBSERVATION`), **never** falsely escalated to `VERIFIED_VULNERABILITY`.
  - Emphasize to the committee: *a scanner that claims finding a public robots.txt or an unconfigured CSP header is a Critical/High vulnerability is misleading. AI-VAPT requires verified exploitability before assigning vulnerability status.*
- **Scan Category Matrix Audit:**
  - Demonstrate the honest category matrix: categories where zero probes executed (e.g. SQL Injection, SSRF, SSTI, Prototype Pollution, Code Injection) are audited as **`NOT TESTED (0 executed)`**.
  - Partially tested categories (e.g. Version SCA 3/12, Configuration 4/22) are audited as **`PARTIALLY TESTED`**.
  - The label **`PASSED`** is reserved strictly for categories where all configured checks execute and produce zero findings.
- **Evidence Domain Isolation:** Point out that candidate evidence is strictly domain-isolated (e.g. CSP candidates never cross-contaminate with CORS coverage evidence).
- **Cryptographic Hash Ledger:** Show that findings include SHA-256 evidence digests verifying genuine HTTP response bytes rather than synthetic mock text.

---

## 11. Multi-Format Report Export Demonstration

Show the reporting capabilities:

1. Click **View Executive Report** in the web console.
2. Point out the Executive Summary, Methodology, and Technical Analysis autonomously drafted by Qwen3-Coder.
3. Click **Export SARIF 2.1.0** — demonstrate standard machine-readable output compliant with GitHub Advanced Security and CI/CD ingestion.
4. Click **Export PDF** — display the formatted executive PDF summary.

---

## 12. Clean Shutdown & Artifact Preservation

Conclude the demonstration by showing clean platform teardown:

```bash
# Gracefully stop AI-VAPT services
./stop.sh

# Confirm process is terminated and port 8000 is freed
ss -tulpn | grep 8000 || echo "Port 8000 successfully freed"

# Verify all scan artifacts, database records, and logs are strictly preserved
ls -la strix_runs/run-9542b3d7/
```

- [ ] `./stop.sh` cleanly terminates background processes.
- [ ] Network ports freed.
- [ ] Run artifacts in `strix_runs/` remain 100% intact.

---

## 13. Demonstration Fallback Plan (Contingency Scenarios)

If unexpected network or infrastructure issues arise during the live defense:

### Contingency A: Cloudflare Quick Tunnel or Remote Model Server Drop
1. **Symptom:** Cloud Hosted validation returns timeout or connection error.
2. **Action:** Switch to **OpenRouter Provider** in Web Settings:
   - Provider: **OpenRouter**
   - Model: **`nvidia/nemotron-3.5-super-vl:free`** or **`meta-llama/llama-3.3-70b-instruct:free`**
   - Enter `OPENROUTER_API_KEY` (held in-memory).
   - *Academic qualification:* State clearly to evaluators that OpenRouter models have live preflight API benchmark validation, but the authoritative Phase D reference run was driven by Cloud Hosted Qwen3-Coder.

### Contingency B: Total Internet Outage (Offline Defense)
1. **Symptom:** No internet access in the demonstration room.
2. **Action:** Run the **Lightweight Active Scanner Mode**:
   ```bash
   # Execute deterministic active scan against local Juice Shop
   strix -m lightweight -t http://127.0.0.1:3000 --max-turns 20
   ```
3. **Demonstration Value:** This offline mode executes 100% locally with zero external network access, demonstrating rapid GAP-1 triage, GAP-2 bounded fallback pivoting ($k=2$, 4 pivots demonstrated in `run-767ba9da`), verified LFI checks, and instant report generation.
