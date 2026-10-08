# Portable Development Restore Guide

**Project:** AI VAPT Framework
**Development HEAD:** `fd396bb` (branch `prototype-development`)
**Frozen Thesis Release:** `v1.0.1-thesis` -> commit
  `c33ddc23317c3bcd18cb078edaed7c33f43086f5`
**Date:** 2026-10-08  

---

## Overview

This guide explains how to restore a complete development environment for the
AI VAPT Framework on a new Linux or Windows (WSL) machine. Two methods are
provided:

| Method | Internet | Speed | Use Case |
|--------|----------|-------|----------|
| **Method 1 — GitHub Clone** | Yes | Fastest | Normal development with network access |
| **Method 2 — Offline Bundle** | No | Moderate | Air-gapped or offline environments |

Both methods produce a working tree at commit `c33ddc2`.

> **Two modes — do not confuse them:**
> - **Continued development** uses the current `prototype-development` HEAD
>   (`fd396bb`, one commit ahead of the frozen release).
> - **Exact thesis reproduction** must checkout the frozen release commit
>   `c33ddc23317c3bcd18cb078edaed7c33f43086f5` or the tag `v1.0.1-thesis`.
> - The current development tree is NOT the frozen thesis release. The tag
>   `v1.0.1-thesis` (annotated tag object `a3ad9b3`) points to commit `c33ddc2`
>   and must remain there.

> **Note:** The current repository HEAD is `fd396bb` (one commit ahead of
> `c33ddc2`). The tagged release `v1.0.1-thesis` points to `c33ddc2`. To
> match the exact release state, checkout `c33ddc2` or the tag after cloning.

---

## Pre-Requirements

### System Dependencies

