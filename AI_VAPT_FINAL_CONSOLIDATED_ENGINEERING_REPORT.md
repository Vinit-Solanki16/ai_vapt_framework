# AI-VAPT — FINAL CONSOLIDATED ENGINEERING REPORT

**Repository:** `/home/vinit/AI_VAPT/ai_vapt_framework`
**Branch:** `ai-vapt-full-application` (never switched)
**Scope:** Complete autonomous VAPT platform — architecture verification, defect remediation, GAP-1/GAP-2 integrity, multi-provider support, and real Juice Shop end-to-end validation.
**Target:** `http://127.0.0.1:3000/` — authorized local OWASP Juice Shop installation.
**Testing LLM:** Kaggle-hosted Qwen3-Coder via a temporary OpenAI-compatible Cloudflare Quick Tunnel, configured at runtime only (endpoint/credentials never hardcoded or committed).
**Report date:** 2026-11-18.

---

## 1. Initial repository and checkpoint commit hash

- **Initial HEAD:** `f8b58a2` — `feat: complete AI-VAPT portability, remote Docker runtime, multi-provider AI, and GAP1/GAP2 integration`.
- **Pre-development state:** 44 modified tracked files and 80 untracked files (source, tests, reports, screenshots, launchers). No staged changes; `.env` present but git-ignored.
- **Checkpoint created (Option 2, user-approved):** all 32 files containing the temporary tunnel URL were sanitized first using the neutral placeholder `[temporary Cloudflare tunnel endpoint]`; no credentials were found or included. A reviewed inventory of 124 files was staged, the staged diff was scanned (0 tunnel URLs, 0 real keys), and the checkpoint was committed:
  - **CHECKPOINT COMMIT HASH: `f4a21079bec1ff0047e438ba2872b28dc486b73e`**
  - Subject: `chore(checkpoint): preserve pre-development state with sanitized provider endpoints`
  - 124 files changed, 28,218 insertions, 1,667 deletions. Clean working tree after commit. No push, reset, clean, stash, branch switch, or history rewrite.

---

## 2. Architecture understanding

The application is a control plane + autonomous engine split:

- **Web Console** (`strix/interface/web/`): vanilla JS SPA for target, provider/model, execution limits, live status, agents, candidates, GAP decisions, findings, history, reports.
- **FastAPI backend** (`strix/interface/api.py`, ~7,000 lines): run creation, provider routing, worker orchestration, event/telemetry collection, persistence, reconciliation, report endpoints (`/runs/{id}/report` supports JSON, HTML, PDF, SARIF, Markdown, CSV).
- **Strix engine** (`strix/core/runner.py`): root agent, specialist subagents, 46+ security tools, Docker/Kali/Caido sandbox, MCP tooling. This is the real execution engine and was preserved.
- **GAP-1** (`strix/core/triage/exploit_assessor.py`, `strix/core/gap_run.py`): candidate discovery/ranking; queue injected into the engine through `control/gap1_queue.json` + `STRIX_GAP_CONTROL_DIR`.
- **GAP-2** (`strix/core/decision_engine/`, `strix/core/gap_bridge.py`, `gap_run.py`): bounded failure threshold (k=2), redirect decisions, pivot history.
- **Provider layer** (`strix/llm/router.py`, `strix/core/runtime_credentials.py`, `strix/llm/cloud_provider.py`, `provider_validation.py`): OpenAI-compatible, OpenRouter, Google, Anthropic, Ollama, custom/cloud-hosted; in-memory runtime credentials with profile persistence.
- **Reporting/evidence** (`strix/report/`): verification contract, evidence hashing, SARIF, category ledger, reconciliation.

Two GAP state systems exist: `GapRun` writes the engine-authoritative `<engine-run>/.state/gap_state.json`; `gap_bridge` writes the control-plane `<control>/gap_state.json`. Understanding this split was central to the reconciliation fix.

---

## 3. Original defects identified

From the task brief plus independent verification:

- Early-completion path in the runner skipped `run_agent_loop` after HTTP probes and wrote a synthetic "success" report.
- Worker accepted clean subprocess exit + status label as success with no model/tool evidence.
- GAP-2 success/pivot events could be recorded without alternative-path execution.
- Engine and control-plane pivot counters disagreed (2 vs 0 in the live GAP run).
- GAP-1 prioritization was not consistently visible as influencing real dispatch.
- Stale `running` records, shared run directories, turn/duration errors, frontend polling issues (mostly previously fixed and verified).
- Provider config propagation gaps; temporary endpoint vs persistent profile mismatch; HTTP 524 stream timeouts.
- Reports could claim coverage that was not actually tested.
- Temporary tunnel URLs and a possible 401 from overwritten configuration.

---

## 4. Root causes

