# AI-VAPT Full Remediation and Validation Plan

**Prepared:** 2026-11-24  
**Repository:** `/home/vinit/AI_VAPT/ai_vapt_framework`  
**Primary benchmark:** Authorized local OWASP Juice Shop at `http://127.0.0.1:3000`  
**Reference run:** `run-2485de38`

## 1. Objective

The objective is to make AI-VAPT a trustworthy and functional security-assessment system. A successful system must execute real security tests, reach defensible conclusions, preserve reproducible evidence, recover safely from runtime failures, and report coverage and limitations accurately.

The latest run proves that real model and security-tool execution occurs, but it also exposes correctness problems:

- Login SQL injection was marked ruled out even though a fresh controlled check returned an administrator token.
- The publicly accessible `/ftp/acquisitions.md` document was dismissed as public documentation even though its content explicitly identifies it as confidential.
- The run exported two candidate findings and zero verified findings, while a lifecycle event claimed four confirmed findings.
- Candidate and probe counts were inferred even when invocation identifiers were absent.
- The first execution exceeded the model context window and required a resumed execution.
- The run completed the candidate workflow while recording only 40.9% assessment completeness, 50% category coverage, thirteen abandoned candidates, and zero executed pivots.
- GAP-1 assessment is heuristic but can be labeled as model-based.

These problems require remediation in dependency order. Evidence truthfulness and state consistency must be fixed before broader detection coverage is treated as reliable.

## 2. Guiding Principles

1. A model statement is not security evidence.
2. An integrity hash proves that data has not changed; it does not prove that an exploit succeeded.
3. Failure to exploit is inconclusive unless a defined negative-proof contract is satisfied.
4. Process completion, assessment completeness, candidate disposition, and finding verification are separate concepts.
5. Every reported probe, pivot, finding, and coverage claim must resolve to a real execution record.
6. Historical run artifacts remain immutable. Corrections are recorded as new interpretations or validation runs.
7. Benchmark success means repeatable performance within a defined scope, not a promise to find every vulnerability in every application.

## 3. Delivery Sequence

The main dependency chain is:

```text
Reproducible baseline
        ↓
Evidence and verification contracts
        ↓
Authoritative state and accounting
        ↓
Detection and investigation workflows
        ↓
GAP-1 and GAP-2 correctness
        ↓
Runtime resilience and resume
        ↓
Reports and dashboard consistency
        ↓
Independent security review
        ↓
Repeatable release benchmark
```

Each phase has a completion gate. Work proceeds based on objective evidence that the gate has passed.

## 4. Phase 0 — Reproducible Baseline and Failure Corpus

### Purpose

Preserve the current behavior and convert every confirmed defect into a repeatable regression case.

### Work

- Record the application commit, branch, working-tree changes, Python and dependency versions, provider/model configuration, Docker version, and Juice Shop image digest.
- Preserve `run-2485de38`, its engine and control-plane directories, agent database, evidence, logs, coverage artifacts, JSON, HTML, and PDF.
- Keep historical artifacts read-only and store future validation runs under distinct names.
- Create a documented procedure to start, reset, seed, and stop the local Juice Shop benchmark.
- Establish safe test identities and repeatable target data for authentication, basket, upload, and authorization tests.
- Create regression fixtures for:
  - Login SQL injection incorrectly marked ruled out.
  - Confidential FTP content incorrectly dismissed.
  - Two candidate findings reported elsewhere as four confirmed findings.
  - Probe counts reported without tool invocation identifiers.
  - Context-window exhaustion followed by resume.
  - Abandoned candidates with no demonstrated GAP-2 pivot.
  - Evidence hash verification for request-only, response-only, and combined evidence.
- Map every observed defect to its responsible subsystem and a planned automated test.
- Inspect existing uncommitted changes before implementation and preserve unrelated user work.

### Deliverables

- Baseline environment manifest.
- Sanitized failure corpus and fixtures.
- Juice Shop reset procedure.
- Defect-to-test traceability table.

### Completion Gate

