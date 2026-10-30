# FINAL PROJECT HANDOVER REPORT — AI VAPT Framework

_Read-only evidence report. Generated 2026-08-24 by Hermes (orchestrator) from
actual repository inspection: Git history, task register, running tests, benchmark
artifacts, source code, and governance docs. No source code was modified to
produce this report. All claims are mapped to artifacts; nothing is taken on
trust from prior chat summaries._

---

## PART 1 — PROJECT IDENTITY AND CURRENT OBJECTIVE

- **Exact project title** (from README.md:1-4):
  "Autonomous AI VAPT Framework — State-aware Vulnerability Assessment &
  Penetration Testing with **Exploit Quality Scoring** and **Dynamic
  Decision-Pivoting** (LangGraph)."
  Working thesis framing (master plan / docs): _"An Autonomous AI Framework for
  Vulnerability Assessment: Integrating Exploit Quality Scoring and Dynamic
  Decision-Pivoting."_

- **Current research objective:**
  Demonstrate that an autonomous pentest agent can (a) pre-score exploit
  usability with an LLM BEFORE execution to prioritise high-viability routes
  (Gap-1), and (b) track per-CVE attempt counts in explicit LangGraph state and
  pivot after N failures to avoid infinite-loop traps (Gap-2); and measure both
  against an unguided baseline.

- **GAP-1 definition** (literature: Lu et al. 2024 PoC quality):
  Existing agents fire exploits without grading whether the PoC is actually
  usable. This framework grades each candidate exploit via a structured-LLM
  usability matrix and uses that score to RANK the attack path.

- **GAP-2 definition** (literature: Deng et al. 2025 Type-B planning/state
  failure):
  Agents lack explicit attempt/state tracking and loop forever on dead-ends.
  This framework keeps explicit attempt counters in state and pivots to the next
  target after `max_attempts` failed attempts.

- **Current project phase:**
  Core framework IMPLEMENTED and VERIFIED under SIMULATION. Master-plan tasks
  T-SAFE, T-BENCH-LOOP, T-TESTS, T-CORPUS, T-BENCH-VAR, T-GAP1-VALID (+v2),
  T-OPENAI, T-CHECKPOINT, T-REQPIN, T-DEADCODE are DONE/VERIFIED. Remaining:
  T-GITHUB, T-README, T-UI (TODO), T-DOCKER (BLOCKED).

- **What the framework CLAIMS to do:**
  Rank exploit candidates by EPSS×usability, assess each with an LLM before
  execution, execute in simulation (label-driven) or safe real mode, pivot after
  N failures, persist/resume state, and emit a JSON/PDF report + benchmark.

- **What it EXPLICITLY does NOT currently claim to do (per executor.py:1-30,
  README.md:62-69, 09_BENCHMARK_EVIDENCE.md):**
  - Claim real-world exploit success against live targets (simulation only by default).
  - Claim production-grade LLM-assessor accuracy (assessor correctness is NOT validated on unseen CVEs).
  - Execute offensive payloads by default (default real mode is connectivity-ONLY; danger_mode is opt-in).

### Three categories — kept strictly separate

| Category | Definition in THIS project | Current status |
|----------|----------------------------|----------------|
| SIMULATION | Outcomes resolved from `data/poc_corpus/labels.json`; no live payload. | THE ONLY MODE RUN IN EVIDENCE. All benchmarks, ablations, tests. |
| CONTROLLED VALIDATION | Offline controlled experiments (ablation, variance) measuring mechanism. | DONE: T-GAP1-VALID, T-BENCH-VAR. |
| REAL OBSERVED RESULT | Live exploit execution in a sandboxed lab, success parsed from real module output. | NOT ACHIEVED. Blocked by T-DOCKER (Docker down). No code path has produced a real-observed exploit success. |

---

## PART 2 — CURRENT REPOSITORY AND GIT STATE

- **Project root:** `/home/vinit/ai_vapt_framework`
- **Current branch:** `master`
- **Current HEAD:** `c1f4d2ba6f5930da0ce840f70e14bbf8ece20cd3` (T-DEADCODE)
- **Working-tree status:** CLEAN (no uncommitted changes at report time).
- **Total tracked files:** 65 (`git ls-files | wc -l`).
- **No `.env` present** (verified); no secrets in tree.

### Recent commit history (chronological, oldest → newest)
```
31ccd06 baseline: verified AI VAPT framework (audit 2026-08-21)
21b0917 governance: project-management memory + reconciliation (STEP A/B/C)
e5d31ba T-SAFE (P0) VERIFIED
9b67dac T-BENCH-LOOP (P0) VERIFIED
62b73ef T-TESTS (P3) VERIFIED (13 tests)
3fa2148 T-CORPUS (P1): corpus 3 -> 12 CVEs (data)
ecdf814 T-CORPUS (P1) REVIEW CLOSURE: VERIFIED
c7de8d8 T-BENCH-VAR (P3) VERIFIED (5 seeds)
eda98c3 T-GAP1-VALID (P1): ablation (uniform EPSS)
5ba1e10 T-GAP1-VALID (P1) CLOSURE: VERIFIED
7617102 T-TESTS extension (P3): +5 tests
57be1f7 T-GAP1-VALID v2 (P1): EPSS-only ablation (12 CVEs)
25e4137 T-OPENAI (P2)
468b138 governance: reconcile register (T-TESTS-ext, GAP1v2, OPENAI)
f1561be T-CHECKPOINT (P2)
3ddf54c governance: mark T-CHECKPOINT DONE
9b0fe96 T-REQPIN (P3)
bef4dee governance: mark T-REQPIN DONE
c1f4d2b T-DEADCODE (P4)
```

