# Future Development Plan

**Date:** 2026-09-09
**Current Milestone:** M2 Complete
**Next Milestone:** M3 (Vulnerability Intelligence)

---

## Current State

| Component | Status |
|-----------|--------|
| Research engine (Gap-1 + Gap-2) | COMPLETE & FROZEN |
| Mentor prototype | COMPLETE |
| Wave 1 (Scan ingestion) | COMPLETE |
| M2 (Canonical normalization) | COMPLETE |
| Tests | 290 passed, 7 skipped |

---

## Development Roadmap

### M3 — Vulnerability Intelligence (NEXT)

**Goal:** Enrich canonical findings with external threat intelligence.

```
Canonical Finding
       ↓
   EPSS (already exists)
   CVSS
   CPE
   CISA KEV
       ↓
Enriched Finding
```

**Tasks:**
1. Reuse existing EPSS code from core/scanner.py
2. Add CVSS score extraction from Nuclei/classification data
3. Add CPE normalization
4. Add CISA KEV cross-reference
5. Severity harmonization across sources

**Files to modify:**
- `vapt_platform/enrichment.py` (NEW)
- `tests/test_enrichment.py` (NEW)

**Acceptance:**
- Canonical findings can be enriched with CVSS/EPSS/CPE/KEV
- Existing EPSS code is reused (not duplicated)
- Severity is harmonized across sources
- Tests pass

**Estimated effort:** 2-3 days

---

### M4 — Asset/Vulnerability Graph

**Goal:** Model assets, services, and vulnerabilities as a graph.

```
Assets
  │
  ├── services
  │
  ├── ports
  │
  └── vulnerabilities
          │
          └── candidates
```

**Tasks:**
1. Define asset identity from scan data
2. Service-to-asset mapping
3. Vulnerability clustering
4. Basic graph traversal
5. Graph-based prioritization

**Files to modify:**
- `vapt_platform/graph.py` (NEW)
- `tests/test_graph.py` (NEW)

**Acceptance:**
- Assets are uniquely identified
- Services map to assets
- Vulnerabilities cluster by asset
- Graph traversal works

**Estimated effort:** 3-5 days

---

### M5 — Enhanced Decision Intelligence

**Goal:** Feed enriched, graph-aware data into the decision engine.

**Tasks:**
1. Priority scoring with enriched data
2. Context-aware pivoting
3. Asset-criticality weighting
4. Multi-candidate strategies

**Acceptance:**
- Priority scores use enriched data
- Pivoting considers asset criticality
- Tests pass

**Estimated effort:** 3-5 days

---

### M6 — GUI & Reporting Polish

**Goal:** Professional-quality interface and reports.

**Tasks:**
1. Interactive workflow
2. Decision timeline visualization
3. Graph visualization
4. PDF/HTML reports
5. Mentor demo mode

**Acceptance:**
- GUI is professional and intuitive
- Reports are exportable
- Demo mode works smoothly

**Estimated effort:** 3-5 days

---

### M7 — Multi-Agent Orchestration (FUTURE)

**Goal:** Planner/Executor/Verifier architecture.

**Tasks:**
1. Planner agent (strategy)
2. Executor agent (tool execution)
3. Verifier agent (validation)
4. Inter-agent communication

**Acceptance:**
- Multi-agent workflow functions
- Agents coordinate on tasks
- Tests pass

**Estimated effort:** 5-7 days

---

## Timeline

| Phase | Duration | Status |
|-------|----------|--------|
| M1 | DONE | ✅ |
| M2 | DONE | ✅ |
| M3 | 2-3 days | NEXT |
| M4 | 3-5 days | Planned |
| M5 | 3-5 days | Planned |
| M6 | 3-5 days | Planned |
| M7 | 5-7 days | Planned |

**Total remaining: 16-25 days**

---

## Architecture Vision

```
                 FULL VAPT PLATFORM
                        │
          ┌─────────────┴─────────────┐
          │                           │
    Platform Layer              Research Layer
          │                           │
  parsers / normalize /        decision_engine/core
  enrich / graph / agents             │
          │                        │
          └──────────────┬─────────────┘
                         ▼
                   Controlled Execution
                         │
                         ▼
                      Report
```

The research engine remains a **reusable decision subsystem**.
The platform layer grows around it without modifying it.

---

## Governance Rules

1. **Research core is frozen** — never modify decision_engine/core/
2. **Build incrementally** — each milestone produces something testable
3. **Reuse existing code** — EPSS already exists, don't duplicate
4. **Use fixtures** — never scan external targets during development
5. **Commit atomically** — one logical change per commit
6. **Test everything** — every new file gets tests

---

*Document prepared by Hermes Agent — 2026-09-09*
