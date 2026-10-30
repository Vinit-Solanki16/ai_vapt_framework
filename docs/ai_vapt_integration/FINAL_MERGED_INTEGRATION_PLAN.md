# Final Merged Implementation Plan: Integrating AI_VAPT with Strix

**Document Reference:** AI-VAPT-STRIX-PLAN-2026-v3 (Merged)  
**Approach:** AI_VAPT as the control plane, Strix as the autonomous execution engine (adapter-first, then targeted hooks)  
**Primary Research Focus:** GAP-1 candidate ranking, GAP-2 failure-threshold pivoting, and multi-model frontend support  
**Sources:** Plan 1 (our plan), Plan 2 (Strix-side plan), Plan 3 (Updated AI_VAPT plan v2)

---

## 1. Project Overview

The project combines the existing AI_VAPT research framework with Strix, an autonomous VAPT execution engine. The goal is to reuse the strongest parts of both applications while keeping the initial integration manageable and preserving the ability to deepen the integration later.

### 1.1 Strix

Strix provides the autonomous testing and execution capabilities, including its agent workflow, browser and shell tools, and Docker-based execution environment. It supports model configuration through LiteLLM and environment variables and produces run outputs such as vulnerability findings and reports.

Relevant capabilities to confirm in the checked-out repository include:

- CLI entry point and run configuration.
- LLM configuration through LiteLLM.
- Agent orchestration and execution lifecycle.
- Run output directory and finding/report formats.
- Existing viewer or web UI functionality.

### 1.2 AI_VAPT

AI_VAPT is the research and decision-making framework. It provides the GAP-1 and GAP-2 logic, provider configuration, a web frontend, and reporting functionality.

Relevant existing components include:

- **GAP-1:** AI-informed candidate assessment and ranking before a candidate is selected.
- **GAP-2:** Per-candidate attempt counters and a configurable failure threshold that causes the engine to pivot.
- **Multi-provider configuration:** Existing support for Ollama, OpenRouter, OpenAI, and Google, with provider/model selection logic.
- **Frontend:** A vanilla JavaScript web SPA and a Streamlit dashboard.
- **Validation and reporting:** Modular validators, finding normalization, and multi-format reports.

The precise paths and interfaces should be confirmed against the current repositories before implementation.

---

## 2. Project Objective

Build an integrated VAPT workflow in which:

1. The operator uses the AI_VAPT frontend to configure and start a run.
2. AI_VAPT launches Strix through a dedicated adapter.
3. Strix performs autonomous testing and returns findings and run information.
4. AI_VAPT normalizes Strix results into its candidate/finding model.
5. GAP-1 assesses and ranks candidates, with the longer-term goal of influencing which candidates are executed next.
6. GAP-2 tracks candidate attempts and outcomes, then triggers a pivot when a candidate reaches the configured failure threshold.
7. The frontend displays run status, findings, GAP-1 decisions, GAP-2 pivot history, and reports.
8. The operator can select a supported model/provider through the AI_VAPT frontend and have that configuration passed to the Strix run.

**Implementation principle:** Start with the adapter-based architecture. Once the baseline integration is stable, add only the targeted internal Strix hooks needed for GAP-1 and GAP-2 to influence execution, borrowing that part of the Strix-side plan.

---

## 3. Target Architecture

```text
                         OPERATOR
                            |
                            v
             AI_VAPT WEB FRONTEND / CONTROL PLANE
             - Start and monitor assessments
             - Select provider and model
             - View findings and reports
             - View GAP-1 ranking and GAP-2 pivots
                            |
                            v
                   AI_VAPT API / APPLICATION
             - Run orchestration
             - Model configuration
             - Candidate/finding normalization
             - GAP-1 assessment and ranking
             - GAP-2 attempt and pivot state
             - Reporting and event updates
                            |
                            v
                    StrixWorkerAdapter
             - Build Strix run configuration
             - Launch and monitor Strix
             - Collect run output
             - Normalize returned findings
                            |
                            v
                    STRIX EXECUTION ENGINE
             - Autonomous agent workflow
             - Browser/shell/tool execution
             - Run lifecycle and findings
             - Native run outputs
                            |
                            v
                  NORMALIZED RESULT PIPELINE
             - Import Strix findings
             - Enrich and classify candidates
             - GAP-1 assess/rank
             - GAP-2 track outcomes/pivot
             - Update frontend and reports
```

### 3.1 Separation of Responsibilities

