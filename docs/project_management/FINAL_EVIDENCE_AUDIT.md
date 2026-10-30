# FINAL EVIDENCE AUDIT (PHASE 6 — Independent Final Evidence Review)

**Audit date:** 2026-08-25
**Auditor role:** Independent evidence reviewer (read-mostly; no source changes made)
**Repository state audited:** `git rev-parse HEAD` → `943f8c9dc27c9a561d9a5105073e2f7e7a38a421` (branch `master`)
**Observed-tier implementation commit:** `b7fb86b` ("T-DOCKER Stage B (loopback observed validation)")
**Verification commands run during this audit (all PASS):**

| Check | Command | Result |
|---|---|---|
| HEAD pin | `git rev-parse HEAD` | `943f8c9…` (expected `943f8c9`) ✔ |
| Offline test suite | `python -m pytest tests/ -q` | **39 passed** in ~0.17s ✔ |
| Scenario runner | `python tests/run_tdocker_scenarios.py` | `[S1] OBSERVED_SUCCESS: status=COMPLETED executions=3 poc_runs=1`; `[S2] OBSERVED_FAILURE: status=COMPLETED executions=2 poc_runs=2`; regression gate `PASS (39 passed)` ✔ |
| Safety (fail-closed) | `Executor(mode="real", danger_mode=True).execute(f,"127.0.0.1")` with empty allowlist | outcome = **FAIL_NO_TARGET** ("target not allowlisted") ✔ |
| Safety (default real) | `Executor(mode="real").execute(f,"127.0.0.1")` | outcome = **SKIPPED** ("no exploit was sent") ✔ |

Fresh-run artifacts cited below are from run `data/experiment_runs/20260825T093510Z_tdocker_stageB_loopback/`.

---

## 1. EVIDENCE TAXONOMY

The thesis requires a four-level evidence taxonomy. Levels are cumulative in rigor; each level must be labelled honestly in the thesis.

| Level | Name | Ground truth source | Required for thesis? | Status in this project |
|---|---|---|---|---|
| **LEVEL 1** | SIMULATION | Labels / deterministic ground truth (`data/poc_corpus/labels.json`) | Yes | **ACHIEVED** (benchmark + ablations) |
| **LEVEL 2** | LOOPBACK OBSERVED VALIDATION | Actual local process / runtime observations (real subprocess I/O over TCP, independently corroborated by target-side logs) | Yes | **ACHIEVED** (T-DOCKER Stage B on 127.0.0.1) |
| **LEVEL 3** | CONTAINER-ISOLATED OBSERVED VALIDATION | Actual target + reproducible isolated environment (Docker bridge/internal network) | Optional upgrade — **NOT claimed** | NOT achieved (Docker daemon unavailable; recorded honestly) |
| **LEVEL 4** | BROADER EXTERNAL VALIDATION | Third-party / internet-range targets | No | Out of scope |

### Per-GAP level reached

| GAP | Research question | Highest level achieved | Evidence anchor |
|---|---|---|---|
| GAP-1 (pre-execution usability assessment influences candidate selection) | RQ1 | **Level 2 achieved** (plus Level 1 ablation support) | S1: HIGH-ranked candidate A selected first; module printed `VULNERABLE`; emulator logged `path=/vuln` (`data/experiment_runs/20260825T093510Z_tdocker_stageB_loopback/emulator_access_s1.log`) |
| GAP-2 (explicit attempt tracking + bounded pivot prevents non-productive loops) | RQ2 | **Level 2 achieved** (plus Level 1 benchmark support) | S2: exactly 2 observed failures on `/fail`, pivot logged, no 3rd attempt, status COMPLETED (`emulator_access_s2.log`, `framework_logs_s2.txt`) |
| Benchmark baselines (request economy, loop events) | RQ1/RQ2 quantitative framing | **Level 1 only** (labels/deterministic ground truth) | `docs/project_management/09_BENCHMARK_EVIDENCE.md`:67–70 — SMART 5 requests / 0 loops vs DUMB 21 requests / 2 loops |

> ⚠️ **Standing prohibition:** T-DOCKER Stage B was executed on LOOPBACK (127.0.0.1) because the Docker daemon was unavailable (see `metadata.json` → `infrastructure.container_isolation_in_effect: false`; `infra_docker_unavailable.txt`). It is a **CONTROLLED LOOPBACK OBSERVED VALIDATION (Level 2)**, **NOT** Level 3. The thesis must **NOT** claim Docker/container isolation for these runs. Level 3 remains an optional future upgrade.

