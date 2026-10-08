"""PHASE 33C — GAP-1 operational effectiveness experiment.

RESEARCH-ONLY, ADDITIVE script. Does NOT modify:
  decision_engine/core/, decision_engine/benchmarks/,
  the ranking algorithm, GAP-1, GAP-2, or any historical results.

RESEARCH QUESTION
"When candidate quality differences are meaningful, does AI-assisted
pre-execution assessment improve the order in which useful candidates are
selected compared with a probability/severity-only baseline?"

DESIGN
Four arms on the SAME synthetic corpus, order, probabilities, ground truth,
budget, ranking procedure, stopping rule, prompts, temperature, and reps:

  A. BASELINE      — probability-only ranking (no assessment signal).
  B. DETERMINISTIC — existing deterministic quality assessor (offline).
  C. LLAMA         — llama3.2:3b via authoritative model configuration.
  D. QWEN          — qwen2.5:3b, explicit experimental model only.

Corpus: CONTROLLED SYNTHETIC research samples (IDs SYN-OE-*). These are NOT
real-world exploit evidence and are NEVER executed. They exercise the
decision mechanism only (syntax validity, dependencies, privileges,
network noise, complexity — the dimensions the assessor prompt grades).
The code text is intentionally tiered (HIGH/MEDIUM/LOW intended quality)
while probabilities are ANTI-ALIGNED with quality, so a quality-blind
ranking must try non-useful candidates first. This is what makes quality
differences "meaningful" for this experiment.

CRITICAL INDEPENDENCE: ground-truth usefulness (USEFUL True/False, with a
simulation Outcome label) is specified STATICALLY below BEFORE any
assessment runs, and is NEVER derived from, copied from, or conditioned
on any assessor output. LLM arms assess only the code text; outcomes are
resolved only from the static ground truth via the existing simulation
Executor. The experiment tests whether ranking changes lead to better
outcomes, not merely whether ranking changes occur.

OPERATIONAL MODEL (identical for every arm and rep):
  - Rank all candidates (existing rank_candidates interface, read-only).
  - Walk the ranked order; attempt each candidate at most once.
  - Resolve each attempt from static ground truth via
    Executor(mode="simulation") — controlled validation only, nothing
    executed, no network, no targets.
  - Stop at the first USEFUL success or when ATTEMPT_BUDGET is exhausted.

PRIMARY METRICS (per arm, per rep): top-1 useful selection, useful success
on first attempt, attempts until useful success (uncapped position),
total attempts, failed attempts, wasted/non-useful attempts, success
within fixed budget, mean rank displacement vs baseline.

SECONDARY METRICS: structured-output validity, fallback count, assessor
consistency, latency, inter-model (llama vs qwen) agreement.

STATISTICS: n=5 reps per arm — descriptive statistics only. No confidence
intervals, no significance tests; the sample size does not justify them.
"""

from __future__ import annotations

import csv
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decision_engine.core.assessor import deterministic_assessor
from decision_engine.core.engine import rank_candidates
from decision_engine.core.executor import Executor
from decision_engine.core.schemas import QualityRank, candidate_from_dict
from vapt_platform.model_config import resolve_model

# ---------------------------------------------------------------------------
# Controlled synthetic corpus (NOT real exploits; never executed)
# ---------------------------------------------------------------------------
# Ground truth ("useful": True/False + simulation "outcome") is fixed here,
# BEFORE assessment, and is independent of any assessor output by
# construction: no assessor has run at import/definition time, and no code
# below writes ground truth from an assessment result.

HIGH_01 = """# CONTROLLED SYNTHETIC RESEARCH SAMPLE — not real exploit code.
# Intended tier: HIGH. Complete, minimal, stdlib-only check script.
import socket


def check_service(host, port, timeout=5):
    # Open a TCP connection and grab the banner (user privileges).
    sock = socket.create_connection((host, port), timeout=timeout)
    try:
        sock.sendall(b"HEAD / HTTP/1.0\\r\\n\\r\\n")
        return sock.recv(1024).decode("utf-8", errors="replace")
    finally:
        sock.close()


if __name__ == "__main__":
    print(check_service("127.0.0.1", 8080))
"""

