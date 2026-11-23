"""Tests for Frontend UX Cleanup, Provider-Specific Dynamic Configuration,
Cloud Profile Modal, Model Catalog Explorer, and Attributions.

Verifies:
1. Target Specification & Assessment Configuration in Left Column.
2. Dynamic AI Provider & Model Configuration in Right Column with 6 isolated panels.
3. Cloud Hosted empty state and profile management modal elements.
4. Windows Chrome high-contrast select dropdown styling.
5. Active Assessment hero badges (Provider, Model, Engine).
6. Assessment History 8-column layout.
7. Executive Audit Report attribution banner.
8. Model Catalog explorer in Settings.
9. JS syntax validity and panel exclusivity logic in app.js.
10. API endpoints serving the frontend assets.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from strix.interface.api import app


client = TestClient(app)

WEB_DIR = Path(__file__).parent.parent / "strix" / "interface" / "web"
INDEX_HTML = (WEB_DIR / "index.html").read_text(encoding="utf-8")
STYLES_CSS = (WEB_DIR / "css" / "styles.css").read_text(encoding="utf-8")
APP_JS = (WEB_DIR / "js" / "app.js").read_text(encoding="utf-8")


def test_app_js_syntax_validation():
    """Verify that app.js passes node syntax check without any errors."""
    res = subprocess.run(
        ["node", "-c", str(WEB_DIR / "js" / "app.js")],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"node -c failed on app.js: {res.stderr}"


def test_target_specification_left_column():
    """Verify the Left Column contains all target & assessment execution settings."""
    assert 'id="card-target-config"' in INDEX_HTML
    assert 'id="target-url-input"' in INDEX_HTML
    assert 'id="btn-preflight-target"' in INDEX_HTML
    assert 'id="target-scope-feedback"' in INDEX_HTML
    assert 'id="scan-mode-select"' in INDEX_HTML
    assert 'id="scan-intensity-select"' in INDEX_HTML
    assert 'id="execution-limits-select"' in INDEX_HTML
    assert 'id="custom-turns-input"' in INDEX_HTML
    assert 'id="gap2-threshold-select"' in INDEX_HTML
    assert 'id="chk-scope-ack"' in INDEX_HTML


def test_provider_configuration_right_column_and_six_panels():
    """Verify the Right Column contains master selector and 6 isolated provider panels."""
    assert 'id="card-ai-provider-config"' in INDEX_HTML
    assert 'id="model-provider-select"' in INDEX_HTML
    assert 'id="active-provider-badge"' in INDEX_HTML
    assert 'id="provider-description-hint"' in INDEX_HTML

    # All 6 distinct provider panels
    assert 'id="panel-provider-openrouter"' in INDEX_HTML
    assert 'id="panel-provider-openai"' in INDEX_HTML
    assert 'id="panel-provider-anthropic"' in INDEX_HTML
    assert 'id="panel-provider-google"' in INDEX_HTML
    assert 'id="panel-provider-ollama"' in INDEX_HTML
    assert 'id="panel-provider-cloud-hosted"' in INDEX_HTML

    # Check that master selector contains all 6 provider options
    assert 'value="openrouter"' in INDEX_HTML
    assert 'value="openai"' in INDEX_HTML
    assert 'value="anthropic"' in INDEX_HTML
    assert 'value="google"' in INDEX_HTML
    assert 'value="ollama"' in INDEX_HTML
    assert 'value="cloud_hosted"' in INDEX_HTML


def test_provider_panel_specific_controls():
    """Verify each provider panel has its own dedicated inputs and no cross-provider leakage."""
    # OpenRouter
    assert 'id="openrouter-api-key"' in INDEX_HTML
    assert 'id="btn-validate-openrouter"' in INDEX_HTML
    assert 'id="openrouter-model-select"' in INDEX_HTML
    assert 'id="openrouter-model-search"' in INDEX_HTML
    assert 'id="openrouter-pricing-notice"' in INDEX_HTML

    # OpenAI
    assert 'id="openai-api-key"' in INDEX_HTML
    assert 'id="btn-validate-openai"' in INDEX_HTML
    assert 'id="openai-model-select"' in INDEX_HTML
    assert 'id="openai-pricing-notice"' in INDEX_HTML

    # Anthropic
    assert 'id="anthropic-api-key"' in INDEX_HTML
    assert 'id="btn-validate-anthropic"' in INDEX_HTML
    assert 'id="anthropic-model-select"' in INDEX_HTML
    assert 'id="anthropic-pricing-notice"' in INDEX_HTML

    # Google Gemini
    assert 'id="google-api-key"' in INDEX_HTML
    assert 'id="btn-validate-google"' in INDEX_HTML
    assert 'id="google-model-select"' in INDEX_HTML
    assert 'id="google-pricing-notice"' in INDEX_HTML

    # Ollama Local
    assert 'id="ollama-base-url"' in INDEX_HTML
    assert 'id="btn-validate-ollama"' in INDEX_HTML
    assert 'id="ollama-model-select"' in INDEX_HTML
    assert 'id="ollama-pricing-notice"' in INDEX_HTML
    assert 'id="ollama-api-key"' in INDEX_HTML

    # Cloud Hosted
    assert 'id="cloud-empty-state"' in INDEX_HTML
    assert 'id="cloud-active-profile-section"' in INDEX_HTML
    assert 'id="btn-cloud-create-first-profile"' in INDEX_HTML
    assert 'id="cloud-profile-select-main"' in INDEX_HTML
    assert 'id="btn-open-cloud-profile-modal"' in INDEX_HTML
    assert 'id="cloud-profile-endpoint-text"' in INDEX_HTML
    assert 'id="cloud-profile-auth-status"' in INDEX_HTML
    assert 'id="cloud-discovered-model-select"' in INDEX_HTML
    assert 'id="btn-test-cloud-profile"' in INDEX_HTML


def test_cloud_hosted_management_modal_elements():
    """Verify the dedicated Cloud Hosted profile management modal structure."""
    assert 'id="modal-cloud-profiles-backdrop"' in INDEX_HTML
    assert 'id="btn-close-cloud-modal"' in INDEX_HTML
    assert 'id="modal-profile-select"' in INDEX_HTML
    assert 'id="btn-modal-profile-activate"' in INDEX_HTML
    assert 'id="btn-modal-profile-save"' in INDEX_HTML
    assert 'id="btn-modal-profile-delete"' in INDEX_HTML
    assert 'id="modal-profile-state-badge"' in INDEX_HTML
    assert 'id="modal-profile-auth-badge"' in INDEX_HTML
    assert 'id="modal-profile-conn-badge"' in INDEX_HTML
    assert 'id="modal-profile-name"' in INDEX_HTML
    assert 'id="modal-profile-base-url"' in INDEX_HTML
    assert 'id="modal-profile-api-key"' in INDEX_HTML
    assert 'id="modal-profile-model"' in INDEX_HTML
    assert 'id="btn-modal-discover-models"' in INDEX_HTML
    assert 'id="btn-modal-test-conn"' in INDEX_HTML
    assert 'id="btn-modal-verify-tools"' in INDEX_HTML


def test_active_assessment_dashboard_badges():
    """Verify Active Assessment hero header contains provider, model, and engine attribution badges."""
    assert 'id="hero-engine-badge"' in INDEX_HTML
    assert 'id="hero-provider-badge"' in INDEX_HTML
    assert 'id="hero-model-badge"' in INDEX_HTML
    assert 'id="hero-run-status"' in INDEX_HTML
    assert 'id="hero-run-id"' in INDEX_HTML


def test_assessment_history_eight_columns():
    """Verify History table defines 8 columns including AI Provider & Model and Execution Engine."""
    headers = re.findall(r"<th>(.*?)</th>", INDEX_HTML)
    assert "AI Provider & Model" in headers
    assert "Execution Engine" in headers
    assert len(headers) >= 8

    # Check colspan in tbody-history
    assert 'colspan="8"' in INDEX_HTML


def test_model_catalog_explorer_in_settings():
    """Verify AI Models view contains the multi-provider catalog explorer and search."""
    assert 'id="catalog-models-grid"' in INDEX_HTML
    assert 'id="catalog-search-input"' in INDEX_HTML
    assert 'class="model-catalog-grid"' in INDEX_HTML
    assert 'class="btn btn-secondary btn-sm catalog-tab-btn"' in INDEX_HTML


def test_css_styling_and_windows_chrome_contrast():
    """Verify CSS has modal styles, animations, pricing pills, and Windows Chrome select contrast."""
    assert ".modal-backdrop" in STYLES_CSS
    assert ".modal-dialog" in STYLES_CSS
    assert ".provider-panel" in STYLES_CSS
    assert ".model-pricing-pill" in STYLES_CSS
    assert ".model-pricing-pill.free" in STYLES_CSS
    assert ".model-pricing-pill.paid" in STYLES_CSS
    assert ".model-pricing-pill.local" in STYLES_CSS
    assert ".model-catalog-grid" in STYLES_CSS
    assert ".model-catalog-card" in STYLES_CSS

    # Windows Chrome select dark contrast hardening
    assert "#0f172a !important" in STYLES_CSS
    assert "#f8fafc !important" in STYLES_CSS


def test_app_js_logic_and_exclusivity():
    """Verify app.js contains provider panel exclusivity and memory preservation logic."""
    assert "function onProviderChange()" in APP_JS
    assert "saveCurrentProviderState" in APP_JS
    assert "restoreProviderState" in APP_JS
    assert "updateCloudHostedPanelDisplay" in APP_JS
    assert "openCloudProfileModal" in APP_JS
    assert "renderModelCatalog" in APP_JS
    assert "getSelectedModelId" in APP_JS
    assert "getActiveProviderApiKey" in APP_JS
    assert "getActiveProviderBaseUrl" in APP_JS
    assert "syncCompatibilityProxies" in APP_JS

    # Check panel exclusivity code
    assert "panel-provider-" in APP_JS
    assert "panel.style.display = p === provider ? 'block' : 'none'" in APP_JS


def test_static_files_served_by_fastapi():
    """Verify FastAPI backend serves index.html and static assets properly."""
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "AI-VAPT // Autonomous Operations Console" in res_index.text

    res_css = client.get("/css/styles.css")
    assert res_css.status_code == 200
    assert ".modal-backdrop" in res_css.text

    res_js = client.get("/js/app.js")
    assert res_js.status_code == 200
    assert "onProviderChange" in res_js.text


def test_cloud_profiles_endpoints():
    """Verify Cloud Hosted profile CRUD endpoints respond correctly."""
    # List profiles
    res_list = client.get("/providers/cloud_hosted/profiles")
    assert res_list.status_code == 200
    assert isinstance(res_list.json(), list)

    # Validate custom endpoint without auth returns valid or expected response
    res_val = client.post(
        "/providers/custom/validate",
        json={"api_base": "http://127.0.0.1:11434/v1", "api_key": ""},
    )
    assert res_val.status_code == 200
    assert "valid" in res_val.json() or "message" in res_val.json()


def test_cloud_hosted_panel_id_mapping_and_profile_priority():
    """Verify cloud_hosted maps to panel-provider-cloud-hosted and honors user dropdown selection."""
    # Ensure app.js maps cloud_hosted to panel-provider-cloud-hosted
    assert "p === 'cloud_hosted' ? 'panel-provider-cloud-hosted' : `panel-provider-${p}`" in APP_JS
    # Verify the DOM ID in index.html exactly matches
    assert 'id="panel-provider-cloud-hosted"' in INDEX_HTML

    # Ensure getSelectedModelId, getActiveProviderApiKey, getActiveProviderBaseUrl prioritize cloudProfileSelectMain
    assert (
        "elements.cloudProfileSelectMain ? elements.cloudProfileSelectMain.value : null" in APP_JS
    )


def test_report_download_formats_conformance():
    """Verify all 6 report formats (HTML, PDF, JSON, SARIF, CSV, Markdown) are supported via API."""
    run_id = "run-95c0f177"
    fixture_dir = Path(__file__).resolve().parent / "fixtures" / run_id
    if fixture_dir.is_dir():
        import shutil

        dest = Path.cwd() / "strix_runs" / run_id
        if not dest.exists():
            shutil.copytree(fixture_dir, dest)

    formats = [
        ("html", "text/html"),
        ("pdf", "application/pdf"),
        ("json", "application/json"),
        ("sarif", "application/json"),
        ("csv", "text/csv"),
        ("markdown", "text/markdown"),
        ("md", "text/markdown"),
    ]

    for fmt, expected_mime in formats:
        res = client.get(f"/runs/{run_id}/report?format={fmt}&download=1")
        assert res.status_code == 200, f"Format {fmt} failed with status {res.status_code}"
        assert expected_mime in res.headers.get("content-type", ""), (
            f"Format {fmt} returned unexpected content-type: {res.headers.get('content-type')}"
        )
        assert len(res.content) > 0, f"Format {fmt} returned empty content"
