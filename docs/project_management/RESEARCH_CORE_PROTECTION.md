# Research Core Protection Boundary

**Date:** 2026-09-21
**Status:** ACTIVE
**Branch:** `prototype-development`

---

## 1. Protected Files

The following files are FROZEN and MUST NOT be modified without explicit user approval:

### 1.1 Decision Engine Core (GAP-1 + GAP-2)

| File | Purpose | Last Modified |
|------|---------|---------------|
| `decision_engine/core/schemas.py` | ActionCandidate, QualityRank, Outcome, priority_score() | 2026-09-16 |
| `decision_engine/core/assessor.py` | deterministic_assessor, assess_candidates (GAP-1) | 2026-09-16 |
| `decision_engine/core/executor.py` | Executor abstraction (simulation/real) | 2026-09-16 |
| `decision_engine/core/engine.py` | LangGraph state machine, pivot logic (GAP-2) | 2026-09-16 |

### 1.2 VAPT Research Core

| File | Purpose | Last Modified |
|------|---------|---------------|
| `core/schemas.py` | Finding, ExploitAssessment, UsabilityRank | 2026-09-16 |
| `core/agent_graph.py` | VAPT LangGraph implementation | 2026-09-16 |
| `core/exploit_assessor.py` | LLM usability scoring (Ollama/OpenAI) | 2026-09-16 |
| `core/executor.py` | VAPT execution (simulation/real) | 2026-09-16 |
| `core/report.py` | VAPT report generation | 2026-09-16 |
| `core/scanner.py` | Nmap/custom scan ingestion | 2026-09-16 |
| `core/poc_corpus.py` | Local PoC corpus | 2026-09-16 |

---

## 2. Research Integrity Verification

### 2.1 GAP-1: Assessment Before Ranking

**Requirement:** Candidate quality assessment MUST occur BEFORE candidate ranking.

**Implementation:** `decision_engine/core/engine.py:initial_state()`

```python
def initial_state(candidates, max_attempts=2, mode="simulation", assess_fn=None):
    raw_candidates = [candidate_from_dict(d) for d in candidates]
    if assess_fn:
        assess_candidates(raw_candidates, assess_fn=assess_fn)  # GAP-1: assess FIRST
    cs = rank_candidates(raw_candidates)  # THEN rank
    return {"candidates": cs, ...}
```

**Verification:** ✅ PASS
- `assess_candidates()` is called before `rank_candidates()`
- `quality_rank` is filled before `priority_score()` is computed
- Test: `test_engine.py` confirms assessment affects ordering

### 2.2 GAP-2: Bounded Pivot with Per-Candidate Counters

**Requirement:** Per-candidate attempt counting with configurable threshold.

**Implementation:** `decision_engine/core/engine.py`

```python
def _execute_node(state, executor):
    result = executor.execute(c)
    state["attempt_count"] += 1  # Increment per-candidate counter
    ...

def _evaluate(state):
    if state["attempt_count"] >= state["max_attempts"]:
        return "pivot"  # Threshold reached → pivot
    return "execute"

def _pivot_node(state):
    state["current_index"] += 1
    if state["current_index"] < len(state["candidates"]):
        state["attempt_count"] = 0  # Reset per-candidate counter (Gap-2)
        ...
```

**Verification:** ✅ PASS
- `attempt_count` is per-candidate (reset in `_pivot_node`)
- Threshold check in `_evaluate()` uses `>=` (correct)
- No hidden state — all counters are explicit in EngineState

---

## 3. Protection Rules

### 3.1 DO NOT

- ❌ Modify any file in `decision_engine/core/` or `core/`
- ❌ Change GAP-1 semantics (assessment → ranking order)
- ❌ Change GAP-2 semantics (per-candidate counters, threshold pivot)
- ❌ Replace LangGraph with another orchestration framework
- ❌ Replace the research engine with another framework
- ❌ Add hidden state to the engine
- ❌ Modify frozen research logic for convenience

### 3.2 DO

- ✅ Add new functionality in `vapt_platform/`, `prototype/`, `frontend/`, `services/`
- ✅ Create adapters that wrap the research core
- ✅ Add tests for new functionality
- ✅ Document changes thoroughly
- ✅ Use existing abstractions (VAPTApplication, EventPublisher, etc.)

---

## 4. Change Log

| Date | Change | Approved By |
|------|--------|-------------|
| 2026-09-16 | GAP-1 fix: assessment before ranking | User (commit 252c99a) |
| 2026-09-21 | Protection boundary established | Lead Engineer |

---

## 5. Verification Commands

```bash
# Verify research core is unchanged
git diff HEAD -- decision_engine/core/ core/

# Run research core tests
python -m pytest decision_engine/tests/ -q

# Run full test suite
python -m pytest tests/ -q
```

---

_This document MUST be updated if any research core file is modified._
