#!/usr/bin/env python3
"""Phase 33A — Phase 3 gate: structured-output contract compatibility probe.

Runs the EXISTING ExploitAssessment structured-output contract unchanged
(same SYSTEM_PROMPT, same human prompt, same temperature=0.1, same schema,
same parsing) against both local models on representative corpus candidates.

Purpose: decide whether qwen2.5:3b can satisfy the existing contract BEFORE
integrating it. Does NOT modify the schema, the prompt, or the temperature.

Read-only w.r.t. the research core. Writes nothing to existing thesis files.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Unbuffered progress so a long/hung call is diagnosable mid-run.
os.environ.setdefault("PYTHONUNBUFFERED", "1")

from core.exploit_assessor import SYSTEM_PROMPT, assess_exploit_quality, get_llm
from core.schemas import ExploitAssessment, UsabilityRank

# Representative candidates: full corpus (same set the historical baseline used).
PROBE_CANDIDATES = [
    "CVE-2021-44228",
    "CVE-2017-0144",
    "CVE-2023-38408",
    "CVE-2022-22965",
    "CVE-2020-1472",
    "CVE-2021-26855",
    "CVE-2019-0708",
    "CVE-2022-1388",
]

MODELS = ["llama3.2:3b", "qwen2.5:3b"]


def probe_model(model_name: str) -> dict:
    out = {
        "model": model_name,
        "attempts": 0,
        "valid": 0,
        "schema_violation": 0,
        "parse_failure": 0,
        "fallback": 0,
        "latencies": [],
        "ranks": {},
        "errors": [],
        "records": [],
    }

    # Confirm the model is actually reachable through the real get_llm path.
    try:
        llm = get_llm(provider="ollama", model_name=model_name)
        _ = llm.invoke("ok")
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"get_llm/reachability failed: {e}")
        return out

    for cve in PROBE_CANDIDATES:
        out["attempts"] += 1
        t0 = time.perf_counter()
        print(f"    [{model_name}] -> {cve} ...", flush=True)
        try:
            a = assess_exploit_quality(cve, provider="ollama", model_name=model_name)
            dt = time.perf_counter() - t0
            print(f"    [{model_name}] <- {cve} {dt:.2f}s", flush=True)
            out["latencies"].append(round(dt, 4))
            if isinstance(a, ExploitAssessment) and isinstance(a.usability_rank, UsabilityRank):
                out["valid"] += 1
                out["ranks"][cve] = a.usability_rank.value
                out["records"].append({
                    "cve": cve,
                    "valid": True,
                    "usability_rank": a.usability_rank.value,
                    "syntax_valid": a.syntax_valid,
                    "privileges_required": a.privileges_required,
                    "network_noise": a.network_noise,
                    "complexity_score": a.complexity_score,
                    "prerequisites_met": a.prerequisites_met,
                    "latency_s": round(dt, 4),
                    "error": None,
                })
            else:
                out["schema_violation"] += 1
                out["records"].append({"cve": cve, "valid": False, "error": "non-schema return"})
        except Exception as e:  # noqa: BLE001
            dt = time.perf_counter() - t0
            msg = f"{type(e).__name__}: {e}"
            out["latencies"].append(round(dt, 4))
            if "validation" in msg.lower() or "schema" in msg.lower():
                out["schema_violation"] += 1
            else:
                out["parse_failure"] += 1
            out["errors"].append(f"{cve}: {msg[:200]}")
            out["records"].append({"cve": cve, "valid": False, "error": msg[:200]})

    return out


def main() -> int:
    print("=" * 72)
    print("PHASE 33A / PHASE 3 GATE — structured-output contract compatibility")
    print("=" * 72)
    print(f"prompt: core.exploit_assessor.SYSTEM_PROMPT (unchanged, {len(SYSTEM_PROMPT)} chars)")
    print("temperature: 0.1 (unchanged, set in get_llm)")
    print("schema: core.schemas.ExploitAssessment (unchanged)")
    print(f"candidates: {len(PROBE_CANDIDATES)} real corpus CVEs")
    print()

    results = {}
    for m in MODELS:
        print(f"--- {m} ---")
        r = probe_model(m)
        results[m] = r
        n = max(r["attempts"], 1)
        print(f"  attempts          : {r['attempts']}")
        print(f"  valid structured  : {r['valid']}  ({r['valid']/n:.0%})")
        print(f"  schema violations : {r['schema_violation']}")
        print(f"  parse failures    : {r['parse_failure']}")
        if r["latencies"]:
            print(f"  latency mean      : {sum(r['latencies'])/len(r['latencies']):.3f}s")
        print(f"  ranks             : {json.dumps(r['ranks'])}")
        if r["errors"]:
            print(f"  errors            : {r['errors'][:3]}")
        print()

    # Gate verdict
    print("=" * 72)
    q = results.get("qwen2.5:3b", {})
    qn = max(q.get("attempts", 0), 1)
    q_valid_rate = q.get("valid", 0) / qn if q.get("attempts") else 0.0
    if not q.get("attempts"):
        print("GATE: FAIL — qwen2.5:3b was not reachable via get_llm.")
        verdict = "FAIL"
    elif q_valid_rate >= 1.0:
        print(f"GATE: PASS — qwen2.5:3b satisfied the existing contract on "
              f"{q['valid']}/{q['attempts']} probes (100%).")
        verdict = "PASS"
    elif q_valid_rate >= 0.75:
        print(f"GATE: CONDITIONAL PASS — qwen2.5:3b valid on {q['valid']}/{q['attempts']} "
              f"({q_valid_rate:.0%}); investigate before full A/B.")
        verdict = "CONDITIONAL"
    else:
        print(f"GATE: FAIL — qwen2.5:3b valid on only {q['valid']}/{q['attempts']} "
              f"({q_valid_rate:.0%}). STOP and report per Phase 3.")
        verdict = "FAIL"

    os.makedirs("experiments/results", exist_ok=True)
    with open("experiments/results/phase33a_structured_output_probe.json", "w") as f:
        json.dump({"verdict": verdict, "probe": results}, f, indent=2)
    print("\nwrote experiments/results/phase33a_structured_output_probe.json")
    return 0 if verdict != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
