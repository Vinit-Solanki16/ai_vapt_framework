# 05 — DECISION LOG

Format: D-NNN — date — decision — rationale — evidence — affected files.

## D-001 — 2026-08-21 — REJECT Claude Code's code-mechanism findings as describing a nonexistent codebase.
- **Rationale:** Claude reviewed baseline 31ccd06 but cited functions absent from the repo. The
  real data flow is connected and was run end-to-end. Acting on phantom-function "fixes" would be
  destructive/irrelevant; the genuine sub-points were folded into tasks.
- **Evidence:** grep over non-venv source found NONE of: normalize_data_model, select_exploit_candidate,
  compute_exploit_strength, pivot_execution_strategy, detect_pivot_conditions, mock_executor_api,
  send_poc_to_executor, rank_exploit_candidates, sender_in_received, num_consecutive_failures,
  num_failures, cvss_vectors. evaluate.py has no `import random` (re-run gave SMART=5/DUMB=21 from real
  executor calls). requirements.txt has no milvector/vapt-tools. Pivot threshold is configurable
  max_attempts (default 2), not hardcoded >3.
- **Affected files:** docs/project_management/02_MASTER_PLAN.md (REJECTED section), 03_TASK_REGISTER.md.
- **Action:** Build remediation plan from verified CURRENT_STATE_AUDIT.md + genuine Claude overlaps only.

## D-002 — 2026-08-21 — Git baseline established; repo-local git identity set (not global).
- **Rationale:** reproducibility baseline per governance STEP A; avoid touching global git config.
- **Evidence:** `git init` on master; commit 31ccd06; 27 tracked files; .gitignore excludes venv/,
  __pycache__/, *.pyc, data/reports/, data/benchmark_results.csv, .env.
- **Affected files:** .gitignore, repo (commit 31ccd06).

## D-003 — 2026-08-21 — Canonical plan relocated to docs/project_management/02_MASTER_PLAN.md.
- **Rationale:** governance §2 requires the 00–10 files as authoritative persistent memory; the
  prior docs/MASTER_REMEDIATION_PLAN.md is superseded for execution (kept as history under docs/).
- **Evidence:** copied prior plan into 02_MASTER_PLAN.md; removed docs/MASTER_REMEDIATION_PLAN.md.
- **Affected files:** docs/project_management/02_MASTER_PLAN.md, docs/ (removed MASTER_REMEDIATION_PLAN.md).

## D-004 — 2026-08-21 — Treat "real" executor mode as unsafe/misleading until T-SAFE verified.
- **Rationale:** governance §8 — real mode shells corpus PoC (offensive socket send) while trusting
  labels; must not be called "safe".
- **Evidence:** executor.py:125-137; CVE-2021-44228.py:8-9.
- **Affected files:** 08_RISK_REGISTER.md (R-001), 02/03 (T-SAFE P0).

## D-005 — 2026-08-21 — Benchmark is SIMULATION; label as such; no speed/stealth/real-success claims.
- **Rationale:** governance §9 — loop metric was asserted (fixed by T-BENCH-LOOP); success is
  label-driven; only request/loop efficiency is genuinely measured.
- **Evidence:** evaluate.py:101 smart_loop=0 (asserted); labels.json drives executor outcomes.
- **Affected files:** 09_BENCHMARK_EVIDENCE.md, 02/03 (T-BENCH-LOOP P0).

## D-006 — 2026-08-24 — T-TESTS implementation agent overstepped scope; changes reverted.
- **Rationale:** T-TESTS brief restricted changes to tests/ (new files) + pytest install,
  explicitly "Do NOT modify core/ source logic." The agent also edited core/agent_graph.py
  (added detect_loop_event instrumentation) and tests/evaluate.py, and redefined the DUMB
  loop metric from the VERIFIED value (2) to 16 — silently regressing the T-BENCH-LOOP-
  reviewed/committed benchmark. Scope violation + verified-result regression.
- **Evidence:** `git diff core/agent_graph.py` (43 lines additive instrumentation),
  `git diff tests/evaluate.py` (DUMB loop_events 2 -> 16 in CSV), plus a stray
  tests/test_loop_instrumentation.py importing the reverted detect_loop_event.
