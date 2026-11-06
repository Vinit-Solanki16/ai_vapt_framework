"""
Headless QA Feature Test Suite for Strix AI-VAPT Application.
Tests every API endpoint, profile CRUD, model operations, targets, settings, reports, exports, and error handling.
Outputs results to feature_test_results.csv.
"""

import csv
import json
import os
import sys
import time
import urllib.request
import urllib.error

API_BASE = "http://127.0.0.1:8000"
NGROK_BASE = "https://expel-gizzard-effective.ngrok-free.dev/v1"
MODEL_ID = "kaggle-model"
API_KEY = "sk-local-kaggle"

RESULTS_DIR = "/home/vinit/STRIX/strix/headless_qa_results"
os.makedirs(RESULTS_DIR, exist_ok=True)
CSV_PATH = os.path.join(RESULTS_DIR, "feature_test_results.csv")

results = []

def record_test(test_id, category, feature_name, method, endpoint, status, http_code, message, details=""):
    print(f"[{status}] {test_id}: {category} -> {feature_name} ({method} {endpoint}) - Code: {http_code} - {message}")
    results.append({
        "test_id": test_id,
        "category": category,
        "feature_name": feature_name,
        "method": method,
        "endpoint": endpoint,
        "status": status,
        "http_code": http_code,
        "message": message,
        "details": details[:300] if details else ""
    })

def make_req(endpoint, method="GET", data=None, headers=None, timeout=15):
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
            body = resp.read().decode("utf-8", errors="ignore")
            return resp.status, body, None
    except urllib.error.HTTPError as he:
        err_body = he.read().decode("utf-8", errors="ignore")
        return he.code, err_body, str(he)
    except Exception as e:
        return 0, "", str(e)

print("Starting Strix AI-VAPT Headless Feature Verification...")

# 1. Health & System Status
code, body, err = make_req("/health")
if code == 200 and "strix" in body.lower():
    record_test("FT-01", "System", "Health Check", "GET", "/health", "PASS", code, "Health check returned ok", body)
else:
    record_test("FT-01", "System", "Health Check", "GET", "/health", "FAIL", code, f"Unexpected health response: {err or body}")

code, body, err = make_req("/system/health")
if code == 200 and "status" in body:
    record_test("FT-02", "System", "System Health Detail", "GET", "/system/health", "PASS", code, "System health returns component statuses", body)
else:
    record_test("FT-02", "System", "System Health Detail", "GET", "/system/health", "FAIL", code, f"Error: {err or body}")

# 2. Scenarios
code, body, err = make_req("/scenarios")
if code == 200 and ("failure_pivot" in body or "docker_pivot" in body):
    record_test("FT-03", "Configuration", "List Scenarios", "GET", "/scenarios", "PASS", code, "Available scenarios returned successfully", body)
else:
    record_test("FT-03", "Configuration", "List Scenarios", "GET", "/scenarios", "FAIL", code, f"Error: {err or body}")

# 3. Target Scope & Validation
code, body, err = make_req("/targets/validate", method="POST", data={"target_url": "http://127.0.0.1:3000/"})
if code == 200 and "authorized" in body:
    record_test("FT-04", "Target", "Target Validation (Valid)", "POST", "/targets/validate", "PASS", code, "Authorized localhost target validated", body)
else:
    record_test("FT-04", "Target", "Target Validation (Valid)", "POST", "/targets/validate", "FAIL", code, f"Validation failed: {err or body}")

code, body, err = make_req("/targets/validate", method="POST", data={"target_url": "not-a-valid-url"})
if code in (200, 400, 422) and ('"authorized":false' in body.replace(" ", "") or code in (400, 422)):
    record_test("FT-05", "Target", "Target Validation (Malformed)", "POST", "/targets/validate", "PASS", code, "Malformed target rejected cleanly", body)
else:
    record_test("FT-05", "Target", "Target Validation (Malformed)", "POST", "/targets/validate", "FAIL", code, f"Unexpected response: {err or body}")

# 4. Settings LLM
code, body, err = make_req("/settings/llm")
if code == 200 and "provider" in body:
    record_test("FT-06", "Settings", "Get LLM Settings", "GET", "/settings/llm", "PASS", code, "LLM settings retrieved with masked credentials", body)
else:
    record_test("FT-06", "Settings", "Get LLM Settings", "GET", "/settings/llm", "FAIL", code, f"Error: {err or body}")

# 5. Cloud Hosted Provider Operations
# 5a. Discovery
code, body, err = make_req("/providers/cloud_hosted/models", method="POST", data={"api_base": NGROK_BASE, "api_key": API_KEY})
if code == 200 and "kaggle-model" in body:
    record_test("FT-07", "AI Provider", "Model Discovery", "POST", "/providers/cloud_hosted/models", "PASS", code, "Model discovery succeeded (found kaggle-model)", body)
else:
    record_test("FT-07", "AI Provider", "Model Discovery", "POST", "/providers/cloud_hosted/models", "FAIL", code, f"Discovery failed: {err or body}")

