"""Comparative benchmark: SMART agent vs DUMB baseline (Phase 4, Task 4.2).

The "dumb" agent is an unguided LLM loop: it tries every exploit with NO
usability scoring and NO pivot threshold, so it can loop on dead-ends. The
"smart" agent is the full framework (EPSS ranking + usability scoring + pivot).

We run both against a labelled target environment and collect the four
thesis metrics:
  1. Total runtime (s)
  2. Total network requests
  3. Task completion rate (%)
  4. Infinite-loop events (avoidance count)
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd

from core.scanner import process_scan
from core.agent_graph import build_vapt_graph, AgentState
from core.executor import Executor
from core.schemas import (
    AgentStatus, ExecutionOutcome, Finding, UsabilityRank, finding_from_dict,
)

# --- Labelled target environment (3 vulns: 1 broken, 1 valid, 1 low-sev) -----
TARGET = "127.0.0.1"
LABELED_FINDINGS = [
    {"cve": "CVE-2021-44228", "port": 8080, "service": "http",
     "description": "Log4Shell (valid, HIGH)", "epss_score": 0.999},
    {"cve": "CVE-2023-38408", "port": 22, "service": "ssh",
     "description": "OpenSSH (broken exploit, would loop)", "epss_score": 0.797},
    {"cve": "CVE-2022-22965", "port": 9090, "service": "http",
     "description": "Spring4Shell (low severity)", "epss_score": 0.31},
]
PROVIDER = "ollama"


def _findings(raw):
    return [finding_from_dict(d) for d in raw]


# ---------------------------------------------------------------------------
# SMART agent (full framework, pivot threshold N)
# ---------------------------------------------------------------------------
def smart_agent(findings, threshold=2):
    fs = sorted(_findings([f.model_dump() for f in findings]),
                key=lambda f: f.priority_score(), reverse=True)
    state: AgentState = {
        "target": TARGET, "findings": fs, "current_index": 0,
        "current_cve": fs[0].cve, "exploit_rank": "PENDING",
        "attempt_count": 0, "max_attempts": threshold,
        "status": AgentStatus.ASSESSING.value, "provider": PROVIDER,
        "mode": "simulation", "logs": [], "results": [],
    }
    app = build_vapt_graph()
    final = app.invoke(state)

    # --- INSTRUMENTED loop measurement (T-BENCH-LOOP fix) -------------------
    # The graph must pivot to the next target after `threshold` failed attempts
    # on a CVE, so a healthy SMART run never executes any CVE more than
    # `threshold` times. We MEASURE (no longer assert a constant) loop events
    # from the actual execution results, grouped per CVE:
    #   loop_events = sum over distinct CVEs of max(0, executions_for_cve - threshold)
    # An excess execution is a measured "loop event" — proof the pivot failed
    # to bound retries. A correctly-pivoting run yields 0.
    exec_counts = Counter(r["cve"] for r in final["results"])
    smart_loop = sum(max(0, count - threshold) for count in exec_counts.values())

    # Runtime guard: the pivot MUST bound retries per CVE. If any CVE was
    # executed more than `threshold` times, the pivot logic failed and the
    # benchmark must ERROR rather than silently reporting 0. This converts the
    # previously-invalid (hardcoded) metric into a real, asserted measurement.
    max_per_cve = max(exec_counts.values()) if exec_counts else 0
    assert max_per_cve <= threshold, (
        f"SMART pivot FAILED to bound retries: a CVE was executed "
        f"{max_per_cve} times, exceeding threshold={threshold}. "
        f"Per-CVE execution counts: {dict(exec_counts)}"
    )

    final["loops"] = smart_loop
    return final


# ---------------------------------------------------------------------------
# DUMB agent (no scoring, no pivot — naive retry loop up to a hard cap)
# ---------------------------------------------------------------------------
def dumb_agent(findings, hard_cap=10):
    """Baseline: tries every exploit blindly, retrying each up to hard_cap
    times. This is the behaviour the smart pivot is meant to eliminate."""
    fs = _findings([f.model_dump() for f in findings])
    executor = Executor(mode="simulation")
    logs, results, loops = [], [], 0
    for f in fs:
        attempts = 0
        while True:
            attempts += 1
            r = executor.execute(f, TARGET)
            results.append(r.model_dump(mode="json"))
            if r.outcome == ExecutionOutcome.SUCCESS:
                break
            if attempts >= hard_cap:
                loops += 1   # stuck — did not self-terminate on this target
                break
    return {"results": results, "loops": loops}


def run_benchmark(provider=PROVIDER, threshold=2):
    findings = _findings(LABELED_FINDINGS)

    t0 = time.time()
    smart = smart_agent(findings, threshold=threshold)
    smart_time = time.time() - t0
    smart_reqs = sum(r.get("request_count", 0) for r in smart["results"])
    smart_success = sum(1 for r in smart["results"]
                        if r["outcome"] == ExecutionOutcome.SUCCESS.value)
    smart_loop = smart["loops"]  # measured from final["results"] (see smart_agent)

    t0 = time.time()
    dumb = dumb_agent(findings, hard_cap=10)
    dumb_time = time.time() - t0
    dumb_reqs = sum(r.get("request_count", 0) for r in dumb["results"])
    dumb_success = sum(1 for r in dumb["results"]
                       if r["outcome"] == ExecutionOutcome.SUCCESS.value)

    rows = [
        {"agent": "SMART (framework)", "runtime_s": round(smart_time, 3),
         "requests": smart_reqs, "validated": smart_success,
         "completion_%": round(100 * smart_success / len(findings), 1),
         "loop_events": smart_loop},
        {"agent": "DUMB (baseline)", "runtime_s": round(dumb_time, 3),
         "requests": dumb_reqs, "validated": dumb_success,
         "completion_%": round(100 * dumb_success / len(findings), 1),
         "loop_events": dumb["loops"]},
    ]
    df = pd.DataFrame(rows)
    return df, {
        "requests_saved": dumb_reqs - smart_reqs,
        "loops_avoided": dumb["loops"] - smart_loop,
        "time_saved_s": round(dumb_time - smart_time, 3),
    }


if __name__ == "__main__":
    out = "data/benchmark_results.csv"
    df, delta = run_benchmark(threshold=2)
    print(df.to_string(index=False))
    print("\nImprovement (SMART over DUMB):")
    for k, v in delta.items():
        print(f"  {k}: {v}")
    os.makedirs("data", exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\nSaved -> {out}")
