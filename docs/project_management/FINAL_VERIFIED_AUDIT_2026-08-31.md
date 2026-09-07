# CURRENT PROJECT STATUS — VERIFIED AUDIT
_Audit date: 2026-08-31. Auditor: Hermes (read-only forensic audit). HEAD inspected: 4dc0599.
No files modified, no commits made. Every factual claim below was traced to a live
file/grep/test-run, not to prior agent reports._

## 1. Executive Summary
The project is in a STRONG, submission-adjacent state. The research engine is implemented
and tested (TRACK0 39/39, TRACK1 16/16, reproduced live this session). The primary
contribution (Gap-2 bounded pivot) is fair-validated and reproducible (+77 at T=2, +200 at
T=5 on the VAPT corpus, confirmed live). A complete 21-section thesis exists and is
claim-disciplined. The loopback L2 observed validation is genuine (real subprocess to
127.0.0.1, two failed attempts then pivot, COMPLETED). Two evidence artifacts cited in the
documents are NOT reproducible from the current repo and must be corrected before
supervisor submission: (a) the agnostic "+175" figure (live fair bench gives +772 for
sparse_success at T=5), and (b) the "28,800-row JSONL" raw data file (no project .jsonl
exists). Neither undermines the VAPT Gap-2 result, but both are factual errors in the
manuscript/register that a careful reviewer would catch.

## 2. Repository State
- HEAD: `4dc0599` (A7 thesis assembly). Branch: `master`. Working tree: clean except the
  two untracked governance docs created earlier this session (MASTER_RESEARCH_PROJECT_REPORT.md,
  PAPER_REQUIREMENTS_MATRIX.md) — both since committed at 70cf0ff; current tree clean.
- Commits since A0: 4dc0599, b7a9f06 (A6), 338159b (A4), 4f345d4 (A3), 70cf0ff (A2) — all
  docs-only except none (no source changed since the engine freeze at 7001c61).
- Structure verified: core/, decision_engine/{core,adapters,benchmarks,tests},
  datasets/, data/experiment_runs/, docs/project_management/. No missing expected top-level
  dirs. The 12_GO_NO_GO.md, R3_CLAIM_REGISTER.md, MASTER_RESEARCH_PROJECT_REPORT.md,
  THESIS_DRAFT_v0.1.md, THESIS_FINAL.md all present.

## 3. What Has Actually Been Built
- Generalized decision engine (`decision_engine/core/`): LangGraph state machine with
  per-candidate `attempt_count`, configurable `max_attempts` threshold, deterministic pivot
  node, bounded termination. VERIFIED by source (engine.py:42,72,90,98,107-114,133-150).
- ActionCandidate schema + priority_score formula `prob × (0.5+0.5×quality)`
  (schemas.py:77, QUALITY_WEIGHT:26). VERIFIED.
- Assessor: offline deterministic scorer + optional local-Ollama hook (assessor.py:19,28;
  vapt_adapter.py:70). VERIFIED.
- Executor abstraction: simulation (label-resolved) + real (pluggable execute_fn)
  (executor.py:26-52). VERIFIED.
- VAPT adapter: sole boundary mapping CVE→ActionCandidate, EPSS→probability, labels→
  ground_truth (vapt_adapter.py:52,70,89). VERIFIED.
- Checkpoint/resume: save_checkpoint (engine.py:172), load_checkpoint (engine.py:183).
  VERIFIED by test.
- Fair 4-agent ablation benchmark (fair_benchmark.py, fair_vapt_benchmark.py). VERIFIED
  (re-ran live, reproducible).
- Loopback L2 harness (tests/run_tdocker_scenarios.py). VERIFIED (real subprocess, logs).
- Original frozen VAPT prototype (core/, 39 tests). VERIFIED.

## 4. What Has Actually Been Tested
- TRACK0 `tests/`: **39 passed** (reproduced live). Covers checkpoint/resume, executor
  allowlist (fail-closed), danger-mode mock, adapter. NOT superficial — these exercise real
  safety boundaries (tests/test_executor_allowlist.py, test_danger_mode_mock.py,
  test_checkpoint.py).
- TRACK1 `decision_engine/tests/`: **16 passed** (reproduced live) — engine pivot/bound,
  priority ordering, checkpoint, fair benchmark 4 tests.