HIGH_02 = """# CONTROLLED SYNTHETIC RESEARCH SAMPLE — not real exploit code.
# Intended tier: HIGH. Complete, one common dependency, error handling.
import requests


def check_endpoint(base_url, timeout=5):
    # Fetch a status endpoint and return parsed JSON (user privileges).
    try:
        response = requests.get(base_url + "/api/status", timeout=timeout)
        response.raise_for_status()
        return {"reachable": True, "payload": response.json()}
    except requests.RequestException as exc:
        return {"reachable": False, "error": str(exc)}


if __name__ == "__main__":
    print(check_endpoint("http://127.0.0.1:8080"))
"""

MED_01 = """# CONTROLLED SYNTHETIC RESEARCH SAMPLE — not real exploit code.
# Intended tier: MEDIUM. Structurally valid but INCOMPLETE (TODO section),
# extra third-party dependency, moderate complexity.
import paramiko  # non-default dependency


def check_ssh_banner(host, port=22, timeout=5):
    # Grab SSH banner; full key handling not implemented yet.
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    # TODO: implement credential flow and command verification below.
    raise NotImplementedError("credential flow not implemented")


def helper_parse_banner(banner):
    # Moderate-complexity parsing with several untested branches.
    parts, result = banner.split(), {}
    for index, part in enumerate(parts):
        if "-" in part and index > 0:
            result.setdefault("tokens", []).append(part.strip())
        elif part.isdigit():
            result["number"] = int(part)
    return result


if __name__ == "__main__":
    print(helper_parse_banner("SSH-2.0-OpenSSH 8.9"))
"""

MED_02 = """# CONTROLLED SYNTHETIC RESEARCH SAMPLE — not real exploit code.
# Intended tier: MEDIUM. Valid syntax and complete flow, but requires ROOT
# (raw sockets) plus two non-default dependencies; noisy threaded design.
import socket  # form: raw sockets below need root privileges
import threading
from scapy.all import IP, TCP, sr1  # non-default dependency 1
from concurrent.futures import ThreadPoolExecutor  # stdlib


def noisy_probe(host, ports):
    # Threaded SYN probe burst (loud on the wire, needs root).
    open_ports = []

    def probe(port):
        pkt = sr1(IP(dst=host) / TCP(dport=port, flags="S"), timeout=1,
                  verbose=False)
        if pkt and pkt.haslayer(TCP) and pkt[TCP].flags == 0x12:
            open_ports.append(port)

    with ThreadPoolExecutor(max_workers=50) as pool:
        list(pool.map(probe, ports))
    return sorted(open_ports)


if __name__ == "__main__":
    print(noisy_probe("127.0.0.1", [80, 443, 8080]))
"""

LOW_01 = """# CONTROLLED SYNTHETIC RESEARCH SAMPLE — not real exploit code.
# Intended tier: LOW. Malformed: syntax error, placeholder body,
# unrealistic dependency (custom kernel module for a banner check).
import socket
import super_kernel_exploit_driver  # unrealistic: kernel module required


def check_service(host, port
    # SYNTAX ERROR: missing closing parenthesis above; body is a stub.
    pass  # placeholder: no implementation at all
"""

LOW_02 = """# CONTROLLED SYNTHETIC RESEARCH SAMPLE — not real exploit code.
# Intended tier: LOW. Truncated/malformed: pseudocode lines, undefined names,
# contradictory prerequisites (Windows driver claimed for a Linux check).
DO THE EXPLOIT MAGIC HERE !!!
result = perform_sploit(target, MAGIC_PAYLOAD)  # undefined names
if result == SUCCESS!!!
    print("pwned"  # unterminated string and missing paren
# PREREQ: requires WinKernelDrv.sys v9 (Windows-only) on this Linux target
# COMPLEXITY: author rates 10/10, multi-stage, manual steps, no automation
"""

