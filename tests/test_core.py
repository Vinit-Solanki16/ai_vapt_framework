"""Regression net for the AI VAPT Framework core units (T-TESTS, P3).

Runs 100% OFFLINE: the LLM assessor is monkeypatched to a deterministic stub,
the EPSS API / sockets / subprocess are blocked or recorded by conftest.py.

Coverage:
  (a) schemas enum validation + Finding construction
  (b) priority_score ordering (rank_findings)
  (c) scanner parsing of sample_scan.json (sorted by EPSS) and live_scan.xml
      (tolerant missing-CVE handling)
  (d) executor simulation outcomes from labels.json, request_count == 1
  (e) executor real mode = connectivity-only safety (SKIPPED, no subprocess)
  (f) agent_graph pivot/loop terminates, bounds retries to max_attempts
"""
from __future__ import annotations

from collections import Counter
from unittest.mock import MagicMock

import pytest

import core.agent_graph as agent_graph
import core.executor as executor
import core.scanner as scanner
from core.agent_graph import rank_findings, run_agent
from core.executor import Executor
from core.schemas import (
    AgentStatus,
    ExecutionOutcome,
    ExploitAssessment,
    Finding,
    UsabilityRank,
    finding_from_dict,
)


# ---------------------------------------------------------------------------
# (a) Schemas: enum validation + Finding construction
# ---------------------------------------------------------------------------
def test_usability_rank_rejects_invalid_value():
    """ExploitAssessment.usability_rank must reject non-enum strings."""
    with pytest.raises(Exception):  # pydantic.ValidationError (or ValueError)
        ExploitAssessment(
            exploit_found=True,
            syntax_valid=True,
            os_dependencies="none",
            privileges_required="none",
            network_noise="low",
            complexity_score=3,
            prerequisites_met=True,
            usability_rank="NOT_A_REAL_RANK",  # invalid
            reasoning="should fail",
        )


def test_usability_rank_accepts_valid_values():
    for rank in ("HIGH", "MEDIUM", "LOW"):
        a = ExploitAssessment(
            exploit_found=True,
            syntax_valid=True,
            os_dependencies="none",
            privileges_required="none",
            network_noise="low",
            complexity_score=3,
            prerequisites_met=True,
            usability_rank=rank,
            reasoning="ok",
        )
        assert a.usability_rank.value == rank


def test_finding_from_dict_missing_cve_is_unknown():
    f = finding_from_dict({})
    assert f.cve == "UNKNOWN-CVE"


def test_finding_from_dict_full_fields():
    f = finding_from_dict({
        "cve": "CVE-2021-44228",
        "port": 8080,
        "service": "http",
        "description": "Log4Shell",
        "epss_score": 0.5,
    })
    assert f.cve == "CVE-2021-44228"
    assert f.port == 8080
    assert f.service == "http"
    assert f.epss_score == 0.5


def test_finding_constructs_from_dict_directly():
    f = Finding(**{"cve": "CVE-1234", "port": 443, "epss_score": 0.2})
    assert f.cve == "CVE-1234"
    assert f.epss_score == 0.2


# ---------------------------------------------------------------------------
# (b) priority_score ordering
# ---------------------------------------------------------------------------
def test_rank_findings_orders_by_priority_descending():
    hi = Finding(cve="CVE-HI", epss_score=0.9, usability_rank=UsabilityRank.HIGH)
    lo = Finding(cve="CVE-LO", epss_score=0.1, usability_rank=UsabilityRank.LOW)
    ranked = rank_findings([lo, hi])  # deliberately unsorted input
    assert ranked[0].cve == "CVE-HI"
    assert ranked[-1].cve == "CVE-LO"


def test_priority_score_formula_and_ordering():
    # priority_score = epss * (0.5 + 0.5 * u)
    hi = Finding(cve="A", epss_score=0.9, usability_rank=UsabilityRank.HIGH)   # u=1.0
    lo = Finding(cve="B", epss_score=0.1, usability_rank=UsabilityRank.LOW)    # u=0.3
    assert hi.priority_score() == pytest.approx(0.9 * (0.5 + 0.5 * 1.0))
    assert lo.priority_score() == pytest.approx(0.1 * (0.5 + 0.5 * 0.3))
    assert hi.priority_score() > lo.priority_score()


# ---------------------------------------------------------------------------
# (c) Scanner parsing
# ---------------------------------------------------------------------------
def test_process_sample_scan_sorted_by_epss(monkeypatch):
    """Custom JSON -> Finding list sorted by EPSS descending (offline, fixed)."""
    fixed = {"CVE-2021-44228": 0.97, "CVE-2023-38408": 0.10}

    def fake_epss(cve_id, timeout=5):
        return fixed.get(cve_id.strip().upper(), 0.0)

    monkeypatch.setattr(scanner, "fetch_epss_score", fake_epss)
    findings = scanner.process_scan("data/sample_scan.json")
    assert len(findings) == 2
    assert findings[0].cve == "CVE-2021-44228"
    assert findings[0].epss_score >= findings[1].epss_score
    assert findings[0].port == 8080


