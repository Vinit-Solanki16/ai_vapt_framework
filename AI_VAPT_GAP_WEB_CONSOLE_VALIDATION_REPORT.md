# AI-VAPT — GAP-Enabled Web Console End-to-End Validation Report

**Repository:** `/home/vinit/AI_VAPT/ai_vapt_framework`
**Branch:** `ai-vapt-full-application` (never switched)
**Checkpoint preserved:** `f4a21079bec1ff0047e438ba2872b28dc486b73e` (HEAD; no commit, push, reset, clean, stash, or history rewrite)
**Target:** `http://127.0.0.1:3000/` — authorized local OWASP Juice Shop v20.3.0
**Report date:** 2026-11-18
**Fresh Web Console run:** `run-acfce979` — **COMPLETED** (model-driven, genuine)

---

## 1. Architecture and execution flow verified in current code

1. **Web Console** (`strix/interface/web/index.html`, `js/app.js`) submits `POST /runs` with target, mode, scan depth, turn limit, GAP-2 threshold, provider/model and runtime credential/base URL. Credentials are held in-memory; the Cloud Hosted panel otherwise uses saved profiles. For this validation I used the documented per-request runtime path (`assessor_provider`, `assessor_model`, `assessor_api_base`, `assessor_api_key`) — the same API contract the UI calls — so no persistent profile was created or changed.
2. **FastAPI control plane** (`create_run` at `api.py:6276`) validates Docker/scope, resolves provider credentials, persists a run record, and spawns `_execute_run_worker`.
3. **Worker** (`api.py:3492`) writes `control/gap1_queue.json`, sets `STRIX_GAP_CONTROL_DIR`, `STRIX_GAP1_ENABLED=1`, `STRIX_GAP2_ENABLED=1`, and launches a real Strix CLI subprocess with a **dedicated engine run name** (`run-acfce979-engine`) so the engine and dashboard do not race on one `run.json`.
4. **Strix engine** (`runner.py`) probes GAP-1 candidates with real HTTP requests, then hands control to the autonomous model loop. Specialist agents, 46+ tools, coverage, verification, report and SARIF generation are unchanged. This run used the Root Agent with real `exec_command` tool calls inside the Docker sandbox.
5. **GAP-1** (`exploit_assessor.py`, `gap_run.py`): 22 ranked candidates injected into both the control queue and the model task context.
6. **GAP-2** (`decision_engine`, `gap_bridge`, `gap_run`): bounded attempts (k=2), real alternatives, strict pivot counting requires alternative execution.
7. **Telemetry sync** (`api.py:_sync_telemetry`) tails engine logs, parses turn/tool events, and reconciles from the engine's authoritative `.state/gap_state.json`. **New in this session:** it also counts productive tools from `run.json["tool_calls"]` telemetry.
8. **Terminal state** (`api.py:4900+`): worker requires clean subprocess exit plus model participation and productive security-tool execution before `completed`.

Two GAP state systems remain: engine-authoritative `run-acfce979-engine/.state/gap_state.json` (22 candidates, 44 probe outcomes) and control-plane `run-acfce979/control/gap_state.json` (0 candidates, 22 probe outcomes). The worker reconciles from the engine file.

---

## 2. Root cause of the previous Web Console failure (600s)

Two distinct causes were confirmed:

1. **`run-043060b0` (previous session):** `scan_mode="quick"` set a hard 600s wall-clock floor (`wall_clock_timeout = max(600, min(3600, max_turns*30))` at `api.py:4329`). The Kaggle tunnel's ~90–121s calls and 6 HTTP 524 timeouts exhausted that window. Environmental latency + config, not an application logic defect.
2. **`run-3dd5de38` (this session, `deep`/200 turns):** the worker's no-progress detector saw **zero** productive turns despite 19 real `exec_command` calls, because it only matched `Invoking tool` log lines. This SDK records tools as `Processing output item type=function_call` and in `run.json["tool_calls"]`; the log tail had no `Invoking tool` lines for those tools. At 600s the worker falsely classified a healthy scan as stalled. **This was a genuine application defect** (the documented SDK log-format pitfall), not model latency.

