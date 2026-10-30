# OpenRouter Optional Provider — Delivery Report

| | |
|---|---|
| **Branch** | `feature/openrouter-provider` (created from `prototype-development` @ `9bad216`) |
| **Commit** | `6040429` — `feat: add optional OpenRouter assessment provider` |
| **Pushed** | yes — `origin/feature/openrouter-provider` only |
| **`prototype-development`** | untouched, still `9bad216` locally and on the remote |
| **Tags** | `v1.0.0-thesis` → `35341a6`, `v1.0.1-thesis` → `a3ad9b3`, both unchanged and not re-pushed |
| **Date** | 2026-10-10 |
| **Validation** | **777 passed, 7 skipped, 0 failed** (baseline 737 + 40 new) |

---

## 1. What was delivered

OpenRouter is an **optional, explicitly-selected, opt-in** hosted assessment
provider. It sits alongside the existing Ollama default and the legacy OpenAI
path, and changes none of their behaviour.

| Area | Change |
|---|---|
| `vapt_platform/model_config.py` | single authoritative provider/model registry; `resolve_model`, `default_model_for`, `is_valid_model_name`, env-key lookup |
| `vapt_platform/provider_errors.py` **(new)** | error classification (`rate_limit` / `auth` / `quota` / `timeout` / `not_found` / `bad_request` / `malformed_output` / `unavailable` / `unknown`) plus `redact()` and `describe_error()` |
| `vapt_platform/assessment.py` | `_try_openrouter_assess`; OpenRouter fail-fast at `create_assessor` |
| `core/exploit_assessor.py` | `ChatOpenRouter` wiring in `get_llm`; clamped `_env_int` / `_env_float` |
| `services/schemas.py`, `services/api.py` | `assessor_provider` / `assessor_model` on `RunRequest`, threaded into both `VAPTRequest` adapters; health reports configuration state only |
| `frontend/app.py`, `frontend/web/js/app.js` | provider + model selectors on **both** forms (standard and web run) |
| `vapt_platform/reporting/builder.py`, `renderers.py` | `ai.outcome` provenance rendered in HTML, Markdown and text |
| `requirements.txt`, `pyproject.toml` | `langchain-openrouter==0.2.9`, `openrouter==0.9.2` |
| `README.md`, `.env.example` | provider table, missing-key semantics, tuning bounds |

### Invariants preserved

- `DEFAULT_PROVIDER` = `ollama`; `DEFAULT_OLLAMA_MODEL` = `llama3.2:3b`.
  The Ollama default is deliberately **not** env-overridable.
- OpenRouter is never selected implicitly and never substituted for the
  baseline; its runs stay a separate labelled arm.
- A hosted failure never dispatches to a different provider — the selected
  provider is always the one named in the result.
- Frozen areas untouched: `decision_engine/core/`, `decision_engine/benchmarks/`,
  `experiments/`, `experiments/results/`, `docs/thesis/`.

---

## 2. Independent audit — findings and resolutions

### Finding A — OpenAI semantics had been broken (HIGH) — **FIXED**

The eager missing-key guard originally applied to *any* hosted provider, so
`create_assessor(mode="ai", provider="openai")` without `OPENAI_API_KEY` began
raising. The pre-existing behaviour (verified against `git show HEAD:...`) was
a silent, explicitly-tagged deterministic fallback.

*Resolved:* the guard in `vapt_platform/assessment.py` now runs only for
`provider == "openrouter"`. OpenAI's legacy semantics are restored and pinned
by `test_openai_missing_key_still_silently_falls_back`. The intentional
difference is documented in the `create_assessor` docstring and in `README.md`.

### Finding B — `services/api.py::_run_engine` is dead code (LOW) — **documented, not removed**

The function is never invoked by any endpoint (the live path is
`start_run` → `application.run()`), yet `tests/test_application.py:173` asserts
it is callable. Removing it would break an existing test for no behavioural
gain, so it was left in place and recorded here as a maintenance note.

### Finding C — health endpoint could leak a key — **verified already safe**

`/system/health` reports only `CONFIGURED` / `NOT CONFIGURED` plus the env-var
*name*. Now additionally covered by a parametrised test for both
`OPENROUTER_API_KEY` and `OPENAI_API_KEY`.

### Finding D — reports did not distinguish success from fallback (HIGH) — **FIXED**

Report provenance carried only `mode` / `provider` / `model`, so an exported
report implied the model had answered even when the deterministic assessor
produced the rank.

*Resolved:* `builder.py` derives an `ai.outcome` field from the per-candidate
details, rendered in all three formats:

| Details | `ai.outcome` |
|---|---|
| none recorded | `NOT RECORDED` |
| no fallbacks | `MODEL ASSESSED` |
| all fell back | `DETERMINISTIC FALLBACK` |
| mixed | `PARTIAL (n of m fell back)` |

The fallback reason is carried alongside (`fallback_detail`) and **re-redacted
at the reporting boundary**, so a secret that somehow reached a stored error
string cannot reach an exported artifact.

### Finding E — unbounded env tuning knobs (MEDIUM) — **FIXED**

`OPENROUTER_MAX_RETRIES=999999` and `OPENROUTER_TIMEOUT_S=1000000` were
accepted verbatim.

