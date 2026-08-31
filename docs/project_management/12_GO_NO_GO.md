# Consolidated Evidence Map – T-DE Architecture (Level 1 Sim / Level 2 Observed / Fair Benchmark Gap-2)

## Claim Hierarchy (R3 Register)

### ✅ A — MAY CLAIM (Backed by E1–E6)
- **A1. Domain-Independent Engine** – Engine is architecturally domain-independent (E1). Verified via code inspection of `decision_engine/core/engine.py` (imports only `decision_engine.core.*`); VAPT integration via `vapt_adapter.py` (sole boundary).
- **A2. Gap-2 Fair Benchmark (Reduced Wasted Attempts)** – Level‑1 simulation + 4‑agent ablation (E2). VAPT corpus (12 CVEs) + synthetic family, under identical per‑candidate cap T. Pivot component (PRIORITY‑ONLY − SMART) is positive and grows with T: VAPT T=2 +77 requests saved, T=5 +200; agnostic sparse T=5 +175. Eliminates cap‑asymmetry bias (B2) and proves bounded failure‑driven pivoting.
- **A3. Safe Bounds + Fail‑Closed Dangerous Path** – Stateful execution with checkpoint/resume (E3). Verified in `tests/test_checkpoint.py` (save/load/resume round‑trip) and `tests/test_executor_allowlist.py` (danger_mode opt‑in + fail‑closed allowlist).
- **A4. Checkpoint/Resume Reproducibility** – `tests/test_checkpoint.py` confirms state serialization (JSON) and safe resumption without duplicated executions.
- **A5. VAPT Domain as Adapter** – The engine is a reusable “Stage 1” core; VAPT is attached via `vapt_adapter.py` (single boundary). The engine’s mechanisms are demonstrated in vulnerability‑testing workflows (E1, E2).

### ⚠️ B — MUST QUALIFY (Claims with Caveats)
- **B1. Intelligent Pre‑Execution Prioritization (Gap‑1)** – Priority ordering (DUMB/PRIORITY‑ONLY) reduces wasted attempts under a per‑visit cap. **Caveat:** Under the current fair per‑visit‑cap protocol, priority ordering alone does not change total attempts without a total‑budget protocol to upgrade to A.
- **B2. Cross‑Domain Evidence** – Experimental cross‑domain generalization (Gap‑2 only, VAPT + one synthetic family). **Caveat:** Architectural independence is proven (A1); experimental generalization across many domains is NOT established.
- **B3. LLM Assessor** – Offline deterministic fallback (`deterministic_assessor`) and optional local‑Ollama path. **Caveat:** Real‑world LLM‑assessor accuracy on unseen CVEs is unmeasured.
- **B4. SMART vs DUMB Comparisons** – Performance gains shown on the full VAPT corpus (E2). **Caveat:** Use ONLY the fair‑benchmark numbers (E2); the biased 5‑vs‑21 / 8‑vs‑17 figures from the original TRACK0 tests are obsolete.

### ❌ C — PROHIBITED (Never Claim)
- **C1. Universal/Provably‑General Domain Independence** – The engine is deliberately domain‑free; this is a strength, not a limitation.
- **C2. LLM‑Assessor Accuracy on Unseen CVEs** – Only offline deterministic or local‑Ollama paths are exercised; real‑world unseen‑input accuracy is unmeasured.
- **C3. Superiority Over Other VAPT Systems** – The framework is evaluated against a single baseline (DUMB) on a labeled subset; broader platform superiority is not demonstrated.
- **C4. Live Multi‑Target Validation** – Only simulated and synthetic‑family experiments are performed; production‑grade live validation is not achieved.
- **C5. Level‑3 Docker‑Isolated Live Validation** – Not implemented; remains a future work item.
- **C6. Multi‑Environment Live Safety Net** – Not implemented.

## Evidence Mapping (File:Line → Claim)

| Claim | Evidence Source | Location |
|-------|-----------------|----------|
| E1 – Engine is domain‑independent | `decision_engine/core/engine.py` | Lines 1‑12 |
| E2 – Gap‑2 fair benchmark (reduced waste) | `decision_engine/benchmarks/fair_benchmark.py` | Lines 1‑20 |
| E3 – Safe bounds + fail‑closed danger mode | `tests/test_executor_allowlist.py` | Line 1 |
| E3 – Checkpoint/resume reproducibility | `tests/test_checkpoint.py` | Lines 149‑180 |
| E4 – Checkpoint/Resume state preservation | `tests/test_checkpoint.py` | Lines 149‑180 |
| E5 – EPSS‑based priority ranking + corpus labeling | `data/poc_corpus/labels.json` + `datasets/epss_corpus_enrichment.json` | Lines 1‑14 |
| E6 – Regression safety nets (TRACK0/TRACK1) | `docs/roadmap/03_TDE_EVIDENCE.md` | Section 6 |

## R3 Register Summary

