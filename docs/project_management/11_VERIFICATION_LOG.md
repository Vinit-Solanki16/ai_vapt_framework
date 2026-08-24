# 11 — INDEPENDENT RE-VERIFICATION LOG (STEP 1)

_Date: 2026-08-24 — performed by Hermes under TOP AUTHORITY DIRECTIVE reconciliation._
_Purpose: treat all prior recap claims as REPORTED STATE; reproduce independently; record only._

## Environment
- WSL2, Python 3.10 venv at /home/vinit/ai_vapt_framework/venv, Ollama llama3.2:3b serving.
- Git: HEAD 21b0917, master, working tree CLEAN. Baseline 31ccd06.

## Results table
| ID | Check | Command | Result | Kind |
|----|-------|---------|--------|------|
| V1 | import core | `python -c "import core"` | PASS (25 syms) | controlled |
| V2 | phantom functions absent | `grep -rnE "normalize_data_model\|select_exploit_candidate\|..."` | ABSENT → confirms D-001 REJECTED valid | repo-truth |
| V3 | benchmark loop assertion | `grep smart_loop tests/evaluate.py` | `smart_loop = 0` at line 101 → R-003 CONFIRMED | repo-truth |
| V4 | scanner JSON | `python -m core.scanner data/sample_scan.json` | PASS (2 findings, EPSS ranked) | controlled |
| V5 | scanner Nmap XML | `python -m core.scanner data/live_scan.xml` | PASS (1 finding, UNKNOWN-CVE EPSS 0) | controlled |
| V6 | EPSS live API | `fetch_epss_score('CVE-2021-44228')` | PASS = 0.99999 (LIVE) | real observed |
| V7 | agent pivot/terminate | `python -m core.agent_graph` | PASS (validates CVE-2021-44228, pivots, terminates, no loop) | controlled/sim |
| V8 | benchmark | `python tests/evaluate.py` | PASS → SMART 5 req / 0 loops* / DUMB 21 / 2 loops | simulation |
| V9 | report gen | build_report+save_json/pdf | PASS (json+pdf written) | controlled |
| V10 | app import | `python -c "import app"` | PASS; earlier Streamlit boot HTTP 200 | controlled |

## Safety re-verification (R-001 / T-SAFE P0)
- `core/executor.py:101-137`: simulation mode is label-driven (safe, no network). REAL mode (108-137): for non-LOW findings on a reachable host, shells `python <corpus>/<CVE>.py` (line 128 subprocess.run). CVE-2021-44228.py (`data/poc_corpus/CVE-2021-44228.py:6-9`) sends a Log4Shell JNDI payload via `s.sendall(...)`. Success still taken from labels.json (line 134), output ignored. CONFIRMED genuine P0 safety+honesty gap. Default benchmark uses simulation, so V7/V8 do not trigger it.

## Reconciliation outcome
- Prior governance (STEP A/B/C: baseline 31ccd06, audit, master plan 02) is CONFIRMED by independent reproduction.
- Prior audit (claude_independent_audit_20260821.md) was correctly REJECTED (D-001): every phantom function it cited is ABSENT; its "randomized benchmark counts" claim is FALSE (no `import random`; counts are from real executor); only its genuine overlaps (safety of un-sandboxed PoC exec, add unit tests, empirical GAP-1 validation) were folded into tasks.
- The two P0 findings the master plan prioritizes are BOTH independently CONFIRMED:
  - T-BENCH-LOOP: `smart_loop = 0` hardcoded (evaluate.py:101) → loop-avoidance metric is ASSERTED, not measured. INVALID experiment until fixed.
  - T-SAFE: real-mode offensive shell-out + mislabeled "safe probe" → genuine safety gap.

## Conclusion
Repository state is largely reproduced and trustworthy for the SIMULATION results (requests 5 vs 21, no infinite loop). The headline "loop avoidance" and "real exploit success" claims are NOT yet measured/validated. Next authoritative task per 02_MASTER_PLAN execution order = **T-SAFE (P0)**, then **T-BENCH-LOOP (P0)** — both outrank the directive's Option A (corpus) and Option B (Docker).
