# Role: AI Agent System Architect
Implement `core/agent_graph.py` using LangGraph to solve Type-B planning/state-management failures (Deng et al., 2025; Gap 2).

## Technical Requirements
1. `AgentState` TypedDict: target, findings, current_index, current_cve, exploit_rank, attempt_count, max_attempts, status, provider, mode, logs, results.
2. Nodes:
   - `assess_node`: grades PoC usability via `assess_exploit_quality` BEFORE execution.
   - `execute_node`: calls `core.executor.Executor.execute` (REAL signal; no hardcoded `False`) and increments attempt_count.
   - `pivot_node`: when `attempt_count >= max_attempts` OR a vulnerability is SUCCESS-validated, advance current_index, reset attempt counter, clean context, redirect. COMPLETE when all findings processed.
3. Conditional edge `evaluate_decision`: END if COMPLETED; pivot on SUCCESS or threshold; else execute.

## Done criteria
- Graph compiles and runs end-to-end.
- On a labelled env (data/poc_corpus/labels.json) it validates CVE-2021-44228, pivots/advances correctly, and never indexes out of range.
