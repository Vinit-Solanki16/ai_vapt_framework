#!/usr/bin/env python3
"""T-DOCKER Stage B experiment harness: Scenario S1 (observed SUCCESS) and
S2 (observed FAILURE -> pivot) against the lab vulnerability emulator.

Protocol: docs/project_management/T_DOCKER_EXPERIMENT_PROTOCOL.md (Parts D-H).

INFRASTRUCTURE NOTE (honest deviation, recorded in metadata.json):
Docker is unavailable in this environment (WSL2 distro without Docker
integration; readiness gate Part J lists Docker as BLOCKED). This harness
therefore runs the SAME emulator application (lab/emulator/app.py) as a local
process bound STRICTLY to 127.0.0.1:8080 (loopback-only, never 0.0.0.0), and
points run_agent at 127.0.0.1 with target_allowlist=["127.0.0.1"]. Outcomes
are REAL OBSERVED results (module <-> emulator over TCP, corroborated by the
emulator's own access log) - NOT labels.json values. Container-level
isolation (Part G) is NOT in effect here; loopback binding plus the fail-
closed allowlist guard are the only boundaries.

core/ is FROZEN for this task (PROMPT 3 not merged): agent_graph builds its
own `Executor(mode=...)`, so the harness injects the authorised executor by
patching core.agent_graph.Executor with a factory that constructs
Executor(mode="real", danger_mode=True, target_allowlist=[<emu-ip>]).
All agent_graph logic (ranking, attempt counters, pivot, termination) runs
UNMODIFIED. Lab modules resolve via core.executor.CORPUS_DIR patched to
data/poc_corpus_lab (harness scope only).

Assessor boundary stubbed deterministically (offline, no Ollama):
A -> HIGH, B -> LOW, C -> MEDIUM. B's LOW rank shows pre-execution assessment
suppressing a dead-end BEFORE the dangerous path (existing LOW-skip gate);
C's MEDIUM rank lets it execute so its observed failure exercises the pivot
threshold (RQ2).

Usage: python tests/run_tdocker_scenarios.py [--run-id RUN_ID]
"""
from __future__ import annotations

import argparse
import csv
import json
import socket
import subprocess
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core.agent_graph as agent_graph  # noqa: E402
import core.executor as core_executor  # noqa: E402
from core.executor import Executor as RealExecutor  # noqa: E402
from core.schemas import ExploitAssessment  # noqa: E402

TARGET_IP = "127.0.0.1"
# NOTE: host port 8080 is occupied by an UNRELATED foreign service on this
# machine (verified via ss). The emulator must never share a port with it -
# a plain TCP connect cannot distinguish listeners. We use 18080 and verify
# identity by requesting /health and checking the JSON body.
EMU_PORT = 18080
LAB_CORPUS = ROOT / "data" / "poc_corpus_lab"
EMU_APP = ROOT / "lab" / "emulator"

MAX_ATTEMPTS = 2

# --- deterministic assessor boundary (offline; documented deviation) --------
def _assessment(rank: str, reasoning: str) -> ExploitAssessment:
    return ExploitAssessment(
        exploit_found=rank != "LOW",
        syntax_valid=True,
        os_dependencies="none",
        privileges_required="none",
        network_noise="low",
        complexity_score={"HIGH": 2, "MEDIUM": 5, "LOW": 9}[rank],
        prerequisites_met=rank != "LOW",
        usability_rank=rank,
        reasoning=f"deterministic stub (offline): {reasoning}",
    )


STUB_ASSESSMENTS = {
    "A": ("HIGH", "lab candidate A targets emulator /vuln (observable success signal)"),
    "B": ("LOW", "lab candidate B targets emulator /fail dead-end; suppressed pre-execution"),
    "C": ("MEDIUM", "lab candidate C targets emulator /fail; executes so pivot-on-failure is exercised"),
}


def _stub_assessor(cve, *args, **kwargs):
    rank, why = STUB_ASSESSMENTS[cve]
    return _assessment(rank, why)


FINDINGS_S1 = [
    {"cve": "A", "port": EMU_PORT, "service": "http",
     "description": "Lab candidate A -> GET /vuln", "epss_score": 0.90},
    {"cve": "B", "port": EMU_PORT, "service": "http",
     "description": "Lab candidate B -> GET /fail (dead-end)", "epss_score": 0.40},
]
FINDINGS_S2 = [
    {"cve": "C", "port": EMU_PORT, "service": "http",
     "description": "Lab candidate C -> GET /fail (non-exploitable)", "epss_score": 0.70},
]


