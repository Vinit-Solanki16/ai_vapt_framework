# Phase 15 Plan: OBSERVED_LOCAL Evidence Tier

## Objective

Complete the evidence taxonomy by distinguishing loopback (127.0.0.1) observations
from Docker-isolated (172.28.0.2) observations.

Current:  simulation → SIMULATED, lab → DOCKER_OBSERVED, real → CONTROLLED VALIDATION
Target:   simulation → SIMULATED, lab_loopback → OBSERVED_LOCAL, lab_docker → DOCKER_OBSERVED, real → CONTROLLED VALIDATION

## Why This Matters

- Loopback (127.0.0.1) hits the host network stack directly — less isolated than Docker
- Calling both "DOCKER_OBSERVED" is inaccurate — loopback is NOT Docker-isolated
- Thesis evidence discipline requires honest tiering
- Small, well-bounded change — no architecture changes, no new features

## Files to Modify

1. `prototype/execution_layer.py` — add `lab_loopback` and `lab_docker` mode strings
2. `prototype/report_generator.py` — update `_get_evidence_tier()` mapping
3. `prototype/report_generator.py` — update `_get_evidence_tier_description()`
4. `prototype/report_generator.py` — update safety notice in `_build_report_dict()`
5. `prototype/tests/test_report.py` — add tests for OBSERVED_LOCAL tier
6. `prototype/tests/test_execution_layer.py` — verify mode routing

## Files NOT to Modify

- decision_engine/ (frozen)
- core/ (frozen)
- lab/ (Docker architecture frozen)
- docs/ (no documentation changes needed)

## Implementation Steps

1. In `execution_layer.py`:
   - `create_lab_executor()` should return executor with mode="lab_loopback" for 127.0.0.1
   - `create_lab_executor()` should return executor with mode="lab_docker" for 172.28.0.2
   - OR: keep mode="lab" and add a sub-mode parameter

2. In `report_generator.py`:
   - `_get_evidence_tier()`: add "lab_loopback" → "OBSERVED_LOCAL"
   - `_get_evidence_tier_description()`: add "lab_loopback" → "Outcomes observed from loopback (127.0.0.1) target"
   - `_build_report_dict()`: update safety notice for lab_loopback

3. In `test_report.py`:
   - Add `test_evidence_tier_loopback()` — verify loopback maps to OBSERVED_LOCAL
   - Update `test_evidence_tier_helper()` — add lab_loopback assertion
   - Update `test_evidence_tier_description_helper()` — verify loopback description

4. Run full test suite: expect 183+ tests (182 + new loopback test)

## Acceptance

- simulation → SIMULATED (unchanged)
- lab_loopback (127.0.0.1) → OBSERVED_LOCAL (NEW)
- lab_docker (172.28.0.2) → DOCKER_OBSERVED (unchanged)
- real → CONTROLLED VALIDATION (unchanged)
- All tests pass
- No Docker architecture changes
- No allowlist changes
- One commit with clear message

## Commit Message

```
refactor: add OBSERVED_LOCAL evidence tier for loopback targets

- lab_loopback (127.0.0.1) → OBSERVED_LOCAL
- lab_docker (172.28.0.2) → DOCKER_OBSERVED (unchanged)
- simulation → SIMULATED (unchanged)
- real → CONTROLLED VALIDATION (unchanged)
```

## Stop Conditions

STOP if:
- Docker architecture needs changes (report, don't fix)
- Allowlist behavior changes unexpectedly
- More than 4 files need modification
- Tests regress
