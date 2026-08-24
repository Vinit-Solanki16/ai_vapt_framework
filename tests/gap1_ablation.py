"""T-GAP1-VALID (P1): controlled ablation proving exploit-quality (usability)
scoring changes the agent's ROUTING and OUTCOMES — not merely that scoring code
executes.

Design
------
Two variants run the SAME LangGraph agent over the SAME labelled findings, in
SIMULATION mode (outcomes driven by data/poc_corpus/labels.json). The ONLY thing
that differs is whether the exploit-quality (usability) signal is allowed to
order the attack path:

  VARIANT A  (WITH scoring) : findings ordered by Finding.priority_score()
                              = epss * (0.5 + 0.5*usability), with usability
                              taken from a deterministic stub that maps each
                              PoC's labels.json `reliability` -> usability_rank
                              (HIGH->HIGH, MEDIUM->MEDIUM, LOW->LOW). This is the
                              real framework's rank_findings() behaviour.

  VARIANT B  (WITHOUT scoring / degraded) : usability signal is ABSENT for
                              routing — findings are shuffled (random order over
                              several seeds), simulating an agent with no
                              exploit-quality scoring to prioritise targets.

EPSS is held UNIFORM across findings so any ordering difference is attributable
purely to the usability signal (clean ablation, no EPSS confound).

Offline & deterministic: core.agent_graph.assess_exploit_quality is monkeypatched
to a labels-driven stub, so NO Ollama / network call occurs.

Metric (decision-relevant, MEASURED from the runs)
--------------------------------------------------
  * requests_to_first_success : cumulative simulated network requests spent
        before the first exploitable (SUCCESS) finding is validated.
  * first_success_index       : position (0-based, over distinct findings
        attempted) at which the first SUCCESS occurs.
The thesis claim: WITH scoring the agent reaches an exploitable finding in FEWER
requests / earlier than WITHOUT scoring. The DELTA is computed from actual runs.

Governance: reads core/* and data/poc_corpus/labels.json read-only; writes only
tests/gap1_ablation.py (this file) and data/gap1_ablation.csv. Simulation only —
no real exploitation, no offensive traffic.
"""
from __future__ import annotations

import csv
import json
import os
import random
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from core import agent_graph
from core.agent_graph import build_vapt_graph, AgentState
from core.schemas import (
    AgentStatus, ExecutionOutcome, ExploitAssessment, Finding, UsabilityRank,
)

TARGET = "127.0.0.1"
PROVIDER = "ollama"          # nominal; the assessor is stubbed so no call is made
THRESHOLD = 2                # pivot threshold (max attempts per CVE)
UNIFORM_EPSS = 0.5           # held constant -> ordering delta is purely usability
LABELS_PATH = ROOT / "data" / "poc_corpus" / "labels.json"
CSV_PATH = ROOT / "data" / "gap1_ablation.csv"
SEEDS = [1, 7, 13, 42, 99]   # multiple shuffles for the signal-absent variant


# ---------------------------------------------------------------------------
# Deterministic, OFFLINE assessor stub (reliability -> usability_rank)
# ---------------------------------------------------------------------------
def _load_labels() -> dict:
    with open(LABELS_PATH) as f:
        return json.load(f)


_LABELS = _load_labels()
_REL2RANK = {
    "HIGH": UsabilityRank.HIGH,
    "MEDIUM": UsabilityRank.MEDIUM,
    "LOW": UsabilityRank.LOW,
}


def stub_assess_exploit_quality(cve_id: str, *args, **kwargs) -> ExploitAssessment:
    """Offline stand-in for the LLM assessor: derives usability from the curated
    corpus `reliability` label. Deterministic, no Ollama, no network."""
    rel = str(_LABELS.get(cve_id.strip().upper(), {}).get("reliability", "MEDIUM")).upper()
    rank = _REL2RANK.get(rel, UsabilityRank.MEDIUM)
    complexity = {"HIGH": 2, "MEDIUM": 5, "LOW": 8}[rank.value]
    return ExploitAssessment(
        exploit_found=True,
        syntax_valid=(rank != UsabilityRank.LOW),
        os_dependencies="none",
        privileges_required="user",
        network_noise="low",
        complexity_score=complexity,
        prerequisites_met=(rank != UsabilityRank.LOW),
        usability_rank=rank,
        reasoning=f"stub: reliability={rel} -> usability={rank.value}",
    )


