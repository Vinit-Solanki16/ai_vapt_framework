# MASTER RESEARCH PROJECT REPORT — ai_vapt_framework

**Author role:** Top-level project orchestrator / technical auditor / research
evidence auditor / project historian (READ-ONLY).
**Audit date:** 2026-08-31 (reconstructed from live repository; not from memory).
**Repository HEAD:** `b1f8b42` (branch `master`). **Working tree:** clean.
**Total commits:** 44 (first: `31ccd06` baseline audit 2026-08-21).
**Python:** 3.10.12 venv, offline-capable. **Tests:** TRACK0 39/39, TRACK1 16/16.

> This document is the authoritative evidence source for thesis/paper drafting.
> Every factual statement is traceable to a source file, test, benchmark,
> experiment artifact, or commit. Where evidence is missing, that is stated.

---

## 0. EXECUTIVE SUMMARY (answering the 10 required questions)

1. **What the project actually is:** An M.Tech research prototype that builds an
   *autonomous decision & pivot engine* for sequential action selection under
   repeated failure. Originally framed for VAPT, it was generalized (Stage 1) into
   a domain-independent engine (`decision_engine/`). The research contribution is a
   **bounded, failure-threshold-driven pivot mechanism (Gap-2)**, fair-validated.
2. **What has been built:** (a) Frozen original VAPT prototype `core/` (39 tests);
   (b) generalized domain-independent engine `decision_engine/` (16 tests) with
   assessor / executor / LangGraph engine / checkpoint / VAPT adapter; (c) a fair
   4-agent ablation benchmark; (d) real datasets (CISA KEV 1,682; EPSS bulk 365k;
   per-corpus EPSS 12).
3. **What has been proven:** Gap-2 (bounded pivot reduces wasted attempts) under a
   *fair, identical cap* — VAPT T=2 +77 requests saved, T=5 +200; agnostic sparse
   T=5 +175. Architecture is domain-independent (no VAPT leakage in `core/`).
   Loopback observed validation (Level 2) confirmed pivot-on-failure with no loop.
4. **What is only partially validated:** Gap-1 (pre-execution prioritization). Under
   the fair per-visit-cap protocol the priority component = 0 (no independent win);
   an older total-budget ablation showed routing value but is a best-case bound;
   the observed-tier GAP-1 used a *stubbed* assessor (mechanism only, not LLM accuracy).
5. **What is still unproven:** LLM-assessor accuracy on unseen CVEs; general
   cross-domain experimental generalization (only VAPT + 1 synthetic family);
   container-isolated (Level 3) validation; real-world superiority over other tools.
6. **What is currently pending:** Thesis/paper writing (A7) scoped to the A/B/C
   register; optional total-budget Gap-1 experiment to upgrade B1→A; optional
   Level-3 Docker lab.
7. **Strongest research contribution:** A domain-free decision engine with a
   *fair, ablation-isolated* Gap-2 pivot that demonstrably cuts wasted attempts,
   plus an honest evidence-tier discipline (no overclaim).
8. **Biggest threat to novelty:** Gap-2 is a *small deterministic* mechanism; related
   work (Reflexion/ReAct, PIVOT) covers trajectory refinement, and bounded retry is
   common. Defensible differentiation = explicit per-candidate attempt counter +
   threshold pivot + fair-cap ablation under identical cap (others not cap-isolated).
9. **Can a paper be written now?** **YES** — as a credible *mechanism/research-prototype*
   paper (venue fit: workshop/short paper or M.Tech thesis). NOT as "complete platform".
10. **Single most important next step:** Write the thesis (A7) strictly against the
    R3 claim register (A-claims only + B-qualified + C-omitted); do not inflate scope.

---

## 1. PROJECT IDENTITY — FOUR DISTINCT THINGS

| Identity | What it is | Repository evidence | Status |
|----------|-----------|--------------------|--------|
| **A. Original VAPT research prototype** | The first implementation: VAPT-specific LangGraph agent, assessor, executor, corpus, 39 tests | `core/` (frozen), `tests/` | DONE / VERIFIED |
| **B. Generalized autonomous decision engine** | Domain-independent copy+refactor of the decision logic, VAPT as one adapter | `decision_engine/` | DONE / VERIFIED |
| **C. Full future VAPT platform** | Long-term Stage-2 product: recon, scanners, UI, multi-tool, reporting | `docs/roadmap/00_TWO_TRACK_ROADMAP.md` TRACK B | NOT STARTED |
| **D. Research paper / thesis** | Academic contribution derived from demonstrated evidence | `docs/project_management/R1..R3`, `12_GO_NO_GO.md` | POSITIONING DONE; WRITING PENDING |

**Key separation (must be preserved in the paper):** B is the *engine*; A is the
*first domain*; C is the *future product*; D is the *write-up*. The paper is about
B demonstrated on A. C must not be presented as existing.

---

## 2. ORIGINAL RESEARCH PROBLEM & GAPS

