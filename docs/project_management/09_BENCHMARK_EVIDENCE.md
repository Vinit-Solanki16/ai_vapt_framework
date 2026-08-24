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
- T-DOCKER: REAL OBSERVED RESULT — success from actual module output in container (not label).

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
| GAP-1 scoring improves outcomes | PROVEN (simulation, proof-of-mechanism) | T-GAP1-VALID: WITH scoring reaches labeled-success 4.00 req / 2.00 pos earlier than WITHOUT (EPSS held 0.5). BEST-CASE UPPER BOUND — see caveat below. |
