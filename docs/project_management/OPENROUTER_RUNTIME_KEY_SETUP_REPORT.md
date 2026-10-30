# OpenRouter Runtime Key Setup — Delivery Report

| | |
|---|---|
| **Branch** | `feature/openrouter-ui-key-setup` (created from `feature/openrouter-provider` @ `b49dd1f`) |
| **Commits** | `feat: add in-UI OpenRouter credential setup` · `docs: document OpenRouter runtime key setup` |
| **Pushed** | yes — `origin/feature/openrouter-ui-key-setup` only |
| **Not merged** | `prototype-development` untouched at `9bad216` locally and on the remote |
| **Tags** | `v1.0.0-thesis` → `35341a6`, `v1.0.1-thesis` → `a3ad9b3`, both unchanged and not re-pushed |
| **Date** | 2026-10-10 |
| **Validation** | **884 passed, 7 skipped, 0 failed** (previous 777 + 107 new) |
| **Live API test** | **NOT PERFORMED** — no key was supplied to this session; all validation is offline and mocked |

---

## 1. What was delivered

A complete runtime credential-setup flow so the OpenRouter arm can be used
**without** a Codespaces secret, a `.env` edit, a server restart, or any
terminal interaction. The user pastes a key into the UI, validates it against
the live catalogue, picks a free model, and runs.

| Area | Change |
|---|---|
| `vapt_platform/openrouter_setup.py` **(new, 401 L)** | status constants, `RUNTIME_KEY_HEADER`, injectable HTTP seam, `is_free_pricing`, `parse_catalogue`, `sort_models`, `validate_runtime_key`, `pick_default_model`, actionable `HELP_TEXT` |
| `services/schemas.py` | `OpenRouterValidateRequest` (model only — no key field), `OpenRouterModelInfo`, `OpenRouterValidateResponse`; `RunRequest` docstring now documents header-based transport |
| `services/api.py` | `Header` extraction, `POST /providers/openrouter/validate`, `GET /providers/openrouter/status`, `_runtime_key()`, secret-redacting `_safe_error_detail(..., extra_secrets=)` |
| `frontend/web/js/app.js` | in-memory session, setup panel, free-first model sync, validation, gating, header transport |
| `frontend/app.py` | Streamlit *OpenRouter Setup* panel, session-state key, run gate, `VAPTRequest(assessor_api_key=…)` |
| `README.md`, `.env.example` | runtime setup section, status table, security properties, env-var demoted to optional server-wide fallback |
| `tests/test_openrouter_runtime_key.py` **(new, 980 L, 107 tests)** | offline coverage of every requirement below |

Diff: **6 files changed, 1065 insertions(+), 55 deletions(−)** plus 2 new files
(1381 lines).

---

## 2. Key lifecycle — in-memory only

| Property | Web UI | Streamlit |
|---|---|---|
| Storage location | module-scope object `state.openrouter` | `st.session_state` |
| Masked by default | `type="password"` + Show/Hide | `type="password"`, `autocomplete="off"` |
| Survives reload | **no** — fresh session, key asked for again | **no** |
| Explicit clear | **Forget Key** → full session reset | **Forget Key** → `st.session_state.pop(...)` |
| Shared across sessions | **no** | **no** (per-session state) |

Never written to: `localStorage`, `sessionStorage`, IndexedDB, cookies, the
URL/query string, `.env`, `os.environ`, a run record, a persisted report, a
health response, an event payload, or a log line. Both `services/api.py` and
`vapt_platform/openrouter_setup.py` are asserted source-clean of
`os.environ[...] =` and `os.putenv`.

---

## 3. Transport — browser → own backend → OpenRouter

```
Browser ──X-OpenRouter-API-Key──> FastAPI ──Authorization: Bearer──> openrouter.ai
```

- The web UI sends the key **only** in the `X-OpenRouter-API-Key` header on
  exactly two requests: `POST /providers/openrouter/validate` and `POST /runs`.
- The FastAPI route signature reads it via `Header(None, alias=...)` — it is
  not part of the Pydantic body, so a logged, stored or replayed JSON payload
  contains no secret. A key smuggled into the body is ignored (tested).
- `services/api.py` threads it into **this run's** in-memory `VAPTRequest`
  (`assessor_api_key=`), never into `os.environ`. It is released when the run
  returns.
- Error paths redact: `_safe_error_detail(..., extra_secrets=(runtime_key,))`
  strips the submitted key, the per-request key, env keys and any
  key-shaped substring before a 500 detail leaves the process.