---

## 3. Changes made and files affected (all uncommitted)

| File | Change |
|---|---|
| `strix/interface/api.py` | Added `productive_tool_count(run_data)` helper; `_sync_telemetry` now counts productive `tool_calls` telemetry (and tracks `seen_tool_telemetry`) so SDK log-format differences cannot cause a false stall. |
| `strix/interface/schemas.py` | Added `execution_evidence: dict[str, Any] | None` to `RunStatus` so the dashboard/API exposes the evidence the worker already computed. |
| `tests/test_telemetry_progress_no_false_stall.py` | **New** — 3 regression tests: telemetry counts real tools, excludes bookkeeping, tolerates real run shapes. |

Previously retained (pre-checkpoint / earlier session, still uncommitted): `strix/core/gap_run.py` (strict pivot counting), `strix/core/runner.py` (preparatory probes emit `GAP2_GUIDANCE`, no fake pivots), `strix/interface/api.py` (engine GAP-state reconciliation), plus two earlier GAP test modules. No tests were weakened; no credentials/endpoints were hardcoded; no persistent provider profile was changed.

---

## 4. Provider/model used and how it was configured

- **Provider path:** `custom` (OpenAI-compatible) via per-request `assessor_provider`/`assessor_api_base`/`assessor_api_key`/`assessor_model` in `POST /runs`. The key/base URL were supplied at runtime and registered in the app's in-memory runtime credentials; nothing was written to `~/.strix/cli-config.json` or source. No secret is reproduced in this report.
- **Endpoint (operator-supplied):** Cloudflare Quick Tunnel to the hosted OpenAI-compatible inference server. Verified: `/v1/models` HTTP 200 (`kaggle-model`, 30.5B params, 131,072 ctx); chat completion HTTP 200 (~20.9s cold, ~8–27s warm); structured tool calling HTTP 200 with a genuine `function_call` and correct arguments in 1.8s.
- **Engine subprocess environment verified from `/proc/<pid>/environ`:** `STRIX_LLM=openai/kaggle-model`, `STRIX_LLM_PROVIDER=cloud_hosted`, `STRIX_API_TYPE=chat_completions`, correct base URL, `LLM_TIMEOUT=300`, `STRIX_GAP_*` enabled, separate engine run name. No silent fallback occurred.
- OpenRouter keys supplied for cross-check were valid (8/9 keys, 50/50 free requests each) but were not used for the final run.

---

## 5. Fresh Web Console run ID and terminal status

**Run ID:** `run-acfce979`
**Terminal status:** `completed` — `process_exit_code=0`, `exit_code_interpretation=clean_no_findings`, model called `finish_scan` (`finish_scan: completed scan with 0 vulnerability report(s)`), sandbox torn down, report/SARIF written.
**Duration:** 1335.33s (22m15s), 44 of 200 turns used.
**Engine run:** `run-acfce979-engine`; dashboard run record persisted at `strix_runs/run-acfce979/run.json`.

---

## 6. Actual LLM request and productive tool-execution evidence

- Engine telemetry: **44 LLM requests**, **44 tool calls** — 21 `exec_command` (productive), 22 `record_coverage` (bookkeeping), 1 `finish_scan` (terminal).
- Evidence helper result (computed from run.json telemetry + log): `{'llm_calls': 44, 'security_tool_calls': 21, 'has_model_participation': True, 'has_security_execution': True}` → genuine.
- Model participation confirmed by `Calling LLM` lines and `Starting turn N, current_agent=Root Agent` through turn 44; tool calling confirmed by `Processing output item type=function_call` and `Invoking tool` lines.
- Completion was model-driven (`finish_scan` invoked after candidate investigations), not a scripted or bookkeeping shortcut.
- **Failed comparison run:** `run-3dd5de38` (preserved) had 20 LLM requests and 19 real `exec_command` calls but was falsely terminated at 600s by the stall defect; it is not counted as a completion.
- Evidence artifacts preserved under `/home/vinit/.hermes/cache/scratch/ai_vapt_evidence/` (both runs, raw logs, SARIF, GAP state, report). SHA-256 for the final run: `run-acfce979-engine/run.json` = `9d239a64…546d13a`; `strix.log` = `f56ef3a2…cb99e`; `findings.sarif` = `33e8c1ae…718d981`; engine `gap_state.json` = `2d9bc3e3…248268`; control `run.json` = `e90d3461…f31f50`.