### Completed tasks → commits
| TASK | ID | PRIORITY | STATUS | IMPL COMMIT | REVIEW/COMMIT |
|------|----|----------|--------|-------------|---------------|
| T-SAFE | P0 | VERIFIED | `e5d31ba` | claude_p0_review_T-SAFE_20260824.md (APPROVE w/ follow-up) |
| T-BENCH-LOOP | P0 | VERIFIED | `9b67dac` | claude_p0_review_T-BENCH-LOOP_20260824.md (APPROVE) |
| T-TESTS | P3 | VERIFIED | `62b73ef` + ext `7617102` | register note; Claude ext review APPROVE |
| T-CORPUS | P1 | VERIFIED | `3fa2148`+`ecdf814` | P1 review APPROVE w/ follow-up |
| T-BENCH-VAR | P3 | VERIFIED | `c7de8d8` | register note |
| T-GAP1-VALID | P1 | VERIFIED | `eda98c3`+`5ba1e10`+v2 `57be1f7` | P1 review APPROVE w/ follow-up |
| T-OPENAI | P2 | DONE | `25e4137` | Claude review APPROVE |
| T-CHECKPOINT | P2 | DONE | `f1561be` | Hermes (P2) verified |
| T-REQPIN | P3 | DONE | `9b0fe96` | Hermes (P3) verified |
| T-DEADCODE | P4 | DONE | `c1f4d2b` | Hermes (P4) verified |

---

## PART 3 — COMPLETE TASK REGISTER

Classification legend: DONE_VERIFIED, DONE_PARTIALLY_VERIFIED, TODO, BLOCKED, SUPERSEDED, REJECTED.

| Task | Priority | Classification | Notes |
|------|----------|----------------|-------|
| T-SAFE | P0 | DONE_VERIFIED | Real mode connectivity-ONLY by default; danger_mode opt-in+warned. |
| T-BENCH-LOOP | P0 | DONE_VERIFIED | Loop metric now measured+asserted, not hardcoded. |
| T-TESTS | P3 | DONE_VERIFIED | 13 → 18 → 29 tests; offline regression net. |
| T-CORPUS | P1 | DONE_VERIFIED | labels.json 3 → 12 CVEs; all have .py. |
| T-BENCH-VAR | P3 | DONE_VERIFIED | 5 seeds; order-invariance PASS. |
| T-GAP1-VALID | P1 | DONE_VERIFIED | Two ablations (uniform-EPSS + EPSS-only). Proof-of-mechanism. |
| T-OPENAI | P2 | DONE_PARTIALLY_VERIFIED | Code hardened + mock-tested. **Live OpenAI path UNVERIFIED** (no key). |
| T-CHECKPOINT | P2 | DONE_VERIFIED | Save/load/resume; round-trip + interrupted-repro tests. |
| T-REQPIN | P3 | DONE_VERIFIED | Exact pins; `.python-version`; README doc. |
| T-DEADCODE | P4 | DONE_VERIFIED | Dead `get_poc` removed + export purge. |
| T-GITHUB | P3 | TODO | Needs GITHUB_TOKEN; mock sufficient for DONE. |
| T-README | P4 | TODO | Stale SMART=1 table (README:77) vs actual 5. |
| T-UI | P4 | TODO | Streamlit imports clean; interactive run unverified; `unsafe_allow_html=True` on logs (app.py:80). |
| T-DOCKER | P1 | BLOCKED | Docker daemon down. Thesis-critical real validation unavailable. |

No tasks SUPERSEDED or REJECTED in the current register. (Historical D-006/D-007/D-008/D-009 incidents were governance-process events, not task definitions; they are recorded in 05_DECISION_LOG, not the task register.)

### Detailed sections for key tasks

**T-SAFE (P0) — DONE_VERIFIED**
- Objective: stop "real" mode from shelling corpus PoC (offensive sends) while mislabeled "safe probe"; make it connectivity-ONLY by default.
- Files changed: `core/executor.py`, README.md, docs/CURRENT_STATE_AUDIT.md note.
- Implementation: `Executor.execute` real mode now performs only `_connectivity_probe` (TCP connect, no payload) unless `danger_mode=True`; LOW-usability findings always SKIPPED; danger_mode emits a runtime warning and parses real module stdout.
- Acceptance: default real mode fires no offensive send. Verified by Hermes reproducibility R1–R7 + Claude P0 review APPROVE w/ follow-up.
- Tests: `tests/test_core.py` monkeypatches `socket`/`subprocess` and asserts no shell-out for corpus modules in default real mode.
- Result: PASS. Evidence: 03_TASK_REGISTER T-SAFE; external_reviews/claude_p0_review_T-SAFE_20260824.md.
- Limitation: danger_mode offensive path is implemented but NEVER executed in a lab (T-DOCKER blocked) → the offensive branch is UNVERIFIED by observation.

**T-BENCH-LOOP (P0) — DONE_VERIFIED**
- Objective: replace hardcoded `smart_loop = 0` with measured, asserted instrumentation.
- Files: `tests/evaluate.py`.
- Implementation: `smart_agent` counts per-CVE executions from `final["results"]`; `loop_events = sum(max(0, count - threshold))`; runtime `assert max_per_cve <= threshold`.
- Acceptance: loops_avoided derived from instrumentation; pytest asserts SMART ≤ max_attempts.
- Result: SMART measured 0 loop events across all runs; DUMB 2. PASS.
- Evidence: `data/benchmark_results.csv`, 09_BENCHMARK_EVIDENCE.md, Claude P0 review APPROVE.

**T-TESTS (P3) — DONE_VERIFIED**
- Objective: real pytest regression net.
- Files: `tests/test_core.py` (13), `tests/conftest.py` (offline guard), `tests/test_ttests_gaps.py` (5), `requirements.txt`.
- Result: suite grew 13 → 18 → 29. All offline, deterministic.
- Evidence: `pytest tests/ -q` 29 passed; 07_TEST_STATUS.md.
- Note: an earlier implementation agent overstepped scope (reverted in D-006); only the in-scope suite was kept.

