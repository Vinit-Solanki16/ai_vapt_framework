# RESEARCH PAPER OUTLINE — ai_vapt_framework

**Constraint:** GAP-2 is the primary contribution. GAP-1 is a qualified/null
secondary result. Only verified quantitative results are used. No unsupported
claims are introduced.

---

## TITLE

A Domain-Independent Decision and Pivot Engine with Fair-Validated Failure-Driven Pivoting

---

## ABSTRACT (sketch)

Autonomous action-selection agents often loop on failing routes instead of
abandoning them. We present a domain-independent decision engine that bounds
repeated failure by tracking per-candidate attempt counts and pivoting away
when a configurable threshold is reached. Under a fair ablation protocol with
identical per-visit caps, the pivot mechanism reduces wasted attempts versus a
no-pivot baseline on a 12-CVE VAPT corpus: the pivot component saves +77
requests at T=2 and +200 at T=5. On a synthetic sparse-success family at T=5,
the pivot component is +772. A secondary pre-execution prioritization mechanism
produced a null independent contribution under the same fair protocol, qualifying
it as scaffolding rather than an independent win. The engine core imports only
domain-independent modules; VAPT logic is isolated behind a single adapter.

---

## 1. INTRODUCTION

- Motivating problem: loop-forever failure in autonomous action-selection agents.
- Type-B planning failure (Deng et al., 2024).
- Research contribution: bounded failure-threshold pivot, fair-validated.
- Positioning: mechanism/research-prototype paper, not a complete platform.
- Roadmap: gap analysis, architecture, methodology, results, discussion, threats, limitations, conclusion.

---

## 2. PROBLEM STATEMENT

- Formal problem statement with candidates `c ∈ C`, unknown outcomes, repeated execution.
- Existing behavior in original VAPT prototype (`core/agent_graph.py`): no per-candidate attempt counter, no pivot.
- Requirements: track attempts, pivot at threshold, guarantee bounded termination, enable fair ablation.

---

## 3. RELATED WORK

Honest qualifiers only:

- **Strix v1.5.3 (2026-08-10):** product-grade multi-agent pentester; no public paper. Relationship: product vs mechanism. Numbers not compared.
- **PentestGPT (USENIX 2024):** three LLM modules; no bounded per-target pivot counter.
- **HackSynth / VulnBot / PentestAgent / xOffense / RapidPen:** named from 2024–2026 lists; titles-only inspection. Deep novelty differentiation not established from repository evidence.
- **Reflexion / ReAct:** generic self-reflection / tool-use; no hard per-candidate attempt cap.
- **PIVOT (arXiv:2605.11225):** trajectory refinement; not attempt-capped.

Differentiation rests on: bounded per-candidate counter + threshold pivot + fair-cap ablation.

---

## 4. GAP ANALYSIS

**Gap-1:** Pre-execution candidate quality scoring and prioritization.
- Mechanism present.
- Caveat: under fair per-visit cap, priority component = 0. Qualified B1.

**Gap-2:** Explicit state-aware failure tracking, bounded attempts, failure-threshold pivot.
- Mechanism present + fair-validated. Primary contribution A2.

---

## 5. RESEARCH QUESTIONS / HYPOTHESES

- **RQ1 (Gap-1):** Does pre-execution prioritization improve selection efficiency?
  - H1: reaches first success earlier under total budget. Evidence: partial (bound only).
- **RQ2 (Gap-2):** Does failure tracking + threshold pivot reduce wasted attempts?
  - H2: guarantees bounded termination and cuts wasted attempts. Evidence: strong (A2).
- **RQ3:** Can mechanisms operate without VAPT-specific logic?
  - H3: engine imports only core.*; VAPT isolated in adapter. Evidence: strong (architectural).

---

## 6. PROPOSED APPROACH / ARCHITECTURE

- Domain-independent core (`decision_engine/core/`).
- VAPT adapter (`adapters/vapt_adapter.py`) as sole boundary.
- Flow diagram:
  - assess_candidates() → quality_rank
  - rank_candidates() → priority_score
  - execute() → outcome
  - attempt_count++
  - _evaluate(): threshold check → pivot
  - _pivot_node(): advance/reset/COMPLETED

