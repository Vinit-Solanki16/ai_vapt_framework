# STRIX + AI-VAPT Integration Blueprint

## Autonomous Penetration Testing Platform with Exploit Quality Scoring (GAP-1), Dynamic Decision-Pivoting (GAP-2), and Unified Multi-Model Web Console

**Document Reference:** `STRIX-AI-VAPT-INT-2026-v1.0`  
**Target Repository:** `/home/vinit/STRIX/strix`  
**Source Repository:** `/home/vinit/AI_VAPT`  
**Author:** AI-VAPT Research & Engineering Team  
**Status:** Architecture Specification & Implementation Plan  

---

## 1. Executive Summary & Objective

The objective of this integration is to synthesize two complementary cybersecurity systems into a single, cohesive, production-grade autonomous penetration testing platform:

1. **STRIX (`/home/vinit/STRIX/strix`)**: An advanced autonomous offensive agent framework utilizing `openai-agents` and `litellm`, offering rich execution sandboxing (Docker execution containers, browser automation, Caido HTTP proxy, shell tools, and multi-agent coordination graphs).
2. **AI-VAPT (`/home/vinit/AI_VAPT`)**: An evidence-backed research decision engine featuring:
   - **GAP-1**: Quantitative AI Exploit Quality Scoring and candidate prioritization.
   - **GAP-2**: Bounded failure recovery with Dynamic Decision-Pivoting.
   - **Multi-Model Frontend Console**: A real-time web operations UI allowing zero-restart hot-swapping of local models (Ollama: `qwen2.5:1.5b`, `llama3.2:3b`) and hosted APIs (Google Gemini, OpenRouter, OpenAI) with in-memory credential safety.
   - **Fail-Closed Target Authorization**: Strict ethical scope management, address validation, and RFC 1918 / CGNAT blocking.
   - **Active Controlled Verification**: Non-destructive validators and cryptographic SHA-256 proof-of-concept capture.

### Key Goals of the Integrated System:
- **Unified Web Operations Console**: Replace Strix's read-only post-run viewer with an interactive SPA web console for live configuration, target scoping, runtime model selection, real-time pipeline visualization, and audit-ready reporting.
- **Frontend Model & Credential Management**: Empower operators to select any LLM (local Ollama or hosted API) and supply runtime API keys via the web interface without modifying `.env` files or restarting CLI processes.
- **GAP-1 Exploit Quality Prioritization**: Inject AI exploit quality scoring into Strix's vulnerability discovery and subagent dispatch pipeline, preventing agents from wasting time on broken or unviable exploits.
- **GAP-2 Dynamic Decision-Pivoting**: Enforce bounded retry thresholds ($k$) across Strix's agent loops, automatically pruning failing attack paths and pivoting to alternative high-priority candidates.

---

## 2. Comparative Architecture Analysis

| System Capability | Existing STRIX Implementation | Existing AI-VAPT Implementation | Integrated Target Platform |
| :--- | :--- | :--- | :--- |
| **User Interface** | CLI, Textual TUI, Read-only post-run HTML viewer | Full interactive SPA Web Console (`frontend/web/`) | **Unified Web Operations Console** (Interactive Assessment Setup + Real-time Streaming DAG + Report Viewer) |
| **LLM Support** | LiteLLM via env vars (`STRIX_LLM`, `LLM_API_KEY`) | Dynamic provider router: Ollama local + Hosted (OpenRouter, Gemini, OpenAI) | **Dynamic Multi-Provider Router** (Configured via Frontend, In-Memory Header Keys, Zero-Restart) |
| **Model Provenance** | Basic token logging | Fallback tracking, latency recording, deterministic fallback labeling | **Auditable AI Provenance** (Tracks real LLM vs. Fallback, Latency, Prompt Hashes) |
| **Candidate Ranking** | Unstructured prompt guidance | **GAP-1**: Quantitative Exploit Quality Scoring ($QualityRank \times Severity$) | **GAP-1 Integrated Triage Queue** (Scores syntax, prerequisites, noise before agent dispatch) |
| **Failure Recovery** | Max turns budget (up to 500 turns); agent can loop on dead ends | **GAP-2**: Strict bounded threshold $k$, automated candidate abandonment, and redirection | **GAP-2 Dynamic Decision Engine** (Prunes dead-end subagent branches at threshold $k$ and redirects) |
| **Target Scoping** | Basic URL safety check | Fail-closed multi-tier validator (DNS resolution, RFC 1918 block, NAT64 unwrapping, Profiles) | **Fail-Closed Scope Gatekeeper** (Ensures full ethical and legal authorization compliance) |
| **Execution Engine** | Docker sandbox, shell, browser, proxy tools | Active non-destructive HTTP validators | **Dual-Tier Execution**: Safe Non-Destructive Validation for production + Sandboxed Exploitation for lab |
| **Proof of Concept** | Raw tool transcripts, markdown report | Cryptographic SHA-256 evidence hashing, response excerpts | **Cryptographic Tamper-Proof PoC Reports** (HTML + JSON + PDF + SARIF) |