- Caveat: several TRACK0/TRACK1 tests run in simulation mode (label-resolved). The
  loopback observed tier is exercised by run_tdocker_scenarios.py (manual/harness, not in
  the pytest suite). This is acceptable but means "tests pass" ≠ "observed execution
  validated by CI".

## 5. What Experiments Have Actually Been Run
- Fair VAPT benchmark: 12-CVE corpus, 4 agents, caps T∈{1,2,3,5}, seeds 30 (ran live this
  session). Decomposition computed (priority_component = DUMB−PRIORITY-ONLY = 0 at all caps;
  pivot_component = PRIORITY-ONLY−SMART = +77/+200). VERIFIED reproducible.
- Fair agnostic benchmark: 6 synthetic families × 50 candidates × 30 seeds × 4 caps × 10
  rankers (ran live this session). Pivot component positive at every cap (range +750..+910
  across families at T=5; sparse_success = +772 at T=5). VERIFIED reproducible.
- Loopback L2: 2 scenarios (S1 success, S2 failure→pivot) against local Flask emulator on
  127.0.0.1, with emulator access logs + module I/O json. VERIFIED by reading artifacts.
- Biased old benchmarks (5-vs-21, 8-vs-17, agnostic 8-vs-17): RETIRED, not used as evidence.

## 6. Verified Experimental Results
- VAPT corpus (12 CVEs, 5 true successes), T=2: DUMB 96 → SMART 19 → **pivot +77** (LIVE).
- T=5: DUMB 240 → SMART 40 → **pivot +200** (LIVE).
- priority_component (DUMB−PRIORITY-ONLY) = **0** at every cap (LIVE) → Gap-1 null confirmed.
- Loopback S2: candidate C executed twice (FAIL_TIMEOUT ×2), then pivot to next candidate,
  terminated_status COMPLETED, no 3rd attempt (LIVE, emulator log + json).
- **DISCREPANCY — agnostic "+175":** thesis/register cite `fair_benchmark.py output`
  claiming "+175 on agnostic sparse family at T=5". Live fair_benchmark.py at T=5 gives
  **+772 for sparse_success** (and +910..+750 for other families). The "+175" figure is
  NOT reproducible from the current fair benchmark. Source of +175 is unverified (possibly
  an older config or the retired biased agnostic benchmark). MUST be corrected.
- **DISCREPANCY — "28,800-row JSONL":** master report claims JSONL raw data exists
  (28,800 rows). No project `.jsonl` artifact is present in the repo (only venv package
  noise). Benchmark is re-runnable and seeded, so raw data is REGENERABLE, but the "raw
  data file exists" claim is unbacked. Statistics can be computed on regeneration.

## 7. Evidence-Tier Status
- L1 (Simulation): ACHIEVED — all benchmark numbers (labels/ground_truth).
- L2 (Loopback observed): ACHIEVED — S1/S2 real subprocess to 127.0.0.1, emulator-corroborated,
  fail-closed allowlist. Stubbed assessor; n=2; single run.
- L3 (Container-isolated): NOT ACHIEVED — Docker daemon unavailable; harness ran loopback only.
- L4 (Real-world/multi-target): NOT ACHIEVED — out of scope; C3/C4/C6 prohibited.

## 8. Gap-1 Status
- Mechanism IMPLEMENTED + TESTED (priority_score, ordering, deterministic assessor).
- Independent efficiency benefit: NULL under fair per-visit cap (priority_component = 0,
  verified live). Consistent with B1 (qualify-only).
- Total-budget best-case bound exists (tests/ablation.py A=1 vs B=3) but is label-correlated
  and NOT a fair win.
- LLM-assessor accuracy on unseen CVEs: UNVALIDATED (C2 prohibited).
- Verdict: qualified secondary; do NOT promote to A without a total-budget experiment.

## 9. Gap-2 Status
- Mechanism IMPLEMENTED + TESTED + FAIR-VALIDATED. Primary contribution.
- VAPT pivot +77/+200 reproduced live. Bounded termination + deterministic pivot verified
  by code + loopback.
- Cross-domain (agnostic) pivot positive but the specific "+175" number is wrong (see §6).
- Verdict: defensible A2 claim; correct the agnostic figure.

