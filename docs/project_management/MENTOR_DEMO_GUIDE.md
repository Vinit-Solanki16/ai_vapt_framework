# Mentor Demonstration Guide

**Project:** AI VAPT Decision Engine
**Date:** 2026-09-08
**Version:** 1.0

---

## Project Purpose

This project develops a domain-independent AI decision engine that addresses two research gaps in autonomous vulnerability assessment:

1. **Gap-1:** Pre-execution candidate prioritization (exploit usability scoring)
2. **Gap-2:** Stateful failure-threshold pivoting to avoid repeated dead-end attempts

The engine is demonstrated in the VAPT (Vulnerability Assessment & Penetration Testing) domain via an adapter, but the core logic is domain-independent.

---

## Research Problem

Autonomous action-selection agents that repeatedly fail on a candidate route often loop indefinitely instead of abandoning that route and trying alternatives. This research presents a domain-independent decision and pivot engine that bounds repeated failure by tracking per-candidate attempt counts and pivoting away when a configurable threshold is reached.

---

## Research Contributions

### Gap-1: Pre-execution Prioritization

Candidates are ranked by `priority_score = probability × quality_factor` where:
- `probability` = EPSS score (exploit likelihood)
- `quality_factor` = assessed exploit usability (HIGH=1.0, MEDIUM=0.6, LOW=0.3)

**Finding:** Under the fair per-visit-cap protocol, the priority component = 0 (no independent win). Priority ranking is necessary scaffolding for pivot ordering, not an independently-measured win.

### Gap-2: Bounded Failure-Driven Pivoting (Primary Contribution)

Per-candidate attempt counter + pivot guarantees bounded termination and cuts wasted attempts vs a no-pivot baseline under identical cap.

**Fair benchmark results (4-agent ablation, 30 seeds):**
- VAPT T=2: +77 requests saved (pivot component)
- VAPT T=5: +200 requests saved
- Agnostic sparse T=5: +772 requests saved

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     INPUT LAYER                              │
│  Scan File (Nmap/Nuclei) → Scan Adapter → ActionCandidate[] │
│  Demo Scenarios → Demo Data → ActionCandidate[]             │
│  VAPT Corpus → VAPT Adapter → ActionCandidate[]             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  DECISION ENGINE (LangGraph)                  │
│                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌────────┐│
│  │  ASSESS  │───▶│  EXECUTE │───▶│ EVALUATE │───▶│  PIVOT ││
│  │  (Gap-1) │    │  (attempt)│    │(threshold)│    │(Gap-2) ││
│  └──────────┘    └──────────┘    └──────────┘    └────────┘│
│       │              │                              │       │
│       ▼              ▼                              ▼       │
│   quality_rank   outcome                    next candidate   │
│   (HIGH/MED/LOW) (SUCCESS/FAIL)             or COMPLETE     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     OUTPUT LAYER                             │
│  Decision Trace → Report Generator → JSON / TXT Reports     │
│  Streamlit GUI / FastAPI / CLI                              │
└─────────────────────────────────────────────────────────────┘
```

---

## What the Prototype Demonstrates

1. **Candidate Ranking:** Candidates are sorted by priority_score (probability × quality)
2. **Bounded Execution:** Each candidate is attempted at most N times (configurable threshold)
3. **Failure-Driven Pivot:** After N failures, the engine abandons the candidate and moves to the next
4. **Bounded Termination:** The engine always terminates (no infinite loops)
5. **Evidence Discipline:** Reports clearly label the evidence tier (SIMULATED/OBSERVED_LOCAL/DOCKER_OBSERVED/CONTROLLED VALIDATION)
6. **Safety:** Allowlist-based target validation, fail-closed design

---

## Setup Commands

```bash
# Clone and enter repository
cd /home/vinit/ai_vapt_framework

# Create virtual environment (if not exists)
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ decision_engine/tests/ prototype/tests/ -q
```

---

## Demo Commands

### CLI Demo (Recommended)

```bash
# Primary demo: failure → pivot → success
python -m prototype.cli run --scenario failure_pivot --max-attempts 2

# Success scenario
python -m prototype.cli run --scenario success --max-attempts 2

# Multiple candidates
python -m prototype.cli run --scenario multi_candidate --max-attempts 2

# Single candidate succeeds immediately
python -m prototype.cli run --scenario single_success --max-attempts 2

# All candidates fail (bounded termination)
python -m prototype.cli run --scenario all_fail --max-attempts 2

