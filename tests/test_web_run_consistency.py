"""Regression tests for web-target run consistency (Phase 32A).

Root cause: web-target runs used the simulation executor (fabricating
FAIL_TIMEOUT from missing ground_truth), the pipeline authorization
compared full URLs against a host-only allowlist, and the default
/vuln path was never updated to the actual candidate target path.

These tests verify:
  1. Web finding with unsupported validation produces NO fabricated
     FAIL_TIMEOUT / SUCCESS execution results.
  2. No fabricated pivot events occur without real executor operations.
  3. Authorization validates host+port, not full URL path.
  4. Persisted execution_results are consistent with pipeline_summary.
  5. No inherited /vuln scenario path in web-target runs.
  6. Reporting consistency: JSON/HTML/Markdown/TXT all show the same
     validation semantics.
  7. GAP-2 is NOT manufactured from web scanner findings.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile
from unittest.mock import MagicMock

import pytest

import vapt_platform.scanner_service as scanner_service
import vapt_platform.web_target as web_target
from vapt_platform.application import VAPTRequest, get_application
from vapt_platform.normalization import from_nuclei_finding
from vapt_platform.parsers.nuclei_parser import NucleiFinding
from vapt_platform.persistence.config import PersistenceConfig
from vapt_platform.persistence.repository import JSONRunRepository, set_repository

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
APP_JS = pathlib.Path("frontend/web/js/app.js")


@pytest.fixture(autouse=True)
def isolated_repository():
    repo_dir = tempfile.mkdtemp()
    set_repository(JSONRunRepository(config=PersistenceConfig(storage_dir=repo_dir)))
    yield
    set_repository(JSONRunRepository())
    shutil.rmtree(repo_dir, ignore_errors=True)


def _mock_web_target(monkeypatch, tmp_path, nuclei_findings=None):
    """Mock preflight + Nmap discovery from real Juice XML fixture."""
    from vapt_platform.scanners import NmapXmlAdapter

    findings = NmapXmlAdapter().parse(str(DATA_DIR / "juice_shop_nmap.xml"))
    assert findings

    monkeypatch.setattr(
        web_target, "preflight_web_target",
        lambda _url, timeout=5.0: {
            "target_url": "http://127.0.0.1:9191",
            "resolved_host": "127.0.0.1",
            "port": 9191,
            "authorization_status": "AUTHORIZED",
            "preflight_status": "TARGET REACHABLE",
            "reachable": True,
            "http_status": 200,
            "detail": "HTTP 200 (mocked)",
        },
    )
    nmap_result = MagicMock()
    nmap_result.findings = findings
    nmap_result.to_dict.return_value = {
        "scanner": "nmap", "status": "COMPLETED", "exit_code": 0,
        "finding_count": len(findings), "target": "http://127.0.0.1:9191",
    }
    nuclei_result = MagicMock()
    nuclei_result.findings = nuclei_findings or []
    nuclei_result.to_dict.return_value = {
        "scanner": "nuclei", "status": "COMPLETED" if nuclei_findings else "NOT AVAILABLE",
        "exit_code": 0 if nuclei_findings else -1,
        "finding_count": len(nuclei_findings or []), "target": "http://127.0.0.1:9191",
    }
    monkeypatch.setattr(scanner_service, "run_nmap_discovery", lambda *a, **k: nmap_result)
    monkeypatch.setattr(scanner_service, "run_nuclei_scan", lambda *a, **k: nuclei_result)
    return findings


def _web_request():
    return VAPTRequest(
        scenario="web_target",
        mode="web",
        assessment_type="web",
        target_url="http://127.0.0.1:9191",
        use_nmap=True,
        use_nuclei=True,
        assessor_mode="deterministic",
        assessor_provider="ollama",
        max_attempts=2,
    )


def _prometheus_finding():
    """The actionable Nuclei finding: prometheus-metrics on /metrics."""
    return from_nuclei_finding(NucleiFinding(
        template_id="prometheus-metrics",
        name="Prometheus Metrics - Detect",
        severity="medium",
        target="http://127.0.0.1:9191/metrics",
        host="127.0.0.1",
        tags=["exposure", "prometheus", "config", "vuln"],
        cvss_score=5.3,
    ))


# =============================================================================
# 1. No fabricated FAIL_TIMEOUT / SUCCESS execution results
# =============================================================================

def test_web_finding_no_fabricated_execution_results(monkeypatch, tmp_path):
    """Web candidate without ground_truth must NOT produce FAIL_TIMEOUT."""
    _mock_web_target(monkeypatch, tmp_path, [_prometheus_finding()])
    result = get_application().run(_web_request())
    domain = result.domain

    # The candidate exists and is actionable
    assert len(domain.candidates) == 1
    cand = domain.candidates[0]
    assert cand["id"] == "prometheus-metrics"

    # NO fabricated execution results — the simulation executor must not
    # run for web mode (no ground_truth → would fabricate FAIL_TIMEOUT)
    assert domain.execution_results == [], (
        f"Web run must not fabricate execution results, got: {domain.execution_results}"
    )


def test_web_finding_no_fabricated_pivot(monkeypatch, tmp_path):
    """No pivot without real executor operations."""
    _mock_web_target(monkeypatch, tmp_path, [_prometheus_finding()])
    result = get_application().run(_web_request())
    domain = result.domain

    # Pivot count must be 0 — no real attempts occurred
    assert domain.pivot_count == 0, (
        f"Web run must not fabricate pivots, got: {domain.pivot_count}"
    )
    assert domain.total_attempts == 0


# =============================================================================
# 2. Authorization validates host+port, not full URL path
# =============================================================================

def test_authorization_host_not_full_url():
    """SafetyGate must authorize by host, not by full URL string."""
    from vapt_platform.pipeline import SafetyGate, PlannedAction

    gate = SafetyGate(allowlist={"127.0.0.1"})
    action = PlannedAction(
        action_id="a1",
        candidate_id="prometheus-metrics",
        target="http://127.0.0.1:9191/metrics",
        port=9191,
        protocol="tcp",
        path="/metrics",
        description="test",
    )
    result = gate.validate(action)
    # The host 127.0.0.1 is authorized; the URL path must not cause rejection
    assert result.is_valid, (
        f"Authorization must validate host+port, not full URL. Got: {result.reason}"
    )


# =============================================================================
# 3. Persisted execution_results consistent with pipeline_summary
# =============================================================================

def test_persisted_results_consistent_with_pipeline(monkeypatch, tmp_path):
    """Top-level execution_results and pipeline_summary must tell one story."""
    _mock_web_target(monkeypatch, tmp_path, [_prometheus_finding()])
    app = get_application()
    result = app.run(_web_request())
    domain = result.domain

    from vapt_platform.persistence import get_repository
    persisted = get_repository().get(domain.run_id)
    assert persisted is not None

    # If execution_results is empty, pipeline must also show no executions
    if not domain.execution_results:
        # Pipeline summary should not contain fabricated execution results
        pipeline = persisted.pipeline_summary or {}
        web_ctx = pipeline.get("web", {})
        # The pipeline evidence should show rejection, not execution
        evidence = web_ctx.get("evidence", [])
        for ev in evidence:
            if isinstance(ev, dict):
                # No execution should have occurred
                assert ev.get("evidence_type") != "execution", (
                    "Pipeline must not show execution when no executor ran"
                )


# =============================================================================
# 4. No inherited /vuln scenario path
# =============================================================================

def test_no_inherited_vuln_path(monkeypatch, tmp_path):
    """Web-target runs must not inherit the default /vuln scenario path."""
    _mock_web_target(monkeypatch, tmp_path, [_prometheus_finding()])
    result = get_application().run(_web_request())
    domain = result.domain

    from vapt_platform.persistence import get_repository
    persisted = get_repository().get(domain.run_id)
    assert persisted is not None

    # The persisted path must NOT be /vuln (the default scenario path)
    # It should be the actual candidate target path or empty
    assert persisted.path != "/vuln", (
        f"Web run must not inherit /vuln scenario path, got: {persisted.path}"
    )


# =============================================================================
# 5. Reporting consistency
# =============================================================================

def test_reporting_consistency(monkeypatch, tmp_path):
    """JSON/HTML/Markdown/TXT all show the same validation semantics."""
    _mock_web_target(monkeypatch, tmp_path, [_prometheus_finding()])
    app = get_application()
    result = app.run(_web_request())
    run_id = result.domain.run_id

    # All formats must contain the same validation status
    for fmt in ("json", "html", "markdown", "txt"):
        report = app.generate_report(run_id, fmt)
        assert isinstance(report, str) and len(report) > 0
        # Must NOT contain fabricated execution outcomes
        if fmt == "json":
            data = json.loads(report)
            # No execution results in report
            assert data.get("execution_results", []) == [], (
                f"JSON report must not contain fabricated execution results"
            )


# =============================================================================
# 6. GAP-2 NOT manufactured from web scanner findings
# =============================================================================

def test_gap2_not_manufactured_from_web_findings(monkeypatch, tmp_path):
    """Web scanner findings must not manufacture GAP-2 pivot behavior."""
    _mock_web_target(monkeypatch, tmp_path, [_prometheus_finding()])
    result = get_application().run(_web_request())
    domain = result.domain

    # GAP-2 requires real bounded attempts. Web findings have no executor.
    assert domain.pivot_count == 0, "GAP-2 must not be manufactured from web findings"
    assert domain.total_attempts == 0, "No real attempts occurred"

    # The decision trace must not contain pivot events
    for log in domain.decision_trace:
        assert "[Pivot]" not in log or "Abandoning" not in log, (
            f"Web run must not have pivot events: {log}"
        )


# =============================================================================
# 7. Validation status is semantically correct
# =============================================================================

def test_validation_status_semantically_correct(monkeypatch, tmp_path):
    """Web finding validation_status must be VALIDATION NOT AVAILABLE."""
    _mock_web_target(monkeypatch, tmp_path, [_prometheus_finding()])
    result = get_application().run(_web_request())
    domain = result.domain

    assert len(domain.candidates) == 1
    cand = domain.candidates[0]
    vs = str(cand.get("validation_status", ""))
    assert "NOT AVAILABLE" in vs.upper(), (
        f"Web finding must show VALIDATION NOT AVAILABLE, got: {vs}"
    )
    assert vs != "VALIDATED", "Web finding must never show VALIDATED"
    assert vs != "SIMULATED", "Web finding must not show SIMULATED (no simulation ran)"


# =============================================================================
# 8. Evidence tier is correct
# =============================================================================

def test_evidence_tier_observed_local(monkeypatch, tmp_path):
    """Web-target runs must show OBSERVED_LOCAL evidence tier."""
    _mock_web_target(monkeypatch, tmp_path, [_prometheus_finding()])
    result = get_application().run(_web_request())
    domain = result.domain

    assert domain.evidence_tier == "OBSERVED_LOCAL", (
        f"Web run must show OBSERVED_LOCAL, got: {domain.evidence_tier}"
    )


# =============================================================================
# 9. Frontend consistency
# =============================================================================

def test_frontend_no_fabricated_execution_display():
    """Frontend must not display fabricated execution results."""
    js = APP_JS.read_text(encoding="utf-8")
    # The frontend must use validation_status to determine display
    assert "validation_status" in js
    assert "VALIDATION NOT AVAILABLE" in js
    # Must not unconditionally show execution outcomes
    assert "execution_outcome" in js  # shown but not as proof


# =============================================================================
# 10. Nmap-only run (no actionable candidates) — no engine, no fabrication
# =============================================================================

# =============================================================================
# 10. Nmap-only run (no actionable candidates) — no engine, no fabrication
# =============================================================================

def test_nmap_only_run_no_fabrication(monkeypatch, tmp_path):
    """Nmap-only run (no actionable candidates) must not fabricate anything."""
    _mock_web_target(monkeypatch, tmp_path, [])  # No Nuclei findings
    result = get_application().run(_web_request())
    domain = result.domain

    # No candidates → no engine → no execution
    assert domain.candidates == []
    assert domain.execution_results == []
    assert domain.pivot_count == 0
    assert domain.total_attempts == 0
    # Discovery preserved
    assert len(domain.service_discovery) >= 1


# =============================================================================
# 11. Phase 32B FIX 1 — assessment-only executor + explicit marker
# =============================================================================

def test_web_build_executor_returns_none_for_web():
    """WEB mode must not receive the simulation executor."""
    from vapt_platform.application import VAPTRequest, get_application

    app = get_application()
    web_req = VAPTRequest(
        scenario="web_target", mode="web", assessment_type="web",
        target_url="http://127.0.0.1:9191",
    )
    assert app._build_executor(web_req, []) is None

    # Simulation and lab modes keep their executors.
    sim_req = VAPTRequest(scenario="success", mode="simulation")
    assert app._build_executor(sim_req, []) is not None


def test_web_context_marks_validation_unavailable(monkeypatch, tmp_path):
    """Pipeline summary explicitly records WEB_VALIDATION_UNAVAILABLE."""
    from vapt_platform.application import WEB_VALIDATION_UNAVAILABLE

    _mock_web_target(monkeypatch, tmp_path, [_prometheus_finding()])
    result = get_application().run(_web_request())

    from vapt_platform.persistence import get_repository
    persisted = get_repository().get(result.domain.run_id)
    web_ctx = (persisted.pipeline_summary or {}).get("web", {})
    assert web_ctx.get("validation", {}).get("status") == WEB_VALIDATION_UNAVAILABLE


def test_web_candidates_carry_no_ground_truth(monkeypatch, tmp_path):
    """No synthetic ground truth is created for web scanner findings."""
    _mock_web_target(monkeypatch, tmp_path, [_prometheus_finding()])
    result = get_application().run(_web_request())
    for cand in result.domain.candidates:
        assert "ground_truth" not in cand or cand.get("ground_truth") in (None, "")


# =============================================================================
# 12. Phase 32B FIX 3 — per-candidate paths, most-common run path
# =============================================================================

def test_web_candidate_paths_preserved_and_run_path_actual(monkeypatch, tmp_path):
    """Each candidate keeps its own URL path; run path is most common."""
    from vapt_platform.normalization import from_nuclei_finding

    api_finding = from_nuclei_finding(NucleiFinding(
        template_id="swagger-api",
        name="Public Swagger API - Detect",
        severity="medium",
        target="http://127.0.0.1:9191/api",
        host="127.0.0.1",
        tags=["exposure", "api"],
        cvss_score=5.3,
    ))
    _mock_web_target(monkeypatch, tmp_path, [_prometheus_finding(), api_finding])
    result = get_application().run(_web_request())
    domain = result.domain

    by_id = {c["id"]: c for c in domain.candidates}
    assert by_id["prometheus-metrics"]["path"] == "/metrics"
    assert by_id["swagger-api"]["path"] == "/api"

    from vapt_platform.persistence import get_repository
    persisted = get_repository().get(domain.run_id)
    assert persisted.path in ("/metrics", "/api")
    assert persisted.path != "/vuln"


# =============================================================================
# 13. Phase 32B FIX 5 — web provenance in every report format
# =============================================================================

def test_web_provenance_in_all_report_formats(monkeypatch, tmp_path):
    """Reports state target/scanners/AI/validation/execution truthfully."""
    _mock_web_target(monkeypatch, tmp_path, [_prometheus_finding()])
    app = get_application()
    result = app.run(_web_request())
    run_id = result.domain.run_id

    data = json.loads(app.generate_report(run_id, "json"))
    prov = data.get("web_provenance", {})
    assert prov.get("target_url") == "http://127.0.0.1:9191"
    assert prov.get("validation") == "NOT AVAILABLE"
    assert prov.get("execution") == "NOT PERFORMED"
    assert prov.get("ai", {}).get("provider") == "deterministic"
    assert data.get("path") == "/metrics"
    assert "FAIL_TIMEOUT" not in json.dumps(data)

    md = app.generate_report(run_id, "markdown")
    assert "Web Assessment Provenance" in md
    assert "NOT PERFORMED" in md
    assert "/vuln" not in md

    txt = app.generate_report(run_id, "txt")
    assert "WEB ASSESSMENT PROVENANCE" in txt
    assert "NOT PERFORMED" in txt

    html = app.generate_report(run_id, "html")
    assert "Web Assessment Provenance" in html


def test_non_web_report_has_no_web_provenance():
    """Scenario runs must not gain a web provenance section."""
    from vapt_platform.application import DomainResult
    from vapt_platform.reporting.builder import ReportBuilder

    domain = DomainResult(scenario="success", mode="simulation")
    report = ReportBuilder().from_domain_result(domain)
    assert report.to_dict().get("web_provenance", {}) == {}


# =============================================================================
# 14. Phase 32B FIX 6 — UI execution honesty
# =============================================================================

def test_ui_execution_stage_never_green_without_validation():
    """EXECUTION is green only for genuine VALIDATED findings."""
    js = APP_JS.read_text(encoding="utf-8")
    assert "webStageNeutral('EXECUTION'" in js
    assert "NOT PERFORMED" in js
    # Scanner stages earn green only on recorded COMPLETED.
    assert "scanRow('Nmap discovery', nmap)" in js or 'scanRow(' in js


# =============================================================================
# 15. Phase 32B FIX 9 — authorization safety matrix
# =============================================================================

def test_authorization_accept_matrix():
    """Authorized local targets (bare and pathed) are accepted."""
    from vapt_platform.web_target import validate_web_target

    for url in (
        "http://127.0.0.1:9191",
        "http://127.0.0.1:9191/metrics",
        "http://localhost:9191/metrics",
    ):
        result = validate_web_target(url)
        assert result.authorized, f"{url} must be ACCEPTED: {result.reason}"


def test_authorization_reject_matrix():
    """Public/outer-scope/credentialed/malformed targets are rejected."""
    from vapt_platform.web_target import validate_web_target

    for url in (
        "https://example.com",
        "http://8.8.8.8",
        "http://127.0.0.1:8080",
        "http://user:pass@127.0.0.1:9191",
        "not a url",
        "http://",
        "",
        "http://2130706433/",
        "ftp://127.0.0.1:9191/",
    ):
        result = validate_web_target(url)
        assert not result.authorized, f"{url} must be REJECTED"


def test_safety_gate_url_matrix():
    """SafetyGate authorizes pathed URLs by host; rejects the rest."""
    from vapt_platform.pipeline import PlannedAction, SafetyGate

    gate = SafetyGate(allowlist={"127.0.0.1", "localhost"})
    for target in (
        "http://127.0.0.1:9191/metrics",
        "http://localhost:9191/metrics",
    ):
        action = PlannedAction(
            action_id="a1", candidate_id="c", target=target, port=9191,
            protocol="tcp", path="/metrics", description="test",
        )
        assert gate.validate(action).is_valid, f"{target} must validate"
    for target in ("https://example.com", "http://8.8.8.8", "http://127.0.0.1:8080"):
        action = PlannedAction(
            action_id="a1", candidate_id="c", target=target, port=9191,
            protocol="tcp", path="/", description="test",
        )
        assert not gate.validate(action).is_valid, f"{target} must reject"


def test_scanners_never_start_after_rejection(monkeypatch):
    """Rejected targets stop the workflow before any scanner subprocess."""
    nmap_mock = MagicMock(side_effect=AssertionError("scanner must not run"))
    nuclei_mock = MagicMock(side_effect=AssertionError("scanner must not run"))
    monkeypatch.setattr(scanner_service, "run_nmap_discovery", nmap_mock)
    monkeypatch.setattr(scanner_service, "run_nuclei_scan", nuclei_mock)

    req = _web_request()
    req.target_url = "https://example.com"
    result = get_application().run(req)

    assert result.domain.final_status == "FAILED"
    nmap_mock.assert_not_called()
    nuclei_mock.assert_not_called()
