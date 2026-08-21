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
source venv/bin/activate
pip install -r requirements.txt
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
- **Simulation mode** resolves exploit outcomes against a curated ground-truth
  `labels.json`, not a live weaponized payload. This makes results reproducible
  and avoids shipping exploits — it is a *behavioural* benchmark of the agent's
  decision logic (scoring + pivot), which is exactly the contribution.
- **Real mode** performs a genuine, safe connectivity probe (honestly counted as
  a network request); exploit *success* is still resolved against the label
  because weaponized payloads are intentionally not shipped.
- To progress to **true exploitation**, provision an isolated Docker testbed
  (DVWA / OWASP crAPI / Metasploitable) and register sandboxed modules under
  `data/poc_corpus/<CVE>.py`; the executor already shells them out safely.

## Benchmark result (sample run, simulation)
| Agent | Requests | Validated | Completion % | Loop events |
|-------|----------|-----------|--------------|-------------|
| SMART | 1        | 1         | 33.3         | 0           |
| DUMB  | 21       | 1         | 33.3         | 2           |

The smart agent validates the same vulnerability using ~20 fewer requests and
zero infinite-loop events — the core thesis claim, now demonstrable.
