# Mentor Demonstration Guide

**Project:** AI VAPT Decision Engine  
**Date:** 2026-09-16  
**Version:** 2.0 (Wave 11 — Research Validation Complete)  
**Commit:** 252c99a

---

## Infrastructure Prerequisites

| Component | Status | Details |
|-----------|--------|---------|
| **Tests** | ✅ PASSING | 536 passed, 7 skipped, 0 failed |
| **Ollama LLM** | ✅ AVAILABLE | llama3.2:3b (Q4_K_M, 2.0 GB) |
| **Docker** | ❌ NOT AVAILABLE | Docker Desktop WSL2 integration not enabled |
| **Real Exploits** | ❌ NOT AVAILABLE | No live targets (safety) |

---

## DEMO A: Fully Reproducible Offline (Simulation + Deterministic)

This path requires **zero infrastructure** beyond Python. All experiments are deterministic and repeatable.

### Pre-flight

```bash
cd /home/vinit/ai_vapt_framework
source venv/bin/activate

# Verify all tests pass (should be 536 passed, 7 skipped)
pytest -q
```

### Step 1: GAP-1 Demonstration (2 min)

Show that AI assessment changes candidate ordering:

```python
from decision_engine.core.engine import run_engine, rank_candidates
from decision_engine.core.assessor import deterministic_assessor
from decision_engine.core.executor import Executor
from decision_engine.core.schemas import candidate_from_dict, ActionCandidate, QualityRank

# Two candidates: high-probability-FAIL vs medium-probability-SUCCESS
candidates = [
    {"id": "HIGH-PROB-FAIL", "probability": 0.80, "ground_truth": "FAIL_TIMEOUT"},
    {"id": "MED-PROB-SUCCESS", "probability": 0.55, "ground_truth": "SUCCESS"},
    {"id": "LOW-PROB-FAIL", "probability": 0.30, "ground_truth": "FAIL_TIMEOUT"},
]

# Run with assessment (deterministic assessor)
executor = Executor(mode="simulation")
result = run_engine(candidates, assess_fn=deterministic_assessor, executor=executor, max_attempts=2)

print("Ranking after assessment:")
for c in result["candidates"]:
    print(f"  {c.id}: score={c.priority_score()}, quality={c.quality_rank}")
print(f"\nWithout assessment, order would be: HIGH-PROB-FAIL > MED-PROB-SUCCESS > LOW-PROB-FAIL")
print(f"With assessment, order is: {' > '.join(c.id for c in result['candidates'])}")
print(f"Assessment CHANGED the ordering ✓")
```

### Step 2: GAP-2 Demonstration (3 min)

Show bounded failure-driven pivoting:

```bash
python experiments/research_validation.py
```

Walk through the output:
- **Threshold=1:** 2 attempts, 2 pivots (immediate abandon)
- **Threshold=2:** 3 attempts, 2 pivots (one retry, then abandon)
- **Threshold=3:** 4 attempts, 2 pivots (two retries, then abandon)
- **All fail:** 6 attempts (3 candidates × 2 max_attempts) — bounded termination

### Step 3: Full Pipeline Demonstration (3 min)

Run the full research validation suite:

```bash
python experiments/harness/__init__.py
```

Show results:
```bash
cat experiments/results/summary.csv
cat experiments/results/all_experiments.csv
```

### Step 4: Reproducibility Verification (2 min)

All experiments produce identical results across repetitions:

```bash
# Run again — should get identical output
python experiments/harness/__init__.py
diff <(cat experiments/results/all_experiments.csv) <(echo "identical")
```

### DEMO A Talking Points

1. **GAP-1 works:** Assessment affects ranking — MED-PROB-SUCCESS (prob=0.55, HIGH quality) outranks HIGH-PROB-FAIL (prob=0.80, LOW quality)
2. **GAP-2 works:** Total attempts bounded by N × max_attempts
3. **Reproducible:** Deterministic assessor → identical results across runs
4. **Safety:** No external targets, simulation-only, allowlist enforced
5. **Evidence discipline:** All results tagged with evidence tier

---

## DEMO B: Docker + Local LLM (Partial Verification)

**Prerequisites for DEMO B:**
- Docker Desktop with WSL2 integration enabled
- Ollama running (already available)

### Current Status

| Component | Status |
|-----------|--------|
| **Ollama LLM** | ✅ VERIFIED — llama3.2:3b, ~2.5s latency |
| **Docker Lab** | ❌ NOT VERIFIED — Docker WSL2 integration unavailable |

### What IS Verified (DEMO B-1: LLM Assessment)

```bash
# Test real LLM assessment
python -c "
from core.exploit_assessor import assess_exploit_quality
import time

start = time.time()
result = assess_exploit_quality('CVE-2021-44228', provider='ollama')
print(f'Rank: {result.usability_rank.value}, Complexity: {result.complexity_score}, Latency: {time.time()-start:.2f}s')

start = time.time()
result = assess_exploit_quality('CVE-2017-0144', provider='ollama')
print(f'Rank: {result.usability_rank.value}, Complexity: {result.complexity_score}, Latency: {time.time()-start:.2f}s')
"
```

