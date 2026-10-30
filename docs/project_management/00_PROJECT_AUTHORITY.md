# 00 — PROJECT AUTHORITY

**Project:** An Autonomous AI Framework for Vulnerability Assessment: Integrating
Exploit Quality Scoring and Dynamic Decision-Pivoting

**Project root:** /home/vinit/ai_vapt_framework

**Governance model:** Project Governance Mode (TOP-LEVEL) — persistent orchestrator
(Hermes) maintains local operational memory and continues work without per-task user
prompts, pausing only for the explicit gate events in §11 of the protocol.

## Roles
- **HERMES** — project manager, architect, integration auditor, task scheduler,
  evidence tracker. Does NOT independently implement large features when a designated
  implementation agent is assigned.
- **CLAUDE CODE** — independent reviewer / architecture & research-validity reviewer /
  reviewer of P0/P1/P2. Default mode: READ-ONLY REVIEW.
- **OPENCODE** — primary implementation worker. Receives ONE atomic approved task at a time.
- **CLINE** — small targeted IDE fixes, debugging, focused reviewer corrections. No
  repo-wide autonomous work.

## Research objective (immutable)
- **GAP-1 — Exploit Usability Gap:** assess candidate exploit/PoC viability BEFORE
  validation; ranking must influence execution / candidate selection.
- **GAP-2 — Agent Pivot Failure:** maintain explicit execution state; track attempts
  and outcomes; detect repeated failure; terminate/pivot; select another candidate;
  terminate safely when exhausted.
- Do NOT rename as Gap 3. Use GAP-1 / GAP-2 consistently in code, docs, experiments, thesis.

## Current phase
AUDIT → INDEPENDENT REVIEW → REMEDIATION. No uncontrolled feature expansion.

## Authority rules
- Actual repository + test evidence are authoritative; prior agent output is hypothesis,
  not truth.
- Marking work DONE requires: implementation inspected, acceptance criteria checked,
  required tests executed, results recorded, no known regression.
- "real" execution mode is UNSAFE/MISLEADING until corrected (see 08_RISK_REGISTER.md,
  09_BENCHMARK_EVIDENCE.md). No offensive PoC against non-authorized targets.

## Gate events requiring user approval
A. deleting significant project data
B. offensive code outside isolated lab
C. changing research objective / thesis scope
D. unusually large deps/models
E. credential/secret/external-account changes
F. destructive Git ops
G. major architecture redesign invalidating prior work

## Canonical documentation
The authoritative plan is the local project-management docs, not chat context.
Files: 00..10 under docs/project_management/.
