# R2 — Novelty / Threat-to-Novelty Matrix

_Documentation only. Every "Yes ours" cites `docs/roadmap/03_TDE_EVIDENCE.md` §3; UNPROVEN marked. Sources: 2026-08-27 review of R1 and engine code._

## 1. Matrix Overview
Novelty focuses on Gap-1 (pre-execution priority) and Gap-2 (bounded failure-driven pivot) mechanisms. Threat-to-novelty acknowledges replication limitations (B2/B3 caveats). All related systems use 5 honest qualifiers (Strix, PentestGPT, HackSynth/VulnBot/PentestAgent/xOffense, Reflexion/ReAct).

## 2. Systems & Honest Qualifiers (from R1)
| System | Auto pentest agent | LLM action-quality scoring | Failure-aware / pivot / loop-prevention | Fair cap / ablation | Evidence backing |
|--------|-------------------|----------------------------|-------------------------------------------|---------------------|------------------|
| **Strix v1.5.3 (2026-08-10)** | Yes (multi-agent graph) | Partially (LLM-judged) | Partially (orchestrator retry; no public per-target counter spec) | Not inspected (no public paper) | None (product) |
| **PentestGPT (USENIX'24)** | Yes (3-module) | Yes (self-scoring) | Partially (LLM memory, no bounded pivot) | Partially (own benchmark; not cap-isolated) | None |
| **HackSynth/VulnBot/PentestAgent/xOffense** | Yes (named) | Partially | Partially | Inspected-not-found (titles only) | None |
| **Reflexion/ReAct (generic)** | N/A | Yes (reflection) | Partially (no hard cap) | N/A | None |
| **Ours — decision_engine/** | Partial (mechanism) | Partially (deterministic + local-Ollama) | **Yes** — Gap-2 bounded pivot (E2) | **Yes** — fair cap, 4-agent ablation, pivot isolated (E2) | **A2** | A2

## 3. Mechanisms Coverage

### 3.1 Pre-execution candidate quality scoring (Gap-1) — deterministic + optional LLM
- **Priority =** `probability × (0.5 + 0.5×quality)`
- **Deterministic fallback:** `deterministic_assessor` (decisions_engine/core/assessor.py:19)
- **LLM optional:** domain adapter may override (vapt_adapter.py, not implemented yet)
- **Evidence:** Gap-1 alone yields zero net attempts under per-visit-cap protocol (B1 qualify-only); no total-budget protocol measured (unproven)
- **Ours?** B — qualify-only (gap-1 priority scaffolding, per §3 B1)

### 3.2 Per-candidate attempt counter + N-threshold pivot (Gap-2)
- **Attempt tracking:** `EngineState.attempt_count` per candidate (engine.py:140)
- **Threshold check:** `_evaluate` pivots at `attempt_count >= max_attempts` (engine.py:112)
- **Per-candidate reset:** `_pivot_node` zeroes `attempt_count` on candidate advance (engine.py:98)
- **Evidence:** E2 — fair identical cap reduces wasted attempts (VAPT T=2 +77, T=5 +200; agnostic sparse T=5 +175). Proven on 12-CVE VAPT corpus + synthetic family.
- **Ours?** Yes ours (A2) — decision_engine/core/engine.py:_evaluate (112) & _pivot_node (98)

### 3.3 Priority = probability × (0.5 + 0.5×quality)
- **Formula:** `priority_score()` (core/schemas.py:77)
- **Quality mapping:** `QUALITY_WEIGHT` {HIGH:1.0, MEDIUM:0.6, LOW:0.3} (core/schemas.py:26)
- **Evidence:** algorithmic definition only; no empirical validation of this exact formula in isolation (unproven)
- **Ours?** Yes ours (A2) — part of defensible Gap-2 claim

### 3.4 Bounded termination / loop prevention
- **Hard cap:** `max_attempts` in `initial_state` (engine.py:141)
- **Structured pivot:** `current_index` progression with early-exit at `COMPLETED` (engine.py:102)
- **Evidence:** E4 — checkpoint/resume exists (tests/test_checkpoint.py)
- **Ours?** Yes ours (A4) — decision_engine/core/engine.py:_pivot_node (102)

### 3.5 Simulation-vs-observed evidence tiers
- **Simulation:** deterministic_assessor + ground_truth for reproducibility (assessor.py:19)
- **Observed:** domain adapter may use live LLM + real exploit execution (not yet implemented)
- **Evidence tiers:** Level 1 simulation, 4-agent ablation (E2); real-mode safety nets (E3); EPSS priority pipeline (E5)
- **Ours?** Yes ours (E5) — EPSS-based priority indexing (datasets/epss_scores.csv.gz:365k)

## 4. Related Systems Honest Qualifiers Summary
| System | 5 honest qualifiers complete? | Cross-domain? | Real LLM accuracy? |
|--------|------------------------------|---------------|-------------------|
| Strix | Yes | No | No |
| PentestGPT | Yes | No | Yes |
| HackSynth/VulnBot/PentestAgent/xOffense | Incomplete | N/A | N/A |
| Reflexion/ReAct | No | N/A | N/A |
| Ours | Partial (B2/B3) | Gap-2-only (B2) | Offline/local only (B3) |

## 5. Verdict
- **A2 Gap-2** proven (E2) — meets the thesis's main defensible claim.
- **B1 Gap-1** qualify-only — necessary scaffolding, no independent measured win.
- **B2 Cross-domain** limited — Gap-2 only (VAPT + 1 synthetic family).
- **B3 LLM assessor** limited — offline/deterministic + optional local-Ollama only; unseen-CVE accuracy unproven (C2 prohibited).
- **B4 SMART vs DUMB** constrained — must use fair-benchmark numbers only (no biased 5-vs-21/8-vs-17).

All other mechanisms are present in code but lack sufficient empirical evidence for higher claims; marked UNPROVEN where evidence is missing.
