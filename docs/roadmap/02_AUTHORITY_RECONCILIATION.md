# AUTHORITY RECONCILIATION — TRACK 0 vs TRACK 1 (2026-08-27)

_Authority review after the Stage-1 `decision_engine/` was created and committed
at HEAD `97eef40`. This report establishes the TRUE CURRENT STATE from the
repository itself. No source code was modified during this review._

## A. CURRENT ARCHITECTURE

### (i) General decision engine + domains (the new framing)
```
GENERAL AUTONOMOUS DECISION ENGINE  (decision_engine/core/  — domain-free)
        |
        +-- VAPT adapter / current research prototype   (adapters/vapt_adapter.py)
        |
        +-- OTHER FUTURE DOMAIN ADAPTERS (none yet)
```
The engine core (`schemas`, `assessor`, `executor`, `engine`) contains NO VAPT,
CVE, PoC, or exploit references in code — only in explanatory docstrings.
Verified: grep for `from core import` / `core.` / `poc_corpus` / `labels.json`
inside `decision_engine/core/` returns ZERO code imports; all imports are
`decision_engine.core.*`. The only file importing the VAPT `core` is
`adapters/vapt_adapter.py` (by design).

### (ii) Future full VAPT platform (Stage 2 — NOT started)
```
FUTURE FULL AUTONOMOUS VAPT PLATFORM
        |
        +-- target ingestion (URL/IP/network)        [future]
        +-- discovery / recon                        [future]
        +-- tool integrations (Nmap, Nuclei, ...)    [future]
        +-- finding normalization                    [future]
        +-- decision engine  (decision_engine/)      [exists, being verified]
        +-- controlled Level-3 validation (Docker)    [parked]
        +-- reporting / dashboard                     [future]
```
Stage 2 is explicitly NOT started. The original `core/` remains the VAPT
research prototype and evidence baseline.

## B. EVIDENCE SEPARATION TABLE

| Claim | Workstream | Tier | Supporting experiment / test | Limitations | Thesis-usable today? |
|-------|-----------|------|------------------------------|------------|----------------------|
| SMART beats DUMB (fewer attempts, bounded loop) on VAPT corpus | TRACK 0 | Level 1 SIM | `tests/evaluate.py` (5 req/0 loops vs 21/2); `tests/test_ttests_gaps.py` | Simulation only; labels.json ground truth | YES (claim scoped to simulation) |
| Gap-1 ablation: scoring changes outcomes vs EPSS-only | TRACK 0 | Level 1 SIM | `tests/gap1_ablation.py` | Simulation; LLM assessor is local Ollama | YES (scoped) |
| Gap-2: per-CVE attempt counter + pivot at threshold, bounded termination | TRACK 0 | Level 1 SIM + Level 2 OBS | `tests/test_core.py` pivot tests; `tests/run_tdocker_scenarios.py` (S1/S2, n=2) | Observed assessor was deterministic stub | YES (mechanism proven; LLM-accuracy NOT) |
| Real mode fires no offensive send by default (safety) | TRACK 0 | Code review | `tests/test_executor_allowlist.py`; `test_danger_mode_mock.py` | danger_mode parses real subprocess I/O | YES (safety claim) |
| Checkpoint / resume | TRACK 0 | Level 1 | `tests/test_checkpoint.py` | — | YES |
| Engine is domain-independent (architecturally) | TRACK 1 | Code inspection | import-grep boundary check (this report §A) | Architectural only; not experimental proof | YES (architectural claim only) |
| Engine bounds repeated failure on a NON-VAPT domain | TRACK 1 | Loop-bound demo (NOT a fair baseline win) | `decision_engine/benchmarks/agnostic_benchmark.py` | **BIASED (T-DE-BOUNDARY Q5 FAIL):** SMART cap=2 vs DUMB cap=5 — the 8-vs-17 gap is the cap asymmetry, not Gap-1 priority. With a fair DUMB cap=2, DUMB also = 8. Single synthetic family; deterministic assessor; Gap-1 never isolated. | NO — do NOT use 8-vs-17 as evidence of SMART superiority. Re-scope via T-DE-BENCH (same cap + budget-at-N + priority-isolation). |
| LLM assessor accuracy on unseen CVEs | TRACK 0/1 | NOT proven | — | No experiment | NO (prohibited) |
| Universal domain independence | TRACK 1 | NOT proven | — | One synthetic family | NO (prohibited) |
| Real-world VAPT superiority | TRACK 0/1 | NOT proven | — | No live multi-target eval | NO (prohibited) |
| Level 3 Docker-isolated observed validation | TRACK 0/1 | PARKED | — | Docker down | NO (parked) |

