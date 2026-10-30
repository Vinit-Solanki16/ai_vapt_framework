# Phased Execution Plan with Verification Gates

**Source Plan:** `/home/vinit/AI_VAPT/docs/project_management/FINAL_MERGED_INTEGRATION_PLAN.md`  
**Project:** AI_VAPT + Strix Integration  
**Approach:** Adapter-first, then targeted hooks. Each phase has a VERIFICATION GATE that must pass before advancing.

---

## Phase 0 — Repository Review and Baseline

**Goal:** Understand both codebases, confirm integration points, establish test baseline.

**Tasks:**
1. Read `FINAL_MERGED_INTEGRATION_PLAN.md` fully.
2. Explore AI_VAPT structure: `vapt_platform/`, `services/`, `frontend/`, `decision_engine/`, `tests/`.
3. Explore Strix structure: `strix/interface/`, `strix/core/`, `strix/llm/`, `strix/tools/`.
4. Run AI_VAPT tests: `PYTHONPATH=.venv/lib/python3.12/site-packages .venv/bin/pytest -q` → expect 1057+ passed.
5. Run Strix independently: `uv run strix -n -t http://127.0.0.1:9191 --scan-mode quick --max-budget 1` against test target.
6. Identify Strix run output directory structure (`strix_runs/<run>/`).
7. Identify Strix candidate-dispatch point in `strix/core/agents.py` or `strix/core/runner.py`.
8. Identify Strix attempt lifecycle in `strix/core/execution.py`.
9. Check Strix viewer token auth mechanism.
10. Check if Go compiler / `strix-tui` binary exists.

**VERIFICATION GATE 0:**
- [ ] AI_VAPT tests pass (1057+)
- [ ] Strix runs successfully against test target
- [ ] Run output directory structure documented
- [ ] Candidate-dispatch and attempt-lifecycle files identified
- [ ] Baseline notes written to `docs/project_management/PHASE0_BASELINE.md`

**Output:** `docs/project_management/PHASE0_BASELINE.md`

---

## Phase 1 — Build the Strix Adapter

**Goal:** Create adapter that launches Strix, collects results, normalizes findings. Wrap with scope enforcement.

**Tasks:**
1. Create `vapt_platform/adapters/base.py`:
   - `ExternalEngineAdapter` ABC
   - `ResultSemantic` enum (OBSERVED_EXTERNAL, etc.)
   - `NormalizedExternalFinding` dataclass
2. Create `vapt_platform/adapters/registry.py`:
   - Adapter manager singleton
   - `register()`, `get()`, `list_adapters()`
3. Create `vapt_platform/adapters/strix_adapter.py`:
   - `StrixWorkerAdapter` implementing `ExternalEngineAdapter`
   - `start_run(target, model_config, scope_profile)` → launches Strix subprocess
   - `get_status(run_id)` → poll process
   - `get_findings(run_id)` → read `vulnerabilities.json`, normalize
   - `cancel(run_id)` → kill process
   - Handle: timeout, failed startup, missing output, malformed JSON
4. Create `vapt_platform/adapters/strix_scope_wrapper.py`:
   - Wrap Strix invocation with `validate_web_target()` from `vapt_platform/web_target.py`
   - Block unauthorized targets before Strix launches
5. Add API endpoints in `services/api.py`:
   - `GET /adapters` → list available adapters
   - `GET /adapters/strix/status` → adapter capability info
   - `POST /adapters/strix/run` → start Strix-backed run
   - `GET /adapters/strix/runs/{run_id}` → run status
   - `GET /adapters/strix/runs/{run_id}/findings` → normalized findings
6. Add schemas in `services/schemas.py`:
   - `StrixRunRequest`, `StrixRunResponse`, `StrixRunStatus`, `NormalizedFindingResponse`
7. Tag findings with provenance: `source_engine="strix"`, `evidence_tier="SCANNER_DETECTED_CANDIDATE"`, `result_semantic="OBSERVED_EXTERNAL"`