## 10. Architecture Verification
- Domain-independence: VERIFIED — 0 real VAPT imports in decision_engine/core/ (grep live).
  Engine imports only decision_engine.core.*; vapt_adapter.py is the sole boundary.
- This is ARCHITECTURAL independence, proven by code inspection + import audit, NOT
  experimental generalization across many live domains (only VAPT + 1 synthetic family
  exercised → B2). Honest as written.

## 11. Thesis Verification
- THESIS_FINAL.md: 359 lines, 25 `## ` sections = title page + declaration + 21 chapters +
  references + appendix B. NOT a skeleton (the earlier A7 agent skeleton was replaced by the
  full assembly at 4dc0599). VERIFIED complete.
- All 21 required chapters present (abstract, intro, problem, related work, gaps, RQ,
  hypotheses, method, architecture, Gap-1, Gap-2, generalized engine, VAPT instantiation,
  methodology, datasets, results, discussion, threats, limitations, future work, conclusion).
- Claim traceability appendix present (every sentence → R3 tier → anchor).
- References present; fair-benchmark reproduction command present.
- TODO placeholders: candidate name, supervisor name, university (intentional, for you to fill).
- Carries the unverified +175 (see §6) — must be corrected.

## 12. Research Paper Verification
- The "research paper" and the thesis are the same artifact (THESIS_FINAL.md / DRAFT). No
  separate shorter paper draft exists. They are mutually consistent. The +175 error propagates
  from the register into both.

## 13. Claim Audit
| Claim | Evidence | Actual status | Safe to claim? | Required qualification |
|-------|----------|---------------|---------------|------------------------|
| Bounded pivoting | engine.py:112,98; live | VERIFIED | YES (A2) | none |
| Reduced wasted attempts (VAPT) | live +77/+200 | VERIFIED | YES (A2) | identical per-visit cap |
| Domain-independent architecture | grep 0 leaks | VERIFIED | YES (A1) | architectural only; B2 cross-domain |
| Gap-1 prioritization | schemas.py:77 | IMPLEMENTED | B1 only | priority_component=0 under fair cap |
| Gap-2 pivoting | live | VERIFIED | YES (A2) | — |
| LLM assessor | assessor.py | offline only | B3 | unvalidated on unseen CVEs (C2) |
| VAPT capability | adapter | DEMO only | A5 | 12-CVE PoC corpus, synthetic stubs |
| Autonomous VAPT (full) | — | NOT BUILT | NO (C-prohibited) | Track B future |
| Real-world validation | — | NONE | NO (C3) | — |
| Container validation | — | NONE | NO (C5) | L2 loopback only |
| Multi-target validation | — | NONE | NO (C6) | — |
| Generalization | 1 synthetic family | PARTIAL | B2 | more domains would strengthen |
| Performance/speed | time_saved −8.5s | NEGATIVE | NO "faster" | never claim speed |
| Comparison vs prior systems | R1/R2 | PARTIAL | qualified | no "better than all" (C4) |
| **Agnostic +175** | cited fair_benchmark | **NOT REPRODUCED (+772 live)** | **NO — FIX** | replace with correct number |

## 14. Implemented vs Unvalidated vs Planned vs Not Required
1. IMPLEMENTED+VERIFIED: engine, schema, assessor, executor(sim+real), adapter, checkpoint,
   fair benchmark, loopback harness, original VAPT prototype, tests (55 total).
2. IMPLEMENTED, NOT FULLY VALIDATED: Gap-1 independent benefit (null under fair cap); LLM
   assessor accuracy (offline only); cross-domain generalization (1 family); loopback (n=2,
   single run, stubbed assessor).
3. DOCUMENTED/PLANNED, NOT IMPLEMENTED: Level-3 Docker lab; multi-run loopback variance;
   total-budget Gap-1 experiment; LLM calibration study.
4. NOT REQUIRED for current contribution (Track B, future): URL/IP ingestion, recon,
   Nmap/Nuclei, finding normalization, candidate generation, multi-target orchestration,
   UI/dashboard, auto-fix.

## 15. Remaining Research Tasks
- P0: Correct the agnostic +175 figure in thesis + register + matrix (replace with the
  verified live number, e.g. sparse_success +772 at T=5, or re-run a defined config that
  yields the cited value and state it precisely).
