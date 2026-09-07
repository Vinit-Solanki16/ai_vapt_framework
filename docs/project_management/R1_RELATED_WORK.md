# R1 — Related Work

_Documentation-only. Verified against `docs/roadmap/03_TDE_EVIDENCE.md` §3 (A/B/C gate); every "Yes ours" maps to it. Sources accessed 2026-08-27._

## 1. Strix — dated snapshot (primary comparison)
- **Strix** (`usestrix/strix`, Apache-2.0). PyPI `strix-agent` **v1.5.3, uploaded 2026-08-10** (pypi.org/project/strix-agent/; verified 2026-08-27). Repo created 2025-08-05; ~57k stars (fluctuating). No public paper.
- Architecture (README/docs.strix.ai): **graph/tree of specialized agents** — Root orchestrator + Sub-Agents (recon, exploitation, validation); HTTP proxy, browser, terminal, Python sandbox; PoC validation; CI/CD. Product-grade pentester.
- Relationship: Strix is a *product*; ours is a *mechanism/engine*. We do **not** compare numbers — "better than Strix/PentestGPT" is PROHIBITED (§3 C4).

## 2. PentestGPT
Deng et al., **USENIX Security 2024** (arXiv:2308.06782). Three self-interacting LLM modules (reasoning, generation, parsing) to curb context loss. Repo `GreyDGL/PentestGPT` (~15k★). Reports +228.6% completion vs GPT-3.5 on its own benchmark; no bounded per-target attempt-counter / pivot mechanism.

## 3. Other named agents
HackSynth (arXiv:2412.01778), VulnBot (arXiv:2501.13411), PentestAgent (ACM 2025), xOffense (arXiv:2509.13021), Pentest-R1, AutoPentest/CAI, pentest-copilot, RapidPen (arXiv:2502.16730) — from 2024–2026 arXiv/preprint lists; named, not deep-read here.

## 4. LLM action / exploit quality scoring
PentestGPT uses LLM self-scoring; the literature adds action-value / success-prediction heads and ReAct tool-use scoring. Our `deterministic_assessor` + optional local-Ollama assessor sits here; accuracy on **unseen** CVEs is **unproven** (§3 B3 / C2).

## 5. Failure-aware / pivot / loop-prevention
Generic agents use Reflexion self-reflection (Shinn et al., 2023) and ReAct; pentest systems mostly use LLM memory, not bounded counters. Our **Gap-2 (per-candidate `attempt_count` + threshold pivot + hard cap)** is a small *deterministic* mechanism — not a Reflexion clone. PIVOT (arXiv:2605.11225) refines trajectories but is not attempt-capped.

## 6. Benchmark methodology
Two defects recur: (a) cap/threshold bias — a "smart" agent wins via a tighter stopping rule (our old 5-vs-21 / 8-vs-17, retiered in §2); (b) cherry-picked CTF subsets. Fair fix: **identical per-visit cap T** across DUMB / PRIORITY-ONLY / SMART / FULL, ≥30 seeds × 6 families × 4 caps × 10 rankers, pivot isolated as `PRIORITY-ONLY − SMART` (§1 E2). Gap-2-only; cross-domain = one synthetic family (§3 B2).

## 7. Comparison table (every row honest)

| System / family | Auto pentest agent | LLM action-quality scoring | Failure-aware / pivot / loop-prevention | Fair cap / ablation | Ours? (gate) |
|---|---|---|---|---|---|
| **Strix v1.5.3 (2026-08-10)** | Yes (multi-agent graph) | Partially (LLM-judged) | Partially (orchestrator retry; no public per-target counter spec) | Not inspected (no public paper) | N/A — product |
| **PentestGPT (USENIX'24)** | Yes (3-module) | Yes (self-scoring) | Partially (LLM memory, no bounded pivot) | Partially (own benchmark; not cap-isolated) | N/A |
| **HackSynth/VulnBot/PentestAgent/xOffense** | Yes (named) | Partially | Partially | Inspected-not-found (titles only) | N/A |
| **Reflexion/ReAct (generic)** | N/A | Yes (reflection) | Partially (no hard cap) | N/A | N/A |
| **Ours — decision_engine/** | Partial (mechanism) | Partially (deterministic + local-Ollama) | **Yes** — Gap-2 bounded pivot (E2) | **Yes** — fair cap, 4-agent ablation, pivot isolated (E2) | **Yes ours (A2)** |
| Ours — Gap-1 priority | N/A | N/A | N/A | Not independently isolated (component = 0 under per-visit cap) | **B — qualify only (B1)** |
| Ours — real-world superiority | — | — | — | — | **C — prohibited (C3,C4)** |

## 8. Bottom line
- **A2:** fair identical cap → bounded pivot reduces wasted attempts (VAPT T=2: +77, T=5: +200; agnostic sparse T=5: +772).
- **B-qualify:** Gap-1 priority scaffolding (B1); cross-domain Gap-2-only (B2); LLM-assessor offline/local only (B3); cite only fair SMART-vs-DUMB (B4).
- **C-prohibited:** universal independence, unseen-CVE LLM accuracy, real-world superiority, "better than Strix/PentestGPT" (C1–C4).
