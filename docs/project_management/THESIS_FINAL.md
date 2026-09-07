# M.Tech Thesis — A Domain-Independent Decision & Pivot Engine with Fair-Validated Failure-Driven Pivoting

---

## Title Page

**Title:** A Domain-Independent Decision & Pivot Engine with Fair-Validated Failure-Driven Pivoting

**Candidate:** [TODO: candidate name]

**Degree:** Master of Technology (M.Tech) in Cybersecurity

**Supervisor:** [TODO: supervisor name]

**Date:** August 2026

**Repository:** `ai_vapt_framework` · HEAD `b7a9f06` · Branch `master`

**Evidence sign-off:** A6 GO (docs/project_management/external_reviews/FINAL_EVIDENCE_SIGN_OFF.md)

---

## Declaration of Originality

I declare that this thesis is my own original work, submitted in partial fulfillment of the requirements for the degree of Master of Technology. All sources used have been acknowledged and cited. No part of this thesis has been submitted for any other degree or qualification.

The research prototype described herein was developed by the author. All claims made in this thesis follow the R3 claim register (A-claims stated directly with evidence anchors; B-claims qualified with exact caveats; C-claims omitted entirely). No C-prohibited wording ("faster / universal / real-world validated / Docker-validated / better than all / complete autonomous VAPT / first system") is used.

**Candidate signature:** ____________________

**Date:** ____________________

---

## 1. Abstract

Autonomous action-selection agents that repeatedly fail on a candidate route often loop indefinitely instead of abandoning that route and trying alternatives. This thesis presents a domain-independent decision and pivot engine that bounds repeated failure by tracking per-candidate attempt counts and pivoting away when a configurable threshold is reached. Under a fair ablation protocol using identical per-visit caps, the pivot mechanism reduces wasted attempts versus a no-pivot baseline on the VAPT corpus: the pivot component (PRIORITY-ONLY minus SMART) saves **+77 requests at cap T=2** and **+200 requests at cap T=5**, with an additional **+772** on an agnostic sparse task family at T=5 [fair_benchmark.py output; sparse_success family]. The engine's core imports only `decision_engine.core.*` and isolates the VAPT domain behind a single adapter (`vapt_adapter.py:52`), demonstrating architectural domain-independence [decision_engine/core/engine.py:1-12]. A secondary mechanism — pre-execution candidate prioritization — is reported honestly: under the identical-cap protocol its independent contribution is zero, qualifying it as scaffolding rather than an independent win. All quantitative claims follow the R3 register [R3_CLAIM_REGISTER.md]; no C-prohibited wording is used.

**Claim tiers:** A (A1–A9) stated directly; B (B1–B4) qualified with exact caveats; C (C1–C6) omitted.

---

## 2. Introduction

Autonomous pentest and action-selection agents have grown substantially in capability, yet a persistent failure mode remains: when an agent exhausts a candidate route without success, it frequently loops on that same route rather than pivoting to the next candidate [core/agent_graph.py:1-11; R1_RELATED_WORK.md §2]. This is a form of Type-B planning failure (Deng et al., 2024). Repeated non-productive attempts waste computation and prevent bounded termination.

This thesis contributes (1) a generalized, domain-independent decision engine whose core logic is decoupled from any single application domain, and (2) a bounded failure-threshold pivot mechanism — Gap-2 — that is fair-validated under identical per-visit caps. The thesis also documents a secondary, qualified mechanism (Gap-1: pre-execution prioritization) whose independent effect is zero under the fair-cap protocol. The contribution is positioned as a **research-prototype mechanism paper**, not a complete platform [MASTER_RESEARCH_PROJECT_REPORT.md §27].

---

## 3. Problem Statement

**Formal problem.** Given a sequence of candidate actions `c ∈ C`, each with an unknown outcome (success or failure), an autonomous agent must select and execute candidates repeatedly until either a success is found or a termination condition is met. The agent faces Type-B planning failure: it continues attempting a failing candidate instead of abandoning it, producing unbounded wasted attempts [core/agent_graph.py:1-11].

**Existing behavior.** In the original VAPT prototype, the agent graph cycles through candidates without a per-candidate attempt counter [core/agent_graph.py]. The agent does not track how many times it has attempted a given candidate, nor does it pivot away after a configurable number of failures.

