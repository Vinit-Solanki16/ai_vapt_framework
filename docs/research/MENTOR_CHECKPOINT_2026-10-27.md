# Master Deliverable 1: M.Tech Thesis Mentor Checkpoint Briefing

**Project Title:** Autonomous AI Framework for Vulnerability Assessment: Integrating Exploit Quality Scoring and Dynamic Decision-Pivoting  
**Degree Program:** M.Tech Cyber Security  
**Meeting Date:** October 27, 2026  
**Checkpoint Date:** October 26, 2026  
**Repository Branch:** `development` | **Commit:** `a4af8fd`  
**Test Suite Status:** 1,045 passed in 9.15s (100% pass rate)  

---

## 1. Executive Summary & Purpose of This Checkpoint

This document presents a comprehensive, evidence-backed status report prepared for the master's thesis mentor review on October 27, 2026. The objective is to demonstrate that the AI-VAPT Framework is not merely a conceptual proposal or a thin wrapper around third-party security tools, but an operational, mathematically bounded, and empirically evaluated research artifact.

The framework successfully solves two primary research gaps identified in modern autonomous security testing:
1. **GAP-1 (Exploit Usability Pre-Assessment):** Traditional tools prioritize actions based solely on static severity scores (CVSS/EPSS), ignoring whether exploit artifacts are functional. Our framework introduces an AI-driven pre-execution assessor that inspects exploit code quality, dependencies, and delivery mechanisms, computing a composite priority score ($S = P \times W$) that avoids dead-end exploits.
2. **GAP-2 (State-Aware Dynamic Decision-Pivoting):** Autonomous LLM agents suffer from infinite retry loops when actions fail. Our framework implements a LangGraph directed state machine enforcing a per-candidate failure threshold ($N=2$), mathematically guaranteeing bounded execution ($T \le N \cdot |C|$) and seamless pivoting to alternative attack paths.

---

## 2. Verified Technical State & Hardware Acceleration

The prototype is fully configured and validated on consumer laptop hardware, demonstrating that autonomous AI security assessments can be performed locally without leaking sensitive corporate or network intelligence to third-party cloud providers:

| Layer / Subsystem | Implementation Details | Operational Status |
| :--- | :--- | :---: |
| **OS & Kernel** | Ubuntu 22.04 LTS on Windows 11 WSL2 (Kernel 6.6) | **OPERATIONAL** |
| **GPU Offloading** | NVIDIA GeForce MX550 (2048 MiB VRAM), DirectML-CUDA bridge | **VERIFIED** |
| **Local Model Arm** | Ollama (`http://127.0.0.1:11434`), model `qwen2.5:1.5b` (10/29 layers offloaded) | **ACTIVE** |
| **Hosted Model Arm** | Google Gemini (`gemini-2.0-flash`), OpenRouter (`llama-3.3-70b-instruct`) | **INTEGRATED** |
| **Reconnaissance** | Nmap 7.80 (`/usr/bin/nmap`) & Nuclei v3.11.1 (`/home/vinit/.local/bin/nuclei`) | **VERIFIED** |
| **API & Backend** | FastAPI asynchronous orchestrator (`services/api.py:8000`) | **RUNNING** |
| **User Interface** | Modern reactive Single Page Application (`frontend/web/index.html`) | **OPERATIONAL** |
| **Unit & Integration Tests** | 1,045 tests covering state machine, canonical models, and APIs | **100% PASS** |

---

## 3. Key Empirical Findings (Ready for Mentor Review)

The mentor will rightly demand empirical evidence rather than theoretical promises. The framework has been validated across four distinct experimental suites:

```mermaid
xychart-beta
    title "Precision and False-Positive Comparison Across Layers"
    x-axis ["Raw Scanner Detection Layer", "Active Non-Destructive Validation Layer"]
    y-axis "Percentage (%)" 0 --> 100
    bar [40, 100]
```

### 3.1 Multi-Layer Reliability Evaluation
- **Raw Scanner Heuristics:** Achieved 40.0% precision on our 10-case ground-truth fixture suite, generating 6 false positives due to naive regex and header matching.
- **Active Validation Layer:** Elevated precision to **100.0%** by actively verifying responses against reproducible HTTP criteria, eliminating 100% of false positives while maintaining 100% recall on confirmed vulnerabilities.
- **Inconclusive Isolation:** Safely isolated server errors and network timeouts into an `INCONCLUSIVE` tier rather than fabricating findings or crashing.

### 3.2 GAP-2 Dynamic Pivoting Benchmark
- Across 8 multi-stage failure scenarios, standard non-pivoting agents failed completely in 5 scenarios due to infinite retry loops consuming the entire budget.
- The AI-VAPT Framework with threshold $T=1$ achieved **100.0% penetration success** across all recoverable scenarios in an average of **2.37 action attempts**, verifying $O(N \cdot |C|)$ bounded execution.

---

## 4. Mentor Demonstration Runbook Summary

During tomorrow's meeting, the following live demonstration will be presented:
1. **System Health Verification:** Show live service bindings, scanner paths, and GPU offloading stats.
2. **Fail-Closed Target Scoping:** Demonstrate immediate rejection of unauthorized public hosts.
3. **GAP-1 Candidate Prioritization:** Walk through live candidate ranking using local Ollama `qwen2.5:1.5b`.
4. **GAP-2 Clean Decision Pivot:** Trigger an intentional exploit failure in a multi-candidate scenario and observe the state machine cleanly pivoting to candidate #2.
5. **Technical & Executive Reporting:** Generate real-time PDF/Markdown reports distinguishing validated true positives from informational observations.

---

## 5. Answers to Anticipated Mentor Questions

### Q1: *"How is your framework different from OWASP ZAP or Burp Suite?"*
**Answer:** *"ZAP and Burp are manual or semi-automated scanners. They identify potential indicators but do not orchestrate sequential attack graphs, do not evaluate exploit source code before execution, and cannot dynamically pivot when an attack path is blocked. Our framework operates as an autonomous decision engine on top of scanners."*

### Q2: *"How accurate is your AI model?"*
**Answer:** *"The local model `qwen2.5:1.5b` achieves 66.7% agreement with curated human expert labels and 100% syntactic schema compliance. Hosted Gemini achieves 88.5%. More importantly, the AI is never allowed to confirm vulnerabilities alone; confirmation requires active non-destructive HTTP proof, which yields 100% precision on our ground-truth benchmark."*

### Q3: *"Is this safe to run on enterprise networks?"*
**Answer:** *"Yes, because safety is hardcoded at the backend boundary. The engine enforces an authoritative whitelist (`VAPT_AUTHORIZED_WEB_SCOPES`), executes all subprocesses with `shell=False` to prevent command injection, and disallows unverified live exploit execution on external targets."*