| Component | Responsibility |
|---|---|
| AI_VAPT frontend | Assessment setup, provider/model selection, live status, findings, decision traces, reports |
| AI_VAPT API/application | Coordinates runs, candidate processing, GAP-1/GAP-2, result persistence, and reporting |
| StrixWorkerAdapter | Provides a stable interface between AI_VAPT and Strix |
| Strix | Executes autonomous testing and emits native run results |
| GAP-1 | Assesses candidate quality and prioritizes candidates before dispatch where integration hooks allow |
| GAP-2 | Tracks attempts and outcomes and chooses when to abandon a candidate and pivot |
| Reporting layer | Combines Strix evidence with AI_VAPT decision history and normalized results |

### 3.2 Integration Strategy

The initial integration should not require copying all of AI_VAPT into Strix or replacing Strix's internal architecture. AI_VAPT remains the control plane, and Strix remains a separate worker process.

After the adapter works, add targeted integration points within Strix's candidate-dispatch and execution lifecycle. This deeper integration is needed because post-processing findings alone cannot change the actions Strix has already chosen or attempted.

---

## 4. GAP-1: AI-Informed Candidate Ranking

### 4.1 Current Idea

GAP-1 assesses candidate quality before ranking candidates. It aims to prioritize candidates that are more likely to be usable and relevant rather than treating every discovered candidate equally.

The existing concept can be summarized as:

```text
Candidate discovery
       |
       v
Assess candidate quality
       |
       v
Calculate priority
       |
       v
Rank candidates
       |
       v
Select candidate for execution
```

### 4.2 Integration with Strix

Implement GAP-1 in stages:

1. Import and normalize Strix findings and candidate-like results.
2. Map available fields—such as title, description, severity, confidence, evidence, endpoint, and source—into AI_VAPT's candidate representation.
3. Run the existing GAP-1 assessment and record its score, rank, confidence, and explanation where available.
4. Display the ranked results in the AI_VAPT frontend.
5. Add a targeted Strix integration hook before candidate dispatch or the next relevant action-selection point.
6. Use GAP-1's ranked queue to influence which eligible candidate is selected next.
7. Record the original order and GAP-1-adjusted order so the impact can be compared.

### 4.3 Candidate Scoring

Use the scoring approach already implemented in AI_VAPT as the starting point. The existing formula is:

```
priority = probability * (0.5 + 0.5 * quality_weight)
```

Where quality weights are: HIGH=1.0, MEDIUM=0.6, LOW=0.3, missing=0.0.

The Strix-side plan proposes an extended composite formula for future enhancement:

```
Final Priority Score = w1 * P_base + w2 * S_CVSS + w3 * E_exposure + w4 * Q_AI
```

Where:
- P_base: Baseline scanner confidence [0.0, 1.0].
- S_CVSS: Normalized severity score [0.0, 1.0].
- E_exposure: Asset exposure factor (e.g. public vs. authenticated) [0.0, 1.0].
- Q_AI: AI quality rank bonus (HIGH = +0.3, MEDIUM = +0.1, LOW = 0.0).

**Recommendation:** Use the existing AI_VAPT formula for baseline. Adopt the extended formula only after experiments demonstrate need.

### 4.4 GAP-1 Outputs

For each candidate, record the fields supported by the implementation, such as:

- Candidate identifier.
- Source (Strix or AI_VAPT).
- Original and normalized details.
- Assessment score and quality category.
- Final priority/rank.
- Short explanation for the ranking.
- Whether the candidate was selected for execution.

### 4.5 Possible Later Enhancements

Once the core integration is working, evaluate the following ideas:

- AI-suggested candidate variants that enter the candidate queue.
- Cross-model comparison or consensus for candidate scoring.
- Feedback from execution outcomes to improve later assessments.
- More explicit explanations for why a candidate received its rank.
- Adaptive assessment thresholds based on measured results.

These are optional follow-on improvements; the first goal is to make the existing GAP-1 logic work end-to-end with Strix.

---

## 5. GAP-2: Bounded Failure-Threshold Pivoting

### 5.1 Current Idea

GAP-2 tracks attempts for each candidate. When the configured failure threshold is reached, the current candidate is abandoned and the engine moves to another eligible candidate rather than continuing indefinitely on the same unsuccessful path.

```text
Select candidate
       |
       v
Execute attempt
       |
       v
Record outcome and increment attempt state
       |
       +---- Success / verified outcome ---> Record result and continue
       |
       +---- Failure below threshold ------> Continue according to policy
       |
       +---- Threshold reached ------------> Pivot to next ranked candidate
```