# (id, probability, simulation outcome label, useful?, intended_tier, code)
# Ground truth is INDEPENDENT of assessment: HIGH-tier samples are useful,
# MEDIUM/LOW-tier samples are not. Probabilities are anti-aligned with
# quality so the probability-only baseline must waste attempts first.
CORPUS = [
    ("SYN-OE-HIGH-01", 0.55, "SUCCESS", True, "HIGH", HIGH_01),
    ("SYN-OE-HIGH-02", 0.62, "SUCCESS", True, "HIGH", HIGH_02),
    ("SYN-OE-MED-01", 0.68, "FAIL_TIMEOUT", False, "MEDIUM", MED_01),
    ("SYN-OE-MED-02", 0.74, "FAIL_TIMEOUT", False, "MEDIUM", MED_02),
    ("SYN-OE-LOW-01", 0.80, "FAIL_SYNTAX", False, "LOW", LOW_01),
    ("SYN-OE-LOW-02", 0.88, "FAIL_DEPENDENCY", False, "LOW", LOW_02),
]

USEFUL_BY_ID = {cid: useful for cid, _p, _g, useful, _t, _c in CORPUS}

REPS = 5
ATTEMPT_BUDGET = 3  # fixed attempt budget, identical for every arm and rep
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

LLAMA_MODEL = resolve_model("ollama", "llama3.2:3b")  # authoritative baseline
QWEN_MODEL = resolve_model("ollama", "qwen2.5:3b")  # experimental arm only


def _fresh_dicts():
    return [
        {"id": cid, "probability": prob, "ground_truth": gt}
        for cid, prob, gt, _u, _t, _c in CORPUS
    ]


def baseline_order():
    """Arm A: probability-only ranking (no assessment signal)."""
    cands = [candidate_from_dict(d) for d in _fresh_dicts()]
    return [c.id for c in rank_candidates(cands)]


def assessed_order(rank_by_id):
    """Rank AFTER applying an id->QualityRank map (arms B/C/D)."""
    cands = [candidate_from_dict(d) for d in _fresh_dicts()]
    for c in cands:
        c.quality_rank = rank_by_id[c.id]
        c.assessed = True
    ranked = rank_candidates(cands)
    return [c.id for c in ranked], {c.id: c.priority_score() for c in ranked}


def simulate_walk(order):
    """Walk ranked order; stop at first USEFUL success or budget exhaustion.

    Each attempt is resolved from STATIC ground truth via the existing
    simulation Executor (controlled validation only — nothing is executed).
    Ground truth is read, never written, here.
    """
    executor = Executor(mode="simulation")
    by_id = {d["id"]: d for d in _fresh_dicts()}
    attempted = []  # candidate ids attempted, in order
    attempt_outcomes = []  # "SUCCESS"/other simulation outcomes
    for cid in order[:ATTEMPT_BUDGET]:
        cand = candidate_from_dict(by_id[cid])
        result = executor.execute(cand)
        attempted.append(cid)
        attempt_outcomes.append(result.outcome.value)
        if USEFUL_BY_ID[cid] and result.outcome.value == "SUCCESS":
            break
    # Uncapped position of the first useful candidate in the full order.
    first_useful_pos = next(
        (i + 1 for i, cid in enumerate(order) if USEFUL_BY_ID[cid]), None
    )
    success_in_budget = any(
        USEFUL_BY_ID[cid] and oc == "SUCCESS"
        for cid, oc in zip(attempted, attempt_outcomes)
    )
    n_success = 1 if success_in_budget else 0
    return {
        "attempted_order": attempted,
        "attempt_outcomes": attempt_outcomes,
        # 1. Top-1 useful candidate selection
        "top1_useful": USEFUL_BY_ID[order[0]],
        "top1_id": order[0],
        # 2. Useful success on the first attempt
        "first_attempt_success": (
            USEFUL_BY_ID[attempted[0]] and attempt_outcomes[0] == "SUCCESS"
        ) if attempted else False,
        # 3. Attempts until useful success (uncapped 1-indexed position)
        "attempts_until_useful_success": first_useful_pos,
        # 4/5/6. Totals under stop-on-success (failed == wasted here by
        # construction: at most one success, walk stops immediately).
        "total_attempts": len(attempted),
        "failed_attempts": len(attempted) - n_success,
        "wasted_attempts": sum(
            1 for cid in attempted if not USEFUL_BY_ID[cid]
        ),
        # 7. Success within the fixed attempt budget
        "success_within_budget": success_in_budget,
    }


