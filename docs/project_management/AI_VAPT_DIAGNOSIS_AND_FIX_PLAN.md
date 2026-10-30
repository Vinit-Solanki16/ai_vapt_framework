# AI-VAPT: Diagnosis and Fix Plan — Model Fallback, Ollama Integration, Scope Preflight, Report Status Consistency

**Generated:** 2026-10-27 (IST)
**Branch:** development
**Model used for this work:** reflection/beam-1.0-501b-a23b:free via Nous Portal
**Baseline test count:** 1057 passing (`uv run pytest -q`)

## 1. Executive summary

Four independent defects were demonstrated in a real run (`98ced3cd-ccd5-4466-9499-07058997aa3a`) and a frontend screenshot. They do not share a root cause:

| # | Symptom | Root cause (audited) | Affected files |
|---|---|---|---|
| 1 | OpenRouter `thinkingmachines/inkling:free` → deterministic fallback labelled as AI assessment | Model rejects generic chat-completion ("restricted to agentic harnesses"); adapter never filters models by API compatibility and never performs a real completion during validation | `core/exploit_assessor.py`, `vapt_platform/assessment.py`, `vapt_platform/model_config.py`, `vapt_platform/openrouter_setup.py` |
| 2 | Ollama `qwen2.5:1.5b` selected but backend default `llama3.2:3b` not installed | Hardcoded default model not present in the running Ollama instance; UI dropdown is static | `vapt_platform/model_config.py`, `vapt_platform/ollama_service.py`, `frontend/web/js/app.js` |
| 3 | `pentest-ground.com:4280` rejected as "outside configured authorized scope" | Backend is correct and fail-closed; env var unset in the running backend, and UI selects "Auto-Detect Active Scope / Direct Scope" without showing which profile/env entry authorizes the target | `vapt_platform/web_target.py`, `vapt_platform/engagements.py`, `frontend/web/js/app.js` |
| 4 | Report says `Validation: NOT AVAILABLE` and candidate `CONFIRMED` simultaneously | `web_executor` maps `CONFIRMED→Outcome.SUCCESS`; metadata counts `SUCCESS` as successful validation; web provenance builder hardcodes `"validation": "NOT AVAILABLE"` | `vapt_platform/web_executor.py`, `vapt_platform/application.py`, `vapt_platform/reporting/builder.py`, `vapt_platform/reporting/renderers.py` |

## 2. Audit findings (exact code paths)

### 2.1 OpenRouter
- `vapt_platform/assessment.py:219` `_try_openrouter_assess` wraps `assess_exploit_quality` in try/except; on failure returns `None`, and the caller applies deterministic fallback without marking the result as fallback in the candidate table.
- `core/exploit_assessor.py:86` `get_llm("openrouter", ...)` constructs `ChatOpenRouter` with no compatibility check.
- `vapt_platform/model_config.py:165` `is_valid_model_name` is syntactic only.
- `vapt_platform/openrouter_setup.py:264` `validate_runtime_key` only verifies catalogue presence; never issues a completion. Falls back to a hardcoded paid-model list when the catalogue is empty (lines 362–366).
- `vapt_platform/provider_errors.py:45` already classifies `Forbidden`/`ForbiddenResponseError` as `auth` category — usable as-is.

### 2.2 Ollama
- `vapt_platform/ollama_service.py:97` `probe_ollama` correctly reports `MODEL_UNAVAILABLE` when the requested model is absent. Confirmed installed set = `{qwen2.5:1.5b}` only.
- `vapt_platform/model_config.py:26` `DEFAULT_OLLAMA_MODEL = "llama3.2:3b"` is not installed; `default_ollama_model_from_env()` does not fall back to an installed model.
- Verified by direct probe: `query_ollama_structured` returns a parsed `x=5` for `qwen2.5:1.5b` in ~1 s.

### 2.3 Scope
- `vapt_platform/web_target.py:459` `authorize_hostname`: with no engagement_id and no env scopes, raises `WebTargetAuthorizationError`. This is correct.
- `vapt_platform/web_target.py:497` external scope path: `any(h == host for h, _port in scopes)` — host match without port at hostname stage, port checked separately in `authorize_port`. Correct.
- `vapt_platform/engagements.py:243` `eng-pentest-ground` is seeded `inactive` with `authorization_reference="PENDING_OPERATOR_AUTHORIZATION_REVIEW"` (a placeholder), so `is_active()` returns False. Correct fail-closed behaviour.
- With `VAPT_AUTHORIZED_WEB_SCOPES=pentest-ground.com:4280`, `validate_web_target` returns authorized and `preflight_web_target` returns HTTP 200. Verified.
- Frontend: `frontend/web/js/app.js:941` renders `-- Auto-Detect Active Scope / Direct Scope --` as the default option; no profile is pre-selected. No preflight gate blocks the Start button.