Every material defect from the reference run can be reproduced against a pinned environment and is linked to its original evidence and intended regression test.

## 5. Phase 1 — Evidence and Verification Semantics

### Purpose

Ensure that positive and negative security conclusions are supported by explicit evidence contracts.

### Primary Components

- `strix/report/evidence.py`
- `strix/report/verification.py`
- `strix/tools/coverage/`
- `strix/tools/reporting/outcome_tool.py`
- Finding schemas and report serialization

### Work

#### 5.1 Define finding states

Use explicit, non-overlapping states:

- `candidate`: a plausible vulnerability that has not been actively established.
- `attempted`: an active test ran but did not produce enough evidence.
- `verified`: the vulnerability-specific positive-proof contract passed.
- `inconclusive`: evidence is insufficient or conflicting.
- `rejected`: a vulnerability-specific negative-proof contract passed.

Candidate workflow state must remain separate from finding verification state. A candidate may be complete while its security conclusion remains inconclusive.

#### 5.2 Define vulnerability-specific positive contracts

At minimum:

| Vulnerability class | Required positive evidence |
|---|---|
| Login SQL injection | Invalid-login baseline, injected request, authenticated response, and authenticated identity or privilege evidence |
| Product-search SQL injection | Baseline and controlled injected requests with meaningful, repeatable behavioral difference |
| Sensitive-file exposure | Unauthenticated request, successful response, and evidence that the returned content is sensitive |
| JWT sensitive-data exposure | Token issuance evidence and decoded sensitive claims tied to the token |
| JWT validation weakness | Demonstrated acceptance of a manipulated or improperly validated token |
| IDOR/BOLA | Two controlled identities or ownership contexts and demonstrated unauthorized resource access |
| DOM XSS | Browser execution evidence in the affected route and sink |
| CSRF | Demonstrated state change under the application's actual authentication and browser behavior |
| File upload weakness | Accepted prohibited input and observable security impact or policy bypass |

#### 5.3 Define negative-proof contracts

- A failed payload cannot by itself rule out a vulnerability class.
- Negative conclusions must identify the tested endpoint, method, content type, parameter, authentication context, payload family, and expected signal.
- Unsupported techniques and unavailable prerequisites produce `inconclusive`, not `rejected`.
- Contradictory positive evidence blocks a negative conclusion until explicitly resolved.
- A candidate can be rejected only when the relevant contract is satisfied with linked evidence.

#### 5.4 Fix evidence provenance and integrity

- Store raw request and response data separately from model interpretation.
- Attach run ID, candidate ID, execution ID, tool invocation ID, timestamp, target, and redaction metadata.
- Define one canonical hashing procedure.
- Verify request-only, response-only, combined, redacted, and tampered evidence.
- Prevent fabricated or auto-generated invocation IDs from proving execution.
- Ensure exported hashes match the canonical stored evidence representation.
- Record transformation and redaction steps so a reviewer can reproduce the exported evidence.

### Tests

- Login SQL injection positive contract passes with an administrator token.
- A failed SQL payload remains inconclusive.
- FTP sensitive-file contract passes on `acquisitions.md`.
- Public nonsensitive content does not pass that contract.
- Request-only and response-only evidence round-trip without false tamper detection.
- Changed evidence fails integrity validation.
- Model prose without execution evidence cannot produce `verified`.

### Completion Gate

The known login and FTP misclassifications are prevented by tests. No finding becomes verified solely from prose, a coverage declaration, or a generated execution identifier.

## 6. Phase 2 — Authoritative State, Accounting, and Completion

### Purpose

Make the engine, control plane, dashboard, JSON, HTML, and PDF derive their conclusions from one authoritative event history.

### Primary Components

- `strix/report/reconciliation.py`
- `strix/report/coverage.py`
- `strix/core/gap_run.py`
- `strix/core/gap_bridge.py`
- API lifecycle and resume handling

### Work

#### 6.1 Introduce authoritative execution events

