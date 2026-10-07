"""FIX 3 — unambiguous validation semantics for web assessments.

Backend source of truth is the per-candidate ``validation_status`` +
run ``evidence_tier`` (never scanner detection alone):
  - web scanner findings: SCANNER-DETECTED (pre-engine) →
    VALIDATION NOT AVAILABLE / SIMULATED-OUTCOME (validation not
    available) post-engine. Never VALIDATED.
  - simulation runs: SIMULATED (no real validation).
  - lab runs: DOCKER_OBSERVED (emulator-observed, not real-world).
  - VALIDATED appears only for genuine controlled validation.

UI/report must mirror backend: pipeline VALIDATION shows neutral
"— NOT AVAILABLE" (no green ✓) unless backend says VALIDATED;
scanner detection is never reported as exploit success.

Offline-safe: mocked scanners/preflight; no live execution.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _isolated_repo(monkeypatch=None):
    from vapt_platform.persistence.config import PersistenceConfig
    from vapt_platform.persistence.repository import JSONRunRepository, set_repository

    repo_dir = tempfile.mkdtemp()
    set_repository(JSONRunRepository(config=PersistenceConfig(storage_dir=repo_dir)))
    return repo_dir


def test_scanner_only_finding_validation_unavailable(monkeypatch):
    """Web scanner finding → SCANNER-DETECTED inventory, NOT AVAILABLE ranking."""
    import vapt_platform.scanner_service as scanner_service
    import vapt_platform.web_target as web_target
    from vapt_platform.application import VAPTRequest, get_application
    from vapt_platform.scanners import NmapXmlAdapter

    repo_dir = _isolated_repo()
    try:
        nmap_findings = NmapXmlAdapter().parse(str(DATA_DIR / "juice_shop_nmap.xml"))
        assert nmap_findings

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
        nmap_result.findings = nmap_findings
        nmap_result.to_dict.return_value = {
            "scanner": "nmap", "status": "COMPLETED", "exit_code": 0,
            "finding_count": len(nmap_findings), "target": "http://127.0.0.1:9191",
        }
        nuclei_result = MagicMock()
        nuclei_result.findings = []
        nuclei_result.to_dict.return_value = {
            "scanner": "nuclei", "status": "NOT AVAILABLE",
            "detail": "Nuclei not installed (mocked).",
        }
        monkeypatch.setattr(scanner_service, "run_nmap_discovery", lambda *a, **k: nmap_result)
        monkeypatch.setattr(scanner_service, "run_nuclei_scan", lambda *a, **k: nuclei_result)

        req = VAPTRequest(
            scenario="web_target", mode="web", assessment_type="web",
            target_url="http://127.0.0.1:9191",
            use_nmap=True, use_nuclei=True,
            assessor_mode="deterministic", assessor_provider="ollama",
            max_attempts=2,
        )
        result = get_application().run(req)
        domain = result.domain

        # Scanner inventory preserved; nothing ranked as exploit.
        assert domain.candidates == []
        assert len(domain.service_discovery) >= 1
        # Web executor state: validation unavailable, evidence loopback.
        assert domain.evidence_tier == "OBSERVED_LOCAL"
        assert "VALIDATION NOT AVAILABLE" in domain.safety_notice
        assert "NOT automatically confirmed" in domain.safety_notice
    finally:
        from vapt_platform.persistence.repository import JSONRunRepository, set_repository

        set_repository(JSONRunRepository())
        shutil.rmtree(repo_dir, ignore_errors=True)


def test_web_actionable_finding_never_reported_as_validated(monkeypatch):
    """Actionable web finding carries NOT AVAILABLE, never VALIDATED/SUCCESS-as-proof."""
    import vapt_platform.scanner_service as scanner_service
    import vapt_platform.web_target as web_target
    from vapt_platform.application import VAPTRequest, get_application
    from vapt_platform.normalization import from_nuclei_finding
    from vapt_platform.parsers.nuclei_parser import NucleiFinding
    from vapt_platform.scanners import NmapXmlAdapter

    repo_dir = _isolated_repo()
    try:
        nmap_findings = NmapXmlAdapter().parse(str(DATA_DIR / "juice_shop_nmap.xml"))
        vuln = from_nuclei_finding(NucleiFinding(
            template_id="CVE-2021-44228",
            name="Apache Log4j RCE (JNDI)",
            severity="critical",
            target="http://127.0.0.1:9191",
            host="127.0.0.1",
        ))
        monkeypatch.setattr(
            web_target, "preflight_web_target",
            lambda _url, timeout=5.0: {
                "target_url": "http://127.0.0.1:9191",
                "resolved_host": "127.0.0.1", "port": 9191,
                "authorization_status": "AUTHORIZED",
                "preflight_status": "TARGET REACHABLE",
                "reachable": True, "http_status": 200,
                "detail": "HTTP 200 (mocked)",
            },
        )
        nmap_result = MagicMock()
        nmap_result.findings = nmap_findings
        nmap_result.to_dict.return_value = {
            "scanner": "nmap", "status": "COMPLETED", "exit_code": 0,
            "finding_count": len(nmap_findings), "target": "http://127.0.0.1:9191",
        }
        nuclei_result = MagicMock()
        nuclei_result.findings = [vuln]
        nuclei_result.to_dict.return_value = {
            "scanner": "nuclei", "status": "COMPLETED", "exit_code": 0,
            "finding_count": 1, "target": "http://127.0.0.1:9191",
        }
        monkeypatch.setattr(scanner_service, "run_nmap_discovery", lambda *a, **k: nmap_result)
        monkeypatch.setattr(scanner_service, "run_nuclei_scan", lambda *a, **k: nuclei_result)

        req = VAPTRequest(
            scenario="web_target", mode="web", assessment_type="web",
            target_url="http://127.0.0.1:9191",
            use_nmap=True, use_nuclei=True,
            assessor_mode="deterministic", assessor_provider="ollama",
            max_attempts=2,
        )
        domain = get_application().run(req).domain
        assert len(domain.candidates) == 1
        cand = domain.candidates[0]
        vs = str(cand.get("validation_status", ""))
        # Scanner detection is discovery, not exploit proof.
        assert vs != "VALIDATED"
        assert "NOT AVAILABLE" in vs.upper() or "NOT AVAILABLE" in vs.upper() or "not available" in vs.lower()
        assert "SCANNER" in vs.upper() or "NOT AVAILABLE" in vs.upper() or "not available" in vs.lower()
        # Engine outcome SUCCESS must not be conflated with validation.
        assert cand.get("validation_status") != cand.get("execution_outcome")
    finally:
        from vapt_platform.persistence.repository import JSONRunRepository, set_repository

        set_repository(JSONRunRepository())
        shutil.rmtree(repo_dir, ignore_errors=True)


def test_simulated_run_semantics():
    """Simulation demo run → SIMULATED validation, SIMULATED evidence, honest notice."""
    from vapt_platform.application import VAPTRequest, get_application

    repo_dir = _isolated_repo()
    try:
        req = VAPTRequest(scenario="success", mode="simulation", assessor_mode="deterministic")
        # 'success' may not exist; fall back to a known demo scenario.
        try:
            domain = get_application().run(req).domain
        except ValueError:
            req.scenario = "failure_pivot"
            domain = get_application().run(req).domain
        assert domain.evidence_tier == "SIMULATED"
        assert "No real vulnerabilities were validated" in domain.safety_notice
        for c in domain.candidates:
            if isinstance(c, dict):
                assert str(c.get("validation_status", "")) == "SIMULATED"
    finally:
        from vapt_platform.persistence.repository import JSONRunRepository, set_repository

        set_repository(JSONRunRepository())
        shutil.rmtree(repo_dir, ignore_errors=True)


def test_docker_observed_run_semantics(monkeypatch):
    """Lab/Docker run → DOCKER_OBSERVED evidence/validation, never real-world claim."""
    from unittest.mock import MagicMock, patch

    from vapt_platform.application import VAPTApplication, VAPTRequest

    repo_dir = _isolated_repo()
    try:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            outcome="SUCCESS",
            request_count=1,
            detail="docker-observed(VULNERABLE)",
        )
        app = VAPTApplication()
        req = VAPTRequest(
            scenario="docker_vuln", mode="lab", target="172.28.0.2",
            port=8080, path="/vuln", max_attempts=2,
            assessor_mode="deterministic",
        )
        with patch.object(app, "_build_executor", return_value=mock_executor):
            domain = app.run(req).domain
        assert domain.evidence_tier == "DOCKER_OBSERVED"
        for c in domain.candidates:
            if isinstance(c, dict):
                assert str(c.get("validation_status", "")) == "DOCKER_OBSERVED"
                # Emulator observation is not real-world exploit proof.
                assert str(c.get("validation_status", "")) != "VALIDATED"
        # Never presented as real-world validated exploit.
        assert "CONTROLLED VALIDATION" not in domain.evidence_tier
    finally:
        from vapt_platform.persistence.repository import JSONRunRepository, set_repository

        set_repository(JSONRunRepository())
        shutil.rmtree(repo_dir, ignore_errors=True)


def test_reports_preserve_validation_semantics(monkeypatch):
    """ReportBuilder JSON/MD/TXT/HTML preserve per-finding validation + evidence."""
    import vapt_platform.scanner_service as scanner_service
    import vapt_platform.web_target as web_target
    from vapt_platform.application import VAPTRequest, get_application
    from vapt_platform.normalization import from_nuclei_finding
    from vapt_platform.parsers.nuclei_parser import NucleiFinding
    from vapt_platform.reporting.builder import ReportBuilder

    repo_dir = _isolated_repo()
    try:
        vuln = from_nuclei_finding(NucleiFinding(
            template_id="CVE-2021-44228", name="Apache Log4j RCE (JNDI)",
            severity="critical", target="http://127.0.0.1:9191", host="127.0.0.1",
        ))
        monkeypatch.setattr(
            web_target, "preflight_web_target",
            lambda _url, timeout=5.0: {
                "target_url": "http://127.0.0.1:9191",
                "resolved_host": "127.0.0.1", "port": 9191,
                "authorization_status": "AUTHORIZED",
                "preflight_status": "TARGET REACHABLE",
                "reachable": True, "http_status": 200, "detail": "HTTP 200 (mocked)",
            },
        )
        nmap_result = MagicMock()
        nmap_result.findings = []
        nmap_result.to_dict.return_value = {"scanner": "nmap", "status": "COMPLETED"}
        nuclei_result = MagicMock()
        nuclei_result.findings = [vuln]
        nuclei_result.to_dict.return_value = {"scanner": "nuclei", "status": "COMPLETED"}
        monkeypatch.setattr(scanner_service, "run_nmap_discovery", lambda *a, **k: nmap_result)
        monkeypatch.setattr(scanner_service, "run_nuclei_scan", lambda *a, **k: nuclei_result)

        req = VAPTRequest(
            scenario="web_target", mode="web", assessment_type="web",
            target_url="http://127.0.0.1:9191",
            use_nmap=True, use_nuclei=True, assessor_mode="deterministic",
        )
        app = get_application()
        result = app.run(req)
        builder = ReportBuilder()
        report = builder.from_domain_result(result.domain, req, {})
        d = report.to_dict()
        assert len(d["candidates"]) == 1
        assert "NOT AVAILABLE" in d["candidates"][0]["validation_status"].upper()
        assert d["candidates"][0]["validation_status"] != "VALIDATED"
        assert d["evidence_tier"] == "OBSERVED_LOCAL"

        # Rendered formats carry the same honest wording, never VALIDATED.
        for fmt in ("json", "markdown", "txt", "html"):
            rendered = app.generate_report(result.domain.run_id, fmt)
            assert "VALIDATED" not in rendered or "No real vulnerabilities were validated" in rendered or "VALIDATION NOT AVAILABLE" in rendered
        md = app.generate_report(result.domain.run_id, "markdown")
        assert "Validation Status" in md
        txt = app.generate_report(result.domain.run_id, "txt")
        assert "Validation Status" in txt
    finally:
        from vapt_platform.persistence.repository import JSONRunRepository, set_repository

        set_repository(JSONRunRepository())
        shutil.rmtree(repo_dir, ignore_errors=True)


def test_ui_text_matches_backend_state():
    """Frontend mirrors backend: neutral VALIDATION unless VALIDATED; no green-wash."""
    import pathlib

    js = pathlib.Path("frontend/web/js/app.js").read_text(encoding="utf-8")
    # Pipeline VALIDATION must not be unconditionally green: the only green
    # VALIDATION path is guarded by genuine VALIDATED backend state.
    assert "webStageNeutral('VALIDATION'" in js
    assert "NOT AVAILABLE (scanner-detected)" in js
    green_uses = [m.start() for m in re.finditer(r"webStage\(true, 'VALIDATION'", js)]
    assert len(green_uses) == 1, "exactly one green VALIDATION path (genuine VALIDATED only)"
    window = js[max(0, green_uses[0] - 600):green_uses[0]]
    assert "validated" in window.lower() and "VALIDATED" in window
    # Genuine VALIDATED is the only green path.
    assert "isValidatedStatus" in js
    # SafetyGate wording must not imply vuln validation.
    assert "SafetyGate validated" not in js
    assert "SafetyGate authorized" in js
    # Findings views expose backend validation_status explicitly.
    assert "Validation Status" in js
    assert "validationBadgeClass" in js
    # Case-insensitive NOT AVAILABLE handling (covers SIMULATED-OUTCOME lowercase).
    assert "function validationSummary" in js
    assert "isValidatedStatus(c.validation_status)" in js
    assert js.count(".toUpperCase()") >= 3
