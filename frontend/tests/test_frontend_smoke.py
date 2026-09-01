"""Frontend smoke tests (Phase 6)."""
from __future__ import annotations

import pytest


class TestFrontendImport:
    def test_frontend_imports(self):
        """Verify frontend/app.py imports without error."""
        import frontend.app

    def test_frontend_uses_real_engine(self):
        """Verify frontend imports the real decision engine."""
        from frontend.app import run_engine
        from decision_engine.core.engine import run_engine as real_run_engine
        assert run_engine is real_run_engine

    def test_frontend_no_free_text_target(self):
        """Verify frontend code has no free-text target input."""
        import inspect
        from frontend import app
        source = inspect.getsource(app)
        # No st.text_input for target
        assert 'st.text_input' not in source or 'target' not in source.lower()
