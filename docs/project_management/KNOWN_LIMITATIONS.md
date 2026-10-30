# Known Limitations

**Date:** 2026-09-21
**Branch:** `prototype-development`

---

## 1. Docker Lab Runtime — VERIFIED

**Status:** ✅ LIVE VERIFIED (2026-09-21, final pre-demo audit)

The Docker laboratory is verified working end-to-end:

**Verified:**
- Docker Compose stack (`lab/docker-compose.yml`): emulator + executor containers running healthy
- Vulnerability emulator (`lab/emulator/app.py`) responding on the lab network
- Executor HTTP API (`lab/executor_server.py`) healthy at localhost:9090
- Allowlist enforcement (`prototype/lab_runner.py`): non-allowlisted targets refused fail-closed
- End-to-end Docker pivot scenario (`docker_pivot`): real HTTP observed in emulator logs
- DOCKER_OBSERVED evidence tier produced correctly with genuine emulator responses

**Remaining scope:**
- Runs on this machine's Docker Desktop only; not re-verified on other hosts

---

## 2. Ollama Live Assessment — VERIFIED

**Status:** ✅ LIVE VERIFIED (2026-09-21, final pre-demo audit)

**Verified:**
- Ollama serving `llama3.2:3b` (Q4_K_M, offline)
- AI assessment path works end-to-end via the API (`assessor=llm`)
- Quality ranks generated for candidates with provenance `mode=ai, provider=ollama`
- Assessment latency ~2–10s per run (2 candidates)
- Deterministic fallback verified when Ollama is not required

**Remaining scope:**
- Consistency across repeated runs varies (documented in `experiments/results/llm_behavior.json`: 6/8 candidates 100% consistent)

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

## 8. API Integration — VERIFIED

**Status:** ✅ LIVE VERIFIED (2026-09-21, final pre-demo audit)

All 16 FastAPI endpoints were exercised against a running server
(uvicorn on :8000): run creation (simulation/AI/Docker lab), status,
trace, events, evidence, findings, candidates, reports (all 4 formats),
persistence, CVE lookup, and system health. Frontend endpoint usage
was cross-checked against the API surface with zero mismatches.

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
| Docker runtime verified on this host only | Low | Re-verify on other hosts if needed |
| Ollama consistency varies across runs | Low | Deterministic mode for reproducibility |
| OpenAI not tested | Low | Use Ollama or deterministic |
| GitHub fetch not tested | Low | Use local corpus |
| PDF reports not implemented | Low | Use HTML reports |
| Real exploitation not performed | By design | N/A |
| Streamlit UI not interactively tested | Low | Dedicated web UI is the demo surface |
| API integration verified via live smoke tests | — | N/A |
| Performance not tested | Low | N/A |
| Cross-platform not verified | Low | N/A |
| No real-time UI updates | Low | Refresh page after runs |

---

_These limitations are honestly documented. No claims are made beyond what is verified._