# Threshold = 1 (immediate pivot)
python -m prototype.cli run --scenario threshold_one --max-attempts 1

# Full VAPT corpus (12 CVEs)
python -m prototype.cli run --scenario corpus --max-attempts 2
```

### GUI Demo

```bash
streamlit run frontend/app.py
```

### Docker Lab Demo (Requires Docker)

```bash
cd lab
docker-compose up -d
cd ..

# Run with Docker target
python -m prototype.cli run --scenario failure_pivot --mode lab --target 172.28.0.2 --port 8080

# Run with loopback target
python -m prototype.cli run --scenario failure_pivot --mode lab --target 127.0.0.1 --port 8080
```

### API Demo

```bash
# Start API
uvicorn services.api:app --reload

# Start a run
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"scenario": "failure_pivot", "max_attempts": 2, "mode": "simulation"}'

# Get report
curl http://localhost:8000/runs/{run_id}/report
```

---

## 5–10 Minute Demonstration Sequence

### Minute 1: Introduction
- Explain the research problem: autonomous agents loop on failed candidates
- State the contribution: bounded failure-driven pivoting (Gap-2)

### Minute 2: CLI Demo
```bash
python -m prototype.cli run --scenario failure_pivot --max-attempts 2
```
- Show candidate ranking (DEMO-WORKER first, then DEMO-DEAD-END)
- Show DEMO-WORKER succeeds immediately
- Show DEMO-DEAD-END fails twice, then pivot
- Show final result: COMPLETED, 3 attempts, 2 pivots

### Minute 3: Explain the Decision Trace
- Walk through the trace:
  - `[INIT]` — Engine initialized
  - `[EXECUTE]` — Attempt 1/2 SUCCESS on DEMO-WORKER
  - `[ADVANCE]` — Move to next candidate
  - `[EXECUTE]` — Attempt 1/2 FAIL on DEMO-DEAD-END
  - `[EXECUTE]` — Attempt 2/2 FAIL on DEMO-DEAD-END
  - `[PIVOT]` — Threshold reached, abandon route
  - `[COMPLETE]` — All candidates processed

### Minute 4: Show the Report
- Open `report_failure_pivot_vapt.txt`
- Point out: Evidence Tier = SIMULATED
- Point out: Per-candidate attempt counts
- Point out: Pivot events (ABANDON, REDIRECT, COMPLETE)

### Minute 5: Show the GUI
```bash
streamlit run frontend/app.py
```
- Select scenario, mode, threshold
- Click "Run Decision Engine"
- Show results: ranking, execution, trace, final result

### Minute 6: Explain Evidence Tiers
- **SIMULATED:** Outcomes from ground-truth labels (demo)
- **OBSERVED_LOCAL:** Outcomes from loopback (127.0.0.1) target
- **DOCKER_OBSERVED:** Outcomes from Docker-isolated emulator (172.28.0.2)
- **CONTROLLED VALIDATION:** Outcomes from live authorized targets (not demonstrated)

### Minute 7: Research Results
- Fair benchmark: +77/+200/+772 requests saved
- Gap-1 priority component = 0 (honest reporting)
- Architecture: domain-independent engine + VAPT adapter

### Minute 8: Safety and Limitations
- Allowlist: {127.0.0.1, 172.28.0.2}
- Fail-closed: non-allowlisted targets rejected
- No external targets contacted
- No real vulnerabilities validated

### Minute 9: Q&A Preparation
See "Questions the Mentor May Ask" below.

---

## Expected Outputs

### CLI Output (failure_pivot)

```
AI VAPT DECISION ENGINE — MENTOR PROTOTYPE
================================================================
Scenario:  failure_pivot
Mode:      simulation
Max Attempts: 2

CANDIDATE RANKING
----------------------------------------
  1. DEMO-WORKER                prob=0.8500  quality=HIGH      score=0.8500
  2. DEMO-DEAD-END              prob=0.7000  quality=LOW       score=0.4550

ENGINE EXECUTION
----------------------------------------
  DEMO-WORKER                Outcome: SUCCESS  (simulated(ground_truth))
  DEMO-DEAD-END              Outcome: FAIL_TIMEOUT  (simulated(ground_truth))
  DEMO-DEAD-END              Outcome: FAIL_TIMEOUT  (simulated(ground_truth))