### 2.4 Reporting
- `vapt_platform/web_executor.py:60` maps `CONFIRMED → Outcome.SUCCESS`.
- `vapt_platform/application.py:365` (domain) / `:502` (persisted) count `successful_validations = sum(... outcome in ("SUCCESS","VALIDATED"))`.
- `vapt_platform/reporting/builder.py:286` (web provenance) hardcodes `"validation": "NOT AVAILABLE"`.
- `vapt_platform/reporting/renderers.py:356` colours candidate row green when `validation_status == 'CONFIRMED'`.
- Result: web provenance says unavailable, candidate table says confirmed, metadata says N successful validations.

## 2.5 Plan corrections (per user review, 2026-10-27)

The following corrections override any conflicting wording in §3–§6.

1. **OpenRouter model compatibility.** Do not mark a model incompatible solely because optional catalogue metadata is absent. Use documented capability information AND an actual minimal completion test. Distinguish unsupported models from authentication errors, rate limits and transient failures (each gets its own category and message).

2. **Ollama selection.** Never silently replace an explicitly selected model with the first installed model. Auto-select an installed default ONLY when the user has not explicitly selected a model. If the selected model is unavailable, display a clear error and ask the user to choose another model. Record the effective model in every run.

3. **Provider testing.** Separate a minimal connection test from a structured assessment test. A one-token completion must not be described as schema validation. Test actual `ExploitAssessment` parsing separately.

4. **Report semantics.** Preserve separate typed fields for validation status, action type, action outcome and confirmed exploit success. If the frozen research-core enum remains unchanged, add application-level metadata and clear presentation labels. Do not rely solely on a textual detail prefix. Derive aggregate counts from candidate records and represent mixed results accurately.

5. **Safety and scope.** Use the authorized local lab as the default end-to-end test. Preserve backend fail-closed authorization, validate scope again at run time, and ensure that failed preflight results trigger no scanner or validator request. Treat external target testing as a separate, explicitly authorized scenario.

6. **Executable verification.** Replace all placeholder commands with actual runnable tests or scripts. Run the full test suite after implementation and report the actual pass, fail and skip counts, Git commit and changed files.

## 3. Implementation plan (ordered, minimal)

### Phase A — OpenRouter compatibility (Phase 2 of user spec)
A1. Add `vapt_platform/model_config.filter_openrouter_models(models, supports_chat=True)` returning (compatible, incompatible) lists. Mark models whose id is in a known-incompatible set or whose catalogue entry lacks `architecture.instruct_type` / chat capability as `supported=False` with reason.
A2. In `openrouter_setup.validate_runtime_key`, when a `requested_model` is supplied, issue a minimal real completion (`POST /chat/completions` with `max_tokens=1`) through the transport seam; classify the result. Return `STATUS_MODEL_UNAVAILABLE` with a clear message on 403/404; record `latency_ms`, `http_status`, `schema_valid`.
A3. In `core/exploit_assessor.get_llm`, for openrouter, do not construct the LLM if the model is in the incompatible set; raise a classified error.
A4. In `vapt_platform/assessment.py`, record `requested_provider`, `requested_model`, `effective_model`, `response_received`, `latency_ms`, `schema_valid`, `error`, `fallback` in the assessment details (already partially present; complete the fields).
A5. Never label deterministic fallback as an LLM assessment: set `ai_outcome = "DETERMINISTIC FALLBACK"` in `_build_web_provenance` when `fell_back == detail_total` (already done) and ensure candidate rows carry `validation_status` unchanged.

### Phase B — Ollama dynamic discovery (Phase 3)
B1. Add `vapt_platform/ollama_service.list_installed_models()` returning the list from `/api/tags`.
B2. In `model_config`, add `resolve_ollama_model(requested)` that returns the requested model if installed, else the first installed model, else `None` with reason.
B3. Frontend: populate the Ollama model `<select>` from `/api/ollama/tags` (or the existing health endpoint) instead of the hardcoded list; show installed models and disable unavailable ones.
B4. Tests: unavailable, missing model, timeout, malformed output, successful inference, fallback.