# ---------------------------------------------------------------------------
# Emulator lifecycle (loopback-only)
# ---------------------------------------------------------------------------
def _emu_healthy() -> bool:
    """True only if OUR emulator answers: GET /health -> 200 + healthy JSON.
    Guards against foreign services occupying the port (a bare TCP connect
    cannot tell listeners apart - this actually happened on host 8080)."""
    try:
        with socket.create_connection((TARGET_IP, EMU_PORT), timeout=0.5) as s:
            s.sendall(b"GET /health HTTP/1.1\r\nHost: localhost\r\n"
                      b"Connection: close\r\n\r\n")
            buf = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
        return b" 200 " in buf.split(b"\r\n", 1)[0] and b"healthy" in buf.lower()
    except OSError:
        return False


def start_emulator(log_path: Path):
    log_fh = open(log_path, "w", encoding="utf-8")
    bootstrap = (
        "import sys; sys.path.insert(0, r'%s'); "
        "from app import app; app.run(host='127.0.0.1', port=%d)"
        % (EMU_APP, EMU_PORT)
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", bootstrap],
        cwd=str(ROOT), stdout=log_fh, stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 15
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"emulator died during startup (port {EMU_PORT} taken by a "
                f"foreign service?) - see {log_path}")
        if _emu_healthy():
            return proc, log_fh
        time.sleep(0.2)
    proc.terminate()
    raise RuntimeError("emulator did not become healthy in time")


def stop_emulator(proc, log_fh):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    log_fh.close()


# ---------------------------------------------------------------------------
# Executor injection (core/ frozen -> patch at the agent_graph boundary)
# ---------------------------------------------------------------------------
def make_allowlisted_executor_factory():
    def factory(mode="simulation", **_kw):
        # Requirement 1: real mode + opt-in danger_mode + fail-closed allowlist.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # construction warning is expected
            return RealExecutor(
                mode=mode, danger_mode=True,
                target_allowlist=[TARGET_IP],
            )
    return factory


class ModuleIORecorder:
    """Tee executor's PoC subprocess stdout/stderr/cmd into evidence records."""

    def __init__(self):
        self.records = []

    def patch(self):
        recorder = self
        real_run = subprocess.run

        def recording_run(cmd, **kwargs):
            proc = real_run(cmd, **kwargs)
            recorder.records.append({
                "cmd": list(cmd),
                "returncode": proc.returncode,
                "stdout": proc.stdout.decode(errors="replace"),
                "stderr": proc.stderr.decode(errors="replace"),
            })
            return proc

        return patch.object(subprocess, "run", recording_run)


# ---------------------------------------------------------------------------
# Scenario execution
# ---------------------------------------------------------------------------
def run_scenario(name, findings, run_dir):
    print(f"\n=== {name} ===")
    emu_log = run_dir / f"emulator_access_{name.lower()}.log"
    proc, log_fh = start_emulator(emu_log)
    recorder = ModuleIORecorder()
    t0 = time.monotonic()
    try:
        with patch.object(core_executor, "CORPUS_DIR", str(LAB_CORPUS)), \
                patch.object(agent_graph, "assess_exploit_quality", _stub_assessor), \
                patch.object(agent_graph, "Executor",
                             make_allowlisted_executor_factory()), \
                recorder.patch():
            final = agent_graph.run_agent(
                TARGET_IP, findings, provider="deterministic-stub",
                max_attempts=MAX_ATTEMPTS, mode="real",
            )
    finally:
        stop_emulator(proc, log_fh)
    runtime = time.monotonic() - t0
    return final, recorder.records, runtime


def classify_s1(final, records, emu_log_text):
    """Part E: OBSERVED_SUCCESS requires module token AND emulator log line."""
    a_results = [r for r in final["results"] if r["cve"] == "A"]
    token_seen = bool(records) and "VULNERABLE" in records[0]["stdout"]
    emu_seen = "path=/vuln" in emu_log_text
    if a_results and a_results[0]["outcome"] == "SUCCESS" \
            and token_seen and emu_seen:
        return "OBSERVED_SUCCESS"
    if token_seen or emu_seen:
        return "INCONCLUSIVE"
    return "OBSERVED_FAILURE"


def classify_s2(final, records, emu_log_text):
    c_results = [r for r in final["results"] if r["cve"] == "C"]
    attempts_happened = len(c_results) == MAX_ATTEMPTS and len(records) == MAX_ATTEMPTS
    no_success_condition = all(r["outcome"] != "SUCCESS" for r in c_results)
    if attempts_happened and no_success_condition:
        return "OBSERVED_FAILURE"
    return "INCONCLUSIVE"