*Resolved:* `_env_int` / `_env_float` gained `minimum` / `maximum` parameters,
clamped at the `get_llm` call site to retries `0..5` and timeout `1..600`
seconds. Out-of-range values fall back to the default rather than the bound,
so a negative value still yields the default.

### Finding F — `resolve_model` accepted any string (MEDIUM) — **FIXED**

*Resolved:* `is_valid_model_name()` performs a **syntactic** check only —
rejecting non-strings, empty/over-200-char values, leading/trailing
whitespace, internal whitespace, and control characters. It is deliberately
**not** an allowlist, so `OPENROUTER_MODEL` stays fully configurable; the
provider itself answers `not_found` for a slug that does not exist.

Validation is routed through `resolve_model` rather than `default_model_for`,
because the health endpoint calls the latter directly and must never raise.
A malformed `OPENROUTER_MODEL` override therefore still breaks assessment
construction loudly, while `/system/health` stays `200` and reports an
explicit `openrouter_model_error`.

### Finding G — missing-key errors classified as `unknown` — **FIXED**

`classify_error` now recognises credential-configuration failures by message,
so a missing-key `RuntimeError` is categorised `auth` and surfaces as an
actionable condition rather than an opaque one.

---

## 3. Validation

| Check | Result |
|---|---|
| Full suite `python -m pytest -q` | **777 passed, 7 skipped, 0 failed** |
| Baseline comparison | 737 passed / 7 skipped → identical, zero regressions |
| Focused provider suites (141 tests) | passed |
| `python -m compileall` on all changed files | OK |
| Import smoke (`services.api`, `frontend.app`, all changed modules) | OK |
| `pip check` | `No broken requirements found.` |
| Secret scan of staged diff | no secrets (only documented test fixtures) |
| Live OpenRouter API smoke test | **SKIPPED — no credentials present** (`OPENROUTER_API_KEY` unset, `.env` absent) |

### Test inventory

| File | Tests | Purpose |
|---|---:|---|
| `tests/test_openrouter_provider.py` | 45 | provider dispatch, key handling, contract, classification, redaction |
| `tests/test_provider_integration_gaps.py` | 40 | **new** — audit findings A/D/E/F/G plus cross-layer agreement |
| `tests/test_openai_provider.py` | 3 | legacy OpenAI semantics |
| `tests/test_model_selection.py` | 17 | model threading |

Notable new coverage:

- OpenAI still silently falls back while OpenRouter still fails fast — the
  deliberate difference is pinned from both sides.
- Report outcome correctness for success / fallback / partial / none, across
  HTML, Markdown and text renderers.
- Clamp behaviour verified through to the actual `ChatOpenRouter` kwargs
  (`max_retries == 5`, `request_timeout == 600_000` ms).
- **JS ↔ Python registry agreement**: `PROVIDER_MODELS` is parsed out of
  `frontend/web/js/app.js` and compared key-by-key and value-by-value against
  `model_config`, including default-first ordering — so frontend/backend drift
  fails the suite instead of shipping silently.
- Both GUI forms send `assessor_provider` / `assessor_model`; both API
  adapters thread `assessor_model`; health stays `200` with a malformed
  override and never leaks either key.

---

## 4. Dependency note

`openrouter==0.9.2` is pinned deliberately. `openrouter>=0.10` caps `pydantic`
at `<2.13`, which would **downgrade** the pinned `pydantic==2.13.4`. 0.9.2
carries no upper bound, so existing pins hold and `pip check` stays clean.
`langchain-openrouter` is pinned at `0.2.9`.

---

## 5. Known limitations

1. **No live API verification.** Credentials were absent, so the hosted path
   was exercised only through mocked, offline tests. Re-run with a real
   `OPENROUTER_API_KEY` to confirm end-to-end behaviour against the live API.
2. **Finding B remains** — `services/api.py::_run_engine` is unused dead code,
   retained because an existing test asserts it is callable.
3. **`_run_engine` vs `start_run` duplication** is a latent maintenance hazard
   if either adapter changes without the other.
4. The JS provider registry is validated by test rather than generated from
   `model_config`; the test catches drift but does not remove the duplication.

---

## 6. Files changed

```
.env.example                            |  31 ++
README.md                               |  51 +++
core/exploit_assessor.py                |  91 +++++-
frontend/app.py                         |  55 +++-
frontend/web/js/app.js                  | 106 ++++++----
pyproject.toml                          |   5 +
requirements.txt                        |   5 +
services/api.py                         |  63 +++++-
services/schemas.py                     |  16 +-
tests/test_openrouter_provider.py       | 600 +++++++++++++++++++++ (new)
tests/test_provider_integration_gaps.py | 423 +++++++++++++++++++ (new)
vapt_platform/assessment.py             | 135 +++++++++++---
vapt_platform/model_config.py           | 141 ++++++++++++--
vapt_platform/provider_errors.py        | 230 ++++++++++++++++++ (new)
vapt_platform/reporting/builder.py      |  31 ++
vapt_platform/reporting/renderers.py    |  38 +-
16 files changed, 1972 insertions(+), 49 deletions(-)
```