def test_nmap_xml_tolerant_missing_cve(monkeypatch):
    """Nmap XML has no CVE -> Finding built with UNKNOWN-CVE, no crash."""
    monkeypatch.setattr(scanner, "fetch_epss_score", lambda c, timeout=5: 0.0)
    findings = scanner.process_scan("data/live_scan.xml")
    assert len(findings) == 1
    assert findings[0].cve == "UNKNOWN-CVE"
    assert findings[0].port == 80
    assert findings[0].service == "http"


# ---------------------------------------------------------------------------
# (d) Executor simulation outcomes (from labels.json) + offline guarantee
# ---------------------------------------------------------------------------
def test_executor_simulation_outcomes(offline_guard, monkeypatch):
    ex = Executor(mode="simulation")
    # simulation must never perform a connectivity probe or shell out
    probe = MagicMock(name="_connectivity_probe")
    monkeypatch.setattr(Executor, "_connectivity_probe", probe)

    r1 = ex.execute(Finding(cve="CVE-2021-44228", port=8080), "127.0.0.1")
    assert r1.outcome == ExecutionOutcome.SUCCESS
    assert r1.request_count == 1

    r2 = ex.execute(Finding(cve="CVE-2023-38408", port=22), "127.0.0.1")
    assert r2.outcome == ExecutionOutcome.FAIL_TIMEOUT
    assert r2.request_count == 1

    # Offline guarantees
    assert probe.call_count == 0, "simulation must not probe the network"
    assert offline_guard.call_count == 0, "simulation must not shell out"


# ---------------------------------------------------------------------------
# (e) Executor real mode = connectivity-only SAFE (no subprocess, SKIPPED)
# ---------------------------------------------------------------------------
def test_executor_real_safe_no_subprocess_when_reachable(offline_guard, monkeypatch):
    probe = MagicMock(return_value=(True, "reachable (stubbed)"))
    monkeypatch.setattr(Executor, "_connectivity_probe", probe)

    ex = Executor(mode="real")
    f = Finding(cve="CVE-2021-44228", port=8080, usability_rank=UsabilityRank.HIGH)
    r = ex.execute(f, "127.0.0.1")

    assert r.outcome == ExecutionOutcome.SKIPPED
    assert r.request_count == 1
    assert probe.call_count == 1
    # T-SAFE: live PoC execution is disabled by default -> no subprocess
    assert offline_guard.call_count == 0


def test_executor_real_low_usability_skipped(offline_guard, monkeypatch):
    probe = MagicMock(return_value=(True, "reachable (stubbed)"))
    monkeypatch.setattr(Executor, "_connectivity_probe", probe)

    ex = Executor(mode="real")
    f = Finding(cve="CVE-2023-38408", port=22, usability_rank=UsabilityRank.LOW)
    r = ex.execute(f, "127.0.0.1")
    assert r.outcome == ExecutionOutcome.SKIPPED
    assert offline_guard.call_count == 0


# ---------------------------------------------------------------------------
# (f) Agent graph pivot/loop: terminates, bounds retries (T-BENCH-LOOP)
# ---------------------------------------------------------------------------
def test_run_agent_terminates_within_max_attempts(offline_guard, monkeypatch):
    """run_agent with stubbed LLM + simulation executor must complete with the
    per-CVE retry count bounded by max_attempts (no infinite loop)."""
    stub = ExploitAssessment(
        exploit_found=True,
        syntax_valid=True,
        os_dependencies="none",
        privileges_required="none",
        network_noise="low",
        complexity_score=2,
        prerequisites_met=True,
        usability_rank=UsabilityRank.HIGH,  # deterministic rank
        reasoning="stubbed assessor (offline)",
    )
    # Patch agent_graph's reference to the LLM assessor
    monkeypatch.setattr(agent_graph, "assess_exploit_quality", lambda *a, **k: stub)

    findings = [
        {"cve": "CVE-2021-44228", "port": 8080, "service": "http",
         "description": "Log4Shell", "epss_score": 0.999},
        {"cve": "CVE-2023-38408", "port": 22, "service": "ssh",
         "description": "OpenSSH", "epss_score": 0.797},
        {"cve": "CVE-2022-22965", "port": 9090, "service": "http",
         "description": "Spring4Shell", "epss_score": 0.31},
    ]
    max_attempts = 2
    final = run_agent(
        "127.0.0.1", findings, provider="ollama",
        max_attempts=max_attempts, mode="simulation",
    )

    # Graph completed (did not loop forever)
    assert final["status"] in (AgentStatus.SUCCESS.value, AgentStatus.COMPLETED.value)

    # T-BENCH-LOOP guard: no CVE executed more than max_attempts times
    counts = Counter(r["cve"] for r in final["results"])
    assert all(c <= max_attempts for c in counts.values()), dict(counts)

    # Advanced through ALL findings
    processed = {r["cve"] for r in final["results"]}
    assert processed == {
        "CVE-2021-44228", "CVE-2023-38408", "CVE-2022-22965"
    }

    # Simulation must not touch the network or shell out
    assert offline_guard.call_count == 0