---

## 3. Target System Architecture

```
                                  OPERATOR WEB BROWSER
                     (Unified AI-VAPT Operations Console on :8000)
                                           │
                    ┌──────────────────────┴──────────────────────┐
                    │                                             │
         [New Assessment Config]                      [Live Monitoring & Reports]
         • Target URL & Scope Profile                 • Real-time Agent DAG Stream
         • AI Provider (Ollama/Gemini/OpenRouter)     • GAP-2 Decision Pivots
         • In-Memory Runtime API Key                  • Cryptographic Proof Hashes
         • Pivot Threshold (k) & Mode                 • Audit-Ready PDF / HTML Reports
                    │                                             ▲
                    ▼                                             │
      ═════════════════════════════════════════════════════════════════════════
                       STRIX + AI-VAPT UNIFIED API GATEWAY
                      (FastAPI / Uvicorn Service Layer)
      ═════════════════════════════════════════════════════════════════════════
                    │
         ┌──────────┴──────────┐
         │ 1. Scope Gatekeeper │ ──[Fail-Closed]──► [Reject Unauthorized Target]
         └──────────┬──────────┘
                    │ Target Authorized
                    ▼
         ┌────────────────────────────────────────────────────────┐
         │ 2. Dynamic Model Router (LiteLLM + AI-VAPT Providers)  │
         │    • Local Ollama: qwen2.5:1.5b / llama3.2:3b          │
         │    • Hosted APIs: Google Gemini, OpenRouter, OpenAI    │
         │    • In-memory ephemeral key injection (No .env leak) │
         └──────────────────────────┬─────────────────────────────┘
                                    │
                                    ▼
         ┌────────────────────────────────────────────────────────┐
         │ 3. Reconnaissance & Surface Mapping Engine             │
         │    • Nmap service discovery                            │
         │    • Nuclei vulnerability scanners                     │
         │    • Strix web spider & Caido HTTP proxy sitemap       │
         └──────────────────────────┬─────────────────────────────┘
                                    │ Raw Discovered Findings
                                    ▼
         ┌────────────────────────────────────────────────────────┐
         │ 4. GAP-1: AI Exploit Quality Scoring & Prioritization  │
         │    • LLM parses exploit syntax, prerequisites, noise   │
         │    • Scores Usability Rank (HIGH / MEDIUM / LOW)       │
         │    • Computes Composite Score: FinalPriority = f(...) │
         └──────────────────────────┬─────────────────────────────┘
                                    │ Ranked Action Candidates
                                    ▼
         ┌────────────────────────────────────────────────────────┐
         │ 5. GAP-2: Dynamic Bounded Decision Engine              │
         │    • Tracks per-candidate attempt counter              │
         │    • If attempts >= k: ABANDON route & REDIRECT        │
         │    • Selects next highest GAP-1 candidate              │
         └──────────────────────────┬─────────────────────────────┘
                                    │ Candidate Dispatched
                                    ▼
         ┌────────────────────────────────────────────────────────┐
         │ 6. Autonomous Execution Engine                         │
         │    • Mode A: Safe Controlled Validator (HTTP Probes)   │
         │    • Mode B: Strix Sandbox Container (Docker / Browser)│
         └──────────────────────────┬─────────────────────────────┘
                                    │
                                    ▼
         ┌────────────────────────────────────────────────────────┐
         │ 7. Proof Verification & Cryptographic Reporting        │
         │    • Computes SHA-256 evidence hash of responses       │
         │    • OWASP Top-10 / CVE / CWE mapping                  │
         │    • Generates HTML, JSON, Markdown & SARIF reports    │
         └────────────────────────────────────────────────────────┘
```

---

## 4. Detailed Component Integration Specifications

### 4.1 Frontend & API Consolidation

