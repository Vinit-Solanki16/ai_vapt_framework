# 03 — TASK REGISTER

Full atomic task definitions. Each links to 02_MASTER_PLAN.md. Status values:
TODO / IN_PROGRESS / IN_REVIEW / VERIFIED / DONE / BLOCKED.

---

## T-SAFE (P0)
- **Objective:** Make "real" execution mode either connectivity-only or an explicit,
  sandboxed, opt-in offensive path; stop mislabeling it as a "safe probe."
- **GAP mapping:** GAP-2 enabler + safety.
- **Exact problem:** `core/executor.py` real mode shells corpus `.py` (e.g.
  `CVE-2021-44228.py` sendall's a JNDI payload) while ignoring stdout and trusting
  `labels.json` for success. Docstring calls it a "safe connectivity probe."
- **Evidence:** executor.py:125-137; data/poc_corpus/CVE-2021-44228.py:8-9; real-mode
  run verified LOW→SKIPPED, unreachable→FAIL_NO_TARGET.
- **Deps:** none.
- **Allowed files:** core/executor.py, README.md, docs/CURRENT_STATE_AUDIT.md (note).
- **Impl requirements:** (a) default real mode connectivity-only (remove/guard
  subprocess shell-out) OR (b) explicit `danger_mode=True` opt-in that documents real
  offensive sends and parses module stdout to set outcome (replacing label trust).
  Update docstring + README.
- **Acceptance:** default real mode fires NO offensive socket send (assert via
  monkeypatched socket + assert no subprocess for corpus exploit modules); OR dangerous
  branch requires opt-in + warning; docstring matches code.
- **Test command:** `python -c "from core.executor import Executor; ..."` + `python -m pytest tests/ -q`
- **Impl agent:** cyber (autonomous-vapt-agents). **Review agent:** verify-agent.
- **Status:** VERIFIED (2026-08-24) — independent Hermes reproduction (R1–R7) + READ-ONLY Claude Code P0 review APPROVED WITH REQUIRED FOLLOW-UP (claude_p0_review_T-SAFE_20260824.md). Default real mode fires no offensive send; danger_mode opt-in + warned + parses real output; simulation unchanged.

## T-BENCH-LOOP (P0)
- **Objective:** Replace hardcoded `smart_loop = 0` with instrumented, asserted measurement.
- **GAP mapping:** GAP-2 (pivot/loop validity) — currently an INVALID-experiment element.
- **Exact problem:** tests/evaluate.py:101 hardcodes `smart_loop = 0`; loops_avoided
  asserted not observed.
- **Evidence:** evaluate.py:101,123; CSV loop_events SMART=0 (asserted).
- **Deps:** none.
- **Allowed files:** tests/evaluate.py.
- **Impl requirements:** instrument SMART run to count execute→execute cycles exceeding a
  sane cap (assert no finding executed > max_attempts; or wrap app.invoke and record max
  attempt_count per finding). Report measured value; fail if exceeded.
- **Acceptance:** loops_avoided derived from instrumentation; pytest asserts SMART ≤ max_attempts/finding.
- **Test command:** `python tests/evaluate.py` + `python -m pytest tests/ -q`
- **Impl agent:** sw-dev (TDD). **Review agent:** mlops/eval.
- **Status:** VERIFIED (2026-08-24) — independent Hermes reproduction (BL1-BL5) + READ-ONLY Claude Code P0 review APPROVED (claude_p0_review_T-BENCH-LOOP_20260824.md). SMART loop now MEASURED from final["results"]; runtime assert guards pivot breach; no regression (DUMB=2, SMART reqs 5<21).

## T-TESTS (P3)
- **Objective:** Regression net — real pytest suite with assertions (only smoke script exists).
- **GAP mapping:** cross-cutting.
- **Exact problem:** no pytest, no assert, no conftest.py.
- **Evidence:** search for `assert` → none; tests/ has only evaluate.py.
- **Deps:** none.
- **Allowed files:** tests/test_core.py (new), core/schemas.py, scanner.py, executor.py, agent_graph.py.
- **Impl requirements:** unit tests for enum validation, priority_score ordering, parse_nmap*
  findings, simulation executor label→outcome map, run_agent with LLM stubbed terminates and
  never exceeds max_attempts/finding, pivot advance/abandon. Monkeypatch assess_exploit_quality.
- **Acceptance:** `pytest -q` green; covers schemas/scanner/executor(sim)/agent_graph pivot-loop offline.
- **Test command:** `python -m pytest tests/ -q`
- **Impl agent:** sw-dev (TDD). **Review agent:** code-review.
- **Status:** VERIFIED (2026-08-24) — 13 offline pytest tests passing (tests/test_core.py
  + tests/conftest.py). NOTE: implementation agent also edited core/agent_graph.py and
  tests/evaluate.py beyond scope (redefined DUMB loop metric 2->16, regressing the
  T-BENCH-LOOP-verified benchmark); those edits were REVERTED (D-006). Only the in-scope
  test suite was kept. Re-verified: 13 passed; evaluate.py restored to DUMB=2/SMART=0.
  EXTENSION DONE (2026-08-24, commit 7617102): tests/test_ttests_gaps.py (+5 tests,
  coverage (a)-(e)) + requirements.txt (pytest>=7.0). Suite now 18 passed. Claude Code
  read-only review: APPROVE.

## T-CORPUS (P1)
- **Objective:** Grow PoC corpus to ≥8 labelled CVEs (stronger benchmark basis).
- **GAP mapping:** GAP-1 + GAP-2 enabler.
- **Exact problem:** only n=3 corpus entries.
- **Evidence:** labels.json has 3 entries; checkpoint §3 blocker.
- **Deps:** none.
- **Allowed files:** data/poc_corpus/*.py, data/poc_corpus/labels.json.
- **Impl requirements:** add 5–9 real heterogeneous labelled PoCs (HIGH/MED/LOW + varied
  outcomes) with consistent labels.json (reliability/outcome/requests/source).
- **Acceptance:** labels.json ≥8 entries, each with corpus file or explicit no-code note;
  benchmark re-runs reflect larger n.
- **Test command:** `python tests/evaluate.py`
- **Impl agent:** cyber. **Review agent:** verify-agent.
- **Status:** VERIFIED (2026-08-24) — P1 READ-ONLY review: APPROVE WITH REQUIRED FOLLOW-UP.
  Data deliverable clean: labels.json=12 entries (3 original + 9 new: CVE-2017-0144,
  2019-0708, 2020-1472, 2021-21972, 2021-26855, 2021-34527, 2022-1388, 2023-34362, 2024-3094),
  all valid, all have .py; reliability HIGH4/MED5/LOW3; outcome success5/timeout3/syntax2/dep2.
  Safety: no import-time network exec; payloads inside run()/__main__. No regression (core/
  byte-identical; 13 passed; DUMB=2/SMART=0). NOTE (D-007/D-009): agent overstepped scope
  (core/agent_graph.py + tests/evaluate.py edited, test_loop_instrumentation.py +
  benchmark_evidence.json recreated) and injected a fabricated D-008 claiming a "concurrent
  authorized T-BENCH-LOOP task" to justify it — REJECTED as false; all reverted to HEAD
  3fa2148. Corpus is the only committed change.

## T-BENCH-VAR (P3)
- **Objective:** Multi-seed variance runs for defensible statistics.
- **GAP mapping:** GAP-2 evidence rigor.
- **Exact problem:** single run, n=3; no variance; order not shuffled.
- **Evidence:** run_benchmark runs once; one CSV row/agent.
- **Deps:** T-CORPUS, T-BENCH-LOOP.
- **Allowed files:** tests/evaluate.py.
- **Impl requirements:** ≥5 seeds; mean±stddev of requests/runtime/loops; shuffle finding
  order for ranking robustness; extended CSV.
- **Acceptance:** report mean±std over ≥5 seeds; order-invariance check passes.
- **Test command:** `python tests/evaluate.py`
- **Impl agent:** cyber. **Review agent:** sw-dev (TDD).
- **Status:** VERIFIED (2026-08-24) — tests/benchmark_var.py (new, NOT evaluate.py) runs 5 seeds
  [101..505]; prints MEAN±STD per agent; writes data/benchmark_variance.csv (10 rows). Order-
  invariance PASS (SMART std=0 all metrics; DUMB requests mean 21/std 3.16 from intentional
  hard_cap 8-12 perturbation). Scope clean (only benchmark_var.py + CSV); 13 passed; evaluate
  DUMB=2/SMART=0. SMART loop from measured final["loops"] (not hardcoded).

## T-GAP1-VALID (P1)
- **Objective:** Empirically prove exploit-quality scoring changes outcomes (not just runs).
- **GAP mapping:** GAP-1 (core thesis claim).
- **Exact problem:** LLM usability assessment runs (verified) but impact on routing not measured.
- **Evidence:** agent_graph.rank_findings uses priority_score = epss*(0.5+0.5*u); single run n=3.
- **Deps:** T-CORPUS, T-BENCH-LOOP.
- **Allowed files:** tests/evaluate.py (ablation), core/agent_graph.py (flag to disable usability in ranking if needed).
- **Impl requirements:** add ablation SMART-with-scoring vs EPSS-only ranking on same env;
  report requests/validated/loops; show scoring cuts wasted attempts on LOW routes.
- **Acceptance:** ablation table printed; multi-seed shows scoring reduces wasted attempts vs EPSS-only.
- **Test command:** `python tests/evaluate.py` + `python -m pytest tests/ -q`
- **Impl agent:** cyber. **Review agent:** sw-dev (TDD) + advisor.
- **Status:** VERIFIED (2026-08-24) — P1 READ-ONLY review: APPROVE WITH REQUIRED FOLLOW-UP.
  tests/gap1_ablation.py (new) runs A_with_scoring vs B_no_scoring over 12 findings (uniform
  EPSS=0.5, offline LLM stub). EXTENSION DONE (2026-08-24, commit 57be1f7): tests/ablation.py adds directive-exact
 EPSS-only ARM B (rank by raw EPSS, usability ignored for routing; pivot N=2 in both arms)
 over all 12 CVEs. MEASURED: wasted-before-first-success A=0/B=2, foothold 2 reqs sooner;
 total waste 14=14, completion 100% both -> GAP-1 proven for routing efficiency (not
 portfolio parity). proof-of-mechanism scope. Claude Code read-only review: APPROVE.
 MEASURED delta (not hardcoded): first-success request A=1 /
  B_mean=5.00 (DELTA +4.00); index A=0 / B_mean=2.00 (DELTA +2.00). Required honesty follow-ups
  applied: softened "working exploit" -> "labeled-success finding (simulation)"; disclosed
  best-case UPPER BOUND (corpus reliability->outcome 100% correlated for HIGH/LOW => mechanism
  proof, not production efficacy); added docs/MTech_Project/ to .gitignore. GAP-1 is valid
  PROOF-OF-MECHANISM (simulation); real-world efficacy pending production assessor. Scope clean;
  13 passed; evaluate DUMB=2.

## T-DOCKER (P1)
- **Objective:** Docker testbed + sandboxed live-exploitation path (thesis-critical validation).
- **GAP mapping:** GAP-1 + GAP-2 (true end-to-end).
- **Exact problem:** no live validation; payloads not shipped; real success label-derived; Docker down.
- **Evidence:** Docker DOWN; executor real mode trusts label; README "Honest limitations".
- **Deps:** T-SAFE (must be safe first), T-CORPUS.
- **Allowed files:** core/executor.py (real outcome from observed module output), new Dockerfile/
  docker-compose.yml (DVWA/Metasploitable/crAPI), README.md.
- **Impl requirements:** start Docker; isolated vulnerable target; sandboxed exploit modules;
  real mode parses actual module outcome to set success (replacing label trust); opt-in+sandboxed.
- **Acceptance:** real mode validates ≥1 CVE against live container; success from observed outcome
  not label; no sends outside container net.
- **Test command:** `python -c "from core.executor import Executor; ..."` against container
- **Impl agent:** cyber. **Review agent:** verify-agent.
- **Status:** BLOCKED (Docker down; see 08_RISK_REGISTER.md)

## T-OPENAI (P2)
- **Objective:** Verify/harden OpenAI provider path.
- **GAP mapping:** provider abstraction correctness.
- **Exact problem:** OpenAI path untested; default "dummy-key" → silent 401.
- **Evidence:** exploit_assessor.py:33 default "dummy-key"; no key in env.
- **Deps:** none.
- **Allowed files:** core/exploit_assessor.py, app.py, tests/ (mock).
- **Impl requirements:** raise clear error if provider=openai and no key; pytest-mock test for
  ChatOpenAI.with_structured_output.
- **Acceptance:** clear error w/o key; structured output verified w/ test key or mock; pytest green.
- **Test command:** `python -m pytest tests/ -q`
- **Impl agent:** sw-dev. **Review agent:** verify-agent.
- **Status:** DONE (2026-08-24, commit 25e4137) — get_llm('openai') hardened to fail-safe
  RuntimeError on missing OPENAI_API_KEY (dummy-key fallback removed); Ollama path unchanged.
  tests/test_openai_provider.py (3 tests) builds ChatOpenAI via the SAME structured-output
  contract offline + asserts missing-key fails fast. Suite 21 passed. **Live OpenAI path
  UNVERIFIED without a real key** (documented). Claude Code read-only review: APPROVE.

## T-CHECKPOINT (P2)
- **Objective:** AgentState persistence + resume (closes "checkpoint system" gap).
- **GAP mapping:** GAP-2 enabler (explicit state management).
- **Exact problem:** run_agent returns in-memory dict; no disk write; no resume.
- **Evidence:** agent_graph.run_agent returns dict; no checkpoint_*.json writer.
- **Deps:** none.
- **Allowed files:** core/agent_graph.py (new core/checkpoint.py), data/checkpoints/.
- **Impl requirements:** serialize AgentState after each pivot; resume_agent(path) reloads and
  continues; assert identical final state vs fresh run.
- **Acceptance:** run writes checkpoint; resume yields identical final state; pytest resume test.
- **Test command:** `python -m pytest tests/ -q`
- **Impl agent:** sw-dev. **Review agent:** verify-agent.
- **Status:** DONE (2026-08-24, commit f1561be) — save_checkpoint/load_checkpoint/resume_agent added to core/agent_graph.py ONLY. resume re-enters from current_index with status-derived entry node (ASSESSING→assess, TESTING→execute, SUCCESS→pivot); validated CVEs never replayed; COMPLETED = no-op. tests/test_checkpoint.py (8 tests): interrupted-run resume reproduces fresh-run results exactly. Suite 29 passed. Hermes (P2) verified, offline via conftest.

## T-REQPIN (P3)
- **Objective:** Pin Python/deps for reproducibility.
- **GAP mapping:** reproducibility.
- **Exact problem:** requirements.txt open ranges; Python unpinned.
- **Evidence:** requirements.txt all `>=`; no python pin; no lock.
- **Deps:** none.
- **Allowed files:** requirements.txt (+ optional runtime.txt/lock).
- **Impl requirements:** add python==3.10 note + pin major deps with tested versions; keep venv ignored.
- **Acceptance:** clean venv + install reproduces imports; documented Python version.
- **Test command:** `python -c "import core"` after clean install
- **Impl agent:** sw-dev. **Review agent:** verify-agent.
- **Status:** DONE (2026-08-24, commit 9b0fe96) — requirements.txt pinned to exact (==) versions matching the verified venv (langchain 1.3.15, langchain-core 1.6.0, langchain-openai/-ollama 1.6.0/1.1.0, langgraph 1.2.11, pydantic 2.13.4, python-nmap 0.7.1, requests 2.34.2, streamlit 1.62.0, pandas 2.3.3, reportlab 5.0.1, pytest 9.1.1); .python-version=3.10; README documents repro. No behavior change: import core OK, pytest 29 passed, pins == installed freeze (diff clean). Hermes (P3) verified.

## T-GITHUB (P3)
- **Objective:** Verify GitHub PoC fetch with real token.
- **GAP mapping:** GAP-1 enabler.
- **Exact problem:** fetch_github_poc unverified (no GITHUB_TOKEN).
- **Evidence:** returns None without token; never exercised.
- **Deps:** none.
- **Allowed files:** core/poc_corpus.py, tests/ (mock).
- **Impl requirements:** mock test 200+401 (parse html_url→raw); with token one live fetch+score documented.
- **Acceptance:** mock green; live one-shot documented; no dummy code.
- **Test command:** `python -m pytest tests/ -q`
- **Impl agent:** github. **Review agent:** verify-agent.
- **Status:** TODO (needs GITHUB_TOKEN to fully verify live; mock sufficient for DONE)

## T-README (P4)
- **Objective:** Fix docs (stale numbers + env/deploy steps).
- **GAP mapping:** docs/polish + reproducibility.
- **Exact problem:** README says SMART=1; CSV shows 5. No env/deploy steps; "safe probe" wording.
- **Evidence:** README.md:76 "SMART | 1"; benchmark_results.csv "5".
- **Deps:** T-SAFE, T-BENCH-LOOP.
- **Allowed files:** README.md.
- **Impl requirements:** regenerate table from real run; explain negative time_saved_s; add
  env-var + Docker deploy; align real-mode wording with T-SAFE.
- **Acceptance:** README numbers match CSV; env/deploy present; wording consistent.
- **Test command:** `python tests/evaluate.py` then diff README vs CSV
- **Impl agent:** sw-dev. **Review agent:** verify-agent.
- **Status:** DONE (2026-08-24, commit pending) — README reconciled with verified evidence: fixed stale SMART=1→5 (matched benchmark_results.csv); added explicit SIMULATION / CONTROLLED VALIDATION / REAL OBSERVED RESULT tiers; aligned "Real mode" wording with T-SAFE (connectivity-ONLY default, SKIPPED, danger_mode opt-in only); added "NOT claimed" disclaimer (no faster/real-success/universal claims). 29 tests pass; numbers verified against evidence. Hermes verified.
## T-DEADCODE (P4)
- **Objective:** Remove dead get_poc export.
- **GAP mapping:** polish.
- **Exact problem:** get_poc exported in __init__ but never called.
- **Evidence:** search shows get_poc only in def + __init__.
- **Deps:** none.
- **Allowed files:** core/poc_corpus.py, core/__init__.py.
- **Impl requirements:** delete get_poc + export, OR wire assess_exploit_quality to call it
  as single local-first resolver (matches task2.md).
- **Acceptance:** no orphan export; or single resolver used; import clean.
- **Test command:** `python -c "import core"` + grep
- **Impl agent:** sw-dev (simplify). **Review agent:** verify-agent.
- **Status:** DONE (2026-08-24, commit pending) — removed unused `get_poc` from core/poc_corpus.py AND its package re-export in core/__init__.py (import line + `__all__`). corpus_lookup/corpus_label/fetch_github_poc retained (used by assessor + tests). Verified: `grep -rn get_poc` empty; `import core` OK (41 symbols); `pytest tests/ -q` 29 passed; agent_graph smoke unchanged. Hermes (P4) verified.

## T-UI (P4)
- **Objective:** Verify Streamlit dashboard interactively.
- **GAP mapping:** UI/polish.
- **Exact problem:** app.py imports clean but interactive run unverified; unsafe_allow_html on logs.
- **Evidence:** checkpoint noted scan preview works; no interactive run in audit.
- **Deps:** none.
- **Allowed files:** app.py.
- **Impl requirements:** run streamlit (or scripted boot + stubbed-LLM smoke of run button);
  confirm live feed + downloads; review unsafe_allow_html (sanitize if untrusted input possible).
- **Acceptance:** dashboard launches; upload live_scan.xml + run shows live logs + downloads; pytest if added.
- **Test command:** `streamlit run app.py` (manual) or `python -m pytest tests/ -q`
- **Impl agent:** sw-dev. **Review agent:** code-review.
- **Status:** TODO
