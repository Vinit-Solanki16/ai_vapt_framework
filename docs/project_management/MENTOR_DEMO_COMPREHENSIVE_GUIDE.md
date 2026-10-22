# Comprehensive Mentor Demonstration Guide — AI VAPT Platform

**Project:** Autonomous AI VAPT Framework  
**Version:** 1.0 (Mentor Demonstration Ready)  
**Branch:** `feature/mentor-demo-readiness`  
**Date:** 2026-10-22  

---

## 1. Demonstration Objectives

This guide provides a structured walkthrough for demonstrating the AI VAPT platform to academic mentors, thesis committees, and technical evaluators.

The demonstration proves:
1. **GAP-1 Research Contribution:** AI pre-execution exploit quality assessment re-ranks candidate attack paths before execution.
2. **GAP-2 Research Contribution:** LangGraph state-tracked per-candidate attempt counts terminate failure loops at a bounded threshold ($attempts \le N \times max\_attempts$) and dynamically pivot.
3. **Dual-Mode AI Capability:** Seamless switching between fully offline local AI (Ollama `llama3.2:3b`) and hosted online AI (OpenRouter) with zero-cost runtime credential verification.
4. **Configurable Authorized Target Scopes:** Exact host-and-port authorization (`VAPT_AUTHORIZED_WEB_SCOPES`), fail-closed DNS validation, and explicit operator acknowledgement.
5. **Scanner Integration & Evidence Discipline:** Bounded Nmap/Nuclei discovery, split vulnerability vs asset discovery, and honest evidence tiering without fabricated exploits.

---

## 2. Environment Preparation

### Option A: Standard Web Operations Console (Recommended)
```bash
# 1. Activate environment
source .venv/bin/activate  # or source venv/bin/activate

# 2. Start the API & Web Console
uvicorn services.api:app --reload --port 8000
```
Open **`http://localhost:8000`** in any web browser.

### Option B: Streamlit Dashboard
```bash
streamlit run frontend/app.py
```
Open **`http://localhost:8501`**.

### Option C: Standalone CLI (Air-Gapped / Headless)
```bash
python -m prototype.cli --help
```

---

## 3. Four-Part Demonstration Script

### Part 1: Offline Deterministic Research Validation (GAP-1 & GAP-2)

**Goal:** Demonstrate the theoretical and empirical core of the thesis without any cloud or local LLM dependencies.

1. **In the Web Console (`http://localhost:8000`):**
   - Navigate to **New Assessment** in the left sidebar.
   - Select **Execution Mode:** `Simulation`.
   - Select **Scenario:** `failure_pivot`.
   - Select **Assessor Mode:** `Deterministic (offline, reproducible)`.
   - Set **Pivot Threshold (N):** `2`.
   - Click **Start Assessment**.

2. **What to Show the Mentor:**
   - **Candidate Prioritization (GAP-1):** Show that `DEMO-WORKER` (high quality) is ranked ahead of `DEMO-DEAD-END` (poor quality).
   - **Execution & Pivot (GAP-2):**
     - `DEMO-WORKER` succeeds on Attempt 1 $\rightarrow$ marked completed $\rightarrow$ advances.
     - `DEMO-DEAD-END` fails Attempt 1 $\rightarrow$ retried Attempt 2 $\rightarrow$ reaches threshold (2) $\rightarrow$ **DYNAMICALLY PIVOTS**.
     - Engine terminates cleanly with 3 total attempts ($3 \le 2 \times 2$), preventing an infinite loop.
   - **Decision Trace:** Walk through the timestamped trace events showing state changes and counter resets.

3. **Terminal Verification (Immediate CLI Backup):**
   ```bash
   python -m prototype.cli run --scenario failure_pivot --max-attempts 2
   ```

---

### Part 2: Dual-Mode AI Assessment (Offline vs Online)

**Goal:** Show how the operator explicitly controls whether AI inference runs locally or via hosted cloud models.

1. **Offline Mode (Ollama):**
   - On the **New Assessment** screen, select **Assessor Mode:** `AI (local Ollama or hosted API)`.
   - Select **AI Provider:** `Ollama (local, offline)`.
   - Observe the baseline model `llama3.2:3b`.
   - If Ollama is running (`ollama serve`), the model scores candidates using local inference.
   - If Ollama is stopped or the model is missing, observe the **Honest Fallback**:
     The system does not crash or claim fake readiness; it executes deterministic fallback, tagging provenance with `fallback=True` and reporting the exact classified cause (`Ollama service is not reachable`).

