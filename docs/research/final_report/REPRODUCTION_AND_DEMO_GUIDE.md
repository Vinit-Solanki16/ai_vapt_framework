# Master Demonstration & Experiment Reproduction Guide

**Project:** Autonomous AI Framework for Vulnerability Assessment (AI-VAPT)  
**Lead Coordinator:** Technical Operations & Experiment Manager  
**Audit Date:** October 26, 2026  
**Target Review:** October 27, 2026  

---

## 1. Environment Requirements & Pre-Flight Verification

Execute these commands in your Ubuntu WSL2 terminal:

```bash
cd ~/AI_VAPT

# 1. Activate Python virtual environment
source .venv/bin/activate
python --version   # Expected: Python 3.10.12

# 2. Check NVIDIA GPU visibility and memory
nvidia-smi         # Expected: GeForce MX550 (2048 MiB)

# 3. Check local Ollama daemon and installed models
curl -s http://127.0.0.1:11434/api/tags
# Expected: {"models":[{"name":"qwen2.5:1.5b",...}]}

# 4. Check installed security scanners
nmap -v | head -n 1     # Expected: Nmap version 7.80
nuclei -version         # Expected: Nuclei Engine v3.11.1
```

---

## 2. Starting the Application

Launch the FastAPI backend orchestrator:

```bash
cd ~/AI_VAPT
uv run uvicorn services.api:app --host 0.0.0.0 --port 8000
```

Verify service health:
```bash
curl -s http://127.0.0.1:8000/health
# Response: {"status":"healthy"}
```

Open Chrome or Firefox to: **`http://127.0.0.1:8000`**

---

## 3. Step-by-Step Mentor Demonstration Script (15 Minutes)

### Act 1: Architectural Overview & System Health (2 Mins)
- Navigate to **System Health** (`http://127.0.0.1:8000/#/system/health`).
- **Showcase:** Green status badges for Nmap 7.80, Nuclei v3.11.1, and Ollama `qwen2.5:1.5b` with 10-layer CUDA GPU offload.
- **Talking Point:** *"Sir, our framework runs completely locally on consumer laptop hardware. Vulnerability scans and AI assessments execute offline without sending sensitive corporate data to external cloud APIs."*

### Act 2: Fail-Closed Scope Authorization (3 Mins)
- Navigate to **New Assessment** (`http://127.0.0.1:8000/#/assessment/new`).
- Intentionally enter an unauthorized external domain: `https://google.com` or `https://pentest-ground.com:4280`.
- Click **Validate**.
- **Showcase:** Prominent red rejection banner: `REJECTED — TARGET OUT OF SCOPE. Host is not authorized under engagement 'Local Lab Default'.`
- **Talking Point:** *"Ethical and legal compliance is hardcoded at the backend boundary. The engine strictly enforces an authorized whitelist (VAPT_AUTHORIZED_WEB_SCOPES), rejecting unauthorized targets before any network packets are transmitted."*

### Act 3: GAP-1 Exploit Usability Pre-Assessment (3 Mins)
- Set target to `http://127.0.0.1:9191` (or local loopback `http://127.0.0.1:8000`).
- Select **AI Assessor (local Ollama)**, model **`qwen2.5:1.5b`**, threshold **`N=2`**.
- Click **START VAPT ASSESSMENT**.
- **Showcase:** Live console showing Nmap port discovery, Nuclei vulnerability identification, and local Ollama `qwen2.5:1.5b` analyzing exploit code structure and calculating Priority Scores ($S = P \times W$).
- **Talking Point:** *"Traditional tools attack blindly based on CVSS. If an exploit has a 9.8 CVSS but broken code, standard agents waste time on it. Our local LLM evaluates code syntax, prerequisites, and noise before execution, dynamically prioritizing viable exploits."*

### Act 4: GAP-2 Dynamic Decision-Pivoting (4 Mins)
- Navigate to **Decision Paths & Pivot Analysis** (`http://127.0.0.1:8000/#/decision-paths`).
- **Showcase:** Candidate attempt tracking: Candidate 1 fails twice $\rightarrow$ Event `FAILURE_THRESHOLD_EXCEEDED (N=2)` $\rightarrow$ State machine forcibly pivots to Candidate 2 without looping.
- **Talking Point:** *"This solves the infinite loop problem in autonomous security agents. Our LangGraph state machine enforces an attempt ceiling of N=2, mathematically bounding execution time by O(N * |C|)."*

### Act 5: Zero False-Positive Reporting (3 Mins)
- Navigate to **Reports** (`http://127.0.0.1:8000/#/reports`).
- **Showcase:** Multi-Layer Reliability Table:
  - Scanner Detection Layer: 40.0% precision (6 false alarms).
  - Active Validation Layer: **100.0% precision** (0 false alarms, 3 validated true positives).
- **Talking Point:** *"On our ground-truth benchmark, our active validation layer filtered out 100% of scanner false alarms using non-destructive HTTP proofs, elevating precision to 100% without human intervention."*

---

## 4. Benchmark & Experiment Reproduction Commands

To reproduce all quantitative findings reported in the thesis:

```bash
cd ~/AI_VAPT

# 1. Full Regression Test Suite (1,045 tests in ~9 seconds)
uv run --extra dev pytest -q

# 2. Multi-Layer Finding Reliability Benchmark (10-fixture server)
uv run --extra dev python scripts/run_reliability_evaluation.py

# 3. GAP-2 Dynamic Pivoting Benchmark (8 failure topologies)
uv run --extra dev python experiments/gap2_failure_pivot_effectiveness_experiment.py

# 4. Wave 12 Scaling Evaluation Suite (44 multi-candidate runs)
uv run --extra dev python experiments/wave12_thesis_evaluation.py

# 5. Re-generate the Master Research Report DOCX
uv run python3 scripts/generate_docx_report.py
```

---

## 5. Output Artifact Locations

- **Master Research Report (DOCX):** [`docs/research/final_report/AI_VAPT_Comprehensive_Research_Report.docx`](file:///home/vinit/AI_VAPT/docs/research/final_report/AI_VAPT_Comprehensive_Research_Report.docx)
- **Master Research Report (Markdown):** [`docs/research/final_report/AI_VAPT_Comprehensive_Research_Report.md`](file:///home/vinit/AI_VAPT/docs/research/final_report/AI_VAPT_Comprehensive_Research_Report.md)
- **Figures & Screenshots:** [`docs/research/final_report/figures/`](file:///home/vinit/AI_VAPT/docs/research/final_report/figures/)
- **Raw Benchmark Manifest:** [`experiments/research_evaluation/experiment_manifest.json`](file:///home/vinit/AI_VAPT/experiments/research_evaluation/experiment_manifest.json)
- **Executive One-Pager:** [`docs/research/MENTOR_ONE_PAGE_SUMMARY.md`](file:///home/vinit/AI_VAPT/docs/research/MENTOR_ONE_PAGE_SUMMARY.md)
- **Pre-Demonstration Verification:** [`docs/research/FINAL_PRE_MENTOR_VERIFICATION.md`](file:///home/vinit/AI_VAPT/docs/research/FINAL_PRE_MENTOR_VERIFICATION.md)

