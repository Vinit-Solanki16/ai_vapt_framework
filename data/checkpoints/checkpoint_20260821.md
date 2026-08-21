# Weekly Checkpoint — Autonomous AI VAPT Framework
Date: 2026-08-21 | Path: /home/vinit/ai_vapt_framework | Python 3.10 venv | Ollama llama3.2:3b

## 1. Overall Status
**ON TRACK.** All 9 core deliverables present, non-trivial, and import cleanly. Benchmark runs end-to-end; SMART agent beats DUMB baseline on requests (5 vs 21) and loops (0 vs 2). No regression of the original hardcoded-success bug.

## 2. Completed Since Last Checkpoint (evidence)
- Full core/ package intact and importing: schemas.py (4.9K), scanner.py (6.3K), poc_corpus.py (3.6K), exploit_assessor.py (3.9K), executor.py (6.3K), agent_graph.py (7.2K), report.py (4.7K). `python -c "import core"` → OK.
- app.py (4.6K) imports and runs its scan preview (identified 2 findings ranked by EPSS: CVE-2021-44228 EPSS 1.0000, CVE-2023-38408 EPSS 0.7970).
- tests/evaluate.py (5.3K) runs to completion and writes data/benchmark_results.csv.
- PoC corpus with 3 real labelled exploits (CVE-2021-44228, CVE-2022-22965, CVE-2023-38408) + labels.json (3 entries, consistent reliability/outcome/requests).
- Report artifacts generated: data/reports/vapt_report_20260821_150351.{json,pdf}.

## 3. Current Blockers
- **GITHUB_TOKEN MISSING** → live GitHub PoC code search disabled (falls back to local corpus by design; unauth = 401). Not a bug, but caps corpus growth.
- **Docker installed but daemon NOT running/usable** → no live sandboxed exploitation yet; "real" mode limited to safe connectivity probe. (Memory said Docker absent — now installed; needs daemon start / WSL integration.)
- **Small PoC corpus (3 CVEs)** → benchmark statistically thin; fine for prototype, weak for thesis defense.
- **time_saved_s negative (-13.4s)** → SMART agent is slower in wall-clock because of Ollama LLM latency; win is in request-efficiency & loop-avoidance, not speed. Framing needs to be explicit in the thesis.

## 4. Next Priorities (ordered)
1. Start/enable Docker daemon and wire a sandboxed live-exploitation path in executor "real" mode (moves beyond connectivity probe).
2. Grow PoC corpus to 8–12 labelled CVEs for a more defensible benchmark.
3. Set GITHUB_TOKEN and validate fetch_github_poc real fetch + scoring path.
4. Add per-metric variance/multiple-seed runs to evaluate.py so results are reproducible with confidence bounds.

## 5. Progress vs Tasking Guide
- task1 (scanner: Nmap XML+JSON+EPSS): **~95%** — parsing + EPSS ranking verified live.
- task2 (exploit_assessor: usability gap, token-gated GitHub, no dummy): **~85%** — real corpus scoring works; GitHub path untested (no token).
- task3 (agent_graph: LangGraph pivot/state): **~95%** — assess→execute→pivot/advance verified, N-threshold pivot, no loops.
- task4 (app.py dashboard): **~85%** — imports & scan preview OK; full Streamlit UI (sidebar toggles, live feed) not re-verified this run (headless).
- task5 (evaluate.py SMART vs DUMB): **~90%** — 4-metric table produced; needs multi-run/variance.

## 6. Architecture Consistency — **PASS**
- Data flow intact: scanner → Finding → assessor/executor → agent_graph → report/app.
- No hardcoded `execution_success = False` in code (only in explanatory docstrings/comments referencing the fixed bug). Executor emits real signal: simulation resolves via labels.json; real mode does a genuine socket connectivity probe (counted honestly).
- `usability_rank` is the constrained `UsabilityRank(str, Enum)` in schemas.py (not loose str). ExecutionResult/Finding/AgentState all present.
- evaluate_decision(): SUCCESS→pivot/advance, attempt_count≥max_attempts→pivot, else execute; pivot→END on COMPLETED. No infinite-loop path.

## 7. Gap Drift
- **Gap 1 (Lu et al. 2024 — PoC quality/usability): PASS.** Assessor scores REAL corpus file content (data/poc_corpus/*.py), not placeholders; labels.json present and consistent; dummy-code returns explicitly refused.
- **Gap 2 (Deng et al. 2025 — Type-B planning/state): PASS.** agent_graph pivots on N failures and advances on success driven by real ExecutionResult signals; benchmark shows 2 loops avoided (SMART loop_events=0 vs DUMB=2).

## 8. Recommended Next Actions
1. `docker` daemon: enable WSL integration / `sudo service docker start`, then add a containerized exploit runner so "real" mode does live (safe, sandboxed) validation.
2. Expand corpus to ≥8 labelled CVEs and re-run evaluate.py; commit updated benchmark_results.csv.
3. Export GITHUB_TOKEN and run one authenticated fetch_github_poc to prove the real-fetch branch.
4. Add N-seed benchmark loop + mean/stddev to evaluate.py; document that SMART's advantage is request/loop efficiency, not wall-clock.
5. Re-verify app.py dashboard interactively (streamlit run) before thesis demo.
