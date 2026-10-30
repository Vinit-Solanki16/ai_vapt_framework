# STRIX + AI-VAPT Integration: Master Architecture & Phase Index

> **STRICT SCOPE RULE:** All software development, refactoring, and code additions occur **EXCLUSIVELY inside `/home/vinit/STRIX/strix`**.  
> The existing `/home/vinit/AI_VAPT` directory is an immutable reference repository used solely to extract algorithms, frontend assets, and validation schemas. **No files inside `/home/vinit/AI_VAPT` will be modified.**

---

## 1. System Vision & Architecture

The objective of this integration is to transform **STRIX** from an unconstrained terminal-only agent into a **fully observable, goal-driven, and resource-bounded autonomous penetration testing platform** powered by the research contributions of **AI-VAPT**:

```
                                 ┌────────────────────────────────────────────────────────┐
                                 │              OPERATOR WEB BROWSER                     │
                                 │     (Unified Operations Console on Port 8000)          │
                                 └───────────────────────────┬────────────────────────────┘
                                                             │ HTTP / WebSocket
                                                             ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                 STRIX INTEGRATED PLATFORM                                              │
│                                                                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ 1. Unified Interface & API Gateway (`strix/interface/api.py`, `strix/interface/web/`)                            │  │
│  │    • Web Operations Console: Target input, scope verification, execution mode selection, report viewing          │  │
│  │    • Multi-Model Configurator: Local Ollama vs. Cloud APIs (Gemini, OpenRouter, OpenAI) with in-memory key safety│  │
│  └─────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────┘  │
│                                                            │                                                           │
│                                                            ▼                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ 2. Fail-Closed Scope Gatekeeper (`strix/core/safety/scope_validator.py`)                                         │  │
│  │    • Multi-tier address resolution: Unwraps NAT64 (RFC 6052), blocks RFC 1918, loopback, CGNAT, link-local, SSRF│  │
│  │    • Engagement profile validation and operator cryptographic acknowledgement                                    │  │
│  └─────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────┘  │
│                                                            │ Target Verified                                           │
│                                                            ▼                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ 3. Reconnaissance & Surface Ingestion (`strix/core/triage/ingest.py`)                                             │  │
│  │    • Nmap service discovery + Nuclei vulnerability detection + Strix Spider & Caido Proxy sitemap                │  │
│  │    • Normalization to OWASP Top-10:2021 categories, CVEs, and CWE identifiers                                    │  │
│  └─────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────┘  │
│                                                            │ Candidate Vulnerabilities                                 │
│                                                            ▼                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ 4. GAP-1: AI Exploit Quality Scoring & Prioritization (`strix/core/triage/exploit_assessor.py`)                  │  │
│  │    • Evaluates exploit syntax, prerequisites, network footprint, and complexity score                            │  │
│  │    • Assigns Usability Rank (HIGH, MEDIUM, LOW) & computes composite priority queue                              │  │
│  └─────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────┘  │
│                                                            │ Sorted Action Queue                                       │
│                                                            ▼                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ 5. GAP-2: Dynamic Bounded Decision-Pivoting Engine (`strix/core/decision_engine/`)                               │  │
│  │    • Enforces bounded attempt threshold k (default k=2) across agent execution loops                             │  │
│  │    • On k failures: Abandons dead-end vector, emits REDIRECT event, and dynamically pivots to next candidate      │  │
│  │    • Streams live decision DAG to the frontend console in real time                                              │  │
│  └─────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────┘  │
│                                                            │ Dispatched Task                                           │
│                                                            ▼                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ 6. Dual Execution Harness (`strix/tools/` & `strix/runtime/`)                                                    │  │
│  │    • Mode A (Safe Web VAPT): Active non-destructive HTTP validators (`strix/tools/validators/`)                  │  │
│  │    • Mode B (Autonomous Pentest): Strix Docker sandbox containers, dynamic shell, browser, and reverse proxy     │  │
│  └─────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────┘  │
│                                                            │ Outcomes & Evidence                                       │
│                                                            ▼                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ 7. Audit Reporting & Cryptographic Proof Verification (`strix/report/builder.py`)                                │  │
│  │    • Generates SHA-256 evidence hashes of raw HTTP responses (tamper-proof PoC)                                  │  │
│  │    • Produces audit-ready HTML reports, structured JSON runs, Markdown summaries, and SARIF 2.1.0 exports       │  │
│  │    • Actionable server hardening configurations (Nginx/Apache) and curl retest procedures                         │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Directory Structure of the Integration Documentation

All phased plans, agent development prompts, and verification procedures are organized into the following self-contained documents:

| Phase | Document Path | Focus Area | Key Deliverables in Strix |
| :--- | :--- | :--- | :--- |
| **Master Plan** | [`MASTER_INTEGRATED_PLAN.md`](file:///home/vinit/STRIX/strix/docs/strix_ai_vapt_integration/MASTER_INTEGRATED_PLAN.md) | Full Architectural Blueprint & 4 Pillars | Complete end-to-end plan integrating Strix with AI-VAPT |
| **Phase 1** | [`PHASE_1_FRONTEND_AND_API_GATEWAY.md`](file:///home/vinit/STRIX/strix/docs/strix_ai_vapt_integration/PHASE_1_FRONTEND_AND_API_GATEWAY.md) | Web Console UI & FastAPI Service | `strix/interface/web/`, `strix/interface/api.py`, `strix web` CLI command |
| **Phase 2** | [`PHASE_2_MULTI_MODEL_CONFIGURATION.md`](file:///home/vinit/STRIX/strix/docs/strix_ai_vapt_integration/PHASE_2_MULTI_MODEL_CONFIGURATION.md) | Multi-Model Routing & Key Safety | In-memory API key handling, Ollama auto-probe, Gemini & OpenRouter validation |
| **Phase 3** | [`PHASE_3_GAP1_EXPLOIT_QUALITY_SCORING.md`](file:///home/vinit/STRIX/strix/docs/strix_ai_vapt_integration/PHASE_3_GAP1_EXPLOIT_QUALITY_SCORING.md) | AI Exploit Quality Scoring (GAP-1) | `strix/core/triage/exploit_assessor.py`, OWASP normalization, composite scoring queue |
| **Phase 4** | [`PHASE_4_GAP2_DYNAMIC_DECISION_PIVOTING.md`](file:///home/vinit/STRIX/strix/docs/strix_ai_vapt_integration/PHASE_4_GAP2_DYNAMIC_DECISION_PIVOTING.md) | Bounded Dynamic Decision-Pivoting (GAP-2) | `strix/core/decision_engine/`, $k$-threshold retry policy, subagent branch pruning |
| **Phase 5** | [`PHASE_5_AUDIT_REPORTING_AND_SAFEGUARDS.md`](file:///home/vinit/STRIX/strix/docs/strix_ai_vapt_integration/PHASE_5_AUDIT_REPORTING_AND_SAFEGUARDS.md) | Reporting, Scope Gatekeeper & Proof | SHA-256 evidence hashing, fail-closed target validator, HTML/JSON/SARIF reports |
| **Prompts** | [`DEVELOPER_PROMPTS_AND_VERIFICATION_GUIDE.md`](file:///home/vinit/STRIX/strix/docs/strix_ai_vapt_integration/DEVELOPER_PROMPTS_AND_VERIFICATION_GUIDE.md) | Copy-Paste Execution Prompts | Exact prompts to feed an AI agent to execute each phase with verification tests |

---

## 3. Core Architectural Principles

1. **Non-Destructive Safe Verification First**: Real-world targets are validated non-destructively; weaponized payloads are restricted to isolated Docker lab containers.
2. **Deterministic Bounded Resource Consumption**: Every action path is bounded by threshold $k$ (default $k=2$) to eliminate infinite agent loops and excessive token expenditure.
3. **Provable Cryptographic Evidence**: Every finding confirmed by the framework records a SHA-256 hash of the server response body/headers to ensure zero fabricated outcomes.
4. **Zero Credential Persistence**: Cloud API keys (Gemini, OpenRouter) are handled exclusively in memory via per-request HTTP headers—never written to `.env`, disk, or logged.
5. **Fail-Closed Target Authorization**: Private RFC 1918 subnets, cloud metadata endpoints, and unacknowledged external domains are unconditionally blocked before any packet leaves the host.

