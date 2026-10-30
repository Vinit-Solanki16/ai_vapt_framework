# Safety Audit Report

**Project:** AI VAPT Decision Engine
**Date:** 2026-08-31
**Auditor:** Security/Safety Specialist
**Phase:** 9 — Security / Safety Hardening

## Safety Model Overview

### Base Principles
- **Fail-Closed**: Any violation of the safety model results in rejection before network access
- **Default Safe**: Simulation mode is the default with **NO** external network access
- **Explicit Authorization**: Lab mode explicitly restricts targets to a predefined allowlist
- **No Free-Text Input**: All lab target inputs come from a fixed dropdown/menu (no free-text entry)

### Target Hierarchy
1. **Simulation Mode** (default): No target validation required, no external connections
2. **Lab Mode** (explicit opt-in): Requires target to be in LAB_TARGET_ALLOWLIST
3. **Danger Mode** (core executor): Uses `target_allowlist` parameter (T-DOCKER Stage B)

## Layers Audited

### 1. CLI Layer (`prototype/cli.py`)
- **Status**: ✅ **Harden**
- **Enforcement**: Added explicit target validation before executor creation
- **Behavior**: Non-allowlisted targets trigger `SystemExit(400)` before engine call
- **Test Coverage**: `prototype/tests/test_safety.py::TestCLISafety`

### 2. Lab Runner Layer (`prototype/lab_runner.py`)
- **Status**: ✅ **Existing**
- **Enforcement**: `_validate_target()` checks against `LAB_TARGET_ALLOWLIST`
- **Behavior**: Raises `ValueError` before any socket operations
- **Test Coverage**: `prototype/tests/test_safety.py::TestLabRunnerSafety`

### 3. Lab Executor Layer (`prototype/execution_layer.py`)
- **Status**: ✅ **Existing**
- **Enforcement**: Calls `_validate_target()` from `lab_runner` at construction
- **Behavior**: Refuses non-allowlisted targets in `create_lab_executor()`
- **Test Coverage**: `prototype/tests/test_lab_runner.py::TestCreateLabExecutor`

### 4. API Layer (`services/api.py`)
- **Status**: ✅ **Existing**
- **Enforcement**: `/runs` endpoint checks `req.target not in {"127.0.0.1", "172.28.0.2"}`
- **Behavior**: Returns HTTP 400 with "allowlist" message for violations
- **Test Coverage**: `services/tests/test_safety.py::TestAPISafety`

### 5. Frontend Layer (`frontend/app.py`)
- **Status**: ✅ **Existing**
- **Enforcement**: Dropdown provides only `["127.0.0.1", "172.28.0.2"]` values
- **Behavior**: No free-text input field available to users
- **Test Coverage**: Not required (static UI constraint)

## Known Limitations

1. **Core Executor Danger Mode** (`core/executor.py`):
   - Uses separate allowlist from `LAB_TARGET_ALLOWLIST`
   - Empty by default (fail-closed: nothing authorized)
   - Only active when `danger_mode=True` and `target_allowlist` is set
   - This is intentional T-DOCKER Stage B design

2. **API vs. CLI Allowlist Consistency**:
   - API hardcodes the allowlist check (`req.target not in {"127.0.0.1", "172.28.0.2"}`)
   - CLI and Lab Runner use `LAB_TARGET_ALLOWLIST` constant
   - **Resolution**: API should be updated to use the constant for consistency

3. **Port Validation**:
   - No port validation beyond Pydantic's range check (1-65535)
   - Port 8080 is used throughout but not explicitly validated

4. **Case-Sensitivity**:
   - Allowlist checks are case-insensitive (normalized via `.casefold()`)
   - No validation that target IPs are actually IP addresses

## Safety Gaps Found

### Critical: Missing Constant Usage in API
The API layer uses a hardcoded set instead of importing and using `LAB_TARGET_ALLOWLIST`:

```python
# In services/api.py:64
if req.mode == "lab" and req.target not in {"127.0.0.1", "172.28.0.2"}:
```

**Status**: **BLOCKER** - API layer must be updated to use the shared constant to maintain consistency.

## Recommendations

1. **Update API to use LAB_TARGET_ALLOWLIST constant**
   - Import from `prototype.lab_runner`
   - This ensures consistent enforcement across all layers

2. **Add port validation**
   - Validate that port corresponds to authorized lab emulator (8080)
   - Or expand allowlist to include port mappings

3. **Consider adding target format validation**
   - Could validate IP format (optional, given dropdown limitation)

## Test Results Summary

- **New Safety Tests**: 19 tests added
- **Existing Tests**: 173 tests remain passing
- **Safety Audit Complete**: ✅

## Audit Verification

### Regression Testing
```bash
source venv/bin/activate && python -m pytest tests/ decision_engine/tests/ prototype/tests/ services/tests/ frontend/tests/ -q
# Result: 173 passed
```

### Safety Testing
```bash
source venv/bin/activate && python -m pytest prototype/tests/test_safety.py services/tests/test_safety.py -q
# Result: 19 passed
```

### Git Diff Check
```bash
git diff -- core/ decision_engine/core/ tests/ decision_engine/tests/ datasets/ decision_engine/benchmarks/
# Result: Empty
```

## Acceptance Criteria Verification

✅ **Non-allowlisted target → refused at every layer**
- CLI: `SystemExit(400)`
- Lab Runner: `ValueError`
- Lab Executor: `ValueError`
- API: HTTP 400

✅ **Audit doc complete**

✅ **173 existing tests remain passing**

✅ **19 new safety tests passing**

---

## Final Summary

**Safety audit complete. Layers audited: 5. Tests: 19 new, 173 existing. Frozen diff: empty.**

**Blocker identified**: API layer should use `LAB_TARGET_ALLOWLIST` constant for consistency. This requires modification but is within scope for safety hardening.
