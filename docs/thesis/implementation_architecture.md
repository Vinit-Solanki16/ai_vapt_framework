# Implementation Architecture — AI-VAPT Framework

**Date:** 2026-09-16  
**Commit:** 9952d95 (post-Wave 12)

---

## 1. Overview

The AI-VAPT framework consists of:

1. **Core VAPT Platform:** `vapt_platform/` — Full VAPT pipeline
2. **Decision Engine:** `decision_engine/` — Domain-independent research core
3. **Prototype:** `prototype/` — Demonstration layer
4. **Services:** `services/` — API and job management
5. **Frontend:** `frontend/` — Web GUI
6. **Experiments:** `experiments/` — Research validation

---

## 2. Research Core (decision_engine/)

### 2.1 Architecture

```
decision_engine/
├── core/
│   ├── schemas.py      # ActionCandidate, Outcome, QualityRank
│   ├── assessor.py     # Gap-1: deterministic + LLM assessor
│   ├── engine.py       # Gap-2: bounded pivot engine
│   └── executor.py     # Simulation + real execution
├── adapters/
│   ├── vapt_adapter.py # VAPT domain adapter
│   └── scan_adapter.py # Scan ingestion
├── benchmarks/
│   ├── agnostic_benchmark.py      # Domain-independent proof
│   ├── fair_benchmark.py          # 4-agent ablation
│   ├── fair_vapt_benchmark.py     # VAPT corpus benchmark
│   └── llm_assessor_benchmark.py  # LLM assessor tests
└── tests/
    ├── test_engine.py             # Engine tests
    ├── test_fair_benchmark.py     # Benchmark tests
    ├── test_llm_assessor_benchmark.py
    └── test_scan_adapter.py
```

### 2.2 Key Components

#### ActionCandidate (schemas.py)

```python
class ActionCandidate(BaseModel):
    id: str
    probability: float          # 0..1 (e.g., EPSS)
    quality_rank: Optional[QualityRank]  # Gap-1 output
    assessed: bool
    attempted: bool
    execution_outcome: Optional[Outcome]
    ground_truth: Optional[Outcome]  # Simulation only

    def priority_score(self) -> float:
        u = QUALITY_WEIGHT[self.quality_rank] if self.quality_rank else 0.0
        return round(self.probability * (0.5 + 0.5 * u), 4)
```

#### Deterministic Assessor (assessor.py)

```python
def deterministic_assessor(candidate: ActionCandidate) -> QualityRank:
    if candidate.ground_truth == Outcome.SUCCESS:
        return QualityRank.HIGH
    if candidate.probability >= 0.9:
        return QualityRank.MEDIUM
    return QualityRank.LOW
```

#### Bounded Pivot Engine (engine.py)

```python
def _evaluate(state: EngineState) -> str:
    if state["status"] == EngineStatus.COMPLETED.value:
        return END
    if state["status"] == EngineStatus.SUCCESS.value:
        return "pivot"
    if state["attempt_count"] >= state["max_attempts"]:
        return "pivot"
    return "execute"
```

---

## 3. VAPT Platform (vapt_platform/)

### 3.1 Architecture

```
vapt_platform/
├── application.py           # Main application
├── assessment.py            # VAPT assessment
├── authorization.py         # Authorization controls
├── decision_intelligence.py # Decision scoring
├── enrichment.py            # Data enrichment
├── graph_builder.py         # Asset/vulnerability graph
├── normalization.py         # Data normalization
├── pipeline.py              # Pipeline orchestration
├── scanners.py              # Scanner integration
├── events/                  # Event system
├── parsers/                 # Data parsers
├── persistence/             # Data persistence
└── reporting/               # Report generation
```

### 3.2 Key Components

- **Pipeline:** Orchestrates VAPT workflow
- **Scanners:** Integrates with scanning tools
- **Parsers:** Normalizes scan results
- **Persistence:** Stores runs and findings
- **Reporting:** Generates reports

---