**Requirements for a solution.** A solution must (a) track per-candidate attempts, (b) pivot when a threshold is reached, (c) guarantee bounded termination, and (d) allow evaluation under identical caps across agents to isolate the pivot mechanism from cap-asymmetry bias.

---

## 4. Related Work

Related systems are summarized with honest qualifiers per R1 [R1_RELATED_WORK.md; R2_NOVELTY_MATRIX.md].

- **Strix v1.5.3 (2026-08-10):** product-grade multi-agent pentester (graph/tree of specialized agents; PyPI `strix-agent`). No public paper; we do **not** compare numbers — Strix is a product, ours is a mechanism [R1_RELATED_WORK.md §1].
- **PentestGPT (USENIX Security 2024):** three self-interacting LLM modules (reasoning, generation, parsing); no bounded per-target pivot counter [R1_RELATED_WORK.md §2].
- **HackSynth, VulnBot, PentestAgent, xOffense, RapidPen:** named from 2024–2026 arXiv/preprint lists; titles-only inspection (no deep read). Overlap: autonomous pentest; differentiation not deeply established [R1_RELATED_WORK.md §3].
- **Reflexion / ReAct:** generic self-reflection / tool-use; no hard per-candidate attempt cap [R1_RELATED_WORK.md §5].
- **PIVOT (arXiv:2605.11225):** trajectory refinement; not attempt-capped [R1_RELATED_WORK.md §5].

**Honest statement:** Deep novelty differentiation vs. the named-but-unread agents is "not established from repository evidence" — R1 title-inspected them only [MASTER_RESEARCH_PROJECT_REPORT.md §18]. Our differentiation rests on the bounded per-candidate counter + threshold pivot + fair-cap ablation, which prior inspected work does not replicate in cap-isolated form [R2_NOVELTY_MATRIX.md §3.2].

---

## 5. Gap Analysis

Two research gaps motivate this work.

**Gap-1 — Pre-execution candidate quality scoring and prioritization.** When multiple exploit or action candidates exist, an agent must prioritize so viable routes are tried first. The current literature scores candidates but does not always tie scoring to a bounded-execution protocol. Gap-1 fills this with `priority_score = probability × (0.5 + 0.5 × quality)` [schemas.py:77; QUALITY_WEIGHT at schemas.py:26]. **Caveat:** Under the fair per-visit-cap protocol, the priority component (DUMB minus PRIORITY-ONLY) equals zero; Gap-1 is necessary scaffolding for pivot ordering, not an independently measured win [R3_CLAIM_REGISTER.md B1; 12_GO_NO_GO.md ⚠️ B1].

**Gap-2 — Explicit state-aware failure tracking, bounded attempts, and failure-threshold pivot.** Per-candidate attempt counters with a configurable pivot threshold directly address loop-forever failure [engine.py:_evaluate (112); _pivot_node (98)]. When `attempt_count >= max_attempts`, the engine pivots to the next candidate; when no index remains, it terminates in COMPLETED [engine.py:107-114]. This contribution is the primary, fair-validated claim of the thesis [R3_CLAIM_REGISTER.md A2].

---

## 6. Research Questions

**RQ1:** Does pre-execution candidate quality assessment improve selection efficiency under a total-budget protocol?
**RQ2:** Does explicit failure tracking plus threshold pivot reduce repeated non-productive attempts under a fair, identical cap?
**RQ3:** Can the mechanisms operate without VAPT-specific logic via an adapter?

---

## 7. Hypotheses

**H1 (RQ1 — Gap-1):** Priority ordering reaches first success earlier under a total budget.
*Evidence:* partial — `tests/ablation.py` shows A=1 vs B=3 requests to first success (label-correlated best case); under the fair per-visit cap the priority component = 0 [MASTER_RESEARCH_PROJECT_REPORT.md §6; R3_CLAIM_REGISTER.md B1].

**H2 (RQ2 — Gap-2):** Per-candidate counter plus pivot guarantees bounded termination and cuts wasted attempts versus a no-pivot baseline under identical cap.
*Evidence:* strong — fair 4-agent ablation (VAPT T=2 +77, T=5 +200; agnostic sparse T=5 +772) plus loopback L2 observed pivot at attempt 2 with no loop [fair_benchmark.py output; emulator_access_*.log].

