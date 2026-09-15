# PHASE 5.5 — IMPLEMENTATION PLAN

**Date:** 2026-09-11
**Based on:** `docs/architecture/PHASE_5_5_ARCHITECTURE_AUDIT.md`

---

## NEXT MILESTONE: Architecture Cleanup

### Priority Order

| Task | Agent | Files | Estimated Effort |
|------|-------|-------|------------------|
| 1. Scanner deduplication | A | `core/scanner.py`, `decision_engine/adapters/scan_adapter.py` | 2-4 hours |
| 2. VAPTResult separation | B | `vapt_platform/application.py`, `services/api.py`, `frontend/app.py` | 3-5 hours |
| 3. Legacy code removal | C | `app.py`, `core/agent_graph.py`, tests | 1-2 hours |
| 4. Integration tests | D | `services/tests/test_api.py`, `tests/test_integration.py` | 2-3 hours |

### Dependency Order

```
Task 1 (Scanner) → Task 2 (VAPTResult) → Task 3 (Legacy) → Task 4 (Tests)
```

Task 1 must complete first because Task 2 depends on the scanner interface.
Task 4 must come last because it tests the cleaned-up system.

---

## AGENT PROMPTS

### Agent A: Scanner Deduplication

```
OBJECTIVE: Remove duplicate scanner infrastructure.

FILES TO MODIFY:
- decision_engine/adapters/scan_adapter.py (update to use new scanners)
- core/scanner.py (delete after migration)

STEPS:
1. Read decision_engine/adapters/scan_adapter.py
2. Replace process_scan() call with get_scanner_registry().parse()
3. Replace findings_to_candidates() to work with CanonicalFinding
4. Delete core/scanner.py
5. Run tests to verify no regressions

ACCEPTATION:
- scan_adapter.py uses vapt_platform.scanners
- core/scanner.py deleted
- All tests pass
```

### Agent B: VAPTResult Separation

```
OBJECTIVE: Separate domain and presentation concerns in VAPTResult.

FILES TO MODIFY:
- vapt_platform/application.py
- services/api.py
- frontend/app.py

STEPS:
1. Create DomainResult dataclass with domain fields only:
   - run_id, scenario, mode, final_status
   - candidates, execution_results, decision_trace
   - total_attempts, pivot_count, candidates_processed
   - evidence_tier, assessment, safety_notice

2. Create PresentationResult dataclass:
   - report (dict)
   - graph_summary (dict, not full graph)
   - scored_candidates (list)
   - pipeline_summary (dict)

3. Update VAPTApplication.run() to return DomainResult
4. Add to_presentation() method for GUI/API
5. Update API to use DomainResult internally
6. Update GUI to use PresentationResult

ACCEPTATION:
- DomainResult has no presentation fields
- PresentationResult has no domain logic
- All tests pass
```

### Agent C: Legacy Code Removal

```
OBJECTIVE: Remove dead code and legacy imports.

FILES TO MODIFY:
- app.py (delete root Streamlit app)
- core/agent_graph.py (mark deprecated)
- tests (remove legacy imports)

STEPS:
1. Delete ./app.py (old Streamlit dashboard)
2. Add deprecation notice to core/agent_graph.py
3. Update tests to not import from core.agent_graph
4. Remove any other dead code identified in audit

ACCEPTATION:
- app.py deleted
- No imports from core.agent_graph in active code
- All tests pass
```

### Agent D: Integration Tests

```
OBJECTIVE: Add missing integration tests.

FILES TO MODIFY:
- services/tests/test_api.py
- tests/test_integration.py

STEPS:
1. Add API integration test:
   - Start test client
   - POST /runs with docker_vuln scenario
   - GET /runs/{id}/report
   - Verify response structure

2. Add full pipeline e2e test:
   - Load scan fixture
   - Enrich findings
   - Build graph
   - Score candidates
   - Run validation pipeline
   - Verify all stages executed

ACCEPTATION:
- API test passes
- Pipeline e2e test passes
- No regressions
```

---

## SUCCESS CRITERIA

- [ ] core/scanner.py deleted
- [ ] scan_adapter.py uses new scanners
- [ ] VAPTResult separated into DomainResult + PresentationResult
- [ ] app.py deleted
- [ ] No legacy imports in active code
- [ ] API integration test passes
- [ ] Pipeline e2e test passes
- [ ] All existing tests pass

---

*Plan created by Hermes Agent — 2026-09-11*