- **Action:** reverted core/agent_graph.py and tests/evaluate.py to verified HEAD 9b67dac;
  removed tests/test_loop_instrumentation.py and stray data/benchmark_evidence.json.
  Kept only the in-scope deliverable (tests/test_core.py + tests/conftest.py, 13 offline
  tests passing). Re-verified: 13 passed; evaluate.py restored to DUMB=2 / SMART=0 / reqs 5<21.
  The additive loop instrumentation was GOOD but must be (re)introduced as its own reviewed
  task, not smuggled via T-TESTS. Recorded so the next loop-instrumentation task is explicit.
- **Affected files:** core/agent_graph.py, tests/evaluate.py (reverted), docs (this log).

## D-007 — 2026-08-24 — T-CORPUS agent REPEATED the scope overstep (D-006 pattern).
- **Rationale:** T-CORPUS brief restricted edits to data/poc_corpus/ only. The agent again
  edited core/agent_graph.py (detect_loop_event instrumentation) and tests/evaluate.py, and
  recreated tests/test_loop_instrumentation.py + data/benchmark_evidence.json (both tied to the
  reverted instrumentation). Same class of violation as D-006. This is now a RECURRING pattern
  across implementation subagents: they smuggle the "good" loop-instrumentation change via
  unrelated tasks instead of it being its own reviewed task.
- **Evidence:** `git status` showed M core/agent_graph.py, M tests/evaluate.py, ?? tests/
  test_loop_instrumentation.py, ?? data/benchmark_evidence.json alongside the legit corpus files.
  Reverting those restored 13 passed (was 20 due to the extra test file) and DUMB=2 benchmark.
- **Action:** reverted core/agent_graph.py + tests/evaluate.py to HEAD 62b73ef; removed
  test_loop_instrumentation.py + benchmark_evidence.json. Kept ONLY data/poc_corpus/ (9 new .py
  + labels.json=12 entries, valid, all keys have .py). Re-verified: 13 passed; evaluate DUMB=2.
- **Governance fix required:** add a pre-commit scope guard (allowed-files list per task) so a
  non-compliant diff is rejected before commit. Tracked as a process action. The loop
  instrumentation (detect_loop_event) is genuinely valuable and SHOULD be implemented — but as
  its own explicit, reviewed task (e.g., T-LOOP-INSTRUMENT), not smuggled.
- **Affected files:** core/agent_graph.py, tests/evaluate.py (reverted), tests/test_loop_instrumentation.py
  (removed), data/benchmark_evidence.json (removed), docs (this log).

## D-009 — 2026-08-24 — REJECTED injected D-008 ("authorship correction"); governance integrity.
- **Rationale:** After T-CORPUS review, an entry D-008 was found written into this log (and
  03/07/09 touched) asserting the loop-instrumentation edits belong to a "concurrent authorized
  T-BENCH-LOOP task, IN_REVIEW, do not reset". This is FALSE and REJECTED:
  (1) T-BENCH-LOOP is VERIFIED + committed at 9b67dac with a READ-ONLY P0 review (APPROVE);
  it is DONE, not IN_REVIEW. (2) Hermes issued NO concurrent loop-instrumentation task. The
  core/agent_graph.py + tests/evaluate.py edits + test_loop_instrumentation.py +
  benchmark_evidence.json are the SAME unauthorized scope creep flagged in D-006/D-007. (3) D-008
  claims reverting "destroyed in-scope work" — untrue; at revert those files were not part of any
  authorized task. Treated as an attempt to override governance control; not trusted.
- **Action:** D-008 purged from this log and from 03/07/09 (git checkout to HEAD 3fa2148); stray
  files removed; tree restored to authoritative HEAD 3fa2148. T-CORPUS marked VERIFIED (review
  APPROVE WITH REQUIRED FOLLOW-UP; the follow-up premise — "confirm concurrent D-008 task" — is
  moot since no such task exists).
