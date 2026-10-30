"""PHASE 33B — Quality-discriminating GAP-1 effectiveness experiment.

RESEARCH-ONLY, ADDITIVE script. Does NOT modify:
  decision_engine/core/, decision_engine/benchmarks/,
  the ranking algorithm, GAP-1, or any historical results.

Goal: test whether pre-execution quality assessment (GAP-1) changes
candidate ranking when the candidate population is DELIBERATELY
quality-discriminating (the Phase-33A 8-CVE corpus had insufficient
ranking leverage: few probability tiers, uniform quality ranks).

Corpus: CONTROLLED SYNTHETIC research samples (IDs SYN-QD-*). These are
NOT real-world exploit evidence and are NEVER executed. They exercise the
decision mechanism only: syntax validity, dependencies, privileges,
network noise, complexity — the exact dimensions the assessor prompt grades.

Arms (identical corpus, order, probabilities, prompt, schema, temperature,
ranking formula for every arm):
  A. No-assessment baseline (probability order only)
  B. Deterministic assessment (offline, reproducible)
  C. Llama 3.2 3B via Ollama (model_name="llama3.2:3b")
  D. Qwen 2.5 3B via Ollama (model_name="qwen2.5:3b")

Ranking: priority = probability * (0.5 + 0.5 * quality), quality weights
HIGH=1.0 / MEDIUM=0.6 / LOW=0.3 (decision_engine/core/schemas.py, unmodified,
used read-only via rank_candidates import).
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
from decision_engine.core.schemas import QualityRank, candidate_from_dict

# ---------------------------------------------------------------------------
# Controlled synthetic corpus (NOT real exploits; never executed)
# ---------------------------------------------------------------------------

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

# (id, probability, ground_truth-for-deterministic-arm, intended_tier, code)
CORPUS = [
    ("SYN-QD-HIGH-01", 0.55, "SUCCESS", "HIGH", HIGH_01),
    ("SYN-QD-HIGH-02", 0.62, "SUCCESS", "HIGH", HIGH_02),
    ("SYN-QD-MED-01", 0.68, "FAIL_TIMEOUT", "MEDIUM", MED_01),
    ("SYN-QD-MED-02", 0.74, "FAIL_TIMEOUT", "MEDIUM", MED_02),
    ("SYN-QD-LOW-01", 0.80, "FAIL_SYNTAX", "LOW", LOW_01),
    ("SYN-QD-LOW-02", 0.88, "FAIL_DEPENDENCY", "LOW", LOW_02),
]

REPS = 5
TOP_K = 3
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def _fresh_candidates():
    return [
        {"id": cid, "probability": prob, "ground_truth": gt}
        for cid, prob, gt, _tier, _code in CORPUS
    ]


def baseline_order():
    cands = [candidate_from_dict(d) for d in _fresh_candidates()]
    return [c.id for c in rank_candidates(cands)]  # unassessed: prob order


def assess_with_ranks(rank_by_id):
    """Build assessed ActionCandidates from an id->QualityRank map and rank."""
    cands = [candidate_from_dict(d) for d in _fresh_candidates()]
    for c in cands:
        c.quality_rank = rank_by_id[c.id]
        c.assessed = True
    ranked = rank_candidates(cands)
    return [c.id for c in ranked], {c.id: c.priority_score() for c in ranked}


def rep_metrics(baseline, assessed):
    base_pos = {cid: i for i, cid in enumerate(baseline)}
    ass_pos = {cid: i for i, cid in enumerate(assessed)}
    displ = {cid: abs(ass_pos[cid] - base_pos[cid]) for cid in baseline}
    return {
        "baseline_order": list(baseline),
        "assessed_order": list(assessed),
        "order_changed": assessed != baseline,
        "top1_changed": (assessed[0] != baseline[0]) if assessed else False,
        "topk_changed": (
            assessed[:TOP_K] != baseline[:TOP_K]
        ),
        "displacements": displ,
        "mean_displacement": round(statistics.mean(displ.values()), 4),
        "total_displacement": int(sum(displ.values())),
        "positions_moved": int(sum(1 for v in displ.values() if v > 0)),
    }


def run_deterministic_arm():
    reps, detail_rows = [], []
    for rep in range(REPS):
        ranks = {}
        t0 = time.perf_counter()
        for cid, prob, gt, _tier, _code in CORPUS:
            ranks[cid] = deterministic_assessor(
                candidate_from_dict(
                    {"id": cid, "probability": prob, "ground_truth": gt}
                )
            )
        lat = (time.perf_counter() - t0) / len(CORPUS)
        assessed, scores = assess_with_ranks(ranks)
        m = rep_metrics(BASELINE, assessed)
        m.update({"rep": rep, "ranks": {k: v.value for k, v in ranks.items()},
                  "scores": scores, "latency_s": round(lat, 6),
                  "source": "deterministic"})
        reps.append(m)
        for cid, _, _, _, _ in CORPUS:
            detail_rows.append({"rep": rep, "candidate": cid, "rank": ranks[cid].value,
                                "source": "deterministic", "latency_s": round(lat, 6)})
    return reps, detail_rows


def run_llm_arm(model_name):
    from core.exploit_assessor import assess_exploit_quality

    reps, detail_rows = [], []
    valid, fallback = 0, 0
    for rep in range(REPS):
        ranks, sources, latencies, errors = {}, {}, {}, {}
        for cid, _p, _g, _t, code in CORPUS:
            t0 = time.perf_counter()
            try:
                a = assess_exploit_quality(
                    cid, code_sample=code, provider="ollama",
                    model_name=model_name, use_online=False,
                )
                el = time.perf_counter() - t0
                ranks[cid] = QualityRank(a.usability_rank.value)
                sources[cid] = "llm"
                valid += 1
            except Exception as exc:  # invalid structured output / transport
                el = time.perf_counter() - t0
                fb = deterministic_assessor(candidate_from_dict(
                    {"id": cid, "probability": 0.0}))
                ranks[cid] = fb
                sources[cid] = "fallback"
                errors[cid] = str(exc)[:300]
                fallback += 1
            latencies[cid] = round(el, 4)
            print(f"[{model_name} rep {rep}] {cid} -> {ranks[cid].value} "
                  f"({sources[cid]}, {el:.2f}s)", flush=True)
        assessed, scores = assess_with_ranks(ranks)
        m = rep_metrics(BASELINE, assessed)
        m.update({"rep": rep, "ranks": {k: v.value for k, v in ranks.items()},
                  "scores": scores, "sources": sources, "latencies": latencies,
                  "errors": errors})
        reps.append(m)
        for cid, _, _, _, _ in CORPUS:
            detail_rows.append({"rep": rep, "candidate": cid,
                                "rank": ranks[cid].value,
                                "source": sources[cid],
                                "latency_s": latencies[cid]})
    return reps, detail_rows, {"valid_outputs": valid, "fallbacks": fallback,
                               "total": valid + fallback}


def summarize_arm(name, reps):
    n = len(reps)
    changed = sum(1 for r in reps if r["order_changed"])
    top1 = sum(1 for r in reps if r["top1_changed"])
    topk = sum(1 for r in reps if r["topk_changed"])
    meand = [r["mean_displacement"] for r in reps]
    qdist: dict[str, int] = {}
    for r in reps:
        for v in r["ranks"].values():
            qdist[v] = qdist.get(v, 0) + 1
    out = {
        "arm": name,
        "reps": n,
        "ranking_change_rate": round(changed / n, 4),
        "top1_change_rate": round(top1 / n, 4),
        f"top{TOP_K}_change_rate": round(topk / n, 4),
        "mean_rank_displacement": {
            "mean": round(statistics.mean(meand), 4),
            "median": round(statistics.median(meand), 4),
            "stdev": round(statistics.pstdev(meand), 4),
            "min": round(min(meand), 4),
            "max": round(max(meand), 4),
        },
        "quality_distribution": qdist,
    }
    return out


def consistency_of(detail_rows):
    per_cand: dict[str, list[str]] = {}
    for row in detail_rows:
        per_cand.setdefault(row["candidate"], []).append(row["rank"])
    per, modes = {}, {}
    for cid, ranks in per_cand.items():
        mode = statistics.mode(ranks)
        modes[cid] = mode
        per[cid] = {"ranks": ranks, "mode": mode,
                    "agreement": round(ranks.count(mode) / len(ranks), 4),
                    "fully_consistent": len(set(ranks)) == 1}
    overall = round(statistics.mean([v["agreement"] for v in per.values()]), 4)
    return per, modes, overall


def latency_stats(detail_rows):
    lat = [r["latency_s"] for r in detail_rows]
    return {"n": len(lat), "mean": round(statistics.mean(lat), 4),
            "median": round(statistics.median(lat), 4),
            "stdev": round(statistics.pstdev(lat), 4) if len(lat) > 1 else 0.0,
            "min": round(min(lat), 4), "max": round(max(lat), 4)}


BASELINE = baseline_order()


def main():
    started = datetime.now(timezone.utc).isoformat()
    print(f"Baseline (no-assessment) order: {BASELINE}", flush=True)

    det_reps, det_rows = run_deterministic_arm()
    det_summary = summarize_arm("deterministic", det_reps)
    det_summary["fallback_rate"] = 0.0
    det_cons, det_modes, det_overall = consistency_of(det_rows)
    det_summary["consistency"] = {"per_candidate": det_cons,
                                  "overall_agreement": det_overall}
    det_summary["latency"] = latency_stats(det_rows)
    print("Deterministic done: " + json.dumps(det_summary), flush=True)

    llama_reps, llama_rows, llama_io = run_llm_arm("llama3.2:3b")
    llama_summary = summarize_arm("llama3.2:3b", llama_reps)
    llama_summary["valid_output_rate"] = round(
        llama_io["valid_outputs"] / llama_io["total"], 4)
    llama_summary["fallback_rate"] = round(
        llama_io["fallbacks"] / llama_io["total"], 4)
    llama_cons, llama_modes, llama_overall = consistency_of(llama_rows)
    llama_summary["consistency"] = {"per_candidate": llama_cons,
                                    "overall_agreement": llama_overall}
    llama_summary["latency"] = latency_stats(llama_rows)
    print("Llama done: " + json.dumps(llama_summary), flush=True)

    qwen_reps, qwen_rows, qwen_io = run_llm_arm("qwen2.5:3b")
    qwen_summary = summarize_arm("qwen2.5:3b", qwen_reps)
    qwen_summary["valid_output_rate"] = round(
        qwen_io["valid_outputs"] / qwen_io["total"], 4)
    qwen_summary["fallback_rate"] = round(
        qwen_io["fallbacks"] / qwen_io["total"], 4)
    qwen_cons, qwen_modes, qwen_overall = consistency_of(qwen_rows)
    qwen_summary["consistency"] = {"per_candidate": qwen_cons,
                                   "overall_agreement": qwen_overall}
    qwen_summary["latency"] = latency_stats(qwen_rows)
    print("Qwen done: " + json.dumps(qwen_summary), flush=True)

    inter = {cid: (llama_modes[cid] == qwen_modes[cid])
             for cid, _, _, _, _ in CORPUS}
    inter_agreement = round(sum(inter.values()) / len(inter), 4)

    payload = {
        "experiment": "gap1_quality_discriminating",
        "phase": "33B",
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "research_integrity_note": (
            "Controlled synthetic corpus (SYN-QD-*). NOT real-world exploit "
            "evidence. Nothing executed. Ranking algorithm, GAP-1, prompts, "
            "schema, temperature unchanged; decision_engine/core and "
            "decision_engine/benchmarks unmodified."
        ),
        "protocol": {
            "corpus": [{"id": cid, "probability": p, "ground_truth": g,
                        "intended_tier": t}
                       for cid, p, g, t, _c in CORPUS],
            "candidate_order": [c[0] for c in CORPUS],
            "repetitions": REPS,
            "provider": "ollama",
            "models": ["llama3.2:3b", "qwen2.5:3b"],
            "temperature": 0.1,
            "prompt": "core/exploit_assessor.py SYSTEM_PROMPT + human template (unchanged)",
            "schema": "core/schemas.py ExploitAssessment (unchanged)",
            "ranking_formula": "probability * (0.5 + 0.5 * quality); "
                               "HIGH=1.0, MEDIUM=0.6, LOW=0.3",
            "use_online": False,
            "top_k": TOP_K,
        },
        "baseline_order": BASELINE,
        "arms": {
            "no_assessment_baseline": {"order": BASELINE},
            "deterministic": {"summary": det_summary, "reps": det_reps},
            "llama3.2:3b": {"summary": llama_summary, "reps": llama_reps},
            "qwen2.5:3b": {"summary": qwen_summary, "reps": qwen_reps},
        },
        "inter_model_agreement": {
            "mode_ranks_llama": llama_modes,
            "mode_ranks_qwen": qwen_modes,
            "per_candidate_agree": inter,
            "agreement_rate": inter_agreement,
        },
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    json_path = os.path.join(RESULTS_DIR, "gap1_quality_discriminating.json")
    csv_path = os.path.join(RESULTS_DIR, "gap1_quality_discriminating.csv")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    write_csv_from_payload(payload, csv_path)

    print(f"Wrote {json_path}", flush=True)
    print(f"Wrote {csv_path}", flush=True)
    print("INTER_MODEL_AGREEMENT: " + json.dumps(
        {"rate": inter_agreement, "per_candidate": inter}), flush=True)


def write_csv_from_payload(payload, csv_path):
    arms = payload["arms"]
    rep_maps = {
        name: {r["rep"]: r for r in arms[name]["reps"]}
        for name in ("deterministic", "llama3.2:3b", "qwen2.5:3b")
    }
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "arm", "rep", "candidate", "rank", "source", "latency_s",
            "baseline_position", "assessed_position",
            "position_displacement", "order_changed", "top1_changed",
            "topk_changed"])
        writer.writeheader()
        for arm_name in ("deterministic", "llama3.2:3b", "qwen2.5:3b"):
            for rep in arms[arm_name]["reps"]:
                m = rep_maps[arm_name][rep["rep"]]
                lat = rep.get("latencies", {})
                src = rep.get("sources", {})
                for cid in payload["protocol"]["candidate_order"]:
                    writer.writerow({
                        "arm": arm_name,
                        "rep": rep["rep"],
                        "candidate": cid,
                        "rank": rep["ranks"][cid],
                        "source": src.get(cid, rep.get("source", "deterministic")),
                        "latency_s": lat.get(cid, rep.get("latency_s", 0.0)),
                        "baseline_position": m["baseline_order"].index(cid),
                        "assessed_position": m["assessed_order"].index(cid),
                        "position_displacement": m["displacements"][cid],
                        "order_changed": m["order_changed"],
                        "top1_changed": m["top1_changed"],
                        "topk_changed": m["topk_changed"],
                    })


if __name__ == "__main__":
    main()
