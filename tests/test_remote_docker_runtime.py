"""Tests for AI-VAPT Remote Docker Runtime, Codespaces Integration, and Diagnostics.

Covers:
1. Docker endpoint resolution (local vs remote DOCKER_HOST).
2. TLS certificate validation (missing directory, missing files, permission warnings, valid certs).
3. Runtime readiness preflight reporting with remote Docker host details.
4. Core diagnostics differentiating local socket from remote DOCKER_HOST.
5. Sandbox container image configuration and defaults.
6. verify_remote_docker CLI diagnostic tool (JSON output and schema).
7. Mocked remote Docker daemon lifecycle (ping, version, hardware sizing, image, container).
8. Live vs. Mocked test boundary distinction.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.verify_remote_docker import (
    check_host_resources,
    check_sandbox_image,
    check_tls_certificates,
    run_diagnostics,
)
from strix.core.diagnostics import evaluate_runtime_readiness
from strix.interface.readiness import _check_docker_runtime
from strix.runtime.docker_connection import (
    resolve_docker_endpoint,
)


# ==============================================================================
# 1. Endpoint Resolution Tests
# ==============================================================================


def test_resolve_docker_endpoint_local():
    """Verify endpoint resolves to default socket when DOCKER_HOST is not set."""
    endpoint = resolve_docker_endpoint(environ={})
    assert endpoint.host is None
    assert endpoint.source == "default socket"


def test_resolve_docker_endpoint_remote():
    """Verify endpoint resolves to DOCKER_HOST when provided."""
    env = {"DOCKER_HOST": "tcp://192.168.1.100:2376"}
    endpoint = resolve_docker_endpoint(environ=env)
    assert endpoint.host == "tcp://192.168.1.100:2376"
    assert endpoint.source == "DOCKER_HOST"
    assert "tcp://192.168.1.100:2376 (DOCKER_HOST)" in endpoint.label


# ==============================================================================
# 2. TLS Certificate Validation Tests
# ==============================================================================


def test_check_tls_certificates_disabled():
    """Verify warning when TLS verification is disabled."""
    res = check_tls_certificates(None, tls_verify=False)
    assert res.status == "WARN"
    assert "TLS verification is disabled" in res.summary


def test_check_tls_certificates_missing_directory(tmp_path: Path):
    """Verify failure when certificate path does not exist."""
    nonexistent = tmp_path / "does_not_exist"
    res = check_tls_certificates(nonexistent, tls_verify=True)
    assert res.status == "FAIL"
    assert "Certificate directory does not exist" in res.summary


def test_check_tls_certificates_missing_files(tmp_path: Path):
    """Verify failure when ca.pem, cert.pem, or key.pem are missing."""
    cert_dir = tmp_path / "certs"
    cert_dir.mkdir()
    (cert_dir / "ca.pem").write_text("dummy ca")
    # cert.pem and key.pem missing
    res = check_tls_certificates(cert_dir, tls_verify=True)
    assert res.status == "FAIL"
    assert "Missing required certificate files" in res.summary
    assert "cert.pem" in res.summary
    assert "key.pem" in res.summary


def test_check_tls_certificates_valid_and_permission_warning(tmp_path: Path):
    """Verify certificate parsing with OpenSSL-generated certs and permission checks."""
    cert_dir = tmp_path / "valid_certs"
    cert_dir.mkdir()

    # Generate test self-signed CA and client cert
    ca_key = cert_dir / "ca-key.pem"
    ca_cert = cert_dir / "ca.pem"
    client_key = cert_dir / "key.pem"
    client_csr = cert_dir / "client.csr"
    client_cert = cert_dir / "cert.pem"

    try:
        subprocess.run(
            ["openssl", "genrsa", "-out", str(ca_key), "2048"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "req",
                "-new",
                "-x509",
                "-days",
                "365",
                "-key",
                str(ca_key),
                "-out",
                str(ca_cert),
                "-subj",
                "/CN=Test CA",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["openssl", "genrsa", "-out", str(client_key), "2048"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "req",
                "-new",
                "-key",
                str(client_key),
                "-out",
                str(client_csr),
                "-subj",
                "/CN=ai-vapt-client",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "x509",
                "-req",
                "-days",
                "365",
                "-in",
                str(client_csr),
                "-CA",
                str(ca_cert),
                "-CAkey",
                str(ca_key),
                "-out",
                str(client_cert),
            ],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError:
        pytest.skip("openssl CLI is not installed")

    # Test with world-readable permissions (should generate WARN)
    client_key.chmod(0o644)
    res_warn = check_tls_certificates(cert_dir, tls_verify=True)
    assert res_warn.status == "WARN"
    assert "Valid client certificate" in res_warn.summary
    assert "600" in (res_warn.remediation or "")

    # Test with strict permissions 0600 (should PASS)
    client_key.chmod(0o600)
    res_pass = check_tls_certificates(cert_dir, tls_verify=True)
    assert res_pass.status == "PASS"
    assert "Valid client certificate" in res_pass.summary
    assert res_pass.details.get("days_remaining", 0) > 300


# ==============================================================================
# 3. Readiness Diagnostics & Differentiation
# ==============================================================================


def test_readiness_diagnostics_reports_remote_host_when_configured():
    """Verify _check_docker_runtime reports remote host details when DOCKER_HOST is set."""
    env = {
        "DOCKER_HOST": "tcp://203.0.113.10:2376",
        "DOCKER_TLS_VERIFY": "1",
        "DOCKER_CERT_PATH": "/home/vscode/.docker/certs-client",
    }
    with patch.dict(os.environ, env, clear=False):
        # Even during unit test, check details map
        res = _check_docker_runtime()
        assert res.details.get("is_remote") is True
        assert res.details.get("docker_host") == "tcp://203.0.113.10:2376"
        assert res.details.get("tls_verify") is True
        assert res.details.get("cert_path") == "/home/vscode/.docker/certs-client"


def test_core_diagnostics_differentiates_remote_docker():
    """Verify evaluate_runtime_readiness includes remote daemon guidance when DOCKER_HOST is set."""
    env = {
        "DOCKER_HOST": "tcp://203.0.113.10:2376",
        "DOCKER_TLS_VERIFY": "1",
        "DOCKER_CERT_PATH": "/home/vscode/.docker/certs-client",
    }
    with patch.dict(os.environ, env, clear=False):
        report = evaluate_runtime_readiness()
        daemon_check = next((c for c in report.checks if c.id == "docker_daemon"), None)
        assert daemon_check is not None
        # When daemon is not connected, the remediation/details should mention the remote host
        assert "203.0.113.10" in daemon_check.details or "203.0.113.10" in (
            daemon_check.remediation or ""
        )


# ==============================================================================
# 4. Sandbox Image Configuration Tests
# ==============================================================================


def test_sandbox_image_configuration_resolution():
    """Verify default and override resolution for STRIX_IMAGE."""
    import strix.config.loader as cfg_loader
    from strix.config.loader import apply_config_override

    settings = cfg_loader.load_settings()
    assert settings.runtime.image == "ghcr.io/usestrix/strix-sandbox:1.3.0"

    with patch.dict(os.environ, {"STRIX_IMAGE": "custom-sandbox:2.0.0"}):
        # Invalidate cache
        apply_config_override(Path("/nonexistent"))
        updated_settings = cfg_loader.load_settings()
        assert updated_settings.runtime.image == "custom-sandbox:2.0.0"
        # Reset override
        apply_config_override(Path.home() / ".strix" / "cli-config.json")


# ==============================================================================
# 5. Diagnostic CLI Tool (scripts/verify_remote_docker.py) Tests
# ==============================================================================


def test_verify_remote_docker_cli_json():
    """Verify verify_remote_docker.py outputs valid JSON schema and handles disconnected host."""
    cmd = [
        sys.executable,
        "scripts/verify_remote_docker.py",
        "--host",
        "tcp://127.0.0.1:2376",
        "--json",
        "--timeout",
        "1.0",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 1  # Connection refused returns exit code 1
    data = json.loads(proc.stdout)
    assert "timestamp" in data
    assert data["target_host"] == "tcp://127.0.0.1:2376"
    assert data["is_remote"] is True
    assert data["overall_ready"] is False
    assert "summary" in data
    assert data["summary"]["failed"] >= 1
    assert any(c["check_id"] == "client_creation" for c in data["checks"])


# ==============================================================================
# 6. Mocked Remote Docker Daemon Lifecycle Tests
# ==============================================================================


def test_mocked_remote_docker_lifecycle_all_pass():
    """Mock full successful diagnostic suite: ping, version, resources, image, container."""
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    mock_client.version.return_value = {
        "Version": "27.1.1",
        "ApiVersion": "1.47",
        "Os": "linux",
        "Arch": "x86_64",
        "KernelVersion": "6.8.0-45-generic",
    }
    mock_client.info.return_value = {
        "NCPU": 8,
        "MemTotal": 16 * (1024**3),
        "Driver": "overlay2",
        "OperatingSystem": "Ubuntu 24.04 LTS",
        "ContainersRunning": 2,
    }
    mock_image = MagicMock()
    mock_image.short_id = "sha256:1a2b3c"
    mock_image.tags = ["ghcr.io/usestrix/strix-sandbox:1.3.0"]
    mock_image.attrs = {"Size": 1_500_000_000}
    mock_client.images.get.return_value = mock_image

    mock_container = MagicMock()
    mock_container.short_id = "test-cont-123"
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_client.containers.create.return_value = mock_container

    mock_net = MagicMock()
    mock_net.name = "bridge"
    mock_client.networks.list.return_value = [mock_net]

    with patch("scripts.verify_remote_docker.create_docker_client", return_value=mock_client):
        results = run_diagnostics(
            host="tcp://10.0.0.5:2376",
            cert_dir=None,
            tls_verify=False,
            image_name="ghcr.io/usestrix/strix-sandbox:1.3.0",
            skip_container_test=False,
        )

        assert all(r.passed for r in results)
        assert any(r.check_id == "daemon_ping" and r.status == "PASS" for r in results)
        assert any(r.check_id == "engine_version" and r.status == "PASS" for r in results)
        assert any(r.check_id == "host_resources" and r.status == "PASS" for r in results)
        assert any(r.check_id == "sandbox_image" and r.status == "PASS" for r in results)
        assert any(r.check_id == "container_lifecycle" and r.status == "PASS" for r in results)
        assert any(r.check_id == "network_configuration" and r.status == "PASS" for r in results)
        mock_container.remove.assert_called_once_with(force=True)


def test_mocked_remote_docker_low_resources_warn():
    """Verify warning when remote VM has insufficient CPU or RAM."""
    mock_client = MagicMock()
    mock_client.info.return_value = {
        "NCPU": 2,  # < 4 recommended
        "MemTotal": 4 * (1024**3),  # < 8 recommended
        "Driver": "overlay2",
        "OperatingSystem": "Ubuntu 24.04 LTS",
    }
    res = check_host_resources(mock_client)
    assert res.status == "WARN"
    assert "CPUs (2) below recommended" in (res.error or "")
    assert "RAM (4.0 GB) below recommended" in (res.error or "")


def test_mocked_remote_docker_missing_sandbox_image():
    """Verify check_sandbox_image properly flags ImageNotFound."""
    from docker.errors import ImageNotFound

    mock_client = MagicMock()
    mock_client.images.get.side_effect = ImageNotFound("ghcr.io/usestrix/strix-sandbox:1.3.0")

    res = check_sandbox_image(mock_client, "ghcr.io/usestrix/strix-sandbox:1.3.0")
    assert res.status == "FAIL"
    assert "not found" in res.summary
    assert "docker pull" in (res.remediation or "")
