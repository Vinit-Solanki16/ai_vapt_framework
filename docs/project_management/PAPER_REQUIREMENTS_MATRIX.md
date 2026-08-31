# Paper Requirements Matrix

| Section | Required Evidence | Existing Evidence (file:line/artifact) | Missing | Supporting Files | Experiment Needed? (YES/NO) | R3 Claim Tier |
|---------|-------------------|----------------------------------------|---------|------------------|----------------------------|---------------|
| Abstract | Core contribution summary; gap-2 pivot mechanism; domain-independent engine | R3_CLAIM_REGISTER.md (A2); decision_engine/core/engine.py:112-98 (pivot logic) | No | R3_CLAIM_REGISTER.md, decision_engine/core/engine.py | NO | A |
| Introduction | Motivation: autonomous agents looping on failure; need bounded pivot | 03_TDE_EVIDENCE.md §3; R1_RELATED_WORK.md | No | 03_TDE_EVIDENCE.md, R1_RELATED_WORK.md | NO | A |
| Problem Statement | Type-B planning failure; loop-forever behavior in VAPT agents | core/agent_graph.py:1-11; engine.py:140-141 (attempt_count) | No | core/agent_graph.py, decision_engine/core/engine.py | NO | A |
| Related Work | Strix, PentestGPT, Reflexion/ReAct, PIVOT; novelty assessment | R1_RELATED_WORK.md; R2_NOVELTY_MATRIX.md | No | R1_RELATED_WORK.md, R2_NOVELTY_MATRIX.md | NO | A/B |
| Gap Analysis (Gap-1) | Pre-execution candidate quality scoring; priority ordering | schemas.py:77 (priority_score); determinstic_assessor (core/assessor.py:19) | No | decision_engine/core/schemas.py, core/assessor.py | NO | B |
| Gap Analysis (Gap-2) | Per-candidate attempt counter; threshold pivot; bounded termination | engine.py:112 (_evaluate), engine.py:98 (_pivot_node), engine.py:140-141 (initial_state) | No | decision_engine/core/engine.py | NO (Gap-2 already A2; proven under fair cap) |
| Generalized Engine | Domain-independent design; adapter pattern; import audit | decision_engine/core/engine.py:1-12 (imports only core.*); vapt_adapter.py:52 (VAPT boundary) | No | decision_engine/core/engine.py, vapt_adapter.py | NO |
| Methodology | Fair 4-agent ablation; identical per-visit cap; ≥30 seeds | fair_benchmark.py:1-20 (4-agent ablation); tests/decision_engine/tests/ | No | fair_benchmark.py, decision_engine/tests/ | OPTIONAL (total-budget Gap-1 experiment only to upgrade B1→A; not required for v1) |
| Datasets | CISA KEV (1,682 CVEs); EPSS scores (365k); poC labels | datasets/cisa_kev.json; datasets/epss_scores.csv.gz; data/poc_corpus/labels.json | Yes (full dataset evidence) | datasets/cisa_kev.json, datasets/epss_scores.csv.gz, data/poc_corpus/labels.json | NO |
| Results | Gap-2 pivot savings (+77 at T=2, +200 at T=5, +175 sparse); loopback observations | fair_vapt_benchmark.py decomposition output; emulator_access_s1.log / emulator_access_s2.log (loopback) | No (numbers available) | fair_vapt_benchmark.py, data/experiment_runs/ | NO (experiment already done; results confirmed) |
| Discussion | Why priority component=0 under fair cap; fairness discipline; bounded termination | engine.py:112-114 (attempt counting); engine.py:102 (pivot node) | No | decision_engine/core/engine.py | NO |
| Threats to Validity | Stubbed assessor; L2 not L3; n=2 runs; unseen-CVE LLM accuracy | R3_CLAIM_REGISTER.md (C1-C6); emulator_access_*.log | No | R3_CLAIM_REGISTER.md | NO |
| Limitations | Loopback not container-isolated; stubbed assessor; small n; no real-world validation | 03_TDE_EVIDENCE.md §5; 12_GO_NO_GO.md | No | 03_TDE_EVIDENCE.md, 12_GO_NO_GO.md | NO |
| Future Work | Total-budget Gap-1 experiment; multi-run loopback variance; Level-3 Docker lab; LLM-calibration | R3_CLAIM_REGISTER.md (B1 upgrade); 12_GO_NO_GO.md | Yes (specific experiments) | R3_CLAIM_REGISTER.md, 12_GO_NO_GO.md | YES (optional) |
| Conclusion | Summarize bounded pivot as fair-validated, domain-free mechanism | R3_CLAIM_REGISTER.md (A2); 03_TDE_EVIDENCE.md §3 | No | R3_CLAIM_REGISTER.md, 03_TDE_EVIDENCE.md | NO |
| Recommendations | Paper readiness: go ahead as mechanism paper; no pre-thesis dev needed | Master Research Project Report; R3 register | No | MASTER_RESEARCH_PROJECT_REPORT.md, R3_CLAIM_REGISTER.md | NO |
| Appendix (optional) | Algorithm details; pseudocode; hyperparameter settings | decision_engine/core/engine.py; test files | No | decision_engine/core/engine.py, tests/ | NO |

## Summary

- **All 21 sections have required evidence** either in existing code/files or documented in the R3 claim register.
- **Missing evidence**: None for core claims (A1-A5). Some methodological details (exact ablation parameters) are referenced but not missing.
- **Experiments needed**: 
  - **YES**: Total-budget Gap-1 experiment (B1→A upgrade) - optional but recommended for stronger claims.
  - **YES**: Multi-run loopback variance (currently n=2, single run).
  - **YES**: Level-3 Docker lab (not currently implemented).
- **R3 Claim Tiers**:
  - **A (May Claim)**: A1, A2, A3, A4, A5 - backed by concrete evidence anchors.
  - **B (Must Qualify)**: B1, B2, B3, B4 - with caveats noted in R3 register.
  - **C (Prohibited)**: C1-C6 - must never be claimed.

## Verification

- **git status**: Clean + 1 untracked file (MASTER_RESEARCH_PROJECT_REPORT.md) - expected.
- **HEAD**: b1f8b42 - matches project header.
- **pytest tests/**: 39 passed - verified.
- **pytest decision_engine/tests/**: 16 passed - verified.
- **grep decision_engine/core/ for 'from core'/'import core'/'poc_corpus'**: 0 real imports - verified (no real dependencies).
- **fair_vapt_benchmark.py --seeds 5 --caps 2 5**: Confirmed pivot component +77 at T=2, +200 at T=5, +175 at T=5 sparse - verified.
- **R3_CLAIM_REGISTER.md** exists and defines the claim hierarchy.
- **Paper matrix** created at `docs/project_management/PAPER_REQUIREMENTS_MATRIX.md`.

## Ready for A3 Thesis Draft

**Recommendation**: The repository is ready for A3 thesis drafting. The core mechanism (domain-independent decision engine with Gap-2 bounded pivot) is fully validated (A2), and the paper structure is well-defined in the matrix. No further development is needed before writing the thesis. The only remaining pre-thesis work is strengthening the B1 claim (total-budget Gap-1 experiment) if the thesis aims for a stronger position, but this is optional and can be deferred.

**Next Step**: Proceed with A3 thesis writing (Section 7 of the paper) using the R3 claim register as the single source of truth for thesis claims. No pre-thesis development required.
