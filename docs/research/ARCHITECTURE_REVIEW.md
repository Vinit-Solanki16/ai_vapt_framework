# Architecture Review — AI-VAPT Research Prototype

## Overview

This document provides a comprehensive architecture review of the AI-VAPT research prototype, covering design decisions, component boundaries, safety mechanisms, and potential issues.

## Architecture Summary

### Canonical Workflow

```
CLI / API / GUI
      ↓
VAPTApplication.run()
      ↓
  1. Load candidates (scenario / scan file)
  2. Enrich with threat intelligence (EPSS, KEV)
  3. Build asset/vulnerability graph
  4. Decision intelligence scoring
  5. Build executor (simulation / lab)
  6. Validation pipeline (Planner → SafetyGate → Executor → Verifier → Evidence)
  7. Decision engine (frozen research core: assess → execute → pivot)
  8. Build result + generate report + persist
      ↓
DomainResult → PresentationResult → Report
```

### Component Hierarchy

| Layer | Components | Responsibility |
|-------|-----------|----------------|
| **Research Core** | `decision_engine/core/` | Frozen: schemas, assessor, executor, engine |
| **Platform** | `vapt_platform/` | Application, pipeline, authorization, enrichment |
| **Services** | `services/api.py` | FastAPI endpoints |
| **Frontend** | `frontend/app.py` | Streamlit dashboard |
| **Data** | `datasets/`, `data/` | EPSS, KEV, corpus labels, scan files |
| **Experiments** | `experiments/` | Reproducible benchmark harness |

## Design Decisions

### 1. Single Canonical Workflow

**Decision:** All interfaces (CLI, API, GUI) must use `VAPTApplication.run()`.

**Rationale:** Prevents interface-specific bugs and ensures consistent behavior.

**Verification:** Search for direct calls to `run_engine()` outside of `VAPTApplication` and `engine_integration.py`.

### 2. Frozen Research Core

**Decision:** `decision_engine/core/` is never modified.

**Rationale:** Ensures research contributions (GAP-1, GAP-2) are stable and reproducible.

**Impact:** All platform extensions must be in `vapt_platform/` or other non-core modules.

### 3. Assessment-then-Execute Ordering

**Decision:** Assessment (Gap-1) always occurs before execution in the engine.

**Implementation:** `_assess_node` → `_execute_node` edge in the LangGraph.

**Verification:** The graph has a hard edge `assess → execute`, not conditional.

### 4. Exhaustive Candidate Processing

**Decision:** Engine processes ALL candidates, not just until first success.

**Rationale:** Provides complete coverage for research analysis of pivot behavior.

**Implication:** `final_status` is "SUCCESS" if any candidate succeeded, "COMPLETED" if all were processed.

### 5. Deterministic Fallback

**Decision:** When AI (Ollama/OpenAI) is unavailable, fall back to deterministic assessment.

**Rationale:** Ensures benchmarks run offline without external dependencies.

**Tracking:** `AssessmentResult.fallback = True` when deterministic is used instead of AI.

## Safety Mechanisms

### 1. Target Allowlist

```python
LAB_TARGET_ALLOWLIST = {"127.0.0.1", "172.28.0.2"}
```

- Only these targets are permitted for lab mode
- Fail-closed: any other target raises `ValueError`
- Validated in `_validate_target()` before any socket operation

### 2. danger_mode Disabled

- The executor's real mode requires explicit `danger_mode=True`
- Default is `False` — no exploitation is attempted
- Only HTTP GET requests to the emulator are performed

### 3. Scope Enforcement

- `ScopeEnforcer` validates target, ports, and protocols
- `AuthorizationTracker` records all authorizations with audit trail
- `AuditLogger` provides immutable audit trail

### 4. Evidence Tier System

Each run is tagged with an evidence tier:
- **SIMULATED:** Ground-truth labels, no real execution
- **OBSERVED_LOCAL:** Loopback target only
- **DOCKER_OBSERVED:** Docker-isolated emulator
- **CONTROLLED_VALIDATION:** Live targets (requires authorization)

