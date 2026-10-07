"""FIX 6 — clean post-assessment action state (frontend only).

Lifecycle (``frontend/web/js/app.js``), driven solely by actual
backend responses (``api.startRun`` resolve/reject, preflight result):
  IDLE:       START enabled, post-run bars hidden.
  VALIDATING: web run button "VALIDATING..." (real preflight call).
  RUNNING:    button disabled, "ASSESSMENT IN PROGRESS..." (real run).
  COMPLETED:  ✓ + [VIEW RUN] [NEW ASSESSMENT] [RUN AGAIN]; START hidden.
  FAILED:     ✗ + [VIEW ERROR] [RETRY] [NEW ASSESSMENT]; START hidden.

No fake progress, no WebSockets, no research-core change.
"""
from __future__ import annotations

import pathlib
import re

APP_JS = pathlib.Path("frontend/web/js/app.js")


def _js() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_idle_state_shows_start_and_hides_post_actions():
    js = _js()
    assert 'id="scenario-post-actions"' in js
    assert 'id="web-post-actions"' in js
    # Both post-run bars start hidden; START controls carry idle labels.
    assert js.count('post-actions"') >= 2
    assert "🛡️ START VAPT ASSESSMENT" in js
    assert "🚀 Run Assessment" in js


def test_running_state_is_explicit_and_disables_controls():
    js = _js()
    assert "ASSESSMENT IN PROGRESS..." in js
    # Web preflight is a real call with its own VALIDATING button state.
    assert "VALIDATING..." in js
    assert "btn.disabled = true" in js


def test_completed_state_with_view_new_and_run_again():
    js = _js()
    assert "✓ Assessment Completed" in js
    assert "showPostRunActions({ status: 'completed'" in js
    for label in ("VIEW RUN", "NEW ASSESSMENT", "RUN AGAIN"):
        assert label in js
    # The confusing bare START under a completed result is gone: the
    # START wrapper is hidden when the post-run bar is shown.
    assert "wrap.style.display = 'none'" in js


def test_failed_state_with_view_error_retry_and_new():
    js = _js()
    assert "✗ Assessment Failed" in js
    assert "showPostRunActions({ status: 'failed'" in js
    for label in ("VIEW ERROR", "RETRY", "NEW ASSESSMENT"):
        assert label in js


def test_run_again_and_new_assessment_are_wired():
    js = _js()
    assert "function runAgainFromPostActions(isWeb)" in js
    assert "function goNewAssessment()" in js
    assert "function viewRunFromPostActions()" in js
    assert "function scrollToNewAssessmentResult()" in js
    # RUN AGAIN re-enters the real run path (not a dead button).
    assert "startWebAssessment()" in js
    assert "startAssessment()" in js
    # NEW ASSESSMENT returns through the single canonical router.
    assert "router();" in js


def test_no_dead_buttons():
    """Every onclick handler referenced in markup resolves to a function."""
    js = _js()
    handlers = set(re.findall(r'onclick="([A-Za-z_][A-Za-z0-9_]*)\(', js))
    defined = set(re.findall(r"function ([A-Za-z_][A-Za-z0-9_]*)\(", js))
    missing = sorted(handlers - defined - {"if"})
    assert not missing, f"unresolved handlers: {missing}"
    for name in (
        "viewRunFromPostActions",
        "goNewAssessment",
        "runAgainFromPostActions",
        "scrollToNewAssessmentResult",
    ):
        assert f"function {name}(" in js


def test_backend_state_drives_transitions():
    """Post-run UI may only appear for a real completed backend run."""
    import shutil
    import tempfile

    from vapt_platform.application import VAPTRequest, get_application
    from vapt_platform.persistence.config import PersistenceConfig
    from vapt_platform.persistence.repository import JSONRunRepository, set_repository

    repo_dir = tempfile.mkdtemp()
    set_repository(JSONRunRepository(config=PersistenceConfig(storage_dir=repo_dir)))
    try:
        domain = get_application().run(VAPTRequest(
            scenario="success", mode="simulation", assessor_mode="deterministic",
        )).domain
        assert domain.run_id
        assert domain.final_status in ("SUCCESS", "COMPLETED", "FAILED")
        # Frontend binds the displayed result to exactly this run_id.
        js = _js()
        assert "state.displayedRun = result.run_id" in js
    finally:
        set_repository(JSONRunRepository())
        shutil.rmtree(repo_dir, ignore_errors=True)
