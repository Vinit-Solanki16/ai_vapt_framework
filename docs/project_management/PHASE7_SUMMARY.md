# Phase 7 — Regression Testing and Evaluation

**Status:** PASS for the integration scope; live-model evaluation and the full
upstream Strix suite are partially blocked (external quota; pre-existing test
drift).
**Date:** 2026-10-27
**Frozen core:** unchanged

## Regression evidence

| Suite | Result |
|---|---|
| Full AI_VAPT suite | **1137 passed** |
| `tests/test_strix_adapter.py` | **28 passed** |
| `tests/test_gap1_strix_integration.py` | **9 passed** |
| `tests/test_gap2_strix_integration.py` | **11 passed** |
| `tests/test_strix_multimodel.py` | **12 passed** |
| `tests/test_strix_ui_reports.py` | **8 passed** |
| `tests/test_strix_candidate_integration.py` | **12 passed** |
| Strix `tests/test_gap_bridge.py` | **12 passed** |
| Strix affected suites (inputs/reporting/runner/writer) | **198 passed** |
| Full upstream Strix suite | **BLOCKED**: 25-min run reached 74% (1,872 tests) with 19 pre-existing fixture failures; 629 not run |

Frozen core check:

```text
git diff -- decision_engine/core/   # empty
git status --porcelain -- decision_engine/core/   # empty
```

Secret check: the configured 73-character OpenRouter key was searched across
`data/`, project docs, and reports; **0 matches**. Pattern hits elsewhere are
placeholder test strings.

## Comparison configurations

The controlled A–E comparison is in
`docs/project_management/gap_evaluation_results.json` and summarized in
`EVALUATION_REPORT.md`:

| Config | Attempts | Pivots | Attempts before first finding |
|---|---|---|---|
| A baseline | 13 | 0 | 13 |
| B GAP-1 | 7 | 0 | 7 |
| C GAP-2 | 5 | 2 | 5 |
| D GAP-1+GAP-2 | 3 | 1 | 3 |
| E full path | 3 | 1 | 3 |

This is a deterministic decision-layer comparison using the actual Strix bridge,
not an LLM benchmark.

## Live runs

- Baseline A: `host-docker-internal-9191_6463`, COMPLETED on
  OpenRouter free Nemotron, 30 requests, 0 findings.
- GAP-1 live injection: `host-docker-internal-9191_376d`, ranking changed from
  `csrf,xss,sqli,default-creds,fi` to
  `default-creds,sqli,xss,fi,csrf`, with `GAP1_ROOT_TASK_INJECTED`.
- Additional hosted runs were blocked by OpenRouter HTTP 429
  (`free-models-per-day`, reset 2026-10-28 00:00 UTC); no paid credits are
  available. Local Ollama qwen2.5:1.5b did not finish within tested turn
  budgets; a 50-turn run stalled at its first LLM call and was stopped.

## Deliverables

- `EVALUATION_REPORT.md`
- `MTECH_IMPLEMENTATION.md`
- `gap_evaluation_results.json`
- `scripts/strix_gap_evaluation.py`
- All phase summaries (1–7) and `PHASE0_BASELINE.md`

## Final gate

| Criterion | Result |
|---|---|
| AI_VAPT + adapter + GAP-1 + GAP-2 tests | PASS |
| Full upstream Strix suite | PARTIAL: affected suites pass; unrelated fixture drift blocks a green full run |
| Frozen core unchanged | PASS |
| No API keys in output | PASS |
| Comparison table A–E | PASS (controlled decision-layer) |
| Evaluation report | PASS |
| MTech documentation | PASS |
| All phases verified | PASS at code/test level; Phase 5 live hosted/local run is documented as blocked |

## Remaining honest gaps

No live LLM run after the baseline produced a finding, so live GAP-2 pivots and
live multi-provider end-to-end runs remain unverified. The full upstream Strix
suite is also not green: its failures are in untouched budget/runner/MCP/
teardown tests whose fixtures predate required `skills` and `settings.telemetry`
arguments. The integration and its decision-layer behavior are verified; the
missing evidence is external provider availability, local model capability, and
upstream test maintenance, not an untested integration path.