**T-CORPUS (P1) — DONE_VERIFIED**
- Objective: grow labelled PoC corpus ≥8.
- Files: `data/poc_corpus/*.py` (12) + `labels.json` (12 entries).
- Composition: reliability HIGH×4, MEDIUM×5, LOW×3; outcome success×5, fail_timeout×3, fail_syntax×2, fail_dependency×2.
- Evidence: 03_TASK_REGISTER T-CORPUS; all `.py` present; byte-identical core.
- Note: corpus CVE IDs are REAL (e.g. CVE-2021-44228). This is intentional for reproducibility; NOT to be anonymised (would break corpus resolution — see Part 10).

**T-BENCH-VAR (P3) — DONE_VERIFIED**
- Objective: multi-seed variance for statistical defensibility.
- Files: `tests/benchmark_var.py`, `data/benchmark_variance.csv`.
- Implementation: 5 explicit seeds [101..505]; finding ORDER shuffled per seed; DUMB benign retry-cap perturbed 8..12 (SMART pivot threshold fixed at 2).
- Result: SMART std=0 for all metrics across seeds (order-invariant); DUMB requests mean 21, std 3.16. ORDER-INVARIANCE CHECK PASS.
- Evidence: `data/benchmark_variance.csv` (10 rows).

**T-GAP1-VALID (P1) — DONE_VERIFIED**
- Two experiments:
  - `tests/gap1_ablation.py` (uniform EPSS=0.5, stub assessor reliability→usability, random order for B): A reaches first success at index 0 / 1 request; B_mean index 2.00 / 5.00 requests. DELTA +4.00 reqs, +2.00 index.
  - `tests/ablation.py` (v2, full 12-CVE, frozen synthetic EPSS table): ARM A (epss×usability) vs ARM B (epss-only). MEASURED: wasted_before_first_success A=0 / B=2; requests_to_first_success A=1 / B=3; total waste A=14 / B=14; completion 100% both.
- Implementation: both monkeypatch `core.agent_graph.assess_exploit_quality` with offline stub → no Ollama/network.
- Acceptance: scoring reaches foothold sooner. PASS (asserts hold).
- Strongest defensible claim: GAP-1 "proven for routing efficiency (not total-attempt parity)." Best-case UPPER BOUND (corpus reliability→outcome 100% correlated for HIGH/LOW). Proof-of-mechanism only.
- Evidence: `data/gap1_ablation.csv`, `data/ablation_epss_only.csv`, 09_BENCHMARK_EVIDENCE.md.
- v2 needed because the first experiment used uniform EPSS and random B-order, which a reviewer could call unrepresentative; v2 uses realistic EPSS magnitudes and a literal "epss-only" control arm on the full corpus.

**T-OPENAI (P2) — DONE_PARTIALLY_VERIFIED**
- Objective: harden + verify OpenAI provider path.
- Files: `core/exploit_assessor.py`, `tests/test_openai_provider.py` (3 tests).
- Implementation: `get_llm('openai')` raises `RuntimeError` if `OPENAI_API_KEY` missing (dummy-key fallback removed). Tests stub `ChatOpenAI` → same structured-output contract offline; missing-key fails fast.
- Result: 21 passed. Ollama path unchanged.
- Limitation: **live OpenAI path UNVERIFIED** (no real key available). Documented.

**T-CHECKPOINT (P2) — DONE_VERIFIED**
- Objective: AgentState persistence + resume.
- Files: `core/agent_graph.py` (save/load/resume), `tests/test_checkpoint.py` (8).
- Implementation: `save_checkpoint` (versioned JSON), `load_checkpoint` (rebuilds Finding models, rejects unknown version), `resume_agent` (re-enters graph at status-derived node: ASSESSING→assess, TESTING→execute, SUCCESS→pivot; COMPLETED→noop). `build_vapt_graph(entry=)` added; `initial_agent_state` extracted.
- Acceptance: interrupted save→resume reproduces fresh run exactly. Verified by Hermes: resume==fresh results True; validated CVE executed once; completed noop True.
- Result: 29 passed.

**T-REQPIN (P3) — DONE_VERIFIED**
- Files: `requirements.txt` (exact == pins), `.python-version` (3.10), README.md, 07.
- Verification: `pip freeze` diff vs pins = clean (reproducible). 29 passed.

**T-DEADCODE (P4) — DONE_VERIFIED**
- Files: `core/poc_corpus.py` (removed `get_poc`), `core/__init__.py` (removed import + `__all__` entry).
- Verification: `grep -rn get_poc` empty; import core OK; 29 passed.

---

## PART 4 — ACTUAL SYSTEM ARCHITECTURE

### Pipeline trace (source-inspected)

| Step | Source function | Input | Output | Nature |
|------|-----------------|-------|--------|--------|
| Scan ingestion | `scanner.process_scan` (`core/scanner.py:131`) | Nmap XML/JSON or custom JSON | `List[Finding]` | deterministic; EPSS enrich calls FIRST.org API (network, fails safe→0.0) |
| Finding normalization | `schemas.finding_from_dict` (`core/schemas.py:118`) | dict | `Finding` (Pydantic) | deterministic |
| EPSS enrichment | `scanner.fetch_epss_score` (`core/scanner.py:26`) | CVE id | float 0..1 | **network** (live FIRST.org), offline-safe default 0.0; in benchmarks EPSS is FROZEN (ablation) or from `sample_scan.json` |
| Candidate lookup | `poc_corpus.corpus_lookup` (`core/poc_corpus.py:35`) | CVE id | PoC source text or None | label-driven file read |
| PoC corpus | `data/poc_corpus/<CVE>.py` + `labels.json` | — | labelled exploit code | static; NOT executed by default |
| Exploit quality assessment | `exploit_assessor.assess_exploit_quality` (`core/exploit_assessor.py:50`) | CVE + code | `ExploitAssessment` | **LLM-driven** (Ollama/OpenAI structured output); in tests/ablation monkeypatched to offline stub |
| Candidate ranking | `agent_graph.rank_findings` (`core/agent_graph.py:59`); `Finding.priority_score` (`core/schemas.py:106`) | findings | sorted findings | deterministic: `epss*(0.5+0.5*usability)` |
| Executor | `executor.Executor.execute` (`core/executor.py:150`) | Finding + target | `ExecutionResult` | SIMULATION: label-driven outcome; REAL: connectivity probe (no payload); danger_mode: shell-out+parse |
| Observed/simulated outcome | `executor._outcome_from_label` / `_connectivity_probe` / `_parse_module_output` | — | `ExecutionOutcome` enum | simulation=label; real=TCP; danger=parsed |
| AgentState update | `agent_graph.execute_node` (`core/agent_graph.py:90`) | result | state | deterministic state mutation |
| Retry/pivot/advance | `evaluate_decision` (`core/agent_graph.py:139`) + `pivot_node` (`core/agent_graph.py:115`) | state | next node | deterministic: pivot if attempt_count>=max_attempts or SUCCESS→advance |
| Completion | `AgentStatus.COMPLETED` | — | final state | deterministic |
| Report/UI | `report.build_report` (`core/report.py:22`) + `app.py` (Streamlit) | final state | JSON/PDF/dashboard | deterministic |
| Benchmark instrumentation | `tests/evaluate.py:74-86` | final results | loop_events, requests | measured from trace |