**Motivation (from `core/agent_graph.py:1-11` and `docs/roadmap/00_TWO_TRACK_ROADMAP.md`):**
Autonomous pentest agents (Deng et al. 2024 / PentestGPT) suffer Type-B
planning failure — they loop on a failing target instead of abandoning it. When
multiple exploit/action candidates exist, an agent must *prioritize* and, on
repeated failure, *pivot*. Naive agents waste attempts and never terminate.

**GAP-1 — Pre-execution candidate quality / usability assessment + prioritization.**
Score each candidate before execution; order by priority so viable routes are
tried first. (`decision_engine/core/assessor.py`, `schemas.py:priority_score`.)

**GAP-2 — Explicit state-aware failure tracking, bounded attempts, failure-threshold
pivot.** Per-candidate attempt counter; after `max_attempts` failures, pivot to the
next candidate; terminate when exhausted. (`engine.py:_evaluate` :112, `_pivot_node`
:98.) This directly addresses the loop-forever failure.

The implementation evolved: the *original* `core/` was VAPT-specific; Stage 1
abstracted the mechanism into `decision_engine/` so Gap-2 is demonstrably
domain-free (verified: `core/engine.py` imports only `decision_engine.core.*`).

---

## 3. GENERALIZED DECISION ENGINE — ABSTRACTION

```
Candidate/Action (id, probability, quality_rank, ground_truth)
        ↓  assess_candidates()  → fills quality_rank            [Gap-1, assessor.py]
        ↓  rank_candidates()    → priority_score = prob×(0.5+0.5×quality)  [Gap-1]
        ↓  Executor.execute()   → Outcome (simulation OR real)   [executor.py]
        ↓  observe outcome
        ↓  EngineState.attempt_count++                            [Gap-2 state]
        ↓  _evaluate(): attempt_count >= max_attempts ? → pivot   [Gap-2]
        ↓  _pivot_node(): advance index, reset counter, OR COMPLETED
        ↓  bounded termination (no index left)
```

Domain-independent parts: `schemas`, `assessor`, `executor`, `engine`, `_evaluate`,
`_pivot_node`, `initial_state`, checkpoint. **VAPT-specific only in**
`adapters/vapt_adapter.py` (CVE→ActionCandidate, EPSS→probability, labels→ground_truth).
**Verdict (T-DE-BOUNDARY Q1–Q4 PASS):** `decision_engine/core/` is genuinely
domain-independent — no CVE/exploit/port/host token appears in it. VAPT is one
adapter (answer = "2. one adapter/domain instantiation", plus "3. both" in that the
mechanisms were first proven on VAPT).

---

## 4. ARCHITECTURE DESCRIPTION (components → file:line)

| Component | File | Purpose | Status |
|-----------|------|---------|--------|
| Candidate schema | `decision_engine/core/schemas.py:55` `ActionCandidate` | domain-free task | VERIFIED |
| Priority formula | `schemas.py:77` `priority_score`; `:26` `QUALITY_WEIGHT` | prob×(0.5+0.5×quality) | VERIFIED |
| Gap-1 assessor (offline) | `assessor.py:19` `deterministic_assessor`; `:28` `assess_candidates` | fills quality_rank | VERIFIED (offline) |
| Gap-1 assessor (LLM) | `vapt_adapter.py:70` `vapt_assess_fn(use_llm=True)` → `core.exploit_assessor` | optional Ollama | UNVALIDATED accuracy |
| Executor (sim) | `executor.py:42` `mode="simulation"` → `_outcome_from_label` | ground_truth resolves | VERIFIED |
| Executor (real) | `executor.py:50` `execute_fn` pluggable | domain action runner | VERIFIED contract; unexercised end-to-end |
| Engine graph | `engine.py:117` `build_graph`; `:107` `_evaluate`; `:90` `_pivot_node` | LangGraph state machine | VERIFIED |
| Engine entry | `engine.py:149` `run_engine`; `:133` `initial_state` | driver | VERIFIED |
| Checkpoint | `engine.py:172` `save_checkpoint`; `:183` `load_checkpoint` | resume | VERIFIED (`tests/test_checkpoint.py`) |
| VAPT adapter | `vapt_adapter.py:52` `vapt_candidates_from_corpus`; `:89` `vapt_real_executor` | SOLE VAPT boundary | VERIFIED |
| Fair benchmark | `decision_engine/benchmarks/fair_benchmark.py` | 4-agent ablation | VERIFIED (commit `7001c61`) |
| VAPT fair bench | `decision_engine/benchmarks/fair_vapt_benchmark.py` | full 12-CVE corpus | VERIFIED |
| Original VAPT graph | `core/agent_graph.py` | frozen prototype | VERIFIED (39 tests) |
| Original assessor | `core/exploit_assessor.py` | VAPT LLM usability scoring | present; offline stub in observed tier |
| Original executor | `core/executor.py` | danger_mode + allowlist | VERIFIED safety; danger_mode unexercised |

**UI:** `app.py` (Streamlit smoke-verified per `b385ec4` T-UI). Not central to the
research contribution.

---

## 5. END-TO-END FLOW (TODAY — what actually runs)

