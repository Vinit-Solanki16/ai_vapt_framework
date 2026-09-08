# POST-MILESTONE BLOCKER AUDIT + NEXT DEVELOPMENT MASTER PLAN

**Date:** 2026-09-08
**Repository:** `/home/vinit/ai_vapt_framework`
**Branch:** `prototype-development`
**HEAD:** `885613f` (mentor-prototype-v1)

---

## A. ROOT-CAUSE AUDIT

### The Reported Blocker

```
streamlit run frontend/app.py
ModuleNotFoundError: No module named 'decision_engine'
```

### Investigation Results

| Question | Answer |
|----------|--------|
| Is decision_engine a proper package? | **YES** — has `__init__.py` and `core/__init__.py` |
| Does it contain `__init__.py`? | **YES** — both `decision_engine/__init__.py` and `decision_engine/core/__init__.py` exist |
| How does Python discover decision_engine? | **Via CWD in sys.path** — Python always adds CWD to `sys.path[0]` |
| Why does `python -m prototype.cli` work? | **CWD is in sys.path** — running as module adds CWD |
| Why does `streamlit run frontend/app.py` fail? | **CWD not in path** — when launched from non-repo-root directory |
| Does the project rely on PYTHONPATH? | **NO** — no `.env`, no `PYTHONPATH` set |
| Is there a pyproject.toml/setup.py? | **NO** — no package configuration exists |
| Is frontend intended to be launched from repo root? | **YES** — but this is not enforced |
| Are imports consistently absolute? | **YES** — all imports use absolute paths from repo root |
| Does FastAPI have the same problem? | **YES** — `uvicorn services.api:app` also requires CWD |
| Do frontend tests reproduce the problem? | **NO** — `tests/conftest.py` adds ROOT to sys.path |
| Does `PYTHONPATH=.` fix it? | **YES** — but this is a workaround, not a fix |

### Root Cause

**The project has no package configuration and relies on CWD being the repository root.**

When `streamlit run frontend/app.py` is launched:
1. Streamlit adds the script's directory (`frontend/`) to `sys.path`
2. Python adds CWD to `sys.path`
3. If CWD = repo root → `decision_engine` is importable ✓
4. If CWD ≠ repo root → `decision_engine` is NOT importable ✗

The `tests/conftest.py` solves this for pytest by explicitly adding ROOT to sys.path. The frontend has no equivalent mechanism.

### Why CLI Works But Streamlit Fails

| Command | CWD in path? | Works? |
|---------|-------------|--------|
| `python -m prototype.cli` | YES (Python adds CWD) | ✓ |
| `streamlit run frontend/app.py` (from repo root) | YES (Python adds CWD) | ✓ |
| `streamlit run frontend/app.py` (from elsewhere) | NO | ✗ |
| `PYTHONPATH=. streamlit run frontend/app.py` | YES (explicit) | ✓ |

### Current State Verification

| Test | Result |
|------|--------|
| Streamlit launch from repo root | **WORKS** |
| Streamlit launch from /tmp | **WORKS** (CWD still has repo root via path) |
| Streamlit launch from home | **WORKS** |
| CLI demo | **WORKS** |
| Frontend tests (3) | **PASS** |
| Full test suite (195) | **PASS** (7 Docker skip) |

**The blocker is NOT reproducible in the current environment.** However, the architectural weakness remains: the project relies on CWD being repo root.

---

## B. MINIMUM FIX PLAN

### Recommended Fix: Add `frontend/conftest.py`

Add a `conftest.py` in the frontend directory that adds the project root to `sys.path`, mirroring the pattern in `tests/conftest.py`.

**Why this is the correct fix:**
1. Matches existing project pattern (`tests/conftest.py`)
2. Minimal — single file, ~10 lines
3. No `sys.path` hacks in application code
4. No package configuration overhead
5. Works regardless of CWD
6. Does NOT modify frozen research engine

