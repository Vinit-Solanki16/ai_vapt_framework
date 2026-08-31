# R3 — Controlled Thesis Claim Register

_Single source of truth for all thesis claims. Every sentence in the thesis must be checkable against this register. Seeded from `docs/roadmap/03_TDE_EVIDENCE.md` §3. Hermes-authored; documentation only._

## A — MAY CLAIM (backed by evidence; cite file:line or dataset)

| ID | Claim | Evidence anchor |
|----|-------|-----------------|
| **A1** | A general autonomous decision & pivot engine was built; its core logic is domain-independent | `03_TDE_EVIDENCE.md` E1; `decision_engine/core/engine.py` imports only `decision_engine.core.*`; `vapt_adapter.py` sole boundary |
| **A2** | Under a fair, identical attempt cap, state-aware failure-threshold pivoting (Gap-2) measurably reduces wasted attempts vs a no-pivot baseline, scaling with the cap | `03_TDE_EVIDENCE.md` E2; VAPT T=2 +77, T=5 +200; agnostic sparse T=5 +175; `engine.py:_evaluate` (line 112), `engine.py:_pivot_node` (line 98) |
| **A3** | The framework/engine safely bounds execution by default and supports an opt-in, fail-closed, authorised-lab-only dangerous path | `03_TDE_EVIDENCE.md` E3; `tests/test_executor_allowlist.py`, `test_danger_mode_mock.py` |
| **A4** | Stateful execution with checkpoint/resume is supported | `03_TDE_EVIDENCE.md` E4; `tests/test_checkpoint.py`, `test_de09`; `engine.py:save_checkpoint` (line 172), `load_checkpoint` (line 183) |
| **A5** | The VAPT domain is one instantiation/adapter of the engine; the engine's mechanisms are demonstrated primarily in vulnerability-testing workflows | `03_TDE_EVIDENCE.md` E1, E2; `vapt_adapter.py` |
| **A6** | Priority ordering uses the formula `probability × (0.5 + 0.5×quality)` | `schemas.py:priority_score` (line 77), `QUALITY_WEIGHT` (line 26); `engine.py:rank_candidates` (line 50) |
| **A7** | A deterministic offline assessor provides reproducible Gap-1 scoring; a local-Ollama LLM assessor is optionally available | `assessor.py:deterministic_assessor` (line 19), `assess_candidates` (line 28) |
| **A8** | EPSS-based priority ranking and corpus labelling pipeline are operational | `03_TDE_EVIDENCE.md` E5; `data/poc_corpus/labels.json` (12 CVEs), `datasets/epss_corpus_enrichment.json`, `datasets/cisa_kev.json` (1682), `datasets/epss_scores.csv.gz` (365k) |
| **A9** | Regression safety nets exist for both workstreams | `03_TDE_EVIDENCE.md` E6; TRACK0 39/39, TRACK1 16/16 |

## B — MUST QUALIFY (claim only with explicit caveat stated)

| ID | Claim | Required caveat |
|----|-------|-----------------|
| **B1** | "Intelligent pre-execution prioritization (Gap-1) improves outcomes" | Under the current fair per-visit-cap protocol, the priority component (DUMB − PRIORITY-ONLY) = 0; Gap-1 is necessary scaffolding for pivot ordering, not an independently-measured win. Requires total-budget protocol to upgrade to A. [`03_TDE_EVIDENCE.md` §3 B1] |
| **B2** | "Cross-domain evidence" | Experimental cross-domain evidence is Gap-2-only (VAPT corpus + one synthetic family). Architectural independence is proven (A1); experimental generalization across many domains is NOT. [`03_TDE_EVIDENCE.md` §3 B2] |
| **B3** | "LLM assessor" | Only offline/deterministic and (optionally local-Ollama) paths are exercised; real LLM-assessor accuracy on unseen inputs is unmeasured. [`03_TDE_EVIDENCE.md` §3 B3] |
| **B4** | "SMART vs DUMB" comparisons | Use ONLY fair-benchmark numbers (E2); never biased 5-vs-21 or 8-vs-17 figures. [`03_TDE_EVIDENCE.md` §3 B4] |

## C — PROHIBITED (must never be claimed)

| ID | Prohibited claim |
|----|------------------|
| **C1** | Universal / provably-general domain independence |
| **C2** | LLM-assessor accuracy on unseen CVEs / exploits |
| **C3** | Real-world VAPT superiority over other tools / systems |
| **C4** | "Better than all autonomous VAPT systems" (Strix, PentestGPT, …) |
| **C5** | Level-3 Docker-isolated live validation (parked; not achieved) |
| **C6** | Any claim that the engine was validated against live multi-target environments |

## Usage

Before writing any thesis sentence, locate the claim's tier in this register. A-claims require a cited evidence anchor; B-claims require their caveat verbatim or in summary; C-claims must be omitted entirely. R1, R2, and `03_TDE_EVIDENCE.md` §3 remain the upstream authorities; this register mirrors them as the single working contract for thesis writing.
