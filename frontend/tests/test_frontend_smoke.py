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
        lines = source.split('\n')
        for line in lines:
            if 'st.text_input' in line and 'target' in line.lower():
                pytest.fail(f"Found free-text target input: {line}")
        assert True

    def test_frontend_has_professional_pages(self):
        """Verify frontend has all required professional pages."""
        import inspect
        from frontend import app
        source = inspect.getsource(app)

        required_pages = [
            "show_dashboard",
            "show_new_assessment",
            "show_run_history",
            "show_findings",
            "show_intelligence",
            "show_attack_paths",
            "show_reports",
            "show_system",
        ]

        for page in required_pages:
            assert page in source, f"Missing page function: {page}"

    def test_frontend_has_research_core_protection(self):
        """Verify frontend references research core protection."""
        import inspect
        from frontend import app
        source = inspect.getsource(app)
        assert "PROTECTED" in source or "Research Core" in source

    def test_frontend_has_evidence_tier_display(self):
        """Verify frontend displays evidence tiers."""
        import inspect
        from frontend import app
        source = inspect.getsource(app)
        assert "DOCKER_OBSERVED" in source
        assert "SIMULATED" in source
        assert "OBSERVED_LOCAL" in source

    def test_frontend_has_safety_status(self):
        """Verify frontend shows safety/authorization status."""
        import inspect
        from frontend import app
        source = inspect.getsource(app)
        assert "AUTHORIZED" in source or "ALLOWLISTED" in source