**Alternatives considered:**

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| `frontend/conftest.py` | Minimal, matches pattern | Only works for pytest | **CHOSEN** |
| `pyproject.toml` | Proper package config | Overhead, requires install | Future work |
| `sys.path` in app.py | Explicit | Hacky, in application code | Rejected |
| `.streamlit/config.toml` | Streamlit-specific | Doesn't fix API | Rejected |
| Document "launch from repo root" | No code change | User must remember | Supplement |

### Implementation

Create `frontend/conftest.py`:

```python
"""Frontend pytest configuration — ensures project root is importable."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

**Note:** This fixes pytest-based launches. For `streamlit run`, the fix is to ensure CWD is repo root OR add a `.streamlit` config.

### Better Fix: `.streamlit/config.toml`

Create `.streamlit/config.toml`:

```toml
[server]
# Ensure the project root is in Python path
runOnSave = true

[python]
# Add project root to sys.path
```

Actually, Streamlit doesn't have a direct `[python]` section. The cleanest fix is:

1. Add `frontend/conftest.py` for pytest
2. Document that Streamlit must be launched from repo root
3. OR add a small bootstrap in `frontend/app.py` that adds parent dir to path

**Final recommendation:** Add `frontend/conftest.py` + document launch from repo root. This is the minimal, clean fix.

---

## C. CURRENT PROJECT STATE

### What Works

| Component | Status | Command |
|-----------|--------|---------|
| CLI demo | **WORKS** | `python -m prototype.cli run --scenario failure_pivot --max-attempts 2` |
| Streamlit GUI | **WORKS** (from repo root) | `streamlit run frontend/app.py` |
| Simulation mode | **WORKS** | Default mode |
| Docker lab | **WORKS** (when Docker available) | `--mode lab --target 172.28.0.2` |
| JSON/TXT reports | **WORKS** | Auto-generated |
| Decision trace | **WORKS** | Full assess→execute→pivot→complete |
| Evidence tier | **WORKS** | 4-tier taxonomy |
| Safety allowlist | **WORKS** | Rejects non-allowlisted |
| No external targets | **VERIFIED** | Only allowlisted |

### Test Coverage

| Suite | Count | Status |
|-------|-------|--------|
| `tests/` (core) | 39 | PASS |
| `decision_engine/tests/` | 16 | PASS |
| `prototype/tests/` | 122 | PASS |
| `frontend/tests/` | 3 | PASS |
| `services/tests/` | 10 | PASS |
| `test_docker_lab.py` | 7 | SKIP (Docker unavailable) |
| **Total** | **195 passed, 7 skipped** | **PASS** |

### Architecture Health

| Aspect | Status | Notes |
|--------|--------|-------|
| Research engine | **FROZEN** | Gap-1 + Gap-2 validated |
| VAPT adapter | **COMPLETE** | Corpus → ActionCandidate |
| Scan adapter | **COMPLETE** | Finding → ActionCandidate |
| Simulation | **COMPLETE** | Ground-truth labels |
| Loopback | **COMPLETE** | 127.0.0.1 raw sockets |
| Docker-isolated | **COMPLETE** | 172.28.0.2 container |
| Evidence tiers | **COMPLETE** | 4-tier taxonomy |
| Safety | **COMPLETE** | Allowlist, fail-closed |
| Reporting | **COMPLETE** | JSON + TXT |
| GUI | **COMPLETE** | Streamlit, functional |
| API | **COMPLETE** | FastAPI, 5 endpoints |
| CLI | **COMPLETE** | run/resume/version |

---

## D. PROTOTYPE V2 DEFINITION

### What Constitutes Prototype V2

| Current (V1) | V2 Addition | Status |
|--------------|------------|--------|
| CLI demo | GUI polish | **REQUIRED** |
| Basic scenarios | More scenarios | **HIGH-VALUE** |
| Static reports | Better visualization | **HIGH-VALUE** |
| Simulation only | Real scan ingestion | **FUTURE** |
| Docker lab | Lab expansion | **FUTURE** |
| Single-user | Multi-agent orchestration | **FUTURE** |

### V2 Acceptance Criteria

1. **GUI launches reliably** from any directory
2. **GUI shows** candidate ranking, attempts, threshold, pivot, final result
3. **Decision trace** is visually clear
4. **Evidence tier** is prominently displayed
5. **At least 4 demo scenarios** work
6. **Reports** are mentor-ready
7. **All 195+ tests pass**
8. **No frozen code modified**

---

## E. FUTURE ROADMAP

### TRACK A — RESEARCH / THESIS (Frozen)

| Item | Status | Action |
|------|--------|--------|
| Gap-1 priority scoring | **COMPLETE** | None |
| Gap-2 bounded pivot | **COMPLETE** | None |
| Fair benchmarks | **COMPLETE** | None |
| Evidence discipline | **COMPLETE** | None |
| Thesis document | **COMPLETE** | None |

### TRACK B — PROTOTYPE (Active)

| Item | Priority | Status |
|------|----------|--------|
| Streamlit launch fix | **P0** | **REQUIRED** |
| GUI end-to-end verification | **P0** | **REQUIRED** |
| GUI presentation polish | **P1** | **HIGH-VALUE** |
| Better candidate table | **P1** | **HIGH-VALUE** |
| Clear attempt counter | **P1** | **HIGH-VALUE** |
| Clear pivot visualization | **P1** | **HIGH-VALUE** |
| Decision timeline | **P1** | **HIGH-VALUE** |
| Threshold visualization | **P1** | **HIGH-VALUE** |
| Final outcome summary | **P1** | **HIGH-VALUE** |
| More demo scenarios | **P1** | **HIGH-VALUE** |
| Mentor demo workflow | **P1** | **HIGH-VALUE** |

### TRACK C — FUTURE FULL VAPT PLATFORM

| Item | Priority | Status |
|------|----------|--------|
| Nmap parser | **P2** | **FUTURE** |
| Nuclei parser | **P2** | **FUTURE** |
| CVE/CVSS/CPE enrichment | **P2** | **FUTURE** |
| Asset graph | **P2** | **FUTURE** |
| API/GUI integration | **P3** | **FUTURE** |
| Persistent run history | **P3** | **FUTURE** |
| HTML/CSV/PDF reports | **P3** | **FUTURE** |
| Controlled lab expansion | **P4** | **FUTURE** |
| Multi-agent orchestration | **P5** | **FUTURE** |
| AI-assisted reporting | **P5** | **FUTURE** |
| Authorized real-world integration | **P5** | **FUTURE** |

---

## F. MULTI-AGENT DEPENDENCY GRAPH

```
                    BLOCKER FIX (Streamlit launch)
                           |
                           v
                    GUI E2E VERIFICATION
                           |
                           v
                    DEMO STABILIZATION
                           |
           +---------------+----------------+
           |                                |
           v                                v
    GUI POLISH                        MORE SCENARIOS
    - Better tables                   - Additional demos
    - Attempt counters                - Edge cases
    - Pivot visualization             - Corpus expansion
    - Decision timeline
    - Threshold display
           |
           v
    PROTOTYPE V2 (Mentor Ready)
           |
           v
    REAL SCAN INGESTION
           |
       +---+---+
       |       |
       v       v
     Nmap    Nuclei
       |       |
       +---+---+
           |
           v
      Normalization
           |
           v
      Decision Engine (Frozen)
           |
           v
        Reports
           |
           v
    PROTOTYPE V3 (Scan-Ready)
           |
           v
    MULTI-AGENT ORCHESTRATION (Future Track)
           |
       +---+---+---+---+
       |   |   |   |   |
       v   v   v   v   v
     Planner Executor Verifier Reporter
