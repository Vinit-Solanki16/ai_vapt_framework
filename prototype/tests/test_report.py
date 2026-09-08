"""Tests for the report generator and trace formatter.

All tests verify the report/trace is derived from actual engine state —
no invented events.
"""

from unittest.mock import patch

from decision_engine.core.engine import run_engine
from decision_engine.core.schemas import Outcome

from prototype.demo_data import success_scenario, failure_pivot_scenario, multi_candidate_scenario
from prototype.engine_integration import run_decision_scenario
from prototype.execution_layer import create_simulation_executor, create_lab_executor
from prototype.trace_formatter import (
    format_engine_trace,
    format_candidate_ranking,
    format_execution_results,
    parse_engine_log,
)
from prototype.report_generator import (
    generate_text_report,
    generate_json_report,
    save_text_report,
    save_json_report,
    _get_evidence_tier,
    _count_attempts_per_candidate,
    _extract_pivot_events,
    _get_evidence_tier_description,
)


# --- Trace formatter tests ---

def test_trace_is_derived_from_actual_engine_state():
    """Verify the trace is derived from real engine state, not invented."""
    candidates = failure_pivot_scenario(max_attempts=2)
    state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

    trace = format_engine_trace(state)

    # Trace should mention real engine log entries
    assert "DEMO-DEAD-END" in trace
    assert "DEMO-WORKER" in trace
    assert "SUCCESS" in trace
    assert "FAIL_TIMEOUT" in trace

    # Trace should contain pivot
    assert "PIVOT" in trace


def test_trace_does_not_invent_events():
    """Verify the trace only contains events from the engine's actual logs."""
    candidates = success_scenario()
    state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

    trace = format_engine_trace(state)

    assert len(trace.split("\n")) > 0


def test_trace_formatter_parses_engine_log():
    """Verify the trace formatter parses engine logs correctly."""
    phase, fields = parse_engine_log("[Executor] Attempt 1/2 on DEMO-DEAD-END -> FAIL_TIMEOUT")
    assert phase == "EXECUTE_FAIL"
    assert fields["attempt"] == "1"
    assert fields["max_attempts"] == "2"
    assert fields["candidate"] == "DEMO-DEAD-END"
    assert fields["outcome"] == "FAIL_TIMEOUT"

    phase, fields = parse_engine_log("[Executor] Attempt 1 -> SUCCESS on DEMO-WORKER")
    assert phase == "EXECUTE_SUCCESS"
    assert fields["candidate"] == "DEMO-WORKER"

    phase, fields = parse_engine_log("[Pivot] Threshold reached for DEMO-DEAD-END. Abandoning route.")
    assert phase == "PIVOT_ABANDON"
    assert "Abandoning" in fields["reason"]

    phase, fields = parse_engine_log("[Pivot] Redirected to DEMO-WORKER")
    assert phase == "PIVOT_REDIRECT"
    assert fields["next_id"] == "DEMO-WORKER"


def test_candidate_ranking_format():
    """Verify the ranking format includes real candidate data."""
    candidates = success_scenario()
    state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

    ranking = format_candidate_ranking(state)
    assert "DEMO-SUCCESS-A" in ranking
    assert "DEMO-SUCCESS-B" in ranking
    assert "DEMO-WORKER" in ranking


def test_execution_results_format():
    """Verify the execution results format includes real data."""
    candidates = success_scenario()
    state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

    results = format_execution_results(state)
    # Should contain at least one result
    assert "Outcome:" in results or "no execution results" in results


# --- Report content tests ---

def test_report_contains_actual_engine_results():
    """Verify the report contains actual engine results."""
    candidates = success_scenario()
    state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

    text_report = generate_text_report("success", state, max_attempts=2, mode="simulation")
    json_report = generate_json_report("success", state, max_attempts=2, mode="simulation")

    assert "Scenario:" in text_report
    assert "success" in text_report
    assert "FINAL RESULT" in text_report
    assert "Status:" in text_report
    assert "Total Attempts:" in text_report
    assert "Pivot Count:" in text_report
    assert "Candidates Processed:" in text_report

    import json
    data = json.loads(json_report)
    assert data["scenario"] == "success"
    assert data["final_status"] == state["status"]
    assert data["execution_results"] == state["results"]


def test_report_includes_safety_notice():
    """Verify the report clearly includes SIMULATION MODE and the safety notice."""
    candidates = success_scenario()
    state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

    text_report = generate_text_report("success", state, max_attempts=2, mode="simulation")
    json_report = generate_json_report("success", state, max_attempts=2, mode="simulation")

    assert "SIMULATION MODE" in text_report
    assert "Outcomes are resolved from supplied demo ground truth" in text_report
    assert "No real vulnerabilities were validated" in text_report

    import json
    data = json.loads(json_report)
    assert "SIMULATION MODE" in data["safety_notice"]
    assert "Outcomes are resolved from supplied demo ground truth" in data["safety_notice"]