**VERIFICATION GATE 1:**
- [ ] `python -c "from vapt_platform.adapters.strix_adapter import StrixWorkerAdapter"` succeeds
- [ ] Adapter starts Strix against test target and returns run_id
- [ ] `get_findings(run_id)` returns normalized findings list
- [ ] Scope wrapper blocks unauthorized target (e.g., 127.0.0.1 without auth)
- [ ] API endpoints return 200 with valid responses
- [ ] Missing/malformed output handled gracefully (no crash, error returned)
- [ ] Tests in `tests/test_strix_adapter.py` pass (≥10 tests)
- [ ] No API keys in any log output or report

**Output:** Working adapter + tests + API endpoints

---

## Phase 2 — Connect Strix Findings to AI_VAPT

**Goal:** End-to-end: operator starts Strix run from AI_VAPT frontend, sees findings in UI and reports.

**Tasks:**
1. Connect adapter output to `vapt_platform/application.py`:
   - Add `run_strix_assessment()` method
   - Import findings into AI_VAPT's finding model
   - Enrich/classify where existing services support it
2. Update frontend (`frontend/web/js/app.js`):
   - Add "Start Strix Run" button/form
   - Display run status (polling or SSE)
   - Display normalized findings table
   - Show source engine badge ("Strix")
3. Update `frontend/web/index.html`:
   - Add Strix run section
4. Reuse AI_VAPT reporting pipeline:
   - Include Strix findings in JSON/HTML/Markdown/TXT reports
   - Include source engine and provenance in report
5. Add adapter status to System Health dashboard