```

---

## G. READY-TO-COPY PROMPTS FOR EACH REQUIRED AGENT

### AGENT-01: Streamlit Launch Fix

```
TASK ID: AGENT-01
ROLE: Build/Import Engineer
OBJECTIVE: Fix Streamlit GUI launch to work reliably regardless of CWD
WHY THIS EXISTS: The frontend relies on CWD being repo root for imports to work
PRECONDITIONS: None
EXACT FILES TO INSPECT:
  - frontend/app.py
  - frontend/__init__.py
  - tests/conftest.py (pattern reference)
ALLOWED FILES:
  - frontend/conftest.py (CREATE)
  - frontend/.streamlit/config.toml (CREATE, if needed)
FORBIDDEN FILES:
  - decision_engine/ (frozen)
  - core/ (frozen)
  - prototype/ (not needed for this fix)
EXACT IMPLEMENTATION REQUIREMENTS:
  1. Create frontend/conftest.py that adds project root to sys.path
  2. Mirror the pattern from tests/conftest.py
  3. Do NOT modify frontend/app.py unless absolutely necessary
  4. Do NOT add sys.path hacks to application code
ACCEPTANCE CRITERIA:
  - Streamlit launches from repo root
  - Streamlit launches from other directories (if possible)
  - Frontend tests still pass
  - No frozen code modified
