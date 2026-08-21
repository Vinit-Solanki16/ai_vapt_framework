# 04 — AGENT ASSIGNMENTS

Policy (governance §6): Hermes = PM/architecture/integration auditor/scheduler/evidence
tracker (does NOT implement large features when a designated worker is assigned). Claude Code
= independent READ-ONLY reviewer by default; reviews P0/P1/P2 implementations. OpenCode = primary
implementation worker (ONE atomic task at a time). Cline = small targeted IDE fixes only.

## Standing assignments
| Agent | Standing role | Notes |
|-------|---------------|-------|
| HERMES | orchestrator | writes/updates 00–10; schedules; reconciles; commits verified tasks |
| CLAUDE CODE | reviewer | READ-ONLY unless edit explicitly required; reviews P0/P1/P2 |
| OPENCODE | impl worker | one atomic task per dispatch; freezes overlapping files |
| CLINE | focused fixer | no repo-wide autonomous work |

## Per-task assignment (from 02/03)
| Task | Impl agent | Review agent | Dispatch mode |
|------|-----------|-------------|---------------|
| T-SAFE | OpenCode (cyber scope) | CLAUDE CODE (read-only review) | one task |
| T-BENCH-LOOP | OpenCode | CLAUDE CODE | one task |
| T-TESTS | OpenCode | CLAUDE CODE | one task |
| T-CORPUS | OpenCode (cyber) | HERMES verify | one task |
| T-BENCH-VAR | OpenCode (mlops) | HERMES/CLAUDE | after deps |
| T-GAP1-VALID | OpenCode (mlops) | HERMES + advisor | after deps |
| T-DOCKER | OpenCode (cyber) | CLAUDE CODE | after T-SAFE; gated by Docker up |
| T-OPENAI | OpenCode | HERMES verify | mock sufficient |
| T-CHECKPOINT | OpenCode | HERMES verify | one task |
| T-REQPIN | OpenCode | HERMES verify | one task |
| T-GITHUB | OpenCode (github) | HERMES verify | mock sufficient |
| T-README | OpenCode | HERMES verify | after SAFE+LOOP |
| T-DEADCODE | OpenCode/Cline | HERMES verify | one task |
| T-UI | OpenCode | CLAUDE CODE | one task |

## File-freeze rules
- Only the assigned task's Allowed files may change during a dispatch.
- No two agents modify overlapping files simultaneously.
- App logic changes (core/*.py) for P0/P1/P2 require a CLAUDE CODE review before DONE.
- Project-management docs (00–10) are owned by HERMES only.

## Prompt generation (governance §10)
HERMES generates each task prompt with: task ID, objective, allowed files, forbidden scope,
dependencies, acceptance criteria, exact tests, stop conditions. Review prompts specify READ-ONLY
unless edit explicitly required. Routine prompts are self-generated; only gate events (§11) escalate
to the user.
