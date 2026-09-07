# PROTOTYPE DEMONSTRATION PLAN — ai_vapt_framework

**Purpose:** Create a polished, working prototype for M.Tech mentor demonstration.
**Research boundary:** Implementation frozen; no source/test/dataset/benchmark changes.
**Demo boundary:** UI wrapper only; real engine exposed; no fake second implementation.

---

## A. EXISTING COMPONENTS REUSABLE WITHOUT MODIFICATION

| Component | Path | Reuse in demo |
|-----------|------|---------------|
| Domain-independent engine | `decision_engine/core/engine.py` | Direct import: `run_engine()`, `initial_state()`, `build_graph()` |
| Domain-independent executor | `decision_engine/core/executor.py` | Direct import: `Executor(mode="simulation")` |
| Domain-independent assessor | `decision_engine/core/assessor.py` | Direct import: `deterministic_assessor`, `assess_candidates()` |
| Domain-independent schemas | `decision_engine/core/schemas.py` | Direct import: `ActionCandidate`, `candidate_from_dict()`, `Outcome`, `QualityRank` |
| VAPT adapter | `decision_engine/adapters/vapt_adapter.py` | Optional import for corpus-backed demo data |
| Fair benchmark simulation logic | `decision_engine/benchmarks/fair_benchmark.py` | Optional reuse for DUMB/SMART comparison in demo |
| VAPT fair benchmark | `decision_engine/benchmarks/fair_vapt_benchmark.py` | Optional reuse for VAPT corpus comparison |
| Existing datasets | `data/poc_corpus/labels.json`, `datasets/epss_corpus_enrichment.json` | Optional corpus-backed demo scenarios |
| Existing lab emulator | `lab/emulator/app.py` | Optional local loopback mode (127.0.0.1) |

**Rule:** The demo must import and call these components. It must NOT reimplement engine logic.

---

## B. MINIMAL PROTOTYPE LAYER REQUIRED

Create two new files only:

1. `prototype_demo_data.py`
   - Hardcoded demo scenarios as lists of dicts.
   - Each scenario maps directly to `candidate_from_dict()` inputs.
   - No engine logic; pure data.

2. `prototype_demo.py`
   - Streamlit entry point.
   - Imports real engine/executor/assessor/schemas.
   - Provides sidebar controls: max_attempts, mode (simulation only by default).
   - Provides scenario buttons: Success, Failure→Pivot, Multi-Candidate, DUMB vs SMART.
   - Visualizes: candidate ranking, execution timeline, attempt counters, pivot events, final status, request comparison.

**No other files need modification.**

---

## C. EXISTING STREAMLIT APP — EXTEND OR SEPARATE?

**Recommendation: SEPARATE entry point.**

Reasoning:
- `app.py` is tightly coupled to the original VAPT prototype (`core/agent_graph.py`, `core/scanner.py`, `core/report.py`).
- The research contribution lives in `decision_engine/`.
- Mixing both in one UI risks conflating the original prototype with the generalized engine during demonstration.
- A separate `prototype_demo.py` keeps the research contribution clearly visible and avoids accidental modification of `app.py` dependencies.

If integration is desired later, `app.py` can link to `prototype_demo.py` via a button, but this is optional.

---

## D. EXACT USER FLOW FOR MENTOR DEMONSTRATION

1. **Start:** Mentor sees Streamlit page titled "Decision Engine Prototype Demo".
2. **Sidebar:** 
   - Pivot threshold slider (1–5, default 2).
   - Execution mode: simulation (default, selected) / local loopback (optional, disabled by default).
   - Safety notice: "Default simulation. No external targets."
3. **Main area:** Four scenario cards/buttons:
   - Scenario 1: Successful candidate
   - Scenario 2: Repeated failure → pivot
   - Scenario 3: Multiple candidates
   - Scenario 4: DUMB vs SMART comparison
4. **Interaction:** Click a scenario button → engine runs → results appear below.
5. **Results per scenario:**
   - Candidate table: id, probability, quality_rank, priority_score.
   - Execution timeline: ordered list of attempts with outcomes.
   - Attempt counter: per-candidate count vs threshold.
   - Pivot events: highlighted when threshold reached.
   - Final status: SUCCESS or COMPLETED.
6. **Scenario 4 extra:** side-by-side request counts for DUMB, PIVOT-ONLY, PRIORITY-ONLY, SMART.