- Define versioned event schemas with stable event and invocation IDs.
- Persist events before derived counters are updated.
- Make replay and resume idempotent.
- Deduplicate by stable event identity rather than text similarity.
- Retain segment identity for initial and resumed execution.

#### 6.2 Correct accounting

Count these independently:

- Model requests and turns.
- Security tool executions.
- Coverage declarations.
- Verification checks.
- Candidate attempts.
- Findings created.
- Findings verified.
- Pivot decisions.
- Pivot executions.

Remove fallback logic that converts candidate counts into unique tool-invocation counts. Missing telemetry must be reported as unknown or unavailable.

#### 6.3 Correct completion semantics

Represent independently:

- Process lifecycle: running, paused, failed, canceled, or completed.
- Objective coverage percentage.
- Candidate disposition counts.
- Verified finding counts.
- Unresolved, abandoned, unsupported, and blocked objectives.

The completion gate may allow an honest partial assessment, but the result must remain visibly partial. A clean process exit cannot imply full security coverage.

#### 6.4 Correct resume behavior

- Do not duplicate probes, findings, coverage records, or counters after resume.
- Scope historical errors to the segment in which they occurred.
- Preserve active errors separately from resolved historical errors.
- Reconcile engine and control state using documented authority and conflict rules.

### Tests

- Replaying the same events does not alter totals.
- Initial execution plus resume produces the same final state as uninterrupted execution.
- Missing invocation IDs never increase concrete probe counts.
- JSON, HTML, PDF, and API output have identical finding and verification totals.
- A run with abandoned work is never represented as a complete security assessment.

### Completion Gate

Every displayed number is traceable to a real event. All report formats agree, and process completion cannot be confused with security-assessment completeness.

## 7. Phase 3 — Detection and Investigation Workflows

### Purpose

Fix the practical testing workflows that missed or misclassified known Juice Shop vulnerabilities.

### Primary Components

- `strix/core/scanner/crawler.py`
- `strix/core/scanner/active_fuzzer.py`
- Candidate generation and scheduling
- Authentication/session management
- Browser and HTTP tooling
- Agent investigation instructions

### Workstreams

#### 7.1 Authentication and login SQL injection

- Preserve the actual POST method, JSON body, content type, and endpoint.
- Establish an invalid-credential baseline.
- Execute syntax, boolean, and authentication-bypass payload families within the authorized target.
- Validate success using token issuance, identity, and privilege evidence.
- Separate default-credential success from injection success.

#### 7.2 Product-search SQL injection

- Use syntax-aware payloads for the observed backend.
- Compare normal, false-condition, and true-condition results.
- Measure status, response structure, record count, and stable semantic differences.
- Generate reproduction instructions from the actual request.

#### 7.3 Sensitive path and FTP testing

- Follow directory links and discovered filenames.
- Inspect retrieved content for explicit sensitivity markers and meaningful confidential data.
- Separate directory listing, unauthenticated file retrieval, and content sensitivity into distinct evidence claims.

#### 7.4 JWT testing

- Separate sensitive claim disclosure, weak signing, algorithm confusion, missing expiration, and validation bypass.
- Decode tokens safely without treating decodability as a vulnerability.
- Require distinct evidence for each JWT weakness.

#### 7.5 Authorization and business logic

- Maintain two controlled user identities and owned objects.
- Test basket access across ownership boundaries.
- Exercise valid and invalid quantity transitions against resettable data.
- Preserve before/after object state.

#### 7.6 Browser-dependent testing

- Drive the actual SPA route for DOM XSS.
- Observe execution rather than reflection alone.
- Evaluate CSRF under the application's actual token, cookie, and browser behavior.
- Record unsupported browser capabilities explicitly.

#### 7.7 Upload and client-bundle testing

- Discover the real upload workflow before testing restrictions.
- Test filename, type, extension, size, and server-side handling boundaries.
- Follow actual versioned JavaScript bundle names rather than assuming `/main.js`.
- Distinguish exposed routes from exposed secrets.

#### 7.8 Discovery correctness

