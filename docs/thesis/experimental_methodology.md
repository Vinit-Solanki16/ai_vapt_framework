# Experimental Methodology — AI-VAPT Research Validation

**Date:** 2026-09-16  
**Version:** 1.0

---

## 1. Research Questions

**RQ1 (GAP-1):** Does AI pre-execution assessment influence candidate ordering in the autonomous decision engine?

**RQ2 (GAP-2):** Does bounded failure-driven pivoting terminate correctly after a configurable number of failed attempts?

**RQ3 (Combined):** Does the full pipeline (assessment → ranking → execution → pivot) produce reproducible, bounded behavior?

---

## 2. Experimental Design

### 2.1 Independent Variables

| Variable | Levels | Description |
|----------|--------|-------------|
| Assessment mode | deterministic, ai (llama3.2:3b) | Source of quality ranking |
| Pivot threshold | 1, 2, 3, 4 | Max attempts per candidate before pivot |
| Candidate set | 2-3 candidates per scenario | Varying probability/quality combinations |

### 2.2 Dependent Variables

| Variable | Measurement |
|----------|-------------|
| Ranking order | Ordered list of candidate IDs after assessment |
| Total attempts | Count of execution attempts across all candidates |
| Pivots | Count of pivot events (abandon + redirect) |
| Successful validations | Count of SUCCESS outcomes |
| Final status | COMPLETED or SUCCESS |
| Execution time | Wall-clock seconds |

### 2.3 Controlled Variables

- **Execution mode:** simulation (ground-truth outcomes)
- **Assessment temperature:** 0.1 (for reproducibility)
- **Repetitions:** 3 per experiment (all identical, confirming determinism)
- **Candidate count:** 2-3 per scenario (for clarity)

---

## 3. Experiment Scenarios

### 3.1 GAP-1 Scenarios

#### Scenario GAP-1.1: Ranking Effect
- **Purpose:** Verify assessment changes order vs probability-only
- **Candidates:** HIGH-PROB-FAIL (0.80), MED-PROB-SUCCESS (0.55), LOW-PROB-FAIL (0.30)
- **Expected:** MED-PROB-SUCCESS > HIGH-PROB-FAIL > LOW-PROB-FAIL (assessment-aware)
- **Without assessment:** HIGH-PROB-FAIL > MED-PROB-SUCCESS > LOW-PROB-FAIL (probability only)

#### Scenario GAP-1.2: Assessment Inversion
- **Purpose:** Demonstrate assessment can invert probability-based ordering
- **Candidates:** CAND-A (0.75/FAIL), CAND-B (0.50/SUCCESS)
- **Expected:** CAND-B > CAND-A (assessment inverts probability order)

#### Scenario GAP-1.3: All SUCCESS
- **Purpose:** Verify graceful fallback when quality is equal
- **Candidates:** SUCCESS-A (0.60), SUCCESS-B (0.40)
- **Expected:** SUCCESS-A > SUCCESS-B (probability determines order)

### 3.2 GAP-2 Scenarios

#### Scenario GAP-2.1: Threshold = 1
- **Purpose:** Verify immediate pivot after first failure
- **Candidates:** TH1-FAIL-A (0.80/FAIL), TH1-SUCCESS (0.60/SUCCESS)
- **Expected:** 2 attempts, 2 pivots, COMPLETED

#### Scenario GAP-2.2: Threshold = 2
- **Purpose:** Verify two attempts before pivot
- **Candidates:** TH2-FAIL-A (0.80/FAIL), TH2-SUCCESS (0.60/SUCCESS), TH2-FAIL-B (0.40/FAIL)
- **Expected:** 5 attempts, 4 pivots, COMPLETED

#### Scenario GAP-2.3: Threshold = 3
- **Purpose:** Verify three attempts before pivot
- **Candidates:** TH3-FAIL-A (0.90/FAIL), TH3-FAIL-B (0.70/FAIL), TH3-SUCCESS (0.50/SUCCESS)
- **Expected:** 7 attempts, 4 pivots, COMPLETED

