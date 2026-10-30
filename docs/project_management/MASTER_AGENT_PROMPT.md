# Master Prompt for AI Agent

Copy-paste this entire prompt into your AI coding agent (Claude Code, Codex, OpenCode, etc.) to execute the full integration project.

---

## PROMPT START

You are an expert full-stack engineer and researcher. Your task is to integrate two cybersecurity projects into a single autonomous penetration testing platform with AI decision intelligence.

### PROJECT CONTEXT

**Project A: AI_VAPT** — Research framework (Python 3.10, FastAPI + Streamlit + vanilla JS SPA)
- Location: `/home/vinit/AI_VAPT`
- Key features: GAP-1 (AI exploit quality scoring before ranking), GAP-2 (bounded failure-threshold pivoting), multi-provider LLM config (ollama/openrouter/openai/google), modular validators, multi-format reporting, scope gatekeeper
- Tests: 1057+ passing (run with `PYTHONPATH=.venv/lib/python3.12/site-packages .venv/bin/pytest -q`)
- Decision engine: `decision_engine/core/` (FROZEN — never modify)

**Project B: Strix** — Autonomous pentesting CLI (Python 3.12+, uv-managed)
- Location: `/home/vinit/STRIX/strix`
- Key features: Multi-agent pentesting, Docker sandbox, browser/shell tools, LiteLLM model support, React/Vite viewer (post-run only)
- Entry: `uv run strix -n -t <target> --scan-mode quick --max-budget 5`
- Output: `strix_runs/<run>/` with `vulnerabilities.json`, SARIF, Markdown report

**Integration Plan:** Read `/home/vinit/AI_VAPT/docs/project_management/FINAL_MERGED_INTEGRATION_PLAN.md` for full architecture.

**Phased Plan:** Read `/home/vinit/AI_VAPT/docs/project_management/PHASED_EXECUTION_PLAN.md` for phase-by-phase tasks and verification gates.

### CRITICAL RULES (NON-NEGOTIABLE)

1. **FROZEN CORE**: `decision_engine/core/` must NEVER be modified. Verify with `git diff -- decision_engine/core/` → must be empty at every phase.
2. **SECRET SAFETY**: API keys must NEVER appear in logs, reports, persistence, or frontend. In-memory only.
3. **SCOPE ENFORCEMENT**: Every Strix invocation MUST pass through `vapt_platform/web_target.py` `validate_web_target()` before launch. Strix has NO programmatic scope filter — only prompt-based.
4. **PROVENANCE**: Strix findings must be tagged `source_engine="strix"`, `evidence_tier="SCANNER_DETECTED_CANDIDATE"`, `result_semantic="OBSERVED_EXTERNAL"`.
5. **TEST FIRST**: Write tests alongside implementation. Each phase needs ≥8 tests. Never fabricate test results.
6. **VERIFY BEFORE ADVANCE**: Do not start next phase until current verification gate passes. Report blockers honestly.
7. **NO FABRICATION**: Never fabricate test results, API responses, or file contents. If something fails, report it and try an alternative.

### ARCHITECTURE DECISION

- AI_VAPT = control plane (frontend, API, GAP-1/GAP-2, reporting, scope enforcement)
- Strix = execution engine (runs as separate process via adapter)
- Adapter pattern: `StrixWorkerAdapter` launches Strix subprocess, reads `vulnerabilities.json`, normalizes to `NormalizedExternalFinding`
- After adapter baseline works, add targeted hooks in Strix's candidate-dispatch (`strix/core/agents.py`) and attempt-lifecycle (`strix/core/execution.py`) so GAP-1 influences selection and GAP-2 influences pivoting

### EXECUTION INSTRUCTIONS

Execute phases 0-7 in order. For each phase:

1. Read the phase tasks from `PHASED_EXECUTION_PLAN.md`
2. Implement all tasks
3. Run all verification gate checks
4. If any gate check fails, fix it before advancing
5. Write phase summary to `docs/project_management/PHASE{N}_SUMMARY.md`
6. Report: "Phase N complete. Gate: PASS/FAIL. Key results: ..."

Do NOT skip phases. Do NOT advance without passing the gate. Do NOT fabricate results.

### PHASE 0 — Repository Review and Baseline

