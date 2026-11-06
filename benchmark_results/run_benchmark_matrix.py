import urllib.request
import urllib.error
import json
import time
import os
import sys

BASE_URL = "http://127.0.0.1:8000"
RUNS_DIR = "/home/vinit/STRIX/strix/benchmark_results/runs"
os.makedirs(RUNS_DIR, exist_ok=True)

def wait_for_no_active_run(timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/runs") as resp:
                data = json.loads(resp.read().decode())
                runs = data if isinstance(data, list) else data.get("runs", [])
                active = [r for r in runs if r.get("status") in ("running", "queued")]
                if not active:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False

def launch_run(payload):
    req = urllib.request.Request(
        f"{BASE_URL}/runs",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        return {"error": f"HTTP {e.code}: {err_msg}"}
    except Exception as e:
        return {"error": str(e)}

def poll_run(run_id, timeout=300):
    t0 = time.time()
    last_status = "unknown"
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/runs/{run_id}") as resp:
                data = json.loads(resp.read().decode())
                status = data.get("status")
                last_status = status
                if status in ("completed", "failed", "stopped"):
                    return data
        except Exception:
            pass
        time.sleep(2)
    return {"run_id": run_id, "status": f"timed_out ({last_status})"}

def save_run_artifact(run_data):
    run_id = run_data.get("run_id") or run_data.get("id") or f"run-{int(time.time())}"
    path = os.path.join(RUNS_DIR, f"{run_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(run_data, f, indent=2)
    print(f"  Saved raw artifact -> {path}")

# Load previously completed runs if available
existing_runs = {
    "kaggle-model_autonomous_deep": "run-0bb94025",
    "kaggle-model_web_quick": "run-b8a6120b",
    "kaggle-model_simulation_quick": "run-1e52cd85",
}

for key, r_id in existing_runs.items():
    try:
        with urllib.request.urlopen(f"{BASE_URL}/runs/{r_id}") as resp:
            d = json.loads(resp.read().decode())
            save_run_artifact(d)
            print(f"Loaded existing baseline run {r_id} for {key}")
    except Exception as e:
        print(f"Could not load {r_id}: {e}")

matrix_tests = [
    # Kaggle Model Tests
    {
        "name": "kaggle-model_web_standard",
        "payload": {
            "mode": "web",
            "scan_mode": "standard",
            "target_url": "http://127.0.0.1:3000/",
            "target_scope_acknowledged": True,
            "assessor_provider": "cloud_hosted",
            "assessor_model": "kaggle-model",
            "max_turns": 100
        }
    },
    {
        "name": "kaggle-model_web_deep",
        "payload": {
            "mode": "web",
            "scan_mode": "deep",
            "target_url": "http://127.0.0.1:3000/",
            "target_scope_acknowledged": True,
            "assessor_provider": "cloud_hosted",
            "assessor_model": "kaggle-model",
            "max_turns": 500
        }
    },
    {
        "name": "kaggle-model_simulation_standard",
        "payload": {
            "mode": "simulation",
            "scenario": "default",
            "scan_mode": "standard",
            "target_scope_acknowledged": True,
            "assessor_provider": "cloud_hosted",
            "assessor_model": "kaggle-model",
            "max_turns": 100
        }
    },
    {
        "name": "kaggle-model_simulation_deep",
        "payload": {
            "mode": "simulation",
            "scenario": "default",
            "scan_mode": "deep",
            "target_scope_acknowledged": True,
            "assessor_provider": "cloud_hosted",
            "assessor_model": "kaggle-model",
            "max_turns": 500
        }
    },
    # Ollama Model Tests
    {
        "name": "ollama_web_quick",
        "payload": {
            "mode": "web",
            "scan_mode": "quick",
            "target_url": "http://127.0.0.1:3000/",
            "target_scope_acknowledged": True,
            "assessor_provider": "ollama",
            "assessor_model": "qwen2.5:1.5b",
            "max_turns": 50
        }
    },
    {
        "name": "ollama_web_standard",
        "payload": {
            "mode": "web",
            "scan_mode": "standard",
            "target_url": "http://127.0.0.1:3000/",
            "target_scope_acknowledged": True,
            "assessor_provider": "ollama",
            "assessor_model": "qwen2.5:1.5b",
            "max_turns": 100
        }
    },
    {
        "name": "ollama_simulation_quick",
        "payload": {
            "mode": "simulation",
            "scenario": "default",
            "scan_mode": "quick",
            "target_scope_acknowledged": True,
            "assessor_provider": "ollama",
            "assessor_model": "qwen2.5:1.5b",
            "max_turns": 50
        }
    },
]

summary_records = []

for item in matrix_tests:
    test_name = item["name"]
    payload = item["payload"]
    print(f"\n--- Running Benchmark: {test_name} ---")
    wait_for_no_active_run()
    
    t_start = time.time()
    res = launch_run(payload)
    if "error" in res:
        print(f"Launch error for {test_name}: {res['error']}")
        summary_records.append({
            "name": test_name,
            "status": "error",
            "error": res["error"],
            "duration": 0
        })
        continue
    
    run_id = res.get("run_id")
    print(f"Launched {test_name} -> {run_id}")
    final_data = poll_run(run_id, timeout=120)
    t_dur = round(time.time() - t_start, 2)
    final_data["benchmark_name"] = test_name
    final_data["duration_seconds"] = t_dur
    save_run_artifact(final_data)
    
    stats = final_data.get("stats", {})
    summary_records.append({
        "name": test_name,
        "run_id": run_id,
        "status": final_data.get("status"),
        "duration": t_dur,
        "findings": len(final_data.get("findings", [])),
        "candidates": len(final_data.get("candidates", [])),
        "attempts": stats.get("attempts", 0),
        "pivots": stats.get("pivots", 0),
        "dispatched": stats.get("candidates_dispatched", 0),
        "investigated": stats.get("candidates_investigated", 0),
        "validated": stats.get("candidates_validated", 0),
        "abandoned": stats.get("candidates_abandoned", 0)
    })
    print(f"Completed {test_name}: {final_data.get('status')} in {t_dur}s (findings={len(final_data.get('findings', []))})")

with open("/home/vinit/STRIX/strix/benchmark_results/matrix_summary.json", "w") as f:
    json.dump(summary_records, f, indent=2)
print("\nAll matrix executions finished successfully.")
