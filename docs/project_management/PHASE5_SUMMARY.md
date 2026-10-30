# Phase 5 — Multi-Model Provider Selection

**Status:** IMPLEMENTED — runtime gate partially blocked by provider availability
**Date:** 2026-10-27
**Frozen core:** unchanged

## Delivered

| Area | Files |
|---|---|
| Provider/model mapping | `vapt_platform/adapters/strix_adapter.py` |
| Runtime key headers | `services/api.py` |
| Dynamic model picker | `frontend/web/js/app.js`, `frontend/web/index.html` |
| Tests | `tests/test_strix_multimodel.py` |

## Behavior implemented

- Supported providers: `ollama`, `openrouter`, `openai`, `google`, `anthropic`.
- Mapping to Strix/LiteLLM:
  - `ollama/<model>`
  - `openrouter/<model>`
  - `openai/<model>`
  - `gemini/<model>`
  - `anthropic/<model>`
- Runtime keys are accepted through `X-OpenRouter-API-Key`,
  `X-Google-API-Key`, `X-OpenAI-API-Key`, and `X-Anthropic-API-Key`, or server
  environment where configured. Keys are never written to run state/reports.
- Ambient provider keys inherited from the parent process are removed before
  launching Strix, so an unrelated shell credential cannot leak into a run.
- The UI provider selector updates its model datalist and default model per
  provider, while still allowing free-text model names.
- Provider/model/scan mode are persisted in `assessment` and
  `pipeline_summary["strix"]`, exposed in status payloads, and rendered in
  reports.

## Verification evidence

- `tests/test_strix_multimodel.py`: **12 passed**, covering:
  - all five provider mappings,
  - hosted API base defaults,
  - header key reaching the adapter without persistence,
  - reasoning-effort propagation,
  - provider/model metadata persistence,
  - unsupported provider rejection (422),
  - ambient key stripping,
  - frontend provider options,
  - compatibility route registration.
- Full AI_VAPT suite: **1137 passed** (the 12 tests above are included).
- Live checks:
  - OpenRouter credential validation previously returned HTTP 200.
  - Baseline Strix run `host-docker-internal-9191_6463` used
    `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` and completed.
  - Adapter launch path was verified with the same provider/model until the
    provider returned HTTP 429 `free-models-per-day`.
- Local Ollama is present with `qwen2.5:1.5b` and supports tools.

## Gate 5

| Criterion | Result |
|---|---|
| Provider dropdown (ollama/openrouter/openai/google, plus anthropic) | PASS |
| Model selection updates per provider | PASS |
| Invalid key error path | PASS at provider-validation endpoints; adapter failure surfaces as run error |
| Selected config reaches Strix | PASS (`STRIX_LLM`, `LLM_API_BASE`, `LLM_API_KEY` tested) |
| Run details show provider + model | PASS |
| Local Ollama end-to-end | BLOCKED: `qwen2.5:1.5b` did not call `finish_scan` within 20 turns; the 50-turn confirmation run stalled at its first LLM call for ~10 minutes and was stopped (0 requests recorded) |
| At least one hosted provider end-to-end | BLOCKED at adapter runtime by OpenRouter free-tier daily 429; the earlier direct Strix baseline completed |
| Anthropic tests (optional) | PASS for mapping and key plumbing; no live Anthropic key available |

## Honest limitation

The provider plumbing and UI are complete and tested, but full live end-to-end
coverage is limited by external availability: OpenRouter's free daily quota was
exhausted, no paid credits/other hosted keys are configured, and the local 1.5B
model is too weak to finish the Strix lifecycle. The baseline completed run
proves hosted Strix execution works; it was not launched through the adapter.
This gate is not overstated as a full live pass.
