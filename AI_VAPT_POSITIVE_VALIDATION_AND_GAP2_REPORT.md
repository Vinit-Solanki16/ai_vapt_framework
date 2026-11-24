# AI-VAPT — Positive Vulnerability Validation and GAP-2 Pivot Investigation

**Repository:** `/home/vinit/AI_VAPT/ai_vapt_framework`
**Branch:** `ai-vapt-full-application` (never switched)
**Checkpoint preserved:** `f4a21079bec1ff0047e438ba2872b28dc486b73e`
**Target:** `http://127.0.0.1:3000/` — authorized local OWASP Juice Shop v20.3.0
**Report date:** 2026-11-18

---

## 1. Architecture and finding/GAP-2 execution flow (verified in code)

- **Candidate → finding:** a GAP-1 candidate or an agent-discovered surface is investigated with real tools. `create_vulnerability_report` validates required text, CVSS breakdown, CWE/CVE identifiers and counterevidence, runs LLM deduplication, then persists a report in `ReportState`. `record_vulnerability_outcome` attaches a `VerificationBlock`; if `verification_state=verified` is claimed without reproducible request, response, procedure, demonstrated impact and timestamp, it is downgraded to `unconfirmed`.
- **Verification:** `strix/report/verification.py:evaluate_finding_verification` applies strict per-class rules (XSS needs DOM proof, LFI needs real file content, missing headers are never confirmed). The worker and dashboard both re-evaluate this on load and on sync.
- **Severity/CWE/confidence:** severity/CVSS come from the report's CVSS breakdown; CWE/CVE are validated identifiers; confidence must be `high|medium|low|none`, with rationale required when not high. Endpoint/method are carried on the report.
- **Dedup:** `strix/report/dedupe.py` uses CVE/package identity for dependencies and an LLM judge for same-root-cause/same-endpoint reports; duplicates are rejected rather than silently merged.
- **Report formats:** `GET /runs/{id}/report` serves JSON, HTML, PDF, SARIF, Markdown and CSV. SARIF puts findings under `results[]` with `security-severity` and a `strix` property carrying CWE/CVSS/endpoint/PoC; coverage-only entries use `no_issue_found`.
- **GAP-2:** `DecisionEngine.record_outcome()` applies bounded attempts (k=2) and returns `REDIRECT` + `to_candidate` when a route is exhausted. `record_probe_outcome` records the outcome on `GapRun` and forwards it to the DecisionEngine/bridge, returning `recommended_next_candidate`. A pivot counts only when the selected alternative is actually dispatched and executed and that execution is linked to the decision.

Two runs in this milestone exercised the real Web Console path (`POST /runs` → FastAPI worker → Strix CLI subprocess → Docker sandbox → configured model endpoint). The provider/model were configured per request at runtime (`assessor_provider=custom`, `assessor_model=kaggle-model`, `assessor_api_base`/`assessor_api_key` in-memory). No persistent profile, source file or commit contains a tunnel URL or credential.

---

## 2. Selected Juice Shop scenario and why it is a valid positive control

**Scenario:** SQL injection authentication bypass at `POST /rest/user/login`.

Ground truth was established non-destructively against the local instance before any assessment:

- Baseline `POST /rest/user/login` with `{"email":"test@example.com","password":"wrong"}` → HTTP 401 `Invalid email or password`.
- Injection `{"email":"' OR 1=1--","password":"anything"}` → HTTP 200 `{"authentication":{"token":"...","bid":1,"umail":"admin@juice-sh.op"}}`.