### 5.2 Outcome Classification (Baseline)

GAP-2 should classify outcomes using these states:

| Outcome | Meaning | Action |
|---|---|---|
| `SUCCESS` | Candidate verified | Record evidence, mark CONFIRMED, advance to next goal |
| `FAIL_TIMEOUT` | Timed out | Increment attempt; retry with longer timeout if available |
| `FAIL_SYNTAX` | Exploit syntax error | Abandon immediately (do not retry) |
| `FAIL_DEPENDENCY` | Missing prerequisite | Try alternative payload if available |
| `NOT_REPRODUCIBLE` | Could not reproduce | Increment attempt; count toward threshold |

### 5.3 Integration with Strix

Implement GAP-2 in stages:

1. Define a common candidate identifier so attempts can be associated with the same candidate across events.
2. Capture candidate-dispatch, attempt-start, attempt-complete, and outcome events where Strix exposes them.
3. Maintain per-candidate attempt counts and the configured threshold.
4. Classify outcomes using the states available from the existing AI_VAPT logic and Strix execution results.
5. When the threshold is reached, mark the candidate as exhausted for the current run and select the next eligible candidate using GAP-1's priority order.
6. Add a targeted hook to the Strix execution/agent coordination lifecycle so the pivot affects subsequent execution rather than appearing only in a report.
7. Emit a pivot event with the previous candidate, next candidate, attempt count, threshold, and reason.
8. Display attempt counts and pivot history in the frontend and include them in the final report.

### 5.4 Pivot State

A per-run state record can contain:

- Candidate identifier.
- Attempt count.
- Configured failure threshold.
- Most recent outcome.
- Candidate status (pending, active, succeeded, exhausted, or equivalent existing states).
- Pivot reason.
- Next selected candidate, if any.

Use existing AI_VAPT state structures where possible instead of creating parallel state that duplicates current behavior.

### 5.5 GAP-2 Outputs

The integrated system should make it possible to inspect:

- How many attempts were made for each candidate.
- Which outcomes were recorded.
- When the threshold was reached.
- Which candidate was selected next.
- Why the pivot occurred.
- Whether the pivot reduced repeated attempts or overall run time.

### 5.6 Possible Later Enhancements

After the basic pivot flow is measurable, consider:

- Pivot ordering based on candidate similarity or alternative techniques.
- A configurable or adaptive threshold (start N=2, scale to N=3 in exploratory mode).
- A live pivot-history panel (WebSocket/SSE).
- A decision-trace table in the report.

These should follow the core bounded pivot implementation, not block the first working integration.

---

## 6. Multi-Model Frontend and Runtime Configuration

### 6.1 Goal

Use the existing AI_VAPT frontend as the main place to select the provider and model. Pass the selected configuration to Strix for each run, using Strix's supported LiteLLM configuration conventions.

Strix already supports multiple models through LiteLLM/environment-based configuration, while AI_VAPT provides a frontend and provider configuration logic. The integration work is to connect these two configuration paths.

### 6.2 Initial Provider Scope

Start with providers already supported in the current projects, confirming exact model IDs and configuration requirements in the checked-out versions:

- Ollama/local models.
- OpenRouter.
- OpenAI.
- Google/Gemini.

**Anthropic** can be added as a follow-up (see Appendix A). It does not need to block the initial Strix integration.

### 6.3 Runtime Configuration Flow

1. The frontend displays available providers and model options.
2. The operator selects a provider/model and supplies any required API key.
3. AI_VAPT validates the configuration using the provider's existing validation flow where available.
4. AI_VAPT maps the selection to the model identifier and configuration expected by Strix/LiteLLM.
5. The adapter passes the configuration into the Strix worker process.
6. The run records the selected provider and model for later comparison.
7. The frontend shows the selected model with the run details.

### 6.4 Configuration Mapping

The mapping layer should be explicit rather than assuming provider names are interchangeable.

| Frontend selection | Strix/LiteLLM configuration |
|---|---|
| Ollama | Model identifier using the appropriate Ollama prefix and local API base |
| OpenRouter | `openrouter/<model_id>` and the corresponding API key |
| OpenAI | Supported OpenAI model identifier and API key |
| Google/Gemini | Supported Gemini/LiteLLM model identifier and API key |
| Anthropic (optional follow-up) | Supported Anthropic model identifier and API key |