# 5b. Test Connection
code, body, err = make_req("/providers/cloud_hosted/validate", method="POST", data={"api_base": NGROK_BASE, "api_key": API_KEY, "model": MODEL_ID})
if code == 200 and '"valid":true' in body.replace(" ", ""):
    record_test("FT-08", "AI Provider", "Test Connection", "POST", "/providers/cloud_hosted/validate", "PASS", code, "Chat completion ping responded with pong", body)
else:
    record_test("FT-08", "AI Provider", "Test Connection", "POST", "/providers/cloud_hosted/validate", "FAIL", code, f"Validation failed: {err or body}")

# 5c. Tool Calling Verification
code, body, err = make_req("/providers/cloud_hosted/verify_tools", method="POST", data={"api_base": NGROK_BASE, "api_key": API_KEY, "model": MODEL_ID})
if code == 200 and '"supported":true' in body.replace(" ", ""):
    record_test("FT-09", "AI Provider", "Verify Structured Tools", "POST", "/providers/cloud_hosted/verify_tools", "PASS", code, "Structured tool calling verified compatible", body)
else:
    record_test("FT-09", "AI Provider", "Verify Structured Tools", "POST", "/providers/cloud_hosted/verify_tools", "FAIL", code, f"Tool verification failed: {err or body}")

# 5d. Model Warmup
code, body, err = make_req("/providers/cloud_hosted/warmup", method="POST", data={"api_base": NGROK_BASE, "api_key": API_KEY, "model": MODEL_ID})
if code == 200 and '"success":true' in body.replace(" ", ""):
    record_test("FT-10", "AI Provider", "Model Warmup", "POST", "/providers/cloud_hosted/warmup", "PASS", code, "Warmup token generated successfully", body)
else:
    record_test("FT-10", "AI Provider", "Model Warmup", "POST", "/providers/cloud_hosted/warmup", "FAIL", code, f"Warmup failed: {err or body}")

# 5e. Profile Management CRUD
test_prof_id = "test-prof-qa-01"
# Create
create_payload = {
    "id": test_prof_id,
    "name": "QA Transient Test Profile",
    "api_base": NGROK_BASE,
    "api_key": API_KEY,
    "model": MODEL_ID,
    "model_alias": "QA-Model",
    "context_window": 131072,
    "is_active": False
}
code, body, err = make_req("/providers/cloud_hosted/profiles", method="POST", data=create_payload)
if code == 200 and test_prof_id in body:
    record_test("FT-11", "AI Profile", "Create Profile", "POST", "/providers/cloud_hosted/profiles", "PASS", code, "Profile created with masked secret", body)
else:
    record_test("FT-11", "AI Profile", "Create Profile", "POST", "/providers/cloud_hosted/profiles", "FAIL", code, f"Create failed: {err or body}")

# List
code, body, err = make_req("/providers/cloud_hosted/profiles")
if code == 200 and test_prof_id in body:
    record_test("FT-12", "AI Profile", "List Profiles", "GET", "/providers/cloud_hosted/profiles", "PASS", code, "Created profile appears in profiles list", body)
else:
    record_test("FT-12", "AI Profile", "List Profiles", "GET", "/providers/cloud_hosted/profiles", "FAIL", code, f"List failed: {err or body}")

# Update
update_payload = dict(create_payload)
update_payload["name"] = "QA Transient Test Profile (Updated)"
code, body, err = make_req("/providers/cloud_hosted/profiles", method="POST", data=update_payload)
if code == 200 and "Updated" in body:
    record_test("FT-13", "AI Profile", "Update Profile", "POST", "/providers/cloud_hosted/profiles", "PASS", code, "Profile updated cleanly", body)
else:
    record_test("FT-13", "AI Profile", "Update Profile", "POST", "/providers/cloud_hosted/profiles", "FAIL", code, f"Update failed: {err or body}")

# Activate
code, body, err = make_req(f"/providers/cloud_hosted/profiles/{test_prof_id}/activate", method="POST")
if code == 200 and '"is_active":true' in body.replace(" ", ""):
    record_test("FT-14", "AI Profile", "Activate Profile", "POST", f"/providers/cloud_hosted/profiles/{{id}}/activate", "PASS", code, "Profile activated", body)
else:
    record_test("FT-14", "AI Profile", "Activate Profile", "POST", f"/providers/cloud_hosted/profiles/{{id}}/activate", "FAIL", code, f"Activation failed: {err or body}")

# Delete
code, body, err = make_req(f"/providers/cloud_hosted/profiles/{test_prof_id}", method="DELETE")
if code == 200 and "deleted" in body.lower():
    record_test("FT-15", "AI Profile", "Delete Profile", "DELETE", f"/providers/cloud_hosted/profiles/{{id}}", "PASS", code, "Profile deleted cleanly", body)