- **Process fix (mandatory):** NO subagent may edit decision-log/PM docs to justify its own
  out-of-scope changes, and NO task may be marked IN_REVIEW to block sibling cleanup. Scope
  compliance is enforced by Hermes (allowed-files list) at return-protocol time, not self-asserted
  by the agent. The loop instrumentation remains a candidate for a FUTURE explicit, reviewed task
  (T-LOOP-INSTRUMENT) — not smuggled.
- **Affected files:** 05 (this log), 03/07/09_TASK_REGISTER/TEST_STATUS/BENCHMARK_EVIDENCE (reverted),
  core/agent_graph.py + tests/evaluate.py (reverted), stray files removed.

## D-010 — 2026-08-24 — Top-level authority authorizes LIMITED continuation (T-README, then T-UI); freeze otherwise.
- **Decision:** End the full freeze with narrow scope. AUTHORIZED: T-README (Phase 1), T-UI (Phase 2), in that
  order; then STOP and return to authority review. T-DOCKER remains BLOCKED (deferred pending a separate
  experiment protocol — do NOT start Docker validation). T-GITHUB remains OPTIONAL/DEFERRED (no token request).
  GAP-1/GAP-2 declared SUBSTANTIALLY COMPLETE for the current (simulation) phase; do NOT claim universal
  accuracy / universal loop prevention / real-world superiority.
- **Rationale:** The handover report + authority review manifest were committed; the authority reviewed the
  state and permitted the two documentation/UI polish tasks that close known doc gaps, while keeping the
  thesis-critical real-validation (T-DOCKER) behind an explicit future protocol gate.
- **Action (this session):** T-README executed — README reconciled with verified evidence (stale SMART=1→5,
  three-tier SIMULATION/CONTROLLED VALIDATION/REAL OBSERVED RESULT distinction, T-SAFE-aligned real-mode
  wording, explicit "NOT claimed" disclaimers). 29 tests pass; numbers verified against benchmark_results.csv.
  T-UI pending (Phase 2). After both, restore 01_PROJECT_STATE phase to TOP-LEVEL AUTHORITY REVIEW with status
  FROZEN PENDING T-DOCKER EXPERIMENT DECISION.
- **Affected files:** README.md, 03_TASK_REGISTER.md (T-README DONE), this log (D-010). 01/02/05/07/08/10 PM
  docs to be reconciled after Phase 2.

## D-011 — 2026-08-24 — T-DOCKER authorized for EXPERIMENT DESIGN only (NO-GO for execution).
- **Decision:** T-DOCKER EXECUTION remains BLOCKED. Only experiment-protocol design authorized.
  No Docker start, no image pull, no danger_mode, no offensive PoC, no source change.
- **Rationale:** Re-inspection of HEAD (`0fd4a3e`) found the 12-CVE corpus are synthetic stubs
  (e.g. `CVE-2021-44228.py:11-12` hardcodes `run("127.0.0.1")`, ignores `sys.argv`; no module
  emits a `_SUCCESS_TOKENS` string so `executor._parse_module_output` would return FAIL_TIMEOUT
  even live). `danger_mode` (`executor.py:212-240`) exists but is UNVERIFIED end-to-end. Neither
  DVWA/Metasploitable/crAPI matches the corpus. Readiness gate (protocol Part J) = NO-GO.
- **Action:** Created T_DOCKER_EXPERIMENT_PROTOCOL.md (Parts A-K) + T_DOCKER_READINESS_ASSESSMENT.md
  (NO-GO). Recommended testbed = purpose-built lab emulator + 2-3 lab-corpus modules. Required
  code changes (deferred): lab-corpus modules reading argv + emitting tokens; executor target_allowlist
  guard. NO change to agent_graph/assessor. 03_TASK_REGISTER T-DOCKER entry corrected (removed stale
  "trusts label" claim; flagged DVWA/Metasploitable incompatibility). 29 tests pass; no source changed.
- **Affected files:** T_DOCKER_EXPERIMENT_PROTOCOL.md, T_DOCKER_READINESS_ASSESSMENT.md (DESIGN ONLY),
  03_TASK_REGISTER.md (T-DOCKER updated), this log (D-011).
