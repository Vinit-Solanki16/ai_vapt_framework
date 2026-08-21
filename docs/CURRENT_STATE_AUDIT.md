# CURRENT STATE AUDIT — Autonomous AI VAPT Framework

**Date of audit:** 2026-08-21 (post-checkpoint)
**Mode:** READ-ONLY audit. No source modified.
**Method:** Full source read of every `core/` module + `app.py` + `tests/evaluate.py` +
`data/*` + `tasks/*` + `README.md` + `checkpoint_20260821.md`, plus live
non-destructive execution of each pipeline stage.
**Environment verified:** Python 3.10.12, `venv` active, Ollama `llama3.2:3b` UP
(live), Docker DOWN, EPSS live API reachable, no `.git` repo present.

---

## 1. Classification Summary (at a glance)

| # | Component | Classification |
|---|-----------|----------------|
| 1 | Repository structure | WORKING (not a git repo — reproducibility gap) |
| 2 | scanner.py / scan ingestion | WORKING AND VERIFIED |
| 3 | Finding / data models (schemas.py) | WORKING AND VERIFIED |
| 4 | exploit_assessor.py | WORKING AND VERIFIED (Ollama); GitHub+OpenAI paths UNVERIFIED |
| 5 | PoC corpus + labels.json | WORKING AND VERIFIED |
| 6 | LLM provider integration | PARTIAL (Ollama verified; OpenAI untested) |
| 7 | Ollama integration | WORKING AND VERIFIED |
| 8 | OpenAI / provider abstraction | IMPLEMENTED BUT NOT VERIFIED |
| 9 | executor.py | WORKING — simulation VERIFIED; real mode PARTIAL (honesty gap) |
| 10 | agent_graph.py / LangGraph | WORKING AND VERIFIED end-to-end |
| 11 | retry + pivot logic | WORKING AND VERIFIED |
| 12 | loop detection / prevention | WORKING (by construction; verified by run) |
| 13 | simulation vs real mode | simulation VERIFIED; real PARTIAL |
| 14 | report generation | WORKING AND VERIFIED |
| 15 | Streamlit UI | IMPLEMENTED BUT NOT VERIFIED (headless; import clean) |
| 16 | tests | PARTIAL — smoke script only, NO pytest, NO assertions |
| 17 | evaluate.py benchmark | WORKING (runs) but metric gaps |
| 18 | SMART vs DUMB baseline | WORKING (DUMB real; SMART loop metric asserted) |
| 19 | checkpoint / cron system | MISSING (no code; only a static markdown note) |
| 20 | config / paths / secrets / reproducibility | PARTIAL (no config file; no git; no secrets leaked) |

---

## 2. Per-Component Detail

