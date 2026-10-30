# MTech Implementation — AI_VAPT + Strix

## 1. Problem and design

The platform separates **decision control** from **autonomous execution**:

- **AI_VAPT** owns scope authorization, candidate state, persistence, reporting,
  and the operator UI.
- **Strix** runs an autonomous LLM pentest worker inside its Docker sandbox.
- **GAP-1** ranks candidate hypotheses with the frozen research core's
  published assess-then-rank behavior.
- **GAP-2** tracks attempts per candidate and pivots after a configurable
  failure threshold.

The frozen `decision_engine/core/` package is imported but never modified.

## 2. Architecture

```text
Frontend (Strix Engine page)
        │  POST /strix/runs + provider key header
        ▼
FastAPI control plane (services/api.py)
        │  scope gate: validate_web_target()
        ▼
StrixRunService
        │  GAP-1 ranking + persistence
        ▼
StrixWorkerAdapter ── subprocess ──► Strix (Docker sandbox)
        │                                  │
        │  control/gap1_queue.json         │ GAP-1 root-task injection
        │  control/decision_trace.jsonl ◄──┤ GAP-2 outcomes / pivots
        ▼                                  │
PersistentRun (mode=strix)                 │ vulnerabilities.json
        │                                  │ run.json
        ▼                                  ▼
Reports (JSON/HTML/MD/TXT)          Native Strix artifacts
```

### Launch path

1. API validates the target with the authoritative web-target gate.
2. Service preserves the operator's original candidate order and computes the
   GAP-1 ranked queue.
3. Adapter re-validates scope (defense in depth), writes the run-scoped control
   directory, strips ambient provider credentials, and launches Strix.
4. Loopback targets are rewritten to `host.docker.internal` only at the Docker
   boundary; authorization remains anchored to the original host:port.
5. Adapter discovers the new `strix_runs/<id>` directory and follows
   `run.json` through its lifecycle.

### Result path

- `vulnerabilities.json` is normalized into `NormalizedFinding` objects.
- Findings become candidates tagged `source_engine=strix`,
  `evidence_tier=SCANNER_DETECTED_CANDIDATE`, `result_semantic=OBSERVED_EXTERNAL`,
  and `validation_status="SCANNER-DETECTED CANDIDATE (NOT VALIDATED)"`.
- Persistence and the existing report builder make the result visible in run
  history, findings, and all report formats.

## 3. GAP-1

- Candidate mapping: title, description, severity, probability/confidence,
  evidence, endpoint/target.
- Frozen-core `rank_candidates()` and `priority_score()` are used unchanged.
- Both original and ranked orders are recorded in `gap1_queue.json` and
  `pipeline_summary`.
- Strix's `build_root_task()` appends the ranked queue with rank, endpoint,
  method, quality, priority, and reasoning.
- `STRIX_GAP1_ENABLED=0` disables injection for comparison.

## 4. GAP-2

- Candidate identity resolves by endpoint, title, then target.
- Failure increments an in-memory per-run counter; at threshold `k` the
  candidate is exhausted and the next ranked candidate is returned.
- Success completes the candidate.
- Events: `GAP2_ATTEMPT`, `GAP2_SUCCESS`, `GAP2_PIVOT`.
- Pivot guidance is returned inside the report tool result so the agent sees
  the instruction to abandon the route.
- `STRIX_GAP2_ENABLED=0` disables the hook for comparison.

## 5. Security properties

- Scope authorization is fail-closed and applied before process launch.
- The adapter repeats the scope check independently.
- API keys travel only in headers or the child environment, never argv.
- Ambient provider keys are removed from the child environment.
- Keys are redacted from errors and never persisted, logged, or rendered.
- Strix findings are never promoted to validated exploits.

## 6. Verification

- AI_VAPT: 1,137 tests pass.
- New tests: adapter 28, GAP-1 9, GAP-2 11, multi-model 12, UI/reports 8.
- Strix bridge: 12 tests; affected Strix suites: 198 tests pass.
- Frozen core diff: empty.
- Controlled A–E comparison: combined GAP-1+GAP-2 uses 3 attempts versus 13
  for baseline in the deterministic decision-layer scenario.

## 7. Known limitations

- OpenRouter free daily quota and lack of paid credits blocked additional live
  hosted runs.
- Local `qwen2.5:1.5b` does not complete the Strix lifecycle within tested turn
  budgets.
- No human browser click-through was performed; UI verification used HTTP smoke
  checks, JS syntax validation, and deterministic payload/report tests.
- Native Strix artifacts are displayed as paths, not served for download.
