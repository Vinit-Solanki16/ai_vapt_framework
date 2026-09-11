"""Frontend smoke tests."""
from __future__ import annotations

import pytest


class TestFrontendImport:
    def test_frontend_imports(self):
        """Verify frontend/app.py imports without error."""
        import frontend.app

    def test_frontend_uses_application(self):
        """Verify frontend imports the canonical VAPTApplication."""
        from frontend.app import get_application
        from vapt_platform.application import VAPTApplication
        app = get_application()
        assert isinstance(app, VAPTApplication)

    def test_frontend_no_free_text_target(self):
        """Verify frontend code has no free-text target input."""
        import inspect
        from frontend import app
        source = inspect.getsource(app)
        # Target must use selectbox, not text_input
        # The GUI should not allow arbitrary target input
        lines = source.split('\n')
        for line in lines:
            if 'st.text_input' in line and 'target' in line.lower():
                pytest.fail(f"Found free-text target input: {line}")
        # If we get here, no text_input for target was found
        assert True
