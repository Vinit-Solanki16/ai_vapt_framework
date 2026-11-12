# Architecture Gap Analysis — AI-VAPT Full VAPT Lifecycle

**Repository:** `ai-vapt-full-application` branch, `/workspaces/ai_vapt_framework`
**Source:** `strix/` package (rebranded AI-VAPT / Strix) + `strix/interface/api.py` web console
**Analysis date:** 2026-11-09

---

## 1. Executive Summary

AI-VAPT on this branch is an **autonomous agent harness with an optional decision-intelligence add-on** (GAP-1/GAP-2) and a **web-app probe scanner**. It is not a complete VAPT lifecycle:

- Agent orchestration, tool surface, report writers, and provider plumbing are mature, but the *assessment control flow* stops at "reconnaissance → candidate generation → agent investigation".
- Vulnerability verification has **no explicit state machine** and no structured evidence object. A scanner alert or suspicious response can become a finding without reproduction.
- GAP-1 and GAP-2 exist as an **optional, environment-gated bridge** (`STRIX_GAP_CONTROL_DIR`, `STRIX_GAP1_QUEUE`) and are **not integrated into `run_strix_scan`**. The main runner therefore does not drive them by default.
- There is **no live duration timer** and **no surfaced execution phases/turn counts** in the web console or in reports.
- Provider errors are caught in one place (`runner.py`), but quota exhaustion is not distinguished from transient 429s, and partial state is not saved in a way that supports clean resume.

The objectives below (verification states, controlled exploitation, GAP1/GAP2 accounting, live duration, provider resumability, report integrity, regression tests, real DVWA run) are achievable by wiring the existing engine's capabilities into a closed VAPT lifecycle. No duplicate scanners need to be added because the existing engine already provides proxy, shell, coverage, scoring, and report tools.

---

## 2. Architecture Audit (Section 1 of the request)

### 2.1 Assessment creation and configuration
- **Entry point:** `strix/core/runner.py::run_strix_scan` (async, top-level scan runner).
- **Configuration:** `scan_config` dict (targets, scan_mode, skills, resume, instructions). `load_settings()` (pyproject `[dependency-groups].dev` + `[tool.*]` config) drives model, budget, coverage, telemetry.
- **State dir:** `runtime_state_dir(run_dir)` holds `agents.json` (coordinator snapshot), `agents.db` (SDK sessions), `coverage.json`, reports.
- **Workflow gap:** Configuration is passed top-down but there is no persisted "assessment lifecycle" object that records start/end timestamps, phases, turn counts, active agent, and GAP1/GAP2 progress. `ReportState.run_record` holds `start_time`/`end_time`/`status`/`llm_usage`, but interfaces read the *coordinator* and in-memory state for progress, so duration cannot be computed from timestamps and the UI cannot preserve start time across refresh.

### 2.2 Agent orchestration
- `AgentCoordinator` (strix/core/agents.py) owns agent statuses, parent/child graph, mailboxes, snapshot/restore, budget stops, and `respawn_subagents` for resume.
- `run_agent_loop` (strix/core/execution.py) drives one agent; `_run_cycle` handles retries: image-strip, context-overflow compaction, transient model retries (5× exponential backoff), provider refusal, MaxTurnsExceeded.
- Sub-agents spawned from the root; `cancel_descendants` tears down the tree.
- **Gaps:** No per-agent "phase/turn/active task" accounting surfaced to the UI; no mechanism for the root to *guarantee* all reconnaissance + verification assigned skills ran; agent states describe *liveness* ("running/stopped/crashed"), not *assessment progress*.

### 2.3 Reconnaissance and endpoint discovery
- `strix/core/scanner/` (passive_rules, crawler, port_scanner, component_analyzer, active_fuzzer, auth_manager, idor_validator, jwt_inspector, credential_validator, full_scanner) is the white-box/black-box discovery layer.
- `strix/tools/proxy/` (Caido HTTP proxy: `list_requests`, `list_sitemap`, `view_request`, `repeat_request`, `scope_rules`) is the live HTTP attack-surface surface with HTTPQL filtering.
- `strix/tools/web_search` and `strix/tools/output_store` assist recon.
- **Gaps:** Discovery and active testing are *separated* (discovery runs somewhere, then GAP-1 triage, then agents). Nothing in the runner orchestrates "recon → enumeration → discovery → GAP1 → GAP2 → verification" as one continuous pipeline. `ReportState.scan_results` can hold a `scan_matrix`, but the matrix is **reconciled from findings** (`_reconcile_scan_matrix` in api.py), so "test_count" in the matrix does not record how many tests actually executed — only how many findings surfaced, which makes "untested" indistinguishable from "no finding".

