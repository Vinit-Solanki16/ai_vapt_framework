# TASK REGISTER — Two-Track Roadmap

Status: TODO / IN_PROGRESS / DONE. Each Track-A item that needs a writing agent
has a ready prompt in `docs/roadmap/AGENT_PROMPTS.md`.

## TRACK A — Research paper / thesis prototype
| ID | Title | Owner | Status | Note |
|----|-------|-------|--------|------|
| A1 | Freeze implementation | Hermes | DONE | core/ frozen; 39 tests pass |
| A2 | Related-work + novelty audit | agent (user dispatches) | TODO | R1 + R2 prompts ready |
| A3 | Define precise research questions | agent | TODO | R3 claim register prompt ready |
| A4 | Hypotheses + experimental methodology | agent | TODO | R5–R7 prompts ready |
| A5 | Validate methodology (SMART vs DUMB, ablation) | Hermes | PARTIAL | agnostic + VAPT benchmarks exist; needs formal protocol |
| A6 | Final evidence review → GO/NO-GO | user+agent | TODO | |
| A7 | Thesis / research paper | user | TODO | |

## TRACK B — Full long-term project (Stage 2)
| ID | Title | Status | Note |
|----|-------|--------|------|
| B1 | Extract/generalize the decision engine | DONE | decision_engine/ built + benchmarked |
| B2 | Define plugin/tool adapter API | TODO | formalize adapters/vapt_adapter.py contract |
| B3 | Add discovery / recon layer | TODO | future |
| B4 | Add URL/IP/network target ingestion | TODO | future |
| B5 | Add multiple VAPT tools (Nmap, Nuclei) | TODO | future |
| B6 | Feed findings into the engine | TODO | adapter already maps corpus→candidates |
| B7 | Controlled validation env (Docker, Level 3) | PARKED | T-DOCKER optional upgrade |
| B8 | Full evidence/reporting system | TODO | future |

## Stage-1 engine acceptance (already met)
- [x] Domain-independent schemas (no CVE/exploit references in core/)
- [x] Gap-1 pre-execution quality scoring (assessor)
- [x] Gap-2 per-candidate attempt counter + N-threshold pivot
- [x] Bounded termination (no infinite loop)
- [x] Checkpoint/resume (core/ behaviour ported)
- [x] Agnostic benchmark: SMART < DUMB attempts on a non-VAPT domain
- [x] VAPT adapter drives engine from existing corpus without touching core/
- [x] Original 39 tests still green