DECISION TRACE
----------------------------------------
  [INIT]   Engine initialized: 2 candidates, pivot_threshold=2, mode=simulation
  [EXECUTE] Attempt: 1/2  Outcome: SUCCESS  Candidate: DEMO-WORKER
  [ADVANCE] DEMO-WORKER validated. Next candidate.
  [PIVOT]   Redirected to: DEMO-DEAD-END
  [EXECUTE] Attempt: 1/2  Outcome: FAIL_TIMEOUT  Candidate: DEMO-DEAD-END
  [EXECUTE] Attempt: 2/2  Outcome: FAIL_TIMEOUT  Candidate: DEMO-DEAD-END
  [PIVOT]   Threshold reached for DEMO-DEAD-END. Abandoning route.
  [PIVOT]   All candidates processed. Workflow complete.

FINAL RESULT
----------------------------------------
Status:         COMPLETED
Total Attempts: 3
Pivot Count:    2
Candidates Processed: 2 (DEMO-WORKER, DEMO-DEAD-END)
```

---

## Evidence Tiers Explained

| Tier | Source | Isolation | Use Case |
|------|--------|-----------|----------|
| **SIMULATED** | Ground-truth labels | Full | Demo, testing, research |
| **OBSERVED_LOCAL** | Loopback (127.0.0.1) | Host network | Local testing |
| **DOCKER_OBSERVED** | Docker emulator (172.28.0.2) | Container-isolated | Safe observed testing |
| **CONTROLLED VALIDATION** | Live authorized targets | Real network | Authorized testing only |

---

## Safety Limitations

1. **No external scanning:** The system does not contact arbitrary external targets
2. **Allowlist-only:** Only {127.0.0.1, 172.28.0.2} are permitted as lab targets
3. **Fail-closed:** Non-allowlisted targets are rejected before any network access
4. **No real exploitation:** The emulator simulates vulnerable endpoints
5. **No production use:** This is a research prototype

---

## Current Research Results

| Experiment | Result | Interpretation |
|------------|--------|----------------|
| VAPT T=2 | +77 requests saved | Pivot reduces wasted attempts |
| VAPT T=5 | +200 requests saved | Effect scales with threshold |
| Agnostic sparse T=5 | +772 requests saved | Mechanism is domain-independent |
| Priority component | 0 | Gap-1 not independently proven |

---

## Known Limitations

1. **Simulation only for demo:** Real observed mode requires Docker lab
2. **Stubbed assessor:** LLM assessor requires local Ollama
3. **Small corpus:** 12 CVEs for demonstration
4. **Single domain:** VAPT is the only implemented domain
5. **No real-world validation:** No external scanning or exploitation

---

## Questions the Mentor May Ask

### Q: How do you know the pivot mechanism is better than random ordering?
**A:** The fair 4-agent ablation isolates the pivot component as `PRIORITY-ONLY − SMART` under identical per-visit caps. The pivot component is consistently positive (+77/+200/+772) while the priority component = 0.

### Q: Why is the priority component = 0?
**A:** Under the fair per-visit-cap protocol, ordering alone doesn't change total attempts when no agent is candidate-budget-constrained. This is an honest finding — Gap-1 is scaffolding, not an independent win.

### Q: What about real-world targets?
**A:** The safety model prohibits unauthorized scanning. The Docker lab provides container-isolated observed testing. Real authorized scanning is future work.

### Q: How is this different from PentestGPT/Strix?
**A:** Our contribution is the bounded failure-driven pivot mechanism with honest evidence discipline. We don't claim real-world superiority — we claim a specific, validated mechanism.

### Q: What about LLM assessor accuracy?
**A:** The LLM assessor is optional (requires Ollama). The deterministic assessor is the default for reproducibility. LLM accuracy on unseen CVEs is not claimed.

### Q: Can this be extended to other domains?
**A:** Yes — the engine is domain-independent. VAPT is attached via `vapt_adapter.py`. Other domains can be added via new adapters.

---

## Future Work

### Near-term (Post-Mentor Feedback)
- GUI polish based on feedback
- Additional demo scenarios
- Decision trace visualization

### Medium-term (Practical VAPT)
- Nmap/Nuclei scan parsers
- CVE/CVSS/CPE enrichment
- Asset graph visualization

### Long-term (Full Platform)
- Multi-agent orchestration (Planner/Executor/Verifier)
- AI-generated reports
- Authorized real-world integration

---

*Document prepared by Hermes Agent — 2026-09-08*
