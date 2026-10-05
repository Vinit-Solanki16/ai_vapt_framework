"""Scanner execution service tests (Phase 32).

Uses mocks/fixtures only — no live nmap/nuclei processes, no network.
Verifies: safe argv construction, adapter parsing, graceful Nuclei absence,
and that scanners are NEVER invoked after authorization rejection.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import vapt_platform.scanner_service as svc
from vapt_platform.web_target import WebTargetAuthorizationError

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JUICE_XML = DATA_DIR / "juice_shop_nmap.xml"

NUCLEI_RECORD = {
    "template-id": "http-missing-security-headers",
    "type": "http",
    "host": "http://127.0.0.1:9191",
    "matched-at": "http://127.0.0.1:9191/",
    "info": {
        "name": "HTTP Missing Security Headers",
        "severity": "info",
        "tags": ["headers", "config"],
        "description": "Missing security headers detected",
        "reference": ["https://example.local/headers"],
        "classification": {"cwe-id": ["CWE-693"]},
    },
    "ip": "127.0.0.1",
    "timestamp": "2026-10-05T00:00:00Z",
    "matcher-status": True,
}


def _nmap_success_side_effect(xml_text: str):
    """Fake subprocess.run that materializes the -oX file like nmap would."""
    def _run(argv, **kwargs):
        assert isinstance(argv, list), "scanner must use argv list, never shell strings"
        assert "-oX" in argv
        out_path = argv[argv.index("-oX") + 1]
        Path(out_path).write_text(xml_text)
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = ""
        proc.stderr = ""
        return proc
    return _run


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def test_scanner_status_shape():
    status = svc.scanner_status()
    assert set(status) == {"nmap", "nuclei"}
    assert set(status["nmap"]) == {"scanner", "available", "path", "version"}


# ---------------------------------------------------------------------------
# Nmap discovery (mocked process + real fixture XML)
# ---------------------------------------------------------------------------

def test_nmap_discovery_parses_juice_shop_fixture(monkeypatch, tmp_path, offline_guard):
    xml_text = JUICE_XML.read_text()
    monkeypatch.setattr(subprocess, "run", _nmap_success_side_effect(xml_text))

    result = svc.run_nmap_discovery("http://127.0.0.1:9191", output_dir=str(tmp_path))

    assert result.status == "COMPLETED"
    assert result.exit_code == 0
    assert result.finding_count == 1
    finding = result.findings[0]
    assert finding.port == 9191
    assert finding.host == "127.0.0.1"
    assert finding.source == "nmap-xml"
    # Safe argv: list form, fixed profile, no shell.
    assert result.command[:4] == [result.command[0], "-Pn", "-sV", "-p"]
    assert "-oX" in result.command
    assert result.command[-1] == "127.0.0.1"
    assert result.output_path.endswith(".xml")
    assert result.start_time and result.end_time


def test_nmap_command_uses_resolved_host_for_localhost(monkeypatch, tmp_path, offline_guard):
    xml_text = JUICE_XML.read_text()
    monkeypatch.setattr(subprocess, "run", _nmap_success_side_effect(xml_text))
    result = svc.run_nmap_discovery("http://localhost:9191", output_dir=str(tmp_path))
    assert result.status == "COMPLETED"
    # localhost is passed as its resolved loopback IP to avoid DNS in scans.
    assert result.command[-1] == "127.0.0.1"


def test_nmap_never_invoked_after_authorization_rejection(offline_guard):
    with pytest.raises(WebTargetAuthorizationError):
        svc.run_nmap_discovery("https://example.com")
    assert offline_guard.call_count == 0


def test_nmap_never_invoked_for_public_ip(offline_guard):
    with pytest.raises(WebTargetAuthorizationError):
        svc.run_nmap_discovery("http://8.8.8.8:9191")
    assert offline_guard.call_count == 0


def test_nmap_not_available_graceful(monkeypatch):
    monkeypatch.setattr(svc.shutil, "which", lambda *_a, **_k: None)
    result = svc.run_nmap_discovery("http://127.0.0.1:9191")
    assert result.status == "NOT AVAILABLE"
    assert result.findings == []


# ---------------------------------------------------------------------------
# Nuclei scan (mocked process + JSONL fixture)
# ---------------------------------------------------------------------------

def _nuclei_success_side_effect(jsonl_text: str):
    def _run(argv, **kwargs):
        assert isinstance(argv, list)
        assert "-target" in argv
        assert "-jsonl" in argv
        out_path = argv[argv.index("-o") + 1]
        Path(out_path).write_text(jsonl_text)
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = ""
        proc.stderr = ""
        return proc
    return _run


def test_nuclei_jsonl_integration(monkeypatch, tmp_path, offline_guard):
    """Nuclei JSONL → parser → CanonicalFinding (existing adapter)."""
    from vapt_platform.scanners import NucleiAdapter

    jsonl_path = tmp_path / "nuclei.jsonl"
    jsonl_path.write_text(json.dumps(NUCLEI_RECORD) + "\n")

    findings = NucleiAdapter().parse(str(jsonl_path))
    assert len(findings) == 1
    f = findings[0]
    assert f.source == "nuclei"
    assert f.rule_id == "http-missing-security-headers"
    assert f.port == 9191
    assert f.metadata["cwe_ids"] == ["CWE-693"]


def test_nuclei_scan_controlled_profile(monkeypatch, tmp_path, offline_guard):
    monkeypatch.setattr(
        subprocess, "run",
        _nuclei_success_side_effect(json.dumps(NUCLEI_RECORD) + "\n"),
    )
    # Pretend nuclei is installed.
    monkeypatch.setattr(svc, "nuclei_status",
                        lambda: {"scanner": "nuclei", "available": True,
                                 "path": "/usr/bin/nuclei", "version": "v3"})
    # Pin the template scope (independent of this machine's ~/nuclei-templates).
    monkeypatch.setattr(svc, "nuclei_template_dirs", lambda: [str(tmp_path)])
    result = svc.run_nuclei_scan("http://127.0.0.1:9191", output_dir=str(tmp_path))
    assert result.status == "COMPLETED"
    assert result.finding_count == 1
    # Fixed safe profile: no user-controlled templates/flags.
    assert "-target" in result.command
    assert result.command[result.command.index("-target") + 1] == "http://127.0.0.1:9191"
    assert "-silent" in result.command
    assert "-t" in result.command


def test_nuclei_missing_templates_fails_closed(monkeypatch, tmp_path, offline_guard):
    monkeypatch.setattr(svc, "nuclei_status",
                        lambda: {"scanner": "nuclei", "available": True,
                                 "path": "/usr/bin/nuclei", "version": "v3"})
    monkeypatch.setattr(svc, "nuclei_template_dirs", lambda: [])
    result = svc.run_nuclei_scan("http://127.0.0.1:9191", output_dir=str(tmp_path))
    assert result.status == "FAILED"
    assert "update-templates" in result.detail
    assert offline_guard.call_count == 0


def test_nuclei_not_installed_is_not_available(monkeypatch):
    # Force the "not installed" path regardless of this machine's PATH.
    monkeypatch.setattr(svc.shutil, "which", lambda *_a, **_k: None)
    assert svc.nuclei_status()["available"] is False
    result = svc.run_nuclei_scan("http://127.0.0.1:9191")
    assert result.status == "NOT AVAILABLE"
    assert result.findings == []
    assert result.finding_count == 0


def test_nuclei_never_invoked_after_authorization_rejection(offline_guard):
    with pytest.raises(WebTargetAuthorizationError):
        svc.run_nuclei_scan("https://example.com")
    assert offline_guard.call_count == 0


# ---------------------------------------------------------------------------
# Real-artifact ingestion: Juice Shop JSONL → CanonicalFinding → enrich
# ---------------------------------------------------------------------------

JUICE_NUCLEI_JSONL = DATA_DIR / "scans" / "nuclei_127.0.0.1_9191.jsonl"


def test_real_juice_shop_jsonl_becomes_canonical_findings():
    """Real scanner output must flow through the EXISTING adapter only."""
    if not JUICE_NUCLEI_JSONL.exists():
        pytest.skip("live Nuclei artifact not present; run the controlled scan first")
    from vapt_platform import enrichment
    from vapt_platform.normalization import deduplicate
    from vapt_platform.scanners import NucleiAdapter

    findings = NucleiAdapter().parse(str(JUICE_NUCLEI_JSONL))
    assert len(findings) >= 1
    assert all(f.source == "nuclei" for f in findings)
    assert all(f.port == 9191 for f in findings)

    deduped = deduplicate(findings)
    assert 1 <= len(deduped) <= len(findings)

    enriched = enrichment.enrich_findings(deduped)
    assert len(enriched) == len(deduped)
    for f in enriched:
        assert "epss_score" in f.metadata
        assert "cisa_kev" in f.metadata
        assert "cwe_ids" in f.metadata


def test_nuclei_duplicate_templates_deduplicated():
    """Identical template hits on the same target collapse to one finding."""
    from vapt_platform.normalization import deduplicate, from_nuclei_finding
    from vapt_platform.parsers.nuclei_parser import NucleiParser

    line = json.dumps({**NUCLEI_RECORD, "matcher-name": "m1"})
    records = NucleiParser().parse(line + "\n" + line)
    assert len(records) == 2
    canonical = [from_nuclei_finding(r) for r in records]
    assert len(deduplicate(canonical)) == 1


def test_nuclei_minimal_record_missing_everything_optional():
    """A record with only template-id must still canonicalize safely."""
    from vapt_platform.normalization import from_nuclei_finding
    from vapt_platform.parsers.nuclei_parser import NucleiParser

    records = NucleiParser().parse(json.dumps({"template-id": "bare-template"}))
    assert len(records) == 1
    canonical = from_nuclei_finding(records[0])
    assert canonical.rule_id == "bare-template"
    assert canonical.severity == "unknown"
    assert canonical.port == 0
