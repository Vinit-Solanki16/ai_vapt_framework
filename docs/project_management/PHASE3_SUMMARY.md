# Phase 3 — GAP-1 Candidate Ranking Influences Strix

**Status:** PASS
**Date:** 2026-10-27
**Frozen core:** unchanged; GAP-1 imports the published `priority_score()` and
`rank_candidates()` behavior without modifying `decision_engine/core/`.

## Delivered

| Area | Files |
|---|---|
| Frozen-core bridge | `vapt_platform/adapters/gap_hooks.py` |
| Service queue construction | `vapt_platform/strix_service.py` |
| Adapter queue persistence | `vapt_platform/adapters/strix_adapter.py` |
| Strix-side queue injection | `strix/strix/core/gap_bridge.py` |
| Root task injection | `strix/strix/core/inputs.py` |
| AI_VAPT tests | `tests/test_gap1_strix_integration.py` |
| Strix tests | `strix/tests/test_gap_bridge.py` |

## Behavior implemented

- Candidate fields are mapped into frozen-core `ActionCandidate` inputs and
  ranked with the published formula:
  `priority_score = probability * (0.5 + 0.5 * quality_weight)`.
- The service preserves the operator's original order in
  `EngineRunRequest.gap1_candidates`; the ranked order is persisted in
  `pipeline_summary["gap1_queue"]` and written to `control/gap1_queue.json`.
- Strix's `build_root_task()` appends a GAP-1 instruction block listing
  candidates in ranked order with rank, endpoint, method, quality, priority, and
  reasoning. An event `GAP1_ROOT_TASK_INJECTED` records both orders.
- `STRIX_GAP1_ENABLED=0` disables injection for comparison configuration B/C
  without removing the queue used by GAP-2 tracking.
- The frontend displays original vs ranked order, quality, priority, and
  assessment reasoning.

## Verification evidence

- `tests/test_gap1_strix_integration.py`: **9 passed**.
- Strix `tests/test_gap_bridge.py`: **12 passed**, including:
  - ranked order insertion into `build_root_task`,
  - no-control-dir no-op,
  - original/ranked comparison,
  - disabled-flag behavior.
- Full AI_VAPT suite: **1137 passed**.
- Strix affected suites (`inputs`, `reporting`, `runner prompt`, `writer`,
  `gap_bridge`): **198 passed**.
- Live run `strix-71ec5ad24695` control trace:
  - original: `["csrf", "xss", "sqli", "default-creds", "fi"]`
  - ranked: `["default-creds", "sqli", "xss", "fi", "csrf"]`
  - `ranking_changed: true`
  - event `GAP1_ROOT_TASK_INJECTED` present.
- Frozen core diff: empty.

## Gate 3

| Criterion | Result |
|---|---|
| GAP-1 assesses all candidates and assigns quality ranks | PASS |
| Priority scores displayed | PASS |
| Assessment reasoning visible | PASS |
| Ranked order differs from original | PASS (live trace above) |
| Strix receives GAP-1 ranked order | PASS (root-task injection event + Strix tests) |
| Original vs ranked logged | PASS |
| ≥8 tests | PASS (9 AI_VAPT + 12 Strix) |
| Frozen core unchanged | PASS |
