# AI-VAPT Research Prototype — M.Tech Project Documentation

## Executive Summary

The AI-VAPT (AI-driven Vulnerability Assessment and Penetration Testing) framework is a research prototype that demonstrates two novel contributions:

1. **GAP-1: AI Pre-Execution Assessment** — Candidates are assessed for quality before execution, and this assessment influences their priority ordering via `priority_score = probability × (0.5 + 0.5 × quality_weight)`.

2. **GAP-2: Bounded Failure-Driven Pivoting** — Per-candidate attempt counters with configurable thresholds ensure the engine abandons failing routes after N attempts and pivots to the next candidate, guaranteeing bounded termination.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Interfaces: CLI / FastAPI / Streamlit                      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  VAPTApplication (vapt_platform/application.py)             │
│  Canonical workflow:                                         │
│    1. Load candidates (scenario/scan file)                  │
│    2. Enrich with threat intelligence (EPSS, KEV)           │
│    3. Build asset/vulnerability graph                       │
│    4. Decision intelligence scoring                         │
│    5. Build executor (simulation/lab)                        │
│    6. Validation pipeline (Planner→SafetyGate→Executor)     │
│    7. Decision engine (frozen research core)                │
│    8. Build result + generate report                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  decision_engine/core/ (FROZEN)                             │
│  - engine.py: LangGraph-based decision & pivot engine       │
│  - assessor.py: Gap-1 quality assessment                    │
│  - executor.py: Simulation + real execution backends        │
│  - schemas.py: Domain-independent types                     │
└─────────────────────────────────────────────────────────────┘
```

## Research Contributions

### GAP-1: AI Pre-Execution Assessment

**Location:** `decision_engine/core/assessor.py`, `decision_engine/core/engine.py`

**Mechanism:**
- Before execution, each candidate is assessed for quality (HIGH/MEDIUM/LOW)
- Quality rank feeds into `priority_score = probability × (0.5 + 0.5 × quality_weight)`
- Candidates are ranked by priority_score (descending) before execution begins
- Assessment can be deterministic (offline) or AI-powered (Ollama/OpenAI)

**Validation:**
```python
# Without assessment: score = probability × 0.5
# With HIGH quality:   score = probability × 1.0
# With LOW quality:    score = probability × 0.65
```

### GAP-2: Bounded Failure-Driven Pivoting

**Location:** `decision_engine/core/engine.py`

**Mechanism:**
- Per-candidate attempt counter (`attempt_count`)
- Configurable pivot threshold (`max_attempts`)
- On failure: increment counter, check threshold
- On threshold reached: abandon candidate, pivot to next
- On success: advance to next candidate
- Guaranteed bounded termination: total attempts ≤ candidates × max_attempts

**State Machine:**
```
ASSESS → execute → SUCCESS → pivot (advance)
                   → FAIL → attempt_count++
                            → if count < max: execute again
                            → if count >= max: pivot (abandon)
```

## Repository Structure

```
ai_vapt_framework/
├── decision_engine/          # FROZEN research core
│   ├── core/
│   │   ├── engine.py         # LangGraph decision engine
│   │   ├── assessor.py       # Gap-1 assessment
│   │   ├── executor.py       # Execution backends
│   │   └── schemas.py        # Domain-independent types
│   ├── adapters/             # Domain adapters
│   ├── benchmarks/           # Research benchmarks
│   └── tests/                # Core tests
├── vapt_platform/            # Platform layer
│   ├── application.py        # VAPTApplication (canonical workflow)
│   ├── pipeline.py           # Validation pipeline
│   ├── authorization.py      # Safety framework
│   ├── scanners.py           # Scanner adapters
│   ├── enrichment.py         # Threat intelligence
│   ├── assessment.py         # Pluggable assessor
│   ├── decision_intelligence.py  # Transparent scoring
│   ├── events/               # Event system
│   ├── persistence/          # Run persistence
│   ├── reporting/            # Report builders/renderers
│   └── normalization.py      # Finding normalization
├── services/
│   ├── api.py                # FastAPI backend
│   ├── schemas.py            # API models
│   └── jobs.py               # Job manager
├── frontend/
│   └── app.py                # Streamlit dashboard
├── experiments/              # Research experiments
│   ├── harness/              # Experiment runner
│   ├── benchmarks/           # Benchmark scenarios
│   └── results/              # Experiment output
├── lab/
│   └── emulator/             # Docker vulnerability emulator
├── data/                     # Datasets (EPSS, KEV, scans)
├── docs/                     # Project documentation
└── tests/                    # Platform tests
```

## Running the Prototype

### Prerequisites
```bash
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run Tests
```bash
pytest -q  # 538+ tests, all passing
```