#### The Strategy
Rather than maintaining Strix's read-only viewer and AI-VAPT's SPA as disjoint applications, we merge them into a single unified web interface:
1. **Host Frontend Files**: Mount `frontend/web/` from AI-VAPT under `strix/interface/viewer/web/` or serve directly via the FastAPI application.
2. **Consolidate Backend API**: Extend `services/api.py` into `strix/interface/api.py`, integrating Strix's `/api/runs` and scan-steering capabilities with AI-VAPT's `/runs`, `/targets/validate`, `/engagements`, `/scanners/status`, and `/system/health`.
3. **Frontend Additions**:
   - Add a **Strix Execution Mode** toggle:
     - `Controlled Validation (Safe HTTP Probes + Cryptographic Hash)`
     - `Autonomous Agent Sandbox (Docker Container + Dynamic Shell/Browser)`
   - Add Strix's Agent Graph visualization to the **Decision Paths / Pivot Analysis** view.

---

### 4.2 Multi-Model Configuration & Runtime Provider Routing

#### The Challenge in Strix
Strix currently relies on static environment variables (`STRIX_LLM="openrouter/..."`, `LLM_API_KEY="..."`). This forces operators to edit shell configs and restart processes to change models or keys.

#### The AI-VAPT Solution Integrated into Strix
1. **Dynamic Model Routing Layer (`strix/config/model_router.py`)**:
   Wrap Strix's `LlmSettings` with AI-VAPT's runtime credential handler:
   ```python
   class RuntimeModelContext:
       provider: Literal["ollama", "google", "openrouter", "openai"]
       model_name: str
       ephemeral_api_key: Optional[str]  # In-memory only, discarded after run
   ```
2. **Frontend Model Switcher**:
   The frontend `New Assessment` screen exposes:
   - **Local Mode (Ollama)**: Automatically probes `http://127.0.0.1:11434` and populates installed models (`qwen2.5:1.5b`, `llama3.2:3b`, `qwen3.5:4b`). No API key required.
   - **Hosted OpenRouter**: Real-time catalogue validation via `X-OpenRouter-API-Key` header.
   - **Hosted Google Gemini**: Real-time validation via `X-Google-API-Key` header (`gemini-2.0-flash`, `gemini-flash-lite-latest`).
   - **Hosted OpenAI**: In-memory `Authorization: Bearer` key.
3. **LiteLLM Mapping**:
   Map incoming frontend selections to LiteLLM model prefixes:
   - Ollama: `ollama/qwen2.5:1.5b` with `api_base="http://127.0.0.1:11434"`
   - Gemini: `gemini/gemini-2.0-flash` with runtime `api_key`
   - OpenRouter: `openrouter/<model_id>` with runtime `api_key`

---

### 4.3 GAP-1 Integration: AI Exploit Quality Scoring & Prioritization

#### Location in Strix
Integrate into `strix/core/inputs.py` and before `build_root_task` / `spawn_child_agent` in `strix/core/runner.py`.

#### Algorithm & Workflow
1. When reconnaissance or static analysis identifies potential vulnerabilities, create an `ActionCandidate` list.
2. For each candidate, pass the vulnerability signature and exploit snippet to `assess_exploit_quality()`:
   - **Evaluation Criteria**:
     - Exploit code presence and syntax validity.
     - Required system privileges (None, User, Administrator/Root).
     - Network footprint & WAF noise (Low, Medium, High).
     - Execution prerequisites.
   - **Quality Ranking Output**:
     - `HIGH`: Fully functional, standalone, low noise, verified logic.
     - `MEDIUM`: Requires minor customization or specific environment conditions.
     - `LOW`: Incomplete snippet, theoretical PoC, high noise, or non-functional.
3. **Mathematical Priority Formulation**:
   $$\text{Final Priority Score} = w_1 \cdot P_{\text{base}} + w_2 \cdot S_{\text{CVSS}} + w_3 \cdot E_{\text{exposure}} + w_4 \cdot Q_{\text{AI}}$$
   Where:
   - $P_{\text{base}}$: Baseline scanner confidence $[0.0, 1.0]$.
   - $S_{\text{CVSS}}$: Normalized severity score $[0.0, 1.0]$.
   - $E_{\text{exposure}}$: Asset exposure factor (e.g. public vs. authenticated) $[0.0, 1.0]$.
   - $Q_{\text{AI}}$: AI quality rank bonus ($HIGH = +0.3$, $MEDIUM = +0.1$, $LOW = 0.0$).
4. Candidates are sorted in descending order of `Final Priority Score`. Strix's subagents are dispatched **strictly to the top candidate first**.

---

### 4.4 GAP-2 Integration: Dynamic Bounded Decision-Pivoting

#### Location in Strix
Integrate into `strix/core/execution.py` (`run_agent_loop`) and `strix/core/agents.py` (`AgentCoordinator`).

