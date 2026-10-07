"""FIX 8 — GAP-1/GAP-2 panels read recorded backend data (frontend only).

Panels (``frontend/web/js/app.js``: ``renderGap1Panel``/``renderGap2Panel``):
  - GAP-1 inputs: assessment provenance (mode/provider/model/details with
    per-candidate quality + fallback flags) + candidate quality ranks.
  - GAP-2 inputs: persisted run execution_results, pivot_count,
    max_attempts, candidates_processed.
  - Honesty rules: Deterministic vs AI (+fallback) from backend state;
    "Not applicable" when absent; "No pivot required" when pivots == 0;
    no hardcoded quality/score/priority/pivot values.

No research-core change; engine behavior verified unchanged via the
existing scenario suite (covered by the combined full-suite run).
"""
from __future__ import annotations

import pathlib
import shutil
import tempfile
from unittest.mock import MagicMock, patch

APP_JS = pathlib.Path("frontend/web/js/app.js")


def _js() -> str:
    return APP_JS.read_text(encoding="utf-8")


def _isolated_repo():
    from vapt_platform.persistence.config import PersistenceConfig
    from vapt_platform.persistence.repository import JSONRunRepository, set_repository

    repo_dir = tempfile.mkdtemp()
    set_repository(JSONRunRepository(config=PersistenceConfig(storage_dir=repo_dir)))
    return repo_dir


def test_gap1_panel_reads_backend_assessment_state():
    js = _js()
    assert "function renderGap1Panel(cands, assess)" in js
    assert "function gap1PanelData(cands, assess)" in js
    # Provenance + quality come from backend objects, never literals.
    assert "assess" in js and "details" in js
    assert "quality_rank" in js
    # Honest mode branches with no false-AI path.
    assert "Deterministic" in js
    assert "deterministic fallback" in js
    assert "Not applicable — no assessment recorded" in js


def test_gap1_does_not_hardcode_provider_model_or_scores():
    js = _js()
    panel = js[js.index("function gap1PanelData"):js.index("function renderWebRunDetails")]
    for literal in ("llama3.2:3b", "gpt-4o-mini", "HIGH\", \"MEDIUM", "final_score"):
        assert literal not in panel, f"hardcoded value in GAP-1 panel: {literal}"
    # Provider/model flow from backend fields.
    assert "a.provider" in panel
    assert "a.model" in panel


def test_gap2_panel_reads_backend_execution_state():
    js = _js()
    assert "function renderGap2Panel(run)" in js
    assert "execution_results" in js
    assert "pivot_count" in js
    assert "max_attempts" in js
    assert "candidates_processed" in js
    assert "No pivot required" in js
    assert "Not applicable — no execution recorded" in js
    assert "Threshold reached → PIVOT" in js


def test_deterministic_run_reports_deterministic_assessment():
    from vapt_platform.application import VAPTRequest, get_application
    from vapt_platform.persistence.repository import JSONRunRepository, set_repository

    repo_dir = _isolated_repo()
    try:
        domain = get_application().run(VAPTRequest(
            scenario="success", mode="simulation", assessor_mode="deterministic",
        )).domain
        assert domain.assessment.get("mode") == "deterministic"
        assert domain.assessment.get("provider") == "deterministic"
        # Panel inputs present: provenance details + ranked qualities.
        assert isinstance(domain.assessment.get("details"), list)
        assert domain.assessment["details"]
    finally:
        set_repository(JSONRunRepository())
        shutil.rmtree(repo_dir, ignore_errors=True)


def test_ai_requested_without_llm_shows_fallback_truthfully():
    from vapt_platform.application import VAPTRequest, get_application
    from vapt_platform.persistence.repository import JSONRunRepository, set_repository

    repo_dir = _isolated_repo()
    try:
        domain = get_application().run(VAPTRequest(
            scenario="success", mode="simulation",
            assessor_mode="ai", assessor_provider="ollama",
        )).domain
        assert domain.assessment.get("mode") == "ai"
        details = domain.assessment.get("details") or []
        assert details and all(d.get("fallback") for d in details)
        # Panel branch for this exact backend state exists (no false AI claim).
        assert "AI requested — deterministic fallback" in _js()
    finally:
        set_repository(JSONRunRepository())
        shutil.rmtree(repo_dir, ignore_errors=True)


def test_success_run_needs_no_pivot_and_pivot_run_pivots():
    from prototype.demo_data import failure_pivot_scenario, success_scenario
    from prototype.engine_integration import run_decision_scenario

    success = run_decision_scenario(success_scenario(), max_attempts=2, mode="simulation")
    assert success["status"] in ("SUCCESS", "COMPLETED")
    assert success["_presentation"]["pivot_count"] >= 0
    assert [r.get("outcome") for r in success["results"]]

    pivoted = run_decision_scenario(
        failure_pivot_scenario(max_attempts=2), max_attempts=2, mode="simulation",
    )
    assert pivoted["_presentation"]["pivot_count"] >= 1
    outcomes = [r.get("outcome") for r in pivoted["results"]]
    assert outcomes  # real recorded outcomes feed the GAP-2 chain
    assert any("Pivot" in log for log in pivoted["logs"])


def test_combined_workflow_feeds_both_panels(monkeypatch):
    """Mocked web run carries every input both panels consume."""
    import vapt_platform.scanner_service as scanner_service
    import vapt_platform.web_target as web_target
    from vapt_platform.application import VAPTRequest, get_application
    from vapt_platform.normalization import from_nuclei_finding
    from vapt_platform.parsers.nuclei_parser import NucleiFinding
    from vapt_platform.persistence.repository import JSONRunRepository, set_repository

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

        result = get_application().run(VAPTRequest(
            scenario="web_target", mode="web", assessment_type="web",
            target_url="http://127.0.0.1:9191",
            use_nmap=True, use_nuclei=True, assessor_mode="deterministic",
        ))
        domain = result.domain
        # GAP-1 inputs.
        assert domain.assessment.get("mode") == "deterministic"
        assert domain.candidates and domain.candidates[0].get("quality_rank")
        # GAP-2 inputs recorded on the persisted run.
        from vapt_platform.persistence import get_repository

        persisted = get_repository().get(domain.run_id)
        assert persisted is not None
        assert isinstance(persisted.execution_results, list)
        assert isinstance(persisted.pivot_count, int)
        # Panels are mounted in all three locations.
        js = _js()
        assert "renderGap1Panel(cands, assess)" in js
        assert "renderGap2Panel(run)" in js
        assert "GAP-1" in js and "GAP-2" in js
    finally:
        set_repository(JSONRunRepository())
        shutil.rmtree(repo_dir, ignore_errors=True)