### Phase C — Scope preflight clarity (Phase 4)
C1. Frontend: display the active authorization profile name + scope entry next to the target input; show "No profile selected — Direct Scope / env scope only" explicitly.
C2. Frontend: disable the Start button until `validateTargetUrl()` returns authorized; show the authorization result inline.
C3. Backend: no weakening. Add regression tests for authorized local targets, exact host/port matching, unregistered external hosts, inactive engagement profiles, malformed targets, authorization failures, and verify no scanner subprocess runs after a failed scope check.
C4. For the configured local lab, register `127.0.0.1:9191` (already in `eng-local-lab`) and verify it passes preflight end-to-end.

### Phase D — Report status consistency (Phase 5)
D1. Rename the web-executor outcome mapping so `CONFIRMED → Outcome.SUCCESS` is documented as "validation confirmed" not "exploit success"; add `Outcome.VALIDATION_CONFIRMED`? No — keep Outcome enum stable; instead set `detail` prefix `VALIDATION_CONFIRMED:` and store `validation_status` on the candidate (already done in `_merge_web_finding_metadata`).
D2. Derive `successful_validations` from `validation_status == "CONFIRMED"` (not from `outcome == "SUCCESS"`), so the count matches candidate rows.
D3. Make `_build_web_provenance` derive `validation` from the candidate records: if any candidate has `validation_status == CONFIRMED` → `"CONFIRMED (N)"`; if validators ran but none confirmed → `"NOT CONFIRMED"`; if no validators ran → `"NOT AVAILABLE"`. Remove the hardcoded `"NOT AVAILABLE"`.
D4. Renderers: candidate row badge colour based on `validation_status` (green only for `CONFIRMED`), with tooltip distinguishing validator success from exploit success.
D5. JSON/HTML/Markdown/TXT must agree — already share `_build_web_provenance`; verify with a test.

### Phase E — Verification (Phase 6)
E1. Start the app with `VAPT_AUTHORIZED_WEB_SCOPES=pentest-ground.com:4280` (or use the local lab only).
E2. Browser scenario A: incompatible OpenRouter model → failure shown, no LLM claim, fallback labelled.
E3. Browser scenario B: compatible OpenRouter model → connection validation succeeds, real inference, model named, fallback false. (Requires a valid key; if none, document as not verified.)
E4. Browser scenario C: local Ollama → model discovered dynamically, invoked, assessment shown.
E5. Browser scenario D: authorized local web assessment → scope preflight succeeds, Nmap/Nuclei run, findings appear, model responds, validators produce evidence, report matches backend.
E6. Browser scenario E: out-of-scope target → UI rejects, no scan/validation sent, report identifies policy rejection.
E7. Browser scenario F: report correctness — candidate status matches validation evidence, attempt trace and aggregate statuses agree, validator success not mislabelled as exploit success.

### Phase F — Evidence (Phase 7)
F1. Write `docs/project_management/AI_VAPT_DIAGNOSIS_EVIDENCE.md` documenting root causes, files modified, tests run and outcomes, screenshots, verified runs.
F2. Capture screenshots of the running frontend for each scenario.

## 4. Tests to add

- `tests/test_openrouter_compatibility.py` — incompatible model filtering, real completion validation, 401/403/404/429/timeout/malformed handling, no key leakage.
- `tests/test_ollama_dynamic_discovery.py` — installed-model listing, missing model, timeout, malformed output, successful inference, fallback.
- `tests/test_scope_preflight.py` — authorized local, exact host/port, unregistered external, inactive engagement, malformed target, authorization failure, no subprocess after failed scope check.
- `tests/test_report_status_consistency.py` — web provenance validation derived from candidates, candidate row agrees, JSON/HTML/MD/TXT agree, validator success not labelled exploit success.

## 5. Verification commands

```
uv run pytest -q
uv run python -c "from vapt_platform.ollama_service import query_ollama_structured; ..."
VAPT_AUTHORIZED_WEB_SCOPES=pentest-ground.com:4280 uv run pytest tests/test_scope_preflight.py
```

## 6. Constraints honored

- No broad refactor; only the files listed above.
- No scope weakening; fail-closed gate preserved.
- No unauthorized external targets; local lab (127.0.0.1:9191) used for E2E.
- No API keys in logs/reports/UI/browser storage.
- Provider success claimed only after a real inference response.
- Application verification claimed only after tests pass.

## 7. Status

Audit complete. Plan written. Implementation not yet started. Next action: Phase A (OpenRouter compatibility).