- Detect SPA fallback responses so HTTP 200 does not automatically prove endpoint existence.
- Preserve method, parameters, authentication prerequisites, and content types in candidate definitions.
- Deduplicate equivalent candidates without merging distinct vulnerability classes.
- Mark unsupported tests explicitly rather than silently abandoning them.

### Completion Gate

Fresh autonomous runs on a reset target repeatedly verify login bypass, product-search injection, confidential FTP exposure, and JWT sensitive-data exposure. Defined negative controls do not become verified findings.

## 8. Phase 4 — Truthful GAP-1 Ranking

### Purpose

Make prioritization provenance accurate and demonstrate whether ranking improves security outcomes.

### Primary Components

- `strix/core/triage/exploit_assessor.py`
- `strix/core/triage/scoring.py`
- `strix/core/scheduler.py`
- Decision-engine initialization

### Work

- Label deterministic string/rule assessment as `heuristic`.
- Document the origin and transformation of every scoring input.
- Stop describing a CVSS-derived number as an independent exploit probability.
- Preserve the same ranked order through dispatch, resume, and alternative selection.
- Place unranked candidates after ranked candidates.
- Deduplicate candidates before ranking.
- If model-based assessment is retained:
  - Perform a real model invocation.
  - Record invocation identity, model, structured response, latency, and fallback reason.
  - Validate the structured result before it affects scheduling.
  - Fall back explicitly to heuristic scoring on failure.
- Compare ranking strategies under equal budgets:
  - Discovery order.
  - Severity-only order.
  - Heuristic GAP-1 order.
  - Model-assisted order, if implemented.
- Measure time and tool executions to verified findings, not only whether ordering changed.

### Completion Gate

All provenance labels are accurate, every dispatch path follows the documented order, and claims that GAP-1 improves results are supported by comparative benchmark data.

## 9. Phase 5 — Execution-Backed GAP-2 Pivots

### Purpose

Ensure bounded attempts and failure-driven pivoting are real, consistent, and auditable.

### Primary Components

- `strix/core/gap_run.py`
- `strix/core/gap_bridge.py`
- Decision engine and scheduler
- `strix/tools/reporting/outcome_tool.py`

### Work

- Define exactly which operations consume a candidate attempt.
- Enforce the attempt limit across normal execution and resume.
- Store pivot decision and alternative execution as separate events.
- Count a pivot only when:
  - An eligible alternative differs from the original candidate.
  - A real security-tool invocation executes against that alternative.
  - The execution is linked to the originating pivot decision.
- Link using original candidate ID, alternative candidate ID, pivot decision ID, and tool invocation ID.
- Reject self-pivots.
- Prevent generated or caller-asserted IDs from proving execution.
- Handle unavailable alternatives and exhausted queues explicitly.
- Reset state for a genuinely new run while preserving legitimate resumed state.
- Display decided, executed, blocked, and exhausted pivot counts separately.
- Build a deterministic scenario where one route fails twice and an alternative succeeds.

### Completion Gate

The deterministic scenario produces a traceable executed pivot within the configured attempt bound. Self-pivots, duplicate events, and asserted executions cannot inflate the count.

## 10. Phase 6 — Model Runtime, Context Management, and Resume

### Purpose

Prevent context failure, compaction failure, or provider errors from corrupting assessment state.

### Primary Components

- `strix/llm/compaction.py`
- Provider error handling
- Agent persistence
- Execution lifecycle and resume

### Work

- Calculate context budgets from model limits, tool schemas, current input, and reserved output.
- Trigger compaction before a request approaches the provider limit.
- Bound command, browser, and scanner output placed in model context.
- Store full raw evidence outside conversational context and pass compact references.
- Preserve unresolved candidates, identities, contradictory evidence, pending decisions, and evidence references during compaction.
- Prevent compaction summaries from upgrading an uncertain conclusion.
- Add bounded retry and timeout handling.
- Pause with an actionable reason when safe recovery is unavailable.
- Classify provider authentication, authorization, rate limits, context overflow, timeout, and network errors separately.
- Ensure resume cannot repeat state-changing target actions unintentionally.
- Preserve accounting across execution segments.
- Record an auditable finish reason tied to remaining objectives and resource limits.

