# EXTERNAL REPOSITORY STUDY + MASTER IMPLEMENTATION PLAN

**Date:** 2026-09-03
**Project:** /home/vinit/ai_vapt_framework
**Status:** READ-ONLY ANALYSIS — NO MODIFICATIONS MADE

---

# EXTERNAL REPOSITORY STUDY

## Repository 1 — vikramrajkumarmajji/AI-VAPT

**URL:** https://github.com/vikramrajkumarmajji/AI-VAPT
**Branch:** main
**License:** None specified
**Stack:** React + TypeScript + Vite + Tailwind CSS + shadcn/ui
**Commit:** (cloned via --depth 1)

### Directory Structure
```
AI-VAPT/
├── src/
│   ├── App.tsx                    # Main app shell
│   ├── main.tsx                   # React entry
│   ├── components/
│   │   ├── home.tsx               # Landing page
│   │   ├── dashboard/
│   │   │   ├── VulnerabilityDashboard.tsx    # Main dashboard view
│   │   │   ├── VulnerabilityDetail.tsx       # Detail panel
│   │   │   └── TargetSpecificationPanel.tsx  # Target input
│   │   └── ui/                    # 40+ shadcn/ui components
│   ├── stories/                   # Storybook stories
│   └── types/                     # TypeScript types
├── Dashboard.png                  # Screenshot of UI
├── Flowchart.png                  # Architecture diagram
├── package.json                   # Node dependencies
└── README.md                      # Extensive claims

### README Claims vs Actual Code

| README Claim | Actual Code | Classification |
|--------------|-------------|----------------|
| AI-Augmented Recon | No code | DOCUMENTATION-ONLY |
| Multi-Vector Scanning (Amass, Nmap, Nikto, etc.) | No code | DOCUMENTATION-ONLY |
| ML Exploit Prediction | No code | DOCUMENTATION-ONLY |
| Smart Reporting | No code | DOCUMENTATION-ONLY |
| Dashboard UI | React components | REAL (frontend only) |
| 5-layer architecture | Flowchart.png | CONCEPTUAL |

### What Actually Exists

1. **TargetSpecificationPanel.tsx** — UI for entering target IP/hostname, selecting scan type
2. **VulnerabilityDashboard.tsx** — Displays vulnerability cards with severity, CVE, status
3. **VulnerabilityDetail.tsx** — Detail view for individual findings
4. **40+ UI components** — shadcn/ui component library (cards, tables, forms, etc.)
5. **TypeScript types** — Interfaces for vulnerabilities, targets, scan results

### What Does NOT Exist

- No Python backend
- No Nmap/scanner integration
- No LLM/AI code
- No exploit execution
- No decision engine
- No reporting engine
- No API server

### Value to Our Project

**UI Inspiration Only.** The dashboard layout (target input → vulnerability cards → detail panel) could inspire our Streamlit GUI. The component design is professional but the stack (React/TypeScript) is incompatible with our Python/Streamlit approach.

---

## Repository 2 — cywarriors/vapt-agents

**URL:** https://github.com/cywarriors/vapt-agents
**Branch:** main
**License:** MIT
**Stack:** Python + CrewAI + subprocess (Nmap) + SQLite
**Commit:** (cloned via --depth 1)

### Directory Structure
```
vapt-agents/
├── agents.py              # 3 CrewAI agents (Recon, Scanner, Reporter)
├── tasks.py               # Task definitions
├── tools.py               # Nmap, Nessus, OpenVAS, Nmap NSE tools
├── crew.py                # CrewAI orchestration + main entry
├── validation.py          # Target validation, error handling
├── output_manager.py      # Multi-format output (JSON/HTML/CSV/XML/TXT/YAML)
├── output_cli.py          # CLI for managing results
├── output_demo.py         # Demo of output features
├── config.py              # Centralized configuration
├── example_usage.py       # Programmatic usage examples
├── requirement.txt        # Python dependencies
├── vapt_config.json       # Configuration file
└── LICENSE                # MIT

### Capability Classification

