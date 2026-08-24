"""T-GAP1-VALID (P1) — directive-exact ablation: EPSS x usability scoring vs
EPSS-ONLY ranking, on the full labelled corpus (n=12).

Difference from tests/gap1_ablation.py (kept as the uniform-EPSS/random-order
proof-of-mechanism): THIS experiment implements the task brief literally —

  ARM A "with_scoring" : findings pre-assessed (reliability->usability stub),
                         ordered by Finding.priority_score()
                         = epss * (0.5 + 0.5*usability). Full SMART routing.
  ARM B "epss_only"    : ordered by RAW EPSS ONLY (descending); the usability
                         signal is NOT used for routing (it is still assessed
                         at runtime — assessment cannot reorder anything since
                         the graph ranks once up front). Pivot stays ENABLED,
                         identical budget N=2 in both arms.

Inputs are frozen for reproducibility:
  * outcomes/reliability: data/poc_corpus/labels.json (ground truth, unchanged)
  * EPSS per CVE: fixed representative-magnitude table below (SYNTHETIC static
    snapshot chosen for experimental control — not live API values). It is an
    INPUT, documented openly; outcomes still come exclusively from labels.

MEASURED metrics (from actual run traces; nothing asserted about direction):
  * wasted_attempts_total      — executions on routes whose label outcome is
                                 never SUCCESS (the brief's literal metric).
  * wasted_before_first_success— same definition, counted up to the first
                                 validated success (foothold-timing view).
  * completion_%               — validated successes / labeled-success CVEs.
  * requests_to_first_success  — secondary context metric (INCLUSIVE of the
                                 successful foothold request itself).
  * per-CVE attempt counts     — pivot-boundedness guard (<= N in both arms).

Structural note (verified numerically by this script, important for the
thesis): because the pivot bounds retries per route in BOTH arms and the graph
covers every finding, TOTAL waste is expected to match across arms; scoring's
effect shows up as EARLIER foothold / less pre-success waste. The script
reports whatever it measures.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from core import agent_graph
from core.agent_graph import build_vapt_graph, AgentState
from core.schemas import (
    AgentStatus, ExecutionOutcome, ExploitAssessment, Finding, UsabilityRank,
)

TARGET = "127.0.0.1"
PROVIDER = "ollama"            # nominal; assessor stubbed -> no call made
THRESHOLD_N = 2                # identical retry budget in BOTH arms
LABELS_PATH = ROOT / "data" / "poc_corpus" / "labels.json"
CSV_PATH = ROOT / "data" / "ablation_epss_only.csv"

# Frozen synthetic EPSS inputs (representative real-world magnitudes, 2dp).
# Experimental-control inputs ONLY — all outcome truth lives in labels.json.
EPSS_TABLE = {
    "CVE-2023-34362": 0.97,   # MOVEit SQLi       (LOW-usability dead end)
    "CVE-2021-44228": 0.96,   # Log4Shell         (HIGH-usability success)
    "CVE-2024-3094":  0.95,   # xz backdoor       (LOW-usability dead end)
    "CVE-2022-1388":  0.94,   # F5 BIG-IP         (HIGH-usability success)
    "CVE-2020-1472":  0.93,   # Zerologon         (HIGH-usability success)
    "CVE-2017-0144":  0.92,   # EternalBlue       (HIGH-usability success)
    "CVE-2021-34527": 0.90,   # PrintNightmare    (MED-usability dead end)
    "CVE-2019-0708":  0.88,   # BlueKeep          (MED-usability dead end)
    "CVE-2021-21972": 0.85,   # vCenter           (MED-usability dead end)
    "CVE-2023-38408": 0.82,   # OpenSSH agent     (MED-usability dead end)
    "CVE-2021-26855": 0.60,   # ProxyLogon        (MED-usability success)
    "CVE-2022-22965": 0.58,   # Spring4Shell      (LOW-usability dead end)
}

_REL2RANK = {"HIGH": UsabilityRank.HIGH, "MEDIUM": UsabilityRank.MEDIUM,
             "LOW": UsabilityRank.LOW}


def _load_labels() -> dict:
    with open(LABELS_PATH) as f:
        return json.load(f)


_LABELS = _load_labels()


def stub_assess(cve_id: str, *args, **kwargs) -> ExploitAssessment:
    """Offline assessor stand-in: labels.reliability -> usability_rank."""
    rel = str(_LABELS.get(cve_id.strip().upper(), {}).get(
        "reliability", "MEDIUM")).upper()
    rank = _REL2RANK.get(rel, UsabilityRank.MEDIUM)
    return ExploitAssessment(
        exploit_found=True,
        syntax_valid=(rank != UsabilityRank.LOW),
        os_dependencies="none",
        privileges_required="user",
        network_noise="low",
        complexity_score={"HIGH": 2, "MEDIUM": 5, "LOW": 8}[rank.value],
        prerequisites_met=(rank != UsabilityRank.LOW),
        usability_rank=rank,
        reasoning=f"stub: reliability={rel} -> usability={rank.value}",
    )


def build_findings() -> list[Finding]:
    fs = []
    for i, cve in enumerate(_LABELS):
        if cve not in EPSS_TABLE:
            raise KeyError(f"no frozen EPSS input for {cve}; extend EPSS_TABLE")
        fs.append(Finding(cve=cve, port=8000 + i, service="sim",
                          description=f"{cve} ({_LABELS[cve]['reliability']}/"
                                      f"{_LABELS[cve]['outcome']})",
                          epss_score=EPSS_TABLE[cve]))
    return fs


def run_arm(ordered: list[Finding], name: str) -> dict:
    """Run one arm through the REAL LangGraph agent (pivot enabled) and
    measure everything from the returned execution trace."""
    state: AgentState = {
        "target": TARGET, "findings": ordered, "current_index": 0,
        "current_cve": ordered[0].cve, "exploit_rank": "PENDING",
        "attempt_count": 0, "max_attempts": THRESHOLD_N,
        "status": AgentStatus.ASSESSING.value, "provider": PROVIDER,
        "mode": "simulation", "logs": [], "results": [],
    }
    final = build_vapt_graph().invoke(state)
    trace = final["results"]

    def is_success_label(cve: str) -> bool:
        return str(_LABELS[cve]["outcome"]).lower() == "success"

    wasted_total = sum(1 for r in trace if not is_success_label(r["cve"]))
    wasted_pre = 0
    reqs_pre = 0
    first_success = False
    order: list[str] = []
    for r in trace:
        if r["cve"] not in order:
            order.append(r["cve"])
        if not first_success:
            reqs_pre += r.get("request_count", 0)
            if not is_success_label(r["cve"]):
                wasted_pre += 1
            else:
                first_success = True
    n_success_cves = sum(1 for c in _LABELS if is_success_label(c))
    validated = sum(1 for r in trace
                    if r["outcome"] == ExecutionOutcome.SUCCESS.value)
    return {
        "arm": name,
        "order": order,
        "requests": sum(r.get("request_count", 0) for r in trace),
        "validated": validated,
        "completion_pct": round(100.0 * validated / n_success_cves, 1),
        "wasted_total": wasted_total,
        "wasted_pre_first_success": wasted_pre,
        "requests_to_first_success": reqs_pre,
        "per_cve_attempts": dict(Counter(r["cve"] for r in trace)),
    }


def main() -> int:
    agent_graph.assess_exploit_quality = stub_assess   # offline graph runs
    findings = build_findings()

    # ARM A: pre-assess usability, then rank by the real priority_score().
    enriched = []
    for f in findings:
        g = f.model_copy()
        g.usability_rank = stub_assess(g.cve).usability_rank
        enriched.append(g)
    a = run_arm(sorted(enriched, key=lambda f: f.priority_score(),
                       reverse=True), "A_with_scoring")

    # ARM B: rank by RAW EPSS ONLY (usability ignored for routing).
    b = run_arm(sorted(findings, key=lambda f: f.epss_score, reverse=True),
                "B_epss_only")

    # Pivot-boundedness guard (regression check, not a direction claim).
    for arm in (a, b):
        assert max(arm["per_cve_attempts"].values()) <= THRESHOLD_N, arm

    rows = []
    for arm in (a, b):
        rows.append({
            "arm": arm["arm"], "requests": arm["requests"],
            "validated": arm["validated"],
            "completion_%": arm["completion_pct"],
            "wasted_attempts_total": arm["wasted_total"],
            "wasted_before_first_success": arm["wasted_pre_first_success"],
            "requests_to_first_success": arm["requests_to_first_success"],
        })
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CSV_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    dw_total = b["wasted_total"] - a["wasted_total"]
    dw_pre = (b["wasted_pre_first_success"]
              - a["wasted_pre_first_success"])
    drq = b["requests_to_first_success"] - a["requests_to_first_success"]

    print("=" * 76)
    print("T-GAP1-VALID ablation: EPSS x usability (A) vs EPSS-ONLY (B)")
    print("=" * 76)
    print(f"corpus n={len(findings)}  pivot N={THRESHOLD_N} both arms  "
          f"mode=simulation (label truth)  EPSS=frozen synthetic table")
    hdr = (f"{'arm':<14}{'reqs':>6}{'valid':>7}{'compl%':>8}"
           f"{'waste_tot':>11}{'waste_pre1st':>14}{'req->1st':>10}")
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{r['arm']:<14}{r['requests']:>6}{r['validated']:>7}"
              f"{r['completion_%']:>8}{r['wasted_attempts_total']:>11}"
              f"{r['wasted_before_first_success']:>14}"
              f"{r['requests_to_first_success']:>10}")
    print("-" * len(hdr))
    print("\nAttempt order:")
    print(f"  A: {a['order']}")
    print(f"  B: {b['order']}")
    print("\nMEASURED DELTAS (B - A):")
    print(f"  wasted_attempts_total       : {dw_total:+d} "
          f"(A={a['wasted_total']}, B={b['wasted_total']})")
    print(f"  wasted_before_first_success : {dw_pre:+d} "
          f"(A={a['wasted_pre_first_success']}, "
          f"B={b['wasted_pre_first_success']})")
    print(f"  requests_to_first_success   : {drq:+d} "
          f"(A={a['requests_to_first_success']}, "
          f"B={b['requests_to_first_success']})")
    print(f"\nCSV written: {CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