---

## E. EXACT DEMO SCENARIOS

### Scenario 1: Successful candidate
**Goal:** Show that success advances immediately without retries.
**Candidates:**
- DEMO-WIN: probability=0.9, ground_truth=SUCCESS
- DEMO-FAIL: probability=0.1, ground_truth=FAIL_TIMEOUT
**Expected behavior:**
- DEMO-WIN assessed, executed once → SUCCESS → pivot/advance → COMPLETED.
- DEMO-FAIL never attempted.
**Key message:** Pivot is not just about failure; success also advances cleanly.

### Scenario 2: Repeated failure → threshold → pivot
**Goal:** Show Gap-2 bounded failure-threshold pivot.
**Candidates:**
- DEMO-FAIL-A: probability=0.5, ground_truth=FAIL_TIMEOUT
- DEMO-SUCCESS-B: probability=0.7, ground_truth=SUCCESS
**Config:** max_attempts=2
**Expected behavior:**
- DEMO-FAIL-A attempted twice → FAIL_TIMEOUT ×2 → pivot at attempt 2 → advance to DEMO-SUCCESS-B.
- DEMO-SUCCESS-B assessed, executed once → SUCCESS → COMPLETED.
**Key message:** Agent does not loop forever; it abandons after threshold.

### Scenario 3: Multiple candidates
**Goal:** Show bounded termination across a larger candidate set.
**Candidates:**
- DEMO-F1: FAIL_SYNTAX
- DEMO-F2: FAIL_DEPENDENCY
- DEMO-F3: FAIL_TIMEOUT
- DEMO-SUCCESS: SUCCESS
**Config:** max_attempts=2
**Expected behavior:**
- Each failing candidate attempted exactly twice → pivot → next.
- DEMO-SUCCESS attempted once → SUCCESS → COMPLETED.
- Total attempts: 2+2+2+1 = 7.
**Key message:** Bounded termination guaranteed; no runaway loops.

### Scenario 4: DUMB vs SMART comparison
**Goal:** Show quantitative difference between no-pivot and pivot strategies.
**Candidates:** Same 4 candidates as Scenario 3.
**Agents:** DUMB (no pivot, cycle to budget), PIVOT-ONLY (random order + pivot), PRIORITY-ONLY (priority order, no pivot), SMART (priority order + pivot).
**Config:** max_attempts=2, cap T=2.
**Expected behavior:**
- DUMB revisits failures; highest request count.
- SMART abandons after 2 failures; lowest request count.
- PRIORITY-ONLY same request count as DUMB under fair cap (priority component = 0).
- PIVOT-ONLY lower than DUMB but higher than SMART.
**Key message:** Pivot component is the separable mechanism; priority alone does not reduce total attempts under identical cap.

---

## F. REQUIRED SAMPLE/DEMO DATA

All data is hardcoded in `prototype_demo_data.py`:

```python
DEMO_SCENARIOS = {
    "success": [
        {"id": "DEMO-WIN", "probability": 0.9, "ground_truth": "SUCCESS"},
        {"id": "DEMO-FAIL", "probability": 0.1, "ground_truth": "FAIL_TIMEOUT"},
    ],
    "failure_pivot": [
        {"id": "DEMO-FAIL-A", "probability": 0.5, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "DEMO-SUCCESS-B", "probability": 0.7, "ground_truth": "SUCCESS"},
    ],
    "multi_candidate": [
        {"id": "DEMO-F1", "probability": 0.3, "ground_truth": "FAIL_SYNTAX"},
        {"id": "DEMO-F2", "probability": 0.4, "ground_truth": "FAIL_DEPENDENCY"},
        {"id": "DEMO-F3", "probability": 0.5, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "DEMO-SUCCESS", "probability": 0.8, "ground_truth": "SUCCESS"},
    ],
    "comparison": [
        {"id": "DEMO-F1", "probability": 0.3, "ground_truth": "FAIL_SYNTAX"},
        {"id": "DEMO-F2", "probability": 0.4, "ground_truth": "FAIL_DEPENDENCY"},
        {"id": "DEMO-F3", "probability": 0.5, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "DEMO-SUCCESS", "probability": 0.8, "ground_truth": "SUCCESS"},
    ],
}
```

Optional: one scenario backed by `vapt_candidates_from_corpus()` to show real VAPT adapter integration, limited to the local corpus.