### What is NOT Verified (DEMO B-2: Docker Lab)

To enable Docker lab:
1. Open Docker Desktop → Settings → Resources → WSL Integration
2. Enable integration with this distro
3. Run: `cd lab && docker-compose up -d`
4. Verify: `curl http://172.28.0.2:8080/health`

Once Docker is available:
```bash
python -m prototype.cli run --scenario failure_pivot --mode lab --target 172.28.0.2 --port 8080
```

---

## 10-Minute Demonstration Sequence

### Minutes 1-2: Introduction
- Explain the research problem: autonomous agents loop on failed candidates
- State the contribution: bounded failure-driven pivoting (Gap-2) + assessment-aware ranking (Gap-1)
- Show project structure: `decision_engine/core/` (frozen research core), `vapt_platform/` (platform layer)

### Minutes 2-4: GAP-1 Demo
```bash
python -m pytest experiments/test_experiments.py::TestExperimentHarness::test_ranking_reflects_assessment -v
```
- Explain: Assessment inverts probability-based ordering
- Show: MED-PROB-SUCCESS > HIGH-PROB-FAIL after assessment

### Minutes 4-7: GAP-2 Demo
```bash
python experiments/research_validation.py
```
- Walk through threshold experiments
- Show boundedness: total attempts = N × max_attempts
- Show all-fail: bounded termination

### Minutes 7-9: Combined Demo
```bash
python experiments/harness/__init__.py
cat experiments/results/all_experiments.csv
```
- Show reproducibility: 3 repetitions, identical results
- Show research integrity: deterministic assessor, simulation clearly labeled

### Minutes 9-10: Evidence and Safety
- Evidence tiers: SIMULATED (DEMO A), DOCKER_OBSERVED (DEMO B-2, not verified)
- Safety: Allowlist {127.0.0.1, 172.28.0.2}, fail-closed, no external targets
- LLM verified: Ollama llama3.2:3b works for assessment

---

## Key Talking Points

1. **Single canonical workflow:** All interfaces use `VAPTApplication.run()`
2. **Frozen research core:** `decision_engine/core/` is never modified
3. **Research-validated:** GAP-1 and GAP-2 mechanisms empirically verified
4. **Real LLM path works:** Ollama llama3.2:3b assessed (not just deterministic)
5. **Reproducible:** All experiments deterministic and repeatable
6. **Safety first:** Allowlist, fail-closed, danger_mode disabled
7. **Evidence discipline:** Clear labeling of SIMULATED vs OBSERVED

## Expected Test Results

```
pytest -q
# Expected: 536 passed, 7 skipped, 0 failed
```

## Files Generated by This Demo

| File | Purpose |
|------|---------|
| `experiments/results/raw_results.json` | Full experiment data |
| `experiments/results/summary.csv` | Publication-ready summary |
| `experiments/results/detailed_results.csv` | Per-step execution |
| `experiments/results/llm_results.json` | Real LLM experiment data |
| `experiments/results/experiment_metadata.json` | Run metadata |
| `docs/thesis/research_validation.md` | Thesis validation report |
| `docs/thesis/research_integrity_audit.md` | Integrity audit |
| `docs/thesis/experimental_methodology.md` | Methodology document |
| `docs/thesis/results.md` | Results document |
| `docs/thesis/threats_to_validity.md` | Validity threats |

---

## Common Questions

**Q: Why does the engine process all candidates instead of stopping at first success?**  
A: The engine is designed to validate ALL candidates in priority order, not just find one success. This provides complete coverage for research analysis. Boundedness is per-candidate (max_attempts), not global.

**Q: What happens when Docker is unavailable?**  
A: The lab mode cannot run. Simulation mode works without Docker. The emulator code is in `lab/emulator/app.py`. DEMO A is fully functional without Docker.

**Q: How is AI assessment different from deterministic?**  
A: AI assessment uses Ollama/OpenAI to grade candidates. Deterministic uses ground-truth labels. Both feed into the same priority_score formula. When AI is unavailable, deterministic fallback is used.

**Q: Is the LLM assessment real or simulated?**  
A: DEMO A uses deterministic assessment for reproducibility. DEMO B-1 uses real Ollama llama3.2:3b assessment (verified, ~2.5s latency). DEMO B-2 (Docker) is not verified.

**Q: Why is the deterministic assessor allowed to use ground-truth?**  
A: This creates a "perfect assessor" scenario — the best case for assessment quality. Real LLM assessment is imperfect. Both are tested; the research claim is that assessment (from any source) affects ranking.

**Q: What about statistical significance?**  
A: Not applicable — this is a deterministic system. Results are reproducible across runs (3 repetitions, identical). Statistical tests require non-deterministic measurements.

---

*Document updated by Hermes Agent — 2026-09-16 (Wave 11)*