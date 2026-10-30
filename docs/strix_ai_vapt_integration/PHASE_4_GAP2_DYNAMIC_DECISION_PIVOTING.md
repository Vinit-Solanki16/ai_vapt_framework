# Phase 4: GAP-2 Dynamic Bounded Decision-Pivoting Engine

## 1. Objective

Integrate **GAP-2 (Dynamic Bounded Decision-Pivoting)** into Strix (`/home/vinit/STRIX/strix`).  
Autonomous offensive agents frequently get trapped in infinite retry loops or waste dozens of turns tweaking minor parameters when an attack path is blocked by a WAF, an unexploitable patch, or network timeouts. GAP-2 introduces an explicit **Pivot Policy** bounded by threshold $k$ (default $k=2$): after $k$ failures, the system abandons the dead-end branch and dynamically pivots to the next prioritized vulnerability.

> **CRITICAL RULE:** All modifications and new files are created **strictly inside `/home/vinit/STRIX/strix`**. The code in `/home/vinit/AI_VAPT` is only copied and adapted.

---

## 2. Target File Structure in STRIX

```
/home/vinit/STRIX/strix/
├── strix/
│   ├── core/
│   │   ├── decision_engine/          # NEW: Core GAP-2 state machine & pivot router
│   │   │   ├── __init__.py
│   │   │   ├── engine.py             # Ported from AI_VAPT/decision_engine/core/engine.py
│   │   │   ├── state.py              # Candidate states: PENDING, ATTEMPTING, VALIDATED, ABANDONED
│   │   │   └── trace.py              # Auditable event logging (REDIRECT, ABANDON, COMPLETE)
│   │   ├── execution.py              # UPDATED: Enforce attempt limits inside run_agent_loop()
│   │   └── agents.py                 # UPDATED: AgentCoordinator handles pivot signals and child pruning
│   └── interface/
│       ├── api.py                    # UPDATED: Expose decision_trace, pivot_events, and DAG endpoints
│       └── web/js/app.js             # UPDATED: Render live interactive DAG in #/pivot-analysis
```

---

## 3. Technical Implementation Specification

### Step 3.1: Port Decision Engine Core (`strix/core/decision_engine/engine.py`)
Port and adapt from `AI_VAPT/decision_engine/core/engine.py`:
- `DecisionEngine`:
  - `pivot_threshold: int = 2` (Configurable via UI or CLI).
  - `attempts: dict[str, int]` (Tracks attempts per candidate).
  - `status: dict[str, CandidateState]` (`PENDING`, `VALIDATED`, `ABANDONED`).
  - `decision_trace: list[str]` (Human-readable trace of all engine actions).
  - `pivot_events: list[PivotEvent]` (Structured events: `INIT`, `ADVANCE`, `REDIRECT`, `ABANDON`, `COMPLETE`).

### Step 3.2: Pivot State Machine Logic
```python
def record_outcome(candidate_id: str, outcome: Outcome) -> PivotAction:
    if outcome == Outcome.SUCCESS:
        decision_engine.mark_validated(candidate_id)
        decision_trace.append(f"[Advance] {candidate_id} validated. Next candidate.")
        return PivotAction.ADVANCE

    attempts[candidate_id] += 1
    if attempts[candidate_id] >= pivot_threshold:
        decision_engine.mark_abandoned(candidate_id)
        decision_trace.append(
            f"[Pivot] Threshold {pivot_threshold} reached for {candidate_id}. Abandoning route."
        )
        next_cand = get_next_available_candidate()
        if next_cand:
            decision_trace.append(f"[Pivot] Redirected to {next_cand.id}")
            return PivotAction.REDIRECT(to_candidate=next_cand.id)
        else:
            decision_trace.append("[Pivot] All candidates processed. Workflow complete.")
            return PivotAction.COMPLETE

    return PivotAction.RETRY(attempt=attempts[candidate_id], max_attempts=pivot_threshold)
```

### Step 3.3: Intercept Strix Subagent Loops (`strix/core/execution.py`)
In Strix's `run_agent_loop()`:
1. When a subagent executes an action tool or payload attempt:
   - Check if execution succeeded or failed (timeout, WAF drop, command failure).
   - Feed the outcome to `DecisionEngine.record_outcome()`.