Exact prefixes, model names, and environment/configuration fields should be verified against the installed Strix/LiteLLM versions.

### 6.5 Frontend Work

Reuse AI_VAPT's existing frontend and extend it to support:

- Provider selection.
- Model selection.
- Provider-specific setup and validation.
- Starting a Strix-backed run.
- Displaying the selected provider/model.
- Run status and output.
- GAP-1 candidate rankings.
- GAP-2 attempt counts and pivot history.
- Findings and reports.

The initial preference is to keep AI_VAPT's frontend as the main UI and connect it to Strix through the adapter and API. Embedding it into Strix's viewer or replacing Strix's viewer can be considered later if it provides a clear benefit.

---

## 7. Strix Worker Adapter

### 7.1 Purpose

The adapter is the central boundary between AI_VAPT and Strix. It should let AI_VAPT start and monitor a Strix run without depending on Strix's internal Python objects.

### 7.2 Proposed Components

| Component | Purpose |
|---|---|
| `vapt_platform/adapters/base.py` | Shared adapter interface and normalized result models |
| `vapt_platform/adapters/registry.py` | Registers and retrieves available execution adapters |
| `vapt_platform/adapters/strix_adapter.py` | Launches Strix, tracks run state, and reads results |
| `vapt_platform/application.py` | Connects adapter results to the AI_VAPT workflow |

The exact module layout can be adjusted to match the current repository conventions.

### 7.3 Adapter Responsibilities

The Strix adapter should:

1. Accept the target/run configuration and selected model configuration.
2. Convert it into Strix's supported CLI or configuration format.
3. Start Strix as a separate process or through its existing supported execution mechanism.
4. Capture process status and relevant output.
5. Locate the completed run directory.
6. Read Strix's structured finding output where available.
7. Normalize findings into a stable AI_VAPT representation.
8. Return run status, findings, output locations, and error details.
9. Handle timeout, failed process startup, missing output, and malformed result files in a way the frontend can display.

### 7.4 Normalized Finding Model

Use or extend the existing `NormalizedExternalFinding` concept. Keep a common structure for fields such as:

- External finding ID.
- Source engine.
- Title and description.
- Severity and confidence, when available.
- Target/endpoint.
- Evidence and references.
- Original Strix finding data or a reference to it.
- Normalization status.

Retain the original finding data so that normalization does not discard useful information from Strix.

### 7.5 Adapter API Integration

Add API operations consistent with the existing AI_VAPT service style. The initial endpoints can cover:

- Adapter status/capability information.
- Starting a Strix-backed run.
- Retrieving run status.
- Retrieving normalized findings and result metadata.

Use the project's existing run and event mechanisms where practical instead of introducing an unrelated API structure.

---

## 8. Findings, Reporting, and Frontend Integration

### 8.1 Finding Pipeline

The initial result pipeline should be:

```text
Strix run output
      |
      v
Read structured findings
      |
      v
Normalize into AI_VAPT finding model
      |
      v
Enrich/classify where existing services support it
      |
      v
GAP-1 assessment and ranking
      |
      v
GAP-2 outcome/attempt history where execution events are available
      |
      v
Frontend views and reports
```

The first adapter milestone may import and display findings before GAP-1/GAP-2 control Strix's execution. Keep this as an explicit intermediate milestone, not the final research integration.

### 8.2 Evidence and Provenance

For imported findings, retain the source engine and original finding reference. Distinguish findings reported by Strix from findings independently validated by an AI_VAPT validator or another execution step.

**Provenance tagging:** Strix findings must be tagged with evidence tier `SCANNER_DETECTED_CANDIDATE` and result semantic `OBSERVED_EXTERNAL`. This distinguishes them from AI_VAPT's own validated findings.

### 8.3 Reporting

Reuse AI_VAPT's reporting implementation and extend it to include Strix-originated findings and decision history. Where supported by the existing report system, include:

- Executive summary and run metadata.
- Findings with severity, confidence, and evidence.
- Source engine and finding provenance.
- GAP-1 scores/ranks and selection order.
- GAP-2 attempt counts and pivot decisions.
- Model/provider used for the run.
- References to native Strix outputs.
- Existing supported report formats, such as JSON, HTML, Markdown, and TXT.

Do not make a new report format a prerequisite if the existing reporting pipeline already provides the required output.

---

## 10. Implementation Roadmap"""


The order below uses the adapter-based approach as the foundation and borrows the Strix-side plan's internal execution hooks after the adapter-based baseline works.