- P0: Either commit the benchmark JSONL raw output, or change the "28,800-row JSONL exists"
  wording to "regenerable via fair_benchmark.py (seeded)".
- P1: Statistical characterization (mean ± 95% CI already computed by the bench; consider
  reporting per-family CIs and a small effect-size note).
- P2: Loopback multi-run variance (n=2 → 5–10 runs) if a reviewer wants robustness.
- P2: Total-budget Gap-1 experiment only if a reviewer blocks on Gap-1.
- P3: Level-3 Docker; LLM calibration; broader cross-domain sweep.

## 16. Remaining Thesis Tasks
- Fill candidate/supervisor/university TODO fields.
- Fix +175 (see §15 P0) in THESIS_FINAL.md §1,§7,§15,§20,§23.
- Optional: expand Related Work §4 with one deeper read of Strix/PentestGPT if supervisor
  wants stronger novelty positioning.
- Optional: add a one-line statistical note (CI) to Results.

## 17. Remaining Engineering Tasks
- NONE required for the current contribution. The engine is frozen and green.
- If +175 fix requires regenerating benchmark numbers, that is a benchmark re-run (docs
  update), not engine change.

## 18. Supervisor-Ready Status
**YES, WITH SPECIFIC CLEANUP.** The project is substantively ready: strong mechanism, fair
validated primary result, honest Gap-1 null, complete claim-disciplined thesis, genuine L2
evidence. Before showing the supervisor, fix the two factual errors (§15 P0): the agnostic
+175 number and the JSONL-exists wording. These are 30-minute doc corrections, not research
gaps. Everything else is supervisor-presentable as-is.

## 19. Final Submission Roadmap
- RESEARCH WORK: done (Gap-2 fair-validated; Gap-1 null reported). Fix +175 only.
- THESIS WORK: THESIS_FINAL.md complete; fill TODOs; fix +175; add CI note.
- SOFTWARE ENGINEERING: none required.
- STATISTICAL ANALYSIS: CIs already produced by bench; optional per-family CI table.
- SUPERVISOR FEEDBACK: hand over; incorporate A8 comments.
- FINAL SUBMISSION: A9 after feedback.

## 20. Highest-Priority Next Actions
1. **P0 — correct +175** across thesis/register/matrix (use verified live agnostic number).
2. **P0 — fix JSONL wording** (regenerable, not a committed file) in master report + register.
3. Fill thesis TODO fields (candidate/supervisor).
4. Hand to supervisor (A8).
5. Incorporate feedback → A9.