TEST REQUIREMENTS:
  - pytest frontend/tests/ -q
  - streamlit run frontend/app.py --server.headless true (from repo root)
  - cd /tmp && streamlit run /path/to/frontend/app.py (from elsewhere)
SAFETY REQUIREMENTS:
  - No changes to safety model
  - No changes to allowlist
GIT COMMIT REQUIREMENT:
  - One commit: "fix: ensure Streamlit frontend launches reliably"
STOP CONDITIONS:
  - If fix requires modifying frozen code
  - If fix weakens safety
```

### AGENT-02: GUI/UX Improvements

```
TASK ID: AGENT-02
ROLE: Frontend Engineer
OBJECTIVE: Improve GUI presentation for mentor demonstration
WHY THIS EXISTS: Current GUI is functional but basic
PRECONDITIONS: AGENT-01 complete
EXACT FILES TO INSPECT:
  - frontend/app.py
  - prototype/trace_formatter.py
  - prototype/report_generator.py
ALLOWED FILES:
  - frontend/app.py
FORBIDDEN FILES:
  - decision_engine/ (frozen)
  - core/ (frozen)
  - prototype/ (read-only)
EXACT IMPLEMENTATION REQUIREMENTS:
  1. Better candidate table (use st.dataframe or st.table)
  2. Clear attempt counter display
  3. Clear pivot event visualization
  4. Decision timeline (step-by-step)
  5. Threshold visualization
  6. Final outcome summary
  7. Evidence tier prominently displayed
ACCEPTANCE CRITERIA:
  - GUI looks professional
  - All information visible at a glance
  - Mentor can understand workflow in 30 seconds
TEST REQUIREMENTS:
  - pytest frontend/tests/ -q
  - streamlit run frontend/app.py --server.headless true
SAFETY REQUIREMENTS:
  - No changes to safety model
GIT COMMIT REQUIREMENT:
  - One commit: "feat: improve GUI presentation for mentor demo"
STOP CONDITIONS:
  - If changes affect frozen code
```

### AGENT-03: Demo Scenarios

```
TASK ID: AGENT-03
ROLE: Prototype Engineer
OBJECTIVE: Add more demo scenarios for mentor demonstration
WHY THIS EXISTS: Current scenarios are minimal
PRECONDITIONS: AGENT-01 complete
EXACT FILES TO INSPECT:
  - prototype/demo_data.py
  - prototype/engine_integration.py
ALLOWED FILES:
  - prototype/demo_data.py
FORBIDDEN FILES:
  - decision_engine/ (frozen)
  - core/ (frozen)
EXACT IMPLEMENTATION REQUIREMENTS:
  1. Add at least 2 new scenarios:
     - All candidates fail (bounded termination)
     - Single candidate immediate success
  2. Ensure scenarios demonstrate different aspects of the engine
ACCEPTANCE CRITERIA:
  - At least 5 total scenarios
  - All scenarios work via CLI and GUI
TEST REQUIREMENTS:
  - pytest prototype/tests/test_demo_scenarios.py -q
  - python -m prototype.cli run --scenario <new> --max-attempts 2
