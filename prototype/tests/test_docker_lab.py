"""Docker integration tests for the VAPT lab environment.

These tests require a running Docker lab (vuln-executor + vuln-emulator).
They are marked with @pytest.mark.docker and skipped when the lab is unavailable.
"""
import pytest
import json
import urllib.request
import urllib.error
import subprocess
import time

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def docker_available() -> bool:
    """Return True if `docker ps` succeeds and port 9090 is reachable."""
    try:
        subprocess.run(
            ["docker", "ps"],
            capture_output=True,
            timeout=10,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False

    # Check port 9090 is open
    try:
        req = urllib.request.Request("http://localhost:9090/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

docker_skip = pytest.mark.skipif(
    not docker_available(),
    reason="Docker lab not available",
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EXECUTOR_URL = "http://localhost:9090"


def _post_execute(target: str, port: int, path: str, timeout: int = 30):
    """Helper: POST /execute and return (status_code, body_dict)."""
    payload = json.dumps({"target": target, "port": port, "path": path}).encode()
    req = urllib.request.Request(
        f"{EXECUTOR_URL}/execute",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode())
        return resp.status, body


def _get(path: str, timeout: int = 10):
    """Helper: GET request, returns (status_code, body)."""
    req = urllib.request.Request(f"{EXECUTOR_URL}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode()
        return resp.status, body


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@docker_skip
@pytest.mark.docker
def test_executor_health():
    """GET /health returns 200 and contains 'healthy'."""
    status, body = _get("/health")
    assert status == 200
    data = json.loads(body) if isinstance(body, str) else body
    assert "healthy" in str(data.get("status", "")).lower()


@docker_skip
@pytest.mark.docker
def test_vuln_path_returns_success():
    """POST /execute with /vuln path returns outcome == 'SUCCESS'."""
    status, body = _post_execute("172.28.0.2", 8080, "/vuln")
    assert status == 200
    assert body.get("outcome") == "SUCCESS"


@docker_skip
@pytest.mark.docker
def test_fail_path_returns_fail_timeout():
    """POST /execute with /fail path returns outcome == 'FAIL_TIMEOUT'."""
    status, body = _post_execute("172.28.0.2", 8080, "/fail")
    assert status == 200
    assert body.get("outcome") == "FAIL_TIMEOUT"


@docker_skip
@pytest.mark.docker
def test_non_allowlisted_target_rejected():
    """POST /execute with non-allowlisted target returns 403."""
    payload = json.dumps({"target": "8.8.8.8", "port": 80, "path": "/"}).encode()
    req = urllib.request.Request(
        f"{EXECUTOR_URL}/execute",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=10)
    assert exc_info.value.code == 403


@docker_skip
@pytest.mark.docker
def test_executor_reaches_emulator():
    """POST /execute to emulator returns 200 (executor can reach emulator)."""
    status, body = _post_execute("172.28.0.2", 8080, "/vuln")
    assert status == 200


@docker_skip
@pytest.mark.docker
def test_emulator_not_directly_accessible_from_host():
    """Direct connection from host to emulator (172.28.0.2:8080) should fail (network isolation)."""
    req = urllib.request.Request("http://172.28.0.2:8080/", method="GET")
    with pytest.raises((urllib.error.URLError, OSError, TimeoutError)):
        urllib.request.urlopen(req, timeout=5)


@docker_skip
@pytest.mark.docker
def test_pivot_through_execution_path():
    """Run engine with a lab executor pointing to /fail; verify pivot occurs."""
    from prototype.execution_layer import create_docker_lab_executor
    from prototype.engine_integration import run_decision_scenario

    executor = create_docker_lab_executor(
        target="172.28.0.2",
        port=8080,
        path="/fail",
    )

    scenario = [
        {"id": "candidate_a", "probability": 0.1},
        {"id": "candidate_b", "probability": 0.1},
    ]

    result = run_decision_scenario(
        scenario=scenario,
        executor=executor,
    )

    assert result.get("status") == "COMPLETED"
    presentation = result.get("_presentation", {})
    assert presentation.get("pivot_count", 0) >= 1