| Capability | File | Classification | Evidence |
|-----------|------|----------------|----------|
| Nmap integration | tools.py:215 | REAL | subprocess.run(["nmap", ...]) |
| Target validation | validation.py:36-54 | REAL | Regex + ipaddress module |
| Timeout handling | tools.py:101-123 | REAL | signal.alarm + SIGALRM |
| Retry logic | tools.py:207 | REAL | 3 retries with backoff |
| Multi-agent orchestration | crew.py:28-40 | REAL | CrewAI Crew with 3 agents |
| Multi-format output | output_manager.py:25-33 | REAL | JSON/XML/CSV/YAML/HTML/TXT |
| SQLite storage | output_manager.py | REAL | sqlite3 database |
| Interactive CLI | crew.py:303-375 | REAL | input() prompts |
| Nessus integration | tools.py:451 | STUB | raise NotImplementedError |
| OpenVAS integration | tools.py | STUB | raise NotImplementedError |

### Architecture

```
crew.py (main)
    ├── agents.py
    │   ├── vuln_scan_agent (Reconnaissance Specialist) → NmapReconTool
    │   ├── vuln_comprehensive_scanner_agent → NessusScanTool, OpenVASScanTool, NmapNSETool
    │   └── report_generator_agent → ReportWriterTool
    ├── tasks.py
    │   ├── reconnaissance_task
    │   ├── comprehensive_vuln_scan_task
    │   └── report_generation_task
    ├── tools.py
    │   ├── NmapReconTool (REAL)
    │   ├── NessusScanTool (STUB)
    │   ├── OpenVASScanTool (STUB)
    │   ├── NmapNSETool
    │   └── ReportWriterTool
    ├── validation.py (TargetValidator)
    ├── output_manager.py (ScanResult, Vulnerability, SeverityLevel)
    └── config.py (VAPTConfig)

```

### Key Implementation Details

1. **NmapReconTool** (tools.py:125-428):
   - Builds nmap command: `["nmap", "-T", "3", "-A", "-sV", "-sC", "-p", ports, target]`
   - Executes via `subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)`
   - Retries up to 3 times with `_is_retryable_error()` check
   - Parses vulnerabilities from stdout using keyword matching
   - Returns `ToolScanResult` with vulnerabilities list

2. **TargetValidator** (validation.py:36-54):
   - Blocks: `.gov`, `.mil`, `.edu`, `*bank*`, `*hospital*`
   - Validates IP format using `ipaddress` module
   - Validates hostname format using regex
   - Checks private IP ranges (RFC 1918)

3. **Output Formats** (output_manager.py:25-33):
   - JSON, XML, CSV, YAML, HTML, TXT, PICKLE
   - SQLite storage via `result_storage`
   - `ScanResult` dataclass with `ScanMetadata` and `List[Vulnerability]`

### What's Missing vs Our Project

| Capability | vapt-agents | Our Project |
|-----------|-------------|-------------|
| Decision engine | MISSING | LangGraph pivot engine |
| Attempt tracking | MISSING | Engine-native |
| Failure threshold | MISSING | Engine-native |
| Pivot logic | MISSING | Engine-native |
| Checkpoint/resume | MISSING | Engine-native |
| Safety allowlist (IP-based) | Basic | 5 layers |
| Lab isolation | MISSING | Docker internal network |
| Testing | None visible | 192 tests |
| Research methodology | None | Fair 4-agent ablation |

---

# COMPARISON MATRIX

| Capability | Our Project | AI-VAPT | vapt-agents | Best Approach |
|------------|-------------|---------|-------------|---------------|
| Target intake | CLI/API/scan file | UI only | Interactive prompt | Ours |
| Reconnaissance | Scan file parser | None | Live Nmap subprocess | Ours (safer) |
| Scan ingestion | Nmap XML/JSON/custom | None | Live Nmap | Ours (offline parser) |
| Finding normalization | scan_adapter.py | None | tools.py parser | Comparable |
| Candidate generation | From scan/corpus | None | From Nmap output | Comparable |
| Assessment | Deterministic + LLM | None | LLM only | Ours (more robust) |
| Prioritization | priority_score | None | Severity-based | Ours (EPSS × quality) |
| Decision engine | **LangGraph pivot** | None | None | **Ours (unique)** |
| Attempt tracking | Engine-native | None | None | **Ours** |
| Failure threshold | Engine-native | None | None | **Ours** |
| Pivot logic | Engine-native | None | None | **Ours** |
| Execution | Simulation/Lab | None | Live subprocess | Ours (bounded) |
| Checkpoint/resume | **Yes** | None | None | **Ours** |
| Safety allowlist | 5 layers | None | Domain-based | Ours |
| Lab isolation | Docker internal | None | None | Ours |
| Reporting | JSON + TXT + evidence | None | JSON/HTML/CSV/XML/YAML/TXT | vapt-agents (more formats) |
| FastAPI | **Yes** | None | None | **Ours** |
| GUI | Streamlit | React (no backend) | None | Ours |
| Agent orchestration | None | None | CrewAI | Neither (not needed) |
| Testing | 192 tests | None | None | **Ours** |
| Research methodology | Fair benchmark | None | None | **Ours** |

