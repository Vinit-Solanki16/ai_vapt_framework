# Future Full Platform Roadmap

**Date:** 2026-09-08
**Status:** Planning only — DO NOT IMPLEMENT during prototype phase

---

## F1 — Real Scan Ingestion

**Objective:** Ingest real vulnerability scan outputs and normalize them into the engine's ActionCandidate format.

**Components:**
- Nmap XML parser (`core/scanner.py` exists, needs enhancement)
- Nuclei JSON parser
- Web recon output parser (ffuf, dirsearch, etc.)
- Safe parsers with input validation and size limits

**Dependencies:** None (standalone)

**Acceptance Criteria:**
- Parse Nmap XML with at least 95% field coverage
- Parse Nuclei JSON with template ID, severity, target
- All parsers reject malformed input gracefully
- Unit tests for each parser

---

## F2 — Finding Normalization

**Objective:** Normalize findings from multiple scan sources into a common schema.

**Components:**
- Common finding schema (extends existing `ActionCandidate`)
- Deduplication engine (by CVE + target + port)
- Asset identification (IP, hostname, service fingerprint)

**Dependencies:** F1

**Acceptance Criteria:**
- Findings from Nmap and Nuclei map to common schema
- Duplicate findings are merged (same CVE + target)
- Asset inventory is generated from scan data

---

## F3 — Vulnerability Intelligence

**Objective:** Enrich findings with external vulnerability intelligence.

**Components:**
- EPSS score lookup (already partially implemented)
- CVSS vector parsing and score calculation
- CPE matching for asset identification
- CVE metadata enrichment (description, references, dates)
- CISA KEV integration (already have `datasets/cisa_kev.json`)

**Dependencies:** F2

**Acceptance Criteria:**
- Each finding is enriched with EPSS, CVSS, CISA KEV status
- Enrichment is cached to avoid repeated API calls
- Graceful fallback when enrichment sources are unavailable

---

## F4 — Asset/Vulnerability Graph

**Objective:** Build a graph model of assets and their vulnerabilities.

**Components:**
- Graph data structure (NetworkX or similar)
- Asset nodes (hosts, services, applications)
- Vulnerability nodes (CVEs, misconfigurations)
- Edge relationships (has_vulnerability, depends_on, communicates_with)
- Graph visualization (interactive or static)

**Dependencies:** F2, F3

**Acceptance Criteria:**
- Graph is built from normalized + enriched findings
- Graph can be queried (e.g., "all critical vulns on host X")
- Visualization renders without errors

---

## F5 — Advanced Decision Intelligence

**Objective:** Enhance the decision engine with contextual decision-making.

**Components:**
- Contextual candidate generation (chain vulnerabilities)
- Multi-factor prioritization (not just EPSS × quality)
- Attack path simulation
- Risk-based threshold adjustment

**Dependencies:** F4

**Acceptance Criteria:**
- Candidates can be generated from attack paths
- Prioritization considers asset criticality
- Threshold adapts based on risk context

---

## F6 — Multi-Agent Architecture

**Objective:** Implement a multi-agent system with Planner, Executor, and Verifier roles.

**Components:**
- Planner agent (generates attack plans)
- Executor agent (executes planned actions)
- Verifier agent (validates results)
- Inter-agent communication protocol
- Controlled orchestration (no autonomous real-world targeting)

**Dependencies:** F5

**Acceptance Criteria:**
- Three agents communicate via defined protocol
- Planner generates valid attack plans
- Executor runs plans within safety bounds
- Verifier confirms or rejects results
- All inter-agent messages are logged

---

## F7 — Validation

**Objective:** Validate findings through controlled execution.

**Components:**
- Safe PoC execution framework
- Result parsing and confirmation
- False positive detection
- Evidence collection (screenshots, response data)

**Dependencies:** F6

**Acceptance Criteria:**
- PoCs run in isolated environment (Docker)
- Results are parsed and classified
- False positives are flagged
- Evidence is collected and stored

---

## F8 — AI-Assisted Reporting

**Objective:** Generate human-readable reports with AI assistance.

**Components:**
- Report template engine
- LLM-powered narrative generation
- Executive summary generation
- Technical detail formatting
- Remediation recommendation engine

**Dependencies:** F7

**Acceptance Criteria:**
- Reports include executive summary
- Technical details are accurate
- Remediation recommendations are relevant
- Reports export to PDF, JSON, HTML

---

## F9 — Full GUI/Dashboard

**Objective:** Build a comprehensive dashboard for VAPT operations.

**Components:**
- Real-time scan monitoring
- Interactive vulnerability explorer
- Attack path visualization
- Report builder
- User management and access control

**Dependencies:** F4, F8

**Acceptance Criteria:**
- Dashboard shows live scan status
- Vulnerabilities are explorable and filterable
- Attack paths are visualized
- Reports can be generated from dashboard

---

## F10 — Authorized Real-Environment Integration

**Objective:** Integrate with authorized real-world environments.

**Components:**
- Authorization verification system
- Target scope enforcement
- Rate limiting and throttling
- Audit logging
- Compliance reporting

**Dependencies:** F6, F9

**Acceptance Criteria:**
- Only authorized targets are scanned
- Scope is enforced (no out-of-bounds scanning)
- All actions are audit-logged
- Compliance reports are generated

---

## Dependency Graph

```
F1 → F2 → F3 → F4 → F5 → F6 → F7 → F8 → F9 → F10
```

Each phase depends on the previous. No phase should be started before
its predecessor is complete and tested.

---

## Safety Constraints (All Phases)

1. **Authorization required** — No scanning without explicit written authorization
2. **Scope enforcement** — Only targets within scope are contacted
3. **Rate limiting** — No aggressive scanning that could cause denial of service
4. **Isolation** — All execution in Docker-isolated environments
5. **Audit logging** — All actions are logged and traceable
6. **Fail-closed** — Any safety violation stops all operations
7. **No autonomous real-world targeting** — Human approval required for all real targets

---

*Document prepared by Hermes Agent — 2026-09-08*