1. **Synthetic completion (fixed before checkpoint):** the runner wrote `scan_results["success"]=True`, called `save_run_data(mark_complete=True)`, set root status completed, and returned before the agent loop.
2. **Evidence-free worker success (fixed before checkpoint):** `_execute_run_worker` trusted exit code 0/2 and engine status; candidate counters and trace events counted as progress.
3. **False GAP-2 pivots (root cause found and fixed this session):** three sources emitted "pivot executed" without alternative execution:
   - `GapRun.record_pivot()` incremented a counter for any decision marker;
   - the preparatory HTTP-probe loop called `record_pivot()` when the decision engine merely recommended a REDIRECT to the next item in an already pre-sorted queue;
   - `DecisionEngine.record_outcome()` and `gap_bridge.record_outcome()` emit `pivot_executed=True` as a *directive* (an alternative exists), which downstream reporting treated as proof.
4. **State-system divergence:** the worker read `control_dir/gap_state.json` only, while the engine wrote the authoritative `engine/.state/gap_state.json`. Candidate attempts/states and pivot counters therefore disagreed.
5. **Provider reliability (external):** the Kaggle tunnel is slow (90–121s per call) and timed out (HTTP 524) 6 times in the successful CLI run and caused the GAP web run to hit the 600s wall-clock limit.

---

## 5. Architectural decisions

- Keep Strix as the sole autonomous engine; never substitute a fallback scanner, bookkeeping loop, or generic HTTP probing for real agents.
- Treat execution evidence (recorded LLM calls + productive tool calls) as the only basis for "genuine assessment". Bookkeeping tools never count.
- Define a genuine GAP-2 pivot as: a decision to redirect **plus recorded execution of the selected alternative**. A decision marker, counter, or queue advance is insufficient.
- Make the engine's `GapRun` state authoritative; the worker reconciles from it instead of trusting only its own control-plane bridge state.
- Preserve the decision-engine `pivot_executed=True` *directive* semantics (tests and callers rely on it) while ensuring pivot **counts** require alternative execution evidence.
- Keep provider endpoints/configuration out of source; use runtime credentials/profiles and neutral placeholders in docs.
- Do not weaken tests, hide failures, or force a vulnerability count.

---

## 6. Files and subsystems changed

**Before the checkpoint (prior work, retained and verified):** `strix/interface/api.py` (execution-evidence helpers, no-genuine-execution gate, final-log re-sync, separate engine run name, stale-state quarantine), `strix/core/runner.py` (removed early completion), five legacy test fixtures, new `tests/test_autonomous_execution_truthful_completion.py`, plus sanitized historical reports/docs.

**After the checkpoint (this session):**

| File | Change |
|---|---|
| `strix/core/gap_run.py` | `record_pivot()` now records `type="pivot_decision"` (not a counted pivot); `pivot_count()` requires either a probe outcome with `pivot_executed=True` **or** a decision followed by real alternative execution. |
| `strix/core/runner.py` | The preparatory probe loop emits `GAP2_GUIDANCE` instead of a fake `GAP2_PIVOT`; it no longer calls `gap_run.record_pivot()` for queue advances. |
| `strix/interface/api.py` | New step 3a in telemetry sync reads `<engine-run>/.state/gap_state.json`, reconciles candidate attempts/states, and admits only pivots whose alternative has an execution record. Added `nonlocal productive_turns, last_progress_time` to `_sync_telemetry` for correct final-sync accounting. |
| `tests/test_gap2_genuine_pivot_reconciliation.py` | 4 new tests: decision marker alone ≠ pivot; executed alternative counts; unexecuted alternative doesn't; engine/persisted counters agree. |
| `tests/test_gap_state_reconciliation.py` | 2 new tests: engine state authoritative for attempts/states; only executed alternatives reconcile as pivots. |

---

## 7. GAP-1 implementation and real execution evidence

GAP-1 is active in the web-worker path. Live proof from `run-043060b0`:

- `control/gap1_queue.json`: 3 ranked candidates for the `failure_pivot` scenario — `firewall-blocked-rce` (0.84, rank 1), `waf-drop-sqli` (0.812, rank 2), `phpinfo-disclosure` (0.812, rank 3); both `original_order` and `ranked_order` persisted.
- `control/decision_trace.jsonl`: `GAP1_ROOT_TASK_INJECTED` with both orders.
- Engine log: `Starting automated GAP-1 investigation of 3 candidate(s)` then `Automated GAP-1 probes finished for 3 candidate(s); handing control to the autonomous model loop`.
- The worker's `run.json` recorded `gap1_candidates_identified=3` and candidate accounting with 3 dispatched, 3 with actual probes, and honest not-tested counts on failure.
- General triage (`run_gap1_triage`) produces 20 ranked candidates for the default scenario; scoring uses the project's composite formula (impact/exposure/severity/quality).
- Tests: 71 GAP-related tests pass (including `test_gap1_queue_consumption_and_prioritization`, `test_gap2_pivoting`, `test_gap_bridge`).