### Phase 0 — Repository Review and Baseline (Days 1-2)

**Tasks**
- Confirm the current AI_VAPT and Strix versions and repository structure.
- Run AI_VAPT's existing test suite (1057 tests, all must pass).
- Run Strix independently against a controlled test target.
- Identify Strix's run-output structure and the relevant candidate-dispatch/execution lifecycle.
- Record baseline results and the commands/configuration used.
- Verify Strix TUI binary availability (Go compiler absent — use packaged binary or skip TUI).
- Verify Strix viewer token auth mechanism.

**Deliverables**
- Baseline notes.
- Confirmed integration points.
- Existing test status and sample Strix output.

### Phase 1 — Build the Strix Adapter (Days 3-7)

**Tasks**
- Create the adapter interface and registry.
- Implement Strix process/configuration invocation.
- Capture run status and output locations.
- Parse structured Strix findings.
- Normalize findings into AI_VAPT's external-finding model.
- Add tests for successful runs, failed startup, missing output, malformed output, and timeouts.
- Implement scope gatekeeper wrapper around Strix invocation.

**Deliverables**
- Working `StrixWorkerAdapter`.
- Adapter tests.
- Normalized Strix findings available to AI_VAPT.
- Scope enforcement active.

### Phase 2 — Connect Strix Findings to AI_VAPT (Days 8-12)

**Tasks**
- Connect adapter output to the AI_VAPT application workflow.
- Add the required API operations for adapter status, starting runs, and retrieving results.
- Display Strix run status and findings in the existing frontend.
- Preserve source and provenance information (tag as `SCANNER_DETECTED_CANDIDATE` / `OBSERVED_EXTERNAL`).
- Reuse AI_VAPT's reporting pipeline for imported results.

**Deliverables**
- An operator can start a Strix run from AI_VAPT.
- Findings appear in the AI_VAPT UI and reports.
- Baseline end-to-end integration works before changing Strix's internal flow.

### Phase 3 — Integrate GAP-1 into Candidate Selection (Days 13-17)

**Tasks**
- Map Strix candidate/finding data to GAP-1 inputs.
- Apply existing GAP-1 assessment and ranking.
- Display the rank and assessment details in the frontend.
- Identify the actual Strix point where candidates or follow-up actions are selected.
- Add the smallest suitable hook to make GAP-1 ordering influence subsequent dispatch.
- Log both the original order and GAP-1-selected order.
- Add tests proving that ranking affects the selection order.

**Deliverables**
- GAP-1 scores and ranks are visible.
- Candidate-selection decisions are recorded.
- A test demonstrates that GAP-1 changes the order of candidates selected for execution.

### Phase 4 — Integrate GAP-2 into Execution Outcomes (Days 18-22)

**Tasks**
- Identify the relevant Strix attempt lifecycle and outcome events.
- Connect attempt outcomes to AI_VAPT's GAP-2 state.
- Track attempts by stable candidate ID.
- Apply the configured threshold and mark exhausted candidates.
- Connect the pivot decision to the next eligible candidate in the GAP-1 queue.
- Emit and display pivot events.
- Add tests for success, repeated failure, threshold reached, and selection of the next candidate.

**Deliverables**
- Per-candidate attempt tracking.
- Visible pivot history.
- Execution flow can move to another candidate after the threshold is reached.
- Tests demonstrate that GAP-2 affects subsequent execution.

### Phase 5 — Complete Multi-Model Frontend Support (Days 23-27)

**Tasks**
- Connect provider/model choices in the AI_VAPT frontend to the Strix adapter.
- Map selected models to Strix/LiteLLM configuration.
- Reuse existing provider validation where available.
- Test local Ollama and the hosted providers supported by the current code.
- Record provider/model metadata with each run.
- Add Anthropic if it is needed for the desired provider set (see Appendix A).

**Deliverables**
- Model/provider selection is available through AI_VAPT.
- Selected configuration is passed correctly to Strix.
- Provider/model used is visible in run details.

### Phase 6 — Improve the Unified UI and Reports (Days 28-30)

**Tasks**
- Add a clear run overview with status and findings.
- Add a GAP-1 ranking view.
- Add GAP-2 attempt/pivot history.
- Link to or display native Strix output where useful.
- Include ranking, pivot, provider, and provenance details in AI_VAPT reports.
- Decide whether to keep the AI_VAPT UI standalone or embed it into Strix's viewer based on the working prototype.
- (Optional) Add WebSocket/SSE for real-time pivot visualization.

