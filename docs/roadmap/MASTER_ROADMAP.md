# AI VAPT Platform — Master Development Roadmap

**Date:** 2026-09-11
**Branch:** prototype-development
**Current HEAD:** ab87e57 (M6 Professional GUI)
**Tests:** 415 passed, 7 skipped

---

## Current State Summary

| Component | Status | Location |
|-----------|--------|----------|
| Research engine (Gap-2) | FROZEN | `decision_engine/core/` |
| Canonical normalization (M2) | COMPLETE | `vapt_platform/normalization.py` |
| AI assessment bridge (M3) | COMPLETE | `vapt_platform/assessment.py` |
| Docker real execution (M4) | COMPLETE | `prototype/execution_layer.py` |
| Unified application workflow (M5) | COMPLETE | `vapt_platform/application.py` |
| Professional GUI (M6) | COMPLETE | `frontend/app.py` |
| Vulnerability intelligence | EXISTS, NOT INTEGRATED | `vapt_platform/enrichment.py` |
| Asset/vulnerability graph | EXISTS, NOT INTEGRATED | `vapt_platform/graph_builder.py` |
| Authorization framework | EXISTS, NOT INTEGRATED | `vapt_platform/authorization.py` |
| Multi-agent orchestration | EXISTS, NOT INTEGRATED | `vapt_platform/orchestration.py` |

---

## Dependency-Aware Wave Plan

### WAVE 1 — Vulnerability Intelligence Integration
**Goal:** Connect existing enrichment layer to canonical workflow

Tasks:
1. Audit existing `enrichment.py` — verify CISA KEV, EPSS, CVSS, CWE support
2. Integrate enrichment into `VAPTApplication.run()` pipeline
3. Add provider abstraction for future NVD/live sources
4. Add caching, timeout, graceful failure
5. Add fixture-based tests
6. Prove: `canonical finding → enrichment → enriched finding → candidate`

**Files:** `vapt_platform/enrichment.py`, `vapt_platform/application.py`, `tests/test_enrichment.py`

### WAVE 2 — Asset/Vulnerability Model Integration
**Goal:** Connect existing graph builder to workflow

Tasks:
1. Audit existing `graph_builder.py`
2. Integrate into `VAPTApplication.run()` pipeline
3. Add asset identity resolution
4. Add graph queries for candidate prioritization
5. Prove: `scan → asset model → vulnerability model → candidate`

**Files:** `vapt_platform/graph_builder.py`, `vapt_platform/application.py`, `tests/test_graph.py`

### WAVE 3 — Decision Intelligence
**Goal:** Transparent scoring using enriched data

Tasks:
1. Build scoring model using EPSS, CVSS, KEV, asset exposure
2. Keep Gap-2 mechanism unchanged
3. Add explainability to scoring
4. Prove: `enriched finding → ranked candidates → explainable decision`

**Files:** `vapt_platform/decision_intelligence.py`, `tests/test_decision.py`

### WAVE 4 — Recon/Scanner Integration
**Goal:** Connect real scanner outputs to workflow

Tasks:
1. Verify existing Nmap/Nuclei parsers
2. Add scanner adapter abstraction
3. Integrate into workflow
4. Prove: `scan file → parser → canonical finding → enrichment → candidate`

**Files:** `vapt_platform/parsers/`, `vapt_platform/application.py`

### WAVE 5 — Controlled Validation Pipeline
**Goal:** Planner → Safety Gate → Executor → Verifier → Evidence

Tasks:
1. Build planner using enriched context
2. Build safety gate using authorization framework
3. Build verifier for observed vs expected
4. Prove: `candidate → plan → safety validation → execution → verification → evidence`

**Files:** `vapt_platform/pipeline.py`, `vapt_platform/authorization.py`

### WAVE 6 — Professional Reporting
**Goal:** Comprehensive report generation

Tasks:
1. Build report generator with all sections
2. Support JSON, Markdown, HTML, PDF
3. Add provenance tracking
4. Prove: `run → comprehensive report`

**Files:** `vapt_platform/reporting.py`, `prototype/report_generator.py`

### WAVE 7 — GUI V2
**Goal:** Operational dashboard

Tasks:
1. Add views: Targets, Scans, Findings, Vulnerabilities, Candidates
2. Add run history, filtering, visualization
3. Prove: `GUI → full operational workflow`

**Files:** `frontend/app.py`

### WAVE 8 — Multi-Agent Orchestration
**Goal:** Coordinated agents with narrow responsibilities

Tasks:
1. Evaluate LangGraph vs existing orchestration
2. Build agents: Recon, Analysis, Intelligence, Planning, Validation
3. Prove: `multi-agent workflow → coordinated output`

**Files:** `vapt_platform/orchestration.py`

### WAVE 9 — Authorized Real-Environment Integration
**Goal:** Explicit authorization for external targets

Tasks:
1. Build authorization configuration
2. Add scope validation
3. Add audit logging
4. Prove: `authorized target → scoped execution → audit trail`

**Files:** `vapt_platform/authorization.py`

### WAVE 10 — Hardening/Release
**Goal:** Full system audit and hardening

Tasks:
1. Security audit
2. Error handling review
3. Concurrency review
4. Full regression suite
5. Manual end-to-end demos

---

## Agent Ownership Boundaries

| Agent | Owned Files | Forbidden Files |
|-------|-------------|-----------------|
| Wave 1 (Intelligence) | `vapt_platform/enrichment.py`, `tests/test_enrichment.py` | `decision_engine/core/`, `core/` |
| Wave 2 (Graph) | `vapt_platform/graph_builder.py`, `tests/test_graph.py` | `decision_engine/core/`, `core/` |
| Wave 3 (Decision) | `vapt_platform/decision_intelligence.py` | `decision_engine/core/`, `core/` |
| Wave 4 (Scanners) | `vapt_platform/parsers/` | `decision_engine/core/`, `core/` |
| Wave 5 (Pipeline) | `vapt_platform/pipeline.py` | `decision_engine/core/`, `core/` |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Enrichment dataset missing | Graceful fallback to no enrichment |
| Graph complexity | Start minimal, extend later |
| Agent conflicts | Sequential waves, not parallel |
| Safety weakening | All changes reviewed against safety model |

---

*This is a living document. Updated after each wave.*
