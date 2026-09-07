# SUPERVISOR REVIEW CHECKLIST — ai_vapt_framework

Use this checklist to evaluate whether the thesis/research paper is ready for
final submission or whether specific experiments/revisions are required.

---

## MANDATORY — MUST ADDRESS BEFORE SUBMISSION

### M1. Claim-Evidence Consistency
- [ ] Every quantitative claim in the thesis maps to a reproducible evidence anchor.
- [ ] VAPT +77/+200 and agnostic +772 are the only current active quantitative pivot claims.
- [ ] No document presents +772 as a current active result.

### M2. Evidence Tier Accuracy
- [ ] L1 simulation claims are labeled as simulation.
- [ ] L2 loopback claims are labeled as observed loopback (not Docker-isolated, not real-world).
- [ ] L3/L4 claims are absent.

### M3. Claim Discipline
- [ ] No "complete autonomous VAPT" claim.
- [ ] No "universal domain independence" claim.
- [ ] No "faster" or "better than all" claim.
- [ ] No Docker-validated claim.
- [ ] No real-world exploitation claim.
- [ ] No unsupported LLM-assessor accuracy claim.

### M4. Gap-1 Qualification
- [ ] Gap-1 is explicitly qualified as null/independent under fair per-visit cap.
- [ ] Thesis does not imply Gap-1 is an independent win.

### M5. Thesis Completeness
- [ ] 21 sections present (title, declaration, abstract, intro, problem, related work, gaps, RQ, hypotheses, method, architecture, Gap-1, Gap-2, generalized engine, methodology, datasets, results, discussion, threats, limitations, future work, conclusion, references, appendix).
- [ ] TODO placeholders for candidate/supervisor/university are either filled or explicitly noted as intentional.

---

## OPTIONAL — STRENGTHENING (NOT BLOCKING)

These items may improve the thesis/paper but are not required for a defensible
mechanism submission.

### O1. Total-Budget Gap-1 Experiment
- **Question:** Is the total-budget ablation (A=1 vs B=3) sufficient, or does the supervisor want a fair total-budget protocol?
- **Effort:** Low–medium.
- **Impact:** Could upgrade B1 → A if positive and fairly isolated.
- **Risk:** May still be label-correlated; does not change Gap-2 primary claim.

### O2. Multi-Run Loopback Variance
- **Question:** Is n=2, single run acceptable, or does the supervisor want 5–10 runs?
- **Effort:** Low.
- **Impact:** Strengthens L2 robustness; no protocol change needed.

### O3. Broader Cross-Domain Sweep
- **Question:** Is one synthetic family enough, or does the supervisor want 2–3 additional families?
- **Effort:** Low (seeded benchmark already supports 6 families).
- **Impact:** Strengthens B2; does not change primary claim.

### O4. LLM-Assessor Calibration
- **Question:** Does the supervisor want a calibration note or small study?
- **Effort:** Medium.
- **Impact:** Strengthens B3; not required for current claims.

### O5. Related-Work Depth
- **Question:** Are title-only inspections of HackSynth/VulnBot/PentestAgent/xOffense/RapidPen sufficient?
- **Effort:** Low (reading papers).
- **Impact:** Strengthens novelty positioning; does not change claims.

### O6. Per-Family CI Table
- **Question:** Should results include a compact per-family mean ± 95% CI table?
- **Effort:** Low (benchmark already computes CIs).
- **Impact:** Strengthens statistical reporting.

---

## EXPERIMENTS THAT ARE NOT REQUIRED (DO NOT START)

| Experiment | Reason |
|------------|--------|
| Level-3 Docker lab | Environment blocked; not required for mechanism paper |
| Real-world multi-target VAPT | C-prohibited; out of scope |
| Full VAPT platform (Stage B) | Separate track; post-thesis |
| New benchmark bias experiments | Biased figures already retired |
| LLM-assessor accuracy on unseen CVEs | Unvalidated; would require new protocol |

---

## SUPERVISOR DECISION MATRIX

| If supervisor says... | Then... |
|-----------------------|---------|
| "Submit as-is" | Fill thesis TODOs, finalize references, submit. |
| "Add total-budget Gap-1 experiment" | Modify `fair_benchmark.py` cap semantics (requires explicit authorization). |
| "Expand cross-domain evidence" | Re-run `fair_benchmark.py` with additional families (docs update only). |
| "Deepen related work" | Read and summarize additional papers; update R1/R2/docs. |
| "Add multi-run loopback variance" | Re-run `tests/run_tdocker_scenarios.py` with additional seeds. |
| "Do not submit yet" | Address specific blocking items; do not broaden claims. |

---

*End of SUPERVISOR_REVIEW_CHECKLIST.md*
