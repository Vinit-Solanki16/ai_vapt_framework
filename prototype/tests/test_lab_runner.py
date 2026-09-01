"""Tests for lab_runner.py and the lab executor integration.

These tests are offline: they mock socket/HTTP at the boundary so we can
verify correct Outcome mapping without a live emulator.
"""
from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import pytest

from decision_engine.core.executor import Executor
from decision_engine.core.schemas import ActionCandidate, Outcome

from prototype.lab_runner import (
    LAB_TARGET_ALLOWLIST,
    _validate_target,
    http_get,
    outcome_from_response,
    run_lab_attempt,
)
from prototype.execution_layer import create_lab_executor


# --- _validate_target ---

class TestValidateTarget:
    def test_allowlisted_targets_pass(self):
        for target in LAB_TARGET_ALLOWLIST:
            result = _validate_target(target)
            assert result == target.strip()

    def test_non_allowlisted_target_raises(self):
        with pytest.raises(ValueError, match="not in the lab allowlist"):
            _validate_target("192.168.1.100")

    def test_empty_target_raises(self):
        with pytest.raises(ValueError, match="not in the lab allowlist"):
            _validate_target("")

    def test_case_insensitive_matching(self):
        result = _validate_target("127.0.0.1")
        assert result == "127.0.0.1"


# --- outcome_from_response ---

class TestOutcomeFromResponse:
    def test_vuln_endpoint_returns_success(self):
        body = "VULNERABLE"
        assert outcome_from_response(200, body) == Outcome.SUCCESS

    def test_fail_endpoint_returns_fail_timeout(self):
        body = "NOT_VULNERABLE: This endpoint simulates a non-exploitable path"
        assert outcome_from_response(200, body) == Outcome.FAIL_TIMEOUT

    def test_non_200_returns_fail_timeout(self):
        assert outcome_from_response(404, "Not Found") == Outcome.FAIL_TIMEOUT

    def test_500_returns_fail_timeout(self):
        assert outcome_from_response(500, "Server Error") == Outcome.FAIL_TIMEOUT

    def test_empty_body_returns_fail_timeout(self):
        assert outcome_from_response(200, "") == Outcome.FAIL_TIMEOUT


# --- http_get (mocked socket) ---

class TestHttpGet:
    def test_successful_get(self):
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [
            b"HTTP/1.1 200 OK\r\nContent-Length: 9\r\n\r\nVULNERABLE",
            b"",
        ]
        with patch("socket.socket") as mock_socket_cls:
            mock_socket_cls.return_value = mock_sock
            status, body = http_get("127.0.0.1", 8080, "/vuln")
        assert status == 200
        assert "VULNERABLE" in body

    def test_fail_endpoint(self):
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [
            b"HTTP/1.1 200 OK\r\n\r\nNOT_VULNERABLE: sim",
            b"",
        ]
        with patch("socket.socket") as mock_socket_cls:
            mock_socket_cls.return_value = mock_sock
            status, body = http_get("127.0.0.1", 8080, "/fail")
        assert status == 200
        assert "NOT_VULNERABLE" in body

    def test_connection_error_returns_0(self):
        with patch("socket.socket") as mock_socket_cls:
            mock_socket_cls.side_effect = OSError("Connection refused")
            status, body = http_get("127.0.0.1", 8080, "/vuln")
        assert status == 0
        assert body == ""

    def test_non_allowlisted_target_raises_before_socket(self):
        with pytest.raises(ValueError, match="not in the lab allowlist"):
            http_get("10.0.0.1", 8080, "/vuln")


# --- run_lab_attempt ---

class TestRunLabAttempt:
    def test_vuln_path(self):
        with patch("prototype.lab_runner.http_get", return_value=(200, "VULNERABLE")):
            outcome = run_lab_attempt("127.0.0.1", 8080, "/vuln")
        assert outcome == Outcome.SUCCESS

    def test_fail_path(self):
        with patch("prototype.lab_runner.http_get", return_value=(200, "NOT_VULNERABLE")):
            outcome = run_lab_attempt("127.0.0.1", 8080, "/fail")
        assert outcome == Outcome.FAIL_TIMEOUT

    def test_non_allowlisted_raises(self):
        with pytest.raises(ValueError):
            run_lab_attempt("192.168.1.1", 8080, "/vuln")


# --- create_lab_executor ---

class TestCreateLabExecutor:
    def test_returns_real_executor(self):
        executor = create_lab_executor("127.0.0.1", 8080, "/vuln")
        assert isinstance(executor, Executor)
        assert executor.mode == "real"

    def test_non_allowlisted_raises_at_construction(self):
        with pytest.raises(ValueError, match="not in the lab allowlist"):
            create_lab_executor("192.168.1.1", 8080)

    def test_executor_runs_lab_attempt(self):
        """Verify the lab executor performs an HTTP GET and maps to Outcome."""
        executor = create_lab_executor("127.0.0.1", 8080, "/vuln")
        candidate = ActionCandidate(id="CVE-TEST", probability=0.5)
        with patch("prototype.lab_runner.http_get", return_value=(200, "VULNERABLE")):
            result = executor.execute(candidate)
        assert result.outcome == Outcome.SUCCESS
        assert result.candidate_id == "CVE-TEST"
        assert result.request_count == 1

    def test_executor_fail_path(self):
        executor = create_lab_executor("127.0.0.1", 8080, "/fail")
        candidate = ActionCandidate(id="CVE-TEST", probability=0.5)
        with patch("prototype.lab_runner.http_get", return_value=(200, "NOT_VULNERABLE")):
            result = executor.execute(candidate)
        assert result.outcome == Outcome.FAIL_TIMEOUT


# --- Lab + engine integration ---

class TestLabEngineIntegration:
    def test_lab_executor_runs_through_engine(self):
        """End-to-end: lab executor → engine → terminal state."""
        from decision_engine.core.engine import run_engine

        executor = create_lab_executor("127.0.0.1", 8080, "/vuln")
        candidates = [
            {"id": "CVE-LAB-1", "probability": 0.8},
        ]
        with patch("prototype.lab_runner.http_get", return_value=(200, "VULNERABLE")):
            final = run_engine(
                candidates,
                assess_fn=None,
                executor=executor,
                max_attempts=2,
                mode="lab",
            )
        assert final["status"] in ("SUCCESS", "COMPLETED")

    def test_lab_fail_executor_runs_through_engine(self):
        """End-to-end: lab fail path → engine → terminal state."""
        from decision_engine.core.engine import run_engine

        executor = create_lab_executor("127.0.0.1", 8080, "/fail")
        candidates = [
            {"id": "CVE-LAB-FAIL", "probability": 0.5},
        ]
        with patch("prototype.lab_runner.http_get", return_value=(200, "NOT_VULNERABLE")):
            final = run_engine(
                candidates,
                assess_fn=None,
                executor=executor,
                max_attempts=2,
                mode="lab",
            )
        assert final["status"] == "COMPLETED"