Key file references:
- `schemas.py:77` priority_score
- `engine.py:112` _evaluate
- `engine.py:98` _pivot_node
- `engine.py:172/183` checkpoint/resume
- `vapt_adapter.py:52` corpus → ActionCandidate mapping

---

## 7. METHODOLOGY

- Fair 4-agent ablation: DUMB, PIVOT-ONLY, PRIORITY-ONLY, SMART.
- Identical per-visit caps T ∈ {1,2,3,5}.
- Decomposition: priority_component = DUMB − PRIORITY-ONLY; pivot_component = PRIORITY-ONLY − SMART.
- ≥30 seeds; 6 synthetic families × 4 caps × 10 rankers.
- VAPT corpus: 12 CVEs, curated labels + EPSS enrichment.
- Loopback observed validation: local Flask emulator, `127.0.0.1`, stubbed assessor.

---

## 8. DATASETS

- CISA KEV: 1,682 vulns (real external, pipeline only)
- EPSS bulk: 365,083 scores (real external, pipeline only)
- EPSS corpus enrichment: 12 CVEs (real external, probability signal)
- PoC corpus labels: 12 CVEs (controlled ground truth, simulation)
- PoC modules: 12 synthetic stubs
- Synthetic families: seeded RNG, 6 regimes × 50 candidates

Distinction: only CISA/EPSS are real external data; success labels are curated/controlled.

---

## 9. RESULTS

1. **Gap-2 pivot (VAPT):** +77 at T=2, +200 at T=5.
2. **Gap-2 pivot (agnostic sparse):** +772 at T=5.
3. **Priority component:** 0 under fair per-visit cap.
4. **Loopback L2:** exactly 2 attempts, pivot, COMPLETED, no 3rd attempt.
5. **Regression safety:** TRACK0 39/39, TRACK1 16/16.

---

## 10. DISCUSSION

- Why priority component = 0: identical per-visit caps give equal attempts per candidate regardless of order.
- Fairness discipline as contribution: replacement of biased 5-vs-21 / 8-vs-17 figures with identical-cap ablation.
- Why Gap-2 is defensible: fair-validated, cap-isolated, confirmed on VAPT + synthetic family, corroborated at L2.

---

## 11. THREATS TO VALIDITY

| Threat | Mitigation |
|--------|------------|
| Stubbed assessor in observed tier | Report as L2 mechanism-only; never as LLM validation |
| L2 not L3 | Report as L2; never say Docker-validated |
| Small observed n=2, single run | Primary evidence is L1 fair benchmark (30 seeds) |
| Synthetic stubs | Report as synthetic; success labels curated/controlled |
| One synthetic family | Report as Gap-2-only; architectural independence proven separately |
| Benchmark bias history | Retired 5-vs-21 / 8-vs-17; use only fair benchmark |

---

## 12. LIMITATIONS

1. Loopback not container-isolated (L2, not L3).
2. Stubbed assessor in observed tier.
3. Small observed n=2, single run.
4. Synthetic corpus.
5. Gap-1 null under fair cap.
6. LLM accuracy unvalidated.
7. Cross-domain = Gap-2 only, one family.
8. No real-world validation.
9. No speed claim.

---

## 13. CONCLUSION

The paper presents a domain-independent decision and pivot engine with a
fair-validated, failure-driven pivot mechanism (Gap-2) as its primary
contribution. Under identical per-visit caps, the pivot component reduces
wasted attempts by +77 at T=2 and +200 at T=5 on the VAPT corpus, with +772
on an agnostic sparse family. The engine's core imports only `decision_engine.core.*`,
isolating VAPT behind a single adapter. Gap-1 is honestly reported as a
qualified null under the current fair protocol.

---

## APPENDIX: REPRODUCTION COMMANDS

```
python -m pytest tests/ -q
python -m pytest decision_engine/tests/ -q
python decision_engine/benchmarks/fair_vapt_benchmark.py --seeds 30 --caps 1 2 3 5
python decision_engine/benchmarks/fair_benchmark.py --seeds 30 --caps 5 --families sparse_success
```

---

*End of RESEARCH_PAPER_OUTLINE.md*
