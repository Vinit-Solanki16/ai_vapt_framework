# Demo Reset Guide

**Date:** 2026-09-21
**Branch:** `prototype-development`

---

## Overview

This guide explains how to return the AI-VAPT Operations Console to a clean demonstration state by clearing persisted runs and old report files.

---

## When to Reset

Reset the demo state when:

- You want a clean dashboard for a new demonstration
- Too many test runs have accumulated
- You want to show the "empty state" UI
- You're preparing for a mentor demonstration

---

## Reset Method

### Quick Reset

```bash
./scripts/reset_demo.sh
```

This script:
1. Clears all persisted runs from `~/.ai_vapt_framework/runs/`
2. Removes old report files from the project root
3. Does NOT modify code, configuration, or research core

### Manual Reset

If you prefer to reset manually:

```bash
# Activate environment
source venv/bin/activate

# Clear persisted runs
rm -f ~/.ai_vapt_framework/runs/*.json
rm -f ~/.ai_vapt_framework/runs/index.json

# Remove old report files
rm -f report_*.json report_*.txt report_*.html report_*.md
```

---

## What Gets Cleared

| Item | Location | Effect |
|------|----------|--------|
| Persisted runs | `~/.ai_vapt_framework/runs/` | Dashboard shows empty state |
| Run index | `~/.ai_vapt_framework/runs/index.json` | Run history empty |
| Old reports | `project_root/report_*` | Clean project directory |

---

## What Does NOT Get Cleared

| Item | Reason |
|------|--------|
| Research core | Frozen, should not be modified |
| Configuration | Safety settings remain intact |
| Code | No code changes |
| Docker containers | May still be running |
| Ollama models | May still be loaded |
| Demo scenarios | Built into the application |

---

## After Reset

1. **Start the application:**
   ```bash
   source venv/bin/activate
   uvicorn services.api:app --reload --port 8000
   ```

2. **Verify clean state:**
   - Open http://localhost:8000
   - Dashboard should show 0 runs
   - Run History should be empty
   - System Health should still show all components

3. **Run a new demo:**
   - Follow the mentor demo sequence
   - Create new assessments
   - Generate new reports

---

## Demo Scenarios Available

After reset, these scenarios are available:

| Scenario | Mode | Description |
|----------|------|-------------|
| success | simulation | Immediate success |
| failure_pivot | simulation | Failure then pivot |
| multi_candidate | simulation | Multiple candidates |
| single_success | simulation | Single candidate |
| all_fail | simulation | All candidates fail |
| threshold_one | simulation | Threshold = 1 |
| docker_vuln | lab | Docker success |
| docker_fail | lab | Docker failure |
| docker_pivot | lab | Docker pivot |
| docker_multi | lab | Docker multi-candidate |

---

## Reset Verification

After running the reset script, verify:

```bash
# Check runs directory is empty
ls ~/.ai_vapt_framework/runs/

# Check no old reports
ls report_* 2>/dev/null || echo "No old reports"

# Start application and verify
uvicorn services.api:app --reload --port 8000
# Open http://localhost:8000 — dashboard should show 0 runs
```

---

## Notes

- The reset script is safe to run multiple times
- It does NOT delete the database or any system files
- It only removes JSON run files and report files
- Docker containers and Ollama are not affected
- The application code is not modified

---

_Use this guide to maintain a clean demonstration environment._