GAP-1 influences real execution order: the engine probes candidates in `rank` order, and the model receives the ranked queue in its task context.

---

## 8. GAP-2 implementation and real pivot evidence

**Finding:** in the live GAP run, the engine reported `gap2_pivots=2` but these were false: the trace showed two `type=pivot` markers produced by the automated probe loop for `/exec/` and `/sqli/` (both returned HTTP 200 from the SPA fallback), with no alternative dispatch, no `pivot_executed=True` probe outcome, and the control plane correctly reported 0.

**Fix verified:**

- Recomputing the real run's state with the new strict `pivot_count()` yields **0** — matching the control plane and the truth.
- `record_probe_outcome(..., pivot_executed=True, alternative_candidate=...)` (the genuine-execution path used by the decision engine and tests) still counts correctly — confirmed by 71 targeted tests.
- A `pivot_decision` followed by a real probe on the alternative counts as 1 — covered by new tests.
- The worker now reconciles from the engine state and admits only pivots with alternative execution records.

**Honest status:** no genuine GAP-2 pivot was demonstrated in a live run before the fix because the only live "pivots" were false. The corrected logic prevents false positives; genuine pivoting remains exercised by isolated tests and is available to agent-driven investigation paths when they actually dispatch alternatives.

---

## 9. Multi-provider architecture and validation

- Provider layer supports OpenAI-compatible, OpenRouter, Google Gemini, Anthropic, Ollama, and custom/cloud-hosted endpoints. Runtime credentials can be injected in-memory without touching persisted config; profiles are persisted only through explicit user actions.
- Worker subprocess environment is built from saved config plus runtime values (`STRIX_LLM`, `LLM_API_BASE`/`OPENAI_BASE_URL`, keys, `LLM_EXTRA_BODY`, timeout, tool-choice mode) — verified by the real cloud-hosted run reaching `openai/kaggle-model` and the tunnel host.
- Frontend provider panels (`cloud_hosted`, OpenAI, etc.) post `assessor_provider`, `assessor_api_base`, and profile IDs in the run payload (`app.js:1495-1498`).
- No tunnel URL or hardcoded key remains in source (`grep` returned nothing).
- Provider tests after sanitization: **37 passed, 1 skipped** (`test_cloud_hosted_qwen3_validation`, `test_multi_provider_routing_and_resume`, `test_runtime_api_key_and_readiness`, `test_frontend_ux_and_provider_panels`).

---

## 10. Kaggle-hosted Qwen3-Coder provider validation

- Endpoint (`/v1/models`) returned HTTP 200: `kaggle-model`, ~30.5B parameters, context 131,072.
- Chat completion returned HTTP 200 with a real response; structured tool calling with `tool_choice="required"` returned a genuine `function_call` to `http_request` — not merely text.
- Real CLI run: 65 LLM requests (53 HTTP 200 successes, 6 HTTP 524 timeouts with retries), 4,093,440 input tokens (3,797,968 cached), 5,523 output tokens.
- Agent DB entries carry `provider_data.model = "kaggle-model"` and real response IDs.
- The endpoint is confirmed functional but slow/flaky; it was configured at runtime only. The persistent config was not modified and still points elsewhere.

---

## 11. Actual Juice Shop assessment details

| Run | Path | Terminal state | Duration | Findings |
|---|---|---|---|---|
| `real-e2e-kaggle` | Direct CLI, cloud model | **completed** (model called `finish_scan`) | ~25 min | 0 |
| `run-043060b0` | Web worker, GAP enabled | **failed** — `Assessment exceeded wall-clock limit of 600s` | 10 min | 0 |

Evidence from the completed CLI run: Docker sandbox created; root agent plus Reconnaissance and Vulnerability Assessment specialists; 53 tool calls (37 `exec_command`, 3 `create_agent`, `finish_scan`, etc.); real model-generated `curl` commands against `/api/products`, `/rest/user/1`, `/swagger`, `/`, and href enumeration, with real Juice Shop responses captured in the agent DB. Coverage: 1 surface reviewed, 6 gaps, 0 findings filed. SARIF: one `strix-coverage/attack-surface-mapping` result with `coverage_outcome=no_issue_found`. No destructive actions; scope limited to the authorized local instance.

The reference 11 vulnerabilities were used only as a comparison checklist; none was forced or assumed present.

---

## 12. Real LLM requests and tool execution evidence

- **Endpoint checks:** HTTP 200 for models, chat, and tool-call requests with real function-call arguments.
- **Completed CLI run:** 65 recorded LLM requests (matching `llm_usage.requests=65`), 53 recorded tool calls; the evidence helper returned `{'llm_calls': 53, 'security_tool_calls': 48, 'genuine': True}`.
- **Completion was model-driven:** log shows `function_call` → `Invoking tool finish_scan` → `finish_scan: completed scan with 0 vulnerability report(s)` → root agent completed → report/SARIF written → sandbox torn down. This is the direct inverse of the original bookkeeping-only false completion.
- **Fake-run control:** a constructed bookkeeping-only record yields `security_tool_calls=0, genuine=False`.
- Tests for the evidence gate: 5/5 pass.