2. If `PivotAction.REDIRECT` is returned:
   - Gracefully terminate the current subagent executing Candidate $A$.
   - Emit `ABANDON` event to the trace.
   - Dispatch a new subagent to Candidate $B$.
3. If `PivotAction.COMPLETE` is returned:
   - Finish scan and generate report.

### Step 3.4: Real-Time Frontend DAG Visualization (`strix/interface/web/js/app.js`)
- Expose `/runs/{run_id}/trace` and `/runs/{run_id}/candidates`.
- In `#/pivot-analysis` and `#/assessment/active`:
  - Render the interactive SVG DAG showing:
    - Root Node $\to$ Candidate Nodes.
    - Attempt badges ($1/2$, $2/2$).
    - Red redirect arcs showing automated pivots.
    - Final outcome badges (`VALIDATED`, `ABANDONED`).

---

## 4. Agent Development Prompt for Phase 4

```markdown
# TASK: Phase 4 — Implement GAP-2 Bounded Dynamic Decision-Pivoting in STRIX

## Strict Boundaries
- Work EXCLUSIVELY inside `/home/vinit/STRIX/strix`.
- DO NOT edit any files in `/home/vinit/AI_VAPT`. Read files from `/home/vinit/AI_VAPT` as read-only reference.

## Objective
Implement the GAP-2 Dynamic Decision-Pivoting Engine inside STRIX so that agent execution is strictly bounded by a failure threshold k (default k=2). When attempts on a candidate fail k times, the engine automatically abandons that candidate, emits a REDIRECT event, and pivots to the next candidate without wasting tokens.

## Detailed Tasks
1. Create directory `/home/vinit/STRIX/strix/strix/core/decision_engine/`.
2. Port the decision engine from `/home/vinit/AI_VAPT/decision_engine/core/`:
   - `engine.py`: Core state machine handling candidate queues, attempt counters, and pivot policies.
   - `schemas.py`: `Outcome` (SUCCESS, FAIL_TIMEOUT, NOT_REPRODUCIBLE), `PivotEvent`, `CandidateState`.
   - `trace.py`: Trace recording functions.
3. Update `strix/core/execution.py` and `strix/core/agents.py`:
   - Intercept Strix agent loops when an action attempt against a candidate fails.
   - Track attempt counts against `pivot_threshold`.
   - If attempts reach `pivot_threshold`, trigger branch pruning, emit event `ABANDON`, and pivot to the next queued candidate.
4. Update `strix/interface/api.py`:
   - In `RunResponse` and `GET /runs/{run_id}`, include:
     `decision_trace`: List of strings showing engine history.
     `pivot_events`: List of structured pivot objects (`type`, `candidate_id`, `details`).
     `pivot_count`: Total number of dynamic pivots executed.
5. In `strix/interface/web/js/app.js`:
   - Connect the live run poller to render the Decision Trace terminal and Decision Paths graph in real time.
6. Write integration tests in `tests/test_gap2_pivoting.py`:
   - Test Scenario: Candidate 1 fails twice $\to$ Engine pivots $\to$ Candidate 2 succeeds.
   - Verify `pivot_count == 1`, `final_status == "COMPLETED"`, and attempt bounds are respected.
```

---

## 5. Verification & Testing Commands

```bash
# 1. Run GAP-2 Decision-Pivoting Integration Tests
cd /home/vinit/STRIX/strix
uv run pytest tests/test_gap2_pivoting.py -v

# 2. Test GAP-2 Bounded Pivot Execution in Simulation
uv run python -c "
from strix.core.decision_engine.engine import DecisionEngine
from strix.core.decision_engine.schemas import ActionCandidate, Outcome

engine = DecisionEngine(pivot_threshold=2)
c1 = ActionCandidate(id='cand-1', probability=0.9)
c2 = ActionCandidate(id='cand-2', probability=0.8)
engine.initialize([c1, c2])

# Attempt 1 on cand-1 fails
engine.record_outcome('cand-1', Outcome.FAIL_TIMEOUT)
# Attempt 2 on cand-1 fails -> Should trigger pivot
act = engine.record_outcome('cand-1', Outcome.FAIL_TIMEOUT)
print('Pivot Action after 2 fails:', act)
print('Current Candidate:', engine.current_candidate.id)
print('Decision Trace:', engine.decision_trace)
"
# Expected: Action is REDIRECT(to_candidate='cand-2'), current_candidate is 'cand-2'
```