### ASCII architecture diagram
```
        ┌─────────────────────────────────────────────────────────┐
        │                   Scan ingestion                         │
        │  scanner.process_scan (Nmap XML/JSON / custom JSON)       │
        │  ├─ parse_nmap_xml / parse_nmap_json / parse_custom_json  │
        │  └─ enrich() → fetch_epss_score (FIRST.org, net, safe)    │
        └───────────────────────────┬─────────────────────────────┘
                                     │ List[Finding] (EPSS attached)
                                     ▼
        ┌─────────────────────────────────────────────────────────┐
        │            PoC corpus (data/poc_corpus/)                  │
        │  corpus_lookup(cve) → real PoC source text (label-driven) │
        └───────────────────────────┬─────────────────────────────┘
                                     │
                                     ▼
        ┌─────────────────────────────────────────────────────────┐
        │      Exploit quality assessment (GAP-1)                   │
        │  exploit_assessor.assess_exploit_quality                  │
        │  → LLM (Ollama/OpenAI) with_structured_output(           │
        │      ExploitAssessment)  [USABILITY RANK]                 │
        └───────────────────────────┬─────────────────────────────┘
                                     │ usability_rank
                                     ▼
        ┌─────────────────────────────────────────────────────────┐
        │      Ranking: priority_score = epss*(0.5+0.5*usability)    │
        │      rank_findings()  → ordered attack path               │
        └───────────────────────────┬─────────────────────────────┘
                                     │
                                     ▼
   ┌─────────────────────────── LangGraph AgentState ───────────────────────────┐
   │  assess_node → execute_node → (conditional) → execute | pivot → assess ...   │
   │                                                                             │
   │  GAP-2: attempt_count per CVE; pivot when attempt_count>=max_attempts (N)    │
   │         or on SUCCESS → advance to next finding. No loops.                   │
   │  executor.execute(): SIMULATION(label) | REAL(connectivity-only) |           │
   │                      REAL+danger_mode(shell-out+parse, opt-in)               │
   └───────────────────────────┬─────────────────────────────────────────────────┘
                                     │ final AgentState
                                     ▼
        ┌─────────────────────────────────────────────────────────┐
        │  report.build_report → JSON + PDF ;  app.py (Streamlit)   │
        │  tests/evaluate.py → SMART vs DUMB benchmark → CSV        │
        └─────────────────────────────────────────────────────────┘
```

---

## PART 5 — GAP-1 EVIDENCE

1. **Assessor implementation path:** `core/exploit_assessor.py:50 assess_exploit_quality` → `get_llm` (`:29`) → `llm.with_structured_output(ExploitAssessment)` → chain invoke with code sample (≤2000 chars).

2. **Input features/signals:** the PoC source code text (from corpus or optional GitHub), CVE id, and (for cross-check only) the curated corpus `reliability` label appended to `reasoning`.

3. **Deterministic vs LLM-derived:**
   - Deterministic: code retrieval, label cross-check, `priority_score` formula.
   - LLM-derived: all 9 `ExploitAssessment` fields (exploit_found, syntax_valid, os_dependencies, privileges_required, network_noise, complexity_score, prerequisites_met, usability_rank, reasoning).

4. **Structured output schema:** `schemas.ExploitAssessment` (`core/schemas.py:34`) — Pydantic model with enum-constrained `privileges_required` (none/user/root), `network_noise` (low/medium/high), `usability_rank` (HIGH/MEDIUM/LOW), `complexity_score` int 1..10. Enum constraint prevents the prototype's garbage `"}"` values.

5. **Scoring/ranking method:** `Finding.priority_score()` = `round(epss * (0.5 + 0.5*u), 4)`, where `u ∈ {HIGH:1.0, MEDIUM:0.6, LOW:0.3}`. `rank_findings()` sorts descending (`agent_graph.py:59`).

6. **Proof assessment occurs BEFORE execution:** `assess_node` (`agent_graph.py:68`) runs `assess_exploit_quality` and sets `usability_rank` BEFORE `execute_node` (`agent_graph.py:90`) runs the executor. The graph edge is `assess → execute`.

7. **Proof ranking affects selection:** `initial_agent_state`/`rank_findings` order findings by `priority_score` before the loop; `execute_node` always processes `findings[current_index]`. The ablation (Part 9) measures the effect.

8. **Corpus composition/labels:** 12 CVEs, each with `.py` PoC + `labels.json` entry `{reliability, outcome, requests, source}`. Reliability HIGH×4/MED×5/LOW×3; outcome success×5/timeout×3/syntax×2/dep×2.

9. **Supporting benchmark/experiment:** `tests/gap1_ablation.py` and `tests/ablation.py` (Part 3 T-GAP1-VALID).