---

## 2. CRITICAL QUESTION: did outcomes genuinely come from runtime observations?

> **"Did the framework's decision/outcome genuinely come from runtime observations, or did any hidden fallback still use labels/expected outcomes?"**

### Verdict: **PASS** — outcomes were derived from runtime observations only. `labels.json` is NOT in the danger_mode success path.

### Code evidence

**(a) The harness forces the real, dangerous, allowlisted path** — `tests/run_tdocker_scenarios.py:210-218`: `run_scenario()` patches `core.executor.CORPUS_DIR` to the lab corpus, patches `agent_graph.assess_exploit_quality` (line 211) and `agent_graph.Executor` (lines 212–213) via a factory (`make_allowlisted_executor_factory()`, lines 165–174) that constructs `Executor(mode="real", danger_mode=True, target_allowlist=["127.0.0.1"])`, then calls `agent_graph.run_agent(..., max_attempts=2, mode="real")` (lines 215–218). There is no simulation-mode execution anywhere in the observed runs.

**(b) In danger_mode, the outcome comes from process I/O ONLY** — `core/executor.py:255-264`: the executor shells out to the corpus module (`subprocess.run([...])`, lines 255–259) and sets the outcome exclusively via `_parse_module_output(proc.stdout..., proc.stderr..., proc.returncode)` (lines 260–264). `_parse_module_output` (core/executor.py:140–159) inspects only `stdout`, `stderr`, and `returncode`: non-zero exit or traceback → FAIL_SYNTAX/FAIL_DEPENDENCY; explicit success token in combined output → SUCCESS; clean run without token → FAIL_TIMEOUT. No label file is read anywhere on this path.

**(c) `labels.json` is consulted ONLY in simulation mode** — `core/executor.py:193-198`: the sole call site of `_outcome_from_label` (defined at core/executor.py:129–135) is inside `if self.mode == "simulation":`. The observed runs ran with `mode="real"` (harness line 217), so this branch never executed. **Stated explicitly: `labels.json` is NOT in the danger_mode success path.** The harness metadata records the same fact (`metadata.json` → `observed_vs_simulation.labels_consulted: false`).

**(d) Independent target-side corroboration (not just self-reported module output):**
- S1: emulator access log shows exactly one `path=/vuln` request and an HTTP 200; the recorded module subprocess stdout contains the token `VULNERABLE` (`module_stdout_stderr_s1.txt`). Classification requires BOTH (`classify_s1`, `tests/run_tdocker_scenarios.py:225-235`) — a label value could not fabricate either signal.
- S2: emulator access log shows exactly two `path=/fail` requests and no third request; both module invocations failed to produce a success token; the framework logs contain `[Pivot] Threshold reached for C. Abandoning route.` and `[Pivot] All targets processed. Workflow complete.` (`framework_logs_s2.txt:6-7`). The hard assertions in `assert_s2` (tests/run_tdocker_scenarios.py:261-275) enforce exactly-2 attempts, no SUCCESS, pivot log present, and termination.

### Honest boundary: the ASSESSOR was a deterministic stub — mechanism validated, NOT LLM accuracy

The usability assessment boundary (`agent_graph.assess_exploit_quality`, called at `core/agent_graph.py:74`) was patched to a deterministic offline stub (`tests/run_tdocker_scenarios.py:83-92`) mapping A → HIGH, B → LOW, C → MEDIUM — **not the real LLM assessor**. Consequences, stated plainly for the thesis:

- What IS validated: the full downstream decision/pivot MECHANISM (ranking-driven candidate selection, the LOW-skip gate, attempt counting, pivot-on-failure threshold, clean termination) responded correctly to genuinely OBSERVED outcomes flowing through unmodified `agent_graph` logic.
- What is NOT validated: LLM-assessor accuracy, ranking quality on unseen CVEs, or any claim about how a real model would rank candidates. The stub chose the ranks; the framework merely executed them faithfully against real observations.

No hidden fallback to labels exists in the real-mode path; conversely, the selection *inputs* were stub-determined. Both halves of that sentence belong in the thesis.

---

## 3. CLAIM → EVIDENCE MAP