2. **Online Mode (OpenRouter Runtime Key Setup):**
   - Select **AI Provider:** `OpenRouter (hosted API)`.
   - Notice the **OpenRouter Setup** card appears dynamically below the form.
   - Key security features to point out:
     - The key is entered into memory for this tab only; it is **never saved to `.env` or disk**.
     - Click **Validate Connection**: performs a zero-token model-catalogue check without spending user credits.
     - Select from free-tier or production models (`meta-llama/llama-3.3-70b-instruct`).
   - If an invalid key or no key is provided, the run gate blocks execution with an actionable warning.

---

### Part 3: Authorized Web Target Scoping & Acknowledgement

**Goal:** Show that the system strictly prevents out-of-scope scanning while supporting configurable authorized targets.

1. **Testing an Out-of-Scope Target:**
   - Switch to the **Web Application** tab under New Assessment.
   - Enter an arbitrary unauthorized domain: `http://example.com:80`.
   - Click **Validate**.
   - Observe: **`❌ REJECTED — TARGET OUT OF SCOPE`**. The start button is strictly disabled, and clear administrator instructions explain how to authorize targets.

2. **Testing an Authorized External Scope:**
   - Stop the backend and start it with an authorized scope:
     ```bash
     VAPT_AUTHORIZED_WEB_SCOPES=pentest-ground.com:4280 uvicorn services.api:app --reload --port 8000
     ```
   - In the UI, enter: `http://pentest-ground.com:4280`.
   - Click **Validate**.
   - Observe:
     - **`✅ AUTHORIZED EXTERNAL TARGET`**.
     - Destination IP is resolved and verified as public.
     - Notice the **Authorization Acknowledgement** checkbox appears:
       *"I confirm that pentest-ground.com:4280 is an exact target I am personally authorized to assess..."*
     - If unchecked, the start button is safely gated.
     - Changing the URL immediately resets the acknowledgement.

---

### Part 4: Evidence Integrity & Multi-Format Reporting

**Goal:** Demonstrate enterprise reporting and research transparency.

1. **Navigate to Reports (`#/reports`) in the Web Console:**
   - Select any completed run.
   - Switch between report formats:
     - **JSON:** Complete machine-readable audit trail including candidate metadata and attempt counts.
     - **HTML:** Formatted executive summary with severity breakdowns and timeline.
     - **Markdown & Text:** Clean, exportable documentation.
2. **Key Evidence Properties to Highlight:**
   - **Evidence Tier:** Displayed as `SIMULATED` (for ground-truth runs) or `OBSERVED_LOCAL` (for real web scans).
   - **No Fabricated Exploits:** For web assessments, scanner findings are honestly labeled `SCANNER-DETECTED` and `VALIDATION NOT AVAILABLE`, proving the platform never fabricates execution outcomes.
   - **AI Provenance:** Explicitly records whether the model answered or fallback was used, naming the model and latency.

---

## 5. Mentor Q&A Cheat Sheet

| Question Mentor Might Ask | Authoritative Answer |
|---|---|
| *"Can your system attack arbitrary public websites?"* | **No, by design.** The system enforces strict fail-closed host-and-port allowlists (`VAPT_AUTHORIZED_WEB_SCOPES`). Unconfigured hosts, lookalike domains, and out-of-scope ports are blocked before any scanner executes. |
| *"What happens if an LLM is hallucinating or unavailable?"* | The platform includes a deterministic fallback assessor. Every candidate evaluation records its provenance (`source`, `provider`, `model`, `fallback`), so hallucinated or fallback assessments are never disguised as live LLM outputs. |
| *"How is GAP-2 proven mathematically?"* | For $N$ candidates with threshold $M$, total execution attempts are guaranteed to be bounded by $\sum_{i=1}^N \min(attempts_i, M) \le N \times M$. The state machine in `decision_engine/core/engine.py` resets attempt counts per candidate upon pivot. |
| *"Are scanner results considered successful exploits?"* | **No.** The platform maintains a strict boundary between asset discovery, vulnerability candidates, and confirmed execution evidence. Scanner findings without sandboxed exploit validation are marked `VALIDATION NOT AVAILABLE`. |
