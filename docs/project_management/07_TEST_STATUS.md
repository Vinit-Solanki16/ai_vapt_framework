# 07 — TEST STATUS

_Updated after every task. Commands run from project root with venv active._

## Current test inventory
- **pytest suite** — PRESENT. `tests/test_core.py` (13 tests) + `tests/conftest.py`
  (offline: blocks network + records subprocess). Covers schemas enum validation,
  priority_score ordering, scanner JSON/XML, executor sim labels + real-mode no-shell-out,
  agent_graph pivot/termination + per-CVE <= max_attempts. All offline, deterministic.
  Runs: PASS (`python -m pytest tests/ -q` -> 13 passed, 0.09s). Added 2026-08-24 (T-TESTS).
- **tests/benchmark_var.py** — NEW (T-BENCH-VAR, 2026-08-24). Multi-seed variance harness:
  runs SMART+DUMB across 5 seeds, prints MEAN±STD, writes data/benchmark_variance.csv.
  Offline-deterministic; order-invariance check PASS. Runs: exit 0, 5/5 seeds OK.

- **tests/gap1_ablation.py** — NEW (T-GAP1-VALID, 2026-08-24). Controlled ablation: A_with_scoring
  vs B_no_scoring over 12 findings (uniform EPSS, offline LLM stub). MEASURED: WITH scoring reaches
  first success 4.00 requests / 2.00 positions earlier than WITHOUT. GAP-1 decision-relevance proven
  (simulation). Runs: exit 0, offline.
| Command | Result |
|---------|--------|
| `python -c "import core"` | OK (25 symbols) |
| `python -m core.scanner data/sample_scan.json` | 2 findings ranked by EPSS |
| `python -m core.scanner data/live_scan.xml` | 1 finding (UNKNOWN-CVE, EPSS 0) |
| `python -c "fetch_epss_score('CVE-2021-44228')"` | 0.99999 (LIVE API) |
| `python -m core.exploit_assessor CVE-2021-44228` | valid ExploitAssessment (real Ollama) |
| `python -m core.agent_graph` | end-to-end, terminates, no loop |
| `python tests/evaluate.py` | CSV written; SMART 5 / DUMB 21 |
| report save_json/save_pdf (to /tmp) | JSON 626B, PDF 2148B valid |
| executor real mode | LOW→SKIPPED, unreachable→FAIL_NO_TARGET |

## Per-task test status (governance §7 required evidence)
| Task | Required test | Status |
|------|---------------|--------|
| T-TESTS | `python -m pytest tests/ -q` | NOT RUN (suite absent) |
| T-BENCH-LOOP | `python tests/evaluate.py` + pytest | NOT RUN |
| T-SAFE | executor assertion (no offensive send by default) + pytest | NOT RUN |
| T-CORPUS | `python tests/evaluate.py` | NOT RUN |
| T-BENCH-VAR | `python tests/evaluate.py` | NOT RUN |
| T-GAP1-VALID | `python tests/evaluate.py` + pytest | NOT RUN |
| T-DOCKER | container executor run | NOT RUN (Docker down) |
| T-OPENAI | `python -m pytest tests/ -q` (mock) | NOT RUN |
| T-CHECKPOINT | `python -m pytest tests/ -q` | NOT RUN |
| T-REQPIN | clean-venv `python -c "import core"` | NOT RUN |
| T-GITHUB | `python -m pytest tests/ -q` (mock) | NOT RUN |
| T-README | diff README vs CSV | NOT RUN |
| T-DEADCODE | `python -c "import core"` + grep | NOT RUN |
| T-UI | `streamlit run app.py` | NOT RUN |

## Convention
On each completed task: record command + output + pass/fail here. DONE requires green required test
and no regression (re-run `python -c "import core"` + affected module smoke).