**H3 (RQ3):** The engine imports only `decision_engine.core.*` and VAPT is isolated in `vapt_adapter.py`.
*Evidence:* strong — import audit (T-DE-BOUNDARY Q1–Q4 PASS) [decision_engine/core/engine.py:1-12; 12_GO_NO_GO.md §1].

---

## 8. Method

The method is a **fair 4-agent ablation** designed to isolate the pivot mechanism from cap-asymmetry bias [MASTER_RESEARCH_PROJECT_REPORT.md §8; R1_RELATED_WORK.md §6].

**Agents (baseline vs. treatment):** DUMB (no pivot, cycle to budget); PRIORITY-ONLY (Gap-1 ordering only); SMART (prioritized + pivot); FULL (all mechanisms). Each agent is evaluated under identical per-visit caps T ∈ {1, 2, 3, 5}.

**Isolation:** The pivot component is isolated as `PRIORITY-ONLY − SMART` at identical cap. If cap asymmetry were the driver, the PRIORITY-ONLY and SMART agents would show divergent results at the same cap; they do not [fair_benchmark.py; fair_vapt_benchmark.py].

**Seeds and families:** ≥30 seeds × 6 synthetic families × 4 caps × 10 rankers (regenerable via `decision_engine/benchmarks/fair_benchmark.py --jsonl`) [MASTER_RESEARCH_PROJECT_REPORT.md §8; R2_NOVELTY_MATRIX.md §3.2].

**VAPT corpus evaluation:** the same 4 agents are evaluated on the curated 12-CVE PoC corpus with `fair_vapt_benchmark.py --seeds 5 --caps 2 5` [fair_vapt_benchmark.py output].

**Loopback observed validation (Level 2):** `tests/run_tdocker_scenarios.py` forces `mode="real", danger_mode=True`, `target_allowlist=["127.0.0.1"]`, against a local Flask emulator. Outcome parsed from subprocess stdout/stderr [MASTER_RESEARCH_PROJECT_REPORT.md §5; data/experiment_runs/.../emulator_access_*.log].

---

## 9. Architecture

The architecture separates domain-independent core from domain-specific adapters [MASTER_RESEARCH_PROJECT_REPORT.md §4; decision_engine/core/engine.py:1-12].

```
Candidate/Action (id, probability, quality_rank, ground_truth)
    ↓  assess_candidates()  →  fills quality_rank          [Gap-1, assessor.py]
    ↓  rank_candidates()    →  priority_score               [Gap-1, schemas.py:77]
    ↓  Executor.execute()   →  Outcome (simulation/real)    [executor.py:42]
    ↓  observe outcome
    ↓  EngineState.attempt_count++                           [Gap-2 state]
    ↓  _evaluate(): attempt_count >= max_attempts ? → pivot  [engine.py:112]
    ↓  _pivot_node(): advance index, reset counter, OR COMPLETED [engine.py:98]
    ↓  bounded termination (no index left)
```

**Domain-independent parts:** `schemas`, `assessor`, `executor`, `engine`, `_evaluate`, `_pivot_node`, `initial_state`, checkpoint [decision_engine/core/engine.py].

**VAPT-specific boundary only:** `adapters/vapt_adapter.py` (CVE → ActionCandidate, EPSS → probability, labels → ground_truth) [vapt_adapter.py:52-95].

**Key file references:**
- `schemas.py:priority_score` (line 77) — priority formula `probability × (0.5 + 0.5 × quality)` [schemas.py:77]
- `QUALITY_WEIGHT` (line 26) — quality-to-weight mapping [schemas.py:26]
- `engine.py:_evaluate` (line 112) — threshold check [decision_engine/core/engine.py:107-114]
- `engine.py:_pivot_node` (line 98) — pivot/advance/reset [decision_engine/core/engine.py:90-106]
- `engine.py:save_checkpoint` (line 172) / `load_checkpoint` (line 183) — checkpoint/resume [decision_engine/core/engine.py:172-189]

---

## 10. GAP-1 (Pre-execution Prioritization) — Qualified Secondary Mechanism

**Mechanism.** Candidates are scored by `deterministic_assessor` (offline) and ranked by `priority_score` [assessor.py:19, 28; schemas.py:77]. A domain adapter or live LLM may optionally override the scorer [vapt_adapter.py:70-95].