---

# ADOPT / ADAPT / INSPIRE / REJECT

| Feature | Source | Decision | Rationale |
|---------|--------|----------|-----------|
| Multi-format output (HTML, CSV, XML, YAML) | vapt-agents/output_manager.py | **ADAPT** | Add formats to our report generator |
| Target validation (domain blocks) | vapt-agents/validation.py | **ADAPT** | Strengthen our allowlist |
| Timeout with signal.alarm | vapt-agents/tools.py:101 | **INSPIRE** | Our engine has bounded retry, different pattern |
| Retry with exponential backoff | vapt-agents/tools.py:207 | **INSPIRE** | Our pivot mechanism supersedes this |
| SQLite result storage | vapt-agents/output_manager.py | **REJECT** | Our JSON/TXT reports are sufficient |
| Nmap subprocess execution | vapt-agents/tools.py | **REJECT** | Safety risk; our offline parser is safer |
| CrewAI multi-agent orchestration | vapt-agents/agents.py | **REJECT** | Would replace our LangGraph engine |
| Dashboard UI layout | AI-VAPT/src/components/dashboard | **INSPIRE** | Visual pattern for Streamlit |
| Target input panel | AI-VAPT/src/components/dashboard/TargetSpecificationPanel.tsx | **INSPIRE** | UI pattern for Streamlit |
| Severity-based cards | AI-VAPT/src/components/dashboard/VulnerabilityDashboard.tsx | **INSPIRE** | UI pattern for reporting |

---

# DOCKER LAB ARCHITECTURE ANALYSIS

## Current Problem

```
Host (framework)  ──X──→  vuln-lab-network (internal:true)  ──→  vuln-emulator (172.28.0.2)
         │                                                            │
         │         CANNOT REACH (no published ports)                   │
         └────────────────────────────────────────────────────────────┘
```

The host is outside the Docker bridge network. `internal: true` prevents any external access. No ports are published. Therefore `prototype/lab_runner.py` running on the host gets connection refused for all requests to `172.28.0.2:8080`.

## Architecture Options

### Option A: Publish Emulator Port to Host

```yaml
services:
  emulator:
    ports:
      - "8080:8080"
```

| Criterion | Assessment |
|-----------|------------|
| Security impact | **HIGH** — emulator reachable from host and potentially LAN |
| Implementation complexity | LOW — one line change |
| Reproducibility | HIGH |
| Effect on evidence quality | MEDIUM — still observed, but isolation weakened |
| Compatibility with current prototype | FULL — no code changes needed |
| Compatibility with GUI/API | FULL |
| Compatibility with research evaluation | FULL |
| **Verdict** | **REJECT** — weakens isolation unnecessarily |

### Option B: Framework Container Attached to vuln-lab-network

```yaml
services:
  emulator:
    # ... existing
  framework:
    build: ..
    networks:
      - vuln-lab-network
    volumes:
      - .:/app
```

| Criterion | Assessment |
|-----------|------------|
| Security impact | **LOW** — emulator still isolated |
| Implementation complexity | MEDIUM — new Dockerfile, compose changes |
| Reproducibility | HIGH |
| Effect on evidence quality | HIGH — genuine observed execution |
| Compatibility with current prototype | MEDIUM — need to run framework in container |
| Compatibility with GUI/API | MEDIUM — need to expose API/GUI ports |
| Compatibility with research evaluation | FULL |
| **Verdict** | **CANDIDATE** — but heavy for a demo |

### Option C: Dedicated Executor Container on vuln-lab-network

```yaml
services:
  emulator:
    # ... existing
  executor:
    build:
      context: .
      dockerfile: lab/executor.Dockerfile
    networks:
      - vuln-lab-network
    volumes:
      - ./prototype:/app/prototype
      - ./decision_engine:/app/decision_engine
```