The unauthorized issuance of an admin JWT, with a failing baseline, is a real, reproducible authentication bypass (OWASP Juice Shop's documented SQLi login challenge). Nothing was modified on the target. This is a positive control for detection and verification, not a manufactured vulnerability.

---

## 3. Web Console run IDs and terminal states

| Run | Path | Terminal state | Turns | Notes |
|---|---|---|---|---|
| `run-83bddfea` | Web Console, autonomous, standard, 120 turns | **completed** | 58 | 58 LLM requests, 38 productive tools; model mis-quoted SQLi payloads in shell; 0 findings, 0 pivots. Ran before the GAP-2 fix. |
| `run-e6831990` | Web Console, autonomous, standard, 120 turns | **failed** (context overflow on endpoint) | 26 | Model detected and filed the SQLi finding; evidence complete; no genuine pivot. |
| `run-f8d33035` | Web Console, autonomous, standard, 40 turns | **failed** (no-progress stall at 600s) | 4 | Model filed the SQLi finding but stalled before verification call; finding remains `candidate`. |

No run in this milestone is labelled successful. The first is a genuine but non-positive assessment; the latter two are genuine partial assessments with real findings but failed terminal states, reported as such. Raw evidence for all runs is preserved under `/home/vinit/.hermes/cache/scratch/ai_vapt_evidence/`.

---

## 4. Model and tool-execution evidence

- `run-83bddfea`: 58 LLM requests, 18 `exec_command`, 14 `record_probe_outcome`, 14 `record_coverage`, 2 `apply_patch`, `finish_scan`; evidence `{llm_calls: 58, security_tool_calls: 38, has_model_participation: true, has_security_execution: true}`.
- `run-e6831990`: 25 LLM requests; 11 `exec_command` (baseline 401, injection 200 with admin token, repeat), `create_vulnerability_report`, `record_vulnerability_outcome`, 2 `record_probe_outcome`; evidence `{llm_calls: 25, security_tool_calls: 24, genuine: true}`.
- `run-f8d33035`: 3 LLM requests, 2 `exec_command`, `create_vulnerability_report`; evidence `{llm_calls: 3, security_tool_calls: 2, genuine: true}`.
- All tool calls are visible in `.state/agents.db` with model `kaggle-model` and real response IDs, and in `run.json["tool_calls"]`. No simulated agents or synthetic events were used.

`run-e6831990`'s SQLi evidence, from the agent's own tool results:

```
baseline: HTTP 401 Invalid email or password.
payload:  HTTP 200 {"authentication":{"token":"...","bid":1,"umail":"admin@juice-sh.op"}}
```

---

## 5. Finding details, evidence, verification, CWE, severity, confidence

**Finding `vuln-0001`** (filed autonomously by the model in `run-e6831990` and again in `run-f8d33035`):

- Title: SQL Injection Authentication Bypass in `/rest/user/login`
- Endpoint/method: `/rest/user/login`, POST
- CWE: `CWE-89`; OWASP `A03:2021 – Injection`
- CVSS: 9.8 CRITICAL (`AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H`)
- Confidence: `high` — rationale: injection returned a valid admin JWT with no valid credentials
- Reproducible request: `POST /rest/user/login` with `{"email":"test@example.com' OR 1=1--","password":"anything"}`
- Reproducible response: `HTTP/1.1 200 OK` with `{"authentication":{"token":"...","bid":1,"umail":"admin@juice-sh.op"}}`
- Procedure: baseline 401, then injection payload; impact: full administrative authentication bypass
- Evidence hash: authentic SHA-256 recorded with the finding (`evidence_intact: true`)
- Verification: in `run-e6831990` the model called `record_vulnerability_outcome(verification_state="verified")` with the full evidence block; the tool returned `verified`. The persisted dashboard finding was later re-evaluated to `unconfirmed` by a worker sync defect (root cause in §8). In `run-f8d33035` the model stalled before that call, so `candidate` is the correct state.

The finding is supported by reproducible evidence and a failing baseline; no hypothesis was promoted without it.

---

## 6. Finding consistency across report formats

In `run-e6831990`, the finding appeared consistently at the engine/report level:

- `findings.sarif`: one result, ruleId `CWE-89`, level `error`, `security-severity: 9.8`, logical location `/rest/user/login`, PoC in `properties.strix`.
- `GET /runs/run-e6831990/report?format=json`: one finding with the correct title, severity, CWE, endpoint, evidence hash and SHA-256 integrity.
- `GET /runs/run-e6831990` dashboard/API: the finding appeared only once the worker synced it at terminal state; it was labelled `unconfirmed` because of the defect below, not because evidence was missing.
- Markdown/HTML/PDF/CSV formats derive from the same `findings` collection; no duplicate finding was created. Dedup was exercised by the model's single `create_vulnerability_report` call and the single SARIF result.

Discrepancy: SARIF treats the finding as a confirmed high-severity result (`error`/9.8) while the dashboard showed `unconfirmed`. Root cause and fix are in §8. A repeat run (`run-f8d33035`) produced a single new finding for the same root cause in its own run scope; cross-run dedup was not required because each run has an independent report state.

---

## 7. GAP-2 decision-to-alternative trace — no genuine pivot occurred

`run-e6831990` satisfied the first two pivot conditions: the model recorded two real negative probes against `phpinfo-disclosure` (HTTP 200 SPA fallback, not PHP output). But `recommended_next_candidate` was `null` on both tool responses, no `pivot_decision` was recorded, no distinct alternative was dispatched/executed, and no execution was linked to a decision. Engine GAP state: 0 `pivot_decision`, 0 `pivot_executed`; dashboard `gap2_pivots=0`. **No genuine pivot occurred in any run this milestone.**

Root cause (proven by code and a local state-machine reproduction): the preparatory GAP-1 probe loop fed all 22 candidates × 2 failures into the **shared** DecisionEngine before the model started. That generated 21 unrecorded REDIRECT directives, marked all 22 candidates `ABANDONED`, and left `get_next_available_candidate() == None`. Additionally, `GapRun.sync_decision_engine()` mapped every `investigated` candidate with `attempts > 0` to `ATTEMPTING`, so even after the private-engine fix the model's own `record_probe_outcome` could not select an alternative: all candidates were already ATTEMPTING/ABANDONED. A minimal reproduction with 22 candidates produced exactly `recommended_next_candidate=None`.

A complete pivot requires a candidate pool with at least one genuinely pending alternative at decision time; the prep loop currently exhausts every candidate with bounded GET probes. Fixing that end-to-end would require changing how preparatory evidence gathering interacts with the agent-driven decision queue; that is beyond "minimal defect fix" and is left as an explicit limitation rather than forcing a synthetic pivot.

---

## 8. Root causes and exact code changes

| File | Change | Why |
|---|---|---|
| `strix/core/runner.py` | The preparatory probe loop now uses a private `prep_decision_engine` instead of the shared `decision_engine` for its bounded GET probes. | The shared engine was exhausted before the model started, making agent-driven pivot recommendations impossible. |
| `strix/core/gap_run.py` | `sync_decision_engine()` maps bounded-exhausted `investigated` candidates (`attempts >= max_attempts`) to `ABANDONED` instead of `ATTEMPTING`. | Incorrect "still attempting" state made exhausted routes look like available alternatives. |
| `strix/interface/api.py` | Worker finding sync carries the engine's `verification_state` from the verification block into `evaluate_finding_verification`. | A fully evidenced, engine-verified finding was downgraded to `unconfirmed`/`candidate` because the state field was dropped during flattening. The gate itself is unchanged: evidence missing still downgrades. |
| `AI_VAPT_GAP_WEB_CONSOLE_VALIDATION_REPORT.md` | Terminology corrected: `no_issue_found` is a bounded negative probe outcome, **not** proof a surface is secure; explicitly distinguished from inconclusive, blocked, untested and confirmed. | Prior report could be read as assurance of safety. |
| `tests/test_gap2_prep_queue_preservation.py` | New — 2 tests: prep loop must not call the shared engine; AST check of the call target. | Regression for the GAP-2 root cause. |
| `tests/test_finding_verification_state_propagation.py` | New — 2 tests: evidenced + engine-verified stays verified; missing state still downgrades. | Regression for the verification-state defect (gate not weakened). |

All changes are uncommitted. No tests were weakened or deleted; no scripted substitute or forced result was introduced. Previously retained uncommitted fixes (`gap_run.py` strict pivot counting, `runner.py` no fake pivots, `api.py` telemetry progress + engine state reconciliation + `RunStatus.execution_evidence`) remain intact.

---

## 9. Focused and full test results

- Focused finding/GAP2/API/provider/telemetry: **148 passed** across `test_finding_verification_state_propagation.py`, `test_verification_lifecycle.py`, `test_reporting_fields.py`, `test_reporting_tool.py`, `test_gap2_prep_queue_preservation.py`, `test_phase6_core_runner_gap_integration.py`, `test_phase6_gap_functional_verification.py`; plus **26 passed** for GAP-2 pivot/reconciliation modules and **19 passed** for earlier telemetry/evidence modules.
- Full suite: **2948 passed, 1 skipped, 3 xfailed, 108 warnings in 412.24s (0:06:52)** — up from 2944 (+4 new regression tests). Log: `/home/vinit/.hermes/cache/scratch/full_pytest_milestone2.log`.
- `py_compile` clean on changed source; Ruff showed no new errors attributable to these changes.

---

## 10. Remaining limitations and honest readiness verdict

1. **No genuine live GAP-2 pivot.** The precondition existed but the decision queue was exhausted by preparatory probes; the fix prevents shared-engine consumption and corrects state mapping, but a fresh run demonstrating an executed alternative was not achieved within this milestone.
2. **No cleanly completed positive run.** `run-e6831990` and `run-f8d33035` produced real findings but failed on provider context overflow / a 600s no-progress stall. The finding and evidence are genuine; the terminal states were not `completed`.
3. **Verification-state discrepancy remains visible in historical runs.** New syncs carry the state correctly, but persisted pre-fix records were already downgraded; no retroactive rewrite was performed.
4. **Model tool-use reliability.** The model mis-quoted shell payloads in one run and produced invalid `apply_patch` input in another — model limitations, not application defects.
5. **Provider latency/flakiness.** The tunneled endpoint caused a 75s call, context overflow and a 10+ minute stream stall.
6. **Report narrative** remains model-authored and generic; the technical evidence fields are specific and reproducible.

**Readiness verdict: POSITIVE DETECTION AND EVIDENCE CAPABILITY PROVEN; END-TO-END CLEAN COMPLETION AND GENUINE PIVOT NOT YET PROVEN.** The application detected a real SQLi auth bypass autonomously through the Web Console, captured reproducible request/response evidence, assigned justified CWE/CVSS/confidence, deduplicated, and exposed it in SARIF and reports. Two verified defects were found and fixed with regression tests. It is not yet ready to claim a fully completed GAP-enabled positive run or a live GAP-2 pivot; both remain honest limitations with traced causes.
