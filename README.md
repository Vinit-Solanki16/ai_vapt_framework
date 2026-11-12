<div align="center">

# AI-VAPT

### Autonomous AI-Powered Vulnerability Assessment & Penetration Testing Platform

Autonomous AI security agents that discover, investigate, and validate application vulnerabilities through genuine dynamic exploits and cryptographic proof-of-concept evidence.

<br/>

[![CI](https://github.com/Vinit-Solanki16/ai_vapt_framework/actions/workflows/ci.yml/badge.svg)](https://github.com/Vinit-Solanki16/ai_vapt_framework/actions/workflows/ci.yml)
[![Python 3.12 | 3.13 | 3.14](https://img.shields.io/badge/Python-3.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://github.com/Vinit-Solanki16/ai_vapt_framework)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Architecture: GAP-1 / GAP-2](https://img.shields.io/badge/Architecture-GAP--1%20%2F%20GAP--2-purple.svg)](docs/strix_ai_vapt_integration/PHASE_5_AUDIT_REPORTING_AND_SAFEGUARDS.md)

</div>

---

## ⚡ Overview

**AI-VAPT** is an advanced autonomous security assessment framework designed to perform automated, end-to-end vulnerability assessment and penetration testing across web applications, APIs, and network endpoints. Unlike traditional static scanners that produce high false-positive rates, AI-VAPT combines multi-agent LLM reasoning with an integrated security toolkit to actively verify vulnerabilities and produce cryptographic proof-of-concept evidence.

### Core Architecture

* **Multi-Agent Autonomous Execution Engine:** Orchestrates specialized agents for reconnaissance, attack surface profiling, parameter fuzzing, and exploit verification across up to 500 autonomous turns.
* **GAP-1 Exploit Triage:** Real-time vulnerability candidate discovery and quality triage that prevents unverified reconnaissance findings from being promoted to confirmed vulnerabilities.
* **GAP-2 Dynamic Pivoting:** Bounded failure tracking ($k \le 3$) that automatically detects blocked or unproductive attack vectors and pivots execution toward promising alternative paths.
* **Headless Attack Surface Profiling:** Built-in web crawler, active parameter fuzzer, and software composition analysis (SCA) to discover hidden endpoints, form vectors, and vulnerable third-party components.
* **Fail-Closed Scope Guard:** Enforces strict boundary validation preventing unintended assessment against cloud metadata endpoints (`169.254.169.254`), non-routable CIDRs, or unauthorized hosts.
* **Audit-Ready Multi-Format Reporting:** Generates comprehensive executive HTML reports with SHA-256 evidence hashes, PDF summaries, SARIF v2.1.0 records, and structured JSON outputs.

---

## 🚀 Quick Start (One-Command Experience)

AI-VAPT is designed for complete portability. Get the entire system running with one command:

### 1. First-Time Setup
```bash
./setup.sh
```
This automated setup script:
- Detects OS (Linux, macOS, WSL2, GitHub Codespaces) and resources.
- Verifies Python 3.12+ and sets up the `.venv` virtual environment.
- Installs all dependencies with `uv` or `pip`.
- Generates `.env` from `.env.example` safely without overwriting user configs.
- Verifies local and remote Docker daemon connectivity and checks the sandbox image (`ghcr.io/usestrix/strix-sandbox:1.3.0`).
- Validates configured AI providers without exposing credentials.
- Runs application preflight readiness checks.

### 2. Everyday Startup
```bash
./start.sh
```
Starts the AI-VAPT Web Operations Console in the background (default port 8000).  
To run in interactive foreground mode: `./start.sh --foreground`  
To specify a custom port: `./start.sh --port 8080`

Open your browser to: **`http://localhost:8000`**

### 3. Clean Shutdown
```bash
./stop.sh
```
Gracefully terminates application services, frees network ports, and clears locks while **strictly preserving** all scan artifacts, logs, findings, configurations, and Docker images.

---

## 📖 Complete Documentation & Guides

| Document | Purpose |
|---|---|
| [**`AI_VAPT_SETUP_GUIDE.md`**](file:///workspaces/ai_vapt_framework/AI_VAPT_SETUP_GUIDE.md) | Step-by-step setup walkthrough for Linux, Codespaces, WSL2, and macOS |
| [**`AI_VAPT_DEVELOPMENT_GUIDE.md`**](file:///workspaces/ai_vapt_framework/AI_VAPT_DEVELOPMENT_GUIDE.md) | Developer guide, codebase architecture, testing, and contribution standards |
| [**`AI_VAPT_DOCKER_RUNTIME_GUIDE.md`**](file:///workspaces/ai_vapt_framework/AI_VAPT_DOCKER_RUNTIME_GUIDE.md) | Local and remote TLS Docker runtime architecture and sandbox container lifecycle |
| [**`AI_VAPT_REMOTE_DOCKER_VM_SETUP.md`**](file:///workspaces/ai_vapt_framework/AI_VAPT_REMOTE_DOCKER_VM_SETUP.md) | Hardened remote Ubuntu Docker VM provisioning guide for Codespaces |
| [**`AI_VAPT_DEPLOYMENT_GUIDE.md`**](file:///workspaces/ai_vapt_framework/AI_VAPT_DEPLOYMENT_GUIDE.md) | Production server sizing, systemd service setup, and Nginx reverse proxy |
| [**`AI_VAPT_OPENROUTER_MODEL_BENCHMARK.md`**](file:///workspaces/ai_vapt_framework/AI_VAPT_OPENROUTER_MODEL_BENCHMARK.md) | Live empirical benchmark results across OpenRouter free models |
| [**`AI_VAPT_FINAL_MODEL_SELECTION.md`**](file:///workspaces/ai_vapt_framework/AI_VAPT_FINAL_MODEL_SELECTION.md) | Final primary and backup model selection with live tool-calling proof |
| [**`AI_VAPT_GAP1_GAP2_INTEGRATION_AUDIT.md`**](file:///workspaces/ai_vapt_framework/AI_VAPT_GAP1_GAP2_INTEGRATION_AUDIT.md) | Verification audit of GAP-1 triage, GAP-2 dynamic pivots, and accounting math |
| [**`AI_VAPT_MASTER_IMPLEMENTATION_REPORT.md`**](file:///workspaces/ai_vapt_framework/AI_VAPT_MASTER_IMPLEMENTATION_REPORT.md) | Master audit report and implementation ledger |
| [**`AI_VAPT_FINAL_COMPLETION_REPORT.md`**](file:///workspaces/ai_vapt_framework/AI_VAPT_FINAL_COMPLETION_REPORT.md) | Consolidated phase completion verdict and manual verification roadmap |

---

---

## 🤖 Supported AI Providers

AI-VAPT features a flexible provider architecture supporting both cloud and local inference:

| Provider | Supported Models | Configuration |
|---|---|---|
| **Cloud Hosted (OpenAI-compatible)** | Qwen 2.5/3 Coder, DeepSeek V3, Llama 3.3 | Configure via Web Settings: custom `api_base`, `model`, optional `api_key` |
| **OpenRouter (Multi-Model Hub)** | NVIDIA Nemotron 3.5 Super VL (Primary Free — 1M Context), NVIDIA Nemotron 3.5 Lightning (Backup Free — 1M Context), Claude 3.5/3.7, GPT-4o, DeepSeek V3 | Set `OPENROUTER_API_KEY` in `.env` or configure in Web Settings |
| **Google Gemini** | Gemini 2.0 Flash, Gemini 1.5 Pro | Set `GEMINI_API_KEY` or configure in Web Settings |
| **Local Ollama** | Qwen 2.5 Coder, Llama 3.1 | Connects to local Ollama instance at `http://127.0.0.1:11434` |

---

## 📊 Features & Security Tooling

* **HTTP Interception & Replay:** Deep request/response analysis with custom header and payload manipulation.
* **Authentication & Session Analysis:** Automated JWT signature inspection, role decoding, and IDOR parameter validation.
* **Injection Testing:** Active fuzzer probes for Reflected/Stored XSS, SQL injection error patterns, Local File Inclusion (LFI), and SSTI.
* **SCA Component Profiler:** Identifies outdated libraries (Bootstrap, jQuery, Angular, Express) against known CVE databases.
* **Cryptographic Evidence Verification:** Every confirmed finding records an immutable SHA-256 evidence hash of the exploit payload and server response.

---

## 📁 Repository Structure

```
├── strix/                     # AI-VAPT Core Package
│   ├── core/                  # Decision engine, GAP bridge, crawler, fuzzer, safety validator
│   ├── interface/             # Web Operations Console, REST API, CLI, and Viewer
│   │   ├── web/               # SPA Frontend assets (index.html, app.js, css)
│   │   ├── viewer/            # Assessment report viewer and PDF builder
│   │   ├── api.py             # FastAPI gateway implementation
│   │   └── main.py            # CLI entrypoint and command dispatcher
│   ├── llm/                   # Multi-model router, Cloud Hosted provider, Ollama service
│   ├── report/                # HTML audit builder, SARIF exporter, and pricing ledger
│   └── tools/                 # Assessment tooling (recon, proxy, fuzzer, reporting)
├── tests/                     # 2,672 test cases across 132 test modules
├── benchmark_results/         # Benchmark data and comparative performance reports
└── pyproject.toml             # Project dependencies, tool configuration, and entrypoints
```

---

## 🔒 Responsible Use & Authorization

> [!WARNING]
> **Authorized Testing Only:** AI-VAPT actively probes targets with dynamic penetration testing techniques. Only assess targets that you own or have **explicit, written authorization** to test. Unauthorized security testing is strictly illegal in most jurisdictions. Users are solely responsible for verifying scope and legal compliance.