| Criterion | Assessment |
|-----------|------------|
| Security impact | **LOW** — emulator still isolated |
| Implementation complexity | MEDIUM — new lightweight container |
| Reproducibility | HIGH |
| Effect on evidence quality | HIGH — genuine observed execution |
| Compatibility with current prototype | MEDIUM — need API/RPC between host and executor |
| Compatibility with GUI/API | MEDIUM |
| Compatibility with research evaluation | FULL |
| **Verdict** | **CANDIDATE** — but adds complexity |

### Option D: docker exec Approach

```bash
# Run executor inside emulator container
docker exec vuln-emulator python -c "
from prototype.lab_runner import run_lab_attempt
outcome = run_lab_attempt('127.0.0.1', 8080, '/vuln')
print(outcome)
"
```

| Criterion | Assessment |
|-----------|------------|
| Security impact | **LOW** — emulator still isolated |
| Implementation complexity | LOW — no compose changes |
| Reproducibility | MEDIUM — requires emulator to have Python + deps |
| Effect on evidence quality | HIGH — genuine observed execution |
| Compatibility with current prototype | MEDIUM — need to install Python in emulator |
| Compatibility with GUI/API | LOW — hard to integrate |
| Compatibility with research evaluation | MEDIUM |
| **Verdict** | **REJECT** — pollutes emulator container |

### Option E: Lightweight Executor Sidecar (RECOMMENDED)

Add a small `executor` service to `docker-compose.yml` that:
- Joins `vuln-lab-network`
- Has Python + project dependencies
- Exposes a Unix socket or minimal HTTP API on the lab network
- Host framework sends execution requests to the executor

```yaml
services:
  emulator:
    # ... existing
  executor:
    build:
      context: ..
      dockerfile: lab/executor.Dockerfile
    networks:
      - vuln-lab-network
    volumes:
      - ..:/app:ro
    environment:
      - LAB_NETWORK=true
```

| Criterion | Assessment |
|-----------|------------|
| Security impact | **LOW** — emulator still isolated, executor has no external access |
| Implementation complexity | MEDIUM — new Dockerfile + small HTTP server |
| Reproducibility | HIGH |
| Effect on evidence quality | HIGH — genuine observed execution |
| Compatibility with current prototype | HIGH — minimal changes to lab_runner.py |
| Compatibility with GUI/API | HIGH — API forwards to executor |
| Compatibility with research evaluation | FULL |
| **Verdict** | **RECOMMENDED** |

---

# RECOMMENDED TARGET ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────┐
│ Host                                                                │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────────────┐    │
│  │ Streamlit GUI │    │ FastAPI      │    │ CLI (prototype/)   │    │
│  │ frontend/     │    │ services/    │    │                    │    │
│  └──────┬───────┘    └──────┬───────┘    └────────┬───────────┘    │
│         │                   │                      │                │
│         └───────────────────┼──────────────────────┘                │
│                             │                                       │
│                             ▼                                       │
│              ┌──────────────────────────────┐                       │
│              │ decision_engine.core.engine   │                       │
│              │ run_engine()                  │                       │
│              └──────────────┬───────────────┘                       │
│                             │                                       │
│                             ▼                                       │
│              ┌──────────────────────────────┐                       │
│              │ Execution Layer               │                       │
│              │ create_simulation_executor()  │                       │
│              │ create_lab_executor()         │                       │
│              └──────────────┬───────────────┘                       │
│                             │                                       │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
                              │ HTTP/API (lab mode only)
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Docker: vuln-lab-network (internal:true)                            │
│                                                                     │
│  ┌─────────────────────────┐    ┌─────────────────────────────┐    │
│  │ executor service        │    │ vuln-emulator               │    │
│  │ (Python + lab_runner)   │───→│ 172.28.0.2:8080             │    │
│  │                         │    │ /vuln → "VULNERABLE"        │    │
│  │ Receives execution      │    │ /fail → "NOT_VULNERABLE"    │    │
│  │ requests from host      │    │ /health → {"status":"ok"}   │    │
│  └─────────────────────────┘    └─────────────────────────────┘    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

# MASTER IMPLEMENTATION PLAN

## PHASE A — Repository Integration/Reuse

**Objective:** Adopt useful external patterns without compromising architecture.

