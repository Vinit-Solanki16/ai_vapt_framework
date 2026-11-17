<div align="center">

# AI-VAPT

### Autonomous AI-Powered Vulnerability Assessment & Penetration Testing Platform

Autonomous AI security agents that discover, investigate, and validate application vulnerabilities through genuine dynamic exploits and cryptographic proof-of-concept evidence.

<br/>

[![CI](https://github.com/Vinit-Solanki16/ai_vapt_framework/actions/workflows/ci.yml/badge.svg)](https://github.com/Vinit-Solanki16/ai_vapt_framework/actions/workflows/ci.yml)
[![Python 3.12 | 3.13 | 3.14](https://img.shields.io/badge/Python-3.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://github.com/Vinit-Solanki16/ai_vapt_framework)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Release: v1.7.0 RC1](https://img.shields.io/badge/Release-v1.7.0%20RC1-orange.svg)](CHANGELOG.md)

</div>

---

## 1. Project Overview

**AI-VAPT** is an advanced autonomous security assessment framework designed to perform automated, end-to-end vulnerability assessment and penetration testing across web applications, APIs, and network endpoints.

Unlike traditional static vulnerability scanners that produce excessive noise and unverified alert lists, AI-VAPT combines multi-agent LLM reasoning with an integrated security runtime. Autonomous agents operate in a containerized Docker sandbox to probe candidate attack surfaces, execute active verification payloads, and produce tamper-evident cryptographic SHA-256 evidence digests for all confirmed findings and posture observations.

---

## 2. Main Capabilities

* **Multi-Agent Autonomous Execution Engine:** Orchestrates specialized agents (Root Agent, Recon Specialist, Injection Specialist, Hardening Auditor) across up to 500 autonomous turns with persistent telemetry.
* **GAP-1 Exploit Triage:** Dynamic vulnerability candidate prioritization and quality triage that prevents unverified reconnaissance observations from being promoted to confirmed vulnerabilities.
* **GAP-2 Adaptive Pivoting:** Bounded failure tracking ($k \le 2$ default, configurable) that detects unproductive, blocked, or timed-out attack vectors and pivots execution toward promising alternative paths.
* **Headless Attack Surface Profiling:** Built-in web crawler, active parameter fuzzer, and software composition analysis (SCA) to discover hidden endpoints, form vectors, and vulnerable third-party components.
* **Fail-Closed Scope Guard:** Enforces strict boundary validation preventing unintended assessment against cloud metadata endpoints (`169.254.169.254`), non-routable CIDRs, loopback escape vectors, or unauthorized hosts.
* **Audit-Ready Multi-Format Reporting:** Generates comprehensive executive HTML reports with SHA-256 evidence hashes, PDF summaries, SARIF v2.1.0 records, structured CSV matrices, and raw JSON telemetry.

---

## 3. Architecture Overview

```
                               ┌─────────────────────────────────────────────────────────────┐
                               │                 Web Operations Console / CLI                │
                               │                (FastAPI Gateway + SPA Assets)               │
                               └──────────────────────────────┬──────────────────────────────┘
                                                              │ REST / WebSocket
                               ┌──────────────────────────────▼──────────────────────────────┐
                               │                    Strix Execution Engine                   │
                               │  ┌───────────────────────┐       ┌────────────────────────┐ │
                               │  │ GAP-1 Dynamic Triage  │◄─────►│ GAP-2 Adaptive Pivots  │ │
                               │  └───────────┬───────────┘       └────────────────────────┘ │
                               │              │ Dispatched Candidates                        │
                               │  ┌───────────▼───────────┐       ┌────────────────────────┐ │
                               │  │   Multi-Agent Graph   │◄─────►│ Multi-Provider Router  │ │
                               │  │ (Root & Specialists)  │       │(Cloud / OpenRouter/Oll)│ │
                               │  └───────────┬───────────┘       └────────────────────────┘ │
                               └──────────────┼──────────────────────────────────────────────┘
                                              │ Sandbox Execution
                               ┌──────────────▼──────────────────────────────────────────────┐
                               │             Docker Sandbox Container Runtime                │
                               │   (curl, headless browser, fuzzers, port scanners, proxy)   │
                               └──────────────────────────────┬──────────────────────────────┘
                                                              │ Empirical Probes
                               ┌──────────────────────────────▼──────────────────────────────┐
                               │                Target Application / Lab Target              │
                               │                    (e.g. OWASP Juice Shop)                  │
                               └─────────────────────────────────────────────────────────────┘
```

---

## 4. Requirements

| Resource | Minimum Requirement | Recommended Specification |
|---|---|---|
| **Operating System** | Linux (Ubuntu 22.04+ / Debian 12+), macOS 13+, Windows 11 with WSL2 | Ubuntu 24.04 LTS or Debian 12 |
| **Python** | Python 3.12.0+ | Python 3.12.11+ |
| **Package Manager** | `uv` (recommended) or `pip` / `venv` | `uv` 0.5.0+ |
| **Container Engine** | Docker Engine 24.0+ (local daemon or remote TLS socket) | Docker 27.0+ with Compose v2 |
| **Sandbox Image** | `ghcr.io/usestrix/strix-sandbox:1.3.0` | Pre-pulled locally via launcher |
| **Hardware** | 2 CPU Cores, 4 GB RAM, 10 GB Disk | 4+ CPU Cores, 8 GB RAM, 25 GB Disk |
| **Network Egress** | Outbound access to chosen LLM provider or local LLM server | Broadband connection |

---

## 5. Installation Instructions

### Step 1: Clone the Repository
```bash
git clone https://github.com/Vinit-Solanki16/ai_vapt_framework.git
cd ai_vapt_framework
```

### Step 2: Automated Environment Setup
Run the unified setup launcher:
```bash
./ai-vapt.sh setup    # or ./setup.sh
```
This automated script:
1. Detects OS architecture, system CPU/RAM, and software prerequisites.
2. Creates and isolates the virtual environment (`.venv/`).
3. Installs runtime dependencies with `uv` (or falls back to `pip`).
4. Generates `.env` from `.env.example` safely without overwriting existing settings.
5. Verifies Docker daemon connectivity and pulls the Strix sandbox image (`ghcr.io/usestrix/strix-sandbox:1.3.0`).
6. Executes environment preflight validation.

---

## 6. Quickstart

Get AI-VAPT running in four simple commands:

```bash
# 1. Setup environment
./ai-vapt.sh setup

# 2. Launch the local lab target (OWASP Juice Shop)
./juice-shop.sh start

# 3. Start the AI-VAPT Operations Console
./ai-vapt.sh start

# 4. Open the Web Console in your browser:
#    http://127.0.0.1:8000
```

To stop services when finished:
```bash
./ai-vapt.sh stop
./juice-shop.sh stop
```

---

## 7. Provider Configuration

AI-VAPT supports a multi-provider LLM routing architecture:

| Provider Category | Supported Models | Configuration Mechanism |
|---|---|---|
| **Cloud Hosted (Custom)** | Qwen3-Coder (30B), DeepSeek-V3, Llama 3.3 | Web Settings UI (`/#/settings`) or `LLM_API_BASE` in `.env` |
| **OpenRouter** | Llama 3.3 70B, DeepSeek R1, Nemotron 3.5 | Set `OPENROUTER_API_KEY` in Web Settings UI or `.env` |
| **Google Gemini** | Gemini 2.0 Flash, Gemini 1.5 Pro | Set `GEMINI_API_KEY` in Web Settings UI or `.env` |
| **Anthropic Claude** | Claude 3.5 Sonnet, Claude 3.7 Sonnet | Set `ANTHROPIC_API_KEY` in Web Settings UI or `.env` |
| **OpenAI** | GPT-4o, GPT-4o-mini | Set `OPENAI_API_KEY` in Web Settings UI or `.env` |
| **Local Ollama** | Qwen 2.5 Coder, Llama 3.1 | Connects to `http://localhost:11434` (zero external network egress) |

> [!TIP]
> **In-Memory Security:** Keys entered in the Web Console are stored in process memory only (`runtime_credentials.py`) and are never written to disk or logged.

---

## 8. Cloud Hosted Profile Configuration (No Hardcoded URLs)

When using remote self-hosted models (e.g. Qwen3-Coder hosted on Kaggle or remote GPU clusters via ephemeral Cloudflare Quick Tunnels):

1. **Strict Dynamic Configuration:** AI-VAPT strictly prohibits hardcoding ephemeral tunnel URLs (such as `[temporary Cloudflare tunnel endpoint]`) in source code or configuration files.
2. **Web Console Profile Registration:**
   - Open **AI Models** (`http://localhost:8000/#/settings`).
   - Under **Cloud Hosted (Custom OpenAI-Compatible)**, click **Add Profile**.
   - Enter your active session endpoint:
     - **Base URL:** `[temporary Cloudflare tunnel endpoint]/v1`
     - **Model Name:** `kaggle-model` (or `kaggle-model-deep`)
     - **Context Window:** `131,072`
   - Click **Validate Credentials** -> Click **Save Profile** -> Set as **Active**.
3. **Session Rotation:** When your temporary tunnel rotates, simply update the Base URL in the Settings UI without restarting the server or modifying configuration files.

---

## 9. Docker and Juice Shop Setup

AI-VAPT includes an automated management script for the OWASP Juice Shop lab target container:

```bash
./juice-shop.sh start     # Starts Juice Shop with dual-binding (127.0.0.1:3000 & 172.17.0.1:3000)
./juice-shop.sh status    # Displays container health, uptime, and host/sandbox URLs
./juice-shop.sh restart   # Restarts container cleanly
./juice-shop.sh logs -f   # Tails Juice Shop access and error logs
./juice-shop.sh stop      # Stops and removes container safely
```

*Sandbox Bridge Routing:* The launcher binds port 3000 to both `127.0.0.1` (host access) and `172.17.0.1` (Docker bridge). When scanning `http://127.0.0.1:3000/`, AI-VAPT automatically rewrites the loopback target to `http://host.docker.internal:3000/` inside the sandbox so the containerized agents can reach the target.

---

## 10. Application Startup and Shutdown

Manage the AI-VAPT backend service using `./ai-vapt.sh`:

```bash
# Start backend in daemon mode (default port: 8000)
./ai-vapt.sh start

# Start on custom port or host
./ai-vapt.sh start --port 8080 --host 0.0.0.0

# Start in interactive foreground mode
./ai-vapt.sh start --foreground

# Check process status and resource usage
./ai-vapt.sh status

# Inspect application server logs
./ai-vapt.sh logs -f

# Gracefully terminate AI-VAPT services
./ai-vapt.sh stop
```

*Data Preservation Guarantee:* Stopping the application preserves all historical run artifacts in `strix_runs/`, evidence hashes, database records, and configuration files.

---

## 11. Assessment Workflow

```
[Target Input] ──► [Crawler & SCA Profiling] ──► [GAP-1 Candidate Triage]
                                                          │
   ┌──────────────────────────────────────────────────────┘
   ▼
[Agent Probe Execution (Docker Sandbox)]
   │
   ├─► [Observation Validated] ──────────► [State: VALIDATED_OBSERVATION]
   ├─► [Exploit Confirmed with Proof] ───► [State: VERIFIED_VULNERABILITY]
   ├─► [Ruled Out / Negative Space] ─────► [State: RULED_OUT / ABANDONED]
   └─► [Timeout / Blocked] ──────────────► [GAP-2 Adaptive Pivot (k <= 2)]
                                                          │
                                                          ▼
                                            [Multi-Format Reports Emitted]
```

1. **Launch:** Enter Target URL, select scan mode (`quick` or `deep`), and pick your AI model.
2. **Reconnaissance:** The crawler discovers routes, parameters, and technologies.
3. **Candidate Triage:** GAP-1 generates candidates scored by priority, usability, and exploit viability.
4. **Investigation:** Agents execute probes in the Docker sandbox.
5. **Contract Verification:**
   - Exploited findings require reproducible proofs to be marked `VERIFIED_VULNERABILITY`.
   - Defensive posture gaps without active exploits are marked `VALIDATED_OBSERVATION`.
   - Non-vulnerable endpoints are added to the negative space ledger.
6. **Completion:** When candidates are exhausted, reports are compiled and reconciled.

---

## 12. Report Formats

Every assessment automatically generates audit-grade deliverables in `strix_runs/<run-id>/`:

* **Executive HTML Report:** Interactive report with findings table, scan matrix, and SHA-256 evidence digests (`vapt_report_<run-id>.html`).
* **Summary PDF Report:** Presentation-ready printable executive summary (`vapt_report_<run-id>.pdf`).
* **SARIF Export:** OASIS SARIF v2.1.0 standard record for CI/CD and GitHub Security integration (`findings.sarif`).
* **CSV Export:** Tabular finding records with OWASP categories and CVSS scores (`vulnerabilities.csv`).
* **Structured JSON Data:** Full machine-readable execution telemetry, probe results, and candidate accounting (`run.json`, `vulnerabilities.json`, `coverage.json`).
* **Technical Markdown:** Detailed penetration test report (`penetration_test_report.md`).

---

## 13. Testing Instructions

Run the automated test and code quality suites:

```bash
# 1. Run full repository test suite (2,920+ passing tests)
.venv/bin/python -m pytest tests/

# 2. Run reporting and export subsystem tests (177 tests)
.venv/bin/python -m pytest tests/test_report*.py

# 3. Run targeted assessment integrity regression tests
.venv/bin/python -m pytest tests/test_assessment_integrity_run_14ee778a_remediation.py \
                           tests/test_phase_b_defect_remediation.py \
                           tests/test_phase5_live_execution_fixes.py

# 4. Code formatting & linting (Ruff)
.venv/bin/ruff check .

# 5. Static type checking (Mypy)
.venv/bin/mypy strix/

# 6. Static security analysis (Bandit)
.venv/bin/bandit -r strix/ -ll -ii
```

---

## 14. Documented Operational Boundaries, Limitations & Responsible Use (RC1)

To ensure academic and operational transparency, the following qualifications are documented for the RC1 release:

1. **Candidate Verification Standards:** AI-VAPT strictly distinguishes genuine vulnerabilities from security observations. Hardening defects (e.g. missing security headers or wildcard CORS on unauthenticated static endpoints) are categorized as `VALIDATED_OBSERVATIONS` and are not claimed as weaponized exploits.
2. **GAP-2 Adaptive Pivots:** Bounded alternative-path pivoting ($k \le 2$) triggers upon execution obstacles (timeouts, blocks). When endpoints respond deterministically without error, the engine completes candidate investigations without unnecessary pivoting.
3. **Model Server Availability:** External cloud-hosted inference requires that the remote inference endpoint remains accessible during the run.
4. **Heuristic Coverage Boundaries:** While AI-VAPT evaluates attack surfaces against OWASP Top 10 vulnerability categories, autonomous scanning operates under finite turn limits and candidate triage. An assessment tests only the specific endpoints and candidate vectors investigated during that run; it does not constitute exhaustive verification of all possible vulnerability classes across the entire target.

> [!WARNING]
> **Authorized Testing Only:** AI-VAPT executes active security probes. Only scan targets that you own or have **explicit, written authorization** to test. Unauthorized security testing is illegal.

---

## 15. License & Contributing

* **License:** AI-VAPT is licensed under the [Apache License, Version 2.0](LICENSE).
* **Contributing:** Pull requests, bug reports, and security disclosures are welcome. Please ensure all modifications pass `pytest`, `ruff`, `mypy`, and `bandit` before submitting.