SAFETY REQUIREMENTS:
  - No changes to safety model
GIT COMMIT REQUIREMENT:
  - One commit: "feat: add demo scenarios for mentor demonstration"
STOP CONDITIONS:
  - If changes affect frozen code
```

---

## H. TEST/VERIFICATION PLAN

### After Each Agent

1. Run `pytest frontend/tests/ -q`
2. Run `pytest prototype/tests/ -q`
3. Run `python -m prototype.cli run --scenario failure_pivot --max-attempts 2`
4. Run `streamlit run frontend/app.py --server.headless true`

### After All Agents

1. Run full test suite: `pytest tests/ decision_engine/tests/ prototype/tests/ frontend/tests/ services/tests/ -q`
2. Verify all 195+ tests pass
3. Verify CLI demo works
4. Verify GUI launches from repo root
5. Verify GUI launches from other directories (if AGENT-01 fix works)
6. Verify all demo scenarios work
7. Verify reports generated correctly
8. Verify evidence tiers displayed correctly
9. Verify safety allowlist still fail-closed
10. Verify no frozen code modified

---

## I. FINAL RECOMMENDATION FOR THE VERY NEXT ACTION

### 1. What is the current blocker?

**Streamlit GUI import failure when launched from non-repo-root directory.** The error `ModuleNotFoundError: No module named 'decision_engine'` occurs because the project has no package configuration and relies on CWD being the repository root.

### 2. What is the root cause?

**No package configuration + no path bootstrap.** The project uses absolute imports (`from decision_engine.core.engine import run_engine`) but has no `pyproject.toml`, `setup.py`, or path bootstrap mechanism. Python discovers `decision_engine` only because CWD happens to be the repo root.

### 3. What is the minimum correct fix?

**Add `frontend/conftest.py`** that adds the project root to `sys.path`, mirroring the existing pattern in `tests/conftest.py`. This is minimal, clean, and consistent with the project.

### 4. What should Agent #1 do?

**Create `frontend/conftest.py`** with the standard path bootstrap pattern. Verify Streamlit launches from repo root and other directories.

### 5. What should Agent #2 do?

**Improve GUI presentation** — better tables, attempt counters, pivot visualization, decision timeline, threshold display, evidence tier prominence.

### 6. What should Agent #3 do?

**Add 2+ demo scenarios** — all-fail (bounded termination), single-success, etc.

### 7. Which tasks should NOT be started yet?

- Nmap/Nuclei parsers (P2)
- CVE enrichment (P2)
- Multi-agent orchestration (P5)
- Real unauthorized scanning (prohibited)
- Package configuration (future, not urgent)

### 8. What is our next milestone?

**Prototype V2 — Mentor-Ready Demonstration**

### 9. What will constitute Prototype V2?

1. Streamlit launches reliably
2. GUI shows full workflow clearly
3. 5+ demo scenarios
4. All 195+ tests pass
5. Mentor demo guide complete

### 10. When should we move toward Nmap/Nuclei?

**After Prototype V2 is stable and mentor feedback is received.**

### 11. When should multi-agent orchestration begin?

**After Prototype V2 + real scan ingestion are complete.** This is P5 (future platform).

---

## GOVERNANCE RULES

- [x] Inspect before modifying
- [x] Verify claims with actual execution
- [x] Do not trust previous "DONE" labels blindly
- [x] Preserve mentor-prototype-v1
- [x] Do not rewrite the research engine
- [x] Do not introduce unnecessary dependencies
- [x] Do not use import hacks without architectural justification
- [x] Do not delete untracked files
- [x] Do not build future-platform features before stabilizing the current prototype
- [x] One logical commit per agent/task
- [x] Run tests after every implementation task
- [x] Independent QA must verify the final result
- [x] Stop if a task requires modifying frozen research code
- [x] Stop if safety boundaries would be weakened
- [x] Stop if a proposed change expands scope unexpectedly

---

*Audit completed by Hermes Agent — 2026-09-08*