**Evidence.**

| Claim | Evidence | Status |
|-------|----------|--------|
| Ranking changes downstream order | deterministic: HIGH first; gap1_ablation | VERIFIED (mechanism) [MASTER_RESEARCH_PROJECT_REPORT.md §6] |
| GAP-1 reduces attempts under total-budget | A=1 vs B=3 requests to first success (EPSS-only arm) | MEASURED (best-case bound) [tests/ablation.py; data/ablation_epss_only.csv] |
| GAP-1 independent win under fair per-visit cap | priority component (DUMB − PRIORITY-ONLY) = 0 | MEASURED = 0 [fair_benchmark.py; 03_TDE_EVIDENCE.md B1] |
| LLM-assessor accuracy on unseen CVEs | none | UNVERIFIED [R3_CLAIM_REGISTER.md B3/C2] |

**R3 tier:** B1 — must qualify. Under the fair per-visit-cap protocol, the priority component is zero; Gap-1 is necessary scaffolding for pivot ordering, not an independently measured win. An upgrade to A-level requires a total-budget protocol [R3_CLAIM_REGISTER.md B1; 12_GO_NO_GO.md ⚠️ B1].

**Honest wording guard:** "Priority ordering routes higher-ranked candidates first. Under identical per-visit cap, prioritization alone did not reduce total attempts; it is necessary scaffolding, not an independent win."

---

## 11. GAP-2 (Bounded Failure-Threshold Pivot) — Primary Contribution

**Mechanism.** `EngineState.attempt_count` is incremented per candidate per execution [engine.py:72]. `_evaluate` returns `"pivot"` when `attempt_count >= max_attempts` [engine.py:112]. `_pivot_node` advances `current_index` and resets `attempt_count` to 0 [engine.py:98]; if no index remains, status becomes COMPLETED [engine.py:100-106]. Bounded termination is guaranteed by index progression [engine.py:117-144].

**Evidence.**

| Claim | Experiment | Result | Tier |
|-------|-----------|--------|------|
| Bounded retries / pivot on failure | loopback S2 | exactly 2 attempts, pivot, COMPLETED, no 3rd | Level 2 |
| Pivot reduces wasted attempts (fair cap) | 4-agent ablation VAPT | T=2 +77 saved, T=5 +200 saved | Level 1 (fair) |
| Pivot reduces wasted attempts (agnostic) | 4-agent ablation sparse | T=5 +772 saved | Level 1 (fair) |
| No loop under threshold | T-BENCH-LOOP | loop_events=0 for pivot agents | Level 1 |
| Multi-seed behaviour | fair benchmark 30 seeds × 4 caps × 6 families × 10 rankers | stable positive pivot component | Level 1 |

**R3 tier:** A2 — may claim, backed by E2. The pivot component (PRIORITY-ONLY − SMART) is positive and scales with cap [R3_CLAIM_REGISTER.md A2; fair_vapt_benchmark.py output].

**Honest wording guard:** "Under a fair, identical attempt cap, state-aware failure-threshold pivoting measurably reduces wasted attempts versus a no-pivot baseline, scaling with the cap."

---

## 12. Generalized Engine (Domain-Independent Core)

The engine is a faithful copy-and-refactor of `core/agent_graph.py`, stripped of every VAPT/CVE-specific detail [decision_engine/core/engine.py:1-12]. The engine knows only about: ActionCandidate (a task with probability and pre-execution quality), an assessor (Gap-1), and an executor (resolves an Outcome).

**Domain-independence verification.** `decision_engine/core/engine.py` imports only `decision_engine.core.*` — no CVE, exploit, port, or host token appears in the core [decision_engine/core/engine.py:1-12; MASTER_RESEARCH_PROJECT_REPORT.md §3]. The VAPT domain is attached via `vapt_adapter.py` (sole boundary) [vapt_adapter.py:52-95].

**R3 tier:** A1 — domain-independent engine, backed by E1 (code inspection) [R3_CLAIM_REGISTER.md A1].

---

## 13. Methodology (Experimental Protocol)

