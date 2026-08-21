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
