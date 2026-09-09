# Full Platform Milestones

**Date:** 2026-09-08
**Status:** Planning only

---

## Milestone 0: Prototype (COMPLETE)

**Status:** DONE

**What was delivered:**
- Working research prototype with 195 passing tests
- CLI, GUI, API interfaces
- 7 deterministic demo scenarios
- Safety model with allowlist + fail-closed
- Research contribution: Gap-2 bounded failure-driven pivoting

---

## Milestone 1: Scan Ingestion Vertical Slice

**Goal:** Prove that real scan output can flow through the entire pipeline.

**User-visible capability:**
```bash
# Ingest a real Nmap scan and run the decision engine on it
python -m prototype.cli run --scan data/live_scan.xml --max-attempts 2
```

**What this milestone delivers:**
1. Reuse existing Nmap XML parser (`core/scanner.py`)
2. Reuse existing scan adapter (`decision_engine/adapters/scan_adapter.py`)
3. Add CLI `--scan` flag to pass scan files
4. Generate report from scan-based run
5. End-to-end test: scan file → candidates → engine → report

**Dependencies:** None (all components exist)

**Files to modify:**
- `prototype/cli.py` — Add `--scan` argument
- `prototype/engine_integration.py` — Add scan-to-candidates path

**Files to create:**
- `tests/test_scan_e2e.py` — End-to-end scan ingestion tests

**Files NOT touched:**
- `decision_engine/core/` — Research protected
- `core/scanner.py` — Already works, no changes needed
- `decision_engine/adapters/scan_adapter.py` — Already works

**Acceptance Criteria:**
- `python -m prototype.cli run --scan data/live_scan.xml --max-attempts 2` works
- Report is generated with correct candidates from scan
- All 195 existing tests still pass
- New E2E test passes

**Safety:** Read-only scan ingestion, no external scanning

**Definition of Done:**
- CLI can accept scan files
- Scan findings become candidates
- Engine processes candidates
- Report is generated
- Tests pass

---

## Milestone 2: Nuclei JSON Parser

**Goal:** Add Nuclei scan output support.

**User-visible capability:**
```bash
python -m prototype.cli run --scan results_nuclei.json --max-attempts 2
```

**What this milestone delivers:**
1. New Nuclei JSON parser module
2. Integration into scan ingestion pipeline
3. Tests with sample Nuclei output

**Dependencies:** Milestone 1

**Files to create:**
- `platform/parsers/__init__.py`
- `platform/parsers/nuclei_parser.py`
- `tests/test_nuclei_parser.py`
- `data/sample_nuclei.json` — Sample Nuclei output for testing

**Files to modify:**
- `prototype/cli.py` — Already supports --scan, may need format detection
- `prototype/engine_integration.py` — Add Nuclei format handling

**Files NOT touched:**
- `decision_engine/core/` — Research protected
- `core/scanner.py` — Not modified (separate parser)

**Acceptance Criteria:**
- Parse Nuclei JSON with template ID, severity, target, CVE
- Map to ActionCandidate format via existing scan_adapter
- Unit tests pass with 100% pass rate
- All existing tests still pass

**Safety:** Read-only parsing, no execution

**Definition of Done:**
- Nuclei parser module exists
- Sample Nuclei file parses correctly
- Candidates flow through engine
- Tests pass

---

## Milestone 3: Finding Normalization

**Goal:** Normalize findings from multiple scan sources into a common format.

**What this milestone delivers:**
1. Canonical finding format (extends existing Finding)
2. Deduplication by CVE + host + port
3. Asset identification

**Dependencies:** Milestone 2

**Files to create:**
- `platform/normalization.py`
- `tests/test_normalization.py`

**Files to modify:**
- `prototype/engine_integration.py` — Use normalization layer

**Files NOT touched:**
- `decision_engine/core/` — Research protected
- `decision_engine/adapters/` — Not modified

**Acceptance Criteria:**
- Nmap + Nuclei findings normalize to common format
- Duplicates are merged
- Asset inventory is generated
- Unit tests pass

**Safety:** Read-only transformation

**Definition of Done:**
- Normalization module exists
- Multiple scan sources produce consistent output
- Deduplication works
- Tests pass

---

## Milestone 4: Vulnerability Intelligence Enrichment

