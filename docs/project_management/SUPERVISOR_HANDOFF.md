# SUPERVISOR_HANDOFF — ai_vapt_framework

**Research stage:** Post-P0 documentation correction, implementation frozen.
**Deliverable state:** Thesis draft complete; core claim-disciplined docs updated; 55/55 tests green.
**Repository:** `/home/vinit/ai_vapt_framework` — branch `master`, HEAD `4dc0599`.
**Date prepared:** 2026-09-01

---

## 1. RESEARCH PROBLEM

Autonomous action-selection agents in vulnerability-testing workflows often loop
indefinitely on a failing candidate route instead of abandoning it and trying
alternatives. This is framed as Type-B planning failure: the agent repeatedly
executes a non-productive candidate without a bounded exit condition.

The research contribution is **not** a complete autonomous VAPT platform. It is
an evaluated decision mechanism within an autonomous testing workflow:
state-aware failure-threshold pivoting with bounded per-candidate attempt counts.

---

## 2. GAP-1 — PRE-EXECUTION PRIORITIZATION (QUALIFIED / NULL)

Mechanism: `priority_score = probability × (0.5 + 0.5 × quality)`. Candidates
are ranked before execution.

Evidence status:
- The mechanism is implemented and tested.
- Under the fair per-visit-cap protocol, the priority component (DUMB − PRIORITY-ONLY) = 0.
- A total-budget ablation shows routing value in a best-case bound (A=1 vs B=3), but this is label-correlated and not a fair independent win.

Tier: **B1 — qualify only.** Gap-1 is necessary scaffolding for pivot ordering,
not an independently measured win under the current protocol.

---

## 3. GAP-2 — STATE-AWARE FAILURE-THRESHOLD PIVOT (PRIMARY CONTRIBUTION)

Mechanism: per-candidate `attempt_count`; pivot when `attempt_count >= max_attempts`;
advance index and reset counter; terminate when no candidates remain.

Verified results (fair 4-agent ablation, identical per-visit cap):

VAPT corpus (12 CVEs):
- T=2: DUMB=96, SMART=19, pivot component = +77
- T=5: DUMB=240, SMART=40, pivot component = +200

Agnostic sparse family (`sparse_success`, T=5):
- pivot component = +772 (30 seeds, 50 candidates)

Cross-domain evidence: one synthetic family only.

Tier: **A2 — may claim**, backed by E2.

---

## 4. ARCHITECTURE

- Domain-independent core: `decision_engine/core/{schemas,assessor,executor,engine}`
- VAPT adapter: `decision_engine/adapters/vapt_adapter.py` (sole boundary)
- Core imports only `decision_engine.core.*`; 0 VAPT code imports in core.
- Original VAPT prototype `core/` is frozen and serves as the evidence baseline.

---

## 5. METHODOLOGY

- Fair 4-agent ablation: DUMB, PIVOT-ONLY, PRIORITY-ONLY, SMART.
- Identical per-visit caps T ∈ {1, 2, 3, 5}.
- Decomposition:
  - priority_component = DUMB − PRIORITY-ONLY
  - pivot_component = PRIORITY-ONLY − SMART
- Seeds: ≥30 per condition; 6 synthetic families × 4 caps × 10 rankers.
- VAPT corpus: 12-CVE PoC corpus with curated labels + EPSS enrichment.
- Loopback observed validation (L2): real subprocess against `127.0.0.1`, stubbed assessor, n=2, single run.

---

## 6. EXPERIMENTS

| Experiment | Tier | Status |
|------------|------|--------|
| Fair VAPT benchmark | L1 (sim) | DONE / REPRODUCED |
| Fair agnostic benchmark | L1 (sim) | DONE / REPRODUCED |
| Loopback observed pivot (S2) | L2 | DONE / OBSERVED |
| Loopback observed success (S1) | L2 | DONE / OBSERVED |
| Total-budget Gap-1 experiment | L1 | NOT DONE (optional) |
| Multi-run loopback variance | L2 | NOT DONE (optional) |
| Level-3 Docker isolation | L3 | PARKED (daemon unavailable) |
| LLM-assessor calibration | — | NOT DONE (optional) |

---

## 7. VERIFIED RESULTS (WHAT IS ACTUALLY PROVEN)

1. **Gap-2 pivot saves attempts under fair cap (VAPT):** +77 at T=2, +200 at T=5.
2. **Gap-2 pivot saves attempts (agnostic):** +772 at T=5 on `sparse_success`.
3. **Priority component = 0** under fair per-visit cap.
4. **Bounded termination + pivot** confirmed by loopback: exactly 2 attempts, pivot, COMPLETED, no 3rd attempt.
5. **Domain-independent architecture** proven by import audit (0 VAPT imports in core).
6. **Regression safety:** TRACK0 39/39, TRACK1 16/16.

---

## 8. EVIDENCE TIERS

| Level | Name | Status |
|-------|------|--------|
| L1 | Simulation / controlled synthetic | ACHIEVED |
| L2 | Loopback observed validation | ACHIEVED (stubbed assessor, n=2, single run) |
| L3 | Container-isolated observed | NOT ACHIEVED (parked) |
| L4 | Real-world / multi-target | OUT OF SCOPE |

---

## 9. LIMITATIONS

1. Loopback is L2, not L3.
2. Observed assessor is deterministic/stubbed; LLM accuracy unvalidated.
3. Small observed n=2, single run.
4. Corpus modules are synthetic stubs; outcomes are curated/controlled in simulation.
5. Gap-1 independent win unproven under fair cap.
6. Cross-domain experimental evidence = Gap-2 only, one synthetic family.
7. No real-world exploitation validation.
8. No speed claim; time_saved = −8.5s in current evidence.

---

## 10. NOVELTY POSITION

- **Defensible differentiation:** explicit per-candidate attempt counter + configurable threshold pivot + fair-cap ablation under identical cap.
- **Honest qualifiers:** bounded retry/loop-prevention ideas exist in Reflexion/ReAct/PIVOT; our contribution is the *reproducible fair-validated isolation* of the pivot mechanism, not a grand architectural first.
- **Not claimed:** universal domain independence, real-world superiority, better-than-all systems, first autonomous VAPT system.

---

## 11. EXPLICIT NON-CLAIMS

The following are **not** claimed and must not appear in any paper/thesis revision:

- Complete autonomous VAPT
- Universal / provably-general domain independence
- LLM-assessor accuracy on unseen CVEs
- Real-world VAPT superiority
- Better than all existing autonomous pentest systems
- Docker-validated / container-isolated results
- Faster execution
- Multi-target real-world validation
- Production-ready platform

---

## 12. QUESTIONS REQUIRING SUPERVISOR JUDGMENT

1. Is the current evidence tiering (L1 + L2) sufficient for the intended venue?
2. Does the supervisor require a total-budget Gap-1 experiment before submission?
3. Does the supervisor require multi-run loopback variance (n=2 → ≥5)?
4. Is the cross-domain evidence (one synthetic family) acceptable, or should we expand families?
5. Are the related-work qualifiers (Strix/PentestGPT/HackSynth/etc.) deep enough?
6. Should the paper be positioned strictly as a mechanism paper, or does the venue allow broader claims with stronger caveats?
7. Are the thesis TODO placeholders (candidate/supervisor/university) acceptable as-is, or should they be filled now?

---

## 13. WHAT IS FROZEN

- `core/`
- `decision_engine/core/`
- `tests/`
- `decision_engine/tests/`
- `datasets/`
- benchmark logic

No source code, tests, datasets, or benchmark logic were modified during P0 corrections.

---

*End of SUPERVISOR_HANDOFF.md*