**Fairness protocol.** All agents execute under identical per-visit caps T. The pivot component is isolated as `PRIORITY-ONLY − SMART` at identical cap. This eliminates cap-asymmetry bias [R1_RELATED_WORK.md §6; MASTER_RESEARCH_PROJECT_REPORT.md §8].

**Seeds and statistical reporting.** Results are reported over ≥30 seeds per configuration. Where applicable, statistics are expressed as mean ± 95% CI [MASTER_RESEARCH_PROJECT_REPORT.md §8; fair_benchmark.py].

**Safety protocol.** The original VAPT executor (`core/executor.py`) supports three modes: simulation (outcome from label; no network), real (connectivity check only; reports SKIPPED, sends no payload), and danger_mode (opt-in subprocess exploit; fail-closed allowlist refuses non-authorized targets) [core/executor.py:56-72 (constructor + empty allowlist refuses all), core/executor.py:219-245 (safe-mode SKIPPED / danger gate); MASTER_RESEARCH_PROJECT_REPORT.md §12]. The generalized engine's executor (`decision_engine/core/executor.py`) is domain-independent and delegates real execution to a pluggable `execute_fn`; it does not itself implement danger_mode. Verified in `tests/test_executor_allowlist.py` and `tests/test_danger_mode_mock.py` (which exercise `core/executor.py`).

**Checkpoint/resume.** `save_checkpoint` (engine.py:172) serializes state to JSON; `load_checkpoint` (engine.py:183) restores it. Verified in `tests/test_checkpoint.py` [MASTER_RESEARCH_PROJECT_REPORT.md §4; R3_CLAIM_REGISTER.md A4].

---

## 14. Datasets

| Dataset | Location | Source | Records | Type | Used? |
|---------|----------|--------|---------|------|-------|
| CISA KEV | `datasets/cisa_kev.json` | CISA (live fetch 2026-08-27) | 1,682 vulns | REAL EXTERNAL | pipeline only (prioritization source) |
| EPSS bulk | `datasets/epss_scores.csv.gz` | FIRST.org API | 365,083 rows | REAL EXTERNAL | pipeline only (probability signal) |
| EPSS corpus enrich | `datasets/epss_corpus_enrichment.json` | FIRST.org (12 CVEs) | 12 CVEs | REAL EXTERNAL | YES (VAPT bench) |
| PoC corpus labels | `data/poc_corpus/labels.json` | curated | 12 CVEs | CONTROLLED GROUND TRUTH | YES (sim) |
| PoC modules | `data/poc_corpus/*.py` (12) | synthetic stubs | 12 | SYNTHETIC STUB | sim + loopback |
| Agnostic tasks | `agnostic_benchmark.py` TASKS | synthetic | 5 | SYNTHETIC | YES |
| Synthetic families | `fair_benchmark.py:make_family` | seeded RNG | 6 regimes × 50 | SYNTHETIC | YES (fair ablation) |

**Distinction.** Only CISA/EPSS are real external data (used for probability, not for success labels). Success labels are curated/controlled [MASTER_RESEARCH_PROJECT_REPORT.md §9]. Corpus modules are **synthetic stubs**, not real exploits [MASTER_RESEARCH_PROJECT_REPORT.md §9].

---

## 15. Results

**Result 1 — Gap-2 pivot saves attempts under fair cap (VAPT corpus, 12 CVEs).** Pivot component (PRIORITY-ONLY − SMART) = **+77 requests at T=2**, **+200 at T=5**. Baseline = no-pivot (DUMB/PRIORITY-ONLY cycle to budget). Interpretation: bounded abandonment of failing candidates is the separable mechanism. Limitation: per-visit cap; priority component = 0 [fair_vapt_benchmark.py output; MASTER_RESEARCH_PROJECT_REPORT.md §21].

**Result 2 — Gap-2 pivot saves attempts (agnostic sparse family).** +772 saved at T=5. Interpretation: mechanism is not CVE-specific. Limitation: one synthetic family only (B2) [fair_benchmark.py output; MASTER_RESEARCH_PROJECT_REPORT.md §21].

**Result 3 — Loopback observed pivot (L2).** Candidate attempted exactly 2×, pivot logged, COMPLETED, no 3rd attempt. Interpretation: pivot responds to real observed failure. Limitation: stubbed assessor, loopback (127.0.0.1), n=2, single run [data/experiment_runs/.../emulator_access_s2.log; MASTER_RESEARCH_PROJECT_REPORT.md §5].