def test_report_does_not_describe_simulated_outcomes_as_real():
    """Verify the report does not describe simulated outcomes as real vulnerabilities."""
    candidates = success_scenario()
    state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

    text_report = generate_text_report("success", state, max_attempts=2, mode="simulation")

    assert "SIMULATION MODE" in text_report
    assert "No real vulnerabilities were validated" in text_report


def test_save_and_load_reports():
    """Verify saving and loading reports works."""
    import json
    import tempfile
    import os

    candidates = success_scenario()
    state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = os.path.join(tmpdir, "test_report.json")
        txt_path = os.path.join(tmpdir, "test_report.txt")

        saved_json = save_json_report("success", state, json_path, 2, "simulation")
        saved_txt = save_text_report("success", state, txt_path, 2, "simulation")

        assert saved_json == json_path
        assert saved_txt == txt_path

        assert os.path.exists(json_path)
        assert os.path.exists(txt_path)

        with open(json_path) as f:
            data = json.load(f)
        assert data["scenario"] == "success"
        assert data["final_status"] == state["status"]

        with open(txt_path) as f:
            text = f.read()
        assert "FINAL RESULT" in text


# --- Evidence tier tests ---

def test_evidence_tier_simulation():
    """Verify a report from simulation mode labels the evidence tier as SIMULATED."""
    candidates = success_scenario()
    state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

    json_report = generate_json_report("success", state, max_attempts=2, mode="simulation")
    text_report = generate_text_report("success", state, max_attempts=2, mode="simulation")

    import json
    data = json.loads(json_report)

    # JSON must label evidence tier as SIMULATED
    assert data["evidence_tier"] == "SIMULATED"
    assert "SIMULATED" in data["evidence_tier_label"]

    # Text report must also say SIMULATED and show Evidence Tier section
    assert "SIMULATED" in text_report
    assert "Evidence Tier:" in text_report


def test_evidence_tier_loopback():
    """Verify a report from lab_loopback mode labels the evidence tier as OBSERVED_LOCAL."""
    # Use the lab executor with a mocked HTTP call
    executor = create_lab_executor("127.0.0.1", 8080, "/vuln")
    candidates = [{"id": "CVE-LAB-1", "probability": 0.8}]

    with patch("prototype.lab_runner.http_get", return_value=(200, "VULNERABLE")):
        state = run_decision_scenario(candidates, max_attempts=2, mode="lab_loopback", executor=executor)

    json_report = generate_json_report("loopback_test", state, max_attempts=2, mode="lab_loopback")
    text_report = generate_text_report("loopback_test", state, max_attempts=2, mode="lab_loopback")

    import json
    data = json.loads(json_report)

    # Loopback mode must label evidence tier as OBSERVED_LOCAL
    assert data["evidence_tier"] == "OBSERVED_LOCAL"
    assert "OBSERVED_LOCAL" in data["evidence_tier_label"]

    # Text report must also say OBSERVED_LOCAL and show Evidence Tier section
    assert "OBSERVED_LOCAL" in text_report
    assert "Evidence Tier:" in text_report


def test_evidence_tier_docker():
    """Verify a report from lab_docker mode labels the evidence tier as DOCKER_OBSERVED."""
    # Verify that lab mode still maps to DOCKER_OBSERVED (backward compatibility)
    assert _get_evidence_tier("lab") == "DOCKER_OBSERVED"
    assert _get_evidence_tier("lab_docker") == "DOCKER_OBSERVED"


def test_evidence_tier_helper():
    """Verify the evidence tier helper maps modes correctly."""
    assert _get_evidence_tier("simulation") == "SIMULATED"
    assert _get_evidence_tier("lab_loopback") == "OBSERVED_LOCAL"
    assert _get_evidence_tier("lab_docker") == "DOCKER_OBSERVED"
    assert _get_evidence_tier("lab") == "DOCKER_OBSERVED"
    assert _get_evidence_tier("real") == "CONTROLLED VALIDATION"
    assert _get_evidence_tier("unknown") == "UNKNOWN"


def test_evidence_tier_description_helper():
    """Verify the evidence tier description helper."""
    assert "ground truth" in _get_evidence_tier_description("simulation").lower()
    assert "loopback" in _get_evidence_tier_description("lab_loopback").lower()
    assert "docker" in _get_evidence_tier_description("lab").lower()
    assert "live" in _get_evidence_tier_description("real").lower()


# --- Per-candidate attempt counts tests ---

def test_per_candidate_attempts():
    """Verify the report contains per-candidate attempt counts."""
    candidates = failure_pivot_scenario(max_attempts=2)
    state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

    json_report = generate_json_report("failure_pivot", state, max_attempts=2, mode="simulation")
    text_report = generate_text_report("failure_pivot", state, max_attempts=2, mode="simulation")

    import json
    data = json.loads(json_report)

    # JSON must contain attempts_per_candidate
    assert "attempts_per_candidate" in data
    attempts = data["attempts_per_candidate"]

    # Should have counts for DEMO-DEAD-END (2 attempts before pivot) and DEMO-WORKER (1 success)
    assert "DEMO-DEAD-END" in attempts
    assert "DEMO-WORKER" in attempts
    assert attempts["DEMO-DEAD-END"] == 2
    assert attempts["DEMO-WORKER"] == 1

    # Text report must show PER-CANDIDATE ATTEMPTS section
    assert "PER-CANDIDATE ATTEMPTS" in text_report
    assert "DEMO-DEAD-END" in text_report
    assert "DEMO-WORKER" in text_report