| Task | Source | Action | Files |
|------|--------|--------|-------|
| Add HTML/CSV output formats | vapt-agents/output_manager.py | ADAPT | prototype/report_generator.py |
| Strengthen target validation | vapt-agents/validation.py | ADAPT | prototype/lab_runner.py |
| UI pattern inspiration | AI-VAPT/dashboard | INSPIRE | frontend/app.py |

**Track:** B (Engineering)

---

## PHASE B — Docker Lab Architecture Correction

**Objective:** Enable real executor access to emulator while preserving isolation.

| Task | Details | Files |
|------|---------|-------|
| Create executor Dockerfile | Lightweight Python image | lab/executor.Dockerfile |
| Add executor service to compose | Joins vuln-lab-network | lab/docker-compose.yml |
| Create executor HTTP server | Minimal Flask/FastAPI on lab network | lab/executor_server.py |
| Update lab_runner.py | Route requests via executor service | prototype/lab_runner.py |
| Update execution_layer.py | Route lab executor via executor service | prototype/execution_layer.py |
| Update services/api.py | Route lab mode via executor service | services/api.py |

**Track:** B (Engineering)

---

## PHASE C — Real Executor Validation

**Objective:** Verify genuine observed execution against emulator.

| Task | Validation |
|------|------------|
| Start lab + executor | `docker compose -f lab/docker-compose.yml up -d` |
| Test /vuln endpoint | Expect SUCCESS |
| Test /fail endpoint | Expect FAIL_TIMEOUT |
| Test failure→pivot | Expect 2 failures then pivot |
| Test success path | Expect SUCCESS on first attempt |
| Test network isolation | External DNS unreachable from executor |

**Track:** B (Engineering)

---

## PHASE D — Evidence/Reporting Correction

**Objective:** Ensure evidence tiers reflect actual execution provenance.