**Simulation path (the one exercised by all benchmarks/tests):**
1. Build candidates (VAPT: `vapt_candidates_from_corpus` reads `labels.json` +
   `epss_corpus_enrichment.json`; agnostic: synthetic tasks).
2. `run_engine` → `initial_state` ranks by `priority_score` (Gap-1 ordering).
3. `_assess_node` fills quality_rank (`deterministic_assessor` offline).
4. `_execute_node` calls `Executor.execute` → SIMULATION resolves outcome from
   `ground_truth`.
5. `_evaluate`: success → pivot/advance; `attempt_count >= max_attempts` → pivot;
   else re-execute (bound).
6. `_pivot_node` advances `current_index`, resets `attempt_count`, or COMPLETED.
7. Results list + logs returned. No network, no real exploit. **This is Level 1.**

**Observed path (loopback, Level 2 — executed once, 2026-08-25):**
- `tests/run_tdocker_scenarios.py` forces `mode="real", danger_mode=True`,
  `target_allowlist=["127.0.0.1"]`, against a local Flask emulator.
- Outcome parsed from *real* module stdout/stderr (`core/executor.py:255-264`),
  `labels.json` NOT consulted (`mode="real"` branch). Emulator access log
  independently corroborates. Assessor was a deterministic stub → mechanism validated,
  not LLM accuracy. **3 run timestamps on disk** under `data/experiment_runs/`.

**NOT implemented (do not present as current):** direct URL/IP/network target
ingestion, automated recon, Nmap/Nuclei integration, multi-target live validation.
These are TRACK B / Stage 2 only.

---

## 6. GAP-1 TECHNICAL ANALYSIS

**Mechanism:** `priority_score = probability × (0.5 + 0.5×quality)`; candidates
sorted descending; assessor fills quality from offline deterministic or optional
local-Ollama LLM.

**Evidence table (GAP-1):**

| Claim | Evidence | Test/Experiment | File | Status | Allowed paper wording |
|-------|----------|-----------------|------|--------|-----------------------|
| Ranking changes downstream order | deterministic: HIGH first | code + gap1_ablation | `schemas.py:77`, `tests/gap1_ablation.py` | VERIFIED (mechanism) | "Priority ordering routes higher-ranked candidates first." |
| GAP-1 reduces attempts to first success (total-budget) | A=1 vs B=3 requests to first success (EPSS-only arm) | `tests/ablation.py` (GAP-1 v2) | `09_BENCHMARK_EVIDENCE.md:32-46` | MEASURED (best-case bound) | "With a total-budget protocol, usability scoring reaches first success earlier (upper-bound, n=12, label-correlated)." |
| GAP-1 independent win under fair per-visit cap | priority component (DUMB−PRIORITY-ONLY) = 0 | 4-agent fair ablation (30 seeds) | `fair_benchmark.py`, `03_TDE_EVIDENCE.md` B1 | MEASURED = 0 | "Under identical per-visit cap, prioritization alone did NOT reduce total attempts; it is necessary scaffolding, not an independent win." |
| GAP-1 observed success at attempt 1 | HIGH candidate selected, module printed VULNERABLE | T-DOCKER Stage B S1 (loopback) | `data/experiment_runs/.../emulator_access_s1.log` | VERIFIED but **stubbed assessor** | "In loopback observed validation the HIGH-ranked candidate succeeded first; assessor ranks were stub-provided (mechanism only)." |
| LLM-assessor accuracy on unseen CVEs | none | — | — | **UNVERIFIED** | PROHIBITED (C2). |

**Conclusion (GAP-1):** Demonstrated as a *mechanism* and as a *routing-efficiency
upper bound*; **not** an independently-measured win under fair cap, and LLM accuracy
is unvalidated. Register: **B1 (qualify-only)**.

---

## 7. GAP-2 TECHNICAL ANALYSIS

**Mechanism:** `EngineState.attempt_count` per candidate; `_evaluate` pivots when
`attempt_count >= max_attempts` (`engine.py:112`); `_pivot_node` resets counter and
advances (`:98`); COMPLETED when no index left. Bounded termination guaranteed by
the index progression.

**Evidence table (GAP-2):**

| Claim | Experiment | Result | Tier | Status |
|-------|-----------|--------|------|--------|
| Bounded retries / pivot on failure | loopback S2 | exactly 2 attempts, pivot, COMPLETED, no 3rd | Level 2 | VERIFIED |
| Pivot reduces wasted attempts (fair cap) | 4-agent ablation VAPT | T=2 +77 saved, T=5 +200 saved | Level 1 (fair) | VERIFIED (A2) |
| Pivot reduces wasted attempts (agnostic) | 4-agent ablation sparse | T=5 +175 saved | Level 1 (fair) | VERIFIED (A2) |
| No loop under threshold | T-BENCH-LOOP, fair_benchmark | loop_events=0 for pivot agents | Level 1 | VERIFIED |
| Multi-seed behaviour | fair benchmark 30 seeds × 4 caps × 6 families × 10 rankers | stable positive pivot component | Level 1 | VERIFIED (28,800 rows) |

