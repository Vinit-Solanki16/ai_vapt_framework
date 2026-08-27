# TWO-TRACK ROADMAP — General Decision Engine → Full VAPT Platform

_Last updated: 2026-08-27. Supersedes the single-track Phase 6 plan for the
purpose of research positioning. The frozen `core/` implementation remains the
verified VAPT research prototype (Phase 0–6). This roadmap adds STAGE 1
(generalize the engine) and STAGE 2 (re-integrate as a VAPT domain adapter)._

## The vision (user-confirmed 2026-08-27)

The project is NOT "build a VAPT tool and write a thesis." It is two stages:

- **STAGE 1 — General autonomous decision & pivot engine.** A domain-free
  engine that: scores candidate actions before execution (Gap-1), selects the
  best by priority, executes, observes the real outcome, tracks per-candidate
  attempt counts, pivots away from failing paths at a threshold (Gap-2), and
  terminates in a bounded way. VAPT is only the FIRST domain it is proven on.
- **STAGE 2 — Full VAPT platform.** Once the core engine is mature, VAPT becomes
  the major application domain: discovery → recon → scanner ingestion → finding
  normalization → fed into the engine → controlled validation/actions → reporting.

## Current state (2026-08-27)

- `core/` — frozen, verified VAPT prototype (39 tests, Phase 0–6 done, evidence
  audit PASS). DO NOT modify during research positioning.
- `decision_engine/` — NEW, Stage-1 generalized engine (copy + refactor of the
  decision logic from `core/`). Domain-independent: `core/schemas.py`,
  `core/assessor.py`, `core/executor.py`, `core/engine.py`. VAPT-specific glue is
  isolated in `adapters/vapt_adapter.py`.
- `datasets/` — real data: CISA KEV (1,682 vulns), EPSS bulk (365k rows), and
  per-corpus EPSS enrichment (12 CVEs, live scores).
- Evidence so far: agnostic benchmark shows SMART=8 attempts vs DUMB=17 on a
  NON-VAPT task domain → engine bounds repeated failure independent of VAPT.

## TRACK A — Research paper / thesis prototype (uses what exists)

```
A1  Freeze implementation (DONE — core/ frozen)
A2  Related-work + novelty audit        -> R1, R2
A3  Define precise research questions   -> R3 (claim register)
A4  Define hypotheses + methodology     -> R5–R7
A5  Validate experimental methodology   (SMART vs DUMB, ablation)
A6  Final evidence review               -> GO/NO-GO
A7  Thesis / research paper
```

## TRACK B — Full long-term project (after core research is stable)

```
B1  Extract/generalize the decision engine        (DONE — decision_engine/)
B2  Define plugin/tool interfaces (adapter API)
B3  Add discovery / recon layer
B4  Add URL/IP/network target ingestion
B5  Add multiple VAPT tools (Nmap, Nuclei, ...)
B6  Feed findings into the engine
B7  Controlled validation environment (Docker lab, Level 3)
B8  Full evidence/reporting system
```

## Governance (carried from prior phases)

- `core/` is FROZEN. All new Stage-1 work lives under `decision_engine/`.
- One atomic task at a time; user dispatches agent prompts; Hermes verifies
  before commit. No parallel agents in the same tree.
- Keep SIMULATION vs OBSERVED vs REAL distinct; never overclaim.
- T-DOCKER (Level 3) stays PARKED unless a claim specifically needs it.

## Repo layout (new)

```
decision_engine/
  core/        # domain-independent engine (schemas, assessor, executor, engine)
  adapters/    # vapt_adapter.py — ONLY VAPT-specific glue
  benchmarks/  # agnostic_benchmark.py — domain-independence evidence
datasets/      # cisa_kev.json, epss_scores.csv.gz, epss_corpus_enrichment.json
```
