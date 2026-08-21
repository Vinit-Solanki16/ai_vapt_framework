# VERIFICATION BACKLOG — Autonomous AI VAPT Framework

Atomic, unstarted tasks. Ordered by dependency where it matters. Each task lists
priority, affected files, problem, evidence, required fix, acceptance criteria,
test command, and a suggested agent. **Nothing here has been fixed yet.**

Legend: P0=critical blocker, P1=high, P2=medium, P3=low.

---

## T1 — Initialize version control for reproducibility
- **Priority:** P1
- **Affected files:** repo root (new `.git`, `.gitignore`)
- **Problem:** No git repo; thesis needs reproducible, versioned baseline.
- **Evidence:** `git status` → *fatal: not a git repository*.
- **Required fix:** `git init`; add `.gitignore` (venv/, `__pycache__/`,
  `data/reports/`, `data/benchmark_results.csv` optional, `.env`); initial commit.
- **Acceptance:** `git rev-parse --is-inside-work-tree` → true; clean commit of
  current source.
- **Test command:** `git status --short` shows tracked source only.
- **Suggested agent:** github / shell

## T2 — Add a real pytest suite with assertions
- **Priority:** P0
- **Affected files:** `tests/test_core.py` (new), `core/schemas.py`,
  `core/scanner.py`, `core/executor.py`, `core/agent_graph.py`
- **Problem:** Only a smoke script exists; no `assert`, no regression safety net.
- **Evidence:** `search_files` for `assert` → none in repo; `tests/` has only
  `evaluate.py`; no `conftest.py`/`pytest.ini`.
- **Required fix:** Add unit tests: (a) `ExploitAssessment` rejects bad enum values;
  (b) `Finding.priority_score` ordering; (c) `parse_nmap_xml`/`parse_custom_json`
  produce expected findings; (d) `Executor(mode="simulation")` maps each label to
  correct `ExecutionOutcome`; (e) `run_agent` with `provider` stubbed terminates and
  never exceeds `max_attempts` per finding; (f) pivot advances on SUCCESS, abandons
  on threshold. Stub the LLM for graph tests (monkeypatch `assess_exploit_quality`)
  so tests are fast + offline.
- **Acceptance:** `pytest -q` green; covers schemas, scanner, executor(sim),
  agent_graph pivot/loop without network/LLM.
- **Test command:** `python -m pytest tests/ -q`
- **Suggested agent:** software-development (TDD skill)

## T3 — Make benchmark MEASURE loop avoidance instead of asserting it
- **Priority:** P0
- **Affected files:** `tests/evaluate.py`
- **Problem:** `smart_loop = 0` is hardcoded; the headline thesis metric
  (loops avoided) is asserted, not observed.
- **Evidence:** `evaluate.py:101` `smart_loop = 0  # by construction...`;
  `delta["loops_avoided"] = dumb["loops"] - smart_loop`.
- **Required fix:** Instrument the SMART run to detect any execute→execute cycle
  that would have exceeded a sane cap (e.g. count `attempt_count` max per finding; or
  wrap `app.invoke` and assert no finding is executed more than `max_attempts` times).
  Report measured value.
- **Acceptance:** `loops_avoided` derived from instrumented counts; assertion in test
  that SMART executes ≤ `max_attempts` per finding.
- **Test command:** `python tests/evaluate.py` + `python -m pytest tests/ -q`
- **Suggested agent:** software-development

## T4 — Add multi-seed / variance runs to the benchmark
- **Priority:** P1
- **Affected files:** `tests/evaluate.py`
- **Problem:** Single run, n=3; no confidence bounds; non-defensible for thesis.
- **Evidence:** `run_benchmark` runs once; CSV has one row per agent.
- **Required fix:** Loop N seeds; collect mean/stddev of requests, runtime, loops;
  shuffle finding order to prove ranking robustness; emit extended CSV.
