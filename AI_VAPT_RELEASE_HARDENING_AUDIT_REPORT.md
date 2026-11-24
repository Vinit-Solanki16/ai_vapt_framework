# AI-VAPT — Release Hardening and Independent Engineering Audit

**Repository:** `/home/vinit/AI_VAPT/ai_vapt_framework`
**Branch:** `ai-vapt-full-application` (never switched)
**Checkpoint preserved:** `f4a21079bec1ff0047e438ba2872b28dc486b73e`
**Audit date:** 2026-11-18
**All changes remain uncommitted. No release commit or push was created.**

---

## 1. Independent audit findings (evidence, not report claims)

### 1.1 Positive finding verification and evidence integrity — VERIFIED

- `strix_runs/run-5b97bb90/run.json`: `status=completed`, `process_exit_code=2`,
  29/40 turns, `findings_verified=1`, `execution_evidence={llm_calls:29, security_tool_calls:24}`.
- Engine `vulnerabilities.json`: `vuln-0001`, `verification_state=verified`, confidence `high`,
  all five contract fields populated; `findings.sarif` has one CWE-89 `error` result.
- Independently recomputed `sha256(vuln-0001_evidence.txt)` =
  `191f9ef0e32662ad35c9fc3d01c4a13aef22e77bee52b37a3b66c9c404b7b411`, identical to
  `vuln-0001_meta.json` and the JSON report; `evidence_intact=true`.
- Raw `.state/agents.db` tool history shows real tool calls and outputs: baseline
  `Invalid email or password.` / `401`, then injection
  `{"email":"test@example.com' OR 1=1--","password":"anything"}` → `Status: 200` and a
  JWT containing `admin@juice-sh.op`. No simulated or scripted finding was found.

**Nuance (not a blocker):** the persisted `verification_response` and evidence file are
the narrative line "HTTP 200 with JWT token for admin user"; the raw JWT response survives
only in the agent tool history. The verification contract (`strix/report/verification.py:104-124`)
checks non-empty fields, so this passes, but the artifact is weaker than a raw HTTP capture.

### 1.2 Finding synchronisation and exports — VERIFIED with two defects found

Primary sync path is correct (`strix/interface/api.py:5299-5312` carries the engine state into
`evaluate_finding_verification`). However:

- The PDF generator counted **all** findings as "confirmed" and showed no verification state
  (`strix/interface/viewer/report_pdf.py:803,626,592-596`). An unconfirmed finding would be
  mislabelled in PDF while HTML/Markdown show UNCONFIRMED. **Fixed.**
- SARIF properties omitted `verification_state`/`verified`
  (`strix/report/sarif.py:536-554`), and the SARIF-fallback harvest called the gate without
  that field (`strix/interface/api.py:5388`), silently downgrading a verified finding on
  recovery. **Fixed.**

No duplicate findings: one filing call, one SARIF finding, one dashboard finding, dedup by
`(title, location, parameter)` at `api.py:5212-5219` and in `strix/report/reconciliation.py`.

### 1.3 GAP-1 ranking/dispatch and GAP-2 linkage — VERIFIED with one correction

- Prepared probes are recorded as `preparatory` evidence and no longer consume agent attempts
  (`strix/core/gap_run.py:288-312`; `strix/core/runner.py:423-522`); alternatives remain eligible.
- `run-e48f1b82`: raw tool history shows two real failed probes of `/exec/`, an engine
  `REDIRECT` decision `firewall-blocked-rce → waf-drop-sqli` (10:10:59), a real `exec_command`
  investigation of `/sqli/`, and `record_probe_outcome(..., pivot_executed=True)` at 10:11:38
  linked to the original decision. One genuine pivot, dashboard count 1. Confirmed.
- **Correction to the prior report:** the claimed "two-pivot chain" in `run-153cd2dc` is not
  fully genuine. The second redirect (`waf-drop-sqli → phpinfo-disclosure`) came from a
  `record_coverage` call whose "evidence" was narrated by the model; raw history shows no
  tool execution against `/phpinfo.php` after that decision. The final bridge gate now
  correctly excludes it; only the first pivot in that run is backed by real execution.