### 2.4 Vulnerability candidate generation
- `strix/core/triage/` (exploit_assessor, scoring, owasp_mapping) builds GAP-1 ranked candidate queues for the *decision-engine* path.
- `strix/report/dedupe.py` deduplicates reports via an LLM judge.
- **Gaps:** Candidate generation is not wired into the main runner. The runner's root task is a single prompt; the root agent must *discover* candidates itself, which means discover→candidate is agent-dependent and unreproducible across runs. There is no persisted candidate queue with status (discovered/investigated/validated/abandoned/unresolved).

### 2.5 GAP1 prioritization and investigation
- `strix/core/gap_bridge.py` implements the optional GAP-1/GAP-2 bridge (env-gated `STRIX_GAP_CONTROL_DIR`, `STRIX_GAP1_QUEUE` file `gap1_queue.json`, `record_outcome` with attempt counting and threshold-based pivot, `gap1_instruction_block` that injects the queue).
- `strix/core/decision_engine/` (`DecisionEngine`) implements the bounded retry state machine (ATTEMPTING → VALIDATED/ABANDONED/COMPLETE, RETRY/REDIRECT/ADVANCE/COMPLETE actions, `pivot_threshold`).
- `strix/core/triage/scoring.py::calculate_composite_score` ranks candidates.
- **Gaps:** `gap_bridge` is **not integrated** into `run_strix_scan`. `runner.py` never reads `STRIX_GAP1_QUEUE`, never injects `gap1_instruction_block`, never calls `record_outcome` for investigation outcomes, and never records `GAP2_PIVOT`/`GAP2_ATTEMPT`/`GAP2_SUCCESS`/`GAP2_NEGATIVE` events. The bridge's own `record_outcome` treats tool errors as "error" *without* counting them toward exhaustion (good), but the main flow never surfaces these. `threshold()` is a module env-read; there is no persisted per-run threshold.

### 2.6 GAP2 adaptive pivoting
- The bridge's `record_outcome` returns `attempts`, `threshold`, `pivot` (True when attempts ≥ threshold), `next_candidate`, `status` ("positive"/"negative"/"inconclusive"/"error"), and `guidance_text` for pivots. It appends `probe_outcomes` and writes `decision_trace.jsonl` via `note_event`.
- `DecisionEngine` gives a cleaner state machine with `PivotEvent` list and `decision_trace`.
- **Gaps:** The two modules duplicate the same concept. The bridge is a *file-based control channel* used by an external AI-VAPT adapter (per the docstring), not by Strix's own engine. Nothing in Strix records *which probe produced which outcome*, *why a retry was made*, *what alternative candidate was selected*, *whether a pivot actually executed*, or *the pivot's result*. `test_gap2_pivoting.py` drives `DecisionEngine` directly but this is NOT wired into the scan.

### 2.7 Exploitation and verification tools
- `strix/tools/reporting/tool.py` (`create_vulnerability_report`, `create_dependency_report`, `update_vulnerability_report`, `delete_vulnerability_report`, `list_reports`, `get_report`) is the finding filing tool. Every agent uses it.
- `strix/tools/coverage/tools.py` is the coverage ledger (outcomes: reported / no_issue_found / ruled_out / not_applicable / needs_follow_up), shared across agents, persisted to disk, and callbacks `record_outcome` to the GAP bridge.
- `strix/tools/finish/tool.py::finish_scan`, `strix/tools/agents_graph/`, `strix/tools/threat_model/`, `strix/tools/proxy/` provide the rest.
- **Gaps:** The reporting tool has **no `verification_state` and no structured verification block**. `create_vulnerability_report` takes free-form fields (title, severity, description, impact, target, technical_analysis, poc, remediation, evidence, assumptions, confidences, cvss/cvss_breakdown, endpoint, method, cve/cwe, code_locations, http_exchange_ids, fix_verification, fix_pr_body). Nothing enforces that a finding has a *reproducible request*, a *verification procedure*, a *demonstrated impact*, or an *evidence timestamp*. The `poc_script_code` field is agent free text, not a structured PoC with HTTP exchange id.

