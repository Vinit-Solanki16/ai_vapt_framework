# Evaluation Report — AI_VAPT + Strix with GAP-1/GAP-2

**Date:** 2026-10-27
**Scope:** AI_VAPT control plane, Strix execution engine, GAP-1 candidate
ranking, GAP-2 attempt/pivot control, multi-model plumbing, unified reports.
**Frozen research core:** unchanged (`git diff -- decision_engine/core/` empty).

## 1. Verification summary

| Check | Result |
|---|---|
| Full AI_VAPT test suite | **1137 passed** |
| Adapter tests (`test_strix_adapter.py`) | **28 passed** |
| GAP-1 tests (`test_gap1_strix_integration.py`) | **9 passed** |
| GAP-2 tests (`test_gap2_strix_integration.py`) | **11 passed** |
| Multi-model tests (`test_strix_multimodel.py`) | **12 passed** |
| UI/report tests (`test_strix_ui_reports.py`) | **8 passed** |
| Strix bridge tests (`tests/test_gap_bridge.py`) | **12 passed** |
| Strix affected suites (inputs/reporting/runner/writer) | **198 passed** |
| Frozen core diff | empty |
| Runtime credential scan of `data/`, reports, and project docs | **0 actual key matches** |

The full Strix repository suite is large (2,499 collected tests) and its
provider/tool-ID matrix is slow; the affected Strix suites and the new bridge
tests were run explicitly and pass. A full-suite run reached 74% (1,872 tests)
before a 25-minute wall-clock cutoff. During that partial run, 19 failures
appeared in upstream budget/runner/MCP/teardown tests due to pre-existing
fixture/API drift (`_start_child_runner(..., skills=...)` and
`settings.telemetry`); none of those files are part of the integration diff.
The remaining 629 tests did not run, so a completed full-suite pass is not
claimed.

## 2. Live Strix runs available

| Run | Config | Provider/model | Status | Requests | Tokens | Findings |
|---|---|---|---|---|---|---|
| `host-docker-internal-9191_6463` | A baseline | OpenRouter free Nemotron | COMPLETED | 30 | 1,864,096 | 0 |
| `host-docker-internal-9191_3f2f` | B GAP-1 only | Ollama qwen2.5:1.5b | INTERRUPTED (720s budget) | 18 | 20,567 | 0 |
| `host-docker-internal-9191_376d` | D GAP-1+GAP-2 | Ollama qwen2.5:1.5b | FAILED (`MaxTurnsExceeded`) | 20 | 23,438 | 0 |
| `host-docker-internal-9191_11cd` | D GAP-1+GAP-2, 50-turn confirmation | Ollama qwen2.5:1.5b | INTERRUPTED after ~10 min stalled at first LLM call | 0 | 0 | 0 |

Live run `_376d` proves the GAP-1 control path end to end:

- original order: `["csrf", "xss", "sqli", "default-creds", "fi"]`
- GAP-1 ranked order: `["default-creds", "sqli", "xss", "fi", "csrf"]`
- `ranking_changed: true`
- Strix bridge emitted `GAP1_QUEUE_WRITTEN` and `GAP1_ROOT_TASK_INJECTED`.

No live GAP-2 attempt/pivot was observed because the worker filed no findings,
so the report tool was never invoked. GAP-2 is evaluated through the controlled
bridge comparison below and the integration/UI/report tests.

### Provider availability constraints

- OpenRouter free-model daily quota returned HTTP 429
  (`free-models-per-day`, reset at 2026-10-28 00:00 UTC) after the baseline.
- The account has no paid credits, so paid fallback models return HTTP 402.
- Local Ollama has only `qwen2.5:1.5b`, which supports tools but does not call
  `finish_scan` within the tested turn budgets.
- No OpenAI/Google/Anthropic runtime keys are configured.

These are external availability limits, not silent test substitutions.

## 3. Controlled A–E comparison

`scripts/strix_gap_evaluation.py` exercises the actual Strix bridge module
(queue file, attempt counters, pivot selection) with deterministic candidate
outcomes. It is not an LLM benchmark; it isolates the GAP decision layer.

Raw output: `docs/project_management/gap_evaluation_results.json`.

| Config | GAP-1 | GAP-2 | Execution order | Attempts | Pivots | Attempts before first finding |
|---|---|---|---|---|---|---|
| A | off | off | csrf → xss → sqli | 13 | 0 | 13 |
| B | on | off | default-creds → sqli | 7 | 0 | 7 |
| C | off | on | csrf → xss → sqli | 5 | 2 | 5 |
| D | on | on | default-creds → sqli | 3 | 1 | 3 |
| E | on | on | default-creds → sqli | 3 | 1 | 3 |

Interpretation:

- GAP-1 alone (B) cuts attempts before the first verified finding from 13 to 7
  by moving the highest-priority candidate first.
- GAP-2 alone (C) cuts attempts from 13 to 5 by abandoning repeated failures at
  threshold 2.
- Combined (D/E) cuts attempts to 3, a **77% reduction** versus A in this
  controlled scenario.
- E is the full integration path (API + persistence + provider metadata); its
  decision-layer result matches D.

## 4. Key metrics captured by the implementation

- candidate ranking and execution order,
- per-candidate attempts,
- pivot count and pivot events (candidate, next candidate, threshold, reason),
- total run duration (from `run.json` start/end),
- requests and token usage,
- findings returned,
- provider/model and scan mode,
- adapter lifecycle status and error,
- provenance tags (`OBSERVED_EXTERNAL`, `SCANNER_DETECTED_CANDIDATE`).

## 5. Limitations and honest conclusions

1. The live LLM configurations did not produce findings, so live time-to-first-
   finding and live pivot counts are unavailable. The controlled comparison
   quantifies the decision layer instead.
2. The hosted provider was only usable before its free daily quota reset; later
   adapter attempts failed at LLM connection with HTTP 429.
3. The local 1.5B model is not a viable autonomous Strix worker for this target
   within practical wall-clock limits.
4. The UI was verified by HTTP smoke checks, JS syntax validation, and
   deterministic payload/report tests, not by a human browser click-through.
5. Native Strix artifacts are exposed as recorded paths, not downloadable via
   the AI_VAPT server.
6. Strix's full 2,499-test suite was not completed: a 25-minute run reached
   74% with 19 pre-existing upstream fixture failures; all changed Strix
   modules were covered by the affected suites and new tests.

The integration, decision hooks, provenance, persistence, reporting, and
multi-model plumbing are implemented and verified at the code/test level. The
remaining gap is live-model evidence, blocked by external provider quota and
local model capability, not by missing integration code.
