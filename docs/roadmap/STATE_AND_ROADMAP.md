# AI VAPT Framework — Current State & Roadmap

**Date:** 2026-09-09
**Branch:** prototype-development
**Tests:** 339 passed, 7 skipped
**Commits:** 79

---

## 1. WHERE WE ARE RIGHT NOW

### Working Prototype (Mentor Demo Ready)

You can demonstrate this **today**:

```bash
# Terminal 1: Start Docker lab (if available)
cd lab && docker-compose up -d && cd ..

# Terminal 2: CLI demo
python -m prototype.cli run --scenario failure_pivot --max-attempts 2

# Terminal 3: GUI demo
streamlit run frontend/app.py

# Terminal 4: API demo
uvicorn services.api:app --reload
```

**What works:**
- CLI with 7 demo scenarios (success, failure_pivot, multi_candidate, single_success, all_fail, threshold_one, corpus)
- Streamlit GUI with candidate ranking, execution trace, pivot events, reports
- FastAPI backend with run/status/trace/report endpoints
- JSON + TXT report generation
- Docker lab with emulator + executor (isolated network)
- 4 evidence tiers (SIMULATED / OBSERVED_LOCAL / DOCKER_OBSERVED / CONTROLLED_VALIDATION)
- Safety allowlist with fail-closed validation

**What the mentor sees:**
1. Candidates enter the framework
2. Candidates are ranked by priority_score = probability x quality
3. Engine attempts each candidate
4. Failed candidates retried up to threshold
5. Engine pivots to next candidate
6. Decision trace explains every step
7. Report summarizes attempts, pivots, evidence tier, outcome

### Research Contribution (Frozen)

- **Gap-1**: Pre-execution priority scoring (implemented, independent contribution = 0)
- **Gap-2**: Stateful failure-threshold pivoting (implemented, +77/+200/+772 requests saved)
- Fair benchmark: 4-agent ablation, 30 seeds, 6 families
- Evidence discipline: honest labeling of simulation vs observation

---

## 2. WHAT WE HAVE BUILT

### Track A — Research (COMPLETE, FROZEN)

| Component | Status |
|-----------|--------|
| Domain-independent decision engine | DONE |
| Gap-1 priority scoring | DONE |
| Gap-2 bounded pivot | DONE |
| LangGraph orchestration | DONE |
| Checkpoint/resume | DONE |
| Fair benchmarks | DONE |
| Evidence taxonomy | DONE |
| Thesis document | DONE |

### Track B — Prototype (COMPLETE, MENTOR READY)

| Component | Status |
|-----------|--------|
| VAPT adapter | DONE |
| Scan adapter | DONE |
| Simulation mode | DONE |
| Loopback mode (127.0.0.1) | DONE |
| Docker lab (172.28.0.2) | DONE |
| JSON/TXT reporting | DONE |
| Streamlit GUI | DONE |
| FastAPI backend | DONE |
| CLI (run/resume/version) | DONE |
| Safety allowlist | DONE |
| 7 demo scenarios | DONE |
| Docker integration tests | DONE |

### Track C — Platform Wave 1 (COMPLETE)

| Component | Status |
|-----------|--------|
| Rich scan fixtures (Nmap XML/JSON, custom JSON) | DONE |
| Scan integration tests (47 tests) | DONE |
| Nuclei JSON parser (isolated) | DONE |
| Nuclei parser tests (27 tests) | DONE |

---

## 3. ARCHITECTURE TODAY

```
                   CURRENT STATE
                        │
          ┌─────────────┴─────────────┐
          │                           │
    Platform Layer              Research Layer
          │                           │
   parsers / scan           decision_engine/core
   adapters / CLI           (FROZEN)
   GUI / API                       │
          │                        │
          └──────────────┬─────────────┘
                         ▼
                   Controlled Execution
                         │
                         ▼
                      Report
```

**Missing layers** (not yet built):
- Canonical normalization
- Enrichment (EPSS/CVSS/CPE/CISA KEV)
- Asset/vulnerability graph
- Multi-agent orchestration
- Advanced GUI
- AI-assisted reporting

---

## 4. WHAT'S NEXT — MILESTONE PLAN

### M2 — Canonical Finding Pipeline (NEXT)

**Goal:** Multiple scanner formats converge into one canonical representation.

```
Nmap XML ─┐
Nmap JSON ├──> Canonical Finding ──> Candidate ──> Engine
Nuclei ───┘
```

**Scope:**
- Design canonical finding schema
- Normalize Nmap, Nuclei, Custom inputs
- Deterministic deduplication
- Preserve source/target/severity
- Bridge to existing candidate generation

**Estimated effort:** 1-2 days
**Deliverable:** `vapt_platform/normalization.py` + tests

---

### M3 — Vulnerability Intelligence

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

**Scope:**
- CVSS score extraction
- CPE normalization
- CISA KEV cross-reference
- Reuse existing EPSS code
- Severity harmonization

**Estimated effort:** 2-3 days
**Deliverable:** `vapt_platform/enrichment.py` + tests

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

**Scope:**
- Asset identity from scan data
- Service-to-asset mapping
- Vulnerability clustering
- Basic graph traversal
- Future: graph-based prioritization

**Estimated effort:** 3-5 days
**Deliverable:** `vapt_platform/graph.py` + tests

---

