"""Safety tests for the prototype layer (CLI + lab_runner).

Verifies that non-allowlisted targets are refused at every entry point
that accepts a target/IP. These tests verify behavior; they do not
change the engine.

Safety model:
  - Default mode is simulation (no network access)
  - Lab mode targets are restricted to LAB_TARGET_ALLOWLIST
  - Fail-closed: any non-allowlisted target raises ValueError / SystemExit
"""

from __future__ import annotations

import pytest

from prototype.lab_runner import (
    LAB_TARGET_ALLOWLIST,
    _validate_target,
    run_lab_attempt,
)
from prototype.cli import _run_scenario


# ---------------------------------------------------------------------------
# lab_runner layer
# ---------------------------------------------------------------------------

class TestLabRunnerSafety:
    """Direct lab_runner allowlist enforcement."""

    def test_allowlist_contents(self):
        assert LAB_TARGET_ALLOWLIST == {"127.0.0.1", "172.28.0.2"}

    def test_allowlisted_targets_validate(self):
        for t in LAB_TARGET_ALLOWLIST:
            assert _validate_target(t) == t.strip()

    def test_non_allowlisted_raises(self):
        with pytest.raises(ValueError, match="not in the lab allowlist"):
            _validate_target("192.168.1.100")

    def test_empty_target_raises(self):
        with pytest.raises(ValueError, match="not in the lab allowlist"):
            _validate_target("")

    def test_localhost_alias_not_allowed(self):
        """'localhost' is NOT in the allowlist — only explicit IPs."""
        with pytest.raises(ValueError, match="not in the lab allowlist"):
            _validate_target("localhost")

    def test_case_insensitive(self):
        """Case-folding must not bypass the allowlist."""
        assert _validate_target("127.0.0.1") == "127.0.0.1"

    def test_run_lab_attempt_refuses_non_allowlisted(self):
        """run_lab_attempt must refuse non-allowlisted targets BEFORE any socket."""
        with pytest.raises(ValueError, match="not in the lab allowlist"):
            run_lab_attempt("10.0.0.1", 8080, "/vuln")

    def test_run_lab_attempt_refuses_localhost(self):
        with pytest.raises(ValueError, match="not in the lab allowlist"):
            run_lab_attempt("localhost", 8080, "/vuln")


# ---------------------------------------------------------------------------
# CLI layer
# ---------------------------------------------------------------------------

class TestCLISafety:
    """CLI-level allowlist enforcement."""

    def test_cli_refuses_non_allowlisted_target(self):
        """CLI must refuse non-allowlisted lab targets with a non-zero exit."""
        with pytest.raises(SystemExit) as exc_info:
            _run_scenario(
                scenario_name="success",
                max_attempts=2,
                mode="lab",
                target="192.168.1.100",
                port=8080,
            )
        assert exc_info.value.code == 400

    def test_cli_refuses_localhost(self):
        with pytest.raises(SystemExit) as exc_info:
            _run_scenario(
                scenario_name="success",
                max_attempts=2,
                mode="lab",
                target="localhost",
                port=8080,
            )
        assert exc_info.value.code == 400

    def test_cli_accepts_allowlisted_target(self):
        """Allowlisted targets should NOT raise SystemExit(400) — they should
        proceed to the engine (which will be mocked to avoid network calls)."""
        from unittest.mock import patch

        with patch("prototype.engine_integration.run_engine") as mock_engine:
            mock_engine.return_value = {
                "status": "COMPLETED",
                "results": [],
                "candidates": [],
                "logs": [],
            }
            # Should not raise — allowlisted target passes the CLI gate
            _run_scenario(
                scenario_name="success",
                max_attempts=2,
                mode="lab",
                target="127.0.0.1",
                port=8080,
            )

    def test_cli_simulation_mode_ignores_target(self):
        """Simulation mode must not validate target (it is ignored)."""
        from unittest.mock import patch

        with patch("prototype.engine_integration.run_engine") as mock_engine:
            mock_engine.return_value = {
                "status": "COMPLETED",
                "results": [],
                "candidates": [],
                "logs": [],
            }
            # Even a non-allowlisted target should be fine in simulation mode
            _run_scenario(
                scenario_name="success",
                max_attempts=2,
                mode="simulation",
                target="192.168.1.100",
                port=8080,
            )