def assert_s1(final, records, emu_log_text):
    assert final["status"] == "COMPLETED", final["status"]
    results = final["results"]
    assert results[0]["cve"] == "A" and results[0]["outcome"] == "SUCCESS", results[0]
    # Part E corroboration: module stdout token + emulator-side access log.
    assert records and "VULNERABLE" in records[0]["stdout"], records[:1]
    assert "path=/vuln" in emu_log_text
    # No loop: every CVE attempted at most max_attempts times; terminated.
    per_cve = {}
    for r in results:
        per_cve[r["cve"]] = per_cve.get(r["cve"], 0) + 1
    assert all(n <= MAX_ATTEMPTS for n in per_cve.values()), per_cve


def assert_s2(final, records, emu_log_text):
    assert final["status"] == "COMPLETED", final["status"]
    c_results = [r for r in final["results"] if r["cve"] == "C"]
    # Exactly 2 executions of C, both observed failures, NO 3rd attempt.
    assert len(c_results) == MAX_ATTEMPTS, len(c_results)
    assert all(r["outcome"] == "FAIL_TIMEOUT" for r in c_results), c_results
    c_records = [x for x in records if x["cmd"][1].endswith("/C.py")]
    assert len(c_records) == MAX_ATTEMPTS, len(c_records)
    fail_hits = [ln for ln in emu_log_text.splitlines() if "path=/fail" in ln]
    assert len(fail_hits) == MAX_ATTEMPTS, fail_hits
    # Explicit pivot log entry present.
    logs = "\n".join(final["logs"])
    assert "[Pivot] Threshold reached for C" in logs
    assert "[Pivot] All targets processed. Workflow complete." in logs
    assert final["attempt_count"] == MAX_ATTEMPTS, final["attempt_count"]


# ---------------------------------------------------------------------------
# Evidence writing (protocol Part H)
# ---------------------------------------------------------------------------
def write_evidence(run_dir, name, final, records, runtime, evidence_class):
    low = name.lower()
    payload = {
        "scenario": name,
        "strategy": "SMART",
        "run_id": run_dir.name,
        "evidence_class": evidence_class,
        "observed_vs_simulation": (
            "OBSERVED: outcome parsed by core.executor._parse_module_output from "
            "the lab module's real stdout/stderr (danger_mode ignores "
            "labels.json) and independently corroborated by the emulator's own "
            "access log. NOT a labels.json/simulation value."
            if not evidence_class.startswith("OBSERVED") else
            "OBSERVED (see evidence_class); labels.json never consulted in danger_mode."
        ),
        "target": TARGET_IP,
        "allowlist": [TARGET_IP],
        "max_attempts": MAX_ATTEMPTS,
        "runtime_seconds": round(runtime, 3),
        "terminated_status": final["status"],
        "module_io": records,
        "final_state": agent_graph._state_to_jsonable(final),
    }
    (run_dir / f"{run_dir.name}_{low}_smart.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")
    (run_dir / f"framework_logs_{low}.txt").write_text(
        "\n".join(final["logs"]) + "\n", encoding="utf-8")
    lines = []
    for i, rec in enumerate(records, 1):
        lines.append(f"[{name} invocation {i}] cmd={rec['cmd']}")
        lines.append(f"rc={rec['returncode']}")
        lines.append(f"stdout:\n{rec['stdout']}")
        lines.append(f"stderr:\n{rec['stderr']}")
        lines.append("-" * 60)
    (run_dir / f"module_stdout_stderr_{low}.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    rows = []
    attempt_of = {}
    for r in final["results"]:
        attempt_of[r["cve"]] = attempt_of.get(r["cve"], 0) + 1
        rows.append([name, "SMART", r["cve"], attempt_of[r["cve"]],
                     r["outcome"], r["request_count"], r["detail"]])
    return rows


def write_benchmark_csv(run_dir, all_rows):
    path = run_dir / f"{run_dir.name}_benchmark.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "strategy", "candidate", "attempt",
                    "observed_outcome", "request_count", "detail"])
        w.writerows(all_rows)
    return path