### Tests

- Injected context overflow.
- Compaction timeout.
- Provider 401/403, rate-limit, 5xx, and network timeout.
- Process interruption before and after event persistence.
- Multiple resumes.
- Compaction with contradictory evidence.

### Completion Gate

Failure-injection tests either recover or pause truthfully without losing, duplicating, or upgrading evidence and conclusions.

## 11. Phase 7 — Reports and Dashboard

### Purpose

Make every user-facing output accurate, consistent, actionable, and reproducible.

### Primary Components

- Report reconciliation and schemas
- HTML/PDF generators
- API serialization
- Web dashboard

### Work

- Generate all output formats from one versioned report model.
- Display verification state beside severity.
- Show process state separately from coverage and verification.
- Prominently display partial coverage, abandoned work, unsupported checks, and unresolved candidates.
- Remove unsupported claims such as confirmed or cryptographically verified when their contracts have not passed.
- Generate vulnerability-specific remediation and retest instructions.
- Ensure SQL retests use the actual endpoint, method, body, and parameter.
- Ensure JWT retests inspect the relevant token property.
- Include evidence references and reproducible requests for verified findings.
- Redact credentials, tokens, and secrets in ordinary exports while retaining controlled raw evidence.
- Label active duration and wall-clock duration correctly.
- Add cross-format consistency tests.
- Inspect generated PDFs for layout, clipping, page breaks, and readable evidence.

### Completion Gate

The API, dashboard, JSON, HTML, and PDF agree on all material counts and states. Reviewers can reproduce every verified finding and identify every untested or inconclusive objective.

## 12. Phase 8 — Daybreak Defense Factory Review

### Purpose

Use Daybreak Defense Factory to independently assess security weaknesses in the AI-VAPT framework itself. This review complements functional benchmark testing; it does not prove Juice Shop detection accuracy.

### Review Scope

- API authentication and authorization.
- Command and subprocess execution boundaries.
- Docker/runtime isolation.
- Target scope enforcement and redirect handling.
- Credential storage, masking, and logs.
- Evidence and report download path handling.
- Browser and network-tool exposure.
- Untrusted target content influencing privileged tool behavior.
- Dependency and code-level security findings.

### Workflow

1. Enable Daybreak access for the workspace.
2. Connect the intended GitHub repository.
3. Select the repository, revision, and compatible scan environment.
4. Read the available security-scan workflow definition.
5. Launch a repository scan with the selected supported model configuration.
6. Inspect all returned findings and output-validation warnings.
7. Reproduce applicable findings locally.
8. Fix confirmed issues and run focused validation.
9. Re-run the relevant security review.
10. Record accepted residual risks and release blockers.

### Current Dependency

Daybreak reported:

- `access: denied`
- `isEligibleWorkspace: false`

The Daybreak setup interface has been opened. Repository scans cannot proceed until workspace access is enabled. This dependency does not block local implementation and validation phases.

### Completion Gate

The independent review is completed and triaged. No confirmed critical or high-severity framework issue remains unresolved without an explicit release decision and documented rationale.

## 13. Phase 9 — Benchmark, CI, and Release Gates

### Purpose

Demonstrate repeatable performance and prevent future regressions.

### Work

- Create a ground-truth manifest for the pinned Juice Shop deployment.
- Independently verify each reference-report item before treating it as benchmark truth.
- Mark benchmark cases as applicable, unsupported, excluded, or environment-dependent.
- Add negative controls and at least one holdout application or Juice Shop variant to reduce overfitting.
- Run at least three fresh autonomous assessments from a clean target state.
- Run deterministic regression tests in normal CI.
- Run resource-intensive live security benchmarks as a separate release check.
- Execute the full test suite and `make check-all` before release.

### Metrics

- Verified detection rate against applicable ground truth.
- Verified false positives.
- Incorrect negative conclusions.
- Evidence completeness.
- Coverage per vulnerability class.
- Time and tool executions to first verified finding.
- Model and security-tool usage.
- Recovery success under injected failures.
- GAP-1 ranking benefit under equal budgets.
- GAP-2 decision and execution correctness.
- Agreement across report formats.