## C. NEW GENERALIZED ENGINE STATUS

`decision_engine/` is classified as a **Stage-1 generalized architecture branch**.
Its maintenance-task benchmark is explicitly classified as:

> **Loop-bound demonstration (NOT a fair-baseline win).**

T-DE-BOUNDARY (Q5, FAIL) found the benchmark structurally biased: SMART uses
`max_attempts=2` while DUMB retries up to 5, so the reported "8 vs 17" gap is the
retry-cap asymmetry, not Gap-1 priority. With a fair DUMB cap=2, DUMB also = 8.
The benchmark therefore proves only that the engine runs and bounds a retry loop
on a non-VAPT domain — a narrow proof-of-mechanism. It does NOT validly show
"SMART beats DUMB because of intelligent prioritization," and the 8-vs-17 figure
must NOT appear as evidence of superiority in any thesis text. The engine's
**architectural** domain independence (Q1–Q4 PASS) stands; the cross-domain
*evidence* must be re-scoped through T-DE-BENCH (same cap + budget-at-N +
priority-isolation + scoring-noise sweeps).

## D. FREEZE STATUS

- **TRACK 0 (original VAPT `core/`): FROZEN** as the evidence baseline.
  39/39 passing. Do not modify unless a separately approved task requires it.
- **TRACK 1 (`decision_engine/`): NEW, PENDING VERIFICATION.** Not eligible for
  thesis claims beyond an architectural + proof-of-mechanism description until
  T-DE-TESTS, T-DE-BOUNDARY, and T-DE-BENCH pass.
- Datasets (`datasets/`) are evidence inputs, not code; frozen as captured.
- Implementation freeze interpreted strictly: TRACK 1 code is committed but its
  research claims are gated behind verification, not merged with TRACK 0's.

## E. EXACT NEXT GATES (sequence before thesis writing)

```
T-DE-TESTS   dedicated pytest regression suite for decision_engine/      [GATE 1]
T-DE-BOUNDARY independent read-only architecture / domain-leakage review [GATE 2]
T-DE-BENCH   benchmark fairness / reproducibility / structural-bias review[GATE 3]
T-DE-EVIDENCE reconcile evidence tiers + claims (TRACK0 vs TRACK1)        [GATE 4]
        ---- only after all four gates ----
R1  related work + dated Strix snapshot
R2  novelty / threat-to-novelty matrix
R3  claim register (A may / B qualify / C prohibited)
R4  independent challenge review
R5-R7 final methodology + evidence reconciliation + GO/NO-GO
```

Thesis writing (A7) and Stage-2 platform build are NOT started until R5-R7
returns GO.

## Boundary verification appendix (reproducible)
```
$ grep -rn "from core import\|core\.\|poc_corpus\|labels.json\|exploit_assessor" decision_engine/core/
  -> only decision_engine.core.* imports; 0 VAPT code imports
$ grep -rln "core" decision_engine/adapters/vapt_adapter.py
  -> vapt_adapter.py is the ONLY boundary-crossing file (by design)
$ python -m pytest tests/ -q   -> 39 passed   (TRACK0 unchanged)
$ python -m pytest decision_engine/ -q  -> no tests ran  (0 regression tests)
```
