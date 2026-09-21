# Demo Checklist

**Date:** 2026-09-21
**Branch:** `prototype-development`
**Status:** READY

---

## Pre-Demo Checklist

### Environment

- [ ] Python 3.10 venv activated (`source venv/bin/activate`)
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Application starts (`uvicorn services.api:app --reload --port 8000`)
- [ ] http://localhost:8000 loads in browser

### Optional Services

- [ ] Ollama running (`ollama serve &`) — for AI assessment demo
- [ ] Docker Desktop running — for Docker lab demo
- [ ] Docker lab containers up (`cd lab && docker-compose up -d`)

### Browser Validation

- [ ] Dashboard loads with metric cards
- [ ] Sidebar navigation works (12 items)
- [ ] New Assessment form renders
- [ ] Run History shows persisted runs
- [ ] Reports page shows download buttons
- [ ] System Health shows component statuses
- [ ] No JavaScript errors in console

---

## Demo Workflow Checklist

### A. Simulation Demo

- [ ] Navigate to New Assessment
- [ ] Select Mode: Simulation
- [ ] Select Scenario: failure_pivot
- [ ] Select Assessor: deterministic
- [ ] Set Pivot Threshold: 2
- [ ] Verify safety status shows "SIMULATION"
- [ ] Click "Run Assessment"
- [ ] Verify pipeline stepper renders
- [ ] Verify candidates table populates
- [ ] Verify decision trace shows events
- [ ] Verify evidence tier shows "SIMULATED"
- [ ] Verify report generates

### B. AI Assessment Demo

- [ ] Ensure Ollama is running
- [ ] Navigate to New Assessment
- [ ] Select Assessor: ai
- [ ] Select Provider: ollama
- [ ] Click "Run Assessment"
- [ ] Verify assessment panel shows "ai" mode
- [ ] Verify provider shows "ollama"
- [ ] Verify quality ranks are displayed

### C. Docker Lab Demo

- [ ] Ensure Docker Desktop is running
- [ ] Ensure lab containers are up
- [ ] Navigate to New Assessment
- [ ] Select Mode: Docker Lab
- [ ] Select Target: 172.28.0.2
- [ ] Select Scenario: docker_pivot
- [ ] Verify safety status shows "AUTHORIZED / ALLOWLISTED"
- [ ] Click "Run Assessment"
- [ ] Verify evidence tier shows "DOCKER_OBSERVED"

### D. Run History Demo

- [ ] Navigate to Run History
- [ ] Verify runs are listed
- [ ] Click a run to view details
- [ ] Verify events timeline renders
- [ ] Verify candidates are displayed

### E. Reports Demo

- [ ] Navigate to Reports
- [ ] Select a run
- [ ] Download JSON report
- [ ] Download HTML report
- [ ] Download Markdown report
- [ ] Download TXT report
- [ ] Verify files contain correct run data

### F. Safety Demo

- [ ] Attempt unauthorized target via API
- [ ] Verify rejection (HTTP 400)
- [ ] Verify UI has no free-text target input
- [ ] Verify only allowlisted targets selectable

---

## Post-Demo Checklist

- [ ] All workflows completed successfully
- [ ] No JavaScript errors observed
- [ ] No broken UI states
- [ ] Research contributions clearly explained:
  - GAP-1: AI assessment before ranking
  - GAP-2: Bounded attempts and pivot
- [ ] Evidence provenance clearly displayed
- [ ] Safety/authorization status visible

---

## Quick Commands

```bash
# Start application
source venv/bin/activate
uvicorn services.api:app --reload --port 8000

# Start Ollama (optional)
ollama serve &

# Start Docker lab (optional)
cd lab && docker-compose up -d && cd ..

# Reset demo state
./scripts/reset_demo.sh

# Run tests
python -m pytest -q
```

---

_Use this checklist before every mentor demonstration._
