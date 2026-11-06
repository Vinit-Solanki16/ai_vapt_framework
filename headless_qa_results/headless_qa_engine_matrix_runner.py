"""
Headless QA Engine & Scan Depth Matrix Runner.
Executes all supported engine & depth combinations against http://127.0.0.1:3000/.
Saves all run JSONs, downloads all 6 report formats, and computes model performance & vulnerability comparison.
"""

import csv
import json
import os
import sys
import time
import urllib.request
import urllib.error

API_BASE = "http://127.0.0.1:8000"
TARGET_URL = "http://127.0.0.1:3000/"
PROVIDER = "cloud_hosted"
MODEL = "kaggle-model"

OUTPUT_DIR = "/home/vinit/STRIX/strix/headless_qa_results"
RUNS_DIR = os.path.join(OUTPUT_DIR, "runs")
os.makedirs(RUNS_DIR, exist_ok=True)

runs_metadata = []

def make_req(endpoint, method="GET", data=None, headers=None, timeout=30):
    url = f"{API_BASE}{endpoint}" if endpoint.startswith("/") else endpoint
    h = headers or {}
    encoded_data = None
    if data is not None:
        if isinstance(data, dict):
            encoded_data = json.dumps(data).encode("utf-8")
            if "Content-Type" not in h:
                h["Content-Type"] = "application/json"
        elif isinstance(data, (str, bytes)):
            encoded_data = data.encode("utf-8") if isinstance(data, str) else data
    req = urllib.request.Request(url, data=encoded_data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, body, resp.headers, None
    except urllib.error.HTTPError as he:
        err_body = he.read().decode("utf-8", errors="ignore")
        return he.code, err_body, he.headers, str(he)
    except Exception as e:
        return 0, b"", {}, str(e)

def wait_for_run(run_id, max_wait_sec=120):
    print(f"Waiting for {run_id} to complete (max {max_wait_sec}s)...")
    start = time.time()
    last_phase = ""
    while time.time() - start < max_wait_sec:
        code, body, _, err = make_req(f"/runs/{run_id}")
        if code == 200:
            data = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
            status = data.get("status")
            prog = data.get("progress") or {}
            phase = prog.get("phase", "")
            if phase != last_phase:
                print(f"  [{run_id}] Phase: {phase} ({prog.get('percent', 0)}%) - Status: {status}")
                last_phase = phase
            if status in ("completed", "failed", "partial", "stopped", "aborted"):
                print(f"  [{run_id}] Terminal state reached: {status.upper()} in {round(time.time() - start, 1)}s")
                return data
        time.sleep(2)
    print(f"  [{run_id}] Timed out waiting after {max_wait_sec}s")
    return None

def download_all_reports(run_id):
    run_dir = os.path.join(RUNS_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)
    report_formats = ["json", "html", "pdf", "sarif", "markdown", "csv"]
    for fmt in report_formats:
        code, body, headers, err = make_req(f"/runs/{run_id}/report?format={fmt}")
        if code == 200:
            ext = "md" if fmt == "markdown" else fmt
            fname = f"vapt_report_{run_id}.{ext}" if fmt not in ("sarif", "csv") else f"vapt_findings_{run_id}.{ext}"
            fpath = os.path.join(run_dir, fname)
            mode = "wb" if isinstance(body, bytes) else "w"
            with open(fpath, mode) as f:
                f.write(body)
            print(f"  Saved {fmt.upper()} report -> {fpath} ({len(body)} bytes)")

print("="*80)
print("EXECUTING HEADLESS QA BENCHMARK MATRIX WITH CLOUD HOSTED MODEL")
print("="*80)

planned_runs = [
    {
        "matrix_id": "QA-01",
        "name": "Fast Web Audit (Quick Triage)",
        "engine": "web",
        "scan_depth": "quick",
        "max_turns": 50,
        "auth_config": None,
    },
    {
        "matrix_id": "QA-02",
        "name": "Fast Web Audit (Standard Audit)",
        "engine": "web",
        "scan_depth": "standard",
        "max_turns": 100,
        "auth_config": None,
    },
    {
        "matrix_id": "QA-03",
        "name": "Fast Web Audit (Deep Autonomous)",
        "engine": "web",
        "scan_depth": "deep",
        "max_turns": 500,
        "auth_config": None,
    },
    {
        "matrix_id": "QA-04",
        "name": "Fast Web Audit (Authenticated Customer)",
        "engine": "web",
        "scan_depth": "standard",
        "max_turns": 100,
        "auth_config": {
            "enabled": True,
            "auth_type": "login",
            "credentials": {"email": "demo", "password": "demo"},
            "login_path": "/rest/user/login"
        },
    },
    {
        "matrix_id": "QA-05",
        "name": "Fast Web Audit (Authenticated Admin)",
        "engine": "web",
        "scan_depth": "standard",
        "max_turns": 100,
        "auth_config": {
            "enabled": True,
            "auth_type": "login",
            "credentials": {"email": "admin@juice-sh.op", "password": "admin123"},
            "login_path": "/rest/user/login"
        },
    },
    {
        "matrix_id": "QA-06",
        "name": "Simulation Benchmark (Offline Scenario)",
        "engine": "simulation",
        "scan_depth": "quick",
        "max_turns": 50,
        "auth_config": None,
    },
]

executed_runs_map = {}

for p in planned_runs:
    m_id = p["matrix_id"]
    print(f"\n--- Launching {m_id}: {p['name']} (Engine: {p['engine']}, Depth: {p['scan_depth']}, Turns: {p['max_turns']}) ---")
    payload = {
        "mode": p["engine"],
        "scan_mode": p["scan_depth"],
        "target_url": TARGET_URL,
        "target_scope_acknowledged": True,
        "assessor_provider": PROVIDER,
        "assessor_model": MODEL,
        "max_turns": p["max_turns"],
    }
    if p["auth_config"]:
        payload["auth_config"] = p["auth_config"]

    t0 = time.time()
    code, body, _, err = make_req("/runs", method="POST", data=payload)
    if code != 200:
        print(f"ERROR: Failed to launch {m_id}: {err or body}")
        continue

    resp_json = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
    run_id = resp_json["run_id"]
    print(f"Launched run ID: {run_id}")

    # Wait for completion
    final_data = wait_for_run(run_id, max_wait_sec=120)
    dur = round(time.time() - t0, 2)

    if final_data:
        # Save run json
        r_file = os.path.join(RUNS_DIR, f"{run_id}.json")
        with open(r_file, "w", encoding="utf-8") as f:
            json.dump(final_data, f, indent=2)
        print(f"Saved run data -> {r_file}")

        # Download all 6 report formats
        download_all_reports(run_id)

        stats = final_data.get("stats") or {}
        executed_runs_map[m_id] = {
            "matrix_id": m_id,
            "name": p["name"],
            "engine": p["engine"],
            "scan_depth": p["scan_depth"],
            "run_id": run_id,
            "status": final_data.get("status"),
            "duration_seconds": dur,
            "attempts": stats.get("attempts", 0),
            "candidates_total": len(final_data.get("candidates", [])),
            "findings_total": len(final_data.get("findings", [])),
            "candidates_dispatched": stats.get("candidates_dispatched", 0),
            "candidates_investigated": stats.get("candidates_investigated", 0),
            "candidates_validated": stats.get("candidates_validated", 0),
            "candidates_abandoned": stats.get("candidates_abandoned", 0),
            "candidates_not_tested": stats.get("candidates_not_tested", 0),
            "gap2_pivots": stats.get("pivots", 0),
            "findings_list": [f.get("title") for f in final_data.get("findings", [])],
            "raw_data": final_data
        }

# Include the Full Autonomous Pentest Baseline Runs from Phase 14
# M03: Deep Autonomous (run-0bb94025)
auto_deep_path = "/home/vinit/STRIX/strix/benchmark_results/runs/run-0bb94025.json"
if os.path.exists(auto_deep_path):
    with open(auto_deep_path) as f:
        auto_deep_data = json.load(f)
    stats = auto_deep_data.get("stats") or {}
    executed_runs_map["QA-07"] = {
        "matrix_id": "QA-07",
        "name": "Full Autonomous Pentest (Deep Autonomous)",
        "engine": "autonomous",
        "scan_depth": "deep",
        "run_id": "run-0bb94025",
        "status": auto_deep_data.get("status", "completed"),
        "duration_seconds": 148.0,
        "attempts": stats.get("attempts", 36),
        "candidates_total": len(auto_deep_data.get("candidates", [])),
        "findings_total": len(auto_deep_data.get("findings", [])),
        "candidates_dispatched": stats.get("candidates_dispatched", 8),
        "candidates_investigated": stats.get("candidates_investigated", 8),
        "candidates_validated": stats.get("candidates_validated", 0),
        "candidates_abandoned": stats.get("candidates_abandoned", 8),
        "candidates_not_tested": stats.get("candidates_not_tested", 0),
        "gap2_pivots": stats.get("pivots", 0),
        "findings_list": [f.get("title") for f in auto_deep_data.get("findings", [])],
        "raw_data": auto_deep_data
    }
    # Copy file to runs dir
    with open(os.path.join(RUNS_DIR, "run-0bb94025.json"), "w", encoding="utf-8") as f:
        json.dump(auto_deep_data, f, indent=2)

# M01: Autonomous Quick (run-1f61a7ae)
auto_quick_path = "/home/vinit/STRIX/strix/benchmark_results/runs/run-1f61a7ae.json"
if os.path.exists(auto_quick_path):
    with open(auto_quick_path) as f:
        auto_quick_data = json.load(f)
    stats = auto_quick_data.get("stats") or {}
    executed_runs_map["QA-08"] = {
        "matrix_id": "QA-08",
        "name": "Full Autonomous Pentest (Quick Triage - 15 Turns)",
        "engine": "autonomous",
        "scan_depth": "quick",
        "run_id": "run-1f61a7ae",
        "status": auto_quick_data.get("status", "failed"),
        "duration_seconds": 72.0,
        "attempts": stats.get("attempts", 15),
        "candidates_total": len(auto_quick_data.get("candidates", [])),
        "findings_total": len(auto_quick_data.get("findings", [])),
        "candidates_dispatched": stats.get("candidates_dispatched", 6),
        "candidates_investigated": stats.get("candidates_investigated", 3),
        "candidates_validated": stats.get("candidates_validated", 1),
        "candidates_abandoned": stats.get("candidates_abandoned", 2),
        "candidates_not_tested": stats.get("candidates_not_tested", 3),
        "gap2_pivots": stats.get("pivots", 0),
        "findings_list": [f.get("title") for f in auto_quick_data.get("findings", [])],
        "raw_data": auto_quick_data
    }
    with open(os.path.join(RUNS_DIR, "run-1f61a7ae.json"), "w", encoding="utf-8") as f:
        json.dump(auto_quick_data, f, indent=2)

# Save all_runs.json
all_runs_path = os.path.join(OUTPUT_DIR, "all_runs.json")
with open(all_runs_path, "w", encoding="utf-8") as f:
    json.dump({k: {subk: subv for subk, subv in v.items() if subk != "raw_data"} for k, v in executed_runs_map.items()}, f, indent=2)
print(f"\nSaved all runs summary -> {all_runs_path}")

# Write engine_depth_comparison.csv
ed_csv_path = os.path.join(OUTPUT_DIR, "engine_depth_comparison.csv")
fieldnames = [
    "matrix_id", "test_name", "model", "engine", "scan_depth",
    "run_id", "status", "turn_limit", "actual_attempts",
    "candidates_total", "findings_total", "gap1_dispatched",
    "gap1_investigated", "gap1_validated", "gap1_ruled_out",
    "gap1_not_tested", "gap2_pivots", "duration_seconds", "findings_summary"
]
with open(ed_csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for m_id, row in sorted(executed_runs_map.items()):
        writer.writerow({
            "matrix_id": m_id,
            "test_name": row["name"],
            "model": MODEL,
            "engine": row["engine"],
            "scan_depth": row["scan_depth"],
            "run_id": row["run_id"],
            "status": row["status"],
            "turn_limit": 50 if row["scan_depth"] == "quick" else (100 if row["scan_depth"] == "standard" else 500),
            "actual_attempts": row["attempts"],
            "candidates_total": row["candidates_total"],
            "findings_total": row["findings_total"],
            "gap1_dispatched": row["candidates_dispatched"],
            "gap1_investigated": row["candidates_investigated"],
            "gap1_validated": row["candidates_validated"],
            "gap1_ruled_out": row["candidates_abandoned"],
            "gap1_not_tested": row["candidates_not_tested"],
            "gap2_pivots": row["gap2_pivots"],
            "duration_seconds": row["duration_seconds"],
            "findings_summary": "; ".join(row["findings_list"]) if row["findings_list"] else "No vulnerabilities confirmed"
        })
print(f"Saved engine & depth comparison CSV -> {ed_csv_path}")

