# 06 — RESEARCH TRACEABILITY (GAP-1 / GAP-2)

Immutable objective (governance §3): GAP-1 exploit usability before validation; GAP-2 explicit
state + loop prevention. Use GAP-1/GAP-2 consistently; do NOT rename as Gap 3.

## GAP-1 — Exploit Usability Gap
**Claim:** framework assesses candidate exploit/PoC viability BEFORE validation; ranking influences
execution / candidate selection.

| Evidence element | Status | Where | Verification |
|------------------|--------|-------|--------------|
| Pre-assessment node (assess_node) runs before execute_node | VERIFIED | core/agent_graph.py:64-83, edges 152 | ran end-to-end |
| LLM usability scoring of REAL corpus code (structured output) | VERIFIED | core/exploit_assessor.py; ran via Ollama | live run returned valid ExploitAssessment |
| Ranking uses usability (priority_score = epss*(0.5+0.5*u)) | VERIFIED (mechanism) | core/schemas.py:106-115; agent_graph.rank_findings | reasoning |
| Ranking IMPACT on outcomes is empirically demonstrated | NOT YET | needs T-GAP1-VALID | ablation planned |
| Corpus breadth for defensible claim | PARTIAL (n=3) | data/poc_corpus/labels.json | needs T-CORPUS |

**Tasks:** T-GAP1-VALID (P1, prove impact), T-CORPUS (P1, breadth), T-OPENAI/T-GITHUB (P2/P3, provider+corpus growth).

## GAP-2 — Agent Pivot Failure
**Claim:** explicit execution state; track attempts/outcomes; detect repeated failure; terminate/pivot;
select another candidate; terminate safely when exhausted.

| Evidence element | Status | Where | Verification |
|------------------|--------|-------|--------------|
| Explicit AgentState (attempt_count, max_attempts, status, current_index) | VERIFIED | core/agent_graph.py:33-45 | code read |
| Attempt counter increments per execute | VERIFIED | agent_graph.execute_node:90 | code read |
| Pivot on SUCCESS (advance) and on threshold (abandon) | VERIFIED | evaluate_decision:135-143; pivot_node:111-132 | ran end-to-end |
| Loop prevention (no infinite loop) | VERIFIED (structural) | router forces pivot at max_attempts → COMPLETED | ran; no loop |
| Loop avoidance MEASURED (not asserted) | NOT YET | needs T-BENCH-LOOP | smart_loop=0 currently hardcoded |
| Per-finding failure isolation / resume | PARTIAL | pivot_node resets attempt_count per finding; no resume | needs T-CHECKPOINT |

**Tasks:** T-BENCH-LOOP (P0, measure), T-CHECKPOINT (P2, persistence/resume),
T-DOCKER (P1, real validation).

## Cross-cutting
- Safety of real-mode PoC exec → T-SAFE (P0), T-DOCKER (P1) — governance §8.
- Benchmark integrity → T-BENCH-LOOP (P0), T-BENCH-VAR (P3) — governance §9.
- Tests/repro → T-TESTS (P3), T-REQPIN (P3).