### 2.8 Evidence collection and storage
- `ReportState._write_artifacts` writes `vulnerabilities/*.md`, `vulnerabilities.csv`, `vulnerabilities.json`, `run.json`, `coverage.json`, `coverage.pdf` (viewer), and `findings.sarif` (SARIF 2.1.0 via `strix/report/sarif.py`).
- `strix/report/state.py` holds run_record with `mcp_connections`, `mcp_connection_status`, `llm_usage`, `llm_requests`, `tool_calls`, `deleted_vulnerability_reports`.
- **Gaps:** Evidence is stored as a *string* inside each finding. There is no keyed evidence store with (url/endpoint, request, response, timestamp, verification procedure, impact, confidence, severity, remediation) indexed by finding id. Correlating evidence across runs (e.g., comparing two runs of the same target) is not supported because there is no run-to-run evidence registry.

### 2.9 Progress reporting and SSE
- `strix/interface/web/` (index.html, css/styles.css, js/app.js) is a single-page console that loads past runs and the viewer SPA. The FastAPI gateway in `strix/interface/api.py` serves `/`, static css/js, and REST endpoints.
- `strix/interface/viewer/frontend/` is a Vite-built SPA (components under `live/`, `vulnerability/`) that reads run files from disk via `local-run-parser.ts` — it is **not live SSE**; it is a post-run viewer.
- **Gaps:** There is no SSE stream that surfaces run phases, active agent, turn counts, GAP1/GAP2 progress, finding counts, or live elapsed duration. The web console is a read-only past-runs viewer; the "dashboard" requirement (continuously updating elapsed timer, phase, turns, GAP1/GAP2, findings, status) has no live implementation. `response_model.RunStatus` exists in schemas.py but no live endpoint populates it.

### 2.10 Finding deduplication and severity calculation
- `strix/report/dedupe.py` runs an LLM dedupe judge (`check_duplicate`) against existing reports, with a dependency-CVE identity shortcut.
- Severity/confidence/cvss are **agent-provided strings and floats** in `create_vulnerability_report`. There is no severity calculator; `ReportState._LOWERCASE_REPORT_FIELDS` lowercases severity/confidence, but `writer.py::write_vulnerabilities` normalizes severity to `UPPER`. No cross-check that CVSS score range matches the severity label.
- **Gaps:** No builtin severity→Cvss consistency check; no "blocked/unconfirmed" handling; `write_vulnerabilities` does not know about verification states.

### 2.11 Report generation (PDF, HTML, JSON, SARIF)
- HTML: `strix/report/builder.py::render_html_report` (executive report with findings table, scan matrix, ports, components, GAP-1 triage, GAP-2 trace). Reads a `run_data` dict.
- Markdown executive: `strix/report/writer.py::write_executive_report` (static header + final_scan_result from `ReportState.update_scan_final_fields`).
- JSON/CSV/SARIF: `writer.py`, `sarif.py`.
- **Gaps:** There is **no PDF writer** in `strix/report/` (the viewer has `report_pdf.py`, but `ReportState` does not emit a PDF path or ensure PDF/HTML/JSON/SARIF agree on run_id/status/duration/findings). `run.json` (created by `write_run_record`) and `ReportState.run_record` are the same record but written at different layers with different status semantics ("running" before finish, "completed"/"stopped"/"failed" after). Report consumers (viewer, API `_save_run_to_disk`) may disagree on whether a partial run is "partial"/"failed"/"interrupted".

