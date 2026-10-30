# Phase 4 — GAP-2 Attempt Tracking and Pivoting

**Status:** PASS (functional and unit/integration-verified; live LLM pivots not
observed because the worker filed no findings)
**Date:** 2026-10-27
**Frozen core:** unchanged

## Delivered

| Area | Files |
|---|---|
| Strix-side attempt/pivot bridge | `strix/strix/core/gap_bridge.py` |
| Report-outcome hook | `strix/strix/tools/reporting/tool.py` |
| Service persistence | `vapt_platform/strix_service.py` |
| Frontend attempt/pivot view | `frontend/web/js/app.js` |
| Reports | `vapt_platform/reporting/renderers.py` |
| Skills | `tests/test_gap2_strix_integration.py` |

## Behavior implemented

- Candidate identity is resolved by endpoint, then title, then target, with a
  stable synthetic id fallback.
- Failures increment a per-candidate attempt counter. At the configured
  threshold (default 2) the candidate is exhausted, the next ranked candidate is
  selected, and a `GAP2_PIVOT` event is written with candidate, attempts,
  threshold, next candidate, and reason.
- Success records `GAP2_SUCCESS`, completes the candidate, and moves to the next
  ranked candidate.
- Exhausted and completed candidates are skipped by `next_candidate()`.
- `_attach_gap2()` returns pivot guidance inside the report tool result, so the
  agent sees the instruction to abandon the current route.
- `STRIX_GAP2_ENABLED=0` disables the hook for comparison.
- Persisted runs expose `total_attempts`, `pivot_count`, `execution_results`
  (outcome + detail), and the decision trace. The frontend shows attempts,
  pivots, threshold, and a GAP-2 event table. Reports include attempts, pivots,
  decision trace, and a dedicated GAP-2 table.

## Verification evidence

- `tests/test_gap2_strix_integration.py`: **11 passed**, including:
  - threshold pivot and trace persistence,
  - success outcomes,
  - independent per-candidate counters,
  - exhausted-candidate skipping,
  - API trace exposure,
  - controlled comparison showing GAP-2 stops at 2 attempts where a baseline
    would repeat 6 times.
- Strix `tests/test_gap_bridge.py`: **12 passed** (attempt, pivot, success,
  matching, threshold fallback, disabled flag).
- Full AI_VAPT suite: **1137 passed** (before the final status-payload field
  addition; the affected 31 tests pass after it).
- Report/UI test `tests/test_strix_ui_reports.py`: **8 passed**.
- Frozen core diff: empty.

## Gate 4

| Criterion | Result |
|---|---|
| Attempt counts tracked per candidate | PASS |
| Outcomes classified | PASS (SUCCESS / FAILURE / ABANDON) |
| Pivot at threshold k | PASS |
| Next candidate from ranked queue | PASS |
| Pivot event has from/to/count/threshold/reason | PASS |
| Pivot history in frontend and report | PASS |
| ≥10 tests | PASS (11 AI_VAPT + 12 Strix) |
| Comparison test | PASS (controlled 2 vs 6 attempts) |

## Honest caveat

Live run `strix-71ec5ad24695` produced no findings, so the Strix agent never
called the report tool and no live GAP-2 attempt/pivot event was generated. The
GAP-2 path is verified by the Strix bridge tests, AI_VAPT integration tests with
recorded event traces, report/UI tests, and a controlled attempt comparison.
This is a model-output limitation, not a silent pass: the live decision trace
contains only `GAP1_QUEUE_WRITTEN` and `GAP1_ROOT_TASK_INJECTED`.
