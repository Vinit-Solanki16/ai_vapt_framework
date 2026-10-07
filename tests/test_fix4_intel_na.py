"""FIX 4 — distinguish "no intelligence data" from numeric zero.

Backend source of truth is ``CanonicalFinding.metadata``:
  - missing CVE → ``epss_score=None``, ``cisa_kev=None`` (unavailable,
    never fabricated 0.0/False); scanner-observed CVSS/CWE preserved.
  - unknown CVE → existing documented provider behavior
    (``get_epss`` 0.0 default, ``is_in_kev`` bool, ``get_cvss`` None).
  - real numeric (including true 0.0) stays numeric via ``!= null``
    display checks; scoring still coalesces None → 0.0
    (``float(... or 0.0)``), so ranking semantics are unchanged.

UI uses the existing 'N/A' convention; no frontend scoring logic added;
sorting unaffected (tables have no sort; backend ranking untouched).
"""
from __future__ import annotations

import json
import pathlib


def test_missing_cve_epss_unavailable():
    """No CVE → EPSS/KEV unavailable (None), not artificial zero/False."""
    from vapt_platform.enrichment import enrich_finding
    from vapt_platform.normalization import CanonicalFinding

    f = CanonicalFinding(
        finding_id="no-cve-1",
        source="nuclei",
        title="Wappalyzer Technology Detection",
        severity="informational",
        rule_id="tech-detect",
        tags=["tech", "discovery"],
        metadata={},
    )
    out = enrich_finding(f)
    assert out.metadata["epss_score"] is None
    assert out.metadata["cisa_kev"] is None
    assert out.metadata["cvss_score"] is None
    assert out.metadata["cwe_ids"] == []
    # Scoring coalescing still yields 0.0 (ranking unchanged).
    assert float(out.metadata.get("epss_score", 0.0) or 0.0) == 0.0


def test_missing_cve_preserves_scanner_observed_intel():
    """Scanner-observed CVSS/CWE without CVE stay numeric/present."""
    from vapt_platform.enrichment import enrich_finding
    from vapt_platform.normalization import CanonicalFinding

    f = CanonicalFinding(
        source="nuclei",
        title="Prometheus Metrics - Detect",
        severity="medium",
        rule_id="prometheus-metrics",
        metadata={"cvss_score": 5.3, "cwe_ids": ["CWE-200"]},
    )
    out = enrich_finding(f)
    assert out.metadata["epss_score"] is None
    assert out.metadata["cisa_kev"] is None
    assert out.metadata["cvss_score"] == 5.3
    assert out.metadata["cwe_ids"] == ["CWE-200"]


def test_unknown_cve_existing_documented_behavior():
    """CVE present but unknown to datasets → provider defaults (unchanged)."""
    from vapt_platform.enrichment import LocalDatasetProvider, enrich_finding
    from vapt_platform.normalization import CanonicalFinding

    provider = LocalDatasetProvider()
    # Documented: unknown key → 0.0, not-in-KEV → False, no CVSS dataset → None.
    assert provider.get_epss("CVE-9999-00000") == 0.0
    assert provider.is_in_kev("CVE-9999-00000") is False
    assert provider.get_cvss("CVE-9999-00000") is None

    f = CanonicalFinding(rule_id="CVE-9999-00000", metadata={})
    out = enrich_finding(f, provider=provider)
    assert out.metadata["epss_score"] == 0.0
    assert out.metadata["cisa_kev"] is False


def test_real_epss_numeric_remains_numeric_and_true_zero_preserved():
    """Real scores (incl. explicit 0.0) stay numeric, never converted to N/A."""
    from vapt_platform.enrichment import enrich_finding
    from vapt_platform.normalization import CanonicalFinding

    f = CanonicalFinding(
        rule_id="CVE-2021-44228", metadata={"cve_ids": ["CVE-2021-44228"]}
    )
    out = enrich_finding(f)
    assert isinstance(out.metadata["epss_score"], float)
    assert out.metadata["epss_score"] > 0.9  # real corpus value

    # True 0.0 from an explicit source stays 0.0 (display: "EPSS 0", not N/A).
    class ZeroProvider:
        def get_epss(self, cve_id):
            return 0.0

        def is_in_kev(self, cve_id):
            return False

        def get_cvss(self, cve_id):
            return 0.0

        def get_cwe_ids(self, cve_id):
            return []

    g = CanonicalFinding(rule_id="CVE-2021-44228", metadata={})
    gout = enrich_finding(g, provider=ZeroProvider())
    assert gout.metadata["epss_score"] == 0.0
    assert gout.metadata["epss_score"] is not None
    assert gout.metadata["cvss_score"] == 0.0


def test_ui_renders_na_rather_than_misleading_zero():
    """Frontend uses explicit N/A; numeric checks preserve true 0.0."""
    js = pathlib.Path("frontend/web/js/app.js").read_text(encoding="utf-8")
    # Single intel display helper with explicit N/A per field.
    assert "function intelDisplay(md)" in js
    assert "EPSS N/A" in js
    assert "CVSS N/A" in js
    assert "KEV N/A" in js
    assert "CWE N/A" in js
    # Null-safe numeric checks (true 0.0 renders as 0, not N/A).
    assert "m.epss_score != null" in js
    assert "m.cvss_score != null" in js
    assert "intelDisplay(md)" in js
    # Old misleading patterns are gone.
    assert "md.epss_score != null ? 'EPSS ' + md.epss_score : null" not in js
    assert "${data.epss || 'N/A'}" not in js
    assert "data.epss != null ? data.epss : 'N/A'" in js
    assert "data.cvss != null ? data.cvss : 'N/A'" in js
    # KEV distinguishes yes / known-no / unavailable.
    assert "KEV yes" in js
    assert "KEV no" in js


def test_report_renders_same_semantics(monkeypatch):
    """Domain metadata None survives to API JSON (null); scoring unaffected."""
    import vapt_platform.scanner_service as scanner_service
    import vapt_platform.web_target as web_target
    from unittest.mock import MagicMock

    from vapt_platform.application import VAPTRequest, get_application
    from vapt_platform.normalization import from_nuclei_finding
    from vapt_platform.parsers.nuclei_parser import NucleiFinding

    from vapt_platform.persistence.config import PersistenceConfig
    from vapt_platform.persistence.repository import JSONRunRepository, set_repository
    import shutil
    import tempfile

    repo_dir = tempfile.mkdtemp()
    set_repository(JSONRunRepository(config=PersistenceConfig(storage_dir=repo_dir)))
    try:
        vuln = from_nuclei_finding(NucleiFinding(
            template_id="tech-detect",
            name="Wappalyzer Technology Detection",
            severity="info",
            target="http://127.0.0.1:9191",
            host="127.0.0.1",
            tags=["tech", "discovery"],
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
        domain = get_application().run(req).domain
        # Informational finding preserved in inventory with unavailable intel.
        assert domain.service_discovery, "inventory must preserve the finding"
        md = domain.service_discovery[0].get("metadata", {})
        assert md.get("epss_score") is None
        assert md.get("cisa_kev") is None
        # JSON serialization keeps null (not 0/false).
        raw = json.dumps(domain.service_discovery[0])
        assert '"epss_score": null' in raw
        assert '"cisa_kev": null' in raw
        # Scoring path still treats missing as 0 (ranking unchanged).
        assert float(md.get("epss_score", 0.0) or 0.0) == 0.0
    finally:
        set_repository(JSONRunRepository())
        shutil.rmtree(repo_dir, ignore_errors=True)