**VERIFICATION GATE 2:**
- [ ] Operator can start Strix run from AI_VAPT frontend (http://localhost:8000)
- [ ] Run status updates in real-time (polling or SSE)
- [ ] Findings appear in frontend table with source="strix" badge
- [ ] Report (HTML/JSON/MD) includes Strix findings
- [ ] Provenance tagged correctly in report
- [ ] End-to-end test: start run → wait → view findings → view report
- [ ] `tests/test_strix_candidate_integration.py` pass (≥8 tests)

**Output:** End-to-end integration working

---

## Phase 3 — Integrate GAP-1 into Candidate Selection

**Goal:** GAP-1 assesses and ranks Strix findings; ranking influences candidate selection.

**Tasks:**
1. Map Strix finding fields to GAP-1 candidate inputs:
   - title → candidate title
   - description → candidate description
   - severity → candidate severity
   - confidence → candidate probability
   - evidence → candidate evidence
   - endpoint → candidate target
2. Apply existing GAP-1 assessment (`vapt_platform/assessment.py`):
   - `assess_exploit_quality()` for each finding
   - Calculate priority using existing formula
   - Sort candidates by priority descending
3. Display GAP-1 ranking in frontend:
   - Show quality rank (HIGH/MEDIUM/LOW)
   - Show priority score
   - Show assessment reasoning
4. Identify Strix candidate-dispatch point (`strix/core/agents.py` or `strix/core/runner.py`)
5. Add targeted hook: before Strix dispatches next candidate, consult GAP-1 ranked queue
   - Pass ranked candidate list to Strix via env var or config file
   - Strix uses ranked order for dispatch
6. Log both original order and GAP-1-selected order for comparison
7. Add tests: `tests/test_gap1_strix_integration.py`

**VERIFICATION GATE 3:**
- [ ] GAP-1 assesses all Strix findings and assigns quality ranks
- [ ] Priority scores calculated and displayed in frontend
- [ ] Assessment reasoning visible per candidate
- [ ] Ranked order differs from original order (demonstrates GAP-1 impact)
- [ ] Strix dispatches candidates in GAP-1 ranked order (verify via logs)
- [ ] Original vs ranked order logged for comparison
- [ ] `tests/test_gap1_strix_integration.py` pass (≥8 tests)
- [ ] Decision engine core unchanged (git diff shows zero changes to `decision_engine/core/`)

**Output:** GAP-1 influencing Strix execution

---

## Phase 4 — Integrate GAP-2 into Execution Outcomes

**Goal:** GAP-2 tracks attempts per candidate; pivots when threshold reached.

**Tasks:**
1. Identify Strix attempt lifecycle (`strix/core/execution.py`):
   - Where attempts start/complete
   - How outcomes are determined
   - How to inject pivot logic
2. Connect attempt outcomes to AI_VAPT GAP-2 state:
   - Create candidate ID mapping (Strix finding ID → AI_VAPT candidate ID)
   - Track attempt count per candidate
   - Classify outcomes: SUCCESS, FAIL_TIMEOUT, FAIL_SYNTAX, FAIL_DEPENDENCY, NOT_REPRODUCIBLE
3. Apply configured threshold (default k=2):
   - Increment attempt on failure
   - When attempts ≥ k: mark candidate as exhausted
   - Select next candidate from GAP-1 ranked queue
   - Emit pivot event (previous, next, count, threshold, reason)
4. Add targeted hook in Strix execution:
   - On threshold reached, Strix abandons current candidate
   - Strix picks next candidate from GAP-1 queue
5. Display in frontend:
   - Attempt count per candidate
   - Pivot history (from → to, reason, timestamp)
6. Include pivot history in reports
7. Add tests: `tests/test_gap2_strix_integration.py`

**VERIFICATION GATE 4:**
- [ ] Attempt counts tracked per candidate (visible in frontend)
- [ ] Outcomes classified correctly (SUCCESS/FAIL_TIMEOUT/etc.)
- [ ] Pivot triggers when threshold k reached
- [ ] Next candidate selected from GAP-1 queue (not sequential)
- [ ] Pivot event emitted with full details (from, to, count, threshold, reason)
- [ ] Pivot history displayed in frontend and report
- [ ] `tests/test_gap2_strix_integration.py` pass (≥10 tests)
- [ ] Comparison test: GAP-2 reduces repeated attempts vs baseline

**Output:** GAP-2 influencing Strix execution

---

## Phase 5 — Complete Multi-Model Frontend Support

**Goal:** Operator can select provider/model from AI_VAPT frontend; config passed to Strix.

**Tasks:**
1. Connect provider/model selection to Strix adapter:
   - Map frontend selection to Strix/LiteLLM config
   - Pass model config via adapter `start_run()` params
2. Reuse existing provider validation:
   - Ollama: probe `http://127.0.0.1:11434/api/tags`
   - OpenRouter: validate via `X-OpenRouter-API-Key` header
   - Google: validate via `X-Google-API-Key` header
   - OpenAI: validate via API key
3. Record provider/model metadata with each run
4. Display selected provider/model in run details
5. (Optional) Add Anthropic provider (Appendix A of merged plan):
   - Follow file-by-file changes in Appendix A
   - Add `tests/test_anthropic_provider.py`

**VERIFICATION GATE 5:**
- [ ] Provider dropdown works in frontend (ollama, openrouter, openai, google)
- [ ] Model selection updates available models per provider
- [ ] API key validation works (invalid key → error shown)
- [ ] Selected config reaches Strix (verify in Strix logs/env)
- [ ] Run details show provider + model used
- [ ] Local Ollama works end-to-end (qwen2.5:1.5b)
- [ ] At least one hosted provider works end-to-end (with test key)
- [ ] (If Anthropic added) Anthropic provider tests pass

**Output:** Multi-model support working

---

## Phase 6 — Improve the Unified UI and Reports

**Goal:** Polish frontend and reports with GAP-1/GAP-2 data.

**Tasks:**
1. Add run overview dashboard:
   - Run status, duration, findings count
   - Provider/model used
   - Scope profile
2. Add GAP-1 ranking view:
   - Candidate table with quality rank, priority, reasoning
   - Original vs ranked order comparison
3. Add GAP-2 attempt/pivot history view:
   - Attempt count per candidate
   - Pivot timeline (from → to, reason, timestamp)
   - Decision trace table
4. Link to native Strix outputs (run directory, SARIF, Markdown report)
5. Enhance reports:
   - Include GAP-1 ranking in HTML/JSON/MD/TXT reports
   - Include GAP-2 pivot history in reports
   - Include provider/model metadata
   - Include provenance tags
6. (Optional) Add WebSocket/SSE for real-time pivot visualization
7. Decide: keep AI_VAPT UI standalone or embed in Strix viewer (document decision)

**VERIFICATION GATE 6:**
- [ ] Run overview shows all key metrics
- [ ] GAP-1 ranking view displays correctly with reasoning
- [ ] GAP-2 pivot history displays with timeline
- [ ] Decision trace table in report
- [ ] All report formats (JSON/HTML/MD/TXT) include GAP-1 + GAP-2 data
- [ ] Native Strix output linked and accessible
- [ ] Frontend responsive and no console errors

**Output:** Polished UI and reports

---

## Phase 7 — Regression Testing and Evaluation

**Goal:** Comprehensive testing, comparative evaluation, documentation.

**Tasks:**
1. Run full AI_VAPT test suite: `pytest -q` → all pass
2. Run adapter tests: `pytest tests/test_strix_adapter.py` → all pass
3. Run GAP-1 tests: `pytest tests/test_gap1_strix_integration.py` → all pass
4. Run GAP-2 tests: `pytest tests/test_gap2_strix_integration.py` → all pass
5. Run comparison configurations A-E against same test scenarios:
   - A: Strix baseline (no GAP-1/GAP-2)
   - B: Strix + GAP-1
   - C: Strix + GAP-2
   - D: Strix + GAP-1 + GAP-2
   - E: Full integration (AI_VAPT + Strix + GAP-1 + GAP-2 + multi-model)
6. Record metrics for each configuration:
   - Candidate ranking/selection order
   - Attempts per candidate
   - Pivots (count + correctness)
   - Time to first verified finding
   - Total run duration
   - Findings returned vs verified
   - Provider/model used
   - Adapter success rate
   - Token/cost (if available)
7. Verify frozen core: `git diff -- decision_engine/core/` → empty
8. Verify no API keys in logs/reports: grep all output for key patterns
9. Write evaluation report: `docs/project_management/EVALUATION_REPORT.md`
10. Write MTech implementation documentation

**VERIFICATION GATE 7 (FINAL):**
- [ ] All tests pass (AI_VAPT + adapter + GAP-1 + GAP-2)
- [ ] Frozen core unchanged (git diff empty)
- [ ] No API keys in any output
- [ ] Comparison table completed (Configs A-E)
- [ ] Evaluation report written
- [ ] MTech documentation complete
- [ ] All phases verified and documented

**Output:** Complete, tested, evaluated integration

---

## Phase Summary Table

| Phase | Name | Days | Key Deliverable | Gate |
|---|---|---|---|---|
| 0 | Repository Review & Baseline | 1-2 | Baseline notes | Tests pass, Strix runs |
| 1 | Strix Adapter | 3-7 | Adapter + scope wrapper | Adapter tests pass, API works |
| 2 | Connect Findings | 8-12 | End-to-end integration | Findings in UI + reports |
| 3 | GAP-1 Integration | 13-17 | GAP-1 influences dispatch | Ranking affects selection |
| 4 | GAP-2 Integration | 18-22 | GAP-2 pivots execution | Pivot triggers at threshold |
| 5 | Multi-Model Support | 23-27 | Provider selection works | Config reaches Strix |
| 6 | UI & Reports Polish | 28-30 | Polished dashboard | All formats include GAP data |
| 7 | Testing & Evaluation | 31-35 | Evaluation report | All tests pass, core frozen |

---

## Critical Rules for All Phases

1. **Frozen Core**: `decision_engine/core/` must never be modified. CI gate on any diff.
2. **Secret Safety**: API keys never in logs, reports, persistence, or frontend.
3. **Scope Enforcement**: Every Strix invocation must pass `validate_web_target()` first.
4. **Provenance**: Strix findings tagged `SCANNER_DETECTED_CANDIDATE` / `OBSERVED_EXTERNAL`.
5. **Test First**: Write tests before or alongside implementation. Each phase has ≥8 tests.
6. **Verify Before Advance**: Do not start next phase until current gate passes.
7. **No Fabrication**: Never fabricate test results or API responses. Report blockers honestly.