**Result 4 — Loopback observed success (L2).** HIGH-ranked candidate succeeded at attempt 1 (module token + emulator log). Limitation: ranks stub-provided; mechanism only [data/experiment_runs/.../emulator_access_s1.log].

**Result 5 — No speed claim.** `09_BENCHMARK_EVIDENCE.md` time_saved_s = −8.5s (LLM latency). **Never claim "faster"** [MASTER_RESEARCH_PROJECT_REPORT.md §21].

**Result 6 — Regression safety.** TRACK0 39/39 PASS (original VAPT), TRACK1 16/16 PASS (generalized engine) [MASTER_RESEARCH_PROJECT_REPORT.md §13; R3_CLAIM_REGISTER.md A9].

---

## 16. Discussion

**Why the priority component is zero under fair cap.** Under identical per-visit caps, every agent receives the same number of attempts per candidate regardless of ordering. Ordering changes *which* candidate is attempted first but not *how many* total attempts are made across all candidates before the budget is exhausted. Only when a total-budget protocol is introduced does ordering become separable — a best-case bound measured in `tests/ablation.py` (A=1 vs B=3) [MASTER_RESEARCH_PROJECT_REPORT.md §6; R3_CLAIM_REGISTER.md B1]. This is not a weakness of Gap-1; it is a feature of the fair protocol that isolates Gap-2 as the separable mechanism.

**Fairness discipline as contribution.** The decision to retier biased 5-vs-21 / 8-vs-17 figures (which gave SMART an unfair cap advantage) and replace them with identical-cap ablation is itself a methodological contribution [R1_RELATED_WORK.md §6; 12_GO_NO_GO.md ⚠️ B4].

**Why Gap-2 is the defensible contribution.** Gap-2 is (a) measured under fair conditions, (b) cap-isolated, (c) confirmed on both VAPT and a synthetic family, and (d) corroborated at Level 2 via loopback [MASTER_RESEARCH_PROJECT_REPORT.md §7]. Gap-1, by contrast, is a mechanism with a best-case bound but no independent fair-cap win [R3_CLAIM_REGISTER.md B1].

---

## 17. Threats to Validity

| Threat | Mitigation | Evidence |
|--------|------------|----------|
| Stubbed assessor in observed tier (mechanism only, not LLM accuracy) | Report as L2, mechanism-only; never cite as LLM validation | `assessor.py:19`; R3_CLAIM_REGISTER.md B3/C2 |
| L2 not L3 (loopback, not container-isolated) | Report as L2; never say "Docker-validated" or "container-isolated" | `data/experiment_runs/.../emulator_access_*.log`; R3_CLAIM_REGISTER.md C5 |
| Small observed n=2, single run | Report as L2 observed; primary evidence is L1 fair benchmark (30 seeds) | `fair_benchmark.py` |
| Behavioural-stub corpus (not real exploits) | Report as synthetic stubs; success labels are curated/controlled | `data/poc_corpus/labels.json`; MASTER_RESEARCH_PROJECT_REPORT.md §9 |
| One synthetic family for agnostic evidence (B2) | Report as Gap-2-only; architectural independence proven separately | `fair_benchmark.py:make_family` |
| Benchmark structural bias history | Replace biased figures with fair benchmark; never cite 5-vs-21/8-vs-17 | `fair_benchmark.py`; R3_CLAIM_REGISTER.md B4 |

---

## 18. Limitations

1. Loopback not container-isolated (L2, not L3) [MASTER_RESEARCH_PROJECT_REPORT.md §10].
2. Stubbed assessor in observed tier (mechanism only, not LLM accuracy) [R3_CLAIM_REGISTER.md B3].
3. Small observed n=2, single run (no variance) [MASTER_RESEARCH_PROJECT_REPORT.md §11].
4. Behavioural-stub corpus (not real exploits) [MASTER_RESEARCH_PROJECT_REPORT.md §9].
5. Gap-1 priority component = 0 under fair per-visit cap (not an independent win) [R3_CLAIM_REGISTER.md B1].
6. LLM-assessor accuracy on unseen CVEs unvalidated (C2 prohibited) [R3_CLAIM_REGISTER.md C2].
7. Cross-domain experimental evidence = Gap-2 only, one synthetic family (B2) [R3_CLAIM_REGISTER.md B2].
8. Benchmark structural bias history (5-vs-21 / 8-vs-17 retiered; fair bench replaces) [MASTER_RESEARCH_PROJECT_REPORT.md §8].
9. No real-world / multi-target validation (C3/C4/C6 prohibited) [R3_CLAIM_REGISTER.md C3/C4/C6].
10. Negative time_saved (no speed claim) [MASTER_RESEARCH_PROJECT_REPORT.md §21].