### M5 — Enhanced Decision Intelligence

**Goal:** Feed enriched, graph-aware data into the decision engine.

**Scope:**
- Priority scoring with enriched data
- Context-aware pivoting
- Asset-criticality weighting
- Multi-candidate strategies

**Estimated effort:** 3-5 days
**Deliverable:** Enhanced candidate scoring + tests

---

### M6 — GUI & Reporting Polish

**Goal:** Professional-quality interface and reports.

**Scope:**
- Interactive workflow
- Decision timeline visualization
- Graph visualization
- PDF/HTML reports
- Mentor demo mode

**Estimated effort:** 3-5 days
**Deliverable:** Polished GUI + report templates

---

### M7 — Multi-Agent Orchestration (FUTURE)

**Goal:** Planner/Executor/Verifier architecture.

**Scope:**
- Planner agent (strategy)
- Executor agent (tool execution)
- Verifier agent (validation)
- Inter-agent communication

**Estimated effort:** 5-7 days
**Deliverable:** Multi-agent workflow + tests

---

## 5. TIMELINE

| Phase | Milestone | Duration | Status |
|-------|-----------|----------|--------|
| M1 | Research Prototype | DONE | ✅ |
| M1 | Platform Wave 1 | DONE | ✅ |
| M2 | Canonical Pipeline | 1-2 days | NEXT |
| M3 | Enrichment | 2-3 days | Planned |
| M4 | Asset Graph | 3-5 days | Planned |
| M5 | Decision Intelligence | 3-5 days | Planned |
| M6 | GUI/Report Polish | 3-5 days | Planned |
| M7 | Multi-Agent | 5-7 days | Planned |
| **Total remaining** | | **17-27 days** | |

---

## 6. HOW MUCH WORK REMAINS

| Layer | Effort | Complexity |
|-------|--------|------------|
| M2: Canonical Pipeline | Low-Medium | Schema design + mapping |
| M3: Enrichment | Medium | External API integration |
| M4: Asset Graph | Medium-High | Graph data structures |
| M5: Decision Intelligence | Medium | Scoring algorithms |
| M6: GUI Polish | Medium | Streamlit customization |
| M7: Multi-Agent | High | Agent coordination |
| **Total** | **Significant** | **Weeks of work** |

---

## 7. WHAT WE CAN ADD MORE

### Near-Term (Practical)

| Addition | Value | Effort |
|----------|-------|--------|
| Nmap JSON fixture expansion | Better test coverage | Low |
| More Nuclei fixtures | Parser robustness | Low |
| Custom scan schema documentation | User guidance | Low |
| CLI `--format json|text` output | Usability | Low |
| Report timestamp filenames | Avoid overwrites | Low |
| `--output-dir` flag | Organize reports | Low |

### Medium-Term (Platform)

| Addition | Value | Effort |
|----------|-------|--------|
| Web recon parser (Wappalyzer, etc.) | More input sources | Medium |
| Export to CSV/Excel | Data portability | Low |
| Scan comparison (diff two scans) | Change detection | Medium |
| Scheduled scans | Automation | Medium |
| Notification system (email/Slack) | Alerting | Medium |

### Long-Term (Advanced)

| Addition | Value | Effort |
|----------|-------|--------|
| AI report generation | Narrative summaries | High |
| Reminder system | Workflow management | Low |
| Multi-user support | Collaboration | High |
| Role-based access control | Security | Medium |
| Audit logging | Compliance | Medium |

---

## 8. SUGGESTIONS

### For Your Thesis

1. **Freeze M1 prototype** — it's mentor-ready
2. **Complete M2 (Canonical Pipeline)** — demonstrates platform thinking
3. **Complete M3 (Enrichment)** — shows practical value
4. **Document everything** — thesis needs clear architecture description
5. **Prepare reproducibility package** — scripts, fixtures, documentation

### For the Platform

1. **Build incrementally** — each milestone should be testable
2. **Protect research core** — never modify decision_engine/core
3. **Reuse existing code** — EPSS already exists, don't duplicate
4. **Use fixtures** — never scan external targets during development
5. **Commit atomically** — one logical change per commit

### For the Demo

1. **Practice the 5-10 minute flow** — smooth delivery matters
2. **Prepare backup** — have screenshots/video if live demo fails
3. **Anticipate questions** — use mentor guide's Q&A section
4. **Show evidence discipline** — honest labeling impresses reviewers
5. **Demonstrate safety** — allowlist, fail-closed, isolation

---

## 9. FINAL VERDICT

| Aspect | Rating |
|--------|--------|
| Research contribution | STRONG (Gap-2 validated) |
| Prototype readiness | MENTOR READY |
| Test coverage | GOOD (339 tests) |
| Safety model | SOUND |
| Documentation | COMPREHENSIVE |
| Platform maturity | EARLY (Wave 1 complete) |
| Remaining work | SIGNIFICANT (weeks) |

**Bottom line:**
- **For thesis**: READY — research is complete, prototype works, evidence is solid
- **For platform**: EARLY STAGE — Wave 1 done, normalization next
- **For product**: FAR — needs M2-M7 plus significant engineering

**Recommended immediate action:**
1. Practice the mentor demo
2. Get feedback
3. Begin M2 (Canonical Pipeline) if mentor wants platform direction

---

*Document prepared by Hermes Agent — 2026-09-09*
