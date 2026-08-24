"""T-CHECKPOINT: AgentState persistence (save / load / resume).

Scope (per task brief):
  (1) serialize the LangGraph AgentState to JSON on completion/interrupt
      -- exercised through save_checkpoint() at a MID-RUN interrupt point
      and at COMPLETED status;
  (2) resume_agent() loads a saved state and re-invokes the graph from
      current_index -- entry node derived from persisted status so no step is
      replayed (a validated CVE is never executed twice);
  (3) save -> load -> resume reproduces the SAME final results as an
      uninterrupted fresh run (results list equality + termination invariants).

All offline & deterministic: conftest.py blocks network and records subprocess;
the LLM boundary is stubbed exactly like test_ttests_gaps.py.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pydantic import BaseModel

import core.agent_graph as agent_graph
from core.agent_graph import (
    initial_agent_state,
    assess_node,
    execute_node,
    pivot_node,
    resume_agent,
    resume_entry_point,
    run_agent,
    save_checkpoint,
    load_checkpoint,
)
from core.schemas import ExploitAssessment, Finding, UsabilityRank


def _canned_assessment() -> ExploitAssessment:
    return ExploitAssessment(
        exploit_found=True,
        syntax_valid=True,
        os_dependencies="paramiko",
        privileges_required="user",
        network_noise="medium",
        complexity_score=4,
        prerequisites_met=True,
        usability_rank=UsabilityRank.HIGH,
        reasoning="mocked structured output",
    )


@pytest.fixture
def stubbed_assessor(monkeypatch):
    """Deterministic HIGH-rank assessor so ordering/outcomes are stable."""
    monkeypatch.setattr(
        "core.agent_graph.assess_exploit_quality",
        lambda *a, **k: _canned_assessment(),
    )


# CVE order = priority order (EPSS desc). Corpus labels give:
#   44228 -> SUCCESS, 38408 -> FAIL_TIMEOUT, 22965 -> FAIL_SYNTAX.
FINDINGS = [
    {"cve": "CVE-2021-44228", "port": 8080, "service": "http",
     "description": "valid target", "epss_score": 0.999},
    {"cve": "CVE-2023-38408", "port": 22, "service": "ssh",
     "description": "dead end (fail_timeout)", "epss_score": 0.797},
    {"cve": "CVE-2022-22965", "port": 9090, "service": "http",
     "description": "dead end (fail_syntax)", "epss_score": 0.31},
]
MAX_ATTEMPTS = 2


def _interrupt_mid_second_cve() -> dict:
    """Replay graph transitions by hand up to a realistic interruption:
    target #1 validated & advanced, target #2 assessed with ONE failed
    attempt recorded (attempt_count=1/2)."""
    st: dict = initial_agent_state("127.0.0.1", FINDINGS, max_attempts=MAX_ATTEMPTS)
    st = assess_node(st)   # assess #1
    st = execute_node(st)  # execute #1 -> SUCCESS
    assert st["status"] == "SUCCESS"
    st = pivot_node(st)    # advance to #2
    st = assess_node(st)   # assess #2
    st = execute_node(st)  # attempt 1/2 fails
    assert st["current_index"] == 1
    assert st["attempt_count"] == 1
    return st


# ---------------------------------------------------------------------------
# (1) serialization round-trip
# ---------------------------------------------------------------------------
def test_save_checkpoint_writes_json_and_load_restores_models(
    stubbed_assessor, tmp_path, offline_guard
):
    st = _interrupt_mid_second_cve()
    path = str(tmp_path / "ckpt.json")

    written = save_checkpoint(st, path)

    assert written == path
    with open(path) as fh:
        payload = json.load(fh)
    # Pure JSON on disk: no pydantic objects leaked into the file.
    assert payload["state"]["findings"][0]["usability_rank"] == "HIGH"
    assert payload["state"]["current_index"] == 1
    assert payload["state"]["status"] == "TESTING"

    loaded = load_checkpoint(path)
    assert isinstance(loaded["findings"][0], Finding)   # rebuilt models
    assert isinstance(loaded["findings"][0].usability_rank, UsabilityRank)
    for key in ("target", "current_index", "current_cve", "exploit_rank",
                "attempt_count", "max_attempts", "status", "provider",
                "mode"):
        assert loaded[key] == st[key]
    assert loaded["results"] == st["results"]
    assert offline_guard.call_count == 0


# ---------------------------------------------------------------------------
# (3) save -> load -> resume == fresh run
# ---------------------------------------------------------------------------
def test_resume_completes_interrupted_run_matching_fresh_results(
    stubbed_assessor, tmp_path, offline_guard
):
    fresh = run_agent("127.0.0.1", FINDINGS, max_attempts=MAX_ATTEMPTS)

    st = _interrupt_mid_second_cve()
    path = save_checkpoint(st, str(tmp_path / "interrupted.json"))
    resumed = resume_agent(path)

    assert resumed["status"] == "COMPLETED"
    assert resumed["current_index"] == len(FINDINGS)
    # Identical final results to the uninterrupted run (order included).
    assert resumed["results"] == fresh["results"]
    # Loop-safety preserved across resume: <= max_attempts per CVE.
    per_cve = {}
    for r in resumed["results"]:
        per_cve[r["cve"]] = per_cve.get(r["cve"], 0) + 1
    assert all(n <= MAX_ATTEMPTS for n in per_cve.values())
    assert "Resuming from" in "\n".join(resumed["logs"])
    assert offline_guard.call_count == 0


def test_resume_from_success_status_does_not_duplicate_validated_cve(
    stubbed_assessor, tmp_path, offline_guard
):
    """Interrupted right AFTER a successful execution: resume must advance
    (pivot), never re-execute the validated CVE."""
    st: dict = initial_agent_state("127.0.0.1", FINDINGS, max_attempts=MAX_ATTEMPTS)
    st = assess_node(st)
    st = execute_node(st)
    assert st["status"] == "SUCCESS"

    path = save_checkpoint(st, str(tmp_path / "after_success.json"))
    resumed = resume_agent(path)

    assert resumed["status"] == "COMPLETED"
    hits = [r for r in resumed["results"] if r["cve"] == "CVE-2021-44228"]
    assert len(hits) == 1                       # exactly once, not replayed
    assert resumed["results"] == run_agent(
        "127.0.0.1", FINDINGS, max_attempts=MAX_ATTEMPTS)["results"]
    assert offline_guard.call_count == 0


def test_resume_of_completed_checkpoint_is_noop(stubbed_assessor, tmp_path):
    final = run_agent("127.0.0.1", FINDINGS, max_attempts=MAX_ATTEMPTS)
    path = save_checkpoint(final, str(tmp_path / "completed.json"))

    again = resume_agent(path)

    assert again["status"] == "COMPLETED"
    assert again["current_index"] == final["current_index"]
    assert again["results"] == final["results"]
    assert resume_entry_point(again) is None


def test_resume_entry_point_mapping(stubbed_assessor):
    """Status -> entry-node contract (no wasted/duplicated steps)."""
    st = initial_agent_state("127.0.0.1", FINDINGS)
    assert resume_entry_point(st) == "assess"           # ASSESSING
    st = assess_node(st)
    assert resume_entry_point(st) == "execute"          # TESTING
    st = execute_node(st)
    assert resume_entry_point(st) == "pivot"            # SUCCESS
    st = pivot_node(st)
    while st["status"] != "COMPLETED":
        st = assess_node(st); st = execute_node(st); st = pivot_node(st)
    assert resume_entry_point(st) is None               # COMPLETED


def test_load_checkpoint_rejects_unknown_version(tmp_path):
    path = tmp_path / "bad_version.json"
    path.write_text(json.dumps({"version": 999, "state": {}}))
    with pytest.raises(ValueError, match="unsupported version"):
        load_checkpoint(str(path))


def test_save_checkpoint_creates_missing_directories(stubbed_assessor, tmp_path):
    st = _interrupt_mid_second_cve()
    nested = str(tmp_path / "deep" / "dir" / "ckpt.json")
    assert save_checkpoint(st, nested) == nested
    assert os.path.exists(nested)


def test_checkpoint_payload_is_plain_json_serializable(stubbed_assessor, tmp_path):
    """Guard against regression: the serialized state must survive a second
    json.dumps round-trip (no BaseModel / enum leakage)."""
    st = _interrupt_mid_second_cve()
    path = save_checkpoint(st, str(tmp_path / "x.json"))
    with open(path) as fh:
        payload = json.load(fh)
    json.dumps(payload)                     # would raise on non-JSON types
    assert not any(isinstance(v, BaseModel) for v in payload["state"].values())