**Deliverables**
- Coherent frontend workflow.
- Reports that show findings and the decisions leading to them.

### Phase 7 — Regression Testing and Evaluation (Days 31-35)

**Tasks**
- Run the existing AI_VAPT and adapter test suites.
- Run Strix baseline and integrated configurations against the same controlled test scenarios.
- Repeat experiments where practical.
- Record findings, candidate order, attempts, pivots, duration, and model/provider.
- Compare results across the evaluation configurations.
- Document limitations and observed outcomes.

**Deliverables**
- Test report.
- Comparative evaluation table.
- MTech implementation and results documentation.

---

## Appendix EL: Commands to Run"""

### 11.1 New AI_VAPT Files

| Proposed file | Purpose |
|---|---|
| `vapt_platform/adapters/base.py` | Adapter interface and normalized finding model |
| `vapt_platform/adapters/registry.py` | Adapter registry |
| `vapt_platform/adapters/strix_adapter.py` | Strix invocation, status, and result collection |
| `vapt_platform/adapters/strix_scope_wrapper.py` | Scope enforcement wrapper |
| `tests/test_strix_adapter.py` | Adapter behavior tests |
| `tests/test_strix_candidate_integration.py` | Candidate pipeline integration tests |
| `tests/test_gap1_strix_integration.py` | GAP-1 ranking/selection integration tests |
| `tests/test_gap2_strix_integration.py` | GAP-2 attempt/pivot integration tests |

### 11.2 AI_VAPT Files to Review or Modify

| File or area | Intended change |
|---|---|
| `vapt_platform/application.py` | Connect Strix findings and run results to the application workflow |
| `vapt_platform/model_config.py` | Reuse provider/model registry and add providers if required |
| `vapt_platform/assessment.py` | Reuse provider-specific assessment and validation paths |
| `services/api.py` | Add adapter/run API operations and connect model configuration |
| `services/schemas.py` | Add or extend run, provider, adapter, and normalized finding schemas |
| `frontend/web/js/app.js` | Add Strix run setup, model selection, ranking, and pivot views |
| `frontend/web/index.html` | Add or update frontend sections as needed |
| `frontend/app.py` | Keep Streamlit dashboard aligned if it remains in use |
| `vapt_platform/reporting/` | Include normalized Strix findings and decision traces |

### 11.3 Strix Areas to Inspect and Potentially Modify Later

| Area mentioned in Plan 2 | Intended use |
|---|---|
| `strix/core/inputs.py` | Candidate/input preparation and possible GAP-1 entry point |
| `strix/core/runner.py` | Run lifecycle and orchestration |
| `strix/core/execution.py` | Attempt lifecycle and possible GAP-2 integration |
| `strix/core/agents.py` | Agent coordination and candidate dispatch |
| Strix model configuration / LiteLLM integration | Accept the provider/model selected in AI_VAPT |
| Strix viewer/API | Optional integration with the AI_VAPT frontend |

These are candidate locations from the original plans, not confirmed current interfaces. Inspect the repository and follow the actual execution flow before making changes.

---

## 12. Testing and Evaluation Strategy

### 12.1 Functional Tests

- Adapter can start Strix and collect run status.
- Structured findings are parsed and normalized.
- Missing or malformed output is handled and reported clearly.
- Imported findings retain their source and original data.
- Selected provider/model configuration reaches Strix correctly.
- GAP-1 ranking is recorded and influences candidate selection.
- GAP-2 counts attempts and triggers a pivot at the configured threshold.
- Frontend displays run status, findings, ranking, and pivot history.
- Reports include the expected finding and decision metadata.
- Scope enforcement blocks unauthorized targets.
- API keys never appear in logs, reports, persistence, or frontend.

### 12.2 Comparison Configurations

| Configuration | Description |
|---|---|
| A — Baseline | Strix without GAP-1/GAP-2 integration |
| B — GAP-1 | Strix with GAP-1 assessment/ranking influencing candidate selection |
| C — GAP-2 | Strix with GAP-2 attempt tracking and pivoting |
| D — GAP-1 + GAP-2 | Strix with both decision components integrated |
| E — Full integration | AI_VAPT frontend/control plane, Strix adapter, GAP-1, GAP-2, and multi-model configuration |

Use the same controlled test scenarios for each applicable configuration so that differences can be compared.

### 12.3 Suggested Metrics

