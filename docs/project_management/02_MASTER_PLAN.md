# 02 — MASTER PLAN (Authoritative)

_Last updated: 2026-08-21. Source: reconciliation of CURRENT_STATE_AUDIT.md,
VERIFICATION_BACKLOG.md, Claude independent review, and live test evidence._

> Supersedes docs/VERIFICATION_BACKLOG.md for execution. The 14 tasks below each
> carry full schema (TASK ID, Priority, Objective, Research-gap mapping, Exact problem,
> Evidence, Dependencies, Allowed files, Implementation requirements, Acceptance criteria,
> Exact test command, Implementation agent, Review agent). Full detail in the prior
> MASTER_REMEDIATION_PLAN.md (relocated here). This index is the scheduler's source of truth.

## Priority legend
- P0 = safety problem, invalid experiment, destructive/uncontrolled behavior
- P1 = research contribution not genuinely demonstrated
- P2 = correctness or integration defect
- P3 = test, reproducibility or robustness issue
- P4 = documentation, UI or polish

## Task register (ordered)
| ID | Pri | Objective (short) | Impl agent | Review agent | Deps | Status |
|----|-----|-------------------|-----------|-------------|------|--------|
| T-SAFE | P0 | Reconcile "real" executor (no offensive send by default / opt-in sandbox) | cyber (autonomous-vapt-agents) | verify-agent | — | DONE_VERIFIED (e5d31ba) |
| T-BENCH-LOOP | P0 | Measure loop avoidance (replace hardcoded smart_loop=0) | sw-dev (TDD) | mlops/eval | — | DONE_VERIFIED (9b67dac) |
| T-TESTS | P3 | Real pytest suite with assertions | sw-dev (TDD) | code-review | — | DONE_VERIFIED (62b73ef+7617102) |
| T-CORPUS | P1 | Grow PoC corpus to ≥8 CVEs | cyber | verify-agent | — | DONE_VERIFIED (3fa2148+ecdf814) |
| T-BENCH-VAR | P3 | Multi-seed variance runs | mlops/eval | sw-dev (TDD) | T-CORPUS, T-BENCH-LOOP | DONE_VERIFIED (c7de8d8) |
| T-GAP1-VALID | P1 | Prove scoring changes outcomes (ablation vs EPSS-only) | mlops/eval | sw-dev + advisor | T-CORPUS, T-BENCH-LOOP | DONE_VERIFIED (eda98c3+5ba1e10+57be1f7) |
| T-DOCKER | P1 | Docker testbed + sandboxed live exploitation | cyber | verify-agent | T-SAFE | BLOCKED (design done d565d7a; NO-GO) |
| T-OPENAI | P2 | Verify/harden OpenAI provider path | sw-dev | verify-agent | — | DONE_PARTIAL (25e4137; live key unverified) |
| T-CHECKPOINT | P2 | AgentState persistence + resume | sw-dev | verify-agent | — | DONE_VERIFIED (f1561be) |
| T-REQPIN | P3 | Pin Python/deps for reproducibility | sw-dev | verify-agent | — | DONE_VERIFIED (9b0fe96) |
| T-GITHUB | P3 | Verify GitHub fetch with real token | github | verify-agent | — | TODO_OPTIONAL (deferred) |
| T-README | P4 | Fix stale README + env/deploy docs | sw-dev | verify-agent | T-SAFE, T-BENCH-LOOP | DONE_VERIFIED (1a9fad9) |
| T-DEADCODE | P4 | Remove dead get_poc export | sw-dev (simplify) | verify-agent | — | DONE_VERIFIED (c1f4d2b) |
| T-UI | P4 | Verify Streamlit dashboard interactively | sw-dev | code-review | — | DONE_SMOKE (b385ec4; interactive N/A) |

## Roadmap phase mapping (authority PHASE 0–7, 2026-08-24)
| Authority phase | Master-plan coverage | State |
|-----------------|----------------------|-------|
| PHASE 0 Recovery/Audit | baseline 31ccd06 + audit | COMPLETE |
| PHASE 1 Governance+Repro | git/repro docs, T-REQPIN | COMPLETE |
| PHASE 2 Core Remediation | T-SAFE, T-BENCH-LOOP, T-TESTS, T-DEADCODE | COMPLETE |
| PHASE 3 Research Validation | T-CORPUS, T-BENCH-VAR, T-GAP1-VALID(+v2), T-OPENAI, T-CHECKPOINT | COMPLETE (simulation) |
| PHASE 4 Evidence+Demo Polish | T-README, T-UI smoke, handover report, authority manifest | COMPLETE |
| PHASE 5 Controlled Real Validation | T-DOCKER (Stage A design DONE; Stage B blocked) | DESIGN_DONE / BLOCKED |
| PHASE 6 Final Evidence Review | independent final review after T-DOCKER | PENDING |
| PHASE 7 Thesis/Paper/Defense | thesis authoring + demo | PENDING (not started) |

> Frozen status: TOP-LEVEL AUTHORITY REVIEW; FROZEN PENDING T-DOCKER EXPERIMENT DECISION.
> No source change; project intentionally frozen. Next real work = T-DOCKER Stage B, gated by
> T_DOCKER_READINESS_ASSESSMENT (NO-GO until Docker up + lab corpus + allowlist guard).

## Execution order (dependency-based)
1. T-SAFE (P0) — safety gate; blocks safe demoing + Docker
2. T-BENCH-LOOP (P0) — makes headline metric valid
3. T-TESTS (P3) — regression net; do early
4. T-CORPUS (P1) — richer labelled env
5. T-BENCH-VAR (P3) — multi-seed (needs corpus + loop fix)
6. T-GAP1-VALID (P1) — empirical GAP-1 proof (needs corpus + loop + tests)
7. T-DOCKER (P1) — live validation (needs T-SAFE)
8. T-OPENAI (P2)
9. T-CHECKPOINT (P2)
10. T-REQPIN (P3)
11. T-GITHUB (P3)
12. T-README (P4)
13. T-DEADCODE (P4)
14. T-UI (P4)

## REJECTED from Claude review (do NOT action)
Any edit to nonexistent functions: normalize_data_model, select_exploit_candidate,
compute_exploit_strength, pivot_execution_strategy, detect_pivot_conditions,
mock_executor_api, send_poc_to_executor, rank_exploit_candidates, sender_in_received,
num_consecutive_failures, num_failures, cvss_vectors.
False claims: random request counts in benchmark; hardcoded ">3" pivot; milvector/vapt-tools
in requirements; "executor entirely mocked".

## Completion gate (per governance §7)
Implementation inspected + acceptance criteria met + required tests run + results recorded
+ no regression. P0/P1/P2 require Claude Code review before DONE.