#### The Problem in Existing Strix
Strix subagents currently operate with turn budgets (e.g. 30–50 turns). When an exploit fails against a protected endpoint, the agent often tries repetitive slight variations, burning tokens and time on an unviable target.

#### The GAP-2 Pivot Engine
1. **Pivot State Machine**:
   - Maintain an in-memory attempt register: `attempts_per_candidate: Dict[str, int]`.
   - Configure Pivot Threshold $k$ (default: $k=2$, configurable via frontend).
2. **Attempt Execution & Outcome Evaluation**:
   - Each action attempt yields an outcome: `SUCCESS`, `FAIL_TIMEOUT`, or `NOT_REPRODUCIBLE`.
   - On `SUCCESS`: Record cryptographic evidence, mark finding as `CONFIRMED`, advance to next goal.
   - On `FAIL_TIMEOUT`: Increment candidate attempt count:
     $$\text{attempts}[c] \leftarrow \text{attempts}[c] + 1$$
3. **Threshold Evaluation & Pivot Redirection**:
   - If $\text{attempts}[c] \ge k$:
     - **Trigger Pivot**: Emit event `ABANDON_CANDIDATE(id=c, reason="Threshold k reached")`.
     - **Prune Subagent**: Terminate or reassign the Strix child agent executing candidate $c$.
     - **Dynamic Redirection**: Select candidate $c_{next}$ from the GAP-1 priority queue.
     - Emit event `PIVOT_REDIRECT(from=c, to=c_next)`.
     - Update live Decision Trace and interactive DAG visualization in the frontend.

---

### 4.5 Safety, Scope Authorization, & Ethical Controls

#### Target Gatekeeper (`strix/core/safety.py`)
Incorporate AI-VAPT's `vapt_platform/web_target.py` into Strix's pre-execution pipeline:
1. **RFC 1918 & Cloud Metadata Blocking**:
   Automatically reject non-authorized targets resolving to:
   - `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
   - `127.0.0.0/8` (unless explicitly authorized local lab profile)
   - `169.254.169.254` (AWS/GCP metadata)
   - `100.64.0.0/10` (Carrier-grade NAT)
2. **NAT64 / DNS64 Handling**:
   Unwrap synthesized RFC 6052 IPv6 prefixes (`64:ff9b::/96`) and validate embedded IPv4 public routability.
3. **Operator Acknowledgement**:
   External targets require explicit authorization reference code and frontend confirmation before dispatching scanner or agent processes.

---

## 5. End-to-End Execution Walkthrough

When an operator assesses `https://xyz.com:4280/` through the integrated system:

1. **Intake & Scope Check**:
   - Operator enters `https://xyz.com:4280/` in the web console.
   - Target is verified: publicly routable IP validated; operator acknowledges engagement scope.
2. **Model Selection**:
   - Operator selects **Ollama (`qwen2.5:1.5b`)** for private offline assessment OR **Google Gemini (`gemini-2.0-flash`)** with an in-memory key.
3. **Reconnaissance & Discovery**:
   - Nmap executes controlled service discovery on port 4280.
   - Nuclei scans for exposures and misconfigurations.
   - Strix spider identifies API endpoints and sitemap parameters.
4. **GAP-1 Quality Scoring**:
   - 12 raw findings are discovered.
   - 8 are categorized as Informational/Discovery (saved to inventory, excluded from attack).
   - 4 Actionable Vulnerabilities are passed to the AI Assessor:
     - Candidate 1 (`/phpinfo.php`): AI Rank = `HIGH` (standalone, zero noise).
     - Candidate 2 (`CORS Misconfiguration`): AI Rank = `MEDIUM`.
     - Candidate 3 (`Theoretical XSS on /search`): AI Rank = `LOW` (requires user interaction).
     - Candidate 4 (`Outdated Library Banner`): AI Rank = `LOW` (no exploit provided).
   - Queue is sorted: Candidate 1 $\to$ Candidate 2 $\to$ Candidate 3 $\to$ Candidate 4.
5. **Execution & GAP-2 Pivoting**:
   - **Candidate 1 Dispatched**: Validator issues non-destructive HTTP check $\to$ HTTP 200, 3 signatures matched $\to$ **SUCCESS**. SHA-256 evidence hash recorded.
   - **Candidate 2 Dispatched**: Dispatched to Strix agent. Attempt 1 fails (CORS header reflective but credential access blocked). Attempt 2 fails (preflight rejected).
   - **GAP-2 Pivot Triggered**: Candidate 2 hits threshold $k=2$. Engine aborts Candidate 2, logs `REDIRECT`, and immediately pivots to Candidate 3.
