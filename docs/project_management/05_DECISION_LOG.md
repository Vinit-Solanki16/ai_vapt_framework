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