- Candidate ranking and selection order.
- Number of attempts per candidate.
- Number and correctness of pivots.
- Time to first verified finding, where verification data is available.
- Total run duration.
- Findings returned and findings verified.
- Provider/model used.
- Adapter success rate and integration errors.
- Token/cost measurements where reliable telemetry is available.

The goal is to determine which improvements come from GAP-1, which come from GAP-2, and what the full integration adds beyond vanilla Strix.

---

## 13. Risk Mitigations

| Risk | Mitigation |
|---|---|
| Strix dependency conflicts (pydantic, langchain) | Run Strix in Docker container only; never install in AI_VAPT venv. Pin versions. |
| Strix scope bypass (prompt-only enforcement) | Wrap with AI_VAPT's `validate_web_target()` before launch (§9.1) |
| OOM in Codespace (Strix Kali image 5-15 GB) | Use `--scan-mode quick`, `--max-turns 3`, `--max-budget 0.50` |
| AGPL contamination (Shannon) | Never copy Shannon code; use REST boundary |
| Research integrity (GAP-1/GAP-2) | Freeze `decision_engine/core/`; CI checks for zero diffs on ported copy |
| Strix TUI binary missing (no Go compiler) | Use packaged binary or skip TUI; web viewer is sufficient |
| Viewer token auth | Handle token-based auth in unified console integration |

### Frozen Core Rule

`decision_engine/core/` must never be modified when ported. The ported copy must be byte-for-byte identical. CI gate fails on any diff. This is critical for research integrity — GAP-1/GAP-2 must be demonstrably unmodified.

---

## 14. Implementation Order at a Glance

```text
Repository review and baseline
             |
             v
       Strix adapter
             |
             v
Findings in AI_VAPT frontend/reports
             |
             v
GAP-1 scoring and selection hook
             |
             v
GAP-2 attempt and pivot hook
             |
             v
Multi-model runtime configuration
             |
             v
Unified UI/report improvements
             |
             v
Regression tests and comparative evaluation
```

---

## 15. Expected Final Deliverables

1. AI_VAPT can launch and monitor Strix through a dedicated adapter.
2. Strix findings are normalized and displayed in AI_VAPT.
3. GAP-1 assesses and ranks candidates, and its ranking affects candidate selection.
4. GAP-2 tracks attempts and outcomes and can redirect execution after the configured threshold.
5. The AI_VAPT frontend can configure a supported model/provider for a Strix run.
6. Reports include findings, source information, GAP-1 ranking, GAP-2 pivot history, and run/model metadata.
7. Automated tests cover the adapter and both GAP integrations.
8. A comparative evaluation documents the effect of GAP-1 and GAP-2 against the Strix baseline.

---

## 16. Final Recommendation

Implement **Plan 1 as the foundation**: AI_VAPT remains the control plane and Strix runs as an external worker through an adapter. This establishes a working end-to-end integration without immediately requiring broad changes to Strix.

Then take the key execution-level idea from **Plan 2**: add targeted hooks into Strix's candidate-dispatch and execution lifecycle so GAP-1 can influence selection and GAP-2 can influence pivots. This is essential for demonstrating that the research logic changes execution behavior rather than only reordering completed findings.

Keep AI_VAPT's frontend as the primary interface, connect its model/provider choices to Strix, and evaluate the integration in stages against a vanilla Strix baseline.

---

## Appendix A: Anthropic Provider Addition (Optional Follow-up)

AI_VAPT currently supports ollama, openrouter, openai, google. Anthropic can be added as a follow-up without blocking initial integration.

### Files to Modify

1. **`vapt_platform/model_config.py`**:
   - Add `DEFAULT_ANTHROPIC_MODEL = "claude-3.5-sonnet"`
   - Add `ANTHROPIC_MODELS` tuple
   - Add `"anthropic"` to `KNOWN_PROVIDERS`
   - Add to `PROVIDER_LABELS`, `PROVIDER_API_KEY_ENV` (`ANTHROPIC_API_KEY`)
   - Add `default_anthropic_model_from_env()`
   - Update `models_for_provider()`, `default_model_for()`, `api_key_env_for()`

2. **`core/exploit_assessor.py`**:
   - Add `from langchain_anthropic import ChatAnthropic` (guarded import)
   - Add `elif provider == "anthropic":` branch in `get_llm()`

3. **`vapt_platform/assessment.py`**:
   - Add `_try_anthropic_assess()` function
   - Add `elif provider == "anthropic":` in `create_assessor()`
   - Add Anthropic to fail-fast key check