**Goal:** Enrich findings with external vulnerability intelligence.

**What this milestone delivers:**
1. CVSS vector parsing and score calculation
2. CISA KEV integration (already have dataset)
3. CVE metadata enrichment
4. Caching to avoid repeated API calls

**Dependencies:** Milestone 3

**Files to create:**
- `platform/enrichment.py`
- `tests/test_enrichment.py`

**Files to modify:**
- `prototype/engine_integration.py` — Use enrichment layer

**Files NOT touched:**
- `decision_engine/core/` — Research protected
- `core/scanner.py` — EPSS enrichment already exists, don't duplicate

**Acceptance Criteria:**
- Findings enriched with CVSS, CISA KEV status
- Enrichment is cached
- Graceful fallback when sources unavailable
- Unit tests pass

**Safety:** Read-only API calls with caching

**Definition of Done:**
- Enrichment module exists
- CVSS scores are calculated
- CISA KEV status is attached
- Tests pass

---

## Milestone 5: Asset/Vulnerability Graph

**Goal:** Build a graph model of assets and their vulnerabilities.

**Dependencies:** Milestone 4

**Files to create:**
- `platform/graph_builder.py`
- `tests/test_graph_builder.py`

**Files NOT touched:**
- `decision_engine/core/` — Research protected

**Acceptance Criteria:**
- Graph is built from normalized + enriched findings
- Graph can be queried
- Visualization renders

**Safety:** Read-only analysis

---

## Milestone 6: Enhanced GUI

**Goal:** Update GUI to support scan ingestion workflow.

**Dependencies:** Milestone 1 (scan ingestion must work first)

**Files to modify:**
- `frontend/app.py` — Add scan file upload, display graph

**Acceptance Criteria:**
- Upload scan file in GUI
- View normalized findings
- View asset/vulnerability graph
- Run decision engine on scan results

**Safety:** Display only

---

## Milestone 7: Enhanced Reporting

**Goal:** Add HTML/Markdown export and AI-assisted narratives.

**Dependencies:** Milestone 1

**Files to modify:**
- `prototype/report_generator.py` — Add HTML/Markdown templates

**Files to create:**
- `platform/ai_narrative.py` — LLM-powered report narratives (future)

**Acceptance Criteria:**
- HTML report export
- Markdown report export
- Executive summary section

**Safety:** File generation only

---

## Milestone 8: Multi-Agent Orchestration (Future)

**Goal:** Implement Planner/Executor/Verifier multi-agent system.

**Dependencies:** Milestone 5 (graph must exist for planning)

**Rationale:** Multi-agent becomes valuable when:
- Multiple scan sources need coordinated analysis
- Attack paths need to be planned across assets
- Verification needs to be independent of execution

**This is NOT needed for scan ingestion or basic platform functionality.**

---

## Milestone 9: Authorized Real-Environment Integration (Future)

**Goal:** Support authorized real-world target validation.

**Dependencies:** Milestone 8

**Safety requirements:**
- Explicit authorization verification
- Target scope enforcement
- Rate limiting
- Full audit logging
- Human approval for each target

---

## Milestone 10: Full Platform Integration (Future)

**Goal:** Complete end-to-end platform with all features integrated.

**Dependencies:** All previous milestones

---

## Dependency Graph

```
M0 (Prototype) ──→ M1 (Scan Ingestion) ──→ M2 (Nuclei Parser)
                                           │
                                           ↓
                              M3 (Normalization)
                                           │
                                           ↓
                              M4 (Enrichment)
                                           │
                                           ↓
                              M5 (Graph)
                                           │
                              ┌────────────┴────────────┐
                              ↓                         ↓
                         M6 (GUI)                M7 (Reporting)
                              │                         │
                              └────────────┬────────────┘
                                           ↓
                              M8 (Multi-Agent)
                                           │
                                           ↓
                              M9 (Real Environment)
                                           │
                                           ↓
                              M10 (Full Platform)
```

## Parallelization Opportunities

- M6 (GUI) and M7 (Reporting) can run in parallel after M5
- M2 (Nuclei) can start before M1 completes if file ownership is separate
- M3 (Normalization) and M4 (Enrichment) can be developed in parallel if they don't share files

---

*Document prepared by Hermes Agent — 2026-09-08*