## 4. Services Layer (services/)

### 4.1 API (services/api.py)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/runs` | POST | Create new run |
| `/runs/{id}` | GET | Get run details |
| `/runs/{id}/events` | GET | Get run events |
| `/runs/{id}/evidence` | GET | Get run evidence |
| `/runs/{id}/report` | GET | Get run report |
| `/findings` | GET | List findings |
| `/candidates` | GET | List candidates |

### 4.2 Jobs (services/jobs.py)

- Background job management
- Run persistence
- Event tracking

---

## 5. Frontend (frontend/)

### 5.1 Features

- **Dashboard:** Run overview
- **Timeline:** Execution timeline
- **Report Export:** PDF/HTML report generation
- **History:** Past runs

### 5.2 Tests

- `frontend/tests/test_frontend_smoke.py` — Smoke tests

---

## 6. Experiments (experiments/)

### 6.1 Experiment Scripts

| Script | Purpose |
|--------|---------|
| `wave12_thesis_evaluation.py` | Wave 12 thesis-grade experiments |
| `research_validation.py` | Research validation |
| `run_all.py` | Run all experiments |

### 6.2 Results

| File | Description |
|------|-------------|
| `experiments/results/gap1_extended.json` | GAP-1 data |
| `experiments/results/gap2_extended.json` | GAP-2 data |
| `experiments/results/combined_results.json` | Combined data |
| `experiments/results/llm_behavior.json` | LLM behavior |
| `experiments/results/statistical_summary.json` | Statistics |

---

## 7. Test Coverage

### 7.1 Test Count

| Category | Count |
|----------|-------|
| Total tests | 538 |
| Passed | 538 |
| Skipped | 7 |
| Failed | 0 |

### 7.2 Test Categories

| Category | Files | Coverage |
|----------|-------|----------|
| Core | `tests/test_core.py` | Agent graph, schemas |
| Decision | `tests/test_decision.py` | Decision engine |
| Docker | `tests/test_docker_lab.py` | Docker lab |
| Enrichment | `tests/test_enrichment.py` | Data enrichment |
| Events | `tests/test_events.py` | Event system |
| Executor | `tests/test_executor_allowlist.py` | Safety allowlist |
| Graph | `tests/test_graph.py` | Graph builder |
| Normalization | `tests/test_normalization.py` | Data normalization |
| Persistence | `tests/test_persistence.py` | Data persistence |
| Reporting | `tests/test_reporting.py` | Report generation |
| Scanners | `tests/test_scanners.py` | Scanner integration |
| Pipeline | `tests/test_pipeline.py` | Pipeline orchestration |
| API | `services/tests/test_api.py` | API endpoints |
| Safety | `services/tests/test_safety.py` | Safety controls |
| Frontend | `frontend/tests/test_frontend_smoke.py` | Frontend |
| Decision Engine | `decision_engine/tests/` | Engine, benchmarks |

---

## 8. Git History

```
9952d95 feat: expand thesis-grade experimental evaluation (Wave 12)
bb82bae feat: Wave 11 — Complete research validation program (12 phases)
252c99a fix: GAP-1 assessment must affect ranking (research-critical bug fix)
134cd01 feat: research validation harness and experiment infrastructure
5d29b0f fix: close Wave 10A integration gaps
4c47c22 refactor: harden platform architecture (Wave 10A)
...
```

---

## 9. Key Design Decisions

### 9.1 Domain-Independent Core

The decision engine is domain-independent. VAPT is attached via adapters, making the research contribution generalizable.

### 9.2 Pluggable Assessment

Assessment sources are pluggable:
- Deterministic (offline, reproducible)
- Real LLM (Ollama, OpenAI, etc.)
- Custom (any callable)

### 9.3 Safety-First

- Allowlist-only execution
- Fail-closed design
- No external targets
- Bounded attempts

### 9.4 Reproducibility

- Deterministic experiments
- Seeded randomness
- Pinned dependencies
- Documented commands
