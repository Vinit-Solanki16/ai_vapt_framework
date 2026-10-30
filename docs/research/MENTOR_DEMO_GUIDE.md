# Mentor Demo Guide

## Pre-Demo Checklist

- [ ] All tests pass: `pytest -q` → 538 passed, 7 skipped
- [ ] API starts: `uvicorn services.api:app`
- [ ] Dashboard starts: `streamlit run frontend/app.py`
- [ ] Experiments run: `python experiments/run_all.py`

## Demo Script (15 minutes)

### 1. Introduction (2 min)

Show the project structure:
```bash
tree -L 2 -I 'venv|__pycache__|.git|*.pyc' --dirsfirst
```

Key points:
- `decision_engine/core/` is the frozen research core
- `vapt_platform/` provides the platform layer
- `services/api.py` and `frontend/app.py` are interfaces
- All interfaces use the canonical `VAPTApplication` workflow

### 2. Run Tests (2 min)

```bash
pytest -q --tb=no
```

Expected: `538 passed, 7 skipped, 0 failed`

### 3. Demonstrate GAP-1 (3 min)

Show that assessment influences ranking:

```python
from decision_engine.core.engine import rank_candidates
from decision_engine.core.assessor import deterministic_assessor
from decision_engine.core.schemas import candidate_from_dict

candidates = [
    candidate_from_dict({"id": "HIGH-P-FAIL", "probability": 0.95, "ground_truth": "FAIL_TIMEOUT"}),
    candidate_from_dict({"id": "LOW-P-SUCCESS", "probability": 0.30, "ground_truth": "SUCCESS"}),
]

# Before assessment
for c in candidates:
    print(f"{c.id}: score={c.priority_score()}")

# After assessment
for c in candidates:
    c.quality_rank = deterministic_assessor(c)
    print(f"{c.id}: quality={c.quality_rank}, score={c.priority_score()}")
```

Key point: Assessment fills `quality_rank` BEFORE execution, changing the priority score.

### 4. Demonstrate GAP-2 (3 min)

Show bounded pivoting with different thresholds:

```bash
python experiments/run_all.py
```

Show results:
- threshold_1: 2 attempts, 2 pivots
- threshold_2: 5 attempts, 4 pivots
- threshold_3: 7 attempts, 4 pivots
- all_fail: 6 attempts, 5 pivots (bounded termination)

### 5. Show Full Workflow (3 min)

Run a scenario through the application:

```python
from vapt_platform.application import VAPTApplication, VAPTRequest

app = VAPTApplication()
req = VAPTRequest(scenario='failure_pivot', mode='simulation', max_attempts=2)
result = app.run(req)

print(f"Status: {result.domain.final_status}")
print(f"Attempts: {result.domain.total_attempts}")
print(f"Pivots: {result.domain.pivot_count}")
print(f"Trace:")
for log in result.domain.decision_trace:
    print(f"  {log}")
```

### 6. Show API (2 min)

Start the API:
```bash
uvicorn services.api:app --port 8000
```

Test endpoints:
```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/runs -H "Content-Type: application/json" \
  -d '{"scenario": "failure_pivot", "max_attempts": 2, "mode": "simulation"}'
```

### 7. Show Dashboard (2 min)

Start the dashboard:
```bash
streamlit run frontend/app.py
```

Navigate to "New Assessment" and run a scenario.

## Key Talking Points

1. **Single canonical workflow:** All interfaces use `VAPTApplication.run()`
2. **Frozen research core:** `decision_engine/core/` is never modified
3. **Safety first:** Allowlist, fail-closed, danger_mode disabled
4. **Reproducible:** Deterministic assessment, no external deps for benchmarks
5. **Bounded termination:** Total attempts ≤ candidates × max_attempts

## Common Questions

**Q: Why does the engine process all candidates instead of stopping at first success?**
A: The engine is designed to validate ALL candidates in priority order, not just find one success. This provides complete coverage for research analysis.

**Q: What happens when Docker is unavailable?**
A: The lab mode cannot run. Simulation mode works without Docker. The emulator code is in `lab/emulator/app.py`.

**Q: How is AI assessment different from deterministic?**
A: AI assessment uses Ollama/OpenAI to grade candidates. Deterministic uses ground-truth labels. Both feed into the same priority_score formula. When AI is unavailable, deterministic fallback is used.

**Q: What is the evidence tier system?**
A: Each run is tagged with an evidence tier (SIMULATED, OBSERVED_LOCAL, DOCKER_OBSERVED, CONTROLLED_VALIDATION) to clearly indicate the source of outcomes.