### 2.12 Provider errors, retries, checkpoints, recovery
- `strix/core/execution.py::_is_permanent_quota_error` detects "free-models-per-day", "daily reset", "daily limit", "insufficient_quota", "exceeded your current quota". `runner.py` catches `RateLimitError` → sets status "failed", exit reason "rate_limited", and instructs the user to resume.
- `execution.py` transient retries: image rejections (3 tries, strip images), context overflow (2 compactions), transient model errors (5 tries, backoff).
- **Gaps:** `runner.py` does **not** distinguish "daily quota exhaustion" (permanent) from "transient 429" (retry). A 429 that is daily quota is treated as a transient retry loop. On `RateLimitError`, there is **no partial-state save** of completed findings, no `interrupted`/`provider_blocked` status, no "resume with working provider" guidance recorded in run.json, and no visibility of *which* provider/model failed. There is no checkpoint of completed skills/exploration beyond the coordinator snapshot (which only holds agent liveness, not assessment progress such as discovered endpoints or verified findings). The `strix_runs/` directory in the workspace root also suggests an older run recording channel is present but not used by the current runner.

---

## 3. Gap Summary (Section 2 of the request)

| # | Requirement | Existing capability | Missing / Gap |
|---|-------------|---------------------|----------------|
| 1 | Assessment lifecycle orchestration | `run_strix_scan` + coordinator | No persisted lifecycle object (phases, turns, active agent, GAP1/GAP2 progress) |
| 2 | Reconnaissance & fingerprinting | Strix scanner + Caido proxy + web search | Discovery and testing not wired into one pipeline; report matrix has no test-count record |
| 3 | Endpoint/API/parameter discovery | Caido HTTPQL, sitemap, crawler | Not structured as "test" entries with status (tested/passed/failed/blocked/untested) |
| 4 | Auth/authz testing | `auth_manager`, `credential_validator` | Not orchestrated as a phase; no credential record with usage status |
| 5 | Active vulnerability testing | Agent tools + shell + proxy | No category status ledger; "passed/failed/blocked/untested" lost |
| 6 | GAP1 prioritization | `exploit_assessor`, `scoring`, optional `gap_bridge` | Not integrated into runner; no persisted candidate queue with status |
| 7 | Controlled PoC exploitation | `create_vulnerability_report`, proxy `repeat_request`, shell | No bounded exploitation executor; payloads are agent-generated free text |
| 8 | Independent verification | `coverage` ledger | Coverage records *surfaces*, not *findings*; no finding-level verification state |
| 9 | GAP2 adaptive pivoting | `gap_bridge`, `DecisionEngine` | Duplicated, env-gated, not wired into runner; no probe-outcome/root-cause/alt-candidate/pivot-result record |
| 10 | Post-exploitation impact | (none explicit) | No impact assessment phase |
| 11 | Evidence collection/validation | findings `evidence` string | No structured, keyed evidence; no evidence timestamp |
| 12 | Final findings/report | `ReportState`, writers, SARIF | No live duration; no PDF; no consistent run_id/status/duration/findings across artifacts |

---

## 4. Detailed Gap Analysis (Sections 3–8 of the request)

### 4.1 Finding verification states
**Desired states:** Discovered → Candidate → Under investigation → Exploitation attempted → Verified → Unconfirmed → False positive → Blocked → Inconclusive.

**Current state:** Findings are flat dicts with string `severity`, `confidence`, `cvss`, and free-text `evidence`. There is no independent verification concept. Any HTTP 200, any stack trace, or any scanner alert can be filed as a finding.

**Gaps to close:**
- Add a persistent `verification` sub-object per finding (tab-separated, stored alongside the finding, not a nested free-text blob): `verification_state`, `reproducible_request`, `verification_response`, `verification_procedure`, `demonstrated_impact`, `evidence_timestamp`, `confidence`, `severity`, `remediation`.
- Add a `findings_status`/`coverage_status` ledger that records, per vulnerability *category*, whether it was tested and the outcome (tested+passed / tested+fail / blocked / untested). This directly serves "Do not claim a category was tested when its agent failed, was blocked, or never executed."
- Verification must be *independent*: a scanner alert alone → Candidate/Unconfirmed; only reproduction + response evidence → Verified. This cannot be fully forced by code (LLM agents file findings), but the **report layer** must mark a finding Verified only if `verification_state` is at least "Exploitation attempted" and `verification_procedure` + `demonstrated_impact` are present. Findings lacking this must be downgraded to Unconfirmed/False positive/Blocked in the report artifacts rather than silently presented as confirmed.

### 4.2 Controlled exploitation
**Desired:** SQLi (differential/harmless query), XSS (safe controlled proof), IDOR (authorized vs unauthorized test accounts), SSRF (controlled callback), LFI/path traversal (designated harmless files), command injection (non-destructive).