**Confidence: Gap-2 is the defensible, proven contribution (A2).**

---

## 8. EXPERIMENT INVENTORY

| ID | Purpose | Baseline | Treatment | N / seeds | Result | Artifact | Tier | Limitations |
|----|---------|----------|-----------|-----------|--------|----------|------|------------|
| SMART vs DUMB (orig) | request economy | DUMB cap10 | SMART cap2 | 3 findings | 5 vs 21 req, 0 vs 2 loops | `09_BENCHMARK_EVIDENCE.md` | L1 (BIASED cap) | cap asymmetry → retiered |
| GAP-1 v1 ablation | scoring reroutes | no-scoring | scoring | 12 findings | A=1 vs B=5 req | `tests/gap1_ablation.py` | L1 | label-correlated best case |
| GAP-1 v2 ablation (EPSS-only) | routing efficiency | raw-EPSS | full SMART | 12 findings | A=1 vs B=3 to first success | `tests/ablation.py`, `data/ablation_epss_only.csv` | L1 | best-case bound |
| T-BENCH-LOOP | loop measured not asserted | — | — | — | loop_events instrumented | `tests/` | L1 | — |
| T-BENCH-VAR | multi-seed variance | — | — | 5 seeds | variance harness | `tests/` | L1 | planned gate; not in current 16 |
| Agnostic benchmark (orig) | domain independence | DUMB | SMART | 5 tasks | 8 vs 17 (BIASED) | `agnostic_benchmark.py` | L1 (BIASED) | cap asymmetry (Q5 FAIL) |
| **Fair 4-agent ablation** | **Gap-2 under fair cap** | DUMB/PIVOT-ONLY | PRIORITY-ONLY/SMART | 6 fam × 30 seed × 4 cap × 10 ranker | VAPT +77/+200, sparse +175 pivot comp | `fair_benchmark.py`, JSONL 28,800 rows | L1 (FAIR) | priority comp=0 |
| VAPT fair bench | Gap-2 on full corpus | same 4 agents | same | 12 CVE × 30 seed | T=2 +77, T=5 +200 | `fair_vapt_benchmark.py` | L1 (FAIR) | per-visit cap |
| T-DOCKER Stage B (loopback) | observed pivot/success | — | real subprocess | 2 scenarios × 1 run | S1 SUCCESS attempt1, S2 pivot@2 | `data/experiment_runs/20260825T*/*` | **L2** | stubbed assessor; loopback only |
| Docker Level-3 | container-isolated | — | — | — | NOT RUN (daemon down) | `T_DOCKER_EXPERIMENT_PROTOCOL.md` NO-GO | — | parked |

No Docker Level-3, no OpenAI live run in evidence (provider path hardened, `25e4137`).

---

## 9. DATASET INVENTORY

| Dataset | Location | Source | Records | Type | Used? | Notes |
|---------|----------|--------|---------|------|-------|-------|
| CISA KEV | `datasets/cisa_kev.json` | CISA (live fetch 2026-08-27) | 1,682 vulns | REAL EXTERNAL | pipeline only | prioritization source |
| EPSS bulk | `datasets/epss_scores.csv.gz` | FIRST.org API | 365,083 rows | REAL EXTERNAL | pipeline only | probability signal |
| EPSS corpus enrich | `datasets/epss_corpus_enrichment.json` | FIRST.org (12 CVEs) | 12 CVEs | REAL EXTERNAL | YES (VAPT bench) | probability per corpus CVE |
| PoC corpus labels | `data/poc_corpus/labels.json` | curated | 12 CVEs | CONTROLLED GROUND TRUTH | YES (sim) | outcome per CVE |
| PoC modules | `data/poc_corpus/*.py` (12) | synthetic stubs | 12 | SYNTHETIC STUB | sim + loopback | NOT real exploits (B.3 of protocol) |
| Agnostic tasks | `agnostic_benchmark.py` TASKS | synthetic | 5 | SYNTHETIC | YES | "maintenance tasks" domain |
| Synthetic families | `fair_benchmark.py:make_family` | seeded RNG | 6 regimes × 50 | SYNTHETIC | YES | fair ablation |

**Distinction:** only CISA/EPSS are real external data (used for *probability*, not
for success labels). Success labels are curated/controlled. Loopback used real
subprocess I/O, not labels.

---

## 10. EVIDENCE-TIER SYSTEM (final taxonomy)

| Level | Name | Ground truth | Status in repo |
|-------|------|--------------|----------------|
| **L1** | SIMULATION / controlled synthetic | labels / deterministic ground truth | ACHIEVED (benchmarks + ablations) |
| **L2** | LOOPBACK OBSERVED VALIDATION | real local subprocess I/O, emulator-corroborated | ACHIEVED (T-DOCKER Stage B, 127.0.0.1) |
| **L3** | CONTAINER-ISOLATED OBSERVED | Docker bridge, no egress | NOT ACHIEVED (daemon unavailable; NO-GO) |
| **L4** | BROADER REAL-WORLD | third-party/internet targets | OUT OF SCOPE |