| Dependency | Version | Purpose | Installation |
|------------|---------|---------|--------------|
| **Python** | 3.10.x | Runtime | `sudo apt install python3.10 python3.10-venv` (Linux) or [python.org](https://www.python.org/downloads/) (Windows) |
| **Git** | 2.x+ | Version control | `sudo apt install git` (Linux) or [git-scm.com](https://git-scm.com/) (Windows) |
| **pip** | Bundled with Python | Package manager | Included with Python 3.10+ |
| **Docker** | 24.0+ | Lab emulator | [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows) or `sudo apt install docker.io docker-compose` (Linux) |
| **Ollama** | 0.3+ | Local LLM inference | [ollama.com](https://ollama.com/) |
| **Nmap** | 7.80+ | Network scanning | `sudo apt install nmap` (Linux) or [nmap.org](https://nmap.org/download.html) (Windows) |

> **Note:** Nmap is required by the `python-nmap` Python package (listed in
> `requirements.txt`). The Python package is a wrapper around the `nmap` binary,
> which must be installed separately on the host system.

### Optional Dependencies

| Dependency | Purpose |
|------------|---------|
| **Nuclei** | Nuclei template-based scanning (used by enrichment layer) |
| **qwen2.5:3b** | Alternative LLM for experiments (default is llama3.2:3b) |

### What Is NOT Included in the Portable Package

The following are **excluded** from the portable ZIP and bundle. They are
recreated on the destination system:

- `venv/` or `.venv/` (Python virtual environment)
- Ollama model binaries (`~/.ollama/`)
- Docker images (pulled via `docker-compose up`)
- `.env` file (created from `.env.example`)
- Secrets, API keys, passwords
- `node_modules/`
- `__pycache__/`, `*.pyc`, `.pytest_cache/`
- Generated reports and runtime artifacts

---

## Method 1 — GitHub Clone (Online)

### Step 1: Clone the Repository

```bash
git clone --branch prototype-development \
  https://github.com/Vinit-Solanki16/ai_vapt_framework.git

cd ai_vapt_framework
```

### Step 2: Verify the Commit

```bash
git log --oneline -1
# Expected: fd396bb docs: add portable development restore guide

git describe --tags --always
# Expected: v1.0.1-thesis-1-gfd396bb
```

To checkout the exact release commit:

```bash
git checkout c33ddc23317c3bcd18cb078edaed7c33f43086f5
# or
git checkout v1.0.1-thesis
```

### Step 3: Create a Virtual Environment

```bash
python3.10 -m venv venv
source venv/bin/activate
```

> **Windows (WSL):** Same commands as above.  
> **Windows (Native):** Use `venv\Scripts\Activate` instead.

### Step 4: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This installs all pinned dependencies including:
- LangChain + LangGraph (agent framework)
- FastAPI + Uvicorn (API server)
- Streamlit (web dashboard)
- python-nmap (scanner integration)
- pandas, reportlab (reporting)
- pytest (testing)

### Step 5: Run Tests

```bash
python -m pytest -q
```

**Expected output:** `687 passed, 3 warnings` (verified 2026-10-08 on both the
project venv and a fresh `pip install -r requirements.txt` environment).

> **Scope note:** `python -m pytest tests/ -q` runs only the root `tests/`
> directory (`448 passed`). The primary validation command is the full
> `python -m pytest -q` suite (687 tests total: 448 in `tests/` + 37 in
> `decision_engine/tests/` + 19 in `services/tests/` + 167 in
> `prototype/tests/` + 7 in `frontend/tests/` + 9 in `experiments/`).

### Step 6: Configure Ollama (LLM Assessment)

The framework uses local Ollama for AI-powered exploit assessment. Without
Ollama, the system falls back to deterministic scoring.

```bash
# Start Ollama (if not already running)
ollama serve &

# Pull the default model
ollama pull llama3.2:3b

# Optional: Pull experimental model
ollama pull qwen2.5:3b
```

Verify Ollama is working:

```bash
ollama list
# Should show llama3.2:3b
```

### Step 7: Run the Application

Choose one of three interfaces:

#### Option A: CLI (Quick Test)

```bash
python -m prototype.cli run --scenario failure_pivot --mode simulation
```

#### Option B: Streamlit Dashboard

```bash
streamlit run frontend/app.py
```

Opens at `http://localhost:8501`

#### Option C: FastAPI Backend (Primary)

```bash
uvicorn services.api:app --reload --port 8000
```

API docs at `http://localhost:8000/docs`  
UI at `http://localhost:8000`

#### Option D: Helper Script

```bash
./scripts/start_demo.sh
```

This checks venv, deps, Ollama, and Docker, then starts the app.

### Step 8: Docker Lab (Optional)

The Docker lab provides an isolated vulnerable emulator for DOCKER_OBSERVED
evidence tier testing.

```bash
cd lab
docker-compose up -d
```

This starts:
- `vuln-emulator` — isolated vulnerable web app (internal network only)
- `vuln-executor` — HTTP API on port 9090

Verify:

```bash
docker ps
# Should show vuln-emulator and vuln-executor

curl http://localhost:9090/health
# Expected: {"status":"healthy"}
```

### Step 9: OWASP Juice Shop (Optional)

For controlled local web application testing:

```bash
docker run --rm --name juice-shop \
  -p 127.0.0.1:9191:3000 \
  bkimminich/juice-shop
```

Target URL: `http://127.0.0.1:9191`

---

## Method 2 — Offline Development Restore (No Internet)

This method uses the portable source ZIP and Git bundle to restore a complete
development environment without network access.

### Required Files

Copy these files to the new machine:

```
AI_VAPT_Framework_Portable_c33ddc2_v1.0.1.zip
AI_VAPT_Framework_GitHistory_v1.0.1.bundle
```

> The files above restore the **frozen thesis release** (`c33ddc2`).
> Continued-development snapshots use matching `_DEVELOPMENT_<HEAD>` names
> (e.g. `AI_VAPT_Framework_Portable_DEVELOPMENT_fd396bb.zip`); for those,
> `prototype-development` HEAD is the development commit, not `c33ddc2`.

### Step 1: Restore Git Repository from Bundle

```bash
git clone AI_VAPT_Framework_GitHistory_v1.0.1.bundle ai_vapt_framework
cd ai_vapt_framework
```

### Step 2: Verify the Restored Repository

```bash
git log --oneline -1
# Expected: c33ddc2 fix: make clean-clone installation reproducible

git describe --tags --always
# Expected: v1.0.1-thesis

git branch -a
# Should show: prototype-development, master, and all tags

git tag
# Should show 8 tags: checkpoint-phase-00-baseline, checkpoint-phase-01-lab,
# checkpoint-phase-05-api, mentor-prototype-v1, mentor-prototype-v2,
# reference-engine-prequalification-2026-09-01, v1.0.0-thesis, v1.0.1-thesis
```

### Step 3: Checkout Development Branch

```bash
git checkout prototype-development
```

### Step 4: Verify Commit Integrity

```bash
git rev-parse HEAD
# Expected: c33ddc23317c3bcd18cb078edaed7c33f43086f5
```

### Step 5: Create Virtual Environment

```bash
python3.10 -m venv venv
source venv/bin/activate
```

### Step 6: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **Note:** If the new machine has no internet access, you must pre-download
> the pip packages on a connected machine and transfer them:
>
> ```bash
> # On connected machine:
> pip download -r requirements.txt -d ./wheels
>
> # On offline machine:
> pip install --no-index --find-links=./wheels -r requirements.txt
> ```

### Step 7: Run Tests

```bash
python -m pytest -q
```

**Expected output:** `687 passed, 3 warnings`

> Subset only: `python -m pytest tests/ -q` gives `448 passed` (root suite).

### Step 8: Configure Ollama (If Available)

If Ollama is pre-installed on the offline machine:

```bash
ollama serve &
ollama pull llama3.2:3b
```

If Ollama is not available, the framework uses deterministic fallback scoring.

### Step 9: Run the Application

Same as Method 1, Step 7.

---

## Environment Variables

The framework uses optional environment variables. Copy `.env.example` to
`.env` and fill in values as needed:

```bash
cp .env.example .env
```

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | No | OpenAI provider for LLM assessment (falls back to Ollama) |
| `GITHUB_TOKEN` | No | GitHub API token for PoC corpus online fetch (falls back to bundled corpus) |

> **Security:** Never commit `.env` to version control. It is git-ignored.

---

## Research Core Protection

The following directories are **FROZEN** and must not be modified:

```
decision_engine/core/
decision_engine/benchmarks/
```

These contain the validated research engine that implements:
- **GAP-1:** AI-informed candidate ranking (assess -> rank -> decide)
- **GAP-2:** Bounded failure-threshold pivoting (attempt -> count -> pivot)

Modifying these directories invalidates the thesis research results.

To verify the frozen core is intact:

```bash
git diff c33ddc23317c3bcd18cb078edaed7c33f43086f5..HEAD -- decision_engine/core/ decision_engine/benchmarks/
# Expected: NO output (empty diff = untouched)
```

> `v1.0.1-thesis` is an annotated tag: `git rev-parse v1.0.1-thesis` returns
> the tag object `a3ad9b3`, while `git rev-parse 'v1.0.1-thesis^{commit}'`
> returns the frozen commit `c33ddc2`. Both are correct; the tag must not be
> moved.

---

## Project Structure

```
ai_vapt_framework/
├── core/                    # VAPT research core (FROZEN)
├── decision_engine/         # Domain-independent engine (FROZEN)
│   ├── core/                # GAP-1 + GAP-2 implementation
│   └── benchmarks/          # Benchmark results
├── vapt_platform/           # Platform services
│   ├── application.py       # VAPTApplication orchestrator
│   ├── enrichment.py        # Nuclei/template enrichment
│   ├── normalization.py     # Data normalization
│   ├── scanners.py          # Nmap scanner integration
│   ├── authorization.py     # Target allowlist enforcement
│   ├── pipeline.py          # Scan pipeline
│   ├── persistence.py       # Result storage
│   ├── events.py            # Event system
│   └── reporting.py         # Report generation
├── prototype/               # Prototype layer
│   ├── cli.py               # CLI interface
│   ├── execution_layer.py   # Execution abstraction
│   ├── lab_runner.py        # Docker lab runner
│   └── demo_data/           # Demo scenarios
├── frontend/                # Web UI
│   ├── app.py               # Streamlit dashboard (legacy)
│   └── web/                 # Dedicated HTML/CSS/JS SPA (primary)
├── services/                # FastAPI backend
│   └── api.py               # REST API
├── lab/                     # Docker lab
│   ├── docker-compose.yml   # Lab orchestration
│   ├── emulator/            # Vulnerable web app
│   └── executor.Dockerfile  # Executor container
├── tests/                   # Root test suite (448 tests; full repo suite = 687 tests)
├── data/                    # Datasets and PoC corpus
├── docs/                    # Documentation
├── experiments/             # Research experiments
└── scripts/                 # Helper scripts
    ├── start_demo.sh        # Startup helper
    └── reset_demo.sh        # Demo state reset
```

---

## Evidence Tiers

The framework supports four evidence tiers:

| Tier | Description | Requirements |
|------|-------------|--------------|
| **SIMULATED** | Outcomes from ground-truth labels | None |
| **OBSERVED_LOCAL** | Real HTTP to loopback (127.0.0.1) | None |
| **DOCKER_OBSERVED** | Real HTTP to isolated Docker emulator | Docker |
| **CONTROLLED_VALIDATION** | Real execution against live targets | Docker + authorization |

---

## Troubleshooting

### `python-nmap` installation fails

Ensure the `nmap` binary is installed on the system:

```bash
# Linux
sudo apt install nmap

# Windows
# Download from https://nmap.org/download.html
```

### `streamlit` command not found

Ensure the virtual environment is activated:

```bash
source venv/bin/activate
```

### Docker lab fails to start

Ensure Docker is running:

```bash
sudo systemctl start docker  # Linux
# or start Docker Desktop on Windows
```

### Ollama connection refused

Ensure Ollama is running:

```bash
ollama serve &
```

### Tests fail with import errors

Ensure all dependencies are installed:

```bash
pip install -r requirements.txt
```

### ModuleNotFoundError

Run from repo root with PYTHONPATH set:

```bash
export PYTHONPATH=$(pwd)
```

---

## Quick Reference

```bash
# Clone and setup
git clone --branch prototype-development https://github.com/Vinit-Solanki16/ai_vapt_framework.git
cd ai_vapt_framework
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Test
python -m pytest -q
# Expected: 687 passed, 3 warnings
# Subset (root only): python -m pytest tests/ -q  # 448 passed

# Run CLI
python -m prototype.cli run --scenario failure_pivot --mode simulation

# Run Web Dashboard (Streamlit)
streamlit run frontend/app.py

# Run API (FastAPI + UI)
uvicorn services.api:app --reload --port 8000

# Run Helper Script
./scripts/start_demo.sh

# Docker Lab
cd lab && docker-compose up -d && cd ..

# OWASP Juice Shop
docker run --rm --name juice-shop -p 127.0.0.1:9191:3000 bkimminich/juice-shop
```

---

## Summary

| Item | Value |
|------|-------|
| Python Version | 3.10.x |
| Git Required | Yes |
| Docker Required | Optional (for DOCKER_OBSERVED tier) |
| Ollama Required | Optional (for AI assessment; deterministic fallback available) |
| Nmap Required | Yes (for scanning features) |
| Nuclei | Optional (for enrichment) |
| Test Command | `python -m pytest -q` |
| Expected Tests | 687 passed, 3 warnings (root-only `tests/` subset: 448 passed) |
| Default LLM | llama3.2:3b |
| Experimental LLM | qwen2.5:3b |
| Research Core | `decision_engine/core/` and `decision_engine/benchmarks/` (FROZEN) |
| Frozen Thesis Tag | v1.0.1-thesis -> c33ddc23317c3bcd18cb078edaed7c33f43086f5 |
| Development HEAD | fd396bb (`prototype-development`) |

---

*Generated: 2026-10-08*  
*Development HEAD: fd396bb712f8289d5759eac702e5969302aa905a*  
*Frozen thesis release: v1.0.1-thesis -> c33ddc23317c3bcd18cb078edaed7c33f43086f5*
