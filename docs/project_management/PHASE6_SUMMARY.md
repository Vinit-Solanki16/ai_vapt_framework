# Phase 6 — Unified UI and Reports

**Status:** PASS
**Date:** 2026-10-27
**Frozen core:** unchanged

## Delivered

| Area | Files |
|---|---|
| Run overview + GAP views | `frontend/web/js/app.js` |
| Reports | `vapt_platform/reporting/renderers.py`, `models.py`, `builder.py` |
| Status payloads | `vapt_platform/strix_service.py`, `services/schemas.py` |
| Tests | `tests/test_strix_ui_reports.py` |

## Behavior implemented

- Strix run detail now shows:
  - provider/model, scan mode, target, status, findings, requests, tokens,
  - native `output_dir` and artifact paths,
  - GAP-1 original vs ranked order, quality, priority, and assessment reasoning,
  - GAP-2 total attempts, pivot count, threshold, and an event table with
    candidate, outcome, attempt, next candidate, and detail,
  - the full decision trace.
- API status payloads expose `assessment`, `pipeline_summary`,
  `total_attempts`, `pivot_count`, and `execution_results`.
- HTML, Markdown, and plain-text reports add:
  - **Strix Execution Provenance** (provider/model/scan mode/engine run/native
    output/tokens),
  - **GAP-1 Candidate Ranking**,
  - **GAP-2 Attempts and Pivots**.
- JSON reports expose `strix_provenance`, `gap1_ranking`, and
  `gap2_decision_trace` at the top level, while retaining `pipeline_summary`.
- Existing report sections for evidence tier, validation status, attempts,
  pivots, and decision trace remain intact.

## Verification evidence

- `tests/test_strix_ui_reports.py`: **8 passed**.
- Full AI_VAPT suite: **1137 passed**.
- `app.js` syntax checked with Node 22 (`node --check`): PASS.
- HTTP page smoke check: `GET /` returned **200**.
- JSON/HTML/Markdown/TXT tests assert the new sections and fields.
- The GAP-1 reasoning string and GAP-2 pivot detail are asserted in HTML,
  Markdown, and TXT output.
- Report test asserts no credential fields in Strix provenance.

## Gate 6

| Criterion | Result |
|---|---|
| Run overview shows key metrics | PASS |
| GAP-1 view with reasoning | PASS |
| GAP-2 pivot timeline | PASS |
| Decision trace table in report | PASS (raw trace + structured GAP-2 table) |
| JSON/HTML/MD/TXT include GAP-1 + GAP-2 | PASS |
| Native Strix output linked/accessible | PASS (path and artifact list; local filesystem, not a web file server) |
| Responsive / no console errors | PARTIAL: JS syntax verified; no interactive browser console session |

## Honest caveat

"Native output linked" means the UI exposes the recorded output directory and
artifact paths. The AI_VAPT server does not serve arbitrary filesystem paths, so
there is no clickable download link to Strix run directories. Adding such a
download endpoint would need an explicit path allowlist.