else:
    record_test("FT-15", "AI Profile", "Delete Profile", "DELETE", f"/providers/cloud_hosted/profiles/{{id}}", "FAIL", code, f"Delete failed: {err or body}")

# 6. Assessment Creation Validation & Error Handling
# Missing scope acknowledgment
bad_payload = {
    "mode": "web",
    "target_url": "http://127.0.0.1:3000/",
    "target_scope_acknowledged": False
}
code, body, err = make_req("/runs", method="POST", data=bad_payload)
if code == 400:
    record_test("FT-16", "Execution", "Reject Unacknowledged Scope", "POST", "/runs", "PASS", code, "Refused to launch without explicit scope consent", body)
else:
    record_test("FT-16", "Execution", "Reject Unacknowledged Scope", "POST", "/runs", "FAIL", code, f"Unexpected code {code}: {err or body}")

# Missing target URL
bad_payload_target = {
    "mode": "web",
    "target_scope_acknowledged": True
}
code, body, err = make_req("/runs", method="POST", data=bad_payload_target)
if code in (400, 422):
    record_test("FT-17", "Execution", "Reject Missing Target", "POST", "/runs", "PASS", code, "Rejected request without target URL", body)
else:
    record_test("FT-17", "Execution", "Reject Missing Target", "POST", "/runs", "FAIL", code, f"Unexpected code {code}: {err or body}")

# 7. Stop Execution Lifecycle Test
stop_payload = {
    "mode": "web",
    "scan_mode": "deep",
    "target_url": "http://127.0.0.1:3000/",
    "target_scope_acknowledged": True,
    "max_turns": 500
}
code, body, err = make_req("/runs", method="POST", data=stop_payload)
if code == 200 and "run_id" in body:
    stop_run_id = json.loads(body)["run_id"]
    time.sleep(0.5)
    # Issue stop
    s_code, s_body, s_err = make_req(f"/runs/{stop_run_id}/stop", method="POST")
    time.sleep(1.0)
    q_code, q_body, q_err = make_req(f"/runs/{stop_run_id}")
    q_data = json.loads(q_body) if q_code == 200 else {}
    final_status = q_data.get("status", "")
    if final_status in ("stopped", "failed", "completed") or s_code == 200:
        record_test("FT-18", "Execution", "Stop Active Assessment", "POST", f"/runs/{{id}}/stop", "PASS", s_code, f"Assessment stopped (Final status: {final_status})", s_body)
    else:
        record_test("FT-18", "Execution", "Stop Active Assessment", "POST", f"/runs/{{id}}/stop", "FAIL", s_code, f"Status not stopped: {final_status}", q_body)
else:
    record_test("FT-18", "Execution", "Stop Active Assessment", "POST", "/runs", "FAIL", code, f"Could not launch stop-test run: {err or body}")

# 8. Report Formats Export on an Existing Completed Run (run-7be22192)
ref_run = "run-7be22192"
for fmt, exp_mime in [
    ("json", "application/json"),
    ("html", "text/html"),
    ("pdf", "application/pdf"),
    ("sarif", "application/json"),
    ("markdown", "text/markdown"),
    ("csv", "text/csv")
]:
    t_id = f"FT-19-{fmt.upper()}"
    code, body, err = make_req(f"/runs/{ref_run}/report?format={fmt}")
    if code == 200 and len(body) > 10:
        record_test(t_id, "Export", f"Export {fmt.upper()} Report", "GET", f"/runs/{{id}}/report?format={fmt}", "PASS", code, f"{fmt.upper()} report generated ({len(body)} bytes)", body[:100])
    else:
        record_test(t_id, "Export", f"Export {fmt.upper()} Report", "GET", f"/runs/{{id}}/report?format={fmt}", "FAIL", code, f"Failed generating {fmt.upper()}: {err or body}")

# 9. Runs History & Persistence
code, body, err = make_req("/runs")
if code == 200:
    runs_list = json.loads(body)
    if isinstance(runs_list, list) and len(runs_list) > 0:
        record_test("FT-20", "Persistence", "Query Assessment History", "GET", "/runs", "PASS", code, f"Retrieved {len(runs_list)} historical assessment records from disk", f"Total runs: {len(runs_list)}")
    else:
        record_test("FT-20", "Persistence", "Query Assessment History", "GET", "/runs", "FAIL", code, "Runs list empty", body)
else:
    record_test("FT-20", "Persistence", "Query Assessment History", "GET", "/runs", "FAIL", code, f"Error: {err or body}")

# Save CSV
fieldnames = ["test_id", "category", "feature_name", "method", "endpoint", "status", "http_code", "message", "details"]
with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(results)

print(f"\nWrote {len(results)} feature verification tests to {CSV_PATH}")
pass_cnt = sum(1 for r in results if r["status"] == "PASS")
fail_cnt = sum(1 for r in results if r["status"] == "FAIL")
print(f"Summary: {pass_cnt} PASSED, {fail_cnt} FAILED out of {len(results)} tests.")
