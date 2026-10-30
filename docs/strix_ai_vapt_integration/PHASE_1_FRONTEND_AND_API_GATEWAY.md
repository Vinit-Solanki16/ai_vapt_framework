# Phase 1: Frontend Web Operations Console & FastAPI Gateway Integration

## 1. Objective

Integrate the **AI-VAPT Single Page Application (SPA)** and a dedicated **FastAPI Gateway** directly into **STRIX** (`/home/vinit/STRIX/strix`).  
This transforms Strix from a terminal-only / read-only viewer tool into an interactive, real-time web operations platform capable of configuring targets, selecting models, monitoring live assessments, and inspecting findings.

> **CRITICAL RULE:** All modifications and new files are created **strictly inside `/home/vinit/STRIX/strix`**. The code in `/home/vinit/AI_VAPT/frontend/web` is only copied and adapted.

---

## 2. Target File Structure in STRIX

```
/home/vinit/STRIX/strix/
├── strix/
│   ├── interface/
│   │   ├── api.py                    # NEW: FastAPI backend service for Strix Web Console
│   │   ├── schemas.py                # NEW: Pydantic schemas for API requests/responses
│   │   ├── web/                      # NEW: Unified Frontend assets
│   │   │   ├── index.html            # Ported from AI_VAPT/frontend/web/index.html
│   │   │   ├── css/
│   │   │   │   └── styles.css        # Ported from AI_VAPT/frontend/web/css/styles.css
│   │   │   └── js/
│   │   │       └── app.js            # Ported & adapted from AI_VAPT/frontend/web/js/app.js
│   │   ├── cli.py                    # UPDATED: Add 'strix web' subcommand
│   │   └── cli_args.py               # UPDATED: Add '--web' flag and 'web' subparser
```

---

## 3. Detailed Technical Implementation Steps

### Step 1.1: Add FastAPI & Dependencies to Strix
Strix's environment already has `uvicorn`. Ensure `fastapi` is added to `pyproject.toml` dependencies:
```toml
# Inside /home/vinit/STRIX/strix/pyproject.toml:
dependencies = [
  ...
  "fastapi>=0.115.0",
  "uvicorn>=0.30.0",
]
```

### Step 1.2: Port Frontend Static Files
1. Create directory: `/home/vinit/STRIX/strix/strix/interface/web/`.
2. Copy `index.html`, `css/styles.css`, and `js/app.js` from `/home/vinit/AI_VAPT/frontend/web/` to `/home/vinit/STRIX/strix/strix/interface/web/`.
3. In `strix/interface/web/index.html`:
   - Update branding title to: `<title>STRIX AI-VAPT Autonomous Operations Console</title>`.
   - Ensure cache-busting query parameter is present: `<script src="/js/app.js?v=strix20261028"></script>`.
4. In `strix/interface/web/js/app.js`:
   - Point API requests to the local server origin (`window.location.origin`).
   - Retain full SPA navigation routes: `#/dashboard`, `#/assessment/new`, `#/assessment/active`, `#/runs`, `#/scenarios`, `#/engagements`, `#/system/health`, `#/pivot-analysis`.

### Step 1.3: Create FastAPI Gateway (`strix/interface/api.py`)
Implement the FastAPI server mounting the web UI and serving core endpoints:
- `GET /`: Serves `strix/interface/web/index.html`.
- Mount `/css` and `/js` static file directories from `strix/interface/web/`.
- `GET /health` & `GET /system/health`: Reports system readiness (Application, LiteLLM, Ollama, Docker, Scanners).
- `GET /scenarios`: Returns available benchmark scenarios (`docker_pivot`, `failure_pivot`, etc.).
- `POST /runs`: Accepts new assessment jobs and dispatches to background worker.
- `GET /runs`: Lists recent runs with pagination.
- `GET /runs/{run_id}`: Returns run status, event logs, candidate quality scores, and decision traces.
- `GET /runs/{run_id}/report`: Returns rendered HTML or JSON reports.
- `POST /targets/validate`: Performs fail-closed target resolution and scope checking.

### Step 1.4: Add CLI Entry Point (`strix web`)
Update `strix/interface/cli.py` and `strix/interface/main.py`:
Add a command to start the web console:
```bash
strix web --host 127.0.0.1 --port 8000
```
This starts Uvicorn with `strix.interface.api:app`.

---

## 4. Agent Development Prompt for Phase 1

Copy and paste this prompt to an autonomous agent or execution session:

```markdown
# TASK: Phase 1 — Implement Unified Web Frontend & FastAPI Gateway in STRIX

## Strict Boundaries
- Work EXCLUSIVELY inside `/home/vinit/STRIX/strix`.
- DO NOT edit any files in `/home/vinit/AI_VAPT`. Read files from `/home/vinit/AI_VAPT` as read-only reference.

## Objective
Implement the interactive Web Operations Console inside STRIX so that running `strix web --host 127.0.0.1 --port 8000` launches a complete FastAPI server serving the interactive web SPA.

## Detailed Tasks
1. Verify `fastapi` is installed in Strix's virtual environment:
   Run `cd /home/vinit/STRIX/strix && uv pip install fastapi`.
2. Create directory `/home/vinit/STRIX/strix/strix/interface/web/`.
3. Copy the frontend assets from `/home/vinit/AI_VAPT/frontend/web/` (`index.html`, `css/`, `js/`) into `/home/vinit/STRIX/strix/strix/interface/web/`.
4. Create `/home/vinit/STRIX/strix/strix/interface/schemas.py` defining Pydantic models:
   `RunRequest`, `RunResponse`, `SystemHealthResponse`, `TargetValidationRequest`, `TargetValidationResponse`.
5. Create `/home/vinit/STRIX/strix/strix/interface/api.py`:
   - Initialize `app = FastAPI(title="STRIX AI-VAPT Console")`.
   - Mount static files for `/css` and `/js`.
   - Add routes:
     - `GET /`: Return `index.html`.
     - `GET /health`: Return `{"status": "ok"}`.
     - `GET /system/health`: Return JSON health checks for Strix core, Docker, Ollama, and LiteLLM.
     - `GET /scenarios`: Return supported test scenarios.
     - `POST /targets/validate`: Stub target validation returning authorized=True for local loopback.
     - `POST /runs` and `GET /runs/{run_id}`: Basic in-memory job tracking.
6. Update Strix CLI in `strix/interface/cli.py` or `strix/interface/cli_args.py` so that `strix web` or `python -m strix.interface.api` starts the server.
7. Run verification tests to confirm the server starts and serves HTML on port 8000.
```

---

## 5. Verification & Testing Commands

To verify that Phase 1 is functioning correctly:

```bash
# 1. Start the Strix Web Gateway
cd /home/vinit/STRIX/strix
uv run uvicorn strix.interface.api:app --host 127.0.0.1 --port 8000

# 2. Test Backend Health (in another terminal)
curl -s http://127.0.0.1:8000/health
# Expected: {"status":"ok"}

# 3. Test System Health Endpoint
curl -s http://127.0.0.1:8000/system/health
# Expected: JSON object with application, docker, ollama, and scanner status

# 4. Test Frontend Static Asset Delivery
curl -s -I http://127.0.0.1:8000/
# Expected: HTTP/1.1 200 OK (Content-Type: text/html)

curl -s -I http://127.0.0.1:8000/js/app.js
# Expected: HTTP/1.1 200 OK (Content-Type: application/javascript)

# 5. Open in Web Browser
# Navigate to: http://127.0.0.1:8000/
# Verify dashboard cards, navigation menu, and New Assessment view render cleanly.
```

