# AUTHORITY REVIEW MANIFEST

_Concise navigation document for an INDEPENDENT TOP-LEVEL EVIDENCE REVIEW of the
AI VAPT Framework. This is NOT a substitute for the full handover report — it is a
map to it and the supporting evidence files. Generated 2026-08-24 after the
implementation/remediation phase was PAUSED._

---

## 1. CURRENT HEAD COMMIT
`1c7b9995be13bd3360eb5fdb5bfb1920432b9514`
(docs: add final project handover evidence report)

## 2. PREVIOUS BASELINE COMMIT
`31ccd06` — baseline: verified AI VAPT framework (audit 2026-08-21)
(The commit from which all P0–P4 governance tasks were executed.)

## 3. CURRENT BRANCH
`master`

## 4. CURRENT TEST COMMAND AND RESULT
```
venv/bin/python -m pytest tests/ -q
29 passed in 0.12s   (verified 2026-08-24)
```
All offline, deterministic. No coverage percentage claimed (coverage.py not run).

## 5. MASTER PLAN STATUS
Plan: `docs/project_management/02_MASTER_PLAN.md` (14-task plan).
- DONE / VERIFIED (10 tasks): T-SAFE, T-BENCH-LOOP, T-TESTS (+ext), T-CORPUS,
  T-BENCH-VAR, T-GAP1-VALID (+v2), T-OPENAI, T-CHECKPOINT, T-REQPIN, T-DEADCODE.
- TODO (3 tasks): T-GITHUB, T-README, T-UI.
- BLOCKED (1 task): T-DOCKER (Docker daemon down).

## 6. COMPLETED TASKS WITH COMMIT HASHES
| Task | Commit |
|------|--------|
| T-SAFE (P0) | `e5d31ba` |
| T-BENCH-LOOP (P0) | `9b67dac` |
| T-TESTS (P3) | `62b73ef` (+ ext `7617102`) |
| T-CORPUS (P1) | `3fa2148` + `ecdf814` |
| T-BENCH-VAR (P3) | `c7de8d8` |
| T-GAP1-VALID (P1) | `eda98c3` + `5ba1e10` (+ v2 `57be1f7`) |
| T-OPENAI (P2) | `25e4137` |
| T-CHECKPOINT (P2) | `f1561be` |
| T-REQPIN (P3) | `9b0fe96` |
| T-DEADCODE (P4) | `c1f4d2b` |

## 7. REMAINING TODO / BLOCKED TASKS
- **T-GITHUB (P3, TODO)** — verify GitHub PoC fetch; needs GITHUB_TOKEN (optional for DONE; mock suffices).
- **T-README (P4, TODO)** — README still shows stale SMART=1 table (README.md:77) vs actual 5; real-mode wording must align with T-SAFE.
- **T-UI (P4, TODO)** — Streamlit dashboard imports clean; interactive run unverified; `unsafe_allow_html=True` on logs (app.py) needs review.
- **T-DOCKER (P1, BLOCKED)** — Docker daemon down; thesis-critical REAL-OBSERVED validation unavailable. NOT started.

## 8. EXACT PATH TO HANDOVER REPORT
`docs/project_management/FINAL_PROJECT_HANDOVER_REPORT.md`
(556 lines; PARTS 1–15; all claims mapped to artifacts.)

## 9. KEY EVIDENCE FILE PATHS
- Master plan: `docs/project_management/02_MASTER_PLAN.md`
- Task register: `docs/project_management/03_TASK_REGISTER.md`
- Research traceability: `docs/project_management/06_RESEARCH_TRACEABILITY.md`
- Test status: `docs/project_management/07_TEST_STATUS.md`
- Benchmark evidence: `docs/project_management/09_BENCHMARK_EVIDENCE.md`
- Risk register: `docs/project_management/08_RISK_REGISTER.md`
- Decision log: `docs/project_management/05_DECISION_LOG.md`
- Independent reviews: `docs/project_management/external_reviews/` (claude_p0_review_T-SAFE_20260824.md, claude_p0_review_T-BENCH-LOOP_20260824.md, claude_review_T-TESTS-ext_T-OPENAI_T-GAP1v2_20260824.md)

## 10. MOST IMPORTANT FILES FOR REVIEW
- **GAP-1 implementation:** `core/exploit_assessor.py` (`assess_exploit_quality`, `get_llm`) + `core/schemas.py` (`ExploitAssessment`, `Finding.priority_score`) + `core/agent_graph.py:59` (`rank_findings`).
- **GAP-2 implementation:** `core/agent_graph.py` (`AgentState`, `evaluate_decision`, `pivot_node`, `execute_node`); loop instrumentation in `tests/evaluate.py:74-86`.
- **Executor safety:** `core/executor.py` (`Executor.execute`, `_connectivity_probe`, danger_mode gating, `_parse_module_output`).
- **Benchmark implementation:** `tests/evaluate.py` (SMART vs DUMB), `tests/benchmark_var.py` (5-seed variance), `tests/gap1_ablation.py` + `tests/ablation.py` (GAP-1 ablations).
- **Test suite:** `tests/test_core.py` (13), `tests/test_ttests_gaps.py` (5), `tests/test_openai_provider.py` (3), `tests/test_checkpoint.py` (8), `tests/conftest.py` (offline guard).

## 11. TOP 5 UNANSWERED QUESTIONS REQUIRING AUTHORITY DECISIONS

1. **Is T-DOCKER mandatory for the intended thesis claims?**
   The framework is proven under SIMULATION only. Real-observed exploit validation
   (T-DOCKER) is blocked. Decision needed: accept simulation proof-of-mechanism as
   sufficient for the thesis, OR require a live sanctioned-lab run before finalization.

2. **Is current GAP-1 evidence sufficient?**
   Two ablations prove the mechanism (routing efficiency), but assessor accuracy on
   UNSEEN CVEs is unvalidated (best-case upper bound, corpus reliability→outcome
   100% correlated). Decision needed: is proof-of-mechanism enough, or is a labelled
   assessor-accuracy study required?

3. **Is current GAP-2 evidence sufficient?**
   Zero loop events measured across 5 seeds in simulation; real-mode pivot unverified
   (T-DOCKER). Decision needed: is simulated pivot guarantee sufficient evidence?

4. **Should T-README and T-UI be completed before implementation freeze?**
   Both are P4 polish. T-README fixes a stale metric (SMART=1 vs 5) and aligns
   real-mode wording; T-UI needs an interactive check + `unsafe_allow_html` review.
   Decision needed: mandatory pre-freeze, or defer to thesis write-up?

5. **Should T-GITHUB remain optional?**
   Live GitHub PoC fetch is unverified (no token); not required for the core claims.
   Decision needed: keep optional, or complete mock + one documented live fetch?

---

_Implementation status is FROZEN pending the authority decision recorded in
01_PROJECT_STATE.md. No offensive PoC execution, danger_mode, or external
target contact is permitted in this review phase._