---

## 7. GAP-1 candidate ranking, selection, dispatch, and execution evidence

- `control/gap1_queue.json`: 22 candidates with both `original_order` and `ranked_order` persisted; scores from the project's composite formula (`sqli-login-bypass` 0.992 rank 1, `sqli-login` 0.992 rank 2, `sqli-product-search` 0.934 rank 3, …).
- `control/decision_trace.jsonl`: `GAP1_ROOT_TASK_INJECTED` carries both orders; the engine log shows `Starting automated GAP-1 investigation of 22 candidate(s)` then `Automated GAP-1 probes finished for 22 candidate(s); handing control to the autonomous model loop`.
- Engine `.state/gap_state.json`: 22 candidates, **44 probe outcomes** (2 attempts each at k=2), all with `rank` 1–22. The first probes follow rank order (ranks 1,2,3,4,5 …), proving rank-ordered dispatch and execution.
- Dashboard/API: `gap1_candidates_identified=22`, `candidate_accounting.dispatched=22`, `with_actual_probes=22`, `candidate_to_probe_associations=22`, `investigated=22`, `actual_probe_count=22`.
- **GAP-1 verdict: demonstrated** — ranking influenced actual probe order, dispatch and execution records exist, and control/engine/dashboard agree on the count.

---

## 8. GAP-2 decision-to-alternative execution evidence

**No genuine live GAP-2 pivot occurred in `run-acfce979`.**

