# AGENT PROMPTS (dispatch-ready)

Every prompt below is self-contained. Copy one at a time into your
implementation/review agent. Hermes verifies after each return; commits are
atomic and bounded to the task's ALLOWED FILES only.

GLOBAL GOVERNANCE (applies to all prompts):
- Do NOT modify original `core/` unless the task explicitly allows it.
- Do NOT merge TRACK0 and TRACK1 claims/test counts.
- Do NOT claim universal domain independence, LLM-assessor accuracy, real-world
  VAPT superiority, or Level-3 validation. Those are prohibited/ parked.
- No thesis writing, no Stage-2 platform build.
- One agent per workstream at a time; no parallel edits to the same files.

====================================================================
## T-DE-TESTS
====================================================================
TASK ID: T-DE-TESTS
AGENT ROLE: implementation agent (scoped coding + tests)
OBJECTIVE: Add a dedicated pytest regression suite for decision_engine/ so the
  new engine has the same automated safety net as TRACK0's 39 tests.
CURRENT VERIFIED CONTEXT:
  - decision_engine/core/{schemas,assessor,executor,engine}.py exist and import
    ONLY decision_engine.core.* (boundary verified by grep, see 02_AUTHORITY_RECONCILIATION.md §A).
  - decision_engine/adapters/vapt_adapter.py is the only VAPT-coupled file.
  - Currently NO tests for decision_engine/ (0 tests run). TRACK0 core/ = 39/39.
  - Engine API: run_engine(candidates, assess_fn, executor, max_attempts, mode);
    Executor(mode, execute_fn); deterministic_assessor; ActionCandidate;
    save_checkpoint/load_checkpoint.
EXACT SCOPE: Create decision_engine/tests/test_engine.py (+ conftest if needed)
  covering: schema validation; priority ordering; success advances immediately;
  failure increments attempt_count; below-threshold retry; threshold pivot;
  bounded termination (no infinite loop); checkpoint create; resume reproduces
  state; generic executor calls supplied execute_fn; adapter import boundary.
ALLOWED FILES:
  - decision_engine/tests/test_engine.py (new)
  - decision_engine/tests/conftest.py (new, if needed)
  - decision_engine/__init__.py (import only)
