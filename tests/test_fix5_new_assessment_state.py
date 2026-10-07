"""FIX 5 — New Assessment always starts from fresh configuration state.

Root cause (frontend only, ``frontend/web/js/app.js``):
  - The inline result lives in page-local DOM (``#run-result``) while the
    last run lives in global ``state.currentRun`` with nothing recording
    which run the displayed output belongs to.
  - Re-clicking "New Assessment" while already on ``#/assessment/new``
    does not change the hash, so no ``hashchange`` fires, ``router()``
    never re-runs, and the previous run's result stays on screen.
  - Editing the form after a completed run left the old result visible,
    mixing old output with new input.

Fix (no backend change, no persisted-data deletion):
  - ``state.displayedRun`` tracks the run_id shown in ``#run-result``.
  - Entering New Assessment resets it and renders the result hidden;
    a previous run is reachable only via an explicit "View Previous Run"
    link (history/API untouched).
  - Completing a run sets both ids to the NEW run_id (new result only).
  - Any form edit clears a stale inline result.
  - Same-hash nav clicks force a router re-run (fresh render).

Backend coverage below proves history retention + per-run selection
still work (old runs listed, individually fetchable, never mixed).
"""
from __future__ import annotations

import pathlib

APP_JS = pathlib.Path("frontend/web/js/app.js")


def _js() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_state_tracks_displayed_result_separately():
    js = _js()
    assert "displayedRun: null" in js
    assert "state.displayedRun" in js
    assert "state.currentRun" in js


def test_new_assessment_renders_fresh_without_previous_result():
    js = _js()
    # Entering the page resets the displayed-result binding ...
    assert "state.displayedRun = null" in js
    # ... and the inline result card starts hidden.
    assert 'id="run-result" style="display:none;"' in js
    # A previous run is offered only as an explicit link, never inline.
    assert "View Previous Run" in js
    assert 'id="previous-run-link"' in js
    assert "#/runs" in js


def test_completed_run_displays_only_the_new_result():
    js = _js()
    # Both run-start paths bind the displayed output to the NEW run_id.
    assert js.count("state.displayedRun = result.run_id") == 2


def test_form_edits_clear_stale_result():
    js = _js()
    assert "function clearStaleNewAssessmentResult" in js
    assert "if (state.displayedRun) clearStaleNewAssessmentResult(container)" in js
    # Clearing hides output; it never deletes persisted history.
    assert "displayedRun = null" in js
    assert "localStorage.clear" not in js
    assert "localStorage.removeItem" not in js


def test_same_hash_navigation_rerenders_fresh():
    js = _js()
    assert "window.location.hash === target" in js
    # The forced re-render goes through the single canonical router.
    assert js.count("router();") >= 2


def test_run_history_keeps_old_runs_and_selection_works():
    """Two runs → history holds both; each id resolves to its own result."""
    import shutil
    import tempfile

    from vapt_platform.application import VAPTRequest, get_application
    from vapt_platform.persistence.config import PersistenceConfig
    from vapt_platform.persistence.repository import JSONRunRepository, set_repository

    repo_dir = tempfile.mkdtemp()
    set_repository(JSONRunRepository(config=PersistenceConfig(storage_dir=repo_dir)))
    try:
        app = get_application()
        first = app.run(VAPTRequest(
            scenario="success", mode="simulation", assessor_mode="deterministic",
        )).domain
        second = app.run(VAPTRequest(
            scenario="success", mode="simulation", assessor_mode="deterministic",
        )).domain
        assert first.run_id != second.run_id

        from vapt_platform.persistence import get_repository

        repo = get_repository()
        ids = {r.run_id for r in repo.list_runs(limit=100)}
        assert first.run_id in ids
        assert second.run_id in ids

        old = repo.get(first.run_id)
        new = repo.get(second.run_id)
        assert old is not None and new is not None
        assert old.run_id == first.run_id
        assert new.run_id == second.run_id
        # Results are not mixed: each persisted run carries its own id.
        assert old.to_dict()["run_id"] != new.to_dict()["run_id"]
    finally:
        set_repository(JSONRunRepository())
        shutil.rmtree(repo_dir, ignore_errors=True)