6. **Audit Reporting**:
   - Compilation of comprehensive HTML, JSON, and SARIF reports detailing:
     - Executive summary, asset metadata, OWASP categories (`A01:2021`, `A05:2021`).
     - Cryptographic proof hashes and reproduction curl commands.
     - Decision trace with GAP-1 rankings and GAP-2 pivot logs.
     - Concrete remediation patches for Nginx and Apache.

---

## 6. Implementation Roadmap

### Phase 1: Gateway & Unified Web UI (Days 1–4)
- [ ] Mount AI-VAPT's `frontend/web/` into Strix's web viewer layer (`strix/interface/viewer/`).
- [ ] Implement FastAPI gateway routes in Strix combining assessment management with agent steering.
- [ ] Verify System Health dashboard reporting Ollama, Docker, LiteLLM, and Scanners.

### Phase 2: Dynamic Multi-Model Provider Router (Days 5–8)
- [ ] Extend Strix's LiteLLM integration to support runtime ephemeral headers (`X-Google-API-Key`, `X-OpenRouter-API-Key`).
- [ ] Add live model catalogue validation endpoints for OpenRouter and Google Gemini.
- [ ] Implement automatic model probing for local Ollama instances (`http://127.0.0.1:11434/api/tags`).

### Phase 3: GAP-1 Exploit Quality Engine (Days 9–13)
- [ ] Port `core/exploit_assessor.py` and `vapt_platform/assessment.py` into `strix/core/triage/`.
- [ ] Integrate OWASP Top-10 / CWE / CVE normalization into Strix finding parsers.
- [ ] Implement composite scoring function: $Score = f(Severity, Exposure, AIQuality)$.

### Phase 4: GAP-2 Dynamic Decision-Pivoting (Days 14–18)
- [ ] Integrate bounded attempt counter ($k$) into Strix's `AgentCoordinator` and `run_agent_loop`.
- [ ] Implement branch pruning and `REDIRECT` event emission upon reaching threshold $k$.
- [ ] Wire pivot events into the frontend WebSocket / SSE stream for real-time DAG rendering.

### Phase 5: Verification, Benchmarking & Mentor Documentation (Days 19–21)
- [ ] Run regression suite across synthetic benchmarks (`docker_pivot`, `failure_pivot`, `all_fail`).
- [ ] Execute comparative benchmark: Strix vanilla (unbounded turns) vs. Strix + GAP-1/2 (bounded pivots).
- [ ] Measure and report token cost reduction, time-to-first-compromise, and precision improvements.

---

## 7. Deliverables & File Placement Table

| Component | Source Path (`AI_VAPT`) | Destination Path in `STRIX` | Purpose |
| :--- | :--- | :--- | :--- |
| **Frontend Web Console** | `frontend/web/` | `strix/interface/web/` | Unified web console (UI, CSS, JS) |
| **API Service Gateway** | `services/api.py`, `schemas.py` | `strix/interface/api.py` | FastAPI assessment control & monitoring endpoints |
| **Model Router** | `vapt_platform/model_config.py`, `ollama_service.py` | `strix/llm/router.py` | Dynamic local/hosted model switching & in-memory keys |
| **GAP-1 Quality Assessor** | `core/exploit_assessor.py`, `vapt_platform/assessment.py` | `strix/core/gap1_assessor.py` | Quantitative exploit quality scoring & triage |
| **GAP-2 Decision Engine**| `decision_engine/core/` | `strix/core/gap2_pivoting.py` | Bounded threshold failure recovery & dynamic pivoting |
| **Scope Gatekeeper** | `vapt_platform/web_target.py`, `engagements.py` | `strix/core/scope_gatekeeper.py` | Fail-closed network validation & profile management |
| **Controlled Validators**| `vapt_platform/validators/` | `strix/tools/validators/` | Safe non-destructive verification & SHA-256 proof hashing |
| **Report Builder** | `vapt_platform/reporting/` | `strix/report/builder.py` | Audit-ready HTML, JSON, PDF & SARIF report generator |

---

## 8. Conclusion

By integrating **AI-VAPT**'s decision intelligence into **STRIX**, the platform evolves from an unconstrained agent harness into an **auditable, goal-driven, and resource-bounded autonomous penetration testing platform**. 

- **GAP-1** eliminates wasted time on non-functional exploits.
- **GAP-2** prevents catastrophic token drain by dynamically pivoting past defensive dead ends.
- The **Multi-Model Web Console** democratizes access, allowing security researchers to seamlessly command local or hosted AI models through an intuitive, real-time graphical interface.