Gap-2 highest level = L1 fair + L2 observed mechanism. Gap-1 highest = L2 mechanism
(stubbed assessor) + L1 bound. NO claim may cite L3/L4.

---

## 11. LOOPBACK / REAL OBSERVED AUDIT (explicit answer)

**Can the loopback result honestly be called a REAL OBSERVED RESULT? — YES, with
strict scope.** Evidence (`FINAL_EVIDENCE_AUDIT.md`, re-confirmed against on-disk
artifacts):
- Execution was a REAL subprocess (`core/executor.py:255` `subprocess.run`), not simulation.
- Outcome parsed from `proc.stdout/stderr/returncode` only; `labels.json` confined to
  `mode=="simulation"` (`executor.py:193-198`) — NOT in the danger path.
- Emulator access log independently corroborates (S1: 1×`/vuln`; S2: exactly 2×`/fail`).
- `metadata.json` records `container_isolation_in_effect: false`, `mode: loopback`.
- **Scope limits:** loopback (127.0.0.1), benign GET probes, **stubbed assessor**
  (ranks A→HIGH etc. provided by harness, not the LLM), n=2 scenarios, single run.
- Therefore: L2 CONTROLLED LOOPBACK, **NOT** L3 container-isolated, **NOT** real-world.
- The thesis must use the exact wording in `FINAL_EVIDENCE_AUDIT.md` §5 and never say
  "Docker-isolated" or "real-world validated".

---

## 12. SAFETY & EXECUTION ANALYSIS

| Mode | Behaviour | Evidence |
|------|-----------|----------|
| simulation (default) | outcome from label; no network | `executor.py:42` |
| real (default) | connectivity check ONLY; reports SKIPPED, sends NO payload | `executor.py:220-229` (verified in audit) |
| danger_mode (opt-in) | subprocess exploit; **fail-closed allowlist** refuses non-authorized target | `executor.py:236-245` (verified: empty allowlist → FAIL_NO_TARGET) |

**Current capability:** cannot target a URL/IP/network live target without code
changes (corpus modules hardcode 127.0.0.1; `target_allowlist` guard required — see
`T_DOCKER_EXPERIMENT_PROTOCOL.md` Part I). No offensive instruction provided; this is
an architecture/evidence audit.

---

## 13. TESTING & SOFTWARE QUALITY

| Suite | Count | File | Status |
|-------|-------|------|--------|
| **Original VAPT (TRACK0)** | **39 passed** | `tests/` | VERIFIED 2026-08-31 |
| **Generalized engine (TRACK1)** | **16 passed** (12 engine + 4 fair) | `decision_engine/tests/` | VERIFIED 2026-08-31 |
| Coverage | not measured (no pytest-cov in evidence) | — | N/A |
| Static | Python 3.10 venv, deps pinned (`requirements.txt`, `9b0fe96` T-REQPIN) | — | reproducible |

Numbers kept separate per governance. Both green; `core/` untouched by Stage-1 work.

---

## 14. GIT / REPRODUCIBILITY HISTORY (timeline)

| Date | Commit | Change | Research significance |
|------|--------|--------|----------------------|
| 2026-08-21 | `31ccd06` | baseline verified framework | audit baseline |
| 2026-08-24 | `9b67dac` | T-BENCH-LOOP (loops MEASURED) | loop evidence honest |
| 2026-08-24 | `5ba1e10`/`eda98c3` | GAP-1 v1/v2 ablation | GAP-1 proof-of-mechanism (bound) |
| 2026-08-25 | `6330a29` | T-DOCKER Stage B loopback | L2 observed pivot/success |
| 2026-08-25 | `943f8c9` | FINAL_EVIDENCE_AUDIT | L1/L2 taxonomy established |
| 2026-08-27 | `97eef40` | STAGE1 generalize engine + datasets | domain-independent core |
| 2026-08-27 | `1718016` | T-DE-TESTS (12) | engine regression |
| 2026-08-27 | `8e8a2b7` | T-DE-BOUNDARY review | arch PASS, bench Q5 FAIL |
| 2026-08-27 | `7001c61` | **T-DE-BENCH-IMPL fair 4-agent ablation** | Gap-2 fair-validated |
| 2026-08-27 | `5e33e74`/`eee1781`/`69dbb4e` | T-DE-EVIDENCE + reviews | A/B/C gate |
| 2026-08-31 | `e4d9f7d`/`4e09c74`/`e59e308` | **R1 / R2 / R3** | related work, novelty, claim register |
| 2026-08-31 | `50900c6`/`b1f8b42` | **R4 / R5-R7** | challenge + GO/NO-GO |

Reproduce: `source venv/bin/activate && pip install -r requirements.txt && python -m pytest tests/ decision_engine/tests/ && python decision_engine/benchmarks/fair_vapt_benchmark.py --seeds 30 --caps 1 2 3 5`

---

## 15. WHAT HAS BEEN COMPLETED (status table)

