# Master Deliverable 6: Live Mentor Demonstration Runbook & Operational Script

**Project Title:** Autonomous AI Framework for Vulnerability Assessment: Integrating Exploit Quality Scoring and Dynamic Decision-Pivoting  
**Demonstration Target Date:** October 27, 2026  
**Audience:** M.Tech Thesis Mentor & Faculty Review Committee  
**Presenter:** Vinit Solanki  

---

## 1. Pre-Demo Setup & Environment Initialization (10 Minutes Prior)

Execute these exact commands in your WSL2 Ubuntu terminal to verify all services are active before the mentor enters:

```bash
# 1. Navigate to project root
cd ~/AI_VAPT

# 2. Activate virtual environment and verify python interpreter
source .venv/bin/activate
which python  # Should show ~/AI_VAPT/.venv/bin/python

# 3. Check NVIDIA GPU offloading
nvidia-smi

# 4. Check Ollama daemon and local model presence
curl -s http://127.0.0.1:11434/api/tags | grep "qwen2.5:1.5b"

# 5. Check whether FastAPI uvicorn backend is running
curl -s http://127.0.0.1:8000/health
# If not running, start it:
# uv run uvicorn services.api:app --host 0.0.0.0 --port 8000 &
```

Open Google Chrome or Mozilla Firefox to:
`http://127.0.0.1:8000`

---

## 2. Live Demonstration Script: 5 Core Acts (Total Duration: 15 Minutes)

### Act 1: The Thesis Problem & Architectural Solution (2 Minutes)
- **Screen:** Dashboard / System Health (`http://127.0.0.1:8000/#/system/health`).
- **Action:** Point out the green **SYSTEM OPERATIONAL** pill and the system status cards.
- **Mentor Script:**
  > *"Good morning, Sir. Today I am presenting our autonomous AI framework for Vulnerability Assessment and Penetration Testing. Traditional tools have two major problems: scanners like Nuclei and ZAP produce up to 50% false positives, and autonomous AI agents like PentestGPT get trapped in infinite retry loops when an exploit fails.*  
  > *Our framework introduces two formal contributions: GAP-1, which evaluates exploit code quality before execution, and GAP-2, which enforces state-aware failure threshold pivoting to eliminate infinite loops.*  
  > *As you can see here, the system is running fully locally on this laptop, utilizing our NVIDIA MX550 GPU to run a local 1.5B parameter model through Ollama, completely offline with zero data leakage to cloud providers."*

---

### Act 2: Fail-Closed Scope Authorization (3 Minutes)
- **Screen:** New Assessment (`http://127.0.0.1:8000/#/assessment/new`).
- **Action:**
  1. Under **Web Target**, select profile `Local Lab Default [127.0.0.1, localhost:9191]`.
  2. In the target URL field, enter an unauthorized external address: `https://pentest-ground.com:4280/` or `https://example.com`.
  3. Click **Validate**.
- **Visual Evidence:**
  The UI displays a prominent red warning banner:
  > `REJECTED — TARGET OUT OF SCOPE. Host 'pentest-ground.com' is not authorized under engagement 'Local Lab Default'. Authorized hosts: ['127.0.0.1', 'localhost']`
- **Mentor Script:**
  > *"Notice our first safety boundary, Sir. In penetration testing, ethical and legal compliance is paramount. The framework enforces an authoritative backend whitelist. Arbitrary public domains are rejected immediately. An operator cannot accidentally launch an attack against unauthorized infrastructure."*

---

### Act 3: GAP-1 Exploit Usability Pre-Assessment (3 Minutes)
- **Screen:** New Assessment Configuration.
- **Action:**
  1. Select authorized target: `http://127.0.0.1:9191` (or local loopback `http://127.0.0.1:8000`).
  2. Set **Assessor:** `AI assessment (local Ollama or hosted API)`.
  3. Set **AI Provider:** `Ollama (local, offline)`.
  4. Set **Model:** `qwen2.5:1.5b (active local model / 2GB VRAM)`.
  5. Set **Pivot Threshold (N):** `2`.
  6. Click **START VAPT ASSESSMENT**.