10. **T-GAP1-VALID findings:** with scoring, foothold reached at index 0 / 1 request (uniform-EPSS exp); in EPSS-only v2, wasted_before_first_success A=0 vs B=2, 2 requests sooner. Mechanism proven.

11. **v2 changes + why:** v2 added a realistic frozen-EPSS control arm over all 12 CVEs because v1 used uniform EPSS and random B-order (reviewer-criticisable). v2 is the "directive-exact" experiment.

12. **Exact remaining limitations:**
   - Assessor accuracy on UNSEEN CVEs is NOT measured. The stub in ablations maps label→usability, so the measured effect assumes a perfect assessor. A production LLM assessor's error is unknown.
   - Corpus reliability→outcome is 100% correlated for HIGH/LOW → best-case UPPER BOUND.
   - No real labelled ground truth for "usability" independent of the corpus author's label.

**Strongest defensible claim (NOT "fully proven"):** GAP-1 is proven as a *proof-of-mechanism* — exploit-quality scoring, when available, demonstrably changes attack-path ordering toward higher-viability routes and reaches a foothold with fewer wasted attempts. Real-world efficacy depends on live assessor accuracy, which is unvalidated.

---

## PART 6 — GAP-2 EVIDENCE

1. **AgentState structure** (`agent_graph.py:37`): target, findings (List[Finding]), current_index, current_cve, exploit_rank, attempt_count, max_attempts, status, provider, mode, logs, results.

2. **Attempt/failure tracking:** `execute_node` increments `attempt_count` each execution; `pivot_node` resets `attempt_count=0` when moving to a new finding (`agent_graph.py:130`). Per-CVE attempts bounded by `max_attempts`.

3. **Pivot threshold logic:** `evaluate_decision` (`agent_graph.py:139`): if `status==SUCCESS` → "pivot" (advance); if `attempt_count >= max_attempts` → "pivot" (abandon route); else "execute" (retry same CVE).

4. **Loop detection/instrumentation:** `tests/evaluate.py:74-86` — after run, `exec_counts = Counter(r["cve"] for r in results)`; `smart_loop = sum(max(0, c - threshold))`; runtime `assert max_per_cve <= threshold` (errors if pivot failed). SMART measured 0 in every run.

5. **Repeated candidates prevented:** pivot advances `current_index`; a CVE is only re-attempted if its prior attempts < max_attempts within the same run. Resume (`resume_agent`) re-enters at status-derived node so a validated CVE is never replayed (verified).

6. **Pivot selects new path:** `pivot_node` increments `current_index`; next finding is the next in the priority-sorted list; logs "Re-directed to <next_cve>."

7. **Termination:** when `current_index >= len(findings)` → `status=COMPLETED`; graph returns END. Full coverage: a SUCCESS also advances, so all findings are attempted.

8. **Boundary conditions:** `max_attempts` default 2; LOW-usability findings in REAL mode are SKIPPED at executor (not at pivot). Resume of COMPLETED checkpoint = no-op.

9. **Measured benchmark evidence:** SMART loop_events=0 across 5 variance seeds; DUMB loop_events=2 per seed (hard-cap stuck). `data/benchmark_results.csv`, `data/benchmark_variance.csv`.

10. **T-BENCH-LOOP implementation:** see Part 3.

11. **Tests covering pivot logic:** `tests/test_core.py` (pivot advance/abandon, per-CVE ≤ max_attempts, terminate), `tests/test_ttests_gaps.py` (ZERO loop events, real-mode unreachable→FAIL_NO_TARGET), `tests/test_checkpoint.py` (no replay on resume). 

12. **Remaining limitations:** pivot correctness is verified only in SIMULATION (labels drive outcome). The danger_mode offensive path that would exercise real retries is unverified (T-DOCKER).

**Strongest defensible claim:** GAP-2 is proven under simulation — the LangGraph state machine with explicit attempt counters and a per-CVE `max_attempts` pivot bound guarantees zero loop events and full target coverage, measured (not asserted) across 5 seeds. Real-world pivot behaviour pending T-DOCKER.

---

## PART 7 — EXECUTION MODES AND SAFETY

| Mode | Entry | Code | Network? | Success determined by | Labels influence? | Real target? | Safety | Thesis claim |
|------|-------|------|----------|----------------------|-------------------|--------------|--------|--------------|
| **simulation** (default) | `mode="simulation"` | `executor._outcome_from_label` | NO (purely label) | `labels.json` outcome | YES (it IS the truth) | NO | Safe by construction | Valid behavioural benchmark of agent logic |
| **real** (default, danger_mode=False) | `mode="real"` | `_connectivity_probe` only | YES (TCP connect, no payload) | reachability; reports SKIPPED (no exploit sent) | NO (labels not trusted) | YES (target host) | Connectivity-ONLY; LOW usability SKIPPED; no offensive traffic | "Safe probe" — honest |
| **real + danger_mode=True** | `mode="real", danger_mode=True` | shell-out corpus `.py` + `_parse_module_output` | YES (offensive send inside corpus module) | parsed from module stdout/stderr | NO (output parsed, not label) | YES (authorised lab only) | Opt-in, warned, parses real output; never against non-authorised targets | Live exploitation (UNVERIFIED by observation) |

**BEFORE vs AFTER T-SAFE:**
- BEFORE (per 03_TASK_REGISTER T-SAFE evidence): real mode shelled corpus `.py` (e.g. `CVE-2021-44228.py` performs a JNDI `sendall`) while ignoring stdout and TRUSTING `labels.json`, and the docstring called it a "safe connectivity probe." This was both unsafe (offensive send) and dishonest (mislabeled).
- AFTER T-SAFE (`executor.py`): default real mode is connectivity-ONLY (no shell-out); danger_mode is explicit opt-in with a prominent warning and parses REAL module output instead of trusting labels.

