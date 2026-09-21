# Known Limitations

**Date:** 2026-09-21
**Branch:** `prototype-development`

---

## 1. Docker Lab Runtime Not Verified

**Status:** ⚠️ CODE COMPLETE, RUNTIME NOT VERIFIED

The Docker laboratory code is complete and tested (13 tests pass), but runtime
verification requires Docker Desktop, which is not available in this WSL
environment.

**What works:**
- Docker Compose configuration (`lab/docker-compose.yml`)
- Vulnerability emulator (`lab/emulator/app.py`)
- Executor HTTP API (`lab/executor_server.py`)
- Allowlist enforcement (`prototype/lab_runner.py`)
- Executor abstraction (`prototype/execution_layer.py`)

**What's not verified:**
- Actual container startup and network isolation
- Real HTTP execution against the emulator
- End-to-end Docker pivot scenario

**To verify:**
```bash
cd lab
docker-compose up -d
python -m prototype.cli run --scenario docker_pivot --mode lab --target 172.28.0.2
```

---

## 2. Ollama Live Assessment Not Integration-Tested

**Status:** ⚠️ INSTALLED, NOT INTEGRATION-TESTED

Ollama is installed with `llama3.2:3b` model available. The LLM assessor
code path is tested with mocked LLM boundaries, but live Ollama assessment
has not been integration-tested in this environment.

**What works:**
- Ollama installation and model availability
- LLM assessor code (`core/exploit_assessor.py`)
- Deterministic fallback (`decision_engine/core/assessor.py`)
- Assessment provenance tracking (`vapt_platform/assessment.py`)

**What's not verified:**
- Live Ollama response parsing
- Structured output validation
- Fallback behavior when Ollama is unavailable

**To verify:**
```bash
ollama serve &
python -m prototype.cli run --scenario failure_pivot --assessor llm
```

---

## 3. OpenAI Provider Not Tested

**Status:** ⚠️ CODE COMPLETE, NOT TESTED

The OpenAI provider path is implemented but requires an API key for testing.
No cloud dependencies are used by default.

---

## 4. GitHub PoC Fetch Not Tested

**Status:** ⚠️ CODE COMPLETE, NOT TESTED

The GitHub PoC fetch requires a `GITHUB_TOKEN` environment variable. The
local corpus is used by default.

---

## 5. PDF Reports Not Implemented

**Status:** ⚠️ NOT IMPLEMENTED

Reports are available in JSON, TXT, HTML, and Markdown formats. PDF support
is not implemented (reportlab is in dependencies but not used for VAPT reports).

---

## 6. Real Exploitation Not Performed

**Status:** ⚠️ NOT PERFORMED

The framework does not perform real exploitation against external targets.
All execution is either:
- Simulation (ground-truth labels)
- Loopback (127.0.0.1)
- Docker lab (isolated emulator)

This is by design for safety and reproducibility.

---

## 7. Streamlit Interactive UI Not Tested

**Status:** ⚠️ CODE COMPLETE, NOT INTERACTIVELY TESTED

The Streamlit dashboard imports cleanly and has smoke tests, but interactive
UI testing (clicking buttons, navigating pages) has not been performed.

**To test:**
```bash
streamlit run frontend/app.py
```

---

## 8. API Not Integration-Tested

**Status:** ⚠️ UNIT TESTS PASS, INTEGRATION NOT TESTED

The FastAPI backend has 10 unit tests that pass, but end-to-end API testing
with a running server has not been performed.

**To test:**
```bash
uvicorn services.api:app --reload --port 8000
curl http://localhost:8000/health
```

---

## 9. Performance Under Load Not Tested

**Status:** ⚠️ NOT TESTED

The framework has not been tested under high load or with large numbers of
candidates. Performance characteristics are unknown.

---

## 10. Cross-Platform Compatibility Not Verified

**Status:** ⚠️ NOT VERIFIED

The framework is developed on WSL (Windows Subsystem for Linux). Compatibility
with native Linux, macOS, and Windows has not been verified.

---

## Summary

| Limitation | Severity | Workaround |
|------------|----------|------------|
| Docker runtime not verified | Medium | Use Simulation mode |
| Ollama live not tested | Low | Use deterministic fallback |
| OpenAI not tested | Low | Use Ollama or deterministic |
| GitHub fetch not tested | Low | Use local corpus |
| PDF reports not implemented | Low | Use HTML reports |
| Real exploitation not performed | By design | N/A |
| Streamlit UI not interactively tested | Low | Run and verify manually |
| API not integration-tested | Low | Run and verify manually |
| Performance not tested | Low | N/A |
| Cross-platform not verified | Low | N/A |

---

_These limitations are honestly documented. No claims are made beyond what is verified._