### 1.4 Pivot counting, exhaustion, eligibility — VERIFIED with defects found

Native `GapRun.pivot_count()` still counted self-pivots and preparatory probes as execution
(`strix/core/gap_run.py:441-460`), and a same-call `pivot_executed=True` fallback decision was
never marked executed (`gap_run.py:425-426`). The prep loop also silently performed only one
bounded probe per candidate because it checked `cand.attempts` after preparatory probes had
stopped incrementing it (`strix/core/runner.py:663-669`). All **fixed**.

Coverage-only alternatives are deliberately **not** counted as executed pivots: adding them
would let a narrated `record_coverage` row fabricate a pivot. A regression test now pins this.

### 1.5 Run lifecycle and truthful terminal states — VERIFIED with defect found

Failed/timed-out/interrupted engine states cannot be relabelled completed even when a report
was harvested (`api.py:658-667,5119-5131,5576-5625`). However a stale **in-memory** `running`
record was never quarantined by `get_run_status` (`api.py:907-908,6790-6801`), so a dead worker
could leave the dashboard showing an active run. **Fixed.**

### 1.6 Provider selection and credential handling — VERIFIED with critical defect found

`create_run`/`resume_run` keep per-request credentials in memory, but the **engine subprocess**
bootstrap calls `persist_current()` (`strix/interface/main.py:412`), which merged the runtime
key and base URL into `~/.strix/cli-config.json`. This was reproduced live: the operator
profile was overwritten with a temporary tunnel URL during a clean-environment run. **Fixed**
with `STRIX_NO_PERSIST_CONFIG=1` in the worker's subprocess environment and an early return
in `strix/config/loader.py:64-76`. A Web Console run with the fix left the profile hash
unchanged. Separately, the full test suite itself wrote to the real profile through
`/settings/llm` tests; session-level test isolation was added in `tests/conftest.py`.

The README claim that Web Console keys are "never written to disk" was inaccurate for keys
saved via Settings (an intentional persisted save); the README is now precise.

### 1.7 Docker sandbox lifecycle — VERIFIED limitation

Engine `finally` cleanup covers normal, error, cancellation and `BaseException` paths
(`strix/core/runner.py:1352-1375`), but cleanup is explicitly best-effort
(`strix/runtime/session_manager.py:465-493`) and SIGKILL fallbacks / abrupt host death bypass
it (`api.py:4950-4952,4970-4972,4981-4983,6728-6731`). Container orphaning is possible; no
auto-remove backstop exists. Not changed (would be a new feature).

### 1.8 Report exports and lint/static baseline

`make check-all` fails at `ruff format --check` on 21 files; three of those
(`runner.py`, `api.py`, `report_pdf.py`) were already non-compliant at the checkpoint and were
left as pre-existing debt. Mypy reports 5 pre-existing errors (same count and files in a clean
checkout of the checkpoint). Bandit passes. Ruff lint on all changed files passes.

---

## 2. Verified defects and fixes (minimal, evidence-driven)

| # | Defect | Fix | Regression test |
|---|---|---|---|
| 1 | Engine CLI persisted per-request key/base URL to the operator profile | `STRIX_NO_PERSIST_CONFIG` guard in `strix/config/loader.py`; worker sets it in subprocess env | `test_runtime_env_is_not_persisted_for_engine_subprocess`; live run hash check |
| 2 | Late-stage model-only hang immune to stall detector after 3 productive tools | `api.should_stop_for_stall()` used alongside the unchanged legacy helper | `test_stall_is_detected_after_three_productive_tools` |
| 3 | Native pivot count included self-pivots and preparatory probes | exclusions in `GapRun.pivot_count()` | `test_native_pivot_count_excludes_self_pivots_and_preparatory_probes` |
| 4 | Same-call pivot execution never marked as executed | `GapRun.link_pivot_execution()` fallback annotates the decision | `test_same_call_pivot_execution_is_persisted_as_linked` |
| 5 | Prep loop probed each candidate only once | removed redundant `cand.attempts` break | `test_preparatory_loop_is_not_cut_after_one_probe` |
| 6 | SARIF dropped verification state and re-import downgraded verified findings | `strix/report/sarif.py` keys + `api.py` fallback | `test_sarif_result_preserves_verification_state` |
| 7 | PDF presented unconfirmed findings as confirmed | verified count + verification badge | `test_pdf_does_not_present_unconfirmed_as_confirmed` |
| 8 | Stale in-memory `running` run shown as active | quarantine in `get_run_status` | `test_in_memory_stale_running_run_is_not_reported_as_running` |
| 9 | Engine/control GAP stores diverged on attempts/status | post-run `reconcile_control_gap_state()` | `test_control_gap_state_is_reconciled_with_engine` |
| 10 | Tests overwrote the real AI provider profile | session-level CLI-config isolation + per-test redirects | full-suite before/after profile hash check |
| 11 | `ruff` SIM103 on `_is_productive_tool` | inlined negated condition | ruff check |