Tasks:
- Read both integration plans fully
- Explore AI_VAPT: `vapt_platform/`, `services/`, `frontend/`, `decision_engine/`, `tests/`
- Explore Strix: `strix/interface/`, `strix/core/`, `strix/llm/`, `strix/tools/`
- Run AI_VAPT tests: expect 1057+ passed
- Run Strix independently against test target (http://127.0.0.1:9191)
- Identify Strix run output structure (`strix_runs/<run>/`)
- Identify candidate-dispatch point in Strix (`strix/core/agents.py` or `strix/core/runner.py`)
- Identify attempt-lifecycle in Strix (`strix/core/execution.py`)
- Check Strix viewer token auth
- Check Go compiler / strix-tui binary availability
- Write baseline notes to `docs/project_management/PHASE0_BASELINE.md`

Gate: AI_VAPT tests pass, Strix runs successfully, integration points documented.

### PHASE 1 — Build the Strix Adapter

Create these files:

1. `vapt_platform/adapters/base.py` — `ExternalEngineAdapter` ABC, `ResultSemantic` enum, `NormalizedExternalFinding` dataclass
2. `vapt_platform/adapters/registry.py` — adapter manager singleton
3. `vapt_platform/adapters/strix_adapter.py` — `StrixWorkerAdapter`:
   - `start_run(target, model_config, scope_profile)` → launches Strix subprocess
   - `get_status(run_id)` → poll process
   - `get_findings(run_id)` → read `vulnerabilities.json`, normalize
   - `cancel(run_id)` → kill process
   - Handle: timeout, failed startup, missing output, malformed JSON
4. `vapt_platform/adapters/strix_scope_wrapper.py` — wrap Strix invocation with `validate_web_target()`
5. API endpoints in `services/api.py`: GET /adapters, GET /adapters/strix/status, POST /adapters/strix/run, GET /adapters/strix/runs/{run_id}, GET /adapters/strix/runs/{run_id}/findings
6. Schemas in `services/schemas.py`: StrixRunRequest, StrixRunResponse, StrixRunStatus, NormalizedFindingResponse
7. Tag findings: source_engine="strix", evidence_tier="SCANNER_DETECTED_CANDIDATE", result_semantic="OBSERVED_EXTERNAL"

Tests: `tests/test_strix_adapter.py` (≥10 tests)

Gate: Adapter imports, starts Strix, returns findings, scope wrapper blocks unauthorized, API works, failure modes handled, no key leakage.

### PHASE 2 — Connect Strix Findings to AI_VAPT

Tasks:
- Connect adapter to `vapt_platform/application.py` (`run_strix_assessment()`)
- Import findings into AI_VAPT finding model
- Update frontend: "Start Strix Run" button, run status, findings table with source badge
- Update `frontend/web/index.html`
- Reuse reporting pipeline: include Strix findings in JSON/HTML/MD/TXT reports
- Add adapter status to System Health dashboard

Tests: `tests/test_strix_candidate_integration.py` (≥8 tests)

Gate: Operator starts Strix run from frontend, findings appear, reports include Strix data, provenance correct.

### PHASE 3 — Integrate GAP-1 into Candidate Selection

Tasks:
- Map Strix finding fields to GAP-1 candidate inputs (title, description, severity, confidence, evidence, endpoint)
- Apply existing GAP-1 assessment (`vapt_platform/assessment.py`)
- Calculate priority, sort candidates
- Display GAP-1 ranking in frontend (quality rank, priority score, reasoning)
- Identify Strix candidate-dispatch point
- Add targeted hook: pass ranked candidates to Strix for dispatch order
- Log original vs ranked order
- Tests: `tests/test_gap1_strix_integration.py` (≥8 tests)

Gate: GAP-1 assesses findings, priority calculated, ranking affects Strix dispatch, original vs ranked logged, decision_engine/core/ unchanged.

### PHASE 4 — Integrate GAP-2 into Execution Outcomes

Tasks:
- Identify Strix attempt lifecycle (`strix/core/execution.py`)
- Connect attempt outcomes to GAP-2 state (candidate ID mapping, attempt counts)
- Classify outcomes: SUCCESS, FAIL_TIMEOUT, FAIL_SYNTAX, FAIL_DEPENDENCY, NOT_REPRODUCIBLE
- Apply threshold (default k=2): increment on failure, pivot when ≥k
- Select next candidate from GAP-1 ranked queue
- Emit pivot event (previous, next, count, threshold, reason)
- Add targeted hook in Strix execution
- Display attempt counts and pivot history in frontend
- Include pivot history in reports
- Tests: `tests/test_gap2_strix_integration.py` (≥10 tests)

Gate: Attempt counts tracked, outcomes classified, pivot triggers at threshold, next from GAP-1 queue, pivot history displayed, comparison shows GAP-2 reduces repeated attempts.

### PHASE 5 — Complete Multi-Model Frontend Support

Tasks:
- Connect provider/model selection to Strix adapter
- Map frontend selection to Strix/LiteLLM config
- Reuse existing provider validation (ollama probe, OpenRouter/Google/OpenAI key validation)
- Record provider/model metadata with run
- Display selected provider/model in run details
- (Optional) Add Anthropic provider (see Appendix A of merged plan)

Tests: provider integration tests

Gate: Provider dropdown works, model selection updates, API key validation works, config reaches Strix, run details show provider+model, Ollama works end-to-end.

### PHASE 6 — Improve the Unified UI and Reports

Tasks:
- Add run overview dashboard
- Add GAP-1 ranking view (candidate table, original vs ranked comparison)
- Add GAP-2 attempt/pivot history view (attempt counts, pivot timeline, decision trace)
- Link to native Strix outputs
- Enhance reports (JSON/HTML/MD/TXT) with GAP-1 + GAP-2 + provenance + provider metadata
- (Optional) WebSocket/SSE for real-time pivot visualization

Gate: All views display correctly, all report formats include GAP data, no console errors.

### PHASE 7 — Regression Testing and Evaluation

Tasks:
- Run full test suite (all pass)
- Run comparison configurations A-E against same scenarios
- Record metrics (ranking, attempts, pivots, duration, findings, provider, adapter success, token/cost)
- Verify frozen core (git diff empty)
- Verify no API keys in outputs
- Write evaluation report
- Write MTech documentation

Gate: All tests pass, frozen core unchanged, no key leakage, comparison table complete, evaluation report written.

### TECHNICAL DETAILS

**AI_VAPT key files:**
- `vapt_platform/model_config.py` — provider/model registry
- `vapt_platform/assessment.py` — GAP-1 assessment
- `vapt_platform/web_target.py` — scope validation
- `vapt_platform/validators/` — modular validators
- `vapt_platform/reporting/` — multi-format reports
- `services/api.py` — FastAPI endpoints
- `services/schemas.py` — Pydantic models
- `frontend/web/js/app.js` — vanilla JS SPA
- `decision_engine/core/` — FROZEN decision engine

**Strix key files:**
- `strix/interface/main.py` — CLI entry point
- `strix/core/agents.py` — agent coordination, candidate dispatch
- `strix/core/runner.py` — run lifecycle
- `strix/core/execution.py` — attempt lifecycle
- `strix/core/inputs.py` — input preparation
- `strix/llm/` — LiteLLM integration
- `strix/tools/` — shell, browser, proxy tools

**Commands:**
- AI_VAPT tests: `cd /home/vinit/AI_VAPT && PYTHONPATH=.venv/lib/python3.12/site-packages .venv/bin/pytest -q`
- Strix run: `cd /home/vinit/STRIX/strix && uv run strix -n -t http://127.0.0.1:9191 --scan-mode quick --max-budget 5`
- AI_VAPT server: `cd /home/vinit/AI_VAPT && VAPT_AUTHORIZED_WEB_SCOPES=pentest-ground.com:4280 uvicorn services.api:app --reload --port 8000`

**Test target:** http://127.0.0.1:9191 (pentest-ground.com)

### START NOW

Begin with Phase 0. Read the codebases, run the tests, document findings. Do not write any code until you understand both repositories. Report your Phase 0 findings before proceeding.

## PROMPT END

---

### How to Use This Prompt

1. Copy everything between "PROMPT START" and "PROMPT END"
2. Paste into your AI coding agent (Claude Code, Codex, OpenCode, etc.)
3. The agent will execute Phase 0 first and report findings
4. Review the agent's Phase 0 output, then tell it to proceed to Phase 1
5. Continue phase by phase, verifying each gate

### Tips for Best Results

- **Use a coding agent with file access** (Claude Code, Codex, OpenCode) — not a chat interface
- **Run tests after each phase** — the agent should report real test results
- **If a phase fails**, tell the agent: "Phase N gate failed on [X]. Fix it and re-verify before advancing."
- **If the agent gets stuck**, break the phase into smaller sub-tasks
- **Keep the frozen core rule** — the agent must never modify `decision_engine/core/`
- **Review the agent's code** before accepting — especially adapter and hook code
- **The agent should report real output** — not fabricate test results or API responses