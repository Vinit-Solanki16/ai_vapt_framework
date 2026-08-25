# 09 — BENCHMARK EVIDENCE

Governance §9: every thesis-relevant metric must be genuinely measured. SIMULATION vs CONTROLLED
VALIDATION vs REAL OBSERVED RESULT must be distinguished. No claims of speed/stealth/real-success
unless measured.

## What is MEASURED today (verified 2026-08-21)
- **Request counts** — from actual Executor.request_count instrumentation (simulation mode: 1/call).
  SMART run = 5 requests, DUMB run = 21 requests (re-run confirmed, deterministic).
- **Completion %** — validated/total = 33.3% (1 of 3 labelled findings exploitable).
- **Loop events (DUMB)** — genuinely counted: DUMB retries to hard_cap=10 → 2 loop events.
- **Loop events (SMART)** — MEASURED from final["results"] (Counter over CVE, sum max(0,count-threshold)); runtime `assert max_per_cve <= threshold` raises on pivot breach. Fixed by T-BENCH-LOOP (2026-08-24, VERIFIED).
- **Runtime** — measured via time.time() but NOT isolated per LLM call; SMART slower (8.5s) due to
  Ollama latency. time_saved_s = NEGATIVE (-8.5s). Do NOT claim speed win.

## What is SIMULATION (label truth, not observed)
- Exploit SUCCESS/FAIL_* outcomes resolved from data/poc_corpus/labels.json.
- Real-mode success is ALSO label-derived (no live validation) — must be labeled SIMULATION.

## Required future evidence (gates)
- T-BENCH-LOOP: instrumented SMART loop count (replace asserted 0).
- T-BENCH-VAR: mean±std over ≥5 seeds; order-invariance.
- **GAP-1 ablation (T-GAP1-VALID, VERIFIED 2026-08-24):** `tests/gap1_ablation.py` runs A_with_scoring
  vs B_no_scoring over 12 findings (uniform EPSS=0.5, offline LLM stub). MEASURED (not hardcoded):
  first-success request A=1 vs B_mean=5.00 (DELTA +4.00); index A=0 vs B_mean=2.00 (DELTA +2.00).
  Usability signal alone re-routes agent ~4 requests earlier to a labeled-success finding.
  **HONESTY CAVEAT (thesis-critical):** corpus reliability->outcome is 100% correlated for HIGH/LOW,
  so WITH-scoring is effectively GUARANTEED success at index 0. The delta is a BEST-CASE UPPER BOUND
  proving the *mechanism*, NOT a realistic estimate of production LLM-assessor efficacy. Valid as
  GAP-1 proof-of-mechanism only; real-world efficacy needs the production assessor on unseen CVEs
  (future work / T-DOCKER-adjacent). n=12 small.
- **GAP-1 ablation v2 (T-GAP1-VALID directive-exact, 2026-08-24): `tests/ablation.py`** —
  ARM A = full SMART ranking (EPSS x usability via priority_score), ARM B = RAW-EPSS-only
  ranking (usability NOT used for routing; pivot N=2 ENABLED in BOTH arms); n=12 corpus;
  frozen synthetic EPSS inputs (documented in-file); outcomes from labels.json only.
  MEASURED (data/ablation_epss_only.csv):
    * wasted_attempts_total       : A=14, B=14, DELTA=0
    * wasted_before_first_success : A=0,  B=2,  DELTA=+2 (B burns both attempts of its
      budget on the high-EPSS/LOW-usability dead end CVE-2023-34362 before foothold)
    * requests_to_first_success   : A=1,  B=3,  DELTA=+2
    * completion_%                : 100.0 BOTH arms (all labeled successes validated)
  STRUCTURAL FINDING (thesis-relevant): with pivot enabled in both arms and full-corpus
  coverage, TOTAL wasted attempts are IDENTICAL by mechanism — bounded retries neutralize
  routing mistakes at portfolio level. Scoring's measurable value is ROUTING EFFICIENCY:
  fewer wasted attempts BEFORE the first validated success and earlier foothold. Claim row
  updated accordingly (YES with scope conditions).
- T-DOCKER: REAL OBSERVED RESULT — success from actual module output in container-isolated testbed (not label) [future gate].

## Controlled observed validation achieved (2026-08-25, loopback tier — NOT container-isolated)
T-DOCKER Stage B was executed against a purpose-built Flask lab emulator on **loopback
(127.0.0.1)** because the Docker daemon was unavailable. This is a separate, honestly-scoped
**CONTROLLED OBSERVED-VALIDATION** tier:
- Execution I/O flowed to a REAL subprocess; module stdout/stderr were parsed by
  `core/executor.py:_parse_module_output` (NOT labels.json).
- Emulator access logs independently corroborate each attempt (S1: 1 GET /vuln; S2: exactly 2 GET /fail).
- GAP-1 (RQ1): observed SUCCESS reached at attempt 1 via the HIGH-usability candidate (module printed `VULNERABLE`).
- GAP-2 (RQ2): observed FAILURE -> pivot after `max_attempts=2`; exactly 2 executions, then pivot, clean termination, NO 3rd attempt (no loop).
- **Honest limitation:** runs were on loopback process isolation with benign GET probes, NOT a
  container/bridge network with no egress. Do NOT label this "Docker-isolated" or "container-sandboxed."
  Full T-DOCKER-as-specified (bridge/internal network) remains an OPTIONAL future upgrade.
- Reproducible via `tests/run_tdocker_scenarios.py`; raw run artifacts gitignored, metadata retained.
- 39 tests pass (incl. `test_executor_allowlist`, `test_danger_mode_mock`).

## Latest raw run (2026-08-21, simulation)
```
agent          runtime_s  requests  validated  completion_%  loop_events
SMART (framework)   8.546         5          1          33.3            0*
DUMB (baseline)     0.000        21          1          33.3            2
* SMART loop_events asserted, not measured (T-BENCH-LOOP fixes this)
Improvement (SMART over DUMB): requests_saved=16, loops_avoided=2*, time_saved_s=-8.546
```

## Claim permissibility matrix
| Claim | Supported? | Condition |
|-------|-----------|-----------|
| Fewer requests via early pivot | YES | measured (5 vs 21) |
| Loop avoidance (SMART) | PARTIAL | structural proof; needs measured metric (T-BENCH-LOOP) |
| Faster than DUMB | NO | time_saved_s negative |
| Stealthier / less network noise | NO | not measured |
| Real exploit success demonstrated | NO | simulation; needs T-DOCKER |
| GAP-1 scoring improves outcomes | YES for routing efficiency; NO for total-attempt/completion parity | MEASURED (tests/ablation.py, EPSS-only baseline, n=12): wasted-before-first-success 0 vs 2 and foothold 2 requests sooner WITH scoring; total waste identical (14 vs 14) and completion identical (100%) because pivot bounds retries in BOTH arms. Simulation, frozen synthetic EPSS inputs, stubbed assessor — proof-of-mechanism scope, not production efficacy. |
