# 07 — TEST STATUS

_Updated after every task. Commands run from project root with venv active._

## Current test inventory
- **pytest suite** — PRESENT. `tests/test_core.py` (13 tests) + `tests/conftest.py`
  (offline: blocks network + records subprocess). Covers schemas enum validation,
  priority_score ordering, scanner JSON/XML, executor sim labels + real-mode no-shell-out,
  agent_graph pivot/termination + per-CVE <= max_attempts. All offline, deterministic.
- **requirements.txt** — PINNED for reproducible builds (T-REQPIN, 2026-08-24). Exact
  (==) versions captured from the verified venv (Python 3.10); `.python-version` pins 3.10;
  README setup documents the `pip install -r requirements.txt` repro path.
- **tests/test_checkpoint.py** — NEW (T-CHECKPOINT, 2026-08-24, +8 tests → suite total 29).
  AgentState persistence in `core/agent_graph.py`: save_checkpoint() serializes state to JSON
  (findings → plain dicts, enums as strings, auto-creates dirs, versioned payload);
  load_checkpoint() rebuilds Finding models (pydantic re-coerces enums) and rejects unknown
  checkpoint versions; resume_agent() re-invokes the graph from current_index with the entry
  node derived from persisted status (ASSESSING→assess, TESTING→execute, SUCCESS→pivot —
  so a validated CVE is NEVER replayed and COMPLETED checkpoints are a no-op).
  Proven: interrupt mid-run (after target #1 SUCCESS + one failed attempt on #2) →
  save → load → resume reproduces EXACTLY the fresh run's final results
  (results list equality, status COMPLETED, index == len(findings), ≤ max_attempts per CVE).
  All offline via conftest. Runs: PASS (see commands below).
- **tests/test_openai_provider.py** — NEW (T-OPENAI, 2026-08-24, +3 tests → suite total 21).
  OpenAI provider branch of `core/exploit_assessor.get_llm()`: ChatOpenAI stubbed at the module
  boundary so NO network/API key needed; asserts assess_exploit_quality(provider="openai")
  returns an enum-constrained ExploitAssessment via the SAME with_structured_output(ExploitAssessment)
  contract as Ollama (constructor kwargs verified: gpt-4o-mini, SecretStr key, temperature=0.1);
  missing OPENAI_API_KEY -> immediate clear RuntimeError (fail-safe, never hangs, dummy-key
  fallback removed). **Live OpenAI path UNVERIFIED without a real key** (offline stub only).
  Runs: PASS (see commands below).
- **tests/benchmark_var.py** — NEW (T-BENCH-VAR, 2026-08-24). Multi-seed variance harness:
  runs SMART+DUMB across 5 seeds, prints MEAN±STD, writes data/benchmark_variance.csv.
  Offline-deterministic; order-invariance check PASS. Runs: exit 0, 5/5 seeds OK.

- **tests/gap1_ablation.py** — NEW (T-GAP1-VALID, 2026-08-24). Controlled ablation: A_with_scoring
  vs B_no_scoring over 12 findings (uniform EPSS, offline LLM stub). MEASURED: WITH scoring reaches
  first success 4.00 requests / 2.00 positions earlier than WITHOUT. GAP-1 decision-relevance proven
  (simulation). Runs: exit 0, offline.
- **tests/test_ttests_gaps.py** — NEW (T-TESTS extension, 2026-08-24, +5 tests → suite total 18).
  Covers directive gaps: (b) assess_exploit_quality full path with MOCKED LLM boundary returns
  enum-constrained ExploitAssessment (+ malformed-LLM-output rejection); (c) run_agent pivots,
  terminates, ZERO loop events (exceedances = Σ max(0, n_cve − max_attempts) == 0, from runtime
  trace; future `loop_events` state field asserted empty if present); (d) simulation executor
  resolves EVERY labels.json entry (data-driven, currently 12 CVEs); (e) real mode UNREACHABLE
  host -> FAIL_NO_TARGET, request_count==1, no subprocess. All offline via conftest.
  Runs: PASS (`python -m pytest tests/ -q` -> 18 passed, 0.09s).

## Last executed commands
| Command | Result |
|---------|--------|
| `venv/bin/python -m pytest tests/ -q` (2026-08-24, T-CHECKPOINT) | **29 passed in 0.11s** (21 prior + 8 test_checkpoint), 0 failed; `python -c "import core"` OK — run_agent refactor is behaviour-preserving (state init extracted to initial_agent_state; build_vapt_graph gained an optional entry param defaulting to "assess") |
| `venv/bin/python -m pytest tests/ -q` (2026-08-24, T-OPENAI) | **21 passed in 0.09s** (18 prior + 3 test_openai_provider), 0 failed; `python -c "import core"` OK — no core regression (only provider branch of exploit_assessor touched) |
| `venv/bin/python -m pytest tests/ -q` (2026-08-24, T-TESTS extension) | **18 passed in 0.09s** (13 test_core + 5 test_ttests_gaps), 0 failed |
| CLAUDE CODE read-only review (T-TESTS extension, same date) | VERDICT: APPROVE — scope clean (3 allowed paths only); coverage (a)-(e) complete; offline guard effective; no regression risk found |
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
| T-TESTS | `python -m pytest tests/ -q` | DONE 2026-08-24 — PASS: 18 passed, 0.09s (test_core 13 + test_ttests_gaps 5); requirements.txt += pytest>=7.0; CLAUDE CODE read-only P3 review: **APPROVE** (checklist A–F all PASS; 2 LOW + 4 INFO non-blocking notes). Scope verified confined to tests/test_ttests_gaps.py + requirements.txt + this file. Register (03) not updated by this task (forbidden scope) — Hermes to reconcile. |
| T-CORPUS | `python tests/evaluate.py` + pytest | PASS 2026-08-24 (independent re-verification) — corpus already grown to **12 CVEs** (commit 3fa2148): 12/12 modules py_compile OK; 12/12 labels resolve via corpus_lookup (no empty); outcome mix success×5 / fail_timeout×3 / fail_syntax×2 / fail_dependency×2; reliability HIGH×4 / MED×5 / LOW×3; content matches labels (e.g. CVE-2023-34362 intentionally malformed = fail_syntax). `python tests/evaluate.py` → SMART 5 req/0 loops, DUMB 21 req/2 loops, exit 0; `pytest tests/ -q` → 18 passed. No core/ changes made by this pass. |
| T-BENCH-LOOP | `python tests/evaluate.py` + pytest | NOT RUN |
| T-SAFE | executor assertion (no offensive send by default) + pytest | NOT RUN |
| T-CORPUS | `python tests/evaluate.py` | NOT RUN |
| T-BENCH-VAR | `python tests/evaluate.py` | NOT RUN |
| T-GAP1-VALID | `python tests/evaluate.py` + pytest | NOT RUN |
| T-DOCKER | container executor run | NOT RUN (Docker down) |
| T-OPENAI | `python -m pytest tests/ -q` (mock) | DONE 2026-08-24 — PASS: 21 passed, 0.09s. get_llm() OpenAI branch hardened (fail-safe RuntimeError on missing OPENAI_API_KEY; dummy-key fallback removed); ChatOpenAI stubbed in tests/test_openai_provider.py → enum-constrained ExploitAssessment via shared structured-output contract; Ollama path unchanged. **Live OpenAI path UNVERIFIED without a real key.** Scope: core/exploit_assessor.py (provider branch only) + tests/test_openai_provider.py + this file. |
| T-CHECKPOINT | `python -m pytest tests/ -q` | DONE 2026-08-24 — PASS: 29 passed, 0.11s (21 prior + 8 new in tests/test_checkpoint.py). save_checkpoint/load_checkpoint/resume_agent added to core/agent_graph.py ONLY; resume re-enters from current_index with status-derived entry node (no replayed/duplicated steps; COMPLETED = no-op); interrupted-run resume reproduces fresh-run results exactly. Fully offline (conftest guard asserted call_count==0). Scope: core/agent_graph.py + tests/test_checkpoint.py + this file. |
| T-REQPIN | clean-venv `python -c "import core"` | DONE 2026-08-24 — requirements.txt pinned to exact (==) versions matching the verified venv; `.python-version`=3.10; README setup documents repro; `import core` OK and `pytest tests/ -q` 29 passed (no behavior change). Reproducibility: pins == installed freeze (diff clean). |
| T-GITHUB | `python -m pytest tests/ -q` (mock) | NOT RUN |
| T-README | diff README vs CSV | NOT RUN |
| T-DEADCODE | `python -c "import core"` + grep | DONE 2026-08-24 — removed unused `get_poc` from poc_corpus.py AND its package re-export in core/__init__.py (import line + `__all__`). Verified: `grep -rn get_poc` returns nothing; `import core` OK (41 symbols); `pytest tests/ -q` 29 passed; agent_graph smoke unchanged. corpus_lookup/corpus_label/fetch_github_poc retained (used by assessor + tests). Hermes (P4) verified. |
| T-UI | `streamlit run app.py` | NOT RUN |

## Convention
On each completed task: record command + output + pass/fail here. DONE requires green required test
and no regression (re-run `python -c "import core"` + affected module smoke).
