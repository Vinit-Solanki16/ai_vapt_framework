"""FIX 7 — honest web-assessment scan status/progress (frontend only).

Status source is recorded backend data (no new architecture):
  web context ``preflight`` (reachable/http_status/detail) +
  nmap/nuclei ``ScanResult.to_dict()`` (status, exit_code, finding_count,
  duration_s, detail) + ``pipeline_s`` totals.

Rules enforced here:
  - a stage is COMPLETED only for recorded status exactly 'COMPLETED';
  - unavailable/failure/timeout render their recorded status + detail,
    never a green ✓;
  - no percentages anywhere (no progress measurement exists);
  - no WebSockets; the only live element is a wall-clock elapsed timer
    during the in-flight synchronous request (measured time, not
    fabricated stage progress).
"""
from __future__ import annotations

import pathlib
import re
import shutil
import tempfile
from unittest.mock import MagicMock

APP_JS = pathlib.Path("frontend/web/js/app.js")


def _js() -> str:
    return APP_JS.read_text(encoding="utf-8")


def _mock_preflight_ok(monkeypatch):
    import vapt_platform.web_target as web_target

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


def _scan_result(scanner, status, detail="", duration=1.5, findings=None, exit_code=0):
    import vapt_platform.scanner_service as scanner_service

    n = len(findings or [])
    res = scanner_service.ScanResult(
        scanner=scanner,
        target="http://127.0.0.1:9191",
        command=[scanner],
        start_time="2026-01-01T00:00:00+00:00",
        end_time="2026-01-01T00:00:01+00:00",
        duration_s=duration,
        output_path=f"/tmp/{scanner}.out",
        exit_code=exit_code,
        finding_count=n,
        status=status,
        detail=detail or f"{scanner} {status.lower()} (mocked).",
        findings=list(findings or []),
    )
    return res


def _isolated_repo():
    from vapt_platform.persistence.config import PersistenceConfig
    from vapt_platform.persistence.repository import JSONRunRepository, set_repository

    repo_dir = tempfile.mkdtemp()
    set_repository(JSONRunRepository(config=PersistenceConfig(storage_dir=repo_dir)))
    return repo_dir


def test_status_source_records_scanner_state():
    """Backend web context records per-scanner status/duration/counts."""
    import vapt_platform.scanner_service as scanner_service
    from vapt_platform.application import VAPTRequest, get_application
    from vapt_platform.scanners import NmapXmlAdapter
    from pathlib import Path as _P

    from vapt_platform.persistence.repository import JSONRunRepository, set_repository

    repo_dir = _isolated_repo()
    try:
        import vapt_platform.web_target as web_target
        from unittest.mock import patch

        findings = NmapXmlAdapter().parse(
            str(_P(__file__).resolve().parent.parent / "data" / "juice_shop_nmap.xml")
        )
        nmap = _scan_result("nmap", "COMPLETED", duration=2.5, findings=findings)
        nuclei = _scan_result("nuclei", "NOT AVAILABLE",
                              "Nuclei executable not found on PATH.")
        with patch.object(web_target, "preflight_web_target", lambda _u, timeout=5.0: {
            "target_url": "http://127.0.0.1:9191", "resolved_host": "127.0.0.1",
            "port": 9191, "authorization_status": "AUTHORIZED",
            "preflight_status": "TARGET REACHABLE", "reachable": True,
            "http_status": 200, "detail": "HTTP 200 (mocked)",
        }), patch.object(scanner_service, "run_nmap_discovery", lambda *a, **k: nmap), \
            patch.object(scanner_service, "run_nuclei_scan", lambda *a, **k: nuclei):
            req = VAPTRequest(
                scenario="web_target", mode="web", assessment_type="web",
                target_url="http://127.0.0.1:9191",
                use_nmap=True, use_nuclei=True, assessor_mode="deterministic",
            )
            get_application().run(req)
            web = req._web_context
        assert web["nmap"]["status"] == "COMPLETED"
        assert web["nmap"]["finding_count"] == len(findings)
        assert web["nmap"]["duration_s"] == 2.5
        assert web["nuclei"]["status"] == "NOT AVAILABLE"
        assert web["preflight"]["reachable"] is True
        assert isinstance(web["pipeline_s"], float)
    finally:
        set_repository(JSONRunRepository())
        shutil.rmtree(repo_dir, ignore_errors=True)


def test_nmap_completed_representation():
    js = _js()
    assert "function renderScanStatusPanel" in js
    assert "Nmap discovery" in js
    assert "finding_count" in js
    assert "duration_s" in js
    assert "pipeline_s" in js


def test_nuclei_completed_representation():
    js = _js()
    assert "Nuclei scan" in js
    # Findings + elapsed come from recorded fields, not invented values.
    assert "Findings" in js
    assert "Elapsed" in js


def test_scanner_unavailable_never_shows_completed():
    js = _js()
    assert "NOT AVAILABLE" in js
    assert "SKIPPED" in js
    # Only an exact recorded 'COMPLETED' earns the green badge.
    m = re.search(r"function scannerStatusBadge\(status\) \{(.+?)\n\}", js, re.S)
    assert m, "scannerStatusBadge must exist"
    body = m.group(1)
    assert "=== 'COMPLETED'" in body
    assert "NOT AVAILABLE" in body


def test_scanner_failure_and_timeout_surface_detail():
    js = _js()
    assert "✗ FAILED" in js
    # Failure/timeout detail text from the backend is rendered verbatim.
    assert "scan.detail" in js
    # Legacy runs without recorded data admit it instead of inventing it.
    assert "not recorded for this run" in js


def test_no_fake_progress():
    js = _js()
    assert "73%" not in js
    assert "new WebSocket" not in js and "WebSocket(" not in js
    # The single interval is the wall-clock elapsed timer only: it writes
    # elapsed seconds and touches no stage/status state.
    intervals = re.findall(r"setInterval\((.+?)\n\s*\}, \d+\)", js, re.S)
    assert len(intervals) == 1, f"expected exactly one timer, found {len(intervals)}"
    assert "vapt-elapsed" in intervals[0]
    assert "status" not in intervals[0].lower()
    # No percentage rendering in the scan-status panel.
    panel = js[js.index("function renderScanStatusPanel"):js.index(
        "function renderWebRunDetails")]
    assert "%" not in panel
    # In-flight copy disclaims stage-level progress explicitly.
    assert "no per-stage" in js.lower() or "No per-stage" in js


def test_elapsed_uses_recorded_durations_with_na_fallback():
    js = _js()
    assert "function formatDurationSec" in js
    assert "'N/A'" in js