| Task / Component | Status | Evidence | Commit |
|------------------|--------|----------|--------|
| Original VAPT prototype | DONE / VERIFIED | 39 tests | frozen |
| Generalized engine (domain-free) | DONE / VERIFIED | 16 tests; import audit | `97eef40` |
| Gap-2 fair benchmark | DONE / VERIFIED | +77/+200/+175 | `7001c61` |
| Gap-2 observed (loopback) | DONE / VERIFIED (L2, stubbed assessor) | `data/experiment_runs/` | `6330a29` |
| Checkpoint/resume | DONE / VERIFIED | `test_checkpoint.py` | `f1561be` |
| Fail-closed safety | DONE / VERIFIED | `test_executor_allowlist.py` | `e5d31ba` |
| Datasets (CISA/EPSS) | DONE / VERIFIED | `datasets/` | `97eef40` |
| R1 related work | DONE / VERIFIED | `R1_RELATED_WORK.md` | `e4d9f7d` |
| R2 novelty matrix | DONE / VERIFIED | `R2_NOVELTY_MATRIX.md` | `4e09c74` |
| R3 claim register | DONE / VERIFIED | `R3_CLAIM_REGISTER.md` | `e59e308` |
| R4 challenge | DONE | `R4_challenge.md` | `50900c6` |
| R5-R7 GO/NO-GO | DONE / VERIFIED | `12_GO_NO_GO.md` | `b1f8b42` |

---

## 16. WHAT IS PENDING

**A. Required for the research paper:** A7 thesis writing (scoped to register). No
further experiments strictly required for a mechanism paper.

**B. Recommended for stronger evidence:**
- Total-budget Gap-1 experiment (would let B1→A). Effort: low (modify fair_benchmark
  cap semantics). Changes claims (upgrades B1). Not required for submission.
- Multi-run loopback variance (currently single run). Effort: low.

**C. Required for full VAPT platform (TRACK B / Stage 2):** discovery/recon, URL/IP
ingestion, Nmap/Nuclei adapters, reporting UI, Level-3 Docker lab. NOT research-claim
blocking.

**D. Optional engineering:** richer executor parsing, CI, broader UI.

**E. Future research:** LLM-assessor calibration on unseen CVEs; broader domain sweep
(>1 synthetic family); RL-based threshold tuning.

**F. Blocked by environment:** Level-3 Docker (daemon unavailable at audit time) —
optional, parked.

---

## 17. FULL VAPT PLATFORM ROADMAP (CURRENT vs FUTURE)

| Capability | Current | Dependencies | Research value | Product value |
|------------|---------|--------------|---------------|---------------|
| Decision engine + pivot | YES (engine) | — | core | core |
| VAPT corpus adapter | YES | — | demo | demo |
| URL/IP/network ingestion | NO | TRACK B B4 | low | high |
| Recon/discovery | NO | B3 | low | high |
| Nmap/Nuclei | NO | B5 | low | high |
| Reporting/UI | partial (`app.py`, `report.py`) | — | low | med |
| Level-3 lab | NO (parked) | Docker daemon | med (evidence) | med |
| Multi-domain orchestration | NO | B2 | future | high |

Future capabilities MUST NOT appear as existing features in the paper.

---

## 18. RELATED WORK / COMPETITOR ANALYSIS

From `R1_RELATED_WORK.md` (dated Strix snapshot v1.5.3 @ 2026-08-10):
- **Strix** — product-grade multi-agent pentester; no public paper; we do NOT compare
  numbers (C4 prohibits). Relationship: product vs our mechanism.