def displacement_vs_baseline(order, baseline):
    base_pos = {cid: i for i, cid in enumerate(baseline)}
    ass_pos = {cid: i for i, cid in enumerate(order)}
    displ = {cid: abs(ass_pos[cid] - base_pos[cid]) for cid in baseline}
    return displ


def run_arm_reps(arm_name, rank_maps, sources_list=None, lat_maps=None,
                 validity=None):
    """Build per-rep records for one arm from per-rep id->QualityRank maps."""
    reps = []
    for rep, ranks in enumerate(rank_maps):
        order, scores = assessed_order(ranks)
        walk = simulate_walk(order)
        displ = displacement_vs_baseline(order, BASELINE)
        rec = {
            "arm": arm_name,
            "rep": rep,
            "ranks": {k: v.value for k, v in ranks.items()},
            "scores": scores,
            "order": order,
            "walk": walk,
            # 8. Mean rank displacement vs the no-assessment baseline
            "order_changed": order != BASELINE,
            "top1_changed": order[0] != BASELINE[0],
            "displacements": displ,
            "mean_displacement": round(
                statistics.mean(displ.values()), 4),
        }
        if sources_list is not None:
            rec["sources"] = sources_list[rep]
        if lat_maps is not None:
            rec["latencies"] = lat_maps[rep]
        if validity is not None:
            rec["valid_outputs"] = validity[rep][0]
            rec["fallbacks"] = validity[rep][1]
        reps.append(rec)
    return reps


def run_deterministic_arm():
    rank_maps = []
    t0 = time.perf_counter()
    for _rep in range(REPS):
        ranks = {}
        for cid, prob, gt, _u, _t, _c in CORPUS:
            ranks[cid] = deterministic_assessor(
                candidate_from_dict(
                    {"id": cid, "probability": prob, "ground_truth": gt}))
        rank_maps.append(ranks)
    per_cand_lat = (time.perf_counter() - t0) / (REPS * len(CORPUS))
    lat_maps = [
        {cid: round(per_cand_lat, 6) for cid, _, _, _, _, _ in CORPUS}
        for _ in range(REPS)
    ]
    return rank_maps, lat_maps


def run_llm_arm(model_name):
    """LLM arm: assess ONLY the code text; ground truth never consulted."""
    from core.exploit_assessor import assess_exploit_quality

    rank_maps, sources_list, lat_maps, validity = [], [], [], []
    for rep in range(REPS):
        ranks, sources, lats = {}, {}, {}
        n_valid, n_fallback = 0, 0
        for cid, _p, _g, _u, _t, code in CORPUS:
            t0 = time.perf_counter()
            try:
                a = assess_exploit_quality(
                    cid, code_sample=code, provider="ollama",
                    model_name=model_name, use_online=False,
                )
                el = time.perf_counter() - t0
                ranks[cid] = QualityRank(a.usability_rank.value)
                sources[cid] = "llm"
                n_valid += 1
            except Exception as exc:  # invalid structured output / transport
                el = time.perf_counter() - t0
                # Neutral fallback: no ground truth consulted (prob 0.0,
                # no label) -> deterministic LOW; preserves probability
                # order among fallbacks.
                ranks[cid] = deterministic_assessor(
                    candidate_from_dict({"id": cid, "probability": 0.0}))
                sources[cid] = "fallback"
                print(f"[{model_name} rep {rep}] {cid} FALLBACK "
                      f"({str(exc)[:120]})", flush=True)
                n_fallback += 1
            lats[cid] = round(el, 4)
            print(f"[{model_name} rep {rep}] {cid} -> {ranks[cid].value} "
                  f"({sources[cid]}, {el:.2f}s)", flush=True)
        rank_maps.append(ranks)
        sources_list.append(sources)
        lat_maps.append(lats)
        validity.append((n_valid, n_fallback))
    return rank_maps, sources_list, lat_maps, validity


