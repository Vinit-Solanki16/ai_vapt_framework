# TASK REGISTER — Two-Track Roadmap (authority-reviewed 2026-08-27)

Status: TODO / IN_PROGRESS / DONE. Tasks are atomic; one agent modifies one
workstream at a time; Hermes verifies before any commit.

## TRACK 0 — FROZEN VAPT EVIDENCE BASELINE
| ID | Title | Status | Note |
|----|-------|--------|------|
| T0-BASE | Original VAPT prototype | FROZEN | core/; 39/39 tests; GAP-1/2 + L2 observed evidence |

## TRACK 1 — GENERALIZED DECISION ENGINE (verify before claiming)
| ID | Title | Owner | Status | Gate |
|----|-------|-------|--------|------|
| T-DE-TESTS | Dedicated regression suite for decision_engine/ | impl agent | TODO | GATE 1 |
| T-DE-BOUNDARY | Independent architecture / domain-leakage review | reviewer (RO) | TODO | GATE 2 |
| T-DE-BENCH | Benchmark fairness / reproducibility / structural-bias review | reviewer (RO) | TODO | GATE 3 |
| T-DE-EVIDENCE | Reconcile evidence tiers + claims (TRACK0 vs TRACK1) | Hermes+review | TODO | GATE 4 |

## TRACK A — THESIS / RESEARCH (after gates)
| ID | Title | Status |
|----|-------|--------|
| R1 | Related work + dated Strix snapshot | TODO (after gates) |
| R2 | Novelty / threat-to-novelty matrix | TODO |
| R3 | Claim register A/B/C | TODO |
| R4 | Independent challenge review | TODO |
| R5-R7 | Methodology + evidence + GO/NO-GO | TODO |
| A7 | Thesis / paper writing | BLOCKED until GO |

## TRACK B — LONG-TERM FULL VAPT PLATFORM (not started)
| ID | Title | Status |
|----|-------|--------|
| B2 | Formal adapter API | TODO (future) |
| B3 | Discovery / recon layer | TODO (future) |
| B4 | URL/IP/network ingestion | TODO (future) |
| B5 | Multiple VAPT tools (Nmap/Nuclei) | TODO (future) |
| B6 | Feed findings into engine | TODO (future) |
| B7 | Level-3 Docker validation | PARKED |
| B8 | Full reporting/UI | TODO (future) |

## Acceptance for T-DE-TESTS (required tests)
TEST-DE-01 candidate schema validation
TEST-DE-02 priority/ranking ordering
TEST-DE-03 successful outcome advances immediately
TEST-DE-04 failed outcome increments attempt counter
TEST-DE-05 below threshold allows controlled retry
TEST-DE-06 threshold triggers pivot
TEST-DE-07 repeated failures terminate within bound
TEST-DE-08 no infinite transition loop
TEST-DE-09 checkpoint creation
TEST-DE-10 resume reproduces expected state
TEST-DE-11 generic executor calls supplied execute_fn
TEST-DE-12 VAPT adapter isolated from engine core (import boundary)

After T-DE-TESTS: report separately — "Frozen VAPT baseline: 39/39; General
engine: X/X" — do NOT blur the counts.