- Engine state: strict `pivot_count()` = 0 — zero `pivot_decision` markers and zero probe outcomes with `pivot_executed=True`/`alternative_candidate`.
- Control decision trace: 22 × `GAP2_NEGATIVE_CONFIRMED` (real unsuccessful outcomes) and zero `GAP2_PIVOT`/`GAP2_SUCCESS` directives. Each candidate reached its bounded attempt threshold and was marked abandoned, but no alternative path was dispatched by a decision.
- Dashboard `gap2_pivots=0`, `pivot_events=[]`; SARIF/report show 0 pivots. Engine, control plane and dashboard agree.
- The 22 unsuccessful outcomes are real bounded negative probes (`no_issue_found` in the coverage ledger; `inconclusive` in engine GAP state after two attempts each). They show only that the specific bounded GET checks did not confirm a vulnerability — **not** that those surfaces are secure. The precondition for a pivot existed, but the agent never selected/dispatched/executed an alternative tied to a decision. Counting the preparatory queue walk as a pivot would be false, so it is not claimed.
- Genuine pivot mechanics remain exercised by isolated tests (including this session's reconciliation tests), but **no live pivot is demonstrated**. Honest statement per the task rules: recommendation, counter, queue advance and narrative are not proof.

---

## 9. Dashboard/API/engine/report consistency

| Surface | Observed |
|---|---|
| Web console `GET /runs/run-acfce979` | `status=completed`, `provider=custom`, `model=kaggle-model`, 44 turns, `gap1=22`, `gap2_pivots=0`, evidence exposed after schema fix |
| Persisted control run.json | Same status/counters; `execution_evidence` present (44/21), termination reason names model-called `finish_scan` |
| Engine run.json | `status=completed`, `llm_usage.requests=44`, 44 tool calls, `llm_usage.cost=0`, agent `openai/kaggle-model` |
| Engine `.state/gap_state.json` | 22 candidates, 44 probes, 0 pivots — authoritative |
| Control `control/gap_state.json` | 0 candidate records, 22 probe outcomes — bridge state, intentionally less complete; reconciliation prefers engine state |
| Decision trace | 1 `GAP1_ROOT_TASK_INJECTED` + 22 `GAP2_NEGATIVE_CONFIRMED`, no pivot directives |
| SARIF | 22 coverage results, all `no_issue_found` (bounded negative probe outcome — **not** proof of safety); 0 confirmed vulnerabilities |
| Coverage | 22 surfaces reviewed, 22 `no_issue_found` (bounded negative, not secure/verified), 0 findings, 0 gaps |
| Generated report | Honest: 0 confirmed findings, 0 inconclusive, 22 investigated candidates; target and run metadata correct |

Discrepancies explained: (1) control GAP state has fewer records than engine state — the worker now reconciles from the engine file; (2) `execution_evidence` was initially absent from the API response because `RunStatus` omitted the field — fixed this session and verified after restart; (3) 22 SARIF results are **coverage records**, not findings — `no_issue_found` means a bounded check produced no confirmed issue; it does **not** mean the surface was proven secure, and it is distinct from inconclusive, blocked, untested, and confirmed results.

---

## 10. Findings and evidence quality

- **Confirmed vulnerabilities:** 0 (no finding was forced or assumed).
- **Validated observations:** 0.
- **Inconclusive/unresolved:** 22 candidates investigated with two bounded attempts each; engine records `inconclusive`, coverage ledger records `no_issue_found` for the bounded GET checks. Neither label proves the surface is secure — deeper, authenticated, or parameter-driven testing was not exhaustively performed for every candidate.
- **Blocked:** none from the engine/proxy. Several SQLi payload attempts failed only because the model mis-quoted the shell command; that is a model tool-use failure, not a target control blocking the test. No HTTP 524/timeouts in the final run; the earlier 524s affected only the older Kaggle run.
- **Untested:** full OWASP Top 10 depth was not achieved within 44 turns; authenticated areas were not exercised (no auth config supplied).
- The SARIF `no_issue_found` entries and the report's "0 findings" are consistent with recorded evidence: they mean no confirmed issue was found by the bounded checks performed, **not** that those surfaces were proven free of vulnerabilities. The model-authored narrative is generic and should be read as coverage notes, not validated security assurance.

---

## 11. Focused and full test results

- Focused: **19 passed** (`test_telemetry_progress_no_false_stall.py`, `test_assessment_lifecycle_integrity_regression.py`, `test_autonomous_execution_truthful_completion.py`, `test_gap2_genuine_pivot_reconciliation.py`, `test_gap_state_reconciliation.py`).
- Full suite: **2944 passed, 1 skipped, 3 xfailed, 108 warnings in 437.12s (0:07:17)** — up from 2941 at checkpoint (+3 new regression tests). Command: `.venv/bin/python -m pytest tests/ -q -p no:cacheprovider`. No test was deleted, weakened, or hidden; 1 skipped / 3 xfailed are pre-existing. Log: `/home/vinit/.hermes/cache/scratch/full_pytest_final.log`.

---

## 12. Remaining limitations and readiness verdict

1. **No genuine live GAP-2 pivot** — the precondition existed (22 bounded failures) but no alternative was dispatched/executed from a decision.
2. **Zero confirmed findings** — a valid zero-finding assessment, but the verification pipeline against a real confirmed vulnerability remains unexercised.
3. **Provider latency** — ~22 min for 44 turns; endpoint is usable but slow and tunnel-dependent.
4. **Report narrative quality** — model-authored prose is generic; telemetry/report counts are consistent, but narrative is not evidence-dense.
5. **Control GAP state remains partial by design** — reconciliation uses the engine file; dashboard counts are correct.
6. **Development changes remain uncommitted** per instruction.

**Verdict: END-TO-END WEB CONSOLE ASSESSMENT VERIFIED, WITH A DOCUMENTED GAP-2 LIMITATION.** A genuine, model-driven, GAP-enabled Web Console run against the authorized Juice Shop target completed with consistent state across dashboard, API, engine, GAP state, decision trace, SARIF and report; 44 real LLM requests and 21 real security-tool executions were recorded. The false-stall defect found during validation was fixed and regression-tested. It is not a claim of a demonstrated pivot or of discovered vulnerabilities — neither occurred, and both are reported honestly.