---

## G. REQUIRED VISUALIZATIONS

All visualizations use Streamlit native components (`st.metric`, `st.table`, `st.json`, `st.bar_chart`).

1. **Candidate ranking table**
   - Columns: id, probability, quality_rank, priority_score.
   - Sorted by priority_score descending.

2. **Execution timeline**
   - Ordered list/table: step, candidate_id, attempt_number, outcome, detail.
   - Highlight pivot events in red.

3. **Attempt counter**
   - Per-candidate bar or metric: attempts / max_attempts.
   - Color change when attempts == max_attempts.

4. **Pivot event marker**
   - Explicit row/badge: "PIVOT at candidate X after N attempts".

5. **Final result**
   - Large metric badge: SUCCESS or COMPLETED.
   - Total requests, total wasted requests.

6. **Request comparison (Scenario 4 only)**
   - Bar chart: DUMB, PIVOT-ONLY, PRIORITY-ONLY, SMART request counts.
   - Table with exact numbers and pivot component.

---

## H. HOW THE PROTOTYPE EXPOSES THE REAL ENGINE

The demo must not create a second fake implementation.

**Correct pattern:**

```python
from decision_engine.core.engine import run_engine, initial_state
from decision_engine.core.executor import Executor
from decision_engine.core.assessor import deterministic_assessor
from decision_engine.core.schemas import candidate_from_dict

candidates = [candidate_from_dict(d) for d in DEMO_SCENARIOS["failure_pivot"]]
executor = Executor(mode="simulation")
final = run_engine(
    candidates=candidates,
    assess_fn=deterministic_assessor,
    executor=executor,
    max_attempts=max_attempts,
    mode="simulation",
)
```

Then visualize `final["logs"]`, `final["results"]`, `final["status"]`, `final["candidates"]`.

For DUMB/SMART comparison, reuse the simulation logic from `fair_benchmark.py` by importing `simulate_agent()` and running it on the same candidate list. Do not copy the logic into the demo.

---

## I. SAFETY BOUNDARY

- **Default mode:** simulation only.
- **Local loopback mode:** optional, disabled by default. If enabled, only targets `127.0.0.1` using the existing lab emulator. No arbitrary external targets.
- **No offensive capability:** demo UI must not provide target URL/IP input, exploit selection, or payload configuration.
- **Clear labeling:** every output must state whether it is SIMULATED or OBSERVED.
- **No real exploit execution in default demo:** simulation resolves from ground_truth labels.

---

## J. EXACT FILES TO BE CREATED/MODIFIED

| Action | File | Purpose |
|--------|------|---------|
| CREATE | `prototype_demo_data.py` | Hardcoded demo scenarios |
| CREATE | `prototype_demo.py` | Streamlit demo app |
| CREATE | `docs/project_management/PROTOTYPE_DEMONSTRATION_PLAN.md` | This plan |
| OPTIONAL | `app.py` | Add link/button to launch `prototype_demo.py` (not required) |

**Frozen files (must not be modified):**
- `core/`
- `decision_engine/core/`
- `tests/`
- `decision_engine/tests/`
- `datasets/`
- `decision_engine/benchmarks/fair_benchmark.py`
- `decision_engine/benchmarks/fair_vapt_benchmark.py`

---

## K. TESTING PLAN

1. **Regression guard:** Run `pytest tests/ -q` and `pytest decision_engine/tests/ -q` after creating demo files. Expected: 39 + 16 = 55 passed.
2. **Import check:** Verify `prototype_demo.py` imports only from `decision_engine/` and stdlib.
3. **Scenario smoke test:** Run each scenario in `prototype_demo_data.py` through the real engine and assert expected status/attempt counts.
4. **No frozen-file modification:** `git diff -- core/ decision_engine/ tests/ datasets/` must show empty.
5. **Manual UI test:** Run `streamlit run prototype_demo.py` and click every scenario button; verify outputs match expected behavior.

---

## L. MENTOR DEMONSTRATION SCRIPT

**Setup:**
```bash
python -m pytest tests/ decision_engine/tests/ -q
streamlit run prototype_demo.py
```

**Opening:**
"This is a prototype demonstration of the research contribution: a domain-independent decision engine with state-aware failure-threshold pivoting. The engine code is the same code used in the fair benchmark experiments."

