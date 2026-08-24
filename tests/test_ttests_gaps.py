"""T-TESTS coverage extension: requirement gaps not covered by test_core.py.

Scope (per task brief):
  (b) exploit_assessor returns a valid, enum-constrained ExploitAssessment --
      exercised through the REAL assess_exploit_quality path (corpus lookup,
      prompt | structured-output chain, corpus-label cross-check) with the
      LLM boundary mocked, so no Ollama/network is needed.
  (c) agent_graph pivots and terminates with ZERO loop events -- asserted as
      max executions per CVE <= max_attempts (exceedances == 0), computed
      from the runtime execution trace. If a state carries an explicit
      "loop_events" log (future instrumentation), it must be empty too.
  (d) executor simulation resolves EVERY corpus outcome from labels.json
      (data-driven over the whole label file, not hardcoded samples).
  (e) executor REAL mode is connectivity-only by default: an UNREACHABLE
      host yields FAIL_NO_TARGET with request_count==1 and never shells out
      (complements test_core's reachable -> SKIPPED case).

All tests are offline & fast: conftest.py blocks requests/socket and records
subprocess.run; the LLM boundary is mocked here.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from langchain_core.runnables import Runnable

import core.exploit_assessor as exploit_assessor
from core.agent_graph import run_agent
from core.executor import Executor
from core.schemas import (
    ExecutionOutcome,
    ExploitAssessment,
    Finding,
    UsabilityRank,
)

CORPUS_LABELS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "poc_corpus", "labels.json",
)


def _canned_assessment() -> ExploitAssessment:
    """A fully valid, constrained ExploitAssessment (as the LLM must emit)."""
    return ExploitAssessment(
        exploit_found=True,
        syntax_valid=True,
        os_dependencies="paramiko",
        privileges_required="user",       # Literal: none|user|root
        network_noise="medium",           # Literal: low|medium|high
        complexity_score=4,               # int 1..10
        prerequisites_met=True,
        usability_rank=UsabilityRank.HIGH,
        reasoning="mocked structured output",
    )


class _FakeStructured(Runnable):
    """Stand-in for llm.with_structured_output(ExploitAssessment)."""

    def __init__(self, payload):
        super().__init__()
        self._payload = payload
        self.schema = None

    def invoke(self, *_args, **_kwargs):
        return self._payload


class _RejectingStructured(Runnable):
    """Simulates the schema rejecting malformed LLM output."""

    def __init__(self, schema):
        super().__init__()
        self.schema = schema

    def invoke(self, *_a, **_k):
        raise ValueError("Invalid JSON or constraint violation")


# ---------------------------------------------------------------------------
# (b) exploit_assessor: full path, mocked LLM, enum-constrained result
# ---------------------------------------------------------------------------
def test_assess_exploit_quality_returns_valid_constrained_assessment(
    monkeypatch, offline_guard
):
    payload = _canned_assessment()
    monkeypatch.setattr(
        exploit_assessor, "get_llm",
        lambda *a, **k: MagicMock(with_structured_output=lambda schema: _FakeStructured(payload)),
    )
    # Defensive: never touch GitHub even if the corpus lookup ever misses.
    monkeypatch.setattr(exploit_assessor, "fetch_github_poc", lambda cve: None)

    result = exploit_assessor.assess_exploit_quality(
        "CVE-2021-44228", provider="ollama"
    )

    # Type + enum constraints enforced by the structured-output contract.
    assert isinstance(result, ExploitAssessment)
    assert isinstance(result.usability_rank, UsabilityRank)
    assert result.usability_rank.value in ("HIGH", "MEDIUM", "LOW")
    assert result.privileges_required in ("none", "user", "root")
    assert result.network_noise in ("low", "medium", "high")
    assert isinstance(result.complexity_score, int)
    assert 1 <= result.complexity_score <= 10
    assert isinstance(result.reasoning, str) and result.reasoning

    # Real path taken: corpus label cross-check appended to reasoning.
    assert "[corpus-label=" in result.reasoning
    # No LLM/network was touched.
    assert offline_guard.call_count == 0


def test_assess_exploit_quality_rejects_malformed_llm_output(monkeypatch):
    """A malformed LLM answer (e.g. the historical '}' garbage) must be
    rejected by the schema, not passed through."""
    monkeypatch.setattr(
        exploit_assessor, "get_llm",
        lambda *a, **k: MagicMock(
            with_structured_output=lambda schema: _RejectingStructured(schema)),
    )
    monkeypatch.setattr(exploit_assessor, "fetch_github_poc", lambda cve: None)

    with pytest.raises(ValueError):
        exploit_assessor.assess_exploit_quality("CVE-2021-44228")


# ---------------------------------------------------------------------------
# (c) agent_graph: pivots through all targets, terminates, ZERO loop events
# ---------------------------------------------------------------------------
@pytest.fixture
def stubbed_assessor(monkeypatch):
    """Deterministic HIGH-rank assessor so ordering is stable."""
    monkeypatch.setattr(
        "core.agent_graph.assess_exploit_quality",
        lambda *a, **k: _canned_assessment(),
    )


def test_run_agent_pivots_terminates_with_zero_loop_events(stubbed_assessor,
                                                           offline_guard):
    findings = [
        {"cve": "CVE-2021-44228", "port": 8080, "service": "http",
         "description": "valid target", "epss_score": 0.999},
        {"cve": "CVE-2023-38408", "port": 22, "service": "ssh",
         "description": "dead end (fail_timeout)", "epss_score": 0.797},
        {"cve": "CVE-2022-22965", "port": 9090, "service": "http",
         "description": "dead end (fail_syntax)", "epss_score": 0.31},
    ]
    max_attempts = 2
    final = run_agent("127.0.0.1", findings, provider="ollama",
                      max_attempts=max_attempts, mode="simulation")

    # Terminated cleanly after visiting every target (pivot advanced).
    assert final["status"] == "COMPLETED"

    # ZERO loop events: no CVE was executed more than max_attempts times.
    per_cve = {}
    for r in final["results"]:
        per_cve[r["cve"]] = per_cve.get(r["cve"], 0) + 1
    exceedances = sum(max(0, n - max_attempts) for n in per_cve.values())
    assert exceedances == 0
    assert all(n <= max_attempts for n in per_cve.values())

    # Pivot evidence: abandoned dead ends AND advanced after success.
    logs = "\n".join(final["logs"])
    assert "Abandoning route" in logs          # threshold pivots
    assert "Moving to next target" in logs     # success advance

    # Future-proof: if explicit loop-event records ever appear in state,
    # a healthy run must carry none.
    assert final.get("loop_events", []) == []

    assert offline_guard.call_count == 0       # fully offline


# ---------------------------------------------------------------------------
# (d) executor simulation resolves EVERY label from labels.json (data-driven)
# ---------------------------------------------------------------------------
def test_executor_simulation_outcomes_match_labels_json(offline_guard):
    with open(CORPUS_LABELS) as fh:
        labels = json.load(fh)
    assert labels, "labels.json must contain corpus ground truth"

    ex = Executor(mode="simulation")
    for cve, meta in labels.items():
        r = ex.execute(Finding(cve=cve, port=8080), "127.0.0.1")
        expected = ExecutionOutcome[str(meta["outcome"]).strip().upper()]
        assert r.outcome == expected, f"{cve}: {r.outcome} != {expected}"
        assert r.request_count == 1
    assert offline_guard.call_count == 0


# ---------------------------------------------------------------------------
# (e) executor REAL mode: connectivity-only, unreachable -> FAIL_NO_TARGET
# ---------------------------------------------------------------------------
def test_executor_real_unreachable_fail_no_target_no_shellout(offline_guard):
    """With sockets blocked (unreachable), real mode reports FAIL_NO_TARGET,
    counts the single honest request, and NEVER spawns a PoC subprocess."""
    ex = Executor(mode="real")                 # danger_mode defaults False
    f = Finding(cve="CVE-2021-44228", port=8080, usability_rank=UsabilityRank.HIGH)

    r = ex.execute(f, "203.0.113.1")           # TEST-NET-3, guaranteed unused

    assert r.outcome == ExecutionOutcome.FAIL_NO_TARGET
    assert r.request_count == 1
    assert "unreachable" in r.detail.lower()
    assert offline_guard.call_count == 0       # no corpus module executed