- **Acceptance:** Report prints mean±std over ≥5 seeds; order-invariance check passes.
- **Test command:** `python tests/evaluate.py`
- **Suggested agent:** mlops/evaluation

## T5 — Reconcile README benchmark numbers with actual output
- **Priority:** P2
- **Affected files:** `README.md`
- **Problem:** README table says SMART=1 request; CSV shows 5. Stale/contradictory.
- **Evidence:** `README.md:76` "SMART | 1"; `data/benchmark_results.csv` "5".
- **Required fix:** Regenerate README table from a real run; clarify that the win is
  request + loop efficiency, NOT wall-clock (time_saved_s is negative).
- **Acceptance:** README numbers match latest CSV; negative time delta explained.
- **Test command:** `python tests/evaluate.py` then diff README vs CSV.
- **Suggested agent:** software-development

## T6 — Reconcile "real" executor semantics (safety/honesty)
- **Priority:** P0
- **Affected files:** `core/executor.py`, `core/executor.py` docstring, `README.md`
- **Problem:** Docstring calls real mode a "safe connectivity probe", but it also
  shells corpus `.py` modules (e.g. CVE-2021-44228 sends a JNDI payload) and ignores
  their output, trusting the label for success. Misleading + potentially unsafe
  against non-sandboxed targets.
- **Evidence:** `executor.py:125-137` shells `python <module> host port`;
  `data/poc_corpus/CVE-2021-44228.py:8-9` `sendall(...jndi...)`; success still from
  `_outcome_from_label`.
- **Required fix:** Either (a) make real mode connectivity-only (never shell corpus
  exploit modules; remove/guard that branch) OR (b) add an explicit
  `danger_mode=True` opt-in that documents real offensive sends and parses module
  stdout to set success. Update docstring + README accordingly.
- **Acceptance:** Default real mode performs NO offensive send; or dangerous branch
  requires explicit opt-in + warning; docstring matches behaviour.
- **Test command:** `python -c "from core.executor import Executor; ..."` asserting
  no subprocess for offensive modules in safe default.
- **Suggested agent:** cybersecurity (autonomous-vapt-agents)

## T7 — Grow PoC corpus to 8–12 labelled CVEs
- **Priority:** P1
- **Affected files:** `data/poc_corpus/*.py`, `data/poc_corpus/labels.json`
- **Problem:** n=3 corpus → thin benchmark, weak thesis defense.
- **Evidence:** checkpoint §3 blocker; 3 entries in labels.json.
- **Required fix:** Add 5–9 more real, heterogeneous labelled PoCs (mix of HIGH/MED/
  LOW reliability + varied outcomes) with consistent labels.json.
- **Acceptance:** labels.json has ≥8 entries; each has a corpus file or explicit
  "no-code" note; benchmark re-run reflects larger n.
- **Test command:** `python tests/evaluate.py` (after wiring new labels).
- **Suggested agent:** cybersecurity

## T8 — Verify / wire GitHub PoC fetch with a real token
- **Priority:** P2
- **Affected files:** `core/poc_corpus.py` (`fetch_github_poc`), `core/exploit_assessor.py`
- **Problem:** Online fetch branch is unverified (no GITHUB_TOKEN); corpus-growth path
  unproven.
- **Evidence:** `fetch_github_poc` returns None when token absent; never exercised.
- **Required fix:** With a token, run one authenticated fetch + score; add a test that
  mocks `requests` to assert parsing of `html_url`→raw URL and 401 handling.
- **Acceptance:** Mock test covers 200 + 401; live one-shot run documented.
- **Test command:** `python -m pytest tests/ -q` (mock) + manual token run.
- **Suggested agent:** github