**Safety/honesty issue fixed by T-SAFE:** removed the contradiction of an offensive path marketed as a safe probe; default path now provably sends no exploit payload.

**Can any code path currently execute an offensive PoC against a non-lab target?**
- Default simulation/real modes: NO offensive traffic.
- `danger_mode=True`: YES, it shells out the corpus PoC, which contains offensive payloads (e.g. `CVE-2021-44228.py`). This path is gated behind an explicit `danger_mode=True` argument AND prints a warning. It is the user's responsibility to point it only at an authorised, isolated lab. The code does NOT auto-enable it and does NOT target anything except the `target` string passed to `run_agent`. **Uncertainty note:** the corpus `.py` files were not executed in this session; their exact runtime behaviour must be reviewed before any live use (T-DOCKER scope). The exact file requiring review is `data/poc_corpus/*.py` plus `executor._parse_module_output` success-token contract.

---

## PART 8 — TESTING EVIDENCE

- **Framework:** pytest (pinned `pytest==9.1.1`).
- **Test files:** `test_core.py` (13), `test_ttests_gaps.py` (5), `test_openai_provider.py` (3), `test_checkpoint.py` (8). Plus `conftest.py` (offline guard: blocks network, records subprocess).
- **Current count:** 29 tests.
- **Exact latest command:** `venv/bin/python -m pytest tests/ -q`
- **Exact latest result (verified 2026-08-24):** `29 passed in 0.10s`.
- **Smoke tests:** `python -m core.agent_graph` (end-to-end run prints results); `python -m core.scanner data/sample_scan.json`.
- **Regression tests:** entire suite is the regression net (offline).
- **Integration tests:** `test_checkpoint.py` (interrupted→resume reproduces fresh run).
- **GAP-1 tests:** `test_ttests_gaps.py` covers assessor enum-constrained output + routing invariants offline.
- **GAP-2 tests:** `test_core.py` (pivot loop bound), `test_ttests_gaps.py` (ZERO loop events), `test_checkpoint.py` (no replay).
- **Safety tests:** `test_core.py` monkeypatches socket/subprocess → asserts default real mode fires no offensive send; LOW usability SKIPPED.
- **Benchmark tests:** `tests/evaluate.py` (asserts SMART ≤ max_attempts), `tests/benchmark_var.py`, `tests/gap1_ablation.py`, `tests/ablation.py` (these are scripts, run separately; not collected by default pytest).
- **Coverage:** NOT measured (no coverage.py run). Do NOT claim a percentage. What is covered: schemas enums, priority_score ordering, scanner parsers, executor sim label→outcome, agent_graph pivot/terminate, resume round-trip, OpenAI fail-safe, offline guard. What is NOT covered by automated tests: live EPSS API, live GitHub fetch, Streamlit UI interaction, danger_mode offensive execution, real OpenAI call.

---

## PART 9 — BENCHMARK AND EXPERIMENTAL EVIDENCE

### A. Experiment design (tests/evaluate.py)
- **SMART:** full framework — `rank_findings` (EPSS×usability) + assess before execute + pivot at N=2.
- **DUMB baseline:** `dumb_agent` tries every exploit blindly, retrying each up to `hard_cap` (10 in evaluate.py; 8..12 in benchmark_var.py) with NO scoring and NO pivot threshold.
- **Starting conditions:** 3 labelled findings (Log4Shell HIGH-success, OpenSSH MED-timeout, Spring4Shell LOW-syntax), `TARGET="127.0.0.1"`, provider Ollama.
- **Ordering:** SMART sorted by priority_score; DUMB processes in listed order.
- **Seeds:** evaluate.py single run; benchmark_var.py uses explicit seeds [101,202,303,404,505] with per-seed finding-order shuffle + DUMB cap perturbation.
- **Runs:** 1 (evaluate) + 5 (variance).
- **Metrics:** requests, loop_events, completion %, runtime.

### B. Measured metrics (instrumentation)
- `requests` = sum of `request_count` over results.
- `loop_events` = `sum(max(0, per_cve_count - threshold))` from `final["results"]`, with `assert max_per_cve <= threshold` (evaluate.py:82).
- `completion_%` = validated_success / n_findings × 100.
- `runtime_s` = `time.time()` delta around `app.invoke`.
- Additional: `requests_saved`, `loops_avoided`, `time_saved_s` (derived).

### C. Actual results
From `data/benchmark_results.csv` (evaluate.py, single run):
```
agent              runtime_s  requests  validated  completion_%  loop_events
SMART (framework)  10.296     5         1          33.3          0
DUMB (baseline)    0.000      21        1          33.3          2
```
From `data/benchmark_variance.csv` (5 seeds):
```
seed  agent              requests  validated  completion_%  loop_events
101   SMART (framework)   5         1          33.3          0
101   DUMB (baseline)    19        1          33.3          2
202   SMART              5         1          33.3          0
202   DUMB               21        1          33.3          2
303   SMART              5         1          33.3          0
303   DUMB               23        1          33.3          2
404   SMART              5         1          33.3          0
404   DUMB               25        1          33.3          2
505   SMART              5         1          33.3          0
505   DUMB               17        1          33.3          2
```
SMART: requests mean 5 / std 0; loop_events 0 all seeds. DUMB: requests mean 21 / std 3.16; loop_events 2 all seeds. ORDER-INVARIANCE: PASS (SMART invariant to finding order).

GAP-1 ablation (`data/ablation_epss_only.csv`): A_with_scoring wasted_before_first_success=0, requests_to_first_success=1; B_epss_only wasted_before_first_success=2, requests_to_first_success=3; total waste 14=14; completion 100% both.

### D. Fairness analysis
SMART is **structurally advantaged** in two intended, disclosed ways: (1) it uses the usability signal to order routes (the contribution under test), and (2) the DUMB baseline has NO pivot, so it burns its full retry cap on dead-ends — that is precisely the behaviour GAP-2 eliminates. This is a fair *controlled comparison* of the proposed design vs an unguided loop, not a neutral "model vs model" race. The 33.3% completion is identical for both because it is driven by the fixed 3-finding corpus (1 success), not by agent quality. The honest takeaway is requests/loops saved, not "more vulnerabilities found."