**Scenario 1 — Success:**
- Click "Successful candidate".
- Point out: DEMO-WIN succeeds on first attempt, DEMO-FAIL never touched.
- "The engine advances immediately on success; no wasted attempts."

**Scenario 2 — Failure → Pivot:**
- Set max_attempts=2 in sidebar.
- Click "Repeated failure → pivot".
- Point out: DEMO-FAIL-A attempted twice → FAIL_TIMEOUT ×2 → pivot event → DEMO-SUCCESS-B succeeds.
- "This is Gap-2: bounded failure tracking with automatic pivot. No infinite loop."

**Scenario 3 — Multiple candidates:**
- Click "Multiple candidates".
- Point out: 3 failures each attempted exactly twice, then SUCCESS candidate, then COMPLETED.
- "Bounded termination is guaranteed by the index progression and attempt counter."

**Scenario 4 — DUMB vs SMART:**
- Click "DUMB vs SMART comparison".
- Point out bar chart: DUMB highest, SMART lowest, PRIORITY-ONLY ≈ DUMB under fair cap.
- "The pivot component is the separable mechanism. Priority alone does not reduce total attempts under identical cap — that's why Gap-1 is qualified, not claimed as an independent win."

**Closing:**
- "All four scenarios run the real engine. The demo is a UI wrapper; the logic is unchanged from the frozen research implementation."

---

## M. IMPLEMENTATION / DEMONSTRATION / SIMULATION / OBSERVED / FUTURE DISTINCTION

| Category | Meaning in this project |
|----------|------------------------|
| IMPLEMENTED | Engine, executor, assessor, adapter, benchmarks, tests, datasets |
| DEMONSTRATED | What the prototype UI shows to the mentor |
| SIMULATED | Default demo mode; outcomes from ground_truth labels; no network |
| OBSERVED | L2 loopback against 127.0.0.1 with real subprocess I/O; stubbed assessor; n=2 |
| FUTURE WORK | Full VAPT platform (recon, Nmap, Nuclei, UI), L3 Docker, LLM calibration, broader cross-domain |

---

## N. IMPLEMENTATION TASKS IN DEPENDENCY ORDER

**Task 1:** Create `prototype_demo_data.py` with four hardcoded scenarios.
- Agent: documentation/research agent (docs-only, no source changes).
- Verification: read back file; confirm dict structure matches `candidate_from_dict()`.

**Task 2:** Create `prototype_demo.py` with Streamlit shell, sidebar, and scenario runner for Scenarios 1–3.
- Agent: implementation agent (allowed: `prototype_demo.py`, `prototype_demo_data.py`).
- Verification: `pytest tests/ decision_engine/tests/ -q` still passes; manual run shows three scenarios.

**Task 3:** Add Scenario 4 (DUMB vs SMART comparison) with bar chart.
- Agent: implementation agent.
- Verification: reuse `simulate_agent()` from `fair_benchmark.py`; assert request counts match expected decomposition.

**Task 4:** Add safety labels and optional local loopback toggle (disabled by default).
- Agent: implementation agent.
- Verification: confirm default mode is simulation; confirm no external-target inputs in UI.

**Task 5:** Final smoke test and mentor script rehearsal.
- Agent: documentation agent.
- Verification: run full demo flow; confirm all visuals render; confirm no frozen-file modifications.

---

## O. AGENT PROMPTS FOR IMPLEMENTATION

### Task 1 Prompt
```
ROLE: Documentation/Research agent.
OBJECTIVE: Create prototype_demo_data.py with four demo scenarios.
ALLOWED FILES: prototype_demo_data.py (CREATE ONLY).
FORBIDDEN FILES: core/, decision_engine/core/, tests/, datasets/, benchmarks/.
REQUIREMENTS:
  - Define DEMO_SCENARIOS dict with keys: success, failure_pivot, multi_candidate, comparison.
  - Each value is a list of dicts with keys: id, probability, ground_truth.
  - Use the exact candidate sets described in PROTOTYPE_DEMONSTRATION_PLAN.md section E.
  - No engine logic; pure data.
VERIFICATION: Read back the file and confirm structure matches candidate_from_dict() expectations.
```