Verification statuses: **VERIFIED (audited)** = reproduced/read during this Phase 6 audit; **MEASURED (prior task)** = measured in a recorded prior task per governance docs.

| # | Claim | GAP | Evidence file(s) | Verification status | EXACT allowed wording |
|---|---|---|---|---|---|
| C1 | Pre-execution usability assessment influenced candidate selection so an observed success was reached earlier | GAP-1 | `tests/run_tdocker_scenarios.py:83-92,210-218`; `data/experiment_runs/20260825T093510Z_tdocker_stageB_loopback/{module_stdout_stderr_s1.txt, emulator_access_s1.log}` (S1 module printed `VULNERABLE`; emulator logged `path=/vuln`; HIGH-ranked candidate A selected first, success at attempt 1). Corroborating Level 1: `docs/project_management/09_BENCHMARK_EVIDENCE.md`:23–46 (ablation: foothold reached 2 requests sooner with scoring) | VERIFIED (audited; fresh run) | "In the loopback observed validation (Level 2), the HIGH-usability-ranked candidate was selected first and produced an observed success on its first attempt (module token `VULNERABLE` corroborated by the emulator access log). Together with the Level 1 ablation, this demonstrates the routing mechanism; assessor ranks were stubbed." |
| C2 | Explicit attempt tracking + pivot responded to an observed failure and terminated without repeated non-productive loops | GAP-2 | `data/experiment_runs/20260825T093510Z_tdocker_stageB_loopback/{emulator_access_s2.log (exactly 2 × `path=/fail`), framework_logs_s2.txt:6-7 (pivot + completion entries), …_s2_smart.json}`; assertions `tests/run_tdocker_scenarios.py:261-275`; pivot gate `core/agent_graph.py:145` | VERIFIED (audited; fresh run) | "In the observed failure scenario (Level 2), the agent attempted candidate C exactly twice (both failures observed on the emulator log), emitted an explicit pivot entry, and terminated with status COMPLETED — no third attempt occurred within the configured threshold of 2." |
| C3 | Default real mode sends NO exploit payload (SKIPPED); danger_mode is opt-in and fail-closed | Safety | Audit command output (this document header): empty-allowlist danger_mode → `FAIL_NO_TARGET` ("target not allowlisted"); default real → `SKIPPED`. Code: `core/executor.py:220-229` (SKIPPED branch), `core/executor.py:236-245` (fail-closed allowlist gate BEFORE any subprocess), constructor default empty allowlist `core/executor.py:76-80` | VERIFIED (audited; re-executed) | "By default, real mode performs connectivity checks only and reports SKIPPED without sending any exploit payload; exploitation requires opt-in danger_mode, and the fail-closed target allowlist refuses every target unless explicitly authorised." |
| C4 | Request-economy benchmark: SMART 5 requests / 0 loops vs DUMB 21 requests / 2 loops | Benchmark (RQ1/RQ2 framing) | `docs/project_management/09_BENCHMARK_EVIDENCE.md`:64–71 | MEASURED (prior task; Level 1) | "Under deterministic simulation (Level 1), the SMART strategy used 5 requests with 0 loop events versus the DUMB baseline's 21 requests with 2 loop events." Must be labelled **simulation**. |
| C5 | T-DOCKER Stage B infrastructure tier | Infrastructure scope | `data/experiment_runs/*/metadata.json` (`infrastructure.mode = "loopback process (DEVIATION)"`, `container_isolation_in_effect: false`); `infra_docker_unavailable.txt`; harness docstring `tests/run_tdocker_scenarios.py:7-16` | VERIFIED (audited) | See recommended wording below (§ "Recommended loopback wording"). |

### Claims explicitly NOT supported by current evidence (must not appear in the thesis)

| Unsupported claim | Why not |
|---|---|
| Universal loop prevention across arbitrary workloads | Demonstrated for n=2 designed scenarios plus a Level 1 structural argument; no general proof or diverse workload sweep. |
| Real-world superiority (production targets/CVEs) | Targets were a purpose-built lab emulator; candidates A/B/C are behavioural stubs, not real CVE exploits. |
| Faster execution than alternatives | Measured time_saved_s is NEGATIVE (LLM latency dominates) — `09_BENCHMARK_EVIDENCE.md`:13–14,78. Never claim speed wins. |
| Universal exploit prediction / LLM-assessor efficacy on unseen CVEs | Assessor was a deterministic stub in the observed tier; accuracy of the real LLM assessor is unvalidated (§2 boundary, §4). |
| Docker/container isolation for Stage B runs | Docker daemon unavailable; loopback-only bind; `container_isolation_in_effect: false`. Level 3 claim prohibited (§1 warning). |

