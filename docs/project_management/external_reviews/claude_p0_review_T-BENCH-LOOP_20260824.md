# READ-ONLY P0 Validity Review — T-BENCH-LOOP (evaluate.py)

_Reviewer: Claude Code (read-only subagent, deleg_8ca6c7e7), 2026-08-24._
_Reviewed: tests/evaluate.py T-BENCH-LOOP fix (git diff)._

## Verdict: APPROVE

All 9 checklist items CONFIRMED. No code changes required; non-blocking doc follow-ups only.

### Checklist
- A. Pre-fix literal `smart_loop = 0` constant — CONFIRMED (removed line).
- B. Diff removes constant; computes from final["results"] via Counter over r["cve"], sum max(0,count-threshold) (evaluate.py:74-75) — CONFIRMED.
- C. Measurement derived from real execution results (instrumented, not asserted) — CONFIRMED.
- D. Runtime `assert max_per_cve <= threshold` (evaluate.py:81-86); verified live to fire on broken pivot (3>2) — CONFIRMED. Governance §9 satisfied.
- E. DUMB baseline loop measurement intact (loops += 1 at attempts>=hard_cap) — CONFIRMED, no regression.
- F. CSV format preserved; SMART=0/5reqs, DUMB=2/21reqs; SMART reqs < DUMB — CONFIRMED.
- G. Scope confined to tests/evaluate.py (git status M tests/evaluate.py only; core/ untouched) — CONFIRMED.
- H. `import core` OK; graph terminates (agent_graph.py:136-142); request-efficiency (5<21) unaffected — CONFIRMED.
- I. Claimed guarantee matches behavior — CONFIRMED.

### Required follow-ups (non-blocking)
1. (Done) Re-run end-to-end in Ollama env — CSV regenerated SMART loop_events=0.
2. Add pytest assertion for SMART <= max_attempts/finding — tracked under T-TESTS.
3. (Done) Update 09_BENCHMARK_EVIDENCE.md to drop "asserted, not measured" footnote.
