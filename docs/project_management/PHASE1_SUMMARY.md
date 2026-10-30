# Phase 1 — Strix Adapter and Scope Wrapper

**Status:** PASS (with live-runtime caveat noted below)
**Date:** 2026-10-27
**Frozen core:** unchanged (`git diff -- decision_engine/core/` is empty)

## Delivered

| Area | Files |
|---|---|
| Adapter contracts | `vapt_platform/adapters/base.py` |
| Registry | `vapt_platform/adapters/registry.py` |
| Strix worker adapter | `vapt_platform/adapters/strix_adapter.py` |
| Mandatory scope gate | `vapt_platform/adapters/strix_scope_wrapper.py` |
| GAP control helpers | `vapt_platform/adapters/gap_hooks.py` |
| Public package | `vapt_platform/adapters/__init__.py` |
| API | `services/api.py` (`/strix/*` and `/adapters/*` aliases) |
| Schemas | `services/schemas.py` |
| Tests | `tests/test_strix_adapter.py` |

## Behavior implemented

- `StrixWorkerAdapter` launches Strix with `uv run strix` in non-interactive mode,
  tracks the child process, discovers the newly created `strix_runs/<id>`
  directory, follows `run.json`, and collects `vulnerabilities.json`.
- Scope is enforced before `Popen`: `authorize_strix_target()` calls the
  authoritative `validate_web_target()`. Unauthorized targets never start a
  process.
- Loopback targets are rewritten to `host.docker.internal` only for the Docker
  sandbox boundary; authorization remains anchored to the operator's original
  host:port. Override with `STRIX_SANDBOX_TARGET_HOST`.
- API keys travel only in the child environment (`LLM_API_KEY`), never argv,
  request persistence, logs, or reports. Ambient provider keys are stripped.
- Missing output, malformed findings, startup failures, timeouts, and stops are
  represented as explicit lifecycle states.
- Every launch writes `control/gap1_queue.json`, `gap_config.json`, `scope.json`,
  and `decision_trace.jsonl`.
- Compatibility endpoints are registered: `GET /adapters`,
  `GET /adapters/strix/status`, `POST /adapters/strix/run`,
  `GET /adapters/strix/runs`, `GET /adapters/strix/runs/{run_id}`,
  `GET /adapters/strix/runs/{run_id}/findings`.

## Verification evidence

- `tests/test_strix_adapter.py`: **28 passed**.
- Full AI_VAPT suite at Phase 1 verification: **1083 passed**; current cumulative
  suite after later phases: **1137 passed**.
- Import gate:
  `.venv/bin/python -c "from vapt_platform.adapters.strix_adapter import StrixWorkerAdapter"` succeeds.
- Live adapter launch against `http://127.0.0.1:9191` (proxied DVWA):
  run `strix-b87390af99d9` started, returned a run id, discovered Strix run
  `host-docker-internal-9191_3f2f`, and reached a terminal interrupted state
  after the wall-clock budget; zero findings was handled as a valid empty list.
- HTTP checks: `/`, `/strix/status`, and `/adapters` returned **200**.
- Secret checks: tests assert the runtime key is absent from argv, `request.json`,
  status payloads, and reports.

## Gate 1

| Criterion | Result |
|---|---|
| Adapter imports | PASS |
| Starts Strix and returns `run_id` | PASS (`strix-b87390af99d9`, engine run `_3f2f`) |
| `get_findings` returns normalized list | PASS (unit fixtures; live empty run returns `[]`) |
| Scope blocks unauthorized target | PASS |
| API endpoints return 200 | PASS |
| Missing/malformed output handled | PASS |
| ≥10 adapter tests | PASS (28) |
| No API keys in logs/reports | PASS |

## Honest caveat

The live adapter smoke run reached `RUNNING` and was tracked through discovery,
but the local Ollama model did not finish within the configured wall-clock
budget. This is a model-speed limitation, not an adapter failure; the adapter
correctly marked the run interrupted and collected its empty findings list.
Hosted free-model verification was later blocked by OpenRouter's daily
free-model rate limit (HTTP 429).