## Component Analysis

### decision_engine/core/engine.py

**Strengths:**
- Clean separation: assess → execute → pivot
- Per-candidate attempt counter with configurable threshold
- LangGraph-based state machine with clear transitions
- Bounded termination guarantee

**Potential Issues:**
- The engine processes all candidates exhaustively. This is intentional but may surprise users expecting early termination.
- `final_status` is "COMPLETED" even when no candidate succeeds. Check `results` for actual outcomes.

### vapt_platform/application.py

**Strengths:**
- Single entry point for all workflows
- Event-driven lifecycle with `EventPublisher`
- Persistence integration for run history
- Clean separation between domain and presentation layers

**Potential Issues:**
- Multiple scenario registries (`SCENARIOS`, `DOCKER_SCENARIOS`) could be unified
- Error handling is broad (catches all exceptions)

### services/api.py

**Strengths:**
- Uses canonical `VAPTApplication` workflow
- Exposes all research-relevant information
- In-memory job manager for run tracking

**Potential Issues:**
- Synchronous run execution may block for long-running scenarios
- Job manager is in-memory (lost on restart)

### frontend/app.py

**Strengths:**
- Professional UI with evidence tier visualization
- Clear indication of AI vs deterministic assessment
- Run history with full trace viewer

**Potential Issues:**
- Direct use of `requests` for API calls (could use API client library)
- Some duplicated display logic between history and live run views

### vapt_platform/pipeline.py

**Strengths:**
- Clean pipeline: Planner → SafetyGate → Executor → Verifier → Evidence
- Immutable evidence chain with hash validation
- Integrated with authorization tracker

**Potential Issues:**
- Pipeline execution results are not stored in persistence layer
- Pipeline runs independently of the decision engine (separate execution path)

## Identified Issues

### 1. Dual Execution Paths

**Issue:** There are two execution paths:
1. `VAPTApplication._run_validation_pipeline()` — pipeline execution
2. `VAPTApplication._run_engine()` — decision engine execution

**Impact:** Both execute candidates independently. The pipeline execution is NOT fed into the engine, and vice versa.

**Recommendation:** Clarify in documentation that the pipeline is for validation/preparation, while the engine is the research core execution. Consider making pipeline execution feed into the engine.

### 2. Scenario Registry Duplication

**Issue:** Scenarios are defined in multiple places:
- `prototype/demo_data.py` — `SCENARIOS` dict
- `prototype/docker_demo_data.py` — `DOCKER_SCENARIOS` dict
- `experiments/benchmarks/__init__.py` — `ALL_BENCHMARKS` dict

**Impact:** Changes to a scenario must be replicated across files.

**Recommendation:** Consolidate into a single scenario registry.

### 3. Test Coverage Gaps

**Issue:** Some areas lack integration tests:
- Full workflow from API to persistence
- GUI component interactions
- Lab mode with real Docker (requires Docker)

**Recommendation:** Add integration tests for API → Application → Persistence flow.

## Performance Considerations

1. **Assessment is O(n)** per candidate — scales linearly
2. **Engine execution is O(n × m)** where n = candidates, m = max_attempts
3. **Evidence chain is O(n)** with constant-time hash verification
4. **Persistence is O(1)** per run (JSON file append)

## Security Considerations

1. **No external targeting:** Allowlist prevents accidental external connections
2. **No exploitation:** `danger_mode` is disabled; only HTTP GET to emulator
3. **Audit trail:** All operations are logged with timestamp and actor
4. **Input validation:** All scan files and candidates are validated before processing

## Conclusion

The architecture is sound with clear separation of concerns:
- Frozen research core ensures reproducibility
- Platform layer provides extensibility
- Single canonical workflow prevents divergence
- Safety mechanisms are fail-closed and auditable

The main area for improvement is clarifying the relationship between the validation pipeline and the decision engine execution path.