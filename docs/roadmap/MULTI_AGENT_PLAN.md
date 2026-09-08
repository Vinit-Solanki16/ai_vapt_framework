# Multi-Agent Development Plan

**Date:** 2026-09-08
**Purpose:** Guide implementation of future platform features using multiple AI coding agents

---

## Strategy

Break the future platform into atomic, independently-implementable features.
Each feature is implemented by a single AI coding agent with:
- Explicit scope (exact files to modify)
- Dependencies (features that must complete first)
- Acceptance criteria (what success looks like)
- Safety constraints

## Critical Rule

No two agents modify the same file simultaneously. The dependency graph
below defines a strict ordering that prevents conflicts.

---

## Agent Plan

### Agent-001: Nmap XML Parser Enhancement
- **Objective:** Extend existing Nmap XML parser for broader coverage
- **Dependencies:** None (standalone)
- **Exact Files:** `core/scanner.py`, `tests/test_nmap_parser.py`
- **Allowed Files:** `core/scanner.py`, `tests/test_nmap_parser.py`, `data/live_scan.xml`
- **Forbidden Files:** All others
- **Acceptance Criteria:**
  - Parse 95%+ of Nmap XML fields
  - Handle malformed XML gracefully
  - Unit tests pass (100% pass rate)
- **Tests:** `pytest tests/test_nmap_parser.py -q`
- **Safety:** Read-only parsing, no execution
- **Commit:** `feat: enhance Nmap XML parser`

---

### Agent-002: Nuclei JSON Parser
- **Objective:** Add Nuclei scan result parser
- **Dependencies:** None (standalone)
- **Exact Files:** `core/scanner.py` (add NucleiParser class), `tests/test_nuclei_parser.py`
- **Allowed Files:** `core/scanner.py`, `tests/test_nuclei_parser.py`
- **Forbidden Files:** All others
- **Acceptance Criteria:**
  - Parse Nuclei JSON output
  - Map to common Finding schema
  - Unit tests pass
- **Tests:** `pytest tests/test_nuclei_parser.py -q`
- **Safety:** Read-only parsing
- **Commit:** `feat: add Nuclei JSON parser`

---

### Agent-003: Finding Normalization Engine
- **Objective:** Build deduplication and normalization layer
- **Dependencies:** Agent-001, Agent-002
- **Exact Files:** `core/normalization.py`, `tests/test_normalization.py`
- **Allowed Files:** `core/normalization.py`, `tests/test_normalization.py`, `core/schemas.py`
- **Forbidden Files:** All others
- **Acceptance Criteria:**
  - Normalize Nmap + Nuclei findings to common schema
  - Deduplicate by CVE + target + port
  - Unit tests pass
- **Tests:** `pytest tests/test_normalization.py -q`
- **Safety:** Read-only transformation
- **Commit:** `feat: add finding normalization engine`

---

### Agent-004: Vulnerability Intelligence Enrichment
- **Objective:** Add EPSS, CVSS, CISA KEV enrichment
- **Dependencies:** Agent-003
- **Exact Files:** `core/enrichment.py`, `tests/test_enrichment.py`
- **Allowed Files:** `core/enrichment.py`, `tests/test_enrichment.py`, `datasets/cisa_kev.json`
- **Forbidden Files:** All others
- **Acceptance Criteria:**
  - Enrich findings with EPSS scores
  - Enrich with CVSS vectors
  - Enrich with CISA KEV status
  - Cache results to avoid repeated API calls
  - Unit tests pass
- **Tests:** `pytest tests/test_enrichment.py -q`
- **Safety:** Read-only API calls with caching
- **Commit:** `feat: add vulnerability intelligence enrichment`

---

### Agent-005: Asset/Vulnerability Graph Builder
- **Objective:** Build graph model of assets and vulnerabilities
- **Dependencies:** Agent-003, Agent-004
- **Exact Files:** `core/graph_builder.py`, `tests/test_graph_builder.py`
- **Allowed Files:** `core/graph_builder.py`, `tests/test_graph_builder.py`
- **Forbidden Files:** All others
- **Acceptance Criteria:**
  - Build graph from normalized findings
  - Support queries (e.g., "all critical vulns on host X")
  - Unit tests pass
- **Tests:** `pytest tests/test_graph_builder.py -q`
- **Safety:** Read-only analysis
- **Commit:** `feat: add asset/vulnerability graph builder`

---

### Agent-006: GUI Enhancement
- **Objective:** Improve Streamlit GUI with tables, colors, interactive elements
- **Dependencies:** None (standalone)
- **Exact Files:** `frontend/app.py`, `frontend/tests/test_frontend_smoke.py`
- **Allowed Files:** `frontend/app.py`, `frontend/tests/test_frontend_smoke.py`
- **Forbidden Files:** All others
- **Acceptance Criteria:**
  - Scenario selection dropdown
  - Candidate ranking table (styled)
  - Execution timeline visualization
  - Attempt counters
  - Pivot event markers
  - Evidence tier badge
  - Download buttons for reports
  - Frontend smoke tests pass
- **Tests:** `pytest frontend/tests/test_frontend_smoke.py -q`
- **Safety:** Display-only, no execution
- **Commit:** `feat: enhance Streamlit GUI`

---

### Agent-007: Report Enhancement
- **Objective:** Add PDF, HTML, markdown export to reports
- **Dependencies:** None (standalone)
- **Exact Files:** `prototype/report_generator.py`, `prototype/tests/test_report.py`
- **Allowed Files:** `prototype/report_generator.py`, `prototype/tests/test_report.py`
- **Forbidden Files:** All others
- **Acceptance Criteria:**
  - JSON report (existing, keep)
  - Text report (existing, keep)
  - HTML report (new)
  - Markdown report (new)
  - Unit tests pass
- **Tests:** `pytest prototype/tests/test_report.py -q`
- **Safety:** File generation only
- **Commit:** `feat: add HTML/Markdown report export`

---

## Dependency Graph

```
Agent-001 ──┐
             ├──→ Agent-003 ──→ Agent-004 ──→ Agent-005
Agent-002 ──┘

Agent-006 (standalone)
Agent-007 (standalone)
```

## Parallel Execution

Agents 001, 002, 006, 007 can run in parallel (no shared files).
Agent-003 requires both 001 and 002.
Agent-004 requires Agent-003.
Agent-005 requires both 003 and 004.

## Acceptance Gate

After each agent completes:
1. Run full test suite: `pytest -q`
2. All tests must pass (100%)
3. No new security issues introduced
4. Documentation updated

## Commit Protocol

Each agent creates exactly one commit:
- Descriptive message matching the acceptance criteria
- No unrelated changes
- Atomic (one logical unit of work)

---

*Document prepared by Hermes Agent — 2026-09-08*