### 1. Repository structure
- **Files:** `core/` (schemas, scanner, poc_corpus, exploit_assessor, executor,
  agent_graph, report, `__init__`), `app.py`, `tests/evaluate.py`, `data/`
  (sample_scan.json, live_scan.xml, poc_corpus/*.py + labels.json, reports/*,
  benchmark_results.csv, checkpoints/*.md), `tasks/task1..5.md`, `requirements.txt`,
  `README.md`.
- **Observation:** `python -c "import core"` → OK (25 exported symbols).
  `core/__init__.py` re-exports everything cleanly.
- **GAP:** `git status` → *fatal: not a git repository*. No version control →
  weak reproducibility story for a thesis. No `conftest.py`, no `pytest.ini`, no
  `Dockerfile`, no `.github/`, no `.env`, no `config.*`.
- **Classification:** WORKING (but no VCS).

### 2. scanner.py / scan ingestion
- **Inputs:** Nmap XML (`-oX`), Nmap JSON (`-oJ`), or custom JSON (`findings` key).
- **Outputs:** `List[Finding]` sorted by EPSS descending.
- **Verified live:**
  - `python -m core.scanner data/sample_scan.json` → 2 findings ranked
    (CVE-2021-44228 EPSS 1.0000, CVE-2023-38408 EPSS 0.7970).
  - `python -m core.scanner data/live_scan.xml` → 1 finding, port 80 (UNKNOWN-CVE,
    EPSS 0.0 because Nmap XML carries no CVE).
  - `fetch_epss_score('CVE-2021-44228')` → `0.99999` (LIVE FIRST.org API, verified).
- **Real signal:** YES (EPSS is a live network call, offline-safe fallback 0.0).
- **Hardcoded/mock:** None. EPSS failure path returns 0.0 and only prints.
- **Dead code:** None material.
- **Security:** No credential handling. Fine.
- **Classification:** WORKING AND VERIFIED.

### 3. Finding / data models (schemas.py)
- **Real fix vs prototype:** `usability_rank` is now `UsabilityRank(str, Enum)`
  (was loose `str` that admitted `"")` garbage). `ExecutionOutcome` enum replaces
  the old hardcoded `execution_success=False`.
- **`priority_score()`** = `round(epss * (0.5 + 0.5*u), 4)` where u∈{HIGH:1,
  MEDIUM:0.6, LOW:0.3}. Verified by reasoning + used by ranking.
- **`finding_from_dict` / `findings_from_state`**: rebuild Finding objects from
  dicts (supports persistence/Streamlit round-trip).
- **Classification:** WORKING AND VERIFIED.

### 4. exploit_assessor.py
- **Inputs:** CVE id; resolves code via `code_sample` → `corpus_lookup` →
  `fetch_github_poc` → fallback placeholder string.
- **Outputs:** `ExploitAssessment` (enum-constrained Pydantic).
- **Verified live (real Ollama):** `python -m core.exploit_assessor CVE-2021-44228`
  returned a fully populated, schema-valid assessment (exploit_found, syntax_valid,
  privileges_required, network_noise, complexity_score, prerequisites_met,
  usability_rank, reasoning). No `"`}"` garbage. Cross-checks corpus label
  (appends `[corpus-label=HIGH]` to reasoning).
- **GitHub path:** `fetch_github_poc` only runs if `GITHUB_TOKEN` set; returns None
  otherwise. **NOT verified** (no token in env).
- **OpenAI path:** `get_llm("openai")` builds `ChatOpenAI`; **NOT verified** (no key).
  Falls back to `"dummy-key"` if unset → would 401 at call time.
- **Mock/stub:** None. Scores REAL corpus text.
- **Classification:** WORKING AND VERIFIED (Ollama); GitHub+OpenAI UNVERIFIED.

### 5. PoC corpus + labels.json
- **Files:** `CVE-2021-44228.py` (real socket JNDI send), `CVE-2023-38408.py`
  (raises `NotImplementedError`, needs `paramiko`), `CVE-2022-22965.py`
  (`print("placeholder; malformed payload")` — intentionally malformed).
- **labels.json:** 3 entries mapping CVE → `{reliability, outcome, requests, source}`.
  Consistent with corpus and with executor resolution.
- **Verified:** `corpus_lookup` / `corpus_label` read files + labels; executor
  resolves outcome from these labels (see §9).
- **Note:** corpus is the SIMULATION ground truth; the 3 PoCs are heterogeneous
  (one real, one stub, one malformed) — fine for a behavioural benchmark but small
  (n=3) for thesis defense.
- **Classification:** WORKING AND VERIFIED.

### 6. LLM provider integration
- `get_llm(provider, model_name, api_key)` → `ChatOllama` or `ChatOpenAI`.
- Ollama VERIFIED. OpenAI UNVERIFIED (no key).
- `with_structured_output(ExploitAssessment)` confirmed working on Ollama.
- **Classification:** PARTIAL.

### 7. Ollama integration
- `ChatOllama(model="llama3.2:3b", temperature=0.1)`. Service confirmed UP,
  model present, structured output returns valid enum-constrained assessment.
- **Classification:** WORKING AND VERIFIED.

### 8. OpenAI / provider abstraction
- Code present and wired into `get_llm` + `app.py` sidebar. No secret stored to
  disk (key taken from env / Streamlit password field, set into `os.environ`).
- **UNVERIFIED** — would need a live key. Default `"dummy-key"` is a latent footgun
  (silent 401 rather than a clear error if user toggles OpenAI without a key).
- **Classification:** IMPLEMENTED BUT NOT VERIFIED.

### 9. executor.py
- **Two modes:**
  - **simulation (default):** `_outcome_from_label(cve)` → `ExecutionOutcome` from
    labels.json. `request_count=1` per call. **VERIFIED:** emitted
    SUCCESS / FAIL_TIMEOUT / FAIL_SYNTAX exactly matching labels.
  - **real:** does a genuine `socket.create_connection` probe (counted as 1 request).
    Safety gate: LOW-usability → SKIPPED. Unreachable → FAIL_NO_TARGET. If corpus
    `.py` module exists, shells it out via `subprocess.run(["python", module, host,
    port])` (captured, result DISCARDED), then STILL resolves success from the label.
- **Verified real-mode behaviours:** LOW→SKIPPED, unreachable→FAIL_NO_TARGET.
- **HONESTY / SAFETY GAP (important):** docstring claims real mode is a "genuine,
  safe connectivity probe", but for CVE-2021-44228 the corpus module actually
  `sendall`s a JNDI payload to `target:port` — i.e. real mode CAN fire an offensive
  socket send, while its *result* is ignored and success is still trusted from the
  label. So "real mode" neither validates nor is purely passive. This must be
  reconciled before any demo against a non-sandboxed target.
- **No weaponized payloads shipped** — by design. Live success determination against
  a real vulnerable service is therefore impossible today.
- **Classification:** WORKING — simulation VERIFIED; real PARTIAL (honesty gap).

### 10. agent_graph.py / LangGraph state machine
- **Nodes:** `assess_node` (calls assessor BEFORE execution — addresses GAP-1),
  `execute_node` (calls Executor, increments `attempt_count`), `pivot_node`
  (advance on SUCCESS, abandon on threshold, reset counter, COMPLETE at end).
- **Edges:** `assess→execute`; `execute→{execute|pivot|END}` via `evaluate_decision`;
  `pivot→{assess|END}`.
- **Verified live (real Ollama, simulation mode):** full run produced a terminating
  log — CVE-2021-44228 SUCCESS then advance, CVE-2023-38408 2×FAIL_TIMEOUT then pivot,
  COMPLETED. No out-of-range index.
- **Upstream/downstream:** consumes `scanner` findings + `exploit_assessor` +
  `executor`; produces `AgentState` consumed by `report` + `app`.
- **Classification:** WORKING AND VERIFIED.

### 11. retry + pivot logic
- `evaluate_decision`: SUCCESS→pivot; `attempt_count >= max_attempts`→pivot;
  else→execute. `attempt_count` incremented only in `execute_node`. Threshold
  demonstrated (max_attempts=2 → exactly 2 attempts then pivot).
- **Classification:** WORKING AND VERIFIED.

### 12. loop detection / prevention
- No explicit "loop counter" — prevention is structural: once `attempt_count`
  reaches `max_attempts` the router forces `pivot`, and `pivot_node` either advances
  or sets COMPLETED→END. Verified non-terminating by both reading and running.
- **Caveat:** benchmark *asserts* SMART loops=0 (see §17) rather than instrumenting
  it; structurally correct but not measured.
- **Classification:** WORKING (by construction).

### 13. simulation vs real mode
- simulation: VERIFIED, reproducible, label-driven.
- real: PARTIAL — connectivity probe verified; corpus shell-out unmeasured; no live
  validation.
- **Classification:** simulation VERIFIED; real PARTIAL.

### 14. report generation
- `build_report` → dict (summary, validated, rejected, remediation, execution_log).
- `save_json` / `save_pdf` (reportlab) VERIFIED by writing to `/tmp` (JSON 626 B,
  PDF 2148 B, both valid). Repo reports dir already has a sample run.
- **Derived (not measured) metric:** `wasted_attempts_avoided = len(rejected)*threshold`
  is illustrative, not observed. Document as such.
- **Classification:** WORKING AND VERIFIED.

### 15. Streamlit UI (app.py)
- Sidebar (provider radio, OpenAI key, threshold slider, mode radio), Tab1 (uploader
  → dataframe), Tab2 (run agent → live log feed + outcomes + JSON/PDF downloads).
- Import is clean; checkpoint noted scan preview works. Full interactive UI NOT run
  in this headless audit. Logic is straightforward and reuses verified modules.
- **Classification:** IMPLEMENTED BUT NOT VERIFIED.

### 16. tests
- **No `pytest` suite, no `conftest.py`, zero `assert` statements anywhere in repo.**
- Only "test" artifact is `tests/evaluate.py` (a smoke script that runs both agents,
  prints a table, writes a CSV). It exercises the pipeline end-to-end but verifies
  nothing programmatically.
- **Classification:** PARTIAL — smoke script only; no real tests.

### 17. evaluate.py benchmark
- `smart_agent` (full graph, threshold=2) vs `dumb_agent` (blind retry to hard_cap=10).
- **Verified live:** ran to completion; CSV written:
  SMART 8.546s / 5 req / 1 validated / 33.3% / 0 loops;
  DUMB 0.0s / 21 req / 1 validated / 33.3% / 2 loops.
- **Gaps:**
  - `smart_loop = 0` is **hardcoded**, not measured (loops_avoided = 2-0 = 2 is
    asserted, not instrumented).
  - Single run, no variance / multi-seed.
  - n=3 labelled findings; only 1 exploitable path → weak statistical basis.
  - `time_saved_s` is NEGATIVE (-8.5s): SMART is slower wall-clock due to Ollama
    latency. The win is request + loop efficiency, not speed — must be framed
    explicitly (checkpoint already notes this).
- **Doc inconsistency:** `README.md` benchmark table says SMART=1 request; actual
  CSV says 5. README is stale.
- **Classification:** WORKING (runs) but metric gaps.

### 18. SMART vs DUMB baseline
- DUMB metric is genuine (21 req, 2 loop events from 10× retries on 2 broken CVEs).
- SMART loop metric asserted (see §17).
- The core thesis signal — fewer requests via early pivot — is REAL and reproducible
  (5 vs 21).
- **Classification:** WORKING.

### 19. checkpoint / cron system
- **MISSING as code.** No scheduler, no persistence of `AgentState` between runs.
  `agent_graph.run_agent` returns an in-memory dict; nothing is written to a
  checkpoint store except the human-authored `checkpoint_20260821.md`.
- Implication: no resume, no run history, no cron-driven re-scans.
- **Classification:** MISSING.

### 20. configuration / paths / secrets / reproducibility
- No config file; paths are repo-relative (`core/../data/...`); works when cwd =
  repo root (all CLIs assume this).
- No secrets in repo (good). `GITHUB_TOKEN` / `OPENAI_API_KEY` via env only.
- App writes OpenAI key into `os.environ` at runtime (not persisted) — acceptable.
- **No `.git`** → reproducibility/version-control gap.
- **Classification:** PARTIAL.

---

## 3. Real Data-Flow Verification (traced + executed)

```
scan input (sample_scan.json / live_scan.xml)
  → scanner.process_scan  [VERIFIED: parses, ranks by EPSS]
  → Finding objects (EPSS live from FIRST.org)  [VERIFIED: 0.99999]
  → rank_findings by priority_score  [VERIFIED: EPSS×usability]
  → assess_node → exploit_assessor.assess_exploit_quality
        [VERIFIED via real Ollama: enum-constrained ExploitAssessment]
  → usability_rank attached to Finding
  → execute_node → executor.execute(finding, target)
        [VERIFIED: simulation resolves from labels.json;
         real does socket probe + shells corpus module]
  → ExecutionResult (outcome, request_count)  [REAL signal, not hardcoded]
  → AgentState update (attempt_count++, status)
  → evaluate_decision: SUCCESS→pivot | attempt≥N→pivot | else execute
        [VERIFIED: terminates, no loop]
  → pivot_node: advance / abandon / COMPLETE  [VERIFIED]
  → next candidate or COMPLETED
  → report.build_report → JSON + PDF  [VERIFIED]
  → app.py dashboard (live feed + downloads)  [IMPORTED; not interactively run]
  → evaluate.py SMART vs DUMB → CSV  [VERIFIED run; loop metric asserted]
```

The exploit-quality gap (GAP-1) and pivot/loop gap (GAP-2) are both genuinely
implemented and exercised by real signals. The remaining risk is in *validation
fidelity* (no live exploitation) and *evidence rigor* (asserted loop metric, no
pytest, n=3).

---

## 4. Security Notes
- S1 (Medium): `executor` real mode shells corpus `.py` modules that may perform
  real offensive network sends (CVE-2021-44228 sends a JNDI payload) while ignoring
  their result and trusting the label. Mislabeled as "safe probe". Gate behind
  explicit opt-in + document, or make real mode connectivity-only.
- S2 (Low): `get_llm` OpenAI default `"dummy-key"` → silent 401 instead of clear error.
- S3 (Info): No secrets committed; key handling is env/UI only. OK.
- S4 (Info): `report.save_pdf` uses `unsafe_allow_html`? No — that's `app.py`
  (line 81) which renders logs via `unsafe_allow_html=True`. Logs are agent-generated
  (not user HTML), low risk, but flag for review if logs ever include untrusted input.

---

## 5. Dead / Unreachable Code
- `poc_corpus.get_poc()` is exported in `__init__` but **never called** by any module
  (assessor uses `corpus_lookup` + `fetch_github_poc` directly). Dead export.
- `assess_exploit_quality(use_online=True)` default is never overridden by callers.
- `app.py` `api_key=""` initial then overwritten — fine.

---

## 6. What Is Genuinely Working (evidence-backed)
1. Scan ingestion (XML/JSON/custom) + live EPSS ranking.
2. Enum-constrained Finding/ExploitAssessment/ExecutionOutcome models.
3. Real LLM exploit-quality scoring via local Ollama (structured output, no garbage).
4. Simulation executor emitting real, label-driven outcomes + request counts.
5. LangGraph assess→execute→pivot/advance with N-threshold pivot and guaranteed
   termination (no infinite loop).
6. Real executor connectivity probe (SKIPPED on LOW, FAIL_NO_TARGET on unreachable).
7. JSON + PDF report generation.
8. SMART-vs-DUMB benchmark that runs and shows a real request/loop efficiency win.
9. Streamlit app imports and reuses the verified pipeline.