def write_metadata_and_infra(run_dir, scenario_summaries):
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=str(ROOT),
                                  capture_output=True, text=True).stdout.strip()
        except Exception as e:
            return f"unavailable: {e}"

    infra = subprocess.run(["docker", "version"], capture_output=True, text=True)
    infra_txt = (
        "$ docker version\n"
        + (infra.stdout + infra.stderr).strip()
        + "\n\nCONSEQUENCE: containerized isolation unavailable; emulator run as "
          "loopback-only local process (see harness docstring). docker-compose.yml "
          "copied for reference; image digests N/A (no daemon).\n"
    )
    (run_dir / "infra_docker_unavailable.txt").write_text(infra_txt, encoding="utf-8")
    compose = ROOT / "lab" / "docker-compose.yml"
    if compose.exists():
        (run_dir / "docker-compose.reference.yml").write_text(
            compose.read_text(encoding="utf-8"), encoding="utf-8")

    metadata = {
        "run_id": run_dir.name,
        "task": "T-DOCKER Stage B: S1/S2 controlled validation runs",
        "protocol": "docs/project_management/T_DOCKER_EXPERIMENT_PROTOCOL.md",
        "git_head": git("rev-parse", "HEAD"),
        "git_dirty_files": git("status", "--porcelain"),
        "started_utc": scenario_summaries[0]["started_utc"],
        "python": sys.version.split()[0],
        "infrastructure": {
            "mode": "loopback process (DEVIATION)",
            "reason": "Docker daemon/CLI unavailable in this WSL2 environment "
                      "(evidence: infra_docker_unavailable.txt); readiness gate "
                      "Part J already lists Docker as BLOCKED.",
            "emulator_app": "lab/emulator/app.py (identical code to container image)",
            "bind": f"127.0.0.1:{EMU_PORT} (strict loopback; host-only reachability)",
            "container_isolation_in_effect": False,
            "network_isolation_equivalent": "loopback bind only; NO bridge/internal network",
        },
        "safety": {
            "target_allowlist": [TARGET_IP],
            "allowlist_enforcement": "core.executor.Executor target_allowlist "
                                     "(Stage B, fail-closed default empty)",
            "non_lab_targets_touched": False,
            "payload": "benign behavioral GET probes only (/vuln, /fail)",
        },
        "observed_vs_simulation": {
            "statement": "ALL reported outcomes are OBSERVED (real module "
                         "execution parsed from real stdout/stderr, corroborated "
                         "by emulator access logs). SIMULATION/labels.json was "
                         "NOT used anywhere in these runs.",
            "labels_consulted": False,
        },
        "assessor_boundary": {
            "type": "deterministic stub (offline; no Ollama/OpenAI reachable)",
            "ranks": {"A": "HIGH", "B": "LOW", "C": "MEDIUM"},
            "rationale": "B LOW exercises pre-execution dead-end suppression "
                         "(RQ1 mechanism); C MEDIUM allows execution so its "
                         "observed failure drives the RQ2 pivot.",
        },
        "core_changes_this_task": [],
        "scenarios": [{k: v for k, v in s.items() if k != "started_utc"}
                      for s in scenario_summaries],
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2),
                                           encoding="utf-8")


def write_regression_gate(run_dir):
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    out = f"$ pytest tests/ -q\nexit={res.returncode}\n\n{res.stdout}{res.stderr}"
    (run_dir / "regression_gate_pytest.txt").write_text(out, encoding="utf-8")
    return res.returncode, res.stdout.strip().splitlines()[-1] if res.stdout else ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = args.run_id or f"{stamp}_tdocker_stageB_loopback"
    run_dir = ROOT / "data" / "experiment_runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    all_rows = []
    for name, findings, classifier, asserter in [
        ("S1", FINDINGS_S1, classify_s1, assert_s1),
        ("S2", FINDINGS_S2, classify_s2, assert_s2),
    ]:
        started = datetime.now(timezone.utc).isoformat()
        final, records, runtime = run_scenario(name, findings, run_dir)
        emu_text = (run_dir / f"emulator_access_{name.lower()}.log").read_text(
            encoding="utf-8")
        asserter(final, records, emu_text)          # hard gate on protocol criteria
        ev = classifier(final, records, emu_text)
        rows = write_evidence(run_dir, name, final, records, runtime, ev)
        all_rows.extend(rows)
        summaries.append({
            "scenario": name, "evidence_class": ev,
            "executions": len(final["results"]),
            "poc_subprocess_invocations": len(records),
            "status": final["status"],
            "runtime_seconds": round(runtime, 3),
            "assertions_passed": True,
            "started_utc": started,
        })
        print(f"[{name}] {ev}: status={final['status']} "
              f"executions={len(final['results'])} poc_runs={len(records)}")

    csv_path = write_benchmark_csv(run_dir, all_rows)
    write_metadata_and_infra(run_dir, summaries)
    rc, last = write_regression_gate(run_dir)
    print(f"\nbenchmark CSV: {csv_path.relative_to(ROOT)}")
    print(f"regression gate: {'PASS' if rc == 0 else 'FAIL'} ({last})")
    artifacts = sorted(p.name for p in run_dir.iterdir())
    print(f"artifacts ({len(artifacts)}):")
    for a in artifacts:
        print(f"  - data/experiment_runs/{run_id}/{a}")
    if rc != 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