### Proposed Release Gates

| Gate | Required Result |
|---|---|
| Core vulnerable scenarios | Login bypass, product-search injection, confidential FTP exposure, and JWT sensitive-data exposure verified in each of three clean runs |
| Negative controls | Zero verified false positives in the defined control suite |
| Evidence | Every verified finding links to reproducible execution evidence |
| Accounting | No invented probes, duplicate events, or contradictory finding totals |
| Coverage | Every scoped objective has an honest disposition |
| GAP-1 | Accurate provenance and consistent scheduling order |
| GAP-2 | Execution-backed pivots and enforced attempt bounds |
| Recovery | Context, interruption, and resume tests preserve state correctly |
| Reporting | JSON, HTML, PDF, API, and dashboard agree |
| Framework security | Independent-review findings are triaged and release blockers are resolved or explicitly accepted |

## 14. Testing Strategy

### Unit Tests

- Evidence canonicalization and hashing.
- Verification contract evaluation.
- Candidate and finding state transitions.
- Counter derivation from events.
- GAP-1 scoring and ordering.
- GAP-2 attempt and pivot rules.
- Error classification.

### Integration Tests

- HTTP tool execution to evidence to finding.
- Engine events to control-plane reconciliation.
- Resume and idempotent replay.
- Report-model generation across all output formats.
- Authentication and multi-user workflows.

### Live Authorized Tests

- Pinned local Juice Shop only unless another target is explicitly authorized.
- Reset target state between benchmark repetitions.
- Prefer non-destructive validation and controlled test accounts.
- Record target image digest and application health before every run.

### Failure-Injection Tests

- Provider and network failures.
- Context overflow and compaction timeout.
- Process termination at persistence boundaries.
- Missing or duplicated events.
- Corrupted evidence.
- Resume after partial completion.

## 15. Work Packages and Review Boundaries

Implementation should be delivered as small, reviewable work packages:

1. Baseline fixtures and regression tests.
2. Evidence integrity and verification contracts.
3. Authoritative events and accounting.
4. Login, product-search, FTP, and JWT detection fixes.
5. Remaining browser, authorization, business-logic, and upload workflows.
6. GAP-1 provenance and scheduling.
7. GAP-2 execution linking and pivot validation.
8. Context, compaction, and resume resilience.
9. Unified reports and dashboard.
10. Benchmark harness, CI gates, and Daybreak finding remediation.

Each package must include:

- The concrete defect or requirement.
- The implementation change.
- Meaningful regression tests.
- Validation evidence.
- Known limitations and follow-up work.

## 16. Immediate First Milestone

The first implementation milestone combines Phases 0 through 2:

1. Preserve and reproduce the known failures.
2. Prevent unsupported positive and negative conclusions.
3. Correct evidence integrity and provenance.
4. Make all counters derive from real execution events.
5. Make completion and coverage states unambiguous.
6. Enforce consistency across API, dashboard, JSON, HTML, and PDF.

This milestone creates the trustworthy foundation required for broader detection improvements. After it passes, Phase 3 should begin with the four live scenarios already demonstrated on the authorized Juice Shop target.

## 17. Definition of a Truly Functional Release

AI-VAPT is ready to be described as a functional autonomous VAPT system for its declared scope when:

- It executes real tests through traceable tool invocations.
- It verifies findings using vulnerability-specific evidence contracts.
- It does not convert unsuccessful tests into unsupported negative conclusions.
- It reports partial coverage and uncertainty clearly.
- Its state and counters remain correct across failures and resume.
- GAP-1 and GAP-2 behavior is both truthful and measurable.
- Its report formats agree and provide reproducible evidence.
- It passes repeatable positive and negative benchmark scenarios.
- Its own framework security has undergone independent review.

Passing these gates supports a bounded and defensible claim about the tested scope. It does not imply universal vulnerability detection.
