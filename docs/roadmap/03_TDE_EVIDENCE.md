# T-DE-EVIDENCE — Consolidated Evidence & Claim Gate

_Authority consolidation after T-DE-TESTS (PASS), T-DE-BOUNDARY (Q1–Q4 PASS, Q5 FAIL),
T-DE-BENCH (11 biases), and T-DE-BENCH-IMPL (fair benchmark committed 7001c61).
This is the single A/B/C claim gate that R1–R7 must consume. Hermes-authored;
no source modified._

## 1. What is now PROVEN (evidence tiers)

| # | Claim | Workstream | Tier | Evidence |
|---|-------|-----------|------|----------|
| E1 | Engine is domain-independent (architecturally) | TRACK 1 | Code inspection | `decision_engine/core/*` imports only `decision_engine.core.*`; `vapt_adapter.py` sole boundary (T-DE-BOUNDARY Q1–Q4 PASS) |
| E2 | Gap-2: bounded failure-driven pivoting reduces wasted attempts under FAIR identical cap | TRACK 1 (on TRACK0 data) | Level 1 sim, 4-agent ablation | `fair_benchmark.py` + `fair_vapt_benchmark.py`, 6 families × ≥30 seeds × 4 caps × 10 rankers. VAPT corpus T=2: DUMB 96 → SMART 19 (+77); T=5: +200. Agnostic sparse T=5: +175 |
| E3 | Real mode fires no offensive send by default; danger_mode opt-in + fail-closed allowlist | TRACK 0 | Code review | `tests/test_executor_allowlist.py`, `test_danger_mode_mock.py`; FINAL_EVIDENCE_AUDIT verdict PASS |
| E4 | Checkpoint / resume reproduces state | TRACK 0 + TRACK 1 | Level 1 | `tests/test_checkpoint.py`; `test_de09` (engine) |
| E5 | EPSS-based priority ranking + corpus labelling pipeline | TRACK 0 + TRACK 1 | Level 1 | `data/poc_corpus/labels.json` (12 CVEs), `datasets/epss_corpus_enrichment.json` (live EPSS), `datasets/cisa_kev.json` (1682), `datasets/epss_scores.csv.gz` (365k) |
| E6 | Regression safety nets exist for both workstreams | TRACK 0 + TRACK 1 | — | TRACK0 39/39; TRACK1 16/16 (12 engine + 4 fair) |

## 2. What is RETIERED / CORRECTED (honesty fixes)

- The original TRACK0 "SMART 5 req vs DUMB 21 req, 0 loops" (tests/evaluate.py,
  curated n=3) is **cap-biased** (T-DE-BENCH B2: SMART threshold=2 vs DUMB
  hard_cap=10). Same defect as the agnostic "8 vs 17". REPLACED by the fair
  VAPT benchmark (E2) on the full 12-CVE corpus — which is both fair and
  stronger. Do NOT use the 5-vs-21 / 8-vs-17 figures as evidence of superiority.
- The agnostic "8 vs 17" maintenance-task benchmark is downgraded to a
  loop-bound demo only (T-DE-BOUNDARY Q5 FAIL); superseded by E2's fair sweep.

## 3. CLAIM GATE (A / B / C)

### A — MAY CLAIM (backed by E1–E6, cite file:line or dataset)
- A1. A general autonomous decision & pivot engine was built; its core logic is
  domain-independent (E1).
- A2. Under a fair, identical attempt cap, state-aware failure-threshold pivoting
  (Gap-2) measurably reduces wasted attempts vs a no-pivot baseline, scaling with
  the cap (E2). Demonstrated on the VAPT corpus AND a non-VAPT synthetic family.
- A3. The framework/engine safely bounds execution by default and supports an
  opt-in, fail-closed, authorised-lab-only dangerous path (E3).
- A4. Stateful execution with checkpoint/resume is supported (E4).
- A5. The VAPT domain is one instantiation/adapter of the engine; the engine's
  mechanisms are demonstrated primarily in vulnerability-testing workflows (E1, E2).

### B — MUST QUALIFY (claim only with explicit caveat)
- B1. "Intelligent pre-execution prioritization (Gap-1) improves outcomes."
  CAVEAT: under the current fair per-visit-cap protocol, the priority component
  (DUMB − PRIORITY-ONLY) = 0 — ordering alone does not change total attempts
  without a total-attempt budget. Gap-1 may be presented as necessary scaffolding
  for pivot ordering, NOT an independently-measured win. Requires a total-budget
  protocol to upgrade to A.
- B2. "Cross-domain evidence." CAVEAT: experimental cross-domain evidence is
  Gap-2-only (VAPT corpus + one synthetic family). Architectural independence is
  proven (A1); experimental generalization across many domains is NOT.
- B3. "LLM assessor." CAVEAT: only the offline/deterministic and (optionally
  local-Ollama) paths are exercised; real LLM-assessor accuracy on unseen inputs
  is unmeasured.
- B4. "SMART vs DUMB" comparisons. CAVEAT: use ONLY the fair-benchmark numbers
  (E2); never the biased 5-vs-21 / 8-vs-17 figures.

### C — PROHIBITED (must never be claimed)
- C1. Universal / provably-general domain independence.
- C2. LLM-assessor accuracy on unseen CVEs / exploits.
- C3. Real-world VAPT superiority over other tools / systems.
- C4. "Better than all autonomous VAPT systems" (Strix, PentestGPT, …).
- C5. Level-3 Docker-isolated live validation (parked; not achieved).
- C6. Any claim that the engine was validated against live multi-target
  environments.

## 4. Readiness for R1–R7

Gates T-DE-TESTS / T-DE-BOUNDARY / T-DE-BENCH / T-DE-BENCH-IMPL are COMPLETE.
Evidence tiers (§1) and the A/B/C gate (§3) are established. R1 (related work),
R2 (novelty matrix), R3 (formal claim register — should mirror §3), R4
(challenge), R5–R7 (GO/NO-GO) may now proceed. All R-claims must be checked
against §3 before entering the thesis.
