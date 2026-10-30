# 10 — CONTINUATION PROTOCOL

How to resume this project after any gap (new session, crash, handoff). The authoritative state is
the local docs/project_management/ files, NOT chat history.

## On (re)start
1. Read in order: 00_PROJECT_AUTHORITY.md → 01_PROJECT_STATE.md → 02_MASTER_PLAN.md →
   03_TASK_REGISTER.md → 07_TEST_STATUS.md → 08_RISK_REGISTER.md.
3. Confirm git baseline: `git log --oneline -1` (current freeze baseline after T-README+T-UI: `b385ec4`) and `git status` clean.
3. Pick the highest-priority task from 02/03 with status TODO and dependencies met.
4. Do NOT trust prior chat claims; re-verify against repo + tests.

## Per-task loop (governance §7)
select → verify deps → brief → assign (one agent, frozen files) → impl → run required tests →
CLAUDE CODE review for P0/P1/P2 → reconcile → re-test → update 00–10 → commit → auto-next.

## Commit discipline
- One commit per verified task. Convention: `<TASK-ID>: <short summary>`.
- Never `git add -A`. Stage only allowed files + relevant project-management doc updates.
- venv/, __pycache__/, *.pyc, data/reports/, data/benchmark_results.csv, .env remain ignored.

## Gate events → PAUSE for user approval (governance §11)
A. delete significant project data
B. offensive code outside isolated lab
C. change research objective / thesis scope
D. unusually large deps/models
E. credential/secret/external-account changes
F. destructive Git ops
G. major architecture redesign invalidating prior work

## Project-management files to update after EVERY task
- 01_PROJECT_STATE.md (phase, last verified task, next task, blockers)
- 03_TASK_REGISTER.md (status)
- 05_DECISION_LOG.md (if a decision was made)
- 07_TEST_STATUS.md (required test result)
- 06_RESEARCH_TRACEABILITY.md (if GAP-1/GAP-2 affected)

## External review storage
Claude/other independent reviews → docs/project_management/external_reviews/ with date suffix.

## Status report format (milestones)
CURRENT PHASE / CURRENT TASK / LAST VERIFIED TASK / NEXT TASK / BLOCKERS / RESEARCH GAP STATUS /
GIT COMMIT / TEST STATUS.