- **CORS was not changed.** `allow_origins=["*"]` was already present and was
  left exactly as found — nothing was widened to make this feature work.

---

## 4. Validation — catalogue only, never a completion

`validate_runtime_key()` makes at most three **GET catalogue/auth** calls:

1. `GET /api/v1/models/user` (authenticated) — proves the key *and* returns the
   model list in one free round trip.
2. On **403** ("only management keys") → `GET /api/v1/auth/key`, then
   `GET /api/v1/models` (public). An ordinary user key therefore still works.
3. On **401** → `invalid_credentials`; on **429** → `rate_limited`; on any
   transport exception, 5xx, or unusable body → `unreachable` — explicitly
   **not** an auth failure, so a network blip never tells the user their key
   is bad.

Endpoint paths and field semantics were verified against the published
OpenRouter API reference before implementation. A key pasted with stray
whitespace/newlines is rejected locally with a clear message **before** any
network call. Results are length-bounded (`MAX_MODELS_RETURNED = 1000`) and
timeout-clamped to `1..600 s`.

Statuses: `not_configured`, `validating`, `configured`, `invalid_credentials`,
`model_unavailable`, `rate_limited`, `unreachable` — each with actionable
`HELP_TEXT` containing no key material.

---

## 5. Free-model catalogue

- **Free ⇔ `pricing.prompt == "0"` AND `pricing.completion == "0"`.** Never
  inferred from a `:free` name suffix (a `:free`-named model with paid pricing
  is reported as paid — tested).
- Missing/absent/malformed pricing is **never** treated as free.
- Free entries are sorted first, each group alphabetical; the list is fetched
  fresh on every validation — no cache, no hard-coded availability.
- Default = `openrouter/free` when present, else the first free entry, else
  **`None`**. A paid model is never selected implicitly.
- The user's own model choice is preserved across validation until they change
  it; until they choose, the UI may only ever move them to a **free** model.
- Choosing a paid model raises an explicit `💰 PAID … $x/M in · $y/M out`
  warning with the derived per-million figures.
- A stale ID (`anthropic/claude-3.5-haiku`, verified removed from the live
  catalogue) yields `model_unavailable` with the full catalogue still returned
  so the UI can offer alternatives.

---

## 6. UI gating

Both `startAssessment()` and `startWebAssessment()` call `openRouterGateError()`
**before** the button enters its in-flight state and **before** any dispatch.
On failure they reveal the setup panel, focus the key field, and render an
actionable message — they never fire a request that would fail at the client.
The gate passes only when a key exists *and* status is `configured`.

Streamlit mirrors this: the gate runs before `VAPTRequest` is built and
`st.stop()`s with three concrete options (paste a key, export the env var, or
pick Ollama), stating explicitly that the platform will not silently switch
providers.

---

## 7. Run threading and session isolation

- Header key → this run's `VAPTRequest.assessor_api_key` → `create_assessor` →
  `assess_exploit_quality` → `get_llm(api_key=SecretStr(...))`. Verified by
  capturing the request object inside a stubbed application.
- `GET /runs` state, `POST /runs` response and the job-manager record are all
  asserted free of the key.
- `assessor_api_key` appears in **no** persistence model and **no** reporting
  module (source-asserted).
- Two sessions validating independently produce independent results; the
  module is stateless and holds no `VALIDATED_KEY`-style global.
- The `POST /providers/openrouter/status` endpoint reports *configuration
  state* only (`env_key_configured: bool`) — never a value.

---

## 8. Provider behaviour preserved

- `DEFAULT_PROVIDER = ollama`, `DEFAULT_OLLAMA_MODEL = llama3.2:3b`, not
  env-overridable.
- `RunRequest()` defaults to `assessor=deterministic`,
  `assessor_provider=ollama`, `assessor_api_key=None`.
- OpenRouter still fails fast at `create_assessor` when *no* key is available
  (session **and** environment both empty).
- OpenAI legacy silent-fallback semantics untouched.
- Report `ai.outcome` provenance unchanged.
- The stale `anthropic/claude-3.5-haiku` entry remains in the offline
  fallback lists, deliberately: it is labelled *availability unverified* in
  the UI and correctly reported `model_unavailable` on validation. Hard-coding
  a different ID would reintroduce exactly the fabricated availability this
  design avoids.

---

## 9. Test coverage (107 new, all offline/mocked)