## 21. Prompts for Other Agents
### Task ID: P0-FIX-175
### Objective: Correct the unverified agnostic "+175" figure in the manuscript/register.
### Why it matters: The number is cited as fair_benchmark.py output but is not reproducible
(live gives +772 for sparse_success at T=5); a reviewer will catch it.
### Files/artifacts to inspect: docs/project_management/THESIS_FINAL.md (§1,§7,§15,§20,§23),
R3_CLAIM_REGISTER.md (A2), PAPER_REQUIREMENTS_MATRIX.md, MASTER_RESEARCH_PROJECT_REPORT.md
(§21,§206,§224,§338), decision_engine/benchmarks/fair_benchmark.py.
### Exact agent prompt:
"ROLE: DOCUMENTATION/RESEARCH agent (docs-only, no source changes, no commit).
OBJECTIVE: Replace every occurrence of the agnostic pivot '+175 at T=5' with the NUMBER
ACTUALLY PRODUCED by running `python decision_engine/benchmarks/fair_benchmark.py --caps 5
--seeds 30` for the sparse_success family (live value ≈ +772 at T=5; confirm by running it).
State the family name and cap explicitly (e.g. 'sparse_success family, T=5, pivot component
+772'). Do NOT invent a number — use the benchmark's live output. Update THESIS_FINAL.md,
R3_CLAIM_REGISTER.md (A2 row), PAPER_REQUIREMENTS_MATRIX.md, and MASTER_RESEARCH_PROJECT_REPORT.md
consistently. Keep VAPT +77/+200 unchanged (they are verified). Do NOT modify any .py.
RETURN the before/after lines changed. STOP: report only, no commit."
### Expected deliverables: all 5 docs cite the verified agnostic number; +175 removed.
### Verification: Hermes re-greps for "175" in docs; re-runs fair_benchmark.py to confirm the
cited number matches; confirms VAPT +77/+200 untouched.
### Must NOT change: source code, tests, datasets, VAPT +77/+200 figures.

### Task ID: P0-FIX-JSONL
### Objective: Fix the "28,800-row JSONL exists" claim (no such file is committed).
### Why it matters: Misstates evidence availability; raw data is regenerable, not present.
### Files: MASTER_RESEARCH_PROJECT_REPORT.md (§224,§338), R3_CLAIM_REGISTER.md (E2).
### Exact agent prompt:
"ROLE: DOCUMENTATION agent (docs-only). OBJECTIVE: Change wording that says raw JSONL data
'exists' (28,800 rows) to state it is REGENERABLE via `python decision_engine/benchmarks/
fair_benchmark.py` (seeded RNG, 6 families × 50 × 30 seeds × 4 caps × 10 rankers = 28,800
rows) and that statistics (mean ± 95% CI) are computed by the benchmark at run time. Optionally
actually run the bench with JSONL dump enabled and commit the .jsonl under data/ if you want a
real artifact — but if no JSONL dump flag exists, do NOT claim a file exists. RETURN changed
lines. STOP: no commit."
### Expected: no false 'exists' claim; accurate regenerability statement.
### Verification: grep for 'JSONL' / '28,800' in docs; confirm wording is 'regenerable'.

### Task ID: P1-STATS (optional)
### Objective: Produce a per-family pivot-component table with mean ± 95% CI for the thesis.
### Why: Strengthens statistical reporting; bench already prints means.
### Files: fair_benchmark.py output, THESIS_FINAL.md §15.
### Exact agent prompt: "ROLE: RESEARCH agent (read/analysis only). Re-run fair_benchmark.py
with --seeds 30 --caps 1 2 3 5; extract per-family pivot_component means at each cap; add a
compact table + CI note to THESIS_FINAL.md §15 (docs-only, no commit). Do not alter conclusions."
### Verification: table numbers match a fresh run.

### Task ID: A8-SUPERVISOR (your action, not an agent)
Hand THESIS_FINAL.md (post P0 fixes) to your supervisor. Collect feedback; return it here for
targeted prompts.

## 22. Things We Should NOT Do Yet
- Build the full VAPT platform (URL/IP/recon/Nmap/Nuclei/UI) — Track B, post-thesis, not a
  research requirement.
- Claim L3/L4, real-world, multi-target, "faster", "better than all", universal independence
  — all C-prohibited.
- Redesign the assessor to force a positive Gap-1 — would manufacture a result.
- Expand to many domains merely for appearance — B2 is acceptable as-is.
- Run arbitrary live targets — only authorized 127.0.0.1 lab.

## 23. Final Verdict
**What we really accomplished:** A complete, domain-independent autonomous decision-and-pivot
engine with a fair-validated primary contribution (Gap-2 bounded failure-threshold pivot:
reproduced +77 wasted-request reduction at T=2 and +200 at T=5 on a 12-CVE VAPT corpus, plus
positive cross-domain pivot). The engine is tested (55 tests green) and architecturally
domain-independent (0 VAPT imports in core). A genuine Level-2 loopback experiment confirms the
pivot responds to real observed failure (two attempts then pivot, COMPLETED). Gap-1 is honestly
reported as a qualified null under fair evaluation. A complete, claim-disciplined 21-section
M.Tech thesis is written and committed.

**What remains:** Two factual corrections in the documentation — (1) the agnostic "+175"
figure is not reproducible from the current fair benchmark (live value ≈ +772 for sparse_success
at T=5) and must be replaced with the verified number; (2) the "28,800-row JSONL exists" claim
should say the data is regenerable, since no such file is committed. Fill the candidate/
supervisor name TODOs. That is all.

**What you should do next:** Run the P0-FIX-175 and P0-FIX-JSONL documentation prompts (or let
me apply them directly — they are docs-only and safe), fill your name/supervisor into
THESIS_FINAL.md, then show the thesis to your supervisor. No further development, no new
experiments, and no platform work are required to submit a credible, honest M.Tech thesis.
The research is done; only honesty-polish and your supervisor's input remain.
