# Full Platform Agent Plan

**Date:** 2026-09-08
**Status:** Planning only

---

## Strategy

Break the future platform into atomic, independently-implementable features.
Each agent has:
- Explicit scope (exact files to modify)
- Dependencies (features that must complete first)
- Acceptance criteria (what success looks like)
- Safety constraints

## Critical Rule

No two agents modify the same file in the same execution wave.

---

## Wave 1: Foundation (Can Run in Parallel)

### Agent-A1: Scan Ingestion Integration

**Role:** Integration engineer
**Objective:** Wire existing Nmap parser to CLI for scan file input
**Why it exists:** Prove that real scan output can flow through the entire pipeline
**Dependencies:** None (all components exist)

**Files to inspect:**
- `prototype/cli.py` — Understand current CLI structure
- `prototype/engine_integration.py` — Understand engine wrapper
- `decision_engine/adapters/scan_adapter.py` — Understand existing bridge
- `core/scanner.py` — Understand existing parser

**Allowed files:**
- `prototype/cli.py`
- `prototype/engine_integration.py`

**Forbidden files:**
- `decision_engine/core/` (research protected)
- `decision_engine/benchmarks/` (research protected)
- `core/scanner.py` (already works, don't touch)
- `decision_engine/adapters/scan_adapter.py` (already works, don't touch)
- `frontend/app.py` (GUI not needed yet)
- `prototype/report_generator.py` (already works)

**Acceptance Criteria:**
- `python -m prototype.cli run --scan data/live_scan.xml --max-attempts 2` works
- CLI detects scan file vs scenario name automatically
- Report is generated with correct candidates from scan
- All 195 existing tests still pass

**Tests:**
- `pytest prototype/tests/test_integration.py -q`
- Manual: `python -m prototype.cli run --scan data/live_scan.xml --max-attempts 2`

**Safety requirements:**
- Read-only scan ingestion
- No external scanning
- No modification to research engine

**Research integrity requirements:**
- Do not modify any file in `decision_engine/core/`
- Do not modify any file in `decision_engine/benchmarks/`
- Do not modify evidence tier labels

**Git commit requirement:** `feat: add scan file ingestion to CLI`

**Stop conditions:**
- If scan file parsing fails, stop and report
- If engine behavior changes, stop and report
- If any existing test fails, stop and fix

---

### Agent-A2: Nuclei JSON Parser

**Role:** Parser engineer
**Objective:** Add Nuclei scan output parser as a new module
**Why it exists:** Support Nuclei scanner users
**Dependencies:** None (standalone new module)

**Files to inspect:**
- `decision_engine/adapters/scan_adapter.py` — Understand candidate conversion
- `decision_engine/core/schemas.py` — Understand ActionCandidate schema

**Allowed files:**
- `platform/parsers/__init__.py` (new)
- `platform/parsers/nuclei_parser.py` (new)
- `tests/test_nuclei_parser.py` (new)
- `data/sample_nuclei.json` (new test fixture)

**Forbidden files:**
- All existing files (this is a new module)
- `decision_engine/core/` (research protected)
- `core/scanner.py` (don't modify existing scanner)

**Acceptance Criteria:**
- Parse Nuclei JSON with template ID, severity, target, CVE
- Map to ActionCandidate format
- Unit tests pass with 100% pass rate
- Sample Nuclei file parses correctly

**Tests:**
- `pytest tests/test_nuclei_parser.py -q`

**Safety requirements:**
- Read-only parsing
- No execution

**Research integrity requirements:**
- None (new module, doesn't touch research code)

**Git commit requirement:** `feat: add Nuclei JSON parser`

**Stop conditions:**
- If parser fails on sample data, stop and report
- If tests fail, stop and fix

---

## Wave 2: Normalization (After Wave 1)

### Agent-B1: Finding Normalization Engine

**Role:** Data engineer
**Objective:** Build normalization layer for scan findings
**Why it exists:** Unify Nmap + Nuclei output into common format
**Dependencies:** Agent-A1, Agent-A2

**Files to inspect:**
- `platform/parsers/nuclei_parser.py` — Understand Nuclei output format
- `core/scanner.py` — Understand Nmap output format
- `decision_engine/adapters/scan_adapter.py` — Understand candidate conversion

**Allowed files:**
- `platform/normalization.py` (new)
- `tests/test_normalization.py` (new)

**Forbidden files:**
- `decision_engine/core/` (research protected)
- `decision_engine/adapters/` (don't modify adapters)
- `core/scanner.py` (don't modify existing scanner)
- `platform/parsers/nuclei_parser.py` (don't modify parser)

**Acceptance Criteria:**
- Nmap + Nuclei findings normalize to common format
- Deduplication by CVE + host + port
- Asset identification from findings
- Unit tests pass

**Tests:**
- `pytest tests/test_normalization.py -q`

**Safety requirements:**
- Read-only transformation

**Research integrity requirements:**
- None (new module)

**Git commit requirement:** `feat: add finding normalization engine`

**Stop conditions:**
- If normalization loses data, stop and report
- If tests fail, stop and fix

---

## Wave 3: Enrichment (After Wave 2)

### Agent-B2: Vulnerability Intelligence Enrichment

**Role:** Enrichment engineer
**Objective:** Add CVSS, CISA KEV enrichment
**Why it exists:** Enhance findings with threat intelligence
**Dependencies:** Agent-B1

**Files to inspect:**
- `core/scanner.py:fetch_epss_score()` — Understand existing EPSS pattern
- `datasets/cisa_kev.json` — Understand CISA KEV data format
- `datasets/epss_corpus_enrichment.json` — Understand EPSS data format
- `platform/normalization.py` — Understand normalized finding format

**Allowed files:**
- `platform/enrichment.py` (new)
- `tests/test_enrichment.py` (new)

**Forbidden files:**
- `decision_engine/core/` (research protected)
- `core/scanner.py` (don't modify existing EPSS code)

**Acceptance Criteria:**
- Enrich findings with CVSS scores
- Enrich with CISA KEV status
- Cache results to avoid repeated API calls
- Graceful fallback when sources unavailable
- Unit tests pass

**Tests:**
- `pytest tests/test_enrichment.py -q`

**Safety requirements:**
- Read-only API calls with caching

**Research integrity requirements:**
- None (new module)

**Git commit requirement:** `feat: add vulnerability intelligence enrichment`

**Stop conditions:**
- If enrichment fails, stop and report
- If tests fail, stop and fix

---

## Wave 4: Graph (After Wave 3)

### Agent-C1: Asset/Vulnerability Graph Builder

**Role:** Graph engineer
**Objective:** Build graph model of assets and vulnerabilities
**Why it exists:** Visualize relationships between assets and vulns
**Dependencies:** Agent-B1, Agent-B2

**Files to inspect:**
- `platform/normalization.py` — Understand normalized finding format
- `platform/enrichment.py` — Understand enriched finding format

**Allowed files:**
- `platform/graph_builder.py` (new)
- `tests/test_graph_builder.py` (new)

**Forbidden files:**
- `decision_engine/core/` (research protected)
- `platform/normalization.py` (don't modify)
- `platform/enrichment.py` (don't modify)

**Acceptance Criteria:**
- Graph is built from normalized + enriched findings
- Graph can be queried (e.g., "all critical vulns on host X")
- Visualization renders without errors
- Unit tests pass

**Tests:**
- `pytest tests/test_graph_builder.py -q`

**Safety requirements:**
- Read-only analysis

**Research integrity requirements:**
- None (new module)

**Git commit requirement:** `feat: add asset/vulnerability graph builder`

**Stop conditions:**
- If graph construction fails, stop and report
- If tests fail, stop and fix

---

## Wave 5: Integration (After Wave 4)

### Agent-D1: GUI Enhancement

**Role:** Frontend engineer
**Objective:** Update GUI to support full platform workflow
**Why it exists:** Enable users to use full platform via GUI
**Dependencies:** Agent-C1 (graph must exist for visualization)

**Files to inspect:**
- `frontend/app.py` — Understand current GUI structure
- `prototype/engine_integration.py` — Understand engine wrapper

**Allowed files:**
- `frontend/app.py`
- `frontend/tests/test_frontend_smoke.py`

**Forbidden files:**
- `decision_engine/core/` (research protected)
- `prototype/report_generator.py` (don't modify reports yet)

**Acceptance Criteria:**
- Upload scan file in GUI
- View normalized findings
- View asset/vulnerability graph
- Run decision engine on scan results
- Frontend smoke tests pass

**Tests:**
- `pytest frontend/tests/test_frontend_smoke.py -q`

**Safety requirements:**
- Display only

**Research integrity requirements:**
- None

**Git commit requirement:** `feat: enhance Streamlit GUI for full platform`

**Stop conditions:**
- If GUI breaks, stop and report
- If tests fail, stop and fix

---

### Agent-D2: Report Enhancement

**Role:** Reporting engineer
**Objective:** Add HTML/Markdown export to reports
**Why it exists:** Provide more report formats
**Dependencies:** None (standalone)

**Files to inspect:**
- `prototype/report_generator.py` — Understand current report structure

**Allowed files:**
- `prototype/report_generator.py`
- `prototype/tests/test_report.py`

**Forbidden files:**
- `decision_engine/core/` (research protected)

**Acceptance Criteria:**
- HTML report export
- Markdown report export
- Executive summary section
- Unit tests pass

**Tests:**
- `pytest prototype/tests/test_report.py -q`

**Safety requirements:**
- File generation only

**Research integrity requirements:**
- None

**Git commit requirement:** `feat: add HTML/Markdown report export`

**Stop conditions:**
- If report generation fails, stop and report
- If tests fail, stop and fix

---

## Wave 6: Multi-Agent Orchestration (Future)

### Agent-E1: Planner Agent

**Role:** Agent architect
**Objective:** Implement Planner agent for attack path planning
**Why it exists:** Coordinate multi-step attack paths
**Dependencies:** Agent-C1 (graph must exist for planning)

**Note:** This is future work. Only implement when multi-agent
orchestration is actually needed.

---

### Agent-E2: Executor Agent

**Role:** Agent architect
**Objective:** Implement Executor agent for plan execution
**Why it exists:** Execute planned actions
**Dependencies:** Agent-E1

**Note:** This is future work.

---

### Agent-E3: Verifier Agent

**Role:** Agent architect
**Objective:** Implement Verifier agent for result validation
**Why it exists:** Validate execution results
**Dependencies:** Agent-E1, Agent-E2

**Note:** This is future work.

---

## Agent Dependency Graph

```
Wave 1 (Parallel):
  Agent-A1 (Scan Ingestion)  ──┐
                               ├──→ Wave 2
  Agent-A2 (Nuclei Parser)   ──┘

Wave 2:
  Agent-B1 (Normalization) ──→ Wave 3

Wave 3:
  Agent-B2 (Enrichment) ──→ Wave 4

Wave 4:
  Agent-C1 (Graph) ──→ Wave 5

Wave 5 (Parallel):
  Agent-D1 (GUI)  ──┐
                    ├──→ Wave 6 (Future)
  Agent-D2 (Reports)──┘

Wave 6 (Future):
  Agent-E1 (Planner) ──→ Agent-E2 (Executor) ──→ Agent-E3 (Verifier)
```

## File Ownership Matrix

| File | Agent | Wave |
|------|-------|------|
| `prototype/cli.py` | Agent-A1 | 1 |
| `prototype/engine_integration.py` | Agent-A1 | 1 |
| `platform/parsers/__init__.py` | Agent-A2 | 1 |
| `platform/parsers/nuclei_parser.py` | Agent-A2 | 1 |
| `tests/test_nuclei_parser.py` | Agent-A2 | 1 |
| `platform/normalization.py` | Agent-B1 | 2 |
| `tests/test_normalization.py` | Agent-B1 | 2 |
| `platform/enrichment.py` | Agent-B2 | 3 |
| `tests/test_enrichment.py` | Agent-B2 | 3 |
| `platform/graph_builder.py` | Agent-C1 | 4 |
| `tests/test_graph_builder.py` | Agent-C1 | 4 |
| `frontend/app.py` | Agent-D1 | 5 |
| `frontend/tests/test_frontend_smoke.py` | Agent-D1 | 5 |
| `prototype/report_generator.py` | Agent-D2 | 5 |
| `prototype/tests/test_report.py` | Agent-D2 | 5 |

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