- **PentestGPT (USENIX'24)** — 3 LLM modules; no bounded per-target pivot counter.
- **HackSynth / VulnBot / PentestAgent / xOffense / RapidPen** — named, not deep-read
  (titles only). Overlap: autonomous pentest; differentiation not deeply established.
- **Reflexion / ReAct** — generic self-reflection; no hard attempt cap.
- **PIVOT (arXiv:2605.11225)** — trajectory refinement, not attempt-capped.
- GAP-1 scoring: PentestGPT self-scoring; action-value heads in literature.

**Honest statement:** "Not established from repository evidence" for deep novelty
differentiation vs the named-but-unread agents — R1 only title-inspected them.

---

## 19. NOVELTY ANALYSIS

**GAP-1 (pre-execution prioritization):**
- Prior work: PentestGPT self-scoring, action-value heads, ReAct scoring.
- Equivalent feature? Partial (others score; we add EPSS×usability formula).
- Evidence: mechanism + routing bound only; accuracy unvalidated.
- Novelty risk: MODERATE — scoring is common; our fairness discipline is the differentiator.
- Assessment: **contribution is the fair, ablation-isolated evaluation, not the scorer itself.**

**GAP-2 (bounded failure-threshold pivot):**
- Prior work: Reflexion (reflection, no hard cap); PIVOT (refinement, not capped);
  PentestGPT (LLM memory, no counter).
- Equivalent feature? Not found in inspected material (bounded per-candidate counter +
  threshold pivot + fair-cap ablation). NOTE: "not found" ≠ "proven not to exist".
- Evidence: fair L1 + L2 observed mechanism.
- Novelty risk: LOW-MODERATE — mechanism is small/deterministic; must be framed as a
  *reproducible, fair-validated* contribution, not a grand architectural claim.
- Assessment: **defensible, but scope it to "bounded pivot under fair evaluation".**

**Generalized engine:** domain-independence is genuine (verified) but architecturally
incremental (adapter pattern). Novelty = demonstration + honest evidence discipline.

---

## 20. RESEARCH QUESTIONS / HYPOTHESES

**RQ1:** Does pre-execution candidate quality assessment improve selection efficiency?
- Hypothesis H1: priority ordering reaches first success earlier under a total budget.
- Experiment: `tests/ablation.py` (A=1 vs B=3) + fair benchmark (priority comp=0 under
  per-visit cap). Evidence: PARTIAL (bound only). Gap: total-budget fair protocol.

**RQ2:** Does explicit failure tracking + threshold pivot reduce repeated non-productive
attempts?
- Hypothesis H2: per-candidate counter + pivot guarantees bounded termination and cuts
  wasted attempts vs no-pivot baseline.
- Experiment: fair 4-agent ablation (VAPT +77/+200; sparse +175) + loopback S2 (pivot@2,
  no loop). Evidence: STRONG (A2). Confidence: high.

**RQ3:** Can the mechanisms operate without VAPT-specific logic via an adapter?
- Hypothesis H3: engine imports only core.*; VAPT isolated in adapter.
- Experiment: import audit (T-DE-BOUNDARY Q1–Q4 PASS) + agnostic benchmark.
- Evidence: STRONG (architectural). Caveat: experimental cross-domain = Gap-2 only (B2).

**RQ4:** Trade-offs of LLM-based pre-execution assessment?
- Evidence: UNVALIDATED (assessor stubbed in observed tier; offline deterministic only).
- Gap: real LLM-assessor calibration study needed.

---

## 21. RESULTS SECTION (paper-ready, strongest results)

1. **Gap-2 pivot saves attempts under fair cap (VAPT corpus, 12 CVEs, 30 seeds):**
   pivot component (PRIORITY-ONLY − SMART) = +77 requests at T=2, +200 at T=5.
   Baseline = no-pivot (DUMB/PRIORITY-ONLY cycle to budget). Interpretation: bounded
   abandonment of failing candidates is the separable mechanism. Limitation: per-visit
   cap; priority component = 0.
2. **Gap-2 pivot saves attempts (agnostic sparse family, 50 candidates, 30 seeds):**
   +175 at T=5. Interpretation: mechanism is not CVE-specific. Limitation: one synthetic
   family only (B2).
3. **Loopback observed pivot (L2):** candidate attempted exactly 2×, pivot logged,
   COMPLETED, no 3rd attempt. Interpretation: pivot responds to real observed failure.
   Limitation: stubbed assessor, loopback, n=2, single run.
4. **Loopback observed success (L2):** HIGH-ranked candidate succeeded at attempt 1
   (module token + emulator log). Limitation: ranks stub-provided; mechanism only.
5. **No speed claim:** `09_BENCHMARK_EVIDENCE.md` time_saved_s = −8.5s (LLM latency).
   **Never claim "faster".**

---

## 22. LIMITATIONS (thesis-ready)

1. Loopback not container-isolated (L2, not L3).
2. Stubbed assessor in observed tier (mechanism only, not LLM accuracy).
3. Small observed n=2, single run (no variance).
4. Behavioural-stub corpus (not real exploits).
5. Gap-1 priority component = 0 under fair per-visit cap (not an independent win).
6. LLM-assessor accuracy on unseen CVEs unvalidated (C2).
7. Cross-domain experimental evidence = Gap-2 only, one synthetic family (B2).
8. Benchmark structural bias history (5-vs-21 / 8-vs-17 retiered; fair bench replaces).
9. No real-world / multi-target validation (C3/C4/C6).
10. Negative time_saved (no speed claim).

---

## 23. FINAL CLAIM REGISTER (authoritative — mirrors R3)

**A — MAY CLAIM:** A1 domain-independent engine; A2 Gap-2 fair-validated pivot;
A3 safe bounds + fail-closed danger; A4 checkpoint/resume; A5 VAPT-as-adapter;
A6 priority formula; A7 offline/optional-LLM assessor; A8 EPSS pipeline; A9 regression nets.

**B — MUST QUALIFY:** B1 Gap-1 priority (component=0 under fair cap; needs total-budget
to upgrade); B2 cross-domain (Gap-2 only); B3 LLM assessor (offline/local only);
B4 SMART/DUMB (use fair numbers only, never biased 5-vs-21/8-vs-17).

**C — PROHIBITED:** C1 universal/provably-general independence; C2 LLM accuracy on
unseen CVEs; C3 real-world superiority; C4 "better than all" systems; C5 Level-3 Docker;
C6 live multi-target validation.

---

## 24. PROPOSED PAPER STRUCTURE (evidence mapping)

1. **Title options:** "A Domain-Independent Decision & Pivot Engine with Fair-Validated
   Failure-Driven Pivoting" / "Bounded Pivoting for Autonomous Action Selection under
   Repeated Failure".
2. **Abstract:** mechanism + Gap-2 fair result + honesty about Gap-1/L2 limits.
3. **Introduction:** autonomous agents loop on failure; need bounded pivot.
4. **Problem statement:** Type-B planning failure (Deng 2024).
5. **Related work:** Strix/PentestGPT/Reflexion/ReAct/PIVOT (R1).
6. **Research gaps:** Gap-1, Gap-2 as defined.
7. **Proposed approach:** `decision_engine/` abstraction (§3).
8. **Architecture:** engine graph, assessor, executor, adapter (§4).
9. **Gap-1:** mechanism + bound + caveat (§6).
10. **Gap-2:** counter + threshold + fair ablation (§7). **Strongest chapter.**
11. **Generalized engine:** adapter pattern, import audit.
12. **Methodology:** fair 4-agent ablation, identical cap, ≥30 seeds, CI.
13. **Datasets:** CISA/EPSS/labels (§9).
14. **Results:** §21.
15. **Discussion:** why priority component=0; fairness discipline as contribution.
16. **Threats to validity:** stubbed assessor, L2 not L3, n=2.
17. **Limitations:** §22.
18. **Future work:** total-budget Gap-1, Level-3 lab, LLM calibration, Stage-2 platform.
19. **Conclusion:** bounded pivot is a real, fair-validated, domain-free mechanism.

**Figures:** architecture; end-to-end; Gap-2 state/pivot; fair-ablation decomposition.
**Tables:** contributions; datasets; benchmark (A2); related-work; novelty; limitations;
claim register.

---

## 25. PAPER-WORTHINESS ASSESSMENT

**Rating: CREDIBLE WITH LIMITATIONS.** Reason: clear problem significance (loop
failure is real), a genuinely domain-independent engine, and a *fair, ablation-isolated*
Gap-2 result with L2 observed corroboration — but Gap-1 is unproven as an independent
win, observed tier is small/stubbed/loopback, and cross-domain evidence is thin.
Publication strength would most increase via: (a) total-budget Gap-1 experiment
(B1→A), (b) multi-run + multi-domain ablation, (c) Level-3 lab repetition. None are
required for an M.Tech thesis framed as a mechanism paper. **No publication guarantee.**

---

## 26. WHAT SHOULD NOT BE BUILT NOW (scope creep)

Defer: full Strix-like feature set, auto-fix, CI/CD, arbitrary internet targeting,
broad cloud integration, heavy UI. These do not strengthen the core (Gap-2) contribution
and risk overclaim. Stage-2 platform is a separate Track B effort.

---

## 27. FINAL PROJECT STATUS

- **PROJECT:** M.Tech research prototype — generalized autonomous decision & pivot engine.
- **CURRENT PHASE:** Research positioning COMPLETE; A7 thesis writing pending.
- **CURRENT ARCHITECTURE:** `decision_engine/` (domain-free) + `vapt_adapter.py` (VAPT).
- **ORIGINAL VAPT PROTOTYPE:** frozen, 39/39, verified.
- **GENERALIZED ENGINE:** 16/16, domain-independent verified.
- **TEST STATUS:** both suites green.
- **EXPERIMENT STATUS:** Gap-2 fair-validated (L1); Gap-2 L2 observed; Gap-1 bound only.
- **OBSERVED VALIDATION:** L2 loopback (stubbed assessor, n=2).
- **DOCKER STATUS:** Level-3 NOT achieved (parked).
- **RELATED WORK:** R1 done (Strix v1.5.3 snapshot).
- **NOVELTY STATUS:** Gap-2 defensible; Gap-1/LLM unvalidated.
- **PAPER READINESS:** GO as mechanism paper; NO-GO as platform/real-world claim.
- **FULL VAPT PLATFORM:** NOT STARTED (Track B).
- **IMPLEMENTATION FREEZE:** `core/` frozen; `decision_engine/` feature-complete for claims.

---

## 28. FINAL ROADMAP (from today)

- **IMMEDIATE:** Write thesis (A7) against R3 register. (No implementation.)
- **NEXT (optional, strengthens evidence):** total-budget Gap-1 experiment (B1→A);
  multi-run loopback variance.
- **LATER (optional):** Level-3 Docker lab repetition.
- **OPTIONAL:** LLM-assessor calibration study.
- **FUTURE (Track B, post-thesis):** Stage-2 VAPT platform.

No evidence gap *blocks* the mechanism paper. The only gap that would *upgrade* a claim
is the total-budget Gap-1 experiment (currently B1).

---

## 29. STOP / AUTHORITY

This report is READ-ONLY. No source modified, no commit made (per instructions, commit
only if explicitly authorized). It supersedes prior handover/audit docs as the current
authority source for thesis writing. Prior reports (`FINAL_PROJECT_HANDOVER_REPORT.md`,
`FINAL_EVIDENCE_AUDIT.md`, etc.) are retained for historical traceability.

*End of MASTER_RESEARCH_PROJECT_REPORT.*
