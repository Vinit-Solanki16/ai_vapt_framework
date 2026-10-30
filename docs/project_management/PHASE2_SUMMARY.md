# Phase 2 — Strix Findings Connected to AI_VAPT

**Status:** PASS
**Date:** 2026-10-27
**Frozen core:** unchanged

## Delivered

| Area | Files |
|---|---|
| Strix service | `vapt_platform/strix_service.py` |
| API | `services/api.py` |
| Schemas | `services/schemas.py` |
| Frontend page | `frontend/web/index.html` |
| Frontend logic | `frontend/web/js/app.js` |
| Tests | `tests/test_strix_candidate_integration.py` |

## Behavior implemented

- Strix runs persist as `PersistentRun(mode="strix",
  scenario="strix_web_assessment")`, so they appear in run history and reuse the
  existing findings and reporting surfaces.
- Normalized findings become candidates with:
  - `source_engine="strix"`
  - `evidence_tier="SCANNER_DETECTED_CANDIDATE"`
  - `result_semantic="OBSERVED_EXTERNAL"`
  - `validation_status="SCANNER-DETECTED CANDIDATE (NOT VALIDATED)"`
- The existing report pipeline (`ReportBuilder` + JSON/HTML/Markdown/TXT
  renderers) renders Strix candidates and provenance without a second reporting
  path.
- `/strix/runs` supports launch, list, live status, result collection, and stop.
  Status payloads include assessment and pipeline metadata for the UI.
- The frontend adds a Strix Engine page with a launch form, provider/model
  selection, GAP candidate JSON, threshold, polling, stop, findings table,
  run history, and links to findings/reports.

## Verification evidence

- `tests/test_strix_candidate_integration.py`: **12 passed**, including:
  - persistence and provenance,
  - report rendering from persisted Strix runs,
  - source-run candidate reuse,
  - stop handling,
  - API start/status/result/stop, scope rejection, external acknowledgement,
  - unavailable adapter (503), unknown run (404),
  - frontend presence of engine and provenance.
- Full suite: **1137 passed** (cumulative).
- Frontend served by the running API: `GET /` returned **200**.
- `app.js` syntax checked with Node 22: **OK**.
- API route check confirmed all `/strix/*` and `/adapters/*` routes.
- Live run `strix-71ec5ad24695` (Ollama) is persisted with status polling and
  zero findings, demonstrating the empty-findings path.

## Gate 2

| Criterion | Result |
|---|---|
| Operator can start from frontend | PASS (API + rendered page + JS checked; no interactive browser session was available) |
| Status updates via polling | PASS (5-second polling; live persisted run observed) |
| Findings table with Strix badge | PASS (UI + tests) |
| Reports include Strix findings | PASS (all formats tested) |
| Provenance tags correct | PASS |
| End-to-end test | PASS (fake engine API + persisted run + report) |
| ≥8 integration tests | PASS (12) |

## Honest caveat

The browser page and API were verified through HTTP and automated tests, not by
human click-through. The live Strix model run produced zero findings, so the
non-empty findings table is covered by deterministic fixtures rather than a
live LLM discovery.