| Item | Status | Notes |
|------|--------|-------|
| A1 – Domain‑independent engine | ✅ GO | Backed by E1 (code inspection) |
| A2 – Gap‑2 fair benchmark (E2) | ✅ GO | Measured reduction in wasted attempts (T=2→5) |
| A3 – Safe bounds + fail‑closed danger mode | ✅ GO | Verified in `test_executor_allowlist.py` |
| A4 – Checkpoint/resume reproducibility | ✅ GO | Verified in `test_checkpoint.py` |
| A5 – VAPT domain as adapter | ✅ GO | `vapt_adapter.py` isolates domain knowledge |
| B1 – Gap‑1 prioritization | ⚠️ QUALIFY | Needs total‑budget protocol to reach A-level guarantee |
| B2 – Cross‑domain evidence | ⚠️ QUALIFY | Experimental; not yet proven across many domains |
| B3 – LLM assessor | ⚠️ QUALIFY | Only offline/deterministic or local‑Ollama; real‑world accuracy unmeasured |
| B4 – SMART vs DUMB comparison | ⚠️ QUALIFY | Valid on fair‑benchmark corpus; ignore biased older figures |
| C1 – Universal domain independence | ❌ PROHIBITED | Engine is intentionally domain‑free |
| C2 – LLM‑assessor accuracy on unseen CVEs | ❌ PROHIBITED | Not experimentally validated |
| C3 – Superiority over other VAPT systems | ❌ PROHIBITED | Only compared against DUMB baseline |
| C4 – Live multi‑target validation | ❌ PROHIBITED | Only simulated/synthetic experiments |
| C5 – Level‑3 Docker‑isolated live validation | ❌ PROHIBITED | Not implemented |
| C6 – Multi‑environment safety net | ❌ PROHIBITED | Not implemented |

## Phase 7 Thesis – Venue Fit & Go/No‑Go

### Recommended Venue Fit
**Credible research‑prototype / mechanism paper** (not a “complete platform”). The work demonstrates a **generalized decision‑engine architecture** with **fair‑validated, failure‑driven pivoting** (Gap‑2 bounded pivoting) on both VAPT and a synthetic domain. The contributions are:

1. **Architectural novelty** – A domain‑free decision engine that separates candidate evaluation (Gap‑1) from execution (Gap‑2) with formal abort thresholds.
2. **Empirical validation** – Fair‑benchmark (E2) shows measurable reduction in wasted attempts under identical per‑visit caps; this eliminates cap‑asymmetry bias (B1) and provides quantitative evidence for the pivot mechanism.
3. **Robustness guarantees** – Checkpoint/resume (E3) ensures safe experimentation; safe danger‑mode handling (E3) prevents accidental exploitation.
4. **Limitations acknowledged** – The framework is a research prototype; it lacks live multi‑target validation (C3/C4) and full LLM‑assessor integration (C3). These are explicitly excluded from the claim.

### Explicit GO/NO‑GO Recommendation

| Component | Verdict | Reasoning |
|-----------|---------|------------|
| **Core Mechanism (Domain‑Free Decision Engine + Gap‑2 Pivoting)** | **✅ GO** | Fully backed by E1–E6; fair‑benchmark (E2) provides quantitative evidence of reduced wasted attempts. The architecture is a genuine research contribution. |
| **Prioritization (Gap‑1)** | **⚠️ QUALIFY** | Improves ordering but does not by itself reduce total attempts under the current fair‑cap protocol. Upgrading to a total‑budget protocol would elevate it to A‑level. |
| **Cross‑Domain Generalization** | **⚠️ QUALIFY** | Experimental (Gap‑2 only); architectural independence is proven (A1), but broad domain transfer is not yet demonstrated. |
| **LLM Assessor Integration** | **⚠️ QUALIFY** | Offline deterministic fallback and local‑Ollama path are implemented; real‑world unseen‑input accuracy remains unmeasured. |
| **Superiority Claims (vs. other VAPT systems)** | **❌ NO‑GO** | Only compared against DUMB baseline on a small labeled subset; no head‑to‑head platform comparison. |
| **Live Multi‑Target Validation** | **❌ NO‑GO** | Only simulated and synthetic‑family experiments; production‑grade live validation is not achieved. |
| **Overall Thesis Scope** | **✅ GO** | The thesis may legitimately claim a **research‑prototype mechanism paper** demonstrating a generalized decision‑engine architecture with fair‑validated failure‑driven pivoting. The scope is bounded to the engine itself and the VAPT/synthetic evaluation; it does not overreach into platform superiority or live multi‑target deployment. |

### Final Recommendation

**Proceed with Phase 7 writing.** The thesis should be positioned as a **credible mechanism paper** focused on the **generalized decision‑engine architecture** and its **empirically validated Gap‑2 pivoting**. Explicitly state the **claim boundaries** (A‑level for core engine, B‑level for prioritization with caveats, C‑level prohibited). Emphasize that the work is a **research prototype** with strong theoretical grounding (fair‑benchmark decomposition) and robust safety properties (checkpointing, fail‑closed danger mode). Avoid any claims of platform superiority or live multi‑target validation—those remain open research questions.

---

*Evidence map and claim gate extracted from `docs/roadmap/03_TDE_EVIDENCE.md`; supporting code located in `decision_engine/core/`, `decision_engine/benchmarks/`, `decision_engine/adapters/`, and test suites `tests/`.*