---

## 13. Findings and verification outcomes

- **Confirmed vulnerabilities:** 0 in both runs.
- **Validated observation:** 0.
- **Inconclusive/unresolved:** 3 GAP candidates in the web run, all inconclusive after automated probes; correctly marked not-tested/investigated per accounting.
- **Blocked:** none; provider timeouts were retried and ultimately the web run failed on wall clock (reported honestly).
- **False positives avoided:** the SARIF `no_issue_found` coverage entry and the final report's "Vulnerabilities 0" statement were not promoted to findings. XSS/LFI/phpinfo verification rules and the verification contract remain in force.
- The final Markdown report is honest about zero findings but its narrative is generic Juice Shop knowledge rather than run-derived evidence. This is model-produced prose, not fabricated telemetry; a zero-finding assessment is explicitly acceptable under §16.

---

## 14. Dashboard/API/engine consistency

- Separate engine and control-plane run directories verified live (`run-043060b0` vs `run-043060b0-engine`).
- `execution_evidence` persisted with status/counters; genuine failures keep their classification (the 600s timeout was reported as `failed` with a clear reason, not `completed`).
- Frontend treats interrupted/partial/blocked/provider_blocked as terminal.
- **Fixed this session:** worker now reads the engine's authoritative GAP state and only admits pivots with alternative-execution evidence, so engine/control counters can no longer diverge on false markers.
- **Not fully demonstrated:** three-way agreement at a *GAP-enabled completed* terminal state, because the only GAP run failed at 600s. The completed CLI run was internally consistent (status, 65 requests, 53 tools, report files, model-called finish).

---

## 15. Full test results

```
python -m pytest tests/ -q -p no:cacheprovider
2941 passed, 1 skipped, 3 xfailed, 108 warnings in 308.39s (0:05:08)
```

- Up from 2935 at checkpoint: 6 new tests added this session (4 pivot-integrity + 2 state-reconciliation).
- Focused checks after changes: 75 API/lifecycle tests passed; 71 GAP tests passed; 37 provider/frontend tests passed (1 skipped).
- `ruff` on all changed files: only a pre-existing style warning (SIM103 at `api.py:531`), unrelated to this work; no new errors. `compileall` clean.
- The 1 skipped and 3 xfailed are pre-existing environment/expected-failure cases; 108 warnings are third-party deprecations (Starlette/httpx, Pydantic/LiteLLM). No failing test was hidden, deleted, or weakened.

---

## 16. Remaining limitations

1. **No GAP-enabled run reached clean completion.** The only GAP run failed at the hardcoded 600s quick-mode wall-clock limit; the completed run was a raw CLI scan without the GAP control plane.
2. **No genuine live GAP-2 pivot demonstrated.** The two engine "pivots" were false and have been eliminated by the fix; genuine pivoting is test-verified and available to agent-driven paths but unproven live.
3. **Zero confirmed findings.** The verification/report-classification pipeline was exercised only through coverage/SARIF, not against a real confirmed vulnerability.
4. **Provider reliability.** The Kaggle tunnel produced HTTP 524 timeouts and ~90–121s calls; it is adequate for validation but not dependable for bounded full assessments.
5. **Persistent provider config unchanged.** It still points at a different model/base URL; the user must configure the tunnel endpoint through the normal profile/frontend mechanism for persistent use. No credentials were invented or exposed.
6. **Final report quality.** Model-authored narrative is generic; it does not misrepresent telemetry but is not a deep evidence-backed discussion.
7. **Development changes after the checkpoint are intentionally uncommitted**, per the instruction not to commit development work without further approval.

---

## 17. Final readiness verdict

**FUNCTIONAL WITH DOCUMENTED LIMITATIONS.**

Rationale: the platform now demonstrably performs genuine autonomous security testing — the configured cloud model drives real Strix agents and real sandbox `curl`/tool executions, a full model-driven run reaches a truthful completed terminal state, the false-completion paths are closed with an execution-evidence gate, GAP-1 ranking is injected and influences probe order, and GAP-2 false pivots are eliminated with engine/control reconciliation. The full suite is green (2941 passed) and the recovery checkpoint is recorded.

It is not "FULLY FUNCTIONAL — END-TO-END VERIFIED" because no GAP-enabled run completed cleanly, no genuine live GAP-2 pivot was observed, no vulnerability was confirmed, and the hosted endpoint is unreliable within the configured time budget. These are documented, evidence-backed limitations — not hidden failures or fabricated success.