| Task | Details | Files |
|------|---------|-------|
| Fix evidence tier logic | Distinguish SIMULATED/OBSERVED_LOCAL/DOCKER_OBSERVED | prototype/report_generator.py |
| Fix +772 documentation | Replace with +772 (or re-run benchmark) | docs/project_management/*.md |
| Fix JSONL wording | Clarify regenerable, not committed | docs/project_management/*.md |
| Add evidence tier tests | Verify correct labeling | prototype/tests/test_report.py |

**Track:** A (Research) for +772 fix, B (Engineering) for rest

---

## PHASE E — GUI/API Integration

**Objective:** Ensure GUI and API can use the corrected lab architecture.

| Task | Details | Files |
|------|---------|-------|
| Update GUI lab mode | Route via executor service | frontend/app.py |
| Update API lab mode | Route via executor service | services/api.py |
| Browser verification | Manual test of GUI lab mode | — |

**Track:** B (Engineering)

---

## PHASE F — Scanner/Recon Improvements

**Objective:** Strengthen target validation and add output formats.

| Task | Details | Files |
|------|---------|-------|
| Add domain-based blocks | Block .gov, .mil, .edu, bank, hospital | prototype/lab_runner.py |
| Add HTML report format | Borrow from vapt-agents | prototype/report_generator.py |
| Add CSV report format | Borrow from vapt-agents | prototype/report_generator.py |

**Track:** B (Engineering)

---

## PHASE G — Reporting Improvements

**Objective:** Enhance report quality and format options.

| Task | Details | Files |
|------|---------|-------|
| Add OWASP ASVS mapping | Borrow from vapt-agents | prototype/report_generator.py |
| Add remediation guidance | Borrow from vapt-agents | prototype/report_generator.py |
| Add executive summary | Borrow from vapt-agents | prototype/report_generator.py |

**Track:** B (Engineering)

---

## PHASE H — Test Expansion

**Objective:** Add tests for new functionality.

| Task | Details | Files |
|------|---------|-------|
| Docker lab integration tests | Test executor→emulator | prototype/tests/test_docker_lab.py |
| Evidence tier tests | Verify correct labeling | prototype/tests/test_report.py |
| Target validation tests | Test domain blocks | prototype/tests/test_safety.py |
| Output format tests | Test HTML/CSV generation | prototype/tests/test_report.py |

**Track:** B (Engineering)

---

## PHASE I — Final End-to-End Validation

**Objective:** Verify complete workflow from GUI/API/CLI to report.

| Step | Command | Expected |
|------|---------|----------|
| 1 | `docker compose -f lab/docker-compose.yml up -d` | Services healthy |
| 2 | `PYTHONPATH=. python -c "..."` | Lab execution works |
| 3 | `PYTHONPATH=. uvicorn services.api:app` | API starts |
| 4 | `curl -X POST .../runs -d '{"mode":"lab"}'` | Run succeeds |
| 5 | `curl .../runs/{id}/report` | Report has DOCKER_OBSERVED |
| 6 | `PYTHONPATH=. streamlit run frontend/app.py` | GUI launches |
| 7 | Manual: select lab mode, run scenario | Results displayed |

**Track:** B (Engineering)

---

## PHASE J — Documentation Cleanup

**Objective:** Fix all documentation discrepancies.

| Task | Details | Files |
|------|---------|-------|
| Fix +772 → +772 | All thesis docs | docs/project_management/THESIS_FINAL.md, etc. |
| Fix JSONL wording | Clarify regenerable | docs/project_management/*.md |
| Update README.md | Reflect current state | README.md |
| Update SAFETY_AUDIT.md | Document new architecture | docs/project_management/SAFETY_AUDIT.md |

**Track:** A (Research) for +772, B (Engineering) for rest

---

# PRIORITY MATRIX

## P0 — Must Fix Before Claiming Lab End-to-End Functionality

| # | Item | Phase | Track |
|---|------|-------|-------|
| P0-1 | Docker lab architecture correction (executor service) | B | B |
| P0-2 | Real executor validation | C | B |
| P0-3 | Evidence/reporting correction | D | A/B |
| P0-4 | +772 documentation fix | D | A |

## P1 — High-Value Engineering Improvements

| # | Item | Phase | Track |
|---|------|-------|-------|
| P1-1 | GUI/API integration with new lab architecture | E | B |
| P1-2 | Target validation strengthening | F | B |
| P1-3 | Multi-format output (HTML, CSV) | F | B |
| P1-4 | Test expansion | H | B |

## P2 — Optional Enhancements

| # | Item | Phase | Track |
|---|------|-------|-------|
| P2-1 | Reporting improvements (OWASP, remediation) | G | B |
| P2-2 | Documentation cleanup | J | B |

## P3 — Ideas to Defer/Reject

| Item | Reason |
|------|--------|
| CrewAI multi-agent orchestration | Would replace LangGraph engine |
| Live Nmap subprocess | Safety risk |
| React frontend replacement | Streamlit is sufficient |
| SQLite result storage | JSON/TXT sufficient |

---

# FILE-LEVEL CHANGE PLAN

## P0-1: Docker Lab Architecture Correction

### Files to Create

| File | Purpose |
|------|---------|
| `lab/executor.Dockerfile` | Lightweight Python image for executor |
| `lab/executor_server.py` | Minimal HTTP server on lab network |
| `lab/docker-compose.yml` (modify) | Add executor service |

### Files to Modify

| File | Change |
|------|--------|
| `prototype/lab_runner.py` | Route requests via executor service |
| `prototype/execution_layer.py` | Route lab executor via executor service |
| `services/api.py` | Route lab mode via executor service |

### executor.Dockerfile (Draft)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "lab/executor_server.py"]
```

### executor_server.py (Draft)

```python
"""Minimal HTTP server running on vuln-lab-network."""
from flask import Flask, request, jsonify
from prototype.lab_runner import run_lab_attempt

app = Flask(__name__)

@app.route('/execute', methods=['POST'])
def execute():
    data = request.json
    outcome = run_lab_attempt(data['target'], data['port'], data['path'])
    return jsonify({'outcome': outcome.value})

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9090)
```

### docker-compose.yml Addition (Draft)

```yaml
services:
  executor:
    build:
      context: ..
      dockerfile: lab/executor.Dockerfile
    container_name: lab-executor
    networks:
      - lab-network
    restart: unless-stopped
```

### lab_runner.py Modification (Draft)

```python
import os

def _get_executor_url():
    """Get executor URL based on environment."""
    if os.environ.get('LAB_NETWORK') == 'true':
        return 'http://lab-executor:9090'
    return None  # Direct execution (simulation or host-based lab)

def http_get(target, port, path, timeout=5.0):
    executor_url = _get_executor_url()
    if executor_url:
        # Route via executor service
        import requests
        resp = requests.post(f'{executor_url}/execute', json={
            'target': target,
            'port': port,
            'path': path
        }, timeout=timeout)
        result = resp.json()
        # Parse outcome back to Outcome enum
        ...
    else:
        # Direct execution (existing code)
        ...
```

---

# VALIDATION PLAN

## Post-Implementation Validation Sequence

| # | Test | Command/Action | Expected | Pass/Fail |
|---|------|----------------|----------|-----------|
| 1 | Unit tests | `pytest tests/ decision_engine/tests/ prototype/tests/ -q` | 192+ pass | |
| 2 | Docker lab startup | `docker compose -f lab/docker-compose.yml up -d` | Services healthy | |
| 3 | Emulator health | `docker exec vuln-emulator curl -s http://localhost:8080/health` | `{"status":"healthy"}` | |
| 4 | Executor connectivity | `docker exec lab-executor curl -s http://localhost:9090/health` | `{"status":"healthy"}` | |
| 5 | Success path (executor) | `docker exec lab-executor python -c "from prototype.lab_runner import run_lab_attempt; print(run_lab_attempt('172.28.0.2', 8080, '/vuln'))"` | SUCCESS | |
| 6 | Fail path (executor) | `docker exec lab-executor python -c "from prototype.lab_runner import run_lab_attempt; print(run_lab_attempt('172.28.0.2', 8080, '/fail'))"` | FAIL_TIMEOUT | |
| 7 | Host→executor→emulator | `curl -X POST http://localhost:9090/execute -d '{"target":"172.28.0.2","port":8080,"path":"/vuln"}'` | `{"outcome":"SUCCESS"}` | |
| 8 | Failure→pivot scenario | Run via CLI/API | 2 failures then pivot | |
| 9 | Checkpoint persistence | Save/load checkpoint | State restored | |
| 10 | Safety allowlist | Try `run_lab_attempt('192.168.1.1', 8080)` | ValueError | |
| 11 | No external egress | `docker exec lab-executor curl -s --max-time 3 http://8.8.8.8` | Timeout/fail | |
| 12 | Evidence tier (simulation) | Run simulation mode | Report says SIMULATED | |
| 13 | Evidence tier (Docker observed) | Run lab mode via executor | Report says DOCKER OBSERVED | |
| 14 | CLI path | `PYTHONPATH=. python prototype/cli.py run --scenario failure_pivot --mode lab` | Works | |
| 15 | API path | `curl -X POST .../runs -d '{"mode":"lab"}'` | Works | |
| 16 | GUI path | `streamlit run frontend/app.py` | Manual verification | |
| 17 | Final report generation | Open generated report | Correct evidence tier | |

---

# RISKS AND SAFETY

| Risk | Mitigation |
|------|------------|
| Executor service exposes attack surface | Only on internal network, no external access |
| Emulator could be used offensively | Returns strings only, no real exploits |
| Host could bypass executor | Enforce allowlist in both host and executor |
| Docker network misconfiguration | Test isolation explicitly |
| Evidence tier inflation | Strict labeling based on actual execution path |

---

# RESEARCH IMPACT

## Protected (Do Not Change)

| Item | Current Status |
|------|----------------|
| Gap-1 conclusion | NULL/ZERO (correctly reported) |
| Gap-2 contribution | State-aware failure-threshold pivot |
| Fair benchmark methodology | 4-agent ablation, identical cap T |
| Research claim discipline | A/B/C tier system |

## Potential Future Experiments

| Experiment | Value | Effort |
|------------|-------|--------|
| Live LLM assessor accuracy on corpus | Medium | Low |
| Cross-domain benchmark (more families) | Medium | Medium |
| Docker-observed success rate statistics | Low | Low |

---

# FINAL RECOMMENDATION

**YELLOW**

The project is technically sound and the research contribution is correctly framed. The primary blocker is the Docker network boundary between the host framework and the isolated emulator. The recommended solution (executor service on the lab network) preserves isolation while enabling genuine observed execution.

**Immediate next actions:**
1. Fix +772 documentation discrepancy (P0, Track A)
2. Implement executor service architecture (P0, Track B)
3. Validate real executor against emulator (P0, Track B)
4. Correct evidence tier labeling (P0, Track A/B)

**After P0 items, the project will have:**
- Genuine Docker-observed VAPT workflow
- Correct evidence tiers
- Fixed documentation discrepancies
- Preserved safety/isolation properties
- Unchanged research contribution

---

**END OF PLAN**

Waiting for your review and approval before implementation.