All new tests are in `tests/test_release_hardening.py` plus two isolation edits in existing
tests. No existing test was weakened, deleted, timeouts relaxed, or made to accept a false
success.

---

## 3. Remaining reliability limitations

1. `should_stop_for_no_progress` keeps its legacy `>=3 productive tools` guard (an existing
   regression test pins it). The new `should_stop_for_stall()` closes the late-stage hang, but
   an engine that emits a tool just under the 600 s threshold can still extend a run.
2. The 600 s stream total timeout and SDK replay remain bounded by 5 retries and the wall-clock
   limit (`strix/core/execution.py:165,910-926`); non-streaming mode remains a process-level
   operator choice, not a persisted profile setting.
3. A failed/timed-out run can harvest findings; they are labelled partial/failed, never clean.
   Historical pre-fix artifacts were not rewritten.
4. Docker sandbox cleanup is best-effort; orphan containers need manual reaping after SIGKILL
   or host death.
5. Coverage-only "pivots" are intentionally not counted; if the operator expects them to count,
   the alternative must be executed with a real tool and recorded via `record_probe_outcome`.
6. `scripts/install.sh` installs upstream Strix, not this framework; it must be excluded from
   the release or renamed.
7. Per-request `api_base` is honoured for custom/OpenAI/Ollama but ignored for OpenRouter,
   Anthropic and Google provider branches (`api.py` worker env setup) — not patched here
   because it is outside the validated path and needs provider-specific env-name verification.
8. Unresolved static-check debt: 5 mypy errors and 3 pre-existing ruff-format files.

---

## 4. Final test and static-check results

- Focused hardening/verification/GAP suites: **81 passed** (1 deprecation warning).
- **Final full suite: 2972 passed, 1 skipped, 3 xfailed, 108 warnings in 387.65 s** —
  `/tmp/opencode/full_suite_definitive_release.log` (up from 2962 at the start of this audit).
  The real CLI profile was restored to its exact pre-audit byte content (SHA-256
  `0bd7617090a80c9f4658dba5fcf48de4b49d7db58cbd30a1b1fc83cce11fca40`) and remained
  unchanged throughout the isolated final suite.
- `ruff check` on all changed files: clean.
- `ruff format --check .`: fails on 21 files; 3 pre-existing among changed files.
- `mypy strix/`: 5 pre-existing errors in 2 files (identical in clean checkpoint worktree).
- `bandit -r strix/ -c pyproject.toml`: pass.
- `py_compile` on changed modules: pass.

---

## 5. Clean-environment installation audit

An isolated worktree was created at the recovery checkpoint with the uncommitted patch applied
(`/tmp/opencode/ai_vapt_clean_audit`); the development tree was untouched.

| Check | Result |
|---|---|
| `uv sync --frozen` | success (resolved Python 3.14.7; lock honoured) |
| CLI + FastAPI import | success |
| `uvicorn strix.interface.api:app` on port 8011 | health 200 |
| Web Console root + `js/app.js` | 200 / 200 (prebuilt assets, no frontend build needed) |
| Docker daemon | 29.9.2 available |
| Runtime provider config | per-request `assessor_provider=custom`, model alias `kaggle-model`, key/base in memory only |
| Authorized Juice Shop assessment | `run-6cbb049d` → `completed`, exit 2, 23 turns, 1 verified SQLi finding, `finish_scan` |
| Report generation | JSON/SARIF/Markdown/HTML/CSV/PDF all HTTP 200, one verified finding |
| Persistent profile | initially written by engine bootstrap (defect); after fix, unchanged during the validation run |