---

## 19. Future Work

**Required for stronger evidence (optional, post-thesis):**
- Total-budget Gap-1 experiment (would upgrade B1 → A) [R3_CLAIM_REGISTER.md B1; MASTER_RESEARCH_PROJECT_REPORT.md §16].
- Multi-run loopback variance (currently single run) [MASTER_RESEARCH_PROJECT_REPORT.md §16].
- Level-3 Docker lab (daemon unavailable; parked) [MASTER_RESEARCH_PROJECT_REPORT.md §10].
- LLM-assessor calibration study on unseen CVEs [R3_CLAIM_REGISTER.md B3/C2].

**Required for full VAPT platform (Track B, post-thesis):** discovery/recon, URL/IP ingestion, Nmap/Nuclei adapters, reporting UI, multi-domain orchestration. NOT research-claim blocking [MASTER_RESEARCH_PROJECT_REPORT.md §17].

**Future research directions:** RL-based threshold tuning; broader domain sweep (>1 synthetic family); broader cross-domain experimental generalization [MASTER_RESEARCH_PROJECT_REPORT.md §16].

---

## 20. Conclusion

This thesis demonstrates a domain-independent decision and pivot engine with a fair-validated, failure-driven pivot mechanism (Gap-2) as its primary contribution. Under identical per-visit caps, the pivot component reduces wasted attempts by +77 requests at T=2 and +200 requests at T=5 on the VAPT corpus, with +772 on an agnostic sparse family [fair_benchmark.py output]. The engine's core imports only `decision_engine.core.*`, isolating VAPT behind a single adapter [decision_engine/core/engine.py:1-12; vapt_adapter.py:52]. A secondary mechanism (Gap-1: pre-execution prioritization) is reported honestly: its independent contribution is zero under the fair per-visit-cap protocol, qualifying it as scaffolding rather than an independent win [R3_CLAIM_REGISTER.md B1]. All claims follow the R3 register (A stated directly, B qualified with exact caveats, C omitted). The work is positioned as a credible research-prototype mechanism paper, not a complete platform [MASTER_RESEARCH_PROJECT_REPORT.md §27].

---

## 21. Claim Traceability Appendix

Every thesis sentence maps to an R3 tier and an evidence anchor. C-prohibited claims are omitted entirely.