**Gaps:**
- `create_vulnerability_report` accepts `poc_script_code` and `poc_description` as free text; there is no execution boundary (no timeout, no benign-only payload allowlist) in the existing tooling.
- The existing `shell` tool permits arbitrary commands (intended for the sandbox). Nothing wraps it to restrict to "non-destructive only" and to record a `demonstrated_impact` string.
- To implement controlled exploitation without adding tools: (a) add a `verification` record that captures the *exact* request and response used to verify; (b) add a `BoundedPocExecutor` service whose `execute` takes a `PocDirective` (category + named harmless target + success criteria) and returns structured `poc_result` (payload_sent, observed_response, success, impact_demonstrated). The **report writer** can then refuse to emit a finding as "confirmed" when its `verification.procedure` does not match the recorded PoC directive execution.

### 4.3 GAP1/GAP2
**Desired:** GAP1 distinguishes discovered/investigated/validated/abandoned/unresolved; GAP2 records probe outcome, retry reason, alternative candidate, actual pivot, pivot result. No artificial pivot counts.

**Current state:** `gap_bridge.record_outcome` counts attempts and pivots at a threshold, returns next candidate and guidance. `DecisionEngine` has a clean state machine. Neither is wired into `run_strix_scan`. The file-based bridge is a legacy adapter.

**Gaps to close:**
- Create a **run-scoped GAP service** (e.g. `strix/core/gap_run.py`) with a `GapRun` object persisted to `{state_dir}/gap_state.json`, holding: `candidates` (id + title + endpoint + category + status discovered/investigated/validated/abandoned + attempts + pivot_reason + alternative_candidate + pivot_executed + pivot_result), `probe_outcomes`, `decision_trace`.
- Integrate into `run_strix_scan`: after recon/enumeration skills run, materialize `ActionCandidate` list (from scanner findings + coverage entries + agent-reported coverage), sort by `calculate_composite_score`, call `gap_run.attach_candidates(candidates)`, and render the `gap1_instruction_block` into the root task context as a *prompt* while the driver retains authoritative state.
- During investigation, agents call a new `record_vulnerability_outcome` tool that both updates the coverage ledger and the GAP run state (status, evidence, outcome), persisting after each call.
- GAP2: when an investigation outcome is `inconclusive` or the agent reports retries, the driver records `probe_outcome` (outcome, detail, retry_reason, alternative_candidate, pivot_executed, pivot_result), and only increments `attempts` and marks "abandoned"/"pivoted" when the threshold is met. The driver must **not** fabricate pivots — a pivot is recorded only when `gap_run.record_pivot` is explicitly called with a real alternative candidate and real probe result.

### 4.4 Live duration and timing
**Desired:** persisted start timestamp as source of truth; elapsed from timestamps; continuous SSE update; preserved across refresh; freeze on completion/failure/cancel; completion time + total duration in final report; consistent timezone; no fabricated turns.