| Class | # | Covers |
|---|---|---|
| `TestKeyLifecycle` | 16 | header constant, no-key path, no network without a key, no `os.environ` writes, no key in any result string, schema has no secret field, session isolation |
| `TestTransport` | 5 | Bearer header only, key never in the URL, no completion endpoint ever hit, body key ignored, header key passed through |
| `TestValidationStates` | 20 | every status, 403 fallback chain, unusable bodies, malformed keys, stale/malformed model IDs, help text |
| `TestFreeModelHandling` | 15 | pricing-only free detection, name-suffix trap, free-first sort, default never paid, display maths, catalogue cap |
| `TestUiGating` | 14 | panel markup, both gates + early `return`, header-only transport, no browser storage, no DOM echo of the key, Forget Key reset, paid-model protection |
| `TestRunThreading` | 10 | header → `VAPTRequest`, no env write, no echo, no job state leak, body key for CLI, error redaction, persistence/report cleanliness |
| `TestStatusEndpoint` | 4 | state without secrets, env presence flag |
| `TestStreamlitFrontend` | 10 | masked input, session-state only, Forget Key, gate + `st.stop()`, no downgrade |
| `TestUnchangedBehavior` | 6 | defaults, Ollama resolution, CORS unchanged, redaction, standalone reload |

**Live API testing was not performed** — no key was supplied to this session.
Every test mocks the HTTP seam; no test opens a socket.

---

## 10. Validation results

| Check | Result |
|---|---|
| `python -m pytest -q` | **884 passed, 7 skipped, 0 failed** |
| `pip check` | `No broken requirements found.` |
| `python -m compileall` (services, vapt_platform, frontend, tests) | OK |
| `node --check frontend/web/js/app.js` | OK |
| `git diff --check` | OK (no whitespace errors) |
| Secret scan on the diff | no real-looking secrets; fake key present only inside tests |
| Frozen paths (`decision_engine/`, `experiments/`, `docs/thesis/`) | unchanged |
| `git status` for `decision_engine/`, `experiments/`, `docs/thesis/` | empty |
| Tags | `v1.0.0-thesis` → `35341a6`, `v1.0.1-thesis` → `a3ad9b3`, unmoved |

---

## 11. Known limitations

1. **Free availability and rate limits change without notice.** The catalogue
   is authoritative *at validation time*; a model can disappear afterwards and
   will then fail with a classified `not_found`/`unavailable`.
2. **No live end-to-end run was executed** with a real key (none was provided).
   The integration is proven against a mocked transport and a stubbed
   application only.
3. **Streamlit is single-process**: `st.session_state` is per browser session,
   but a multi-worker deployment would not share state (nor should it — the key
   is deliberately not shared).
4. **The `anthropic/claude-3.5-haiku` fallback entry is stale.** Kept on
   purpose (see §8); it validates as `model_unavailable`.
5. **`GET /api/v1/models/user` may return 403** for ordinary keys — handled by
   the documented fallback, but it costs two extra round trips.

---

## 12. How to use it

**Web UI**

1. `uvicorn services.api:app --reload --port 8000` and open the console.
2. New Assessment → Assessor **AI** → Provider **openrouter**.
3. The *OpenRouter Setup* panel appears. Paste the key (masked), press
   **Validate Connection**.
4. Pick a model — free entries are first; `openrouter/free` is preselected.
5. **Use OpenRouter** → **Run**. **Forget Key** at any time.

**Streamlit**

1. `streamlit run frontend/app.py`
2. Sidebar → Provider **openrouter** → paste → **Validate Connection** →
   **Use OpenRouter** → Run.

No `.env`. No Codespaces secret. No restart.

---

## 13. Research integrity

- Frozen areas untouched: `decision_engine/core/`,
  `decision_engine/benchmarks/`, `experiments/`, `experiments/results/`,
  `docs/thesis/`.
- Ollama remains the default and `llama3.2:3b` the baseline; neither is
  selectable-by-accident and neither is env-overridable.
- OpenRouter remains a separate, clearly-labelled, opt-in run arm. This change
  affects **how the credential is supplied**, not how a run is scored,
  persisted or compared. No historical baseline result is altered.
- No claim of a live, successful OpenRouter run is made anywhere in this
  report: **the live API test was not performed.**

---

## 14. Files changed

```
 M .env.example                            |  13 +-
 M README.md                               |  57 ++++
 M frontend/app.py                         | 258 +++++++++++++++---
 M frontend/web/js/app.js                  | 638 ++++++++++++++++++++++++++++---
 M services/api.py                         | 101 +++++++-
 M services/schemas.py                     |  53 +++-
?? tests/test_openrouter_runtime_key.py    | 980 lines (new)
?? vapt_platform/openrouter_setup.py       | 401 lines (new)
```