# ---------------------------------------------------------------------------
# Build findings from labels.json (uniform EPSS to isolate the usability signal)
# ---------------------------------------------------------------------------
def build_findings() -> list[Finding]:
    fs = []
    for i, (cve, lab) in enumerate(_LABELS.items()):
        fs.append(Finding(
            cve=cve,
            port=8000 + i,
            service="sim",
            description=f"{cve} ({lab.get('reliability')}/{lab.get('outcome')})",
            epss_score=UNIFORM_EPSS,
        ))
    return fs


# ---------------------------------------------------------------------------
# Ranking policies
# ---------------------------------------------------------------------------
def rank_with_scoring(findings: list[Finding]) -> list[Finding]:
    """VARIANT A: pre-assess (fill usability from the stub) then order by the
    real priority_score() — this reproduces the framework's usability-aware
    routing (rank_findings computes on priority_score)."""
    enriched = []
    for f in findings:
        g = f.model_copy()
        g.usability_rank = stub_assess_exploit_quality(g.cve).usability_rank
        enriched.append(g)
    # stable sort by priority_score desc == rank_findings() semantics
    return sorted(enriched, key=lambda f: f.priority_score(), reverse=True)


def rank_without_scoring(findings: list[Finding], seed: int) -> list[Finding]:
    """VARIANT B: usability signal ABSENT for routing -> random order."""
    fs = [f.model_copy() for f in findings]
    rng = random.Random(seed)
    rng.shuffle(fs)
    return fs


# ---------------------------------------------------------------------------
# Run one variant through the real agent graph and MEASURE outcomes
# ---------------------------------------------------------------------------
def run_variant(ordered_findings: list[Finding]) -> dict:
    state: AgentState = {
        "target": TARGET,
        "findings": ordered_findings,
        "current_index": 0,
        "current_cve": ordered_findings[0].cve,
        "exploit_rank": "PENDING",
        "attempt_count": 0,
        "max_attempts": THRESHOLD,
        "status": AgentStatus.ASSESSING.value,
        "provider": PROVIDER,
        "mode": "simulation",
        "logs": [],
        "results": [],
    }
    app = build_vapt_graph()
    final = app.invoke(state)

    results = final["results"]
    total_requests = sum(r.get("request_count", 0) for r in results)
    validated = sum(1 for r in results
                    if r["outcome"] == ExecutionOutcome.SUCCESS.value)

    # --- MEASURED: requests spent until the first SUCCESS is validated ---------
    requests_to_first_success = 0
    first_success_index = -1     # index over DISTINCT findings attempted
    seen_cves: list[str] = []
    hit = False
    for r in results:
        requests_to_first_success += r.get("request_count", 0)
        if r["cve"] not in seen_cves:
            seen_cves.append(r["cve"])
        if r["outcome"] == ExecutionOutcome.SUCCESS.value:
            first_success_index = len(seen_cves) - 1
            hit = True
            break
    if not hit:
        requests_to_first_success = total_requests

    # attempt ORDER = distinct CVE sequence as attempted
    attempt_order = []
    for r in results:
        if r["cve"] not in attempt_order:
            attempt_order.append(r["cve"])

    total_success_findings = sum(
        1 for f in ordered_findings
        if str(_LABELS.get(f.cve.upper(), {}).get("outcome", "")).lower() == "success"
    )
    completion_pct = round(100.0 * validated / total_success_findings, 1) \
        if total_success_findings else 0.0

    return {
        "requests": total_requests,
        "validated": validated,
        "completion_pct": completion_pct,
        "requests_to_first_success": requests_to_first_success,
        "first_success_index": first_success_index,
        "attempt_order": attempt_order,
    }


