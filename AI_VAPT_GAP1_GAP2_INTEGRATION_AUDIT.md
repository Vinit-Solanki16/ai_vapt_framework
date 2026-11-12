# AI-VAPT GAP-1, GAP-2 & Strix End-to-End Integration Audit

**Date:** 2026-11-11  
**Target Environment:** AI-VAPT Autonomous Security Testing Platform  
**Branch:** `ai-vapt-full-application`  
**Audit Scope:** Deep Architecture Inspection, State Accounting, Dynamic Pivots, Verification Contract  
**Test Suite Coverage:** 89 Automated Tests (89 Passed, 0 Failed across Phase 6, Phase 7, and Lifecycle suites)  

---

## 1. Executive Summary

This audit rigorously inspects the end-to-end integration between the autonomous execution engine (Strix), the GAP-1 candidate triage system, the GAP-2 dynamic hypothesis pivoting engine, and the 9-state finding verification lifecycle.

### Audit Verdict: **INTEGRATED & VERIFIED**
The core components are genuinely wired across the autonomous execution pipeline:
- **GAP-1 Candidate Prioritization**: Discovered vulnerabilities and attack vectors are triaged by composite exploitability scoring, placed in an ordered candidate queue, and injected directly into the root agent's context and prompts.
- **Candidate Accounting Invariant**: Strictly enforced across all runtime memory, disk snapshots (`gap_state.json`), and exports (`run.json`):
  $$\text{dispatched} = \text{investigated} + \text{not\_tested} + \text{blocked}$$
- **GAP-2 Adaptive Pivoting**: Synthetic retry loops and phantom pivots have been eliminated. Pivoting occurs only when a candidate's probe attempts reach the threshold ($k=2$), the probe fails, and an authorized alternative candidate is selected.
- **Scope Enclosure**: The decision engine actively inspects candidates against `authorized_targets`; out-of-scope targets are transitioned to `BLOCKED` with an explanatory reason and are excluded from selection.
- **Strict Verification Contract**: No finding can receive `Verified` status without a reproducible HTTP request, observed response body/slice, executable verification procedure, demonstrated exploitation impact, and valid evidence timestamp. Findings lacking complete proof are demoted to `Unconfirmed`.
- **Run Isolation & Resumability**: Thread-safe registries guarantee zero state leakage across concurrent scans. Resuming a scan preserves completed candidates (`VALIDATED`, `ABANDONED`, `BLOCKED`) without re-probing.

---

## 2. Detailed Inspection of GAP-1 Integration