No tunnel URL, key, or endpoint was added to source, docs, defaults, or committed files.

---

## 6. Proposed professional release inventory

**Keep (runtime/core):** `pyproject.toml`, `uv.lock`, `Makefile`, `strix/` (including committed
prebuilt `strix/interface/web/index.html`, `web/js/app.js`, `viewer/static`), `ai-vapt.sh`,
`setup.sh`, `juice-shop.sh`, `start.sh`, `stop.sh`, `.env.example`, `README.md`, `CHANGELOG.md`,
`CONTRIBUTING.md`, `AGENTS.md`, `LICENSE` (Apache-2.0), and only the scripts actually referenced
by launch/setup.

**Configuration examples:** provider/base URL examples with placeholder values only; document
that Settings saves credentials to `~/.strix/cli-config.json` (0600) while per-run credentials
stay in memory. No real keys or tunnel URLs.

**Validation evidence to ship (curated):** a short release-validation note and the focused test
results; keep raw run artifacts, internal reports, and scratch data out.

**Exclude from the professional distribution:** 74 tracked `AI_VAPT_*.md` internal reports,
`headless_qa_results/` (11 tracked files; contains a hardcoded ngrok endpoint and test key),
`benchmark_results/` (19 tracked files; same leaked endpoint), `docs/research/` (44 tracked),
`docs/ai_vapt_integration/` (4 tracked), `.env`, `~/.strix/cli-config.json`, `strix_runs/`,
`strix_runs_main/`, `agent_runs/`, `.run/`, `.ai_vapt.pid`, `.ai-vapt.pid`, `ai_vapt_server.log`,
`logs/`, `.venv/`, caches, `__pycache__/`, and misleading dev-only `scripts/install.sh`.
Add these directories to `.gitignore` in the release branch; do not delete them from the
research branch.

**License/attribution:** Apache-2.0 `LICENSE`; preserve upstream Strix attribution and
Juice Shop (MIT) notices in container/demo documentation; third-party licenses come from
`uv.lock` dependencies.

**Release mechanics (proposed, not executed):** create a fresh worktree from the release
baseline, copy only the curated inventory, run `uv sync --frozen`, focused tests, clean-install
smoke test, then review before any commit. No release commit/push without explicit approval.

---

## 7. Risks and unresolved issues

- The original `~/.strix/cli-config.json` key was a 22-character test dummy (`sk-cus…`); it was
  restored byte-for-byte to the pre-audit hash `0bd761…` and verified stable after the final
  isolated suite. The operator should still confirm the profile before release.
- Profile-writing tests are now isolated; if a new test adds a settings endpoint call it must
  patch `CLI_CONFIG_FILE` or it will again touch the developer profile.
- Coverage-only pivot semantics may surprise operators; document explicitly.
- Orphan Docker containers after abnormal termination are possible.
- Provider-specific `api_base` handling for OpenRouter/Anthropic/Google is unresolved.
- Static-check debt (format/mypy) is pre-existing but will fail a strict `make check-all` gate.
- The operator-supplied model endpoint is temporary; no run is reproducible without an
  equivalent OpenAI-compatible endpoint configured through the supported runtime mechanism.

---

## 8. Recommendation

**Ready for release preparation, conditional.** The delivered implementation is functionally
validated: clean positive run, verified finding, genuine executed pivot, cross-format
consistency, clean-environment install and assessment all pass. The audited defects are fixed
with deterministic regressions. Before publishing a professional release, complete the four
release-blocker chores: (1) curate the tracked file inventory and add `.gitignore` exclusions,
(2) fix or explicitly waive the pre-existing format/mypy debt so `make check-all` is green,
(3) decide and document coverage-only pivot semantics and provider-specific `api_base`
support, and (4) add a Docker container reaper/backstop. Do not create a release commit or push
until those items and a final operator review are complete.
