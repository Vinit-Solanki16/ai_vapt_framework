# Autonomous AI VAPT Framework

State-aware Vulnerability Assessment & Penetration Testing with **Exploit Quality
Scoring** and **Dynamic Decision-Pivoting** (LangGraph). Built for an M.Tech
cybersecurity thesis. Runs fully offline via local Ollama (no API cost).

## Literature basis
- **Paul et al. (2024)** — enrich static scans with live EPSS threat intelligence.
- **Lu et al. (2024)** — PoC quality / usability gap → structured scoring matrix.
- **Deng et al. (2025)** — Type-B planning/state-management failures → pivot logic.

## Architecture
```
core/
  schemas.py        Shared Pydantic models + enums (fixes prototype bugs)
  scanner.py        Nmap XML/JSON + custom JSON ingestion + EPSS enrichment
  poc_corpus.py     Local labelled PoC corpus + token-aware GitHub fetch
  exploit_assessor.py  LLM usability scoring matrix (Ollama / OpenAI)
  executor.py       REAL execution signal (no hardcoded False) + sim harness
  agent_graph.py    LangGraph state machine: assess → execute → pivot/advance
  report.py         JSON + PDF VAPT report generation
app.py             Streamlit dashboard (live state viz + reports)
tests/evaluate.py  SMART vs DUMB comparative benchmark → CSV
data/
  sample_scan.json  Custom scan schema
  live_scan.xml     Real Nmap XML sample
  poc_corpus/       Labelled PoC files + labels.json
tasks/             task1.md … task5.md (one per phase module)
```

## Setup
```bash
cd ~/ai_vapt_framework
python3.10 -m venv venv        # Python 3.10 (pinned in .python-version)
source venv/bin/activate
pip install -r requirements.txt   # exact pins for reproducible builds (T-REQPIN)
# optional, for live GitHub PoC fetch:
export GITHUB_TOKEN=ghp_xxx
# ensure Ollama is running locally:
ollama serve &   # llama3.2:3b already pulled
```

## Run
```bash
# 1) Scan ingestion
python -m core.scanner data/sample_scan.json
python -m core.scanner data/live_scan.xml

# 2) Usability scoring (local Ollama)
python -m core.exploit_assessor CVE-2021-44228

# 3) Full agent run
python -m core.agent_graph

# 4) Comparative benchmark
python tests/evaluate.py        # -> data/benchmark_results.csv

# 5) Dashboard
streamlit run app.py
```

## Honest limitations (document these in the thesis)

Three evidence tiers — keep them distinct:
- **SIMULATION** — exploit outcomes resolved from `data/poc_corpus/labels.json` (curated
  ground truth), not a live weaponized payload. This makes results reproducible and
  avoids shipping exploits; it is a *behavioural* benchmark of the agent's decision
  logic (scoring + pivot), which is exactly the contribution.
- **CONTROLLED VALIDATION** — offline ablations (`tests/gap1_ablation.py`,
  `tests/ablation.py`, `tests/benchmark_var.py`) measuring the mechanism with frozen
  inputs and stubbed assessor; no external target.
- **REAL OBSERVED RESULT** — NOT YET ACHIEVED. Would require an isolated Docker testbed
  (T-DOCKER) executing sandboxed PoC modules and parsing actual output. Currently blocked.

- **Real mode (default `real`, danger_mode=False)** is a genuine but connectivity-ONLY
  probe: it opens a TCP connection to verify reachability and sends NO exploit payload.
  It reports `SKIPPED` (no exploit sent), never a simulated success. LOW-usability
  findings are always skipped. Live exploitation is possible ONLY via the explicit,
  opt-in `danger_mode=True` in an authorized, isolated lab — never against targets you
  are not permitted to test.
- To progress to **true exploitation**, provision an isolated Docker testbed
  (DVWA / OWASP crAPI / Metasploitable) and register sandboxed modules under
  `data/poc_corpus/<CVE>.py`; the executor can shell them out in danger_mode
  (opt-in, requires authorized isolated lab).

## Benchmark result (sample run, SIMULATION)

> Evidence category: **SIMULATION** (outcomes resolved from `labels.json`, not a live
> weaponized payload). See "Honest limitations" below for the three-tier distinction.

| Agent | Requests | Validated | Completion % | Loop events |
|-------|----------|-----------|--------------|-------------|
| SMART (framework) | 5  | 1 | 33.3 | 0 |
| DUMB (baseline)   | 21 | 1 | 33.3 | 2 |

The smart agent reaches the same validated vulnerability using **16 fewer requests**
(5 vs 21) and **zero loop events** vs the baseline's 2 — the core thesis claim, now
measured (not asserted). It does NOT run faster: LLM scoring adds latency, so
wall-clock time is longer for SMART (time_saved is NEGATIVE).

Demonstrated, evidence-backed benefits (SIMULATION / CONTROLLED VALIDATION):
- pre-execution candidate assessment via a structured-LLM usability matrix;
- EPSS × usability ranking/prioritization of the attack path;
- measured request-attempt reduction (5 vs 21) and loop-event elimination (0 vs 2);
- explicit state-driven pivoting after N failed attempts (no infinite loops);
- reproducible local evaluation (pinned deps, frozen inputs, offline test suite).

NOT claimed: faster execution, real exploit success, universal GAP-1 prediction
accuracy, or universal loop prevention. See `docs/project_management/09_BENCHMARK_EVIDENCE.md`.