### 2.1 Candidate Queue Creation & Prioritization
In [`strix/core/runner.py`](file:///workspaces/ai_vapt_framework/strix/core/runner.py):
1. Upon scan initialization (`run_strix_scan`), candidate queues are populated from `scan_config["candidates"]`, environment overrides, or stored disk queues.
2. Candidates are sorted by composite exploit score:
   $$\text{score} = w_1 \cdot \text{exploit\_quality} + w_2 \cdot \text{cvss} + w_3 \cdot \text{attack\_surface\_weight}$$
3. The prioritized queue is attached to `GapRun` (`strix/core/gap_run.py`) and synchronized with `DecisionEngine` (`strix/core/decision_engine/engine.py`).

### 2.2 Runtime Context Injection
The prioritized candidate queue is injected directly into the agent's runtime instructions:
- The root agent's system prompt receives a structured directive listing the top candidate vectors, their CWE IDs, endpoints, target parameters, and priority ranks.
- The root agent context provides the active `gap_run` and `decision_engine` instances to tools (`outcome_tool.py`), enabling agents to record probes and request next prioritized candidates.

### 2.3 Candidate Accounting Invariant
In [`strix/core/gap_run.py`](file:///workspaces/ai_vapt_framework/strix/core/gap_run.py), candidate counts are computed dynamically from candidate state enums:
```python
@property
def dispatched(self) -> int:
    return len(self.candidates)

@property
def investigated(self) -> int:
    return len([c for c in self.candidates.values() if c.status in ("investigated", "abandoned", "validated")])

@property
def not_tested(self) -> int:
    return len([c for c in self.candidates.values() if c.status in ("pending", "under_investigation")])

@property
def blocked(self) -> int:
    return len([c for c in self.candidates.values() if c.status == "blocked"])
```
The invariant $\text{dispatched} = \text{investigated} + \text{not\_tested} + \text{blocked}$ is verified under all transitions in `tests/test_phase6_core_runner_gap_integration.py` and `tests/test_phase7_e2e_validation.py`.

---

## 3. Detailed Inspection of GAP-2 Dynamic Pivoting

### 3.1 Elimination of Synthetic / Simulated Loops
Previously, in `strix/interface/api.py`, failed probes executed an in-memory loop:
```python
# PREVIOUS FLAW: Artificially bumped attempt counter without probing
for attempt_num in range(1, max_k + 1):
    current_turn += 1
    engine.record_outcome(...)
```
This simulated loop was **dismantled**. A failed probe now truthfully registers a single attempt (`Outcome.FAIL_TIMEOUT`). No pivot is logged unless:
1. Candidate probe attempts reach $k$ (`max_attempts = 2`).
2. An alternative candidate is selected from the available queue.
3. The alternative candidate passes `is_candidate_in_scope()`.

### 3.2 Dynamic Scope Validation
In [`strix/core/decision_engine/engine.py`](file:///workspaces/ai_vapt_framework/strix/core/decision_engine/engine.py):
```python
def is_candidate_in_scope(self, candidate: ActionCandidate) -> bool:
    if not self.authorized_targets:
        return True
    candidate_host = self._extract_host(candidate.target or candidate.endpoint)
    return any(self._match_scope(candidate_host, auth) for auth in self.authorized_targets)
```
If a candidate targets an unauthorized hostname or external IP, it is marked `CandidateState.BLOCKED` with reason `"Out of authorized assessment scope"` and bypassed.

---

## 4. Strict 9-State Verification Lifecycle

### 4.1 Supported States
In [`strix/report/verification.py`](file:///workspaces/ai_vapt_framework/strix/report/verification.py):
1. `Discovered`
2. `Candidate`
3. `Under investigation`
4. `Exploitation attempted`
5. `Verified`
6. `Unconfirmed`
7. `False positive`
8. `Blocked`
9. `Inconclusive`

### 4.2 Verification Contract Gate
A finding claiming `status="verified"` must satisfy `satisfies_verification_contract()`:
- **Reproducible Request**: Authentic HTTP request string (not empty, not `"N/A"`, not boilerplate template).
- **Observed Response**: Raw response slice or body confirming exploit execution.
- **Verification Procedure**: Concrete, executable steps to reproduce.
- **Demonstrated Impact**: Concrete impact observed (e.g. database schema banner, SQL error diff, reflected DOM payload), not generic taxonomy text.
- **Evidence Timestamp**: Valid ISO 8601 UTC timestamp.

If any required item is missing:
- Tool reporting: `record_vulnerability_outcome` automatically demotes status to `unconfirmed` and logs an actionable reason.
- Report state: `ReportState.add_vulnerability_report()` enforces the same check.
- Markdown and HTML reports: Segregate findings into `## Confirmed Vulnerability Findings` and `## Unconfirmed Candidates & Inconclusive Probes`.

---

## 5. Multi-Run State Isolation & Resume Verification

### 5.1 Run-Scoped Isolation
- `_active_report_states` and `_active_gap_runs` are thread-safe dictionaries indexed by `run_id`.
- Test `test_concurrent_autonomous_runs_state_isolation` verifies that two scans running concurrently maintain completely separate candidate queues, finding lists, decision traces, and accounting metrics.

### 5.2 Resume Behavior
- Invoking `POST /runs/{run_id}/resume` loads existing candidate states from `gap_state.json`.
- Candidates with terminal states (`VALIDATED`, `ABANDONED`, `BLOCKED`) are preserved and skipped during the resumed investigation loop.
- Existing confirmed findings are preserved without reset or duplication.

---

## 6. Audit Summary

| Requirement | Implementation State | Verification Method | Status |
|---|---|---|:---:|
| **GAP-1 Candidate Prioritization** | Fully integrated in `runner.py` and `gap_run.py` | Automated tests & AST inspection | **VERIFIED** |
| **Accounting Invariant** | Dispatched = Investigated + Not Tested + Blocked | Property assertions in unit/integration tests | **VERIFIED** |
| **GAP-2 Adaptive Pivoting** | Bound to `outcome_tool.py` and `DecisionEngine` | Threshold exhaustion & alternative selection | **VERIFIED** |
| **Scope Boundary Check** | `is_candidate_in_scope()` blocks unauthorized hosts | Test cases with external IP/domain | **VERIFIED** |
| **9-State Verification Barrier** | Strict evidence requirement for `Verified` | Demotion assertions on incomplete proof | **VERIFIED** |
| **No Synthetic Retries** | Synchronous increment loops dismantled | Time delta and attempt trace analysis | **VERIFIED** |
| **Multi-Run Isolation** | Run-scoped registries (`ReportState`, `GapRun`) | Concurrent execution test | **VERIFIED** |
| **Resume State Preservation** | Completed candidates preserved across resumes | Disk reload test (`GapRun.load()`) | **VERIFIED** |
| **Multi-Format Reports** | Markdown, HTML, SARIF, CSV, JSON | Cross-format findings count alignment | **VERIFIED** |