### E. Strongest defensible conclusion
- **Evidentially supported:** Under simulation, the framework reaches the single exploitable target using 5 requests vs DUMB's 21 (≈76% fewer), with 0 loop events vs DUMB's 2, deterministically and order-invariantly across 5 seeds.
- **Suggested but not proven:** That these efficiency gains transfer to real engagements (depends on assessor accuracy + real pivot behaviour).
- **Unsupported:** Any claim of higher real-world exploitation success rate, or that the framework "finds more vulnerabilities" (completion is corpus-bound). Also unsupported: speed improvement (time_saved is NEGATIVE — 10.3s SMART vs ~0s DUMB — because Ollama LLM scoring adds latency; do NOT claim faster).

---

## PART 10 — PoC CORPUS

12 CVEs, all with real labelled `.py` PoC + `labels.json` entry. Safe-to-execute: NO — these are real exploit scripts; they are NOT executed by default (simulation uses labels; default real mode is connectivity-only). Executed: NONE in this project's evidence runs (only labels consumed). Result: SIMULATED (label-driven), never observed.

| CVE | reliability | outcome (label) | has .py | executed? | result |
|-----|-------------|----------------|---------|-----------|--------|
| CVE-2021-44228 (Log4Shell) | HIGH | success | yes | no | simulated success |
| CVE-2023-38408 (OpenSSH) | MEDIUM | fail_timeout | yes | no | simulated fail |
| CVE-2022-22965 (Spring4Shell) | LOW | fail_syntax | yes | no | simulated fail |
| CVE-2017-0144 (EternalBlue) | HIGH | success | yes | no | simulated success |
| CVE-2020-1472 (Zerologon) | HIGH | success | yes | no | simulated success |
| CVE-2019-0708 (BlueKeep) | MEDIUM | fail_timeout | yes | no | simulated fail |
| CVE-2021-26855 (ProxyLogon) | MEDIUM | success | yes | no | simulated success |
| CVE-2021-34527 (PrintNightmare) | MEDIUM | fail_dependency | yes | no | simulated fail |
| CVE-2021-21972 (vCenter) | MEDIUM | fail_timeout | yes | no | simulated fail |
| CVE-2022-1388 (F5 BIG-IP) | HIGH | success | yes | no | simulated success |
| CVE-2024-3094 (xz backdoor) | LOW | fail_dependency | yes | no | simulated fail |
| CVE-2023-34362 (MOVEit) | LOW | fail_syntax | yes | no | simulated fail |

Distribution: HIGH 4, MEDIUM 5, LOW 3; success 5, fail_timeout 3, fail_syntax 2, fail_dependency 2.

**Important:** CVE IDs are real and intentional. An earlier review note suggested "anonymising" them; that is REJECTED — `core/poc_corpus.py:39` resolves corpus files as `os.path.join(CORPUS_DIR, f"{cve}.py")`, so renaming keys would break corpus lookup. Real CVE IDs are correct for a reproducible thesis.

---

## PART 11 — EXTERNAL INTEGRATIONS

| Integration | Classification | Evidence |
|-------------|----------------|----------|
| Ollama (local LLM) | VERIFIED_WORKING | `assess_exploit_quality` runs against `llama3.2:3b`; agent_graph smoke works; Ollama UP at runtime. |
| OpenAI | IMPLEMENTED_UNVERIFIED | Code hardened; mock-tested; live call UNVERIFIED (no key). |
| FIRST EPSS API | IMPLEMENTED_UNVERIFIED | `scanner.fetch_epss_score` calls api.first.org; offline-safe default 0.0; live call not exercised in benchmarks (EPSS frozen/stubbed). |
| GitHub PoC fetch | IMPLEMENTED_UNVERIFIED | `fetch_github_poc` returns None without GITHUB_TOKEN; never exercised live (T-GITHUB TODO). |
| Docker | BLOCKED | Daemon down; T-DOCKER blocked. No sandboxed live execution exists. |
| Streamlit | IMPLEMENTED_UNVERIFIED | `app.py` imports clean; interactive run unverified (T-UI TODO); `unsafe_allow_html=True` on logs (review). |
| PDF generation | VERIFIED_WORKING | `report.save_pdf` uses reportlab; imports OK, exercised via run path. |
| pandas (CSV) | VERIFIED_WORKING | benchmark CSV writes succeed. |

Thesis-critical unverified integrations: **Docker (T-DOCKER)** is the only one whose verification would change the thesis's core claim (real observed result). OpenAI/GitHub/EPSS are conveniences; their absence does not weaken the simulation-proven claims.

No tokens/keys/credentials are present in the repository (no `.env`, no hardcoded secrets in source — verified by grep of `getenv`/`os.environ` usage and absence of `.env`).

---

## PART 12 — REMAINING RISKS AND BLOCKERS

| ID | Risk | Class | Consequence | Recommended action | Thesis-blocking? |
|----|------|-------|-------------|--------------------|------------------|
| R-002 | No Docker/sandbox for live PoC | THESIS_CRITICAL | No real-observed exploit validation | T-DOCKER once Docker up + authorised lab | YES (for real-observed claim) |
| R-003 (mitigated) | Benchmark loop metric was hardcoded | resolved by T-BENCH-LOOP | — | — | No |
| R-006 (mitigated) | GAP-1 impact not demonstrated | resolved by T-GAP1-VALID | — | — | No (mechanism proven) |
| R-007 (partial) | OpenAI path unverified | LOW | No impact on sim claims | T-OPENAI live key (optional) | No |
| R-009 | Streamlit unverified; unsafe_allow_html | LOW | UI claim weak; minor XSS if untrusted logs | T-UI review | No |
| R-011 | README stale numbers | LOW (docs) | Confuses reader | T-README | No |
| R-004/005 (mitigated) | no tests / small corpus | resolved | — | — | No |
| NEW | Assessor accuracy on unseen CVEs unvalidated | MEDIUM (thesis honesty) | GAP-1 efficacy claim is best-case bound | Document as limitation; optionally lab-test | No (already disclosed) |
| NEW | time_saved is NEGATIVE | MEDIUM (honesty) | Don't claim "faster" | Report requests/loops saved only | No |