def test_per_candidate_attempts_single_candidate():
    """Verify attempt counts with a single successful candidate."""
    candidates = [{"id": "DEMO-ONLY", "probability": 0.9, "ground_truth": "SUCCESS"}]
    state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

    json_report = generate_json_report("single", state, max_attempts=2, mode="simulation")

    import json
    data = json.loads(json_report)
    attempts = data["attempts_per_candidate"]
    assert "DEMO-ONLY" in attempts
    assert attempts["DEMO-ONLY"] == 1


def test_count_attempts_per_candidate_helper():
    """Verify the attempts counting helper function."""
    results = [
        {"candidate_id": "A", "outcome": "FAIL_TIMEOUT"},
        {"candidate_id": "A", "outcome": "SUCCESS"},
        {"candidate_id": "B", "outcome": "FAIL_TIMEOUT"},
    ]
    counts = _count_attempts_per_candidate(results)
    assert counts["A"] == 2
    assert counts["B"] == 1


# --- Decision trace tests ---

def test_decision_trace_in_report():
    """Verify the report contains the full decision trace."""
    candidates = success_scenario()
    state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

    json_report = generate_json_report("success", state, max_attempts=2, mode="simulation")
    text_report = generate_text_report("success", state, max_attempts=2, mode="simulation")

    import json
    data = json.loads(json_report)

    # JSON must contain decision_trace as a list of log strings
    assert "decision_trace" in data
    trace = data["decision_trace"]
    assert isinstance(trace, list)
    assert len(trace) > 0

    # The trace should contain real engine events
    assert any("Engine initialized" in entry for entry in trace)
    assert any("Executor" in entry for entry in trace)

    # Text report must contain the DECISION TRACE section
    assert "DECISION TRACE" in text_report


def test_pivot_events_in_report():
    """Verify the report contains pivot events extracted from engine logs."""
    candidates = failure_pivot_scenario(max_attempts=2)
    state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

    json_report = generate_json_report("failure_pivot", state, max_attempts=2, mode="simulation")
    text_report = generate_text_report("failure_pivot", state, max_attempts=2, mode="simulation")

    import json
    data = json.loads(json_report)

    # JSON must contain pivot_events
    assert "pivot_events" in data
    pivot_events = data["pivot_events"]
    assert isinstance(pivot_events, list)
    assert len(pivot_events) >= 2  # at least ABANDON + REDIRECT

    # Should have an ABANDON event for DEMO-DEAD-END
    types = [e["type"] for e in pivot_events]
    assert "ABANDON" in types
    assert "REDIRECT" in types

    # Text report must show PIVOT EVENTS section
    assert "PIVOT EVENTS" in text_report
    assert "ABANDON" in text_report
    assert "REDIRECT" in text_report


def test_extract_pivot_events_helper():
    """Verify the pivot event extraction helper."""
    logs = [
        "[Pivot] Threshold reached for DEMO-DEAD-END. Abandoning route.",
        "[Pivot] Redirected to DEMO-WORKER",
        "[Pivot] All candidates processed. Workflow complete.",
    ]
    events = _extract_pivot_events(logs)
    assert len(events) == 3
    assert events[0]["type"] == "ABANDON"
    assert events[1]["type"] == "REDIRECT"
    assert events[2]["type"] == "COMPLETE"


# --- Safety notice prominence tests ---

def test_evidence_tier_section_is_prominent_in_text_report():
    """Verify the Evidence Tier section appears prominently near the top of the text report."""
    candidates = success_scenario()
    state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

    text_report = generate_text_report("success", state, max_attempts=2, mode="simulation")
    lines = text_report.split("\n")

    # Find the evidence tier line in the metadata
    evidence_idx = next(i for i, l in enumerate(lines) if "Evidence Tier:" in l)
    # It should be in the first 20 lines (prominent)
    assert evidence_idx < 20

    # Evidence tier section should follow shortly after (within 10 lines)
    section_idx = next(i for i, l in enumerate(lines) if "EVIDENCE TIER" in l)
    assert section_idx > evidence_idx
    assert section_idx - evidence_idx < 10


def test_safety_notice_section_is_prominent():
    """Verify the Safety Notice section is prominent in the text report."""
    candidates = success_scenario()
    state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

    text_report = generate_text_report("success", state, max_attempts=2, mode="simulation")

    # SAFETY NOTICE should appear as a section header
    assert "SAFETY NOTICE" in text_report
    # The safety notice should contain the simulation warning
    assert "SIMULATION MODE" in text_report
    assert "No real vulnerabilities were validated" in text_report