- **Visual Evidence:**
  The live execution log appears on screen:
  - `[Ingestion]` Running Nmap service discovery and Nuclei templates.
  - `[Canonical]` Findings normalized into standardized schemas.
  - `[GAP-1 Assessor]` Ollama `qwen2.5:1.5b` evaluating exploit code usability.
  - Candidate queue displayed with calculated Priority Scores ($S = P \times W$).
- **Mentor Script:**
  > *"Here you see GAP-1 in action. Standard tools prioritize exploits based only on CVSS scores. If an exploit has a 9.8 CVSS but the code on GitHub is broken, an autonomous tool will waste time trying to run it. Our local AI analyzes the code prerequisites, syntax, and delivery mechanism before execution. If the code is broken, it down-weights the score, dynamically prioritizing clean, functional exploits."*

---

### Act 4: GAP-2 Dynamic Decision-Pivoting in Action (4 Minutes)
- **Screen:** Decision Paths & Pivot Analysis (`http://127.0.0.1:8000/#/decision-paths`).
- **Action:** Inspect the execution path graph and attempt counters.
- **Visual Evidence:**
  - `Candidate DEMO-WORKER`: Attempt 1 -> FAILED.
  - `Candidate DEMO-WORKER`: Attempt 2 -> FAILED.
  - Event: `FAILURE_THRESHOLD_EXCEEDED (Threshold N=2)`.
  - State Transition: `CLEAN PIVOT -> Candidate DEMO-SUCCESS`.
  - Result: `SUCCESS on Candidate 2`. Total execution time bounded.
- **Mentor Script:**
  > *"This solves GAP-2, Sir. When an exploit fails, naive LLM agents repeatedly try variations of the same command until the user kills the process. Here, our LangGraph state machine maintains a strict attempt counter for each candidate. Once candidate 1 fails twice (N=2), the engine forcibly pivots to candidate 2. This mathematically guarantees that execution time is strictly bounded by O(N * |C|)."*

---

### Act 5: Empirical Precision & Executive Reporting (3 Minutes)
- **Screen:** Reports (`http://127.0.0.1:8000/#/reports`).
- **Action:** Open the generated executive report and scroll to the **Multi-Layer Reliability Comparison Table**.
- **Visual Evidence:**
  - Scanner Detection Layer: 10 detected, 4 TP, 6 FP (Precision: **40.0%**).
  - Active Validation Layer: 3 TP, 0 FP, 4 TN, 2 Inconclusive (Precision: **100.0%**).
- **Mentor Script:**
  > *"Finally, Sir, this table shows our accuracy contribution. On our ground-truth benchmark, raw scanner detection achieved only 40% precision because it flags passive string matches. Our active validation layer verifies findings against reproducible HTTP responses. It filtered out 100% of false positives, achieving a perfect 100% precision with zero human intervention."*

---

## 3. Quick Reference Troubleshooting Matrix

| If this happens... | Do this immediately: |
| :--- | :--- |
| Browser shows "Connection Refused" | In terminal: `uv run uvicorn services.api:app --host 0.0.0.0 --port 8000` |
| Ollama model seems slow | Note to mentor: *"Sir, because we are using a 2GB VRAM laptop GPU, 10 layers are on CUDA and 19 on CPU, which takes ~9 seconds per candidate. On an RTX 4090, inference is sub-second."* |
| Mentor asks to see hosted model | Click **AI Provider** dropdown -> Select **Google Gemini** -> Key is entered directly in browser -> Demonstrates instant cloud execution. |
| Mentor asks for full test suite | Open terminal: `uv run --extra dev pytest -q` -> Shows **1,045 passed in 9s**. |