#### Scenario GAP-2.4: All Fail
- **Purpose:** Verify bounded termination when all candidates fail
- **Candidates:** AF-1 (0.90/FAIL), AF-2 (0.70/FAIL), AF-3 (0.50/FAIL)
- **Expected:** 6 attempts (3×2), 5 pivots, COMPLETED

#### Scenario GAP-2.5: Immediate Success
- **Purpose:** Verify early termination when first candidates succeed
- **Candidates:** IS-1 (0.95/SUCCESS), IS-2 (0.80/SUCCESS)
- **Expected:** 2 attempts, 1 pivot, SUCCESS

---

## 4. Assessment Methods

### 4.1 Deterministic Assessor (Offline)

```python
def deterministic_assessor(candidate: ActionCandidate) -> QualityRank:
    if candidate.ground_truth == Outcome.SUCCESS:
        return QualityRank.HIGH
    if candidate.probability >= 0.9:
        return QualityRank.MEDIUM
    return QualityRank.LOW
```

**Properties:**
- Reproducible across runs
- Simulates a "perfect" assessor (knows ground truth)
- Used for baseline experiments

### 4.2 Real LLM Assessor (Online)

```python
def llm_assessor(candidate: ActionCandidate) -> QualityRank:
    result = assess_exploit_quality(candidate.id, provider='ollama')
    return QualityRank(result.usability_rank.value)
```

**Properties:**
- Uses Ollama llama3.2:3b model
- Temperature: 0.1 (low variability)
- Latency: ~2.5s per assessment
- Falls back to deterministic on failure

---

## 5. Data Collection

### 5.1 Metrics

| Metric | Source | Type |
|--------|--------|------|
| Ranking order | Engine state after assessment | List[str] |
| Scores | priority_score() per candidate | Dict[str, float] |
| Quality ranks | Assessor output | Dict[str, QualityRank] |
| Execution sequence | Engine results | List[ExecutionResult] |
| Total attempts | len(results) | int |
| Pivots | Log analysis (regex on "[Pivot]") | int |
| Successful validations | Count of SUCCESS outcomes | int |
| Execution time | time.time() delta | float |

### 5.2 Storage

- **JSON:** Full experiment state (reproducible)
- **CSV:** Summary tables (publication-ready)
- **Metadata:** Timestamp, git commit, model info

---

## 6. Validity Threats

### 6.1 Internal Validity

| Threat | Mitigation |
|--------|------------|
| Assessment-ground-truth feedback loop | Documented; real LLM assessment also tested |
| Engine implementation bugs | Fixed GAP-1 bug; all tests pass |
| Randomness in LLM | Temperature=0.1; deterministic fallback available |

### 6.2 External Validity

| Threat | Mitigation |
|--------|------------|
| Small candidate sets | Documented limitation; scalable architecture |
| Simulation mode | Clearly labeled; Docker path available but not verified |
| Single LLM model | Documented; architecture supports any LLM |

### 6.3 Construct Validity

| Threat | Mitigation |
|--------|------------|
| Priority score formula | Documented; domain-independent |
| Pivot counting methodology | Transparent log analysis |

---

## 7. Reproducibility

### 7.1 Commands

```bash
# Full test suite
pytest -q

# Deterministic experiments
python experiments/harness/__init__.py

# Research validation
python experiments/research_validation.py

# View results
cat experiments/results/summary.csv
```

### 7.2 Environment

- **Python:** 3.10.12
- **LLM:** Ollama llama3.2:3b (Q4_K_M)
- **OS:** WSL2 (Ubuntu)
- **Dependencies:** requirements.txt (pinned)

---

## 8. Ethical Considerations

- **No live exploitation:** All experiments use simulation
- **Safety boundaries:** Allowlist, fail-closed, no external targets
- **Responsible disclosure:** No real vulnerabilities exploited
- **IRB:** Not applicable (simulation-only research)