### Run API
```bash
uvicorn services.api:app --reload
```

### Run Dashboard
```bash
streamlit run frontend/app.py
```

### Run Experiments
```bash
python experiments/run_all.py
```

## Safety Model

1. **Target Allowlist:** Only `127.0.0.1` and `172.28.0.2` are permitted as lab targets
2. **Fail-Closed:** Any non-allowlisted target is refused before any socket is opened
3. **danger_mode disabled:** Real exploitation is never attempted
4. **Authorization Tracking:** All target authorizations are recorded with audit trail
5. **Scope Enforcement:** Port/protocol scope is validated per authorization

## Evidence Tiers

| Tier | Source | Description |
|------|--------|-------------|
| SIMULATED | Ground-truth labels | No real execution |
| OBSERVED_LOCAL | Loopback (127.0.0.1) | Local-only, no external systems |
| DOCKER_OBSERVED | Docker emulator | Isolated lab, no external systems |
| CONTROLLED_VALIDATION | Live targets | Requires authorization |

## Current Limitations

1. **Docker unavailable in WSL:** Lab mode requires Docker Desktop WSL integration
2. **Ollama not running:** AI assessment falls back to deterministic
3. **Simulation-only:** All demo scenarios use ground-truth labels
4. **Research prototype:** Not a production tool

## Test Coverage

- **538 tests passed, 7 skipped, 0 failed**
- Covers: core engine, platform layer, API, pipeline, safety, persistence, reporting
- Integration tests for all boundaries
- Deterministic benchmarks for thresholds 1, 2, 3

## Experiment Results

| Experiment | Attempts | Pivots | Status |
|-----------|----------|--------|--------|
| gap2_threshold_1 | 2 | 2 | SUCCESS |
| gap2_threshold_2 | 5 | 4 | COMPLETED |
| gap2_threshold_3 | 7 | 4 | SUCCESS |
| gap2_all_fail | 6 | 5 | COMPLETED |
| gap2_immediate_success | 2 | 1 | SUCCESS |
| gap1_ai_informed_ranking | 5 | 4 | SUCCESS |

All experiments are reproducible (deterministic assessment, no external dependencies).

## Research Traceability

| Claim | Evidence | Location |
|-------|----------|----------|
| GAP-1: Assessment before execution | `assess_candidates()` called in `_assess_node` before `_execute_node` | `engine.py:55-66` |
| GAP-1: Assessment influences ranking | `rank_candidates()` sorts by `priority_score()` which uses `quality_rank` | `engine.py:50-52` |
| GAP-2: Per-candidate attempt counter | `attempt_count` field in `EngineState`, reset on pivot | `engine.py:37-47` |
| GAP-2: Configurable threshold | `max_attempts` parameter throughout | `engine.py:133-146` |
| GAP-2: Bounded termination | `_evaluate()` routes to pivot when `attempt_count >= max_attempts` | `engine.py:107-114` |
| Safety: Target allowlist | `LAB_TARGET_ALLOWLIST` in `lab_runner.py` | `lab_runner.py:22` |
| Safety: Fail-closed | `_validate_target()` raises on non-allowlisted | `lab_runner.py:29-42` |
| Reproducibility | Deterministic assessor, no external deps | `assessor.py:19-25` |