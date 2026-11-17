# Changelog — AI-VAPT Platform

All notable changes to the AI-VAPT (Autonomous AI Vulnerability Assessment & Penetration Testing) platform are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.7.0-rc1] — 2026-11-16

### Release Overview
**AI-VAPT 1.7.0 Release Candidate 1 (RC1)** marks the completion of the full autonomous security testing platform. AI-VAPT combines the Strix multi-agent penetration testing engine with Guided Attack Planning (GAP-1) for exploit candidate prioritization and Bounded Dynamic Pivoting (GAP-2) for adaptive execution.

### Added
- **Autonomous Multi-Agent Runner Integration:** Full integration with Strix multi-agent execution loop (`strix.core.runner`) operating within containerized Docker sandboxes (`ghcr.io/usestrix/strix-sandbox:1.3.0`).
- **GAP-1 Exploit Triage Engine:** Real-time attack surface profiling, stack discovery (`GENERIC_WEB`, `PHP_NGINX`), and exploit viability scoring to prioritize vulnerability candidates before agent dispatch.
- **GAP-2 Adaptive Execution & Bounded State Machine:** Failure tracking ($k \le 2$), candidate state transitions, probe outcome recording, and dynamic guidance towards uninvestigated candidates.
- **Completion Guard (`finish_scan`):** Strict completion gate that forbids premature scan termination while uninvestigated GAP-1 candidates remain in the queue.
- **Multi-Provider LLM Architecture:** Unified routing and in-memory credential storage across 6 provider categories:
  - Cloud Hosted / Custom (OpenAI-compatible endpoints: vLLM, llama.cpp, Kaggle/Cloudflare Quick Tunnels). **Live-Tested** in Phase D (`run-9542b3d7`).
  - OpenRouter (Multi-model hub: NVIDIA Nemotron 3.5 Super VL, DeepSeek R1, Llama 3.3 70B). **Live Preflight Validated**.
  - Google Gemini (Gemini 2.0 Flash, Gemini 1.5 Pro). **Unit & Contract Tested**.
  - Anthropic Claude (Claude 3.5 Sonnet, Claude 3.7 Sonnet). **Unit & Contract Tested**.
  - OpenAI (GPT-4o, GPT-4o-mini). **Unit & Contract Tested**.
  - Local Ollama (Qwen 2.5 Coder, Llama 3.1). **Local Mock & Connectivity Tested**.
- **In-Memory Credential Security (`strix/core/runtime_credentials.py`):** Ephemeral runtime credential storage that never writes API keys to disk and masks secrets in UI, API responses, and logs.
- **Multi-Format Reporting:** Comprehensive executive HTML reports with SHA-256 evidence hashes, PDF summaries, SARIF v2.1.0 compliant records, and machine-readable JSON.
- **Single-Page Operations Console:** Lightweight vanilla JS/HTML/CSS dashboard with live DAG visualization, real-time SSE progress, provider management, and historical run inspection.
- **State Hydration and Scan Resumption:** Robust state recovery via SQLite `agents.db` and coordinator snapshots, allowing interrupted or paused scans to resume without losing evidence.

### Fixed & Remediated
- **DEF-01:** Corrected false security assurance in scan category reporting by distinguishing unexamined categories from tested-clean categories.
- **DEF-02:** Corrected GAP-2 pivot accounting in HTML reports to accurately distinguish executed pivots from attempted probes.
- **DEF-03:** Added explicit multi-host and subdomain target scope enforcement to prevent out-of-scope requests.
- **DEF-04:** Eliminated synthetic request/response fallbacks in reports, enforcing cryptographic SHA-256 verification of genuine HTTP bytes.
- **DEF-05:** Restored strict Mypy type-checking across all 178 source files without module-level exclusions.
- **Timer Recovery:** Fixed elapsed timer behavior so duration freezes accurately upon pause or completion without runaway client-side timers.

### Verified in Live Assessment
- **Authoritative Phase D Assessment (`run-9542b3d7`):** Completed a fresh autonomous assessment against local OWASP Juice Shop v17.1.1 using Cloud Hosted Qwen3-Coder (`kaggle-model-deep`):
  - 100% GAP-1 queue completion (6 of 6 candidates investigated).
  - 5 validated security conditions (robots.txt disclosure, /ftp directory exposure, permissive wildcard CORS, missing security headers, missing CSP).
  - 1 confirmed negative condition (client-side DOM sink absence).
  - 0 uninvestigated candidates remaining (`not_tested: 0`).
  - Active duration of 1,100.5 seconds over 41 turns across 2 execution segments (Segment 1: 25 turns under initial turn budget; Segment 2: 16 turns under 45-turn resume limit; engine supports configurable limits up to 500 turns).
- **Test Suite Verification:**
  - Platform-wide Test Suite: 2,880 passed, 1 skipped, 3 xfailed across 2,884 collected tests.
  - Phase C Targeted Regression Suite: 221 passed, 1 skipped across all phase and defect remediation tests.
  - Core Phase & Provider Sub-Suite: 177 passed, 1 skipped across core phase contract tests.

### Known Limitations & Operational Qualifications
- **GAP-2 Alternative-Probe Fallback Pivoting:** Fallback alternative-probe pivoting was not triggered in the Phase D Juice Shop assessment because all targeted endpoints responded deterministically without network faults. Fallback pivoting remains verified under the lightweight scanner engine (`run-767ba9da`).
- **Configuration vs. Exploitation:** Validated Phase D findings represent configuration observations (wildcard CORS without credentials, missing security headers, directory indexing) and must not be presented as weaponized RCE exploits.
- **Ephemeral Remote Tunnels:** Cloudflare Quick Tunnel URLs (`[temporary Cloudflare tunnel endpoint]`) used for Cloud Hosted inference are ephemeral and require an active tunnel session.
- **Static Analysis Baseline:** Bandit reports 73 medium-severity findings (71 B310 URL audit warnings inherent to automated pentest tools, 2 B104 interface bindings) and 150 low-severity findings. Zero high-severity findings exist.