**T-DOCKER specifics:** would add a REAL-OBSERVED exploit-success result by running sandboxed corpus modules against an isolated container (DVWA/Metasploitable/crAPI) and parsing actual module output (replacing label trust). This is the only evidence category currently missing and the only thing that would let the thesis state observed (not simulated) efficacy. It requires: Docker daemon running, an authorised isolated lab, and review of each `data/poc_corpus/*.py` for safety. Until then, all efficacy claims remain simulation/proof-of-mechanism.

---

## PART 13 — WHAT IS ACTUALLY COMPLETE?

| Dimension | Rating | Evidence |
|-----------|--------|----------|
| A. Core software implementation | COMPLETE | All modules implemented; 29 tests pass; smoke runs. |
| B. GAP-1 research evidence | SUBSTANTIALLY_COMPLETE | Proof-of-mechanism via 2 ablations; assessor accuracy on unseen CVEs unvalidated (disclosed as upper bound). |
| C. GAP-2 research evidence | SUBSTANTIALLY_COMPLETE | Measured 0 loops across 5 seeds in simulation; real-mode pivot unverified (DOCKER). |
| D. Experimental evaluation | COMPLETE (simulation) | SMART vs DUMB benchmark + variance + ablations; all reproducible offline. |
| E. Controlled real-world/lab validation | BLOCKED | T-DOCKER; no live observed result exists. |
| F. Reproducibility | COMPLETE | Pinned deps (==), .python-version, frozen EPSS inputs, offline guards, deterministic seeds. |
| G. Thesis readiness | PARTIAL | Framework + evidence ready; thesis document authoring and (optionally) T-DOCKER real run remain. Reader must be told clearly it is simulation/proof-of-mechanism. |

No percentage is asserted; ratings are evidence-based categorical judgements.

---

## PART 14 — RECOMMENDED NEXT ROADMAP (DO NOT AUTO-EXECUTE)

### MANDATORY BEFORE THESIS FINALIZATION
1. **T-DOCKER (P1, BLOCKED)** — Get Docker daemon up + authorised isolated lab; run sandboxed corpus modules; parse real output. Needed for REAL OBSERVED validation. Requires user action (infra + authorisation). Stop condition: ≥1 CVE validated against a live container with success parsed from observed output, no traffic outside container net. Agent: cyber (impl) + verify-agent (review). Thesis impact: HIGH (converts simulation→observed). User action: YES (Docker + lab).
2. **Thesis document authoring** — Structure results chapter around simulation/proof-of-mechanism; include related-work comparison with the UI-centric `vikramrajkumarmajji/AI-VAPT` repo (already analysed). Agent: Hermes-assisted writing. User action: YES (content decisions).

### STRONGLY RECOMMENDED
3. **T-README (P4)** — Fix stale SMART=1 table (README:77) to actual 5; align real-mode wording with T-SAFE. Stop: README numbers match CSV. Agent: sw-dev. User action: NO.
4. **T-UI (P4)** — Boot Streamlit; review `unsafe_allow_html=True` on logs (sanitize if logs could carry untrusted input). Stop: dashboard launches + run shows live feed + downloads. Agent: sw-dev + code-review. User action: NO (but interactive verify needs a display).

### OPTIONAL / POLISH
5. **T-GITHUB (P3)** — Mock test + optional one live fetch with GITHUB_TOKEN. Stop: mock green + one documented live fetch. Agent: github. User action: YES (token, optional).
6. **Coverage measurement** — Add coverage.py to quantify test coverage (currently unreported). Optional.

Sequencing: T-DOCKER (if infra available) → thesis writing in parallel → T-README/T-UI polish → T-GITHUB optional.

---

## PART 15 — EXECUTIVE HANDOVER SUMMARY

```
CURRENT PHASE:        Core framework implemented & verified under SIMULATION.
LAST VERIFIED TASK:   T-DEADCODE (P4), commit c1f4d2b (2026-08-24).
CURRENT GIT COMMIT:   c1f4d2ba6f5930da0ce840f70e14bbf8ece20cd3 (master, tree clean).
CURRENT TEST STATUS:  29 passed (pytest, offline, deterministic).
CORE SYSTEM STATUS:   COMPLETE — all modules implemented; smoke runs green.
GAP-1 STATUS:        SUBSTANTIALLY_COMPLETE — proof-of-mechanism proven (2 ablations);
                      assessor accuracy on unseen CVEs unvalidated (disclosed upper bound).
GAP-2 STATUS:        SUBSTANTIALLY_COMPLETE — 0 loop events measured across 5 seeds (simulation);
                      real-mode pivot unverified (T-DOCKER).
BENCHMARK STATUS:     COMPLETE (simulation) — SMART 5 req / 0 loops vs DUMB 21 req / 2 loops;
                      order-invariant; variance harness green. Do NOT claim faster (time_saved negative).
REAL OBSERVED VALIDATION STATUS: NONE — blocked by T-DOCKER (Docker down).
MAIN BLOCKER:         T-DOCKER — no Docker/sandbox; no real-observed exploit result exists.
NEXT RECOMMENDED DECISION:
   (a) If Docker + authorised lab available → execute T-DOCKER for observed validation.
   (b) Else → accept simulation proof-of-mechanism (defensible) and proceed to thesis writing;
       run T-README + T-UI polish. Do NOT claim real-world efficacy.
```

---
_End of handover report. No source code was modified. All statuses verified against
Git, the task register, live test output, and source inspection at report time._