def summarize_operational(arm_name, reps, lat_maps=None, overall_valid=None,
                          overall_fallback=None):
    n = len(reps)
    top1 = [r["walk"]["top1_useful"] for r in reps]
    first = [r["walk"]["first_attempt_success"] for r in reps]
    within = [r["walk"]["success_within_budget"] for r in reps]
    totals = [r["walk"]["total_attempts"] for r in reps]
    failed = [r["walk"]["failed_attempts"] for r in reps]
    wasted = [r["walk"]["wasted_attempts"] for r in reps]
    until = [r["walk"]["attempts_until_useful_success"] for r in reps]
    until_ok = [u for u in until if u is not None]
    meand = [r["mean_displacement"] for r in reps]
    qdist: dict[str, int] = {}
    for r in reps:
        for v in r["ranks"].values():
            qdist[v] = qdist.get(v, 0) + 1
    out = {
        "arm": arm_name,
        "reps": n,
        "attempt_budget": ATTEMPT_BUDGET,
        "top1_useful_rate": round(sum(top1) / n, 4),
        "first_attempt_success_rate": round(sum(first) / n, 4),
        "success_within_budget_rate": round(sum(within) / n, 4),
        "attempts_until_useful_success": {
            "per_rep": until,
            "n_successful_reps": len(until_ok),
            "mean": round(statistics.mean(until_ok), 4) if until_ok else None,
            "median": (round(statistics.median(until_ok), 4)
                       if until_ok else None),
            "min": min(until_ok) if until_ok else None,
            "max": max(until_ok) if until_ok else None,
        },
        "total_attempts": {
            "per_rep": totals,
            "mean": round(statistics.mean(totals), 4),
            "median": round(statistics.median(totals), 4),
            "min": min(totals),
            "max": max(totals),
        },
        "failed_attempts": {
            "per_rep": failed,
            "mean": round(statistics.mean(failed), 4),
        },
        "wasted_attempts": {
            "per_rep": wasted,
            "mean": round(statistics.mean(wasted), 4),
        },
        "ranking_change_rate": round(
            sum(1 for r in reps if r["order_changed"]) / n, 4),
        "top1_change_rate": round(
            sum(1 for r in reps if r["top1_changed"]) / n, 4),
        "mean_rank_displacement": {
            "per_rep": meand,
            "mean": round(statistics.mean(meand), 4),
            "median": round(statistics.median(meand), 4),
            "stdev": round(statistics.pstdev(meand), 4),
            "min": round(min(meand), 4),
            "max": round(max(meand), 4),
        },
        "quality_distribution": qdist,
    }
    if lat_maps is not None:
        lat = [v for m in lat_maps for v in m.values()]
        out["latency"] = {"n": len(lat),
                          "mean": round(statistics.mean(lat), 4),
                          "median": round(statistics.median(lat), 4),
                          "stdev": (round(statistics.pstdev(lat), 4)
                                    if len(lat) > 1 else 0.0),
                          "min": round(min(lat), 4),
                          "max": round(max(lat), 4)}
    if overall_valid is not None:
        total = overall_valid + overall_fallback
        out["valid_output_rate"] = round(overall_valid / total, 4)
        out["fallback_rate"] = round(overall_fallback / total, 4)
        out["valid_outputs"] = overall_valid
        out["fallbacks"] = overall_fallback
    return out


def consistency_of(arm_reps):
    per_cand: dict[str, list[str]] = {}
    for r in arm_reps:
        for cid, rank in r["ranks"].items():
            per_cand.setdefault(cid, []).append(rank)
    per, modes = {}, {}
    for cid, ranks in per_cand.items():
        mode = statistics.mode(ranks)
        modes[cid] = mode
        per[cid] = {"ranks": ranks, "mode": mode,
                    "agreement": round(ranks.count(mode) / len(ranks), 4),
                    "fully_consistent": len(set(ranks)) == 1}
    overall = round(
        statistics.mean([v["agreement"] for v in per.values()]), 4)
    return per, modes, overall


BASELINE = baseline_order()


