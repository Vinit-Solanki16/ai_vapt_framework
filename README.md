# Autonomous AI VAPT Framework

State-aware Vulnerability Assessment & Penetration Testing with **Exploit Quality
Scoring** and **Dynamic Decision-Pivoting** (LangGraph). Built for an M.Tech
cybersecurity thesis. Runs fully offline via local Ollama (no API cost).

## Research Contributions

### GAP-1: AI-Informed Candidate Ranking
AI/LLM assessment of exploit quality occurs BEFORE candidate ranking and
influences attack-path prioritization.

### GAP-2: Bounded Failure-Threshold Pivoting
The system maintains per-candidate attempt state, detects repeated failures,
and dynamically pivots after a configurable failure threshold.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INTERFACES                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  Streamlit   │  │   FastAPI    │  │     CLI      │              │
│  │  frontend/   │  │  services/   │  │  prototype/  │              │
│  │  app.py      │  │  api.py      │  │  cli.py      │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         └─────────────────┼─────────────────┘                       │
│                           ▼                                         │
│              ┌─────────────────────────┐                            │
│              │    VAPTApplication      │                            │
│              │  vapt_platform/         │                            │
│              │  application.py         │                            │
│              └───────────┬─────────────┘                            │
│                          │                                          │
│  ┌───────────────────────┼───────────────────────┐                  │
│  │                       ▼                       │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │         DECISION ENGINE (FROZEN)        │  │                  │
│  │  │  decision_engine/core/                  │  │                  │
│  │  │  GAP-1: assess → rank → decide         │  │                  │
│  │  │  GAP-2: attempt → count → pivot        │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  │                                               │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │      VAPT RESEARCH CORE (FROZEN)        │  │                  │
│  │  │  core/                                  │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  │                                               │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │           PLATFORM SERVICES             │  │                  │
│  │  │  vapt_platform/                         │  │                  │
│  │  │  enrichment, normalization, scanners    │  │                  │
│  │  │  authorization, pipeline, persistence  │  │                  │
│  │  │  events, reporting                      │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  │                                               │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │         PROTOTYPE LAYER                 │  │                  │
│  │  │  prototype/                             │  │                  │
│  │  │  execution_layer, lab_runner, demo_data │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  │                                               │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │         DOCKER LAB                      │  │                  │
│  │  │  lab/                                   │  │                  │
│  │  │  docker-compose.yml, emulator, executor │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  └───────────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Setup

```bash
cd ~/ai_vapt_framework
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Optional: Start Ollama for AI assessment
ollama serve &
ollama pull llama3.2:3b
```

### Run

```bash
# 1) CLI — run a scenario
python -m prototype.cli run --scenario failure_pivot --mode simulation

# 2) Web dashboard
streamlit run frontend/app.py

# 3) API
uvicorn services.api:app --reload --port 8000

# 4) Run tests
python -m pytest tests/ -q
```

## Evidence Tiers

| Tier | Description |
|------|-------------|
| **SIMULATED** | Outcomes from ground-truth labels (`labels.json`) |
| **OBSERVED_LOCAL** | Real HTTP to loopback (127.0.0.1) |
| **DOCKER_OBSERVED** | Real HTTP to isolated Docker emulator |
| **CONTROLLED_VALIDATION** | Real execution against live targets |

## Research Integrity

### GAP-1: Assessment Before Ranking

```python
# decision_engine/core/engine.py:initial_state()
if assess_fn:
    assess_candidates(raw_candidates, assess_fn=assess_fn)  # Assess FIRST
cs = rank_candidates(raw_candidates)  # THEN rank
```

### GAP-2: Bounded Pivot

```python
# decision_engine/core/engine.py:_evaluate()
if state["attempt_count"] >= state["max_attempts"]:
    return "pivot"  # Threshold reached → pivot
```

## Project Structure

```
ai_vapt_framework/
├── core/                    # VAPT research core (FROZEN)
├── decision_engine/         # Domain-independent engine (FROZEN)
├── vapt_platform/           # Platform services
├── prototype/               # Prototype layer (executors, demo data)
├── frontend/                # Streamlit dashboard
├── services/                # FastAPI backend
├── lab/                     # Docker lab
├── tests/                   # Test suite (545 tests)
├── data/                    # Datasets and PoC corpus
├── docs/                    # Documentation
└── experiments/             # Research experiments
```

## Honest Limitations

- **SIMULATION mode** uses ground-truth labels, not live exploitation
- **DOCKER_OBSERVED** requires Docker Desktop (not available in all environments)
- **AI assessment** requires local Ollama (deterministic fallback available)
- **No external targets** — only allowlisted lab targets are permitted

## Documentation

- [Current State Audit](docs/project_management/CURRENT_STATE_AUDIT.md)
- [Research Core Protection](docs/project_management/RESEARCH_CORE_PROTECTION.md)
- [Mentor Demo](docs/project_management/MENTOR_DEMO.md)
- [Current Architecture](docs/architecture/CURRENT_ARCHITECTURE.md)
- [Known Limitations](docs/project_management/KNOWN_LIMITATIONS.md)
