# AI-VAPT Empirical Test & Evaluation Results

**Date:** 26 October 2026  
**Test Environment:** WSL2 Ubuntu 22.04 LTS, Python 3.10.12, NVIDIA GeForce MX550 (2048 MiB VRAM)  
**Target Assessed:** `https://pentest-ground.com:4280/` (Authorized Lab Scope Profile)  

---

## 1. Regression Test Suite Execution

The entire platform regression suite was executed via Pytest:
- **Command:** `uv run --extra dev pytest`
- **Collected Tests:** 1,057
- **Passed:** **1,057**
- **Failed:** **0**
- **Skipped:** 0
- **Duration:** 7.05 seconds
- **Pass Rate:** **100.0%**

### Subsystem Breakdown

| Test Module | Tests | Result | Purpose |
|---|---|---|---|
| `decision_engine/tests/` | 33 | 100% Pass | Frozen research core, graph traversal, benchmarking |
| `prototype/tests/` | 131 | 100% Pass | Lab runner, CLI, Docker demo, execution abstractions |
| `services/tests/` | 26 | 100% Pass | FastAPI routes, async worker queue, safety controls |
| `tests/test_validators.py` | 8 | 100% Pass | Modular finding validation framework (PHPInfo, Headers, Cookies, Files, Tech) |
| `tests/test_web_execution_and_pivot.py` | 2 | 100% Pass | Controlled web validation and GAP-2 bounded attempt pivoting |
| `tests/test_google_provider.py` | 11 | 100% Pass | Google Gemini provider, 404 auto-fallback, telemetry, key redaction |
| `tests/test_openrouter_provider.py` | 47 | 100% Pass | OpenRouter runtime key header, model catalog, retry logic |
| `tests/test_web_run_consistency.py` | 22 | 100% Pass | Stage A vs Stage B consistency, evidence tier honesty |
| `tests/test_saved_engagements.py` | 32 | 100% Pass | Reusable engagement scope governance outside Git |
| `tests/test_reporting.py` | 21 | 100% Pass | JSON, HTML, Markdown, TXT report renderers |

---

## 2. Comparative Assessment Runs on `pentest-ground.com:4280`

Two live assessments were performed against the authorized target using identical scanner inputs but different AI providers:

| Metric | Run 1: Local AI Model | Run 2: Hosted OpenRouter API | Manual Expert Baseline |
|---|---|---|---|
| **Run ID** | `6e030d37-b406-4f00-9391-19ad8d22e401` | `6ebb238e-9e1f-4722-a467-7f1642a3374b` | Manual Security Audit |
| **Provider** | Ollama (Local, Offline) | OpenRouter (Hosted API) | Security Auditor |
| **Model** | `qwen2.5:1.5b` (Q4_K_M) | `meta-llama/llama-3.3-70b-instruct` | Human Analyst |
| **GPU Offload** | 10/29 layers to CUDA (583 MiB VRAM) | Cloud NPU/GPU cluster | Human Mind |
| **Inference Latency** | 12.57 seconds | 4.11 seconds | ~5 minutes |
| **Cost** | \$0.00 (Zero API cost) | ~\$0.0001 | \$50–\$150/hr |
| **Actionable Candidates** | 1 (`phpinfo-files`) | 1 (`phpinfo-files`) | 1 (`phpinfo-files`) |
| **Service Discovery Inventory**| 10 records (Nmap, Tech, Headers) | 10 records (Nmap, Tech, Headers) | 10 observations |
| **Quality Assessment (GAP-1)** | `LOW` | `LOW` | Informational (Low exploitability) |
| **Validator Mobilized** | `PhpInfoValidator` | `PhpInfoValidator` | Manual GET curl |
| **Validation Status** | `CONFIRMED` | `CONFIRMED` | Confirmed Exposed |
| **Evidence Hash (SHA-256)** | `a56cbe33fb4f7ea072c5824b6518bc...` | `a56cbe33fb4f7ea072c5824b6518bc...` | Identical proof |
| **Decision Trace** | Attempt 1 -> SUCCESS -> Complete | Attempt 1 -> SUCCESS -> Complete | Verified |
| **Evidence Tier** | `CONTROLLED_VALIDATION` | `CONTROLLED_VALIDATION` | Active Verification |

### Conclusion on Model Accuracy
Both the lightweight local model `qwen2.5:1.5b` and the 70B parameter hosted model `llama-3.3-70b` produced **100% agreement** on exploit usability ranking, correctly recognizing that phpinfo exposure is an informational configuration flaw without remote code execution weaponization.