def main():
    started = datetime.now(timezone.utc).isoformat()
    print(f"Baseline (no-assessment) order: {BASELINE}", flush=True)
    print(f"Attempt budget: {ATTEMPT_BUDGET}, reps: {REPS}", flush=True)

    # Arm A — baseline walk (no assessment).
    base_reps = run_arm_reps(
        "baseline_no_assessment",
        [{cid: QualityRank.LOW  # placeholder; order replaced below
          for cid, _, _, _, _, _ in CORPUS} for _ in range(REPS)],
    )
    for r in base_reps:  # true probability-only order + walk
        r["order"] = list(BASELINE)
        r["walk"] = simulate_walk(BASELINE)
        r["ranks"] = {cid: "NONE(unassessed)" for cid in BASELINE}
        r["scores"] = {}
        r["order_changed"] = False
        r["top1_changed"] = False
        r["displacements"] = {cid: 0 for cid in BASELINE}
        r["mean_displacement"] = 0.0

    # Arm B — deterministic.
    det_maps, det_lats = run_deterministic_arm()
    det_reps = run_arm_reps("deterministic", det_maps, lat_maps=det_lats)

    # Arm C — llama (authoritative baseline model).
    llama_maps, llama_src, llama_lats, llama_val = run_llm_arm(LLAMA_MODEL)
    llama_reps = run_arm_reps("llama3.2:3b", llama_maps,
                              sources_list=llama_src, lat_maps=llama_lats,
                              validity=llama_val)

    # Arm D — qwen (experimental model only).
    qwen_maps, qwen_src, qwen_lats, qwen_val = run_llm_arm(QWEN_MODEL)
    qwen_reps = run_arm_reps("qwen2.5:3b", qwen_maps,
                             sources_list=qwen_src, lat_maps=qwen_lats,
                             validity=qwen_val)

    summaries = {
        "baseline_no_assessment": summarize_operational(
            "baseline_no_assessment", base_reps),
        "deterministic": summarize_operational(
            "deterministic", det_reps, lat_maps=det_lats,
            overall_valid=REPS * len(CORPUS), overall_fallback=0),
        "llama3.2:3b": summarize_operational(
            "llama3.2:3b", llama_reps, lat_maps=llama_lats,
            overall_valid=sum(v[0] for v in llama_val),
            overall_fallback=sum(v[1] for v in llama_val)),
        "qwen2.5:3b": summarize_operational(
            "qwen2.5:3b", qwen_reps, lat_maps=qwen_lats,
            overall_valid=sum(v[0] for v in qwen_val),
            overall_fallback=sum(v[1] for v in qwen_val)),
    }
    for name, reps in (("deterministic", det_reps),
                       ("llama3.2:3b", llama_reps),
                       ("qwen2.5:3b", qwen_reps),
                       ("baseline_no_assessment", base_reps)):
        per, modes, overall = consistency_of(reps)
        summaries[name]["consistency"] = {"per_candidate": per,
                                         "overall_agreement": overall}
        summaries[name]["mode_ranks"] = modes

    # Inter-model agreement (llama vs qwen, paired by rep and candidate).
    agree_pairs, agree_match = 0, 0
    per_cand_agree: dict[str, dict] = {}
    for cid, _, _, _, _, _ in CORPUS:
        pairs = [(llama_reps[r]["ranks"][cid], qwen_reps[r]["ranks"][cid])
                 for r in range(REPS)]
        m = sum(1 for x, y in pairs if x == y)
        agree_pairs += len(pairs)
        agree_match += m
        per_cand_agree[cid] = {"pairs": pairs, "matches": m,
                               "agreement": round(m / len(pairs), 4)}
    inter = {"per_candidate": per_cand_agree,
             "overall_agreement": round(agree_match / agree_pairs, 4),
             "paired_observations": agree_pairs}

    payload = {
        "experiment": "gap1_operational_effectiveness",
        "phase": "33C",
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "research_integrity_note": (
            "Controlled synthetic corpus (SYN-OE-*). NOT real-world exploit "
            "evidence. Nothing executed: outcomes resolved from STATIC "
            "ground truth (defined before assessment) via the existing "
            "simulation Executor. Ground truth was never derived from, "
            "copied from, or conditioned on any assessor output. Ranking "
            "algorithm, GAP-1, prompts, schema, temperature unchanged; "
            "decision_engine/core and decision_engine/benchmarks "
            "unmodified. Statistics are descriptive only (n=5 reps/arm); "
            "no significance claimed."
        ),
        "independence_statement": {
            "ground_truth_defined": "statically in CORPUS before assessment",
            "useful_ids": sorted(
                cid for cid, u in USEFUL_BY_ID.items() if u),
            "non_useful_ids": sorted(
                cid for cid, u in USEFUL_BY_ID.items() if not u),
            "assessor_inputs": "code text + candidate id only",
            "outcome_resolution": "Executor(mode=simulation) from static "
                                  "ground truth; assessor output never "
                                  "flows into outcome",
        },
        "protocol": {
            "corpus": [{"id": cid, "probability": p, "ground_truth": g,
                        "useful": u, "intended_tier": t}
                       for cid, p, g, u, t, _c in CORPUS],
            "candidate_order": [c[0] for c in CORPUS],
            "repetitions": REPS,
            "attempt_budget": ATTEMPT_BUDGET,
            "stopping_rule": "stop at first USEFUL success or budget "
                             "exhaustion; max one attempt per candidate",
            "provider": "ollama",
            "models": {"llama": LLAMA_MODEL, "qwen": QWEN_MODEL},
            "temperature": 0.1,
            "prompt": "core/exploit_assessor.py SYSTEM_PROMPT + human "
                      "template (unchanged)",
            "schema": "core/schemas.py ExploitAssessment (unchanged)",
            "ranking_formula": "probability * (0.5 + 0.5 * quality); "
                               "HIGH=1.0, MEDIUM=0.6, LOW=0.3 "
                               "(decision_engine/core/schemas.py, read-only)",
            "use_online": False,
        },
        "baseline_order": BASELINE,
        "summaries": summaries,
        "arms": {
            "baseline_no_assessment": {"reps": base_reps},
            "deterministic": {"reps": det_reps},
            "llama3.2:3b": {"reps": llama_reps},
            "qwen2.5:3b": {"reps": qwen_reps},
        },
        "inter_model_agreement_llama_qwen": inter,
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    json_path = os.path.join(
        RESULTS_DIR, "gap1_operational_effectiveness.json")
    csv_path = os.path.join(
        RESULTS_DIR, "gap1_operational_effectiveness.csv")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    write_csv(payload, csv_path)
    print(f"Wrote {json_path}", flush=True)
    print(f"Wrote {csv_path}", flush=True)
    for name, s in summaries.items():
        print(f"{name}: top1_useful={s['top1_useful_rate']} "
              f"first_success={s['first_attempt_success_rate']} "
              f"within_budget={s['success_within_budget_rate']} "
              f"mean_total={s['total_attempts']['mean']} "
              f"mean_wasted={s['wasted_attempts']['mean']} "
              f"mean_displ={s['mean_rank_displacement']['mean']}",
              flush=True)
    print("INTER_MODEL_AGREEMENT(llama,qwen): "
          + json.dumps(inter["overall_agreement"]), flush=True)


def write_csv(payload, csv_path):
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["arm", "rep", "order", "top1_id", "top1_useful",
                    "first_attempt_success", "attempts_until_useful_success",
                    "success_within_budget", "total_attempts",
                    "failed_attempts", "wasted_attempts",
                    "attempted_order", "attempt_outcomes",
                    "order_changed", "top1_changed", "mean_displacement",
                    "ranks", "sources", "latency_mean_s"])
        for arm_name, bundle in payload["arms"].items():
            for r in bundle["reps"]:
                lat = r.get("latencies", {})
                lat_mean = (round(statistics.mean(lat.values()), 4)
                            if lat else "")
                w.writerow([arm_name, r["rep"], "|".join(r["order"]),
                            r["walk"]["top1_id"], r["walk"]["top1_useful"],
                            r["walk"]["first_attempt_success"],
                            r["walk"]["attempts_until_useful_success"],
                            r["walk"]["success_within_budget"],
                            r["walk"]["total_attempts"],
                            r["walk"]["failed_attempts"],
                            r["walk"]["wasted_attempts"],
                            "|".join(r["walk"]["attempted_order"]),
                            "|".join(r["walk"]["attempt_outcomes"]),
                            r["order_changed"], r["top1_changed"],
                            r["mean_displacement"],
                            json.dumps(r["ranks"]),
                            json.dumps(r.get("sources", {})),
                            lat_mean])


if __name__ == "__main__":
    main()