4. **`services/api.py`**:
   - Add `X-Anthropic-API-Key` header to `start_run()`
   - Add `/providers/anthropic/validate` endpoint
   - Add `AnthropicValidateResponse` schema

5. **`services/schemas.py`**:
   - Add `"anthropic"` to `assessor_provider` Literal
   - Add `AnthropicValidateResponse` model

6. **`frontend/web/js/app.js`**:
   - Add `anthropic` to `PROVIDER_MODELS`, `PROVIDER_NOTES`
   - Add Anthropic setup panel (similar to Google)

7. **`frontend/app.py`** (Streamlit):
   - Add Anthropic to provider selectbox
   - Add Anthropic setup panel

8. **`.env.example`**:
   - Add `ANTHROPIC_API_KEY` section

### Test Addition
- `tests/test_anthropic_provider.py` — mock HTTP transport, no real API calls

---

## Appendix B: End-to-End Walkthrough Example

When an operator assesses `https://xyz.com:4280/` through the integrated system:

1. **Intake & Scope Check**:
   - Operator enters `https://xyz.com:4280/` in the web console.
   - Target is verified: publicly routable IP validated; operator acknowledges engagement scope.
2. **Model Selection**:
   - Operator selects **Ollama (`qwen2.5:1.5b`)** for private offline assessment OR **Google Gemini (`gemini-2.0-flash`)** with an in-memory key.
3. **Reconnaissance & Discovery**:
   - Nmap executes controlled service discovery on port 4280.
   - Nuclei scans for exposures and misconfigurations.
   - Strix spider identifies API endpoints and sitemap parameters.
4. **GAP-1 Quality Scoring**:
   - 12 raw findings are discovered.
   - 8 are categorized as Informational/Discovery (saved to inventory, excluded from attack).
   - 4 Actionable Vulnerabilities are passed to the AI Assessor:
     - Candidate 1 (`/phpinfo.php`): AI Rank = `HIGH` (standalone, zero noise).
     - Candidate 2 (`CORS Misconfiguration`): AI Rank = `MEDIUM`.
     - Candidate 3 (`Theoretical XSS on /search`): AI Rank = `LOW` (requires user interaction).
     - Candidate 4 (`Outdated Library Banner`): AI Rank = `LOW` (no exploit provided).
   - Queue is sorted: Candidate 1 → Candidate 2 → Candidate 3 → Candidate 4.
5. **Execution & GAP-2 Pivoting**:
   - **Candidate 1 Dispatched**: Validator issues non-destructive HTTP check → HTTP 200, 3 signatures matched → **SUCCESS**. SHA-256 evidence hash recorded.
   - **Candidate 2 Dispatched**: Dispatched to Strix agent. Attempt 1 fails (CORS header reflective but credential access blocked). Attempt 2 fails (preflight rejected).
   - **GAP-2 Pivot Triggered**: Candidate 2 hits threshold k=2. Engine aborts Candidate 2, logs `REDIRECT`, and immediately pivots to Candidate 3.
6. **Audit Reporting**:
   - Compilation of comprehensive HTML, JSON, and SARIF reports detailing:
     - Executive summary, asset metadata, OWASP categories.
     - Cryptographic proof hashes and reproduction curl commands.
     - Decision trace with GAP-1 rankings and GAP-2 pivot logs.
     - Concrete remediation patches.

---

## Appendix C: Commands to Run

### Start AI_VAPT (existing)
```bash
cd /home/vinit/AI_VAPT
source .venv/bin/activate
VAPT_AUTHORIZED_WEB_SCOPES=pentest-ground.com:4280 uvicorn services.api:app --reload --port 8000
# Open http://localhost:8000
```

### Start Strix (existing)
```bash
cd /home/vinit/STRIX/strix
export STRIX_LLM="ollama/qwen2.5:1.5b"
export LLM_API_BASE="http://127.0.0.1:11434"
export LLM_API_KEY="ollama"
uv run strix -n -t http://127.0.0.1:9191 --scan-mode quick --max-budget 5
```

### After Integration (future)
```bash
# Run Strix as AI_VAPT worker
cd /home/vinit/AI_VAPT
python -m vapt_cli run --target-url http://127.0.0.1:9191 --engine strix --max-budget 0.50

# View Strix findings in AI_VAPT dashboard
# Open http://localhost:8000 → Findings → filter by source: strix
```