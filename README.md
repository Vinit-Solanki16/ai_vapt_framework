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

## 🚀 Quick Start

### 1. Launch the AI-VAPT Web Operations Console

Start the local web gateway and Single Page Application console:

```bash
uv run ai-vapt web --port 8000
```

Open `http://localhost:8000` in your browser to access the complete dashboard, configure AI providers, launch assessments, and track live turn-by-turn DAG traces.

### 2. Autonomous CLI Assessment

Execute an autonomous security assessment directly from your terminal:

```bash
# Autonomous deep assessment (500 turns, crawler, active fuzzer, SCA)
uv run ai-vapt --target http://127.0.0.1:3000/ -m deep --max-turns 500

# Targeted assessment with explicit focus
uv run ai-vapt --target https://example.com --instruction "Focus on authentication, JWT handling, and IDOR"

# Open local web viewer to inspect results
uv run ai-vapt view
```

*(Note: The legacy command `strix` is fully preserved as an alias for backwards compatibility).*

### 3. Verification Test Suite

Run the full local test suite:

```bash
# Run core test suites
uv run pytest tests/test_full_scanner.py tests/test_gap1_triage.py tests/test_gap2_pivoting.py tests/test_interface_api.py

# Run all 2,672 test cases
uv run pytest
```

---

## 🤖 Supported AI Providers

AI-VAPT features a flexible provider architecture supporting both cloud and local inference:

| Provider | Supported Models | Configuration |
|---|---|---|
| **Cloud Hosted (OpenAI-compatible)** | Qwen 2.5/3 Coder, DeepSeek V3, Llama 3.3 | Configure via Web Settings: custom `api_base`, `model`, optional `api_key` |
| **OpenRouter** | Anthropic Claude 3.5/3.7, OpenAI GPT-4o, DeepSeek V3 | Set `OPENROUTER_API_KEY` or configure in Web Settings |
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