---

## 4. LIMITATIONS (draft for thesis "Limitations" section)

1. **Loopback, not container-isolated.** Stage B ran the emulator as a local process bound to 127.0.0.1:18080 because the Docker daemon was unavailable. Loopback binding plus the fail-closed allowlist were the only boundaries; there was no container/bridge-network isolation or egress control. The experiment therefore establishes Level 2, not Level 3.
2. **Stubbed assessor (mechanism-only).** Usability ranks in the observed tier were supplied by a deterministic offline stub (A→HIGH, B→LOW, C→MEDIUM), not the production LLM assessor. Results validate the decision/pivot mechanism under observed outcomes, not LLM judgement quality.
3. **Small scenario count (n=2).** Exactly one observed-success scenario (S1) and one observed-failure/pivot scenario (S2) constitute the observed tier. No statistical generality is implied.
4. **Behavioural-stub corpus.** Lab candidates A/B/C and the emulator endpoints are minimal behavioural emulators (e.g., module A prints `VULNERABLE` when the emulator's `/vuln` returns HTTP 200), not faithful reproductions of real CVEs; exploit-chain realism is low.
5. **Single-run observed tier.** Each observed scenario was executed once (deterministic harness, fixed seed-free inputs). No multi-seed/multi-run variance analysis exists for the observed tier; multi-seed variance exists only as a planned gate (T-BENCH-VAR) and is likewise absent.
6. **Unvalidated LLM-assessor accuracy on unseen CVEs.** Because the real assessor never participated in the observed runs, no statement can be made about ranking quality, false-positive rates, or calibration on novel vulnerabilities.

---

## 5. REPRODUCIBILITY

| Dimension | Status | Evidence |
|---|---|---|
| Dependency pins | All runtime dependencies pinned with `==` in `requirements.txt` (13 pinned entries; header documents T-REQPIN intent and the exact reinstall command) | `requirements.txt` |
| Python version | Python 3.10 venv (audit environment: Python 3.10.12) | `venv/`; audit header above |
| Offline test suite | `python -m pytest tests/ -q` → **39 passed**, fully offline (no network/LLM required) | Audit header; also embedded in each run's `regression_gate_pytest.txt` |
| Scenario runner re-runnable | `python tests/run_tdocker_scenarios.py [--run-id ID]` rebuilds the emulator, reruns S1/S2 with hard protocol assertions, and regenerates all artifacts + regression gate | Re-executed during this audit (fresh run `20260825T093510Z_tdocker_stageB_loopback` reproduced S1 `OBSERVED_SUCCESS` / S2 `OBSERVED_FAILURE+pivot`) |
| Raw artifacts policy | Raw run directories under `data/experiment_runs/` are gitignored (`.gitignore:13`); durable evidence retained via `metadata.json` fields, governance docs (`09_BENCHMARK_EVIDENCE.md`, `11_VERIFICATION_LOG.md`), and this audit | `.gitignore`; run tree listing |

Reproduction recipe (one line):
`source venv/bin/activate && pip install -r requirements.txt && python -m pytest tests/ -q && python tests/run_tdocker_scenarios.py`

---

## Auditor's bottom line

- **Critical question:** **PASS** — every reported observed-tier outcome traces to `proc.stdout/stderr/returncode` via `core/executor.py:_parse_module_output` (danger path, lines 255–264), with `labels.json` confined to the `mode=="simulation"` branch (lines 193–194) and independently corroborated by emulator-side access logs. Selection *inputs* were stub-provided; say so.
- **Recommended exact wording for the loopback claim:**
  > "T-DOCKER Stage B constitutes a controlled loopback observed validation (Level 2): exploit modules executed as real subprocesses against a live emulator bound strictly to 127.0.0.1, and all outcomes were parsed from actual module output and independently corroborated by the emulator's access log — not from ground-truth labels. Container-level isolation was not in effect (Docker daemon unavailable), so no Docker/container-sandboxing claim is made; a container-isolated (Level 3) repetition remains optional future work."

*End of audit. No source files modified; no commits made.*