FORBIDDEN FILES:
  - core/ (original VAPT prototype) — DO NOT touch
  - decision_engine/core/*.py — DO NOT modify (only test against them)
  - any docs except a test-status note
ACTIONS NOT ALLOWED:
  - No changes to engine logic to make tests pass (fix only test harness, or
    flag a real bug to Hermes instead of patching engine silently).
  - No new features. This is a regression net only.
REQUIRED VERIFICATION:
  - `python -m pytest decision_engine/tests/ -q` => all pass
  - `python -m pytest tests/ -q` => 39 passed (must stay green)
  - Report counts separately: "General engine: X/X; Frozen baseline: 39/39"
ACCEPTANCE CRITERIA:
  - >=12 explicit test functions (TEST-DE-01..12 from 01_TASK_REGISTER.md)
  - Both suites green; no overlap/merge of counts.
REQUIRED RETURN FORMAT:
  - test count, list of test names, pytest output tail, and a one-line note
    that TRACK0 39/39 still passes.
COMMIT RULES:
  - One atomic commit: "T-DE-TESTS: regression suite for decision_engine/ (X tests)".
  - Do not commit unrelated changes.
STOP CONDITIONS:
  - Stop and report (do not patch engine) if a test reveals a real engine bug.

====================================================================
## T-DE-BOUNDARY
====================================================================
TASK ID: T-DE-BOUNDARY
AGENT ROLE: independent reviewer (READ-ONLY, no modifications, challenge assumptions)
OBJECTIVE: Verify the generalized engine is genuinely domain-independent and that
  VAPT concepts did not leak into decision_engine/core/.
CURRENT VERIFIED CONTEXT:
  - 02_AUTHORITY_RECONCILIATION.md §A documents the boundary: grep for
    `from core import`/`core.`/`poc_corpus`/`labels.json` inside decision_engine/core/
    shows 0 VAPT code imports; vapt_adapter.py is the only boundary file.
  - The agnostic benchmark uses a synthetic "maintenance tasks" domain.
EXACT SCOPE: Read-only review of decision_engine/core/* and adapters/vapt_adapter.py.
  Challenge specifically:
  1. Do any VAPT/CVE/exploit assumptions hide in engine logic (not just docstrings)?
  2. Is the maintenance example structurally independent, or does it reuse the
     same data shapes as VAPT by accident?
  3. Is the generic Executor truly generic (any execute_fn) or VAPT-shaped?
  4. Does checkpoint state encode domain assumptions?
  5. Is the benchmark circular / structurally biased toward SMART?
ALLOWED FILES: read decision_engine/**, core/**, docs/roadmap/** (read-only)
FORBIDDEN FILES: none writable
ACTIONS NOT ALLOWED: any file write, any commit
REQUIRED VERIFICATION: a written findings list with PASS/FAIL per question above
ACCEPTANCE CRITERIA: explicit verdict per question + a short summary
REQUIRED RETURN FORMAT: markdown review under docs/roadmap/external_reviews/
  (you may write to a NEW review file path you create; do not edit other docs)
COMMIT RULES: reviewer does not commit; Hermes records findings.
STOP CONDITIONS: none (read-only).

====================================================================
## T-DE-BENCH
====================================================================
TASK ID: T-DE-BENCH
AGENT ROLE: independent reviewer (READ-ONLY) + light experiment design
OBJECTIVE: Review and improve the fairness, reproducibility, and structural bias
  of the engine's benchmarks (agnostic + VAPT), addressing RQ1-RQ4 from the
  authority review: scoring-information value, sensitivity to scoring errors
  (perfect/noisy/random/heuristic/LLM), pivot-policy comparison, domain-structure
  generalization.
CURRENT VERIFIED CONTEXT:
  - decision_engine/benchmarks/agnostic_benchmark.py: SMART 8 vs DUMB 17 on one
    synthetic task family with deterministic assessor.
  - tests/evaluate.py: TRACK0 SMART 5 req/0 loops vs DUMB 21/2 (VAPT simulation).
EXACT SCOPE: Critique both benchmarks; propose (do NOT implement) a small set of
  added synthetic task families + scoring-noise sweeps + pivot-policy baselines
  that would raise the evidence from "proof-of-mechanism" toward "validated".
ALLOWED FILES: read decision_engine/**, tests/**, docs/roadmap/** (read-only)
FORBIDDEN FILES: none writable
ACTIONS NOT ALLOWED: any file write except a NEW review doc; no commit
REQUIRED VERIFICATION: written list of biases found + a concrete experiment
  design (families, noise levels, baselines, metrics) for Hermes to later enact
ACCEPTANCE CRITERIA: >=3 concrete bias findings + >=1 experiment-design proposal
REQUIRED RETURN FORMAT: markdown under docs/roadmap/external_reviews/
COMMIT RULES: reviewer does not commit.
STOP CONDITIONS: none (read-only).

====================================================================
## T-DE-EVIDENCE
====================================================================
TASK ID: T-DE-EVIDENCE
AGENT ROLE: Hermes (final verification, reconciliation, governance) + reviewer input
OBJECTIVE: Reconcile evidence tiers and claims between TRACK0 (frozen VAPT) and
  TRACK1 (generalized engine) after T-DE-TESTS/BOUNDARY/BENCH return.
CURRENT VERIFIED CONTEXT: 02_AUTHORITY_RECONCILIATION.md §B evidence-separation
  table is the draft; it must be finalised once gates pass.
EXACT SCOPE: Update the evidence-separation table; confirm which claims are
  thesis-usable (A), qualify (B), or prohibited (C); keep tiers distinct.
ALLOWED FILES: docs/roadmap/02_AUTHORITY_RECONCILIATION.md (edit), 01_TASK_REGISTER.md
FORBIDDEN FILES: core/, decision_engine/core/*.py (no logic change)
ACTIONS NOT ALLOWED: claiming universal independence / LLM accuracy / real-world
  superiority / Level-3 unless evidence supports it.
REQUIRED VERIFICATION: updated table + final claim gate
ACCEPTANCE CRITERIA: every claim has a tier + a file:line or dataset reference
REQUIRED RETURN FORMAT: updated markdown doc
COMMIT RULES: one atomic commit after review sign-off.

====================================================================
## R1 (after gates)
====================================================================
TASK ID: R1
AGENT ROLE: research/review agent (documentation only, no source changes)
OBJECTIVE: Related-work section + dated Strix snapshot.
CURRENT VERIFIED CONTEXT: repo at /home/vinit/ai_vapt_framework; TRACK0 = VAPT
  prototype (GAP-1/2 evidence); TRACK1 = generalized engine (proof-of-mechanism).
EXACT SCOPE: Cover autonomous pentest agents (Strix w/ DATE, PentestGPT, others),
  LLM action-quality scoring, failure-aware/pivot planning, benchmark methodology.
ALLOWED FILES: docs/project_management/R1_RELATED_WORK.md (new)
FORBIDDEN FILES: all .py
ACTIONS NOT ALLOWED: source edits; bare "No" for related work.
REQUIRED VERIFICATION: comparison table; honest qualifiers (Not inspected /
  Inspected-not-found / Partially / Yes / N/A); dated Strix snapshot.
ACCEPTANCE CRITERIA: <600 words; no overclaim.
REQUIRED RETURN FORMAT: markdown deliverable.
COMMIT RULES: Hermes verifies then one atomic doc commit.

====================================================================
## R2 (after R1)
====================================================================
TASK ID: R2
AGENT ROLE: research/review agent (documentation only)
OBJECTIVE: Novelty / threat-to-novelty matrix.
EXACT SCOPE: mechanisms = Gap-1 pre-execution quality; Gap-2 attempt-counter+pivot;
  priority=prob*(0.5+0.5*quality); bounded termination; sim-vs-observed tiers.
  Every "Yes ours" cites file:line (decision_engine/core/engine.py or core/).
ALLOWED FILES: docs/project_management/R2_NOVELTY_MATRIX.md (new)
FORBIDDEN FILES: all .py
ACTIONS NOT ALLOWED: bare "No"; claims not backed by evidence (mark UNPROVEN).
REQUIRED VERIFICATION: matrix with honest qualifiers per related system.
ACCEPTANCE CRITERIA: <500 words; every ours-claim has file:line.
COMMIT RULES: Hermes verifies then one atomic doc commit.

====================================================================
## R3 (after R2)
====================================================================
TASK ID: R3
AGENT ROLE: research/review agent (documentation only)
OBJECTIVE: Approved thesis claim register (A may / B qualify / C prohibited).
EXACT SCOPE: seed facts from 02_AUTHORITY_RECONCILIATION.md §B (Level1 proven;
  Level2 n=2; LLM-accuracy NOT proven; Level3 NOT achieved; real-world NOT proven;
  "better than all VAPT systems" PROHIBITED). Register governs all thesis writing.
ALLOWED FILES: docs/project_management/R3_CLAIM_REGISTER.md (new)
FORBIDDEN FILES: all .py
REQUIRED VERIFICATION: each claim tier + caveat (for B) + file:line or dataset.
ACCEPTANCE CRITERIA: <500 words; single source of truth for claims.
COMMIT RULES: Hermes verifies then one atomic doc commit.

====================================================================
## R4 (after R3)  +  R5-R7 (final)
====================================================================
TASK ID: R4
AGENT ROLE: independent reviewer (READ-ONLY challenge)
OBJECTIVE: Challenge R1-R3; list weakest claim, biggest overclaim risk, missing
  baseline; specifically test whether the agnostic benchmark proves independence
  or just reuses pivot logic with different labels.
ALLOWED FILES: docs/project_management/external_reviews/R4_challenge.md (new)
FORBIDDEN FILES: all .py
REQUIRED RETURN FORMAT: 3-5 concrete threats to novelty.

TASK ID: R5-R7
AGENT ROLE: research/review agent + authority
OBJECTIVE: Final methodology + evidence reconciliation + GO/NO-GO for thesis writing.
ALLOWED FILES: docs/project_management/12_GO_NO_GO.md (new)
FORBIDDEN FILES: all .py
REQUIRED VERIFICATION: consolidated evidence map (Level1/2), R3 as claim gate,
  honest venue fit, explicit GO/NO-GO. Tie items to file:line or datasets/.