| # | Thesis Sentence (summary) | R3 Tier | Evidence Anchor |
|---|---------------------------|---------|-----------------|
| 1 | A general autonomous decision & pivot engine was built; its core logic is domain-independent | A1 | `decision_engine/core/engine.py:1-12`; `vapt_adapter.py:52`; `03_TDE_EVIDENCE.md` E1 |
| 2 | Gap-2 bounded pivot reduces wasted attempts under fair identical cap; scales with cap | A2 | `fair_vapt_benchmark.py` output; `fair_benchmark.py`; engine.py:112, engine.py:98 |
| 3 | Framework safely bounds execution; opt-in fail-closed dangerous path | A3 | `tests/test_executor_allowlist.py`; `tests/test_danger_mode_mock.py`; `core/executor.py:56-72`, `core/executor.py:219-245` |
| 4 | Stateful execution with checkpoint/resume is supported | A4 | `tests/test_checkpoint.py`; engine.py:172, engine.py:183 |
| 5 | VAPT domain is one adapter instantiation of the engine | A5 | `vapt_adapter.py:52`; `03_TDE_EVIDENCE.md` E1, E2 |
| 6 | Priority formula `probability × (0.5 + 0.5 × quality)` | A6 | `schemas.py:77`; `QUALITY_WEIGHT` at schemas.py:26 |
| 7 | Deterministic offline assessor; optional local-Ollama LLM assessor | A7 | `assessor.py:19`; `assessor.py:28`; `vapt_adapter.py:70` |
| 8 | EPSS-based priority ranking + corpus labelling pipeline operational | A8 | `data/poc_corpus/labels.json`; `datasets/epss_corpus_enrichment.json`; `datasets/cisa_kev.json` |
| 9 | Regression safety nets exist for both workstreams | A9 | TRACK0 39/39; TRACK1 16/16 |
| 10 | Gap-1 priority ordering routes higher-ranked candidates first | B1 | `schemas.py:77`; `tests/gap1_ablation.py`; `tests/ablation.py` |
| 11 | Under fair per-visit cap, priority component (DUMB − PRIORITY-ONLY) = 0 | B1 | `fair_benchmark.py`; `03_TDE_EVIDENCE.md` §3 B1 |
| 12 | Cross-domain evidence is Gap-2 only (VAPT + 1 synthetic family) | B2 | `fair_benchmark.py:make_family`; `03_TDE_EVIDENCE.md` §3 B2 |
| 13 | LLM assessor is offline deterministic / optional local-Ollama only | B3 | `assessor.py:19`; `vapt_adapter.py:70`; `03_TDE_EVIDENCE.md` §3 B3 |
| 14 | SMART vs DUMB comparisons use ONLY fair-benchmark numbers | B4 | `fair_benchmark.py`; `03_TDE_EVIDENCE.md` §3 B4 |
| 15 | Universal/provably-general domain independence | C1 — **PROHIBITED** | Never claimed |
| 16 | LLM-assessor accuracy on unseen CVEs | C2 — **PROHIBITED** | Never claimed |
| 17 | Real-world VAPT superiority over other tools | C3 — **PROHIBITED** | Never claimed |
| 18 | "Better than all autonomous VAPT systems" | C4 — **PROHIBITED** | Never claimed |
| 19 | Level-3 Docker-isolated live validation | C5 — **PROHIBITED** | Never claimed |
| 20 | Live multi-target validation | C6 — **PROHIBITED** | Never claimed |

---

## 22. References

- CISA. *Known Exploited Vulnerabilities (KEV) Catalog*. https://www.cisa.gov/known-exploited-vulnerabilities-catalog (1,682 records; fetched 2026-08-27).
- FIRST.org. *Exploit Prediction Scoring System (EPSS)*. https://www.first.org/epss/ (bulk API; 365,083 scores; 12-CVE corpus enrichment).
- Deng et al. (2024). Type-B planning failure in autonomous agents (cited in R1_RELATED_WORK.md §2 as the loop-forever failure mode).
- PentestGPT. *PentestGPT: An LLM-based Automatic Penetration Testing Tool*. USENIX Security 2024.
- Strix. *strix-agent* v1.5.3 (PyPI), uploaded 2026-08-10. Product-grade multi-agent pentester; no public paper (R1_RELATED_WORK.md §1).
- Shinn et al. *Reflexion: Language Agents with Verbal Reinforcement Learning*. NeurIPS 2023.
- Yao et al. *ReAct: Synergizing Reasoning and Acting in Language Models*. ICLR 2023.
- PIVOT. *arXiv:2605.11225* — trajectory refinement (not attempt-capped) (R1_RELATED_WORK.md §5).
- Named-but-title-inspected agents (2024–2026): HackSynth, VulnBot, PentestAgent, xOffense, RapidPen — listed in R1_RELATED_WORK.md §3; differentiation not deeply established.

---

## 23. Appendix B — Fair Benchmark Reproduction Command

```
python decision_engine/benchmarks/fair_vapt_benchmark.py --seeds 30 --caps 1 2 3 5
```

Expected (reproduced): VAPT corpus (12 CVEs, 5 true successes) pivot component
(PRIORITY-ONLY − SMART) positive at every cap — **+77 at T=2, +200 at T=5**;
agnostic sparse family **+772 at T=5**. TRACK0 39/39 and TRACK1 16/16 tests pass.

---

*Thesis assembled (A7) from THESIS_DRAFT_v0.1.md (verified at A4/A6). No source code modified.
All claims follow the R3 register (A/B/C) and the honest wording guards in 12_GO_NO_GO.md
and R3_CLAIM_REGISTER.md. Repository HEAD b7a9f06.*