### Task 2 Prompt
```
ROLE: Implementation agent.
OBJECTIVE: Create prototype_demo.py (Streamlit demo app) with sidebar and Scenarios 1-3.
ALLOWED FILES: prototype_demo.py (CREATE ONLY), prototype_demo_data.py (READ ONLY).
FORBIDDEN FILES: core/, decision_engine/core/, tests/, datasets/, benchmarks/.
REQUIREMENTS:
  - Import real engine: run_engine, initial_state from decision_engine.core.engine.
  - Import real executor: Executor from decision_engine.core.executor.
  - Import real assessor: deterministic_assessor from decision_engine.core.assessor.
  - Import schemas: candidate_from_dict from decision_engine.core.schemas.
  - Sidebar: max_attempts slider (1-5, default 2), mode selector (simulation only, real disabled).
  - Main: four buttons for scenarios; on click, run engine and show results.
  - Visualizations: candidate table, execution timeline, attempt counter, pivot event, final status.
  - Do NOT reimplement engine logic.
VERIFICATION:
  - Run pytest tests/ decision_engine/tests/ -q; expect 55 passed.
  - Run streamlit run prototype_demo.py and click each button; confirm expected behavior.
```

### Task 3 Prompt
```
ROLE: Implementation agent.
OBJECTIVE: Add Scenario 4 (DUMB vs SMART comparison) to prototype_demo.py.
ALLOWED FILES: prototype_demo.py (MODIFY), prototype_demo_data.py (READ ONLY).
FORBIDDEN FILES: core/, decision_engine/core/, tests/, datasets/, benchmarks/.
REQUIREMENTS:
  - Import simulate_agent from decision_engine.benchmarks.fair_benchmark.
  - Run DUMB, PIVOT-ONLY, PRIORITY-ONLY, SMART on the same candidate list.
  - Show bar chart of request counts and a table with exact numbers.
  - Highlight pivot component = PRIORITY-ONLY - SMART.
VERIFICATION:
  - Run pytest tests/ decision_engine/tests/ -q; expect 55 passed.
  - Confirm bar chart shows DUMB >= PRIORITY-ONLY and SMART <= PIVOT-ONLY.
```

### Task 4 Prompt
```
ROLE: Implementation agent.
OBJECTIVE: Add safety labels and optional local loopback toggle to prototype_demo.py.
ALLOWED FILES: prototype_demo.py (MODIFY).
FORBIDDEN FILES: core/, decision_engine/core/, tests/, datasets/, benchmarks/.
REQUIREMENTS:
  - Add safety notice in sidebar: "Default simulation. No external targets."
  - Add disabled toggle for "Local loopback (127.0.0.1)" with explanation that it requires lab emulator.
  - Ensure no text field or input allows arbitrary target specification.
  - All outputs must label mode as SIMULATED or OBSERVED.
VERIFICATION:
  - Run pytest tests/ decision_engine/tests/ -q; expect 55 passed.
  - Confirm UI has no external-target input fields.
```

### Task 5 Prompt
```
ROLE: Documentation agent.
OBJECTIVE: Final smoke test and mentor script rehearsal.
ALLOWED FILES: READ-ONLY inspection of prototype_demo.py, prototype_demo_data.py.
FORBIDDEN FILES: core/, decision_engine/core/, tests/, datasets/, benchmarks/.
REQUIREMENTS:
  - Run full demo flow: start streamlit, click every scenario, verify visuals.
  - Confirm no modifications to frozen files via git diff.
  - Produce a short rehearsal note: exact clicks and what the mentor sees.
VERIFICATION:
  - git diff -- core/ decision_engine/ tests/ datasets/ must be empty.
  - pytest tests/ decision_engine/tests/ -q must show 55 passed.
```

---

## P. ROLLBACK / SAFETY RULES

1. **Frozen boundary:** If any agent proposes modifying `core/`, `decision_engine/core/`, `tests/`, `datasets/`, or benchmark files, STOP and report.
2. **No new claims:** Demo text must not introduce complete-VAPT, real-world, Docker-validated, or speed claims.
3. **No fake engine:** If demo code reimplements pivot/assessor/executor logic, STOP and refactor to import real components.
4. **No external targets:** If demo UI accepts arbitrary URLs/IPs, STOP and remove.
5. **Verification gate:** After each task, run the 55-test suite before proceeding.
6. **Rollback:** If a task breaks tests or modifies frozen files, revert the task file and redo with stricter constraints.

---

*End of PROTOTYPE_DEMONSTRATION_PLAN.md*