## T9 — Verify OpenAI provider path or harden the fallback
- **Priority:** P2
- **Affected files:** `core/exploit_assessor.py` (`get_llm`), `app.py`
- **Problem:** OpenAI path untested; default `"dummy-key"` gives silent 401.
- **Evidence:** `get_llm` uses `"dummy-key"` when `OPENAI_API_KEY` unset.
- **Required fix:** Raise a clear error if provider=openai and no key; OR add a
  recorded/pytest-mock test hitting `ChatOpenAI.with_structured_output`.
- **Acceptance:** Clear error without key; structured output verified with a test key
  or mock.
- **Test command:** `python -m pytest tests/ -q`
- **Suggested agent:** software-development

## T10 — Add AgentState persistence / checkpointing (closes "checkpoint system" gap)
- **Priority:** P1
- **Affected files:** `core/agent_graph.py` (`run_agent`), new `core/checkpoint.py`
- **Problem:** No state saved between runs; no resume; "checkpoint/cron" absent.
- **Evidence:** `run_agent` returns in-memory dict; no disk write; no scheduler.
- **Required fix:** Serialize `AgentState` (findings, index, logs, results) to
  `data/checkpoints/run_<ts>.json` after each pivot; add `resume_agent(path)` that
  reloads and continues. Optionally a cron wrapper (out of scope for code audit).
- **Acceptance:** A run writes a checkpoint; `resume_agent` continues from saved index
  and yields identical final results.
- **Test command:** `python -m pytest tests/ -q` (resume test) or manual
  `python -m core.agent_graph` + resume.
- **Suggested agent:** software-development

## T11 — Remove dead `get_poc` export (or wire it in)
- **Priority:** P3
- **Affected files:** `core/poc_corpus.py`, `core/__init__.py`
- **Problem:** `get_poc` is exported but never called; assessor uses `corpus_lookup`
  + `fetch_github_poc` directly. Dead surface.
- **Evidence:** `search_files` shows `get_poc` only in definition + `__init__`.
- **Required fix:** Either delete `get_poc` + its `__init__` export, or have
  `assess_exploit_quality` call it (local-first resolver) for consistency with task2.md.
- **Acceptance:** No orphan export; or single resolver used everywhere.
- **Test command:** `python -c "import core"` + grep.
- **Suggested agent:** software-development (simplify-code)

## T12 — Provision Docker testbed + sandboxed live-exploitation path
- **Priority:** P1 (thesis-critical)
- **Affected files:** `core/executor.py` (real mode), infra (Dockerfile,
  docker-compose with DVWA/Metasploitable/crAPI)
- **Problem:** No live validation; weaponized payloads not shipped; "real" success is
  label-derived. Core contribution (validated exploitation) not demonstrable on a real
  target.
- **Evidence:** Docker DOWN; executor real mode trusts label; README §"Honest
  limitations".
- **Required fix:** Start Docker daemon; add an isolated vulnerable target; register
  sandboxed exploit modules; make real mode parse actual module outcome to set success
  (replacing label trust). Keep it opt-in + sandboxed.
- **Acceptance:** Real mode validates ≥1 CVE against a live container; success derived
  from observed outcome, not label.
- **Test command:** `python -c "from core.executor import Executor; ..."` against
  container.
- **Suggested agent:** cybersecurity (autonomous-vapt-agents)

---

## Dependency-ordered top 10 (recommended execution sequence)
1. **T1** init git (reproducibility baseline) — do first, nothing depends on it.
2. **T2** pytest suite (regression net for everything below).
3. **T3** measure loop avoidance (fixes headline metric before any demo).
4. **T6** reconcile real-mode safety/honesty (blocks safe demoing).
5. **T10** checkpoint/persistence (enables resume + run history).
6. **T7** grow corpus to ≥8 CVEs (stronger benchmark).
7. **T4** multi-seed variance (defensible stats).
8. **T5** fix README numbers (docs integrity).
9. **T12** Docker live-exploitation path (thesis-critical validation).
10. **T8/T9** verify GitHub + OpenAI paths (corpus growth + provider parity).

(T11 dead-code cleanup can ride along with T2/T9.)