# ---------------------------------------------------------------------------
# Main ablation
# ---------------------------------------------------------------------------
def main() -> int:
    # Monkeypatch the assessor used INSIDE the graph -> fully offline run.
    agent_graph.assess_exploit_quality = stub_assess_exploit_quality

    findings = build_findings()

    # VARIANT A (with scoring) — deterministic
    a = run_variant(rank_with_scoring(findings))

    # VARIANT B (without scoring) — averaged over seeds
    b_runs = [run_variant(rank_without_scoring(findings, s)) for s in SEEDS]

    rows = []
    rows.append({
        "variant": "A_with_scoring", "seed": "-",
        "requests": a["requests"], "validated": a["validated"],
        "completion_%": a["completion_pct"],
        "requests_to_first_success": a["requests_to_first_success"],
        "first_success_index": a["first_success_index"],
    })
    for s, b in zip(SEEDS, b_runs):
        rows.append({
            "variant": "B_no_scoring", "seed": s,
            "requests": b["requests"], "validated": b["validated"],
            "completion_%": b["completion_pct"],
            "requests_to_first_success": b["requests_to_first_success"],
            "first_success_index": b["first_success_index"],
        })

    # --- write CSV -------------------------------------------------------------
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    fields = ["variant", "seed", "requests", "validated", "completion_%",
              "requests_to_first_success", "first_success_index"]
    with open(CSV_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # --- MEASURED deltas (computed from the runs, NOT hardcoded) --------------
    b_mean_rtfs = mean(b["requests_to_first_success"] for b in b_runs)
    b_mean_fsi = mean(b["first_success_index"] for b in b_runs)
    delta_requests = b_mean_rtfs - a["requests_to_first_success"]
    delta_index = b_mean_fsi - a["first_success_index"]

    # --- report ----------------------------------------------------------------
    print("=" * 74)
    print("T-GAP1-VALID ablation: exploit-quality (usability) scoring vs none")
    print("=" * 74)
    print(f"Findings: {len(findings)} (uniform EPSS={UNIFORM_EPSS}, "
          f"pivot threshold={THRESHOLD}, simulation mode, OFFLINE stub)")
    print()
    hdr = f"{'variant':<20}{'seed':>5}{'reqs':>7}{'valid':>7}{'compl%':>8}{'req->1st_succ':>15}{'1st_succ_idx':>14}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['variant']:<20}{str(r['seed']):>5}{r['requests']:>7}"
              f"{r['validated']:>7}{r['completion_%']:>8}"
              f"{r['requests_to_first_success']:>15}{r['first_success_index']:>14}")
    print("-" * len(hdr))
    print()
    print("Attempt ORDER (distinct CVE sequence):")
    print(f"  A (with scoring): {a['attempt_order']}")
    for s, b in zip(SEEDS, b_runs):
        print(f"  B seed={s:<3}      : {b['attempt_order']}")
    print()
    print("MEASURED DELTA (B_mean - A):")
    print(f"  requests-to-first-success : A={a['requests_to_first_success']}  "
          f"B_mean={b_mean_rtfs:.2f}  ->  DELTA={delta_requests:+.2f}")
    print(f"  first-success-index       : A={a['first_success_index']}  "
          f"B_mean={b_mean_fsi:.2f}  ->  DELTA={delta_index:+.2f}")
    print()

    # The signal is decision-relevant iff scoring reaches the exploitable
    # finding sooner (fewer requests AND earlier index) on average.
    assert delta_requests > 0, (
        f"Expected WITH-scoring to reach first success in fewer requests, "
        f"but delta={delta_requests}")
    assert delta_index > 0, (
        f"Expected WITH-scoring to attempt the success finding earlier, "
        f"but delta={delta_index}")

    print("RESULT: exploit-quality scoring is DECISION-RELEVANT.")
    print(f"  WITH scoring reaches an exploitable finding {delta_requests:.2f} "
          f"requests sooner and {delta_index:.2f} positions earlier (avg) than "
          f"WITHOUT scoring.")
    print(f"CSV written: {CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