**Gaps:**
- `ReportState.start_time` is set at `ReportState()` init (UTC ISO). `save_run_data` writes `end_time`/`status` but there is **no live elapsed** derived from timestamps anywhere. The web console reads past runs and the viewer reads run files; there is no SSE stream.
- **Gaps to close:**
  - Add a `RunLifecycle` (or extend `ReportState`) with `start_time` (persisted), `end_time`, `status`, `phase`, `turns_completed`, `active_agent`, `active_task`, `gap1_candidates`, `gap1_investigated`, `gap2_pivots`, `findings_discovered`, `findings_verified`, `findings_under_investigation`.
  - The gateway must expose an SSE endpoint (`/runs/{run_id}/stream` or `/runs/{run_id}/events`) that emits progress events keyed by the persisted lifecycle (new phase, new finding count, new GAP status, new turn count, timer tick).
  - The frontend (replacing/injecting into the web console) renders an elapsed timer that calculates `now - start_time` from the **persisted** start_time, **not** a counter. On reconnect, it restores start_time from the server and continues.
  - On completion/failure/interrupt, freeze the final duration and write `completed_at` / `final_duration_seconds` into run.json.
  - Final reports (HTML/markdown/PDF/SARIF) include run_id, status, start_time, completed_at, duration, phase, turn count, GAP1/GAP2 progress, findings counts.
  - Use a consistent timezone (e.g. `Asia/Kolkata` as the user's environment suggests; the code samples use `.astimezone()` → local). The user said "Display the correct timezone consistently" — the implementation should read the run-configured timezone and format consistently; default to UTC + offset, or a `TZ` setting. I'll choose: store UTC ISO in run.json, display in a run-persisted `timezone` field (default "UTC"), formatted with explicit offset.

### 4.5 Provider failure handling and resumability
**Desired:** permanent daily quota detected; futile retries stop; partial state saved; completed recon/investigations preserved; run marked interrupted/provider_blocked; resume possible with working provider; previously completed tasks not repeated; provider errors visible/actionable; partial findings/evidence available; no silent model/provider switch.

**Gaps:**
- `runner.py` catches `RateLimitError` and sets status "failed". `execution.py::_is_permanent_quota_error` exists but the runner's `except RateLimitError` branch does not call it, set "provider_blocked"/"interrupted", or persist resumability metadata (which provider/model, quota type, retry-after guidance, failed-attempts log).
- No checkpointing of completed work (recon, investigation) between turns except the coordinator snapshot (agent liveness only). Findings are saved on each `save_run_data` (good), but there is no "completed_skills"/completed_task ledger that resume can consult to avoid re-running.
- **Gaps to close:**
  - In `run_strix_scan`, wrap per-agent turns in a retry loop that (1) on `RateLimitError`/`APIError(429)`, classifies quota vs transient via `_is_permanent_quota_error` and error text, (2) on permanent quota, stops retrying, saves partial state with `status="interrupted"`/`"provider_blocked"`, writes a `provider_error` record (type, category, model, provider, retry attempts, guidance, timestamp) visible in the dashboard, (3) on transient 429/5xx, waits and retries (bounded), and (4) on cancellation, sets "interrupted".
  - Persist a `resume_token`/checkpoint per run that records completed skills, completed endpoints, verified findings, and coverage entries; resume consults it and replays only the un-run portions. The coordinator snapshot already gives agent state; extend it with an `assessment_checkpoint` persisted after each skill completes.
  - Never silently switch provider: if a run is provider-blocked and the user resumes with a new model, `run.json` records `switched_provider: true`, `previous_provider`, `new_provider`, `resume_from: checkpoint_id`, and the dashboard shows it as an actionable error/warning, not a hidden change.
  - Partial findings remain available in `vulnerabilities.json` and the coverage ledger.

### 4.6 Coverage and report integrity
**Desired:** failed tests not "passed"; blocked tests not "vulnerabilities absent"; untested categories explicitly untested; incomplete runs not presented as completed; duplicate findings consolidated; service identification backed by evidence; CDN edge not attributed to origin; CVSS/severity agree; remediation commands reference correct ports/endpoints/components; artifacts agree on run_id/status/duration/findings.

**Current state:** Findings are deduplicated by an LLM judge; severity/confidence/cvss are agent fields. Reports (HTML/markdown/json/sarif) are derived from the same `vulnerability_reports` list, so they agree on findings — but **coverage/status is not derived consistently**: the API's `_reconcile_scan_matrix` counts findings per category, so "untested" is invisible. `ReportState.run_record` is written by both the runner (`write_run_record`) and the state module (`_write_artifacts`), and the API's own `_save_run_to_disk` writes a second `run.json` with its own `findings` from a different channel.

**Gaps to close:**
- Add a category/test ledger: `category_tests` = {category: {tested: bool, passed: bool, failed: bool, blocked: bool, untested: bool, test_count: n, pass_count: n, fail_count: n, blocked_count: n}}. Populate it from the coverage ledger + categories exercised by skills. The scan matrix is then a projection of this ledger, with explicit `untested` rows.
- `write_vulnerabilities`/`writer.py` must not claim "passed" for a category without a `passed` marker; the scan matrix should show "PASSED (verified)", "FAILED (confirmed)", "BLOCKED (not testable)", "UNTESTED (insufficient scope)".
- Coverage entries are agent-reported; report must label provenance (self-report vs machine observation) — already partially done in `strix/report/coverage.py` via `build_coverage_document`.
- Service identification: Caido/proxy sitemap and scanner `component_analyzer` provide service names; the report's open-ports table must not attribute a CDN/edge service to the origin — add a `reverse_proxy`/edge flag sourced from actual response headers (e.g., `server` + `x-cdn` attributes), not from arbitrary banner strings.
- CVSS/severity: add a consistency check in `ReportState` — if `cvss` is set, require `0 <= cvss <= 10`, and map to a severity label; if `severity` is set, map to CVSS band; on save, re-emit both consistently. This is a *consistency reconciliation* on report write, not a re-scan.
- Artifacts: add a single source of truth `run.json` field set (`run_id`, `status`, `start_time`, `completed_at`, `duration_seconds`, `phase`, `turns_completed`, `active_agent`, `active_task`, `gap1_candidates`, `gap1_investigated`, `gap2_pivots`, `findings_total`, `findings_verified`, `findings_unconfirmed`, `findings_blocked`, `findings_false_positive`, `findings_incomplete`). Every writer (HTML/markdown/PDF/SARIF) reads this same record so they agree. `SARIF` already uses `tool.driver.version`; align `run_id` into the `runs` array.

### 4.7 Preserve architecture
The existing engine (agents, SDK, proxy, coverage, report writers, coordinator snapshot, multi-model router with LiteLLM) is preserved. The additions are: a run-scoped lifecycle + progress store, a structured verification record, a bounded PoC executor, an integrated GAP1/GAP2 run service, a live SSE progress stream, a provider-error/resume service, and report consistency reconciliation. No new external security tools are required.

---

## 5. Implementation Roadmap (Staged)

### Stage 1 — Structured findings & verification (backend core)
- Introduce `strix/report/verification.py`: `VerificationBlock` dataclass (verification_state + reproducible_request + verification_response + verification_procedure + demonstrated_impact + evidence_timestamp + confidence + severity + remediation), `VerificationError`/serialization helpers, and a `Finding` model that merges core finding fields + verification.
- Extend `strix/tools/reporting/tool.py` (`create_vulnerability_report`, `update_vulnerability_report`) to accept and persist this block, and to emit a `finding_verified` SSE progress event.
- Add a `findings_status` category ledger to the report state, populated from coverage + skill executions; wire it into the scan matrix output.
- **Tests:** verification states, positive/negative exploit validation, severity/Cvss consistency, duplicate finding detection.

### Stage 2 — GAP1/GAP2 integration
- Create `strix/core/gap_run.py`: `GapRun` (candidates with statuses discovered/investigated/validated/abandoned; attempts; retry reasons; alternative candidates; pivot executed/result; probe outcomes; decision trace) persisted to `{state_dir}/gap_state.json`.
- Extend `strix/tools/reporting/tool.py` with `record_vulnerability_outcome` and `record_probe_outcome` tools that update both coverage and GAP state.
- Wire integration into `run_strix_scan`: materialize candidates, attach to `GapRun`, render `gap1_instruction_block` into context, and drive GAP2 outcome recording on agent outcomes.
- **Tests:** GAP1 accounting, genuine GAP2 pivots, probe outcome recording, no artificial pivots.

### Stage 3 — Live duration + SSE progress + frontend
- Add `RunLifecycle`/`RunProgress` to the report state with persistent start/end timestamps and phase/turn/GAP/findings counters.
- Add `/runs/{run_id}/stream` SSE endpoint to the FastAPI gateway emitting progress events (phase, turns, active agent, GAP1/GAP2, findings, timer tick).
- Extend the web console (`strix/interface/web/js/app.js` / injected viewer) to: on load, fetch persisted run record, restore start_time, render an elapsed timer computed from timestamps, update via SSE without resetting, freeze on terminal, show completed_at/final duration in final report, use consistent timezone.
- Ensure final reports (HTML/markdown/Pdf/Sarif) carry run_id/status/duration/findings and no fabricated counts.
- **Tests:** live elapsed duration, timer persistence after refresh, duration freezing after completion/failure, incomplete coverage reporting.

### Stage 4 — Provider failure handling & resumability
- Refactor `run_strix_scan` retry handling: classify RateLimitError 429 into permanent quota vs transient; permanent → stop, save `provider_error` + `provider_blocked` status + resume guidance; transient → bounded retries.
- Add `AssessmentCheckpoint` persisted to `{state_dir}/checkpoint.json` after each skill/exploration stage; resume consults it to skip already-completed tasks. Coordinator snapshot already preserves agent state; extend checkpoint to "completed endpoints/categories/findings".
- Record provider/provider_model in the provider_error record; include `switched_provider` metadata on resume; never silent switch.
- **Tests:** interrupted assessment recovery, provider rate-limit handling, resumability.

### Stage 5 — Report integrity + completion
- `ReportState` severity/Cvss consistency reconciliation on save; run_record as single source of truth; every artifact (HTML, markdown, PDF, SARIF) reads the same record.
- Final report surface: completed_at, duration_seconds, phase, turns_completed, active_agent, active_task, GAP1/GAP2 progress, findings counts (discovered/candidate/under_investigation/exploitation_attempted/verified/unconfirmed/false_positive/blocked/inconclusive), status, provider_error if any.
- **Tests:** report consistency, incomplete coverage reporting, PDF/HTML/JSON/SARIF agreement.

### Stage 6 — Proof & DVWA assessment
- Run unit/integration regression tests.
- Perform an actual assessment against the authorized DVWA test environment, recording real duration, model/provider, real agent turns, endpoints discovered, categories actually tested, GAP1 candidates investigated, GAP2 pivots executed, exploitation attempts, independently verified findings, unconfirmed/blocked tests, and generated reports/evidence. Clearly separate unit tests, integration tests, and real live assessment results. No fabricated findings/duration/pivots.

---

## 6. Verified facts used in this analysis
- `strix/core/runner.py::run_strix_scan` is the top-level async scan runner; `RunResultBase | None` return.
- `strix/core/agents.py::AgentCoordinator` owns statuses/parents/mailboxes/snapshot; resume via `restore()`.
- `strix/core/gap_bridge.py` is optional (env `STRIX_GAP_CONTROL_DIR`), file-based `gap1_queue.json`, `record_outcome` (attempts/threshold/pivot), `decision_trace.jsonl` via `note_event`; **not** wired into `run_strix_scan`.
- `strix/core/decision_engine/engine.py::DecisionEngine` has a clean retry/pivot state machine and is **not** integrated.
- `strix/report/state.py::ReportState` holds `run_record` (start_time/end_time/status/llm_usage/mcp_connections/tool_calls/llm_requests/deleted_vulnerability_reports) and writes run.json via `write_run_record`; `save_run_data` sets end_time but no live duration.
- `strix/tools/reporting/tool.py` = `create_vulnerability_report` etc.; no verification block.
- `strix/tools/coverage/tools.py` = coverage ledger (reported/no_issue_found/ruled_out/not_applicable/needs_follow_up) with GAP callbacks.
- `strix/tools/proxy/` = Caido HTTP proxy tools (list_requests, list_sitemap, view_request, repeat_request, scope_rules).
- `strix/interface/api.py` = FastAPI gateway (self-contained web console + REST); no live SSE; `_probe_web_candidate` is a web-app probe helper.
- `strix/interface/viewer/frontend` = Vite SPA (post-run viewer; `local-run-parser.ts`), not live SSE.
- Existing tests: `test_gap1_triage.py`, `test_gap2_pivoting.py`, `test_phase1..14_*.py` show phased incremental patterns.
- Env conventions: `uv`/`uv.lock`, `pyproject.toml` (py>=3.12, strict mypy+pyright, ruff, bandit), `make check-all`, `pytest`.

---

## 7. Remaining limitations (explicit)
- Fully *forcing* an LLM agent's findings through a verification state machine is not possible by code alone; the **report layer** enforces that a finding is presented as confirmed only when a structured verification block is present, and downgrades the rest. This is the honest boundary.
- Controlled exploitation cannot be *completely* prevented from a free-text tool; the PoC executor provides a bounded directive + recorded response, and the report writer refuses confirmed status without it. Real safety is a property of the authorization/scope gate (already enforced by `strix/core/safety/scope_validator.py` against an authorized target).
- The DVWA live run is the empirical proof; its numbers (duration, turns, pivots, findings) are recorded in the run artifacts and are not pre-stated here.

---

*Authored for the ai-vapt-full-application branch; implementation staged in the order above, with regression tests written before the code they guard.*
