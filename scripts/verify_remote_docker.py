#!/usr/bin/env python3
"""AI-VAPT Remote Docker Diagnostic & Verification Utility.

Performs safe, non-destructive validation of remote Docker connectivity:
1. Environment & TLS certificate validation (CA, client cert, private key, permissions, expiry).
2. Docker daemon TCP connectivity and ping latency.
3. Docker Engine version and API compatibility.
4. Host hardware sizing (CPUs, RAM, storage driver).
5. Strix sandbox container image availability.
6. Harmless container lifecycle verification (create -> start -> wait -> delete).
7. Network configuration and host-gateway resolution check.

Usage:
    python scripts/verify_remote_docker.py
    python scripts/verify_remote_docker.py --json
    python scripts/verify_remote_docker.py --host tcp://192.168.1.50:2376 --cert-path ~/.docker/certs-client
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import stat
import sys
import time
from pathlib import Path
from typing import Any


try:
    import docker
    from docker.errors import ImageNotFound
    from docker.tls import TLSConfig
except ImportError:
    print(
        "ERROR: 'docker' Python package is not installed. Run `uv sync` or `pip install docker`.",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
GRAY = "\033[90m"


def _color(text: str, color_code: str, use_color: bool = True) -> str:
    return f"{color_code}{text}{RESET}" if use_color else text


class DiagnosticResult:
    def __init__(self, check_id: str, title: str) -> None:
        self.check_id = check_id
        self.title = title
        self.passed: bool = False
        self.status: str = "PENDING"
        self.summary: str = ""
        self.details: dict[str, Any] = {}
        self.error: str | None = None
        self.remediation: str | None = None

    def mark_pass(self, summary: str, details: dict[str, Any] | None = None) -> None:
        self.passed = True
        self.status = "PASS"
        self.summary = summary
        self.details = details or {}

    def mark_fail(
        self,
        summary: str,
        error: str,
        remediation: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.passed = False
        self.status = "FAIL"
        self.summary = summary
        self.error = error
        self.remediation = remediation
        self.details = details or {}

    def mark_warn(
        self,
        summary: str,
        warning: str,
        remediation: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.passed = True
        self.status = "WARN"
        self.summary = summary
        self.error = warning
        self.remediation = remediation
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "title": self.title,
            "status": self.status,
            "passed": self.passed,
            "summary": self.summary,
            "details": self.details,
            "error": self.error,
            "remediation": self.remediation,
        }


def check_tls_certificates(cert_dir: Path | None, tls_verify: bool) -> DiagnosticResult:
    result = DiagnosticResult("tls_certificates", "TLS Certificates Validation")
    if not tls_verify:
        result.mark_warn(
            "TLS verification is disabled (DOCKER_TLS_VERIFY != 1)",
            "Unencrypted or unauthenticated Docker API access is insecure.",
            "Set DOCKER_TLS_VERIFY=1 and configure DOCKER_CERT_PATH.",
        )
        return result

    if not cert_dir or not cert_dir.exists():
        result.mark_fail(
            "Certificate directory does not exist",
            f"Path not found: '{cert_dir}'",
            "Ensure DOCKER_CERT_PATH points to a directory containing ca.pem, cert.pem, and key.pem.",
        )
        return result

    ca_file = cert_dir / "ca.pem"
    cert_file = cert_dir / "cert.pem"
    key_file = cert_dir / "key.pem"

    missing = [f.name for f in [ca_file, cert_file, key_file] if not f.is_file()]
    if missing:
        result.mark_fail(
            f"Missing required certificate files: {', '.join(missing)}",
            f"Directory '{cert_dir}' must contain ca.pem, cert.pem, and key.pem.",
            f"Copy the missing files ({', '.join(missing)}) from the remote Docker host to '{cert_dir}'.",
        )
        return result

    # Check key permissions
    details: dict[str, Any] = {
        "cert_directory": str(cert_dir),
        "ca_file": str(ca_file),
        "cert_file": str(cert_file),
        "key_file": str(key_file),
    }

    try:
        key_stat = key_file.stat()
        key_mode = oct(stat.S_IMODE(key_stat.st_mode))
        details["key_permissions"] = key_mode
        if (key_stat.st_mode & (stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)) != 0:
            key_perm_warn = f"Private key '{key_file}' has permissions {key_mode} (should be 0600)."
        else:
            key_perm_warn = None
    except Exception as e:
        key_perm_warn = f"Could not inspect key permissions: {e}"

    # Parse certificates if cryptography is available
    if HAS_CRYPTO:
        try:
            cert_bytes = cert_file.read_bytes()
            x509_cert = x509.load_pem_x509_certificate(cert_bytes)
            now = dt.datetime.now(dt.UTC)
            not_valid_before = x509_cert.not_valid_before_utc
            not_valid_after = x509_cert.not_valid_after_utc

            details["cert_subject"] = x509_cert.subject.rfc4514_string()
            details["cert_issuer"] = x509_cert.issuer.rfc4514_string()
            details["valid_from"] = not_valid_before.isoformat()
            details["valid_to"] = not_valid_after.isoformat()

            if now < not_valid_before:
                result.mark_fail(
                    "Client certificate is not yet valid",
                    f"Valid from: {not_valid_before.isoformat()} (Current UTC: {now.isoformat()})",
                    "Check system clocks on client and server.",
                    details,
                )
                return result
            if now > not_valid_after:
                result.mark_fail(
                    "Client certificate has expired",
                    f"Expired on: {not_valid_after.isoformat()}",
                    "Regenerate client certificate on the Docker VM and update Codespaces.",
                    details,
                )
                return result

            days_left = (not_valid_after - now).days
            details["days_remaining"] = days_left

            # Verify private key loads cleanly
            key_bytes = key_file.read_bytes()
            serialization.load_pem_private_key(key_bytes, password=None)

            summary = f"Valid client certificate (expires in {days_left} days)"
            if key_perm_warn:
                result.mark_warn(summary, key_perm_warn, f"Run `chmod 600 {key_file}`", details)
            else:
                result.mark_pass(summary, details)
            return result
        except Exception as exc:
            result.mark_fail(
                "Certificate parsing failed",
                str(exc),
                "Verify that cert.pem and key.pem are valid unencrypted PEM files.",
                details,
            )
            return result
    else:
        summary = "Certificate files exist and readable (cryptography module not available for deep inspect)"
        if key_perm_warn:
            result.mark_warn(summary, key_perm_warn, f"Run `chmod 600 {key_file}`", details)
        else:
            result.mark_pass(summary, details)
        return result


def create_docker_client(
    host: str,
    cert_dir: Path | None,
    tls_verify: bool,
    timeout: float = 5.0,
) -> docker.DockerClient:
    """Create a configured DockerClient instance."""
    if host.startswith("unix://") or not host:
        return docker.from_env(timeout=timeout)

    if tls_verify and cert_dir:
        ca_cert = str(cert_dir / "ca.pem")
        client_cert = (str(cert_dir / "cert.pem"), str(cert_dir / "key.pem"))
        tls_config = TLSConfig(
            client_cert=client_cert,
            ca_cert=ca_cert,
            verify=True,
        )
        return docker.DockerClient(base_url=host, tls=tls_config, timeout=timeout)
    return docker.DockerClient(base_url=host, timeout=timeout)


def check_daemon_ping(client: docker.DockerClient, host: str) -> DiagnosticResult:
    result = DiagnosticResult("daemon_ping", "Docker Daemon Ping")
    start_t = time.perf_counter()
    try:
        ok = client.ping()
        elapsed_ms = (time.perf_counter() - start_t) * 1000
        if ok:
            result.mark_pass(
                f"Daemon reachable at {host} ({elapsed_ms:.1f}ms)",
                {"host": host, "ping_ms": round(elapsed_ms, 2)},
            )
        else:
            result.mark_fail(
                "Daemon returned unexpected ping response",
                "client.ping() returned False",
                "Check Docker daemon status on the remote host.",
            )
    except Exception as exc:
        result.mark_fail(
            f"Cannot connect to Docker daemon at '{host}'",
            str(exc),
            "Verify VM is running, port 2376 is accessible in security groups/UFW, and TLS certs match.",
            {"host": host},
        )
    return result


def check_engine_version(client: docker.DockerClient) -> DiagnosticResult:
    result = DiagnosticResult("engine_version", "Docker Engine Version & Compatibility")
    try:
        v_info = client.version()
        engine_ver = v_info.get("Version", "Unknown")
        api_ver = v_info.get("ApiVersion", "Unknown")
        os_name = v_info.get("Os", "Unknown")
        arch = v_info.get("Arch", "Unknown")
        kernel = v_info.get("KernelVersion", "Unknown")

        details = {
            "version": engine_ver,
            "api_version": api_ver,
            "os": os_name,
            "arch": arch,
            "kernel": kernel,
        }

        # Check for minimum recommended engine version (>= 20.10)
        result.mark_pass(f"Docker Engine {engine_ver} (API {api_ver}, {os_name}/{arch})", details)
    except Exception as exc:
        result.mark_fail("Failed to retrieve Docker Engine version", str(exc), None)
    return result


def check_host_resources(client: docker.DockerClient) -> DiagnosticResult:
    result = DiagnosticResult("host_resources", "Host Hardware Sizing")
    try:
        info = client.info()
        cpus = info.get("NCPU", 0)
        total_mem = info.get("MemTotal", 0)
        mem_gb = round(total_mem / (1024**3), 2)
        driver = info.get("Driver", "Unknown")
        os_type = info.get("OperatingSystem", "Unknown")
        containers_running = info.get("ContainersRunning", 0)

        details = {
            "cpus": cpus,
            "memory_gb": mem_gb,
            "storage_driver": driver,
            "os": os_type,
            "containers_running": containers_running,
        }

        # Recommended: >= 4 vCPUs, >= 8 GB RAM
        warnings: list[str] = []
        if cpus < 4:
            warnings.append(f"CPUs ({cpus}) below recommended 4 cores")
        if mem_gb < 7.5:
            warnings.append(f"RAM ({mem_gb} GB) below recommended 8 GB")

        summary = f"{cpus} vCPUs, {mem_gb} GB RAM, storage driver: {driver}"
        if warnings:
            result.mark_warn(
                summary,
                "; ".join(warnings),
                "Consider upgrading the remote VM (e.g. 4 vCPU, 16 GB RAM) for intensive pentesting tasks.",
                details,
            )
        else:
            result.mark_pass(summary, details)
    except Exception as exc:
        result.mark_fail("Failed to query host hardware resources", str(exc), None)
    return result


def check_sandbox_image(client: docker.DockerClient, image_name: str) -> DiagnosticResult:
    result = DiagnosticResult("sandbox_image", "Strix Sandbox Image Availability")
    try:
        img = client.images.get(image_name)
        img_id = img.short_id if hasattr(img, "short_id") else str(img.id)[:12]
        tags = img.tags or [image_name]
        size_mb = round(img.attrs.get("Size", 0) / (1024**2), 1)
        details = {
            "image": image_name,
            "id": img_id,
            "tags": tags,
            "size_mb": size_mb,
        }
        result.mark_pass(f"Image '{image_name}' is available ({img_id}, {size_mb} MB)", details)
    except ImageNotFound:
        result.mark_fail(
            f"Image '{image_name}' is not found on the remote Docker daemon",
            f"docker.errors.ImageNotFound: {image_name}",
            f"Pull the image on the remote host: `docker pull {image_name}`",
            {"image": image_name},
        )
    except Exception as exc:
        result.mark_fail(
            f"Failed to inspect sandbox image '{image_name}'",
            str(exc),
            f"Verify network connectivity and run `docker pull {image_name}`.",
            {"image": image_name},
        )
    return result


def check_container_lifecycle(client: docker.DockerClient, image_name: str) -> DiagnosticResult:
    result = DiagnosticResult("container_lifecycle", "Container Lifecycle Verification")
    test_container = None
    container_name = f"ai-vapt-diag-{int(time.time())}"
    try:
        # Create a harmless container running 'true'
        test_container = client.containers.create(
            image=image_name,
            command=["true"],
            name=container_name,
            labels={"ai-vapt-diagnostic": "true", "purpose": "connectivity-test"},
            detach=True,
        )
        test_container.start()
        res = test_container.wait(timeout=10)
        exit_code = (
            res.get("StatusCode", -1) if isinstance(res, dict) else getattr(res, "status_code", -1)
        )

        if exit_code == 0:
            result.mark_pass(
                "Harmless container created, executed, and exited cleanly (code 0)",
                {"container_id": test_container.short_id, "exit_code": exit_code},
            )
        else:
            result.mark_fail(
                f"Diagnostic container exited with non-zero code {exit_code}",
                f"Exit code: {exit_code}",
                "Check container environment or image entrypoint compatibility.",
            )
    except Exception as exc:
        result.mark_fail(
            "Container lifecycle verification failed",
            str(exc),
            "Ensure remote Docker daemon allows container creation and execution with required caps.",
        )
    finally:
        if test_container:
            try:
                test_container.remove(force=True)
            except Exception:
                pass
    return result


def check_network_configuration(client: docker.DockerClient) -> DiagnosticResult:
    result = DiagnosticResult("network_configuration", "Network & Host Gateway Inspection")
    try:
        networks = client.networks.list()
        net_names = [n.name for n in networks]
        details = {
            "networks": net_names,
            "bridge_present": "bridge" in net_names,
            "host_present": "host" in net_names,
        }
        if "bridge" in net_names:
            result.mark_pass(
                f"Standard Docker networks operational ({len(net_names)} networks found)", details
            )
        else:
            result.mark_warn(
                "Default 'bridge' network not found in network list",
                "Custom network configuration detected.",
                "Ensure default container networking or STRIX_DOCKER_SANDBOX_NETWORK is configured.",
                details,
            )
    except Exception as exc:
        result.mark_fail("Failed to inspect Docker networks", str(exc), None)
    return result


def run_diagnostics(
    host: str,
    cert_dir: Path | None,
    tls_verify: bool,
    image_name: str,
    skip_container_test: bool = False,
    timeout: float = 5.0,
) -> list[DiagnosticResult]:
    results: list[DiagnosticResult] = []

    # 1. TLS Certificates Check
    is_remote = bool(host and not host.startswith("unix://"))
    if is_remote and tls_verify:
        tls_res = check_tls_certificates(cert_dir, tls_verify)
        results.append(tls_res)
        if not tls_res.passed and tls_res.status == "FAIL":
            # Cannot proceed with connection if TLS files are missing or expired
            return results

    # 2. Connection & Ping
    try:
        client = create_docker_client(host, cert_dir, tls_verify, timeout=timeout)
    except Exception as exc:
        res = DiagnosticResult("client_creation", "Docker Client Initialization")
        res.mark_fail(
            "Failed to initialize Docker SDK client",
            str(exc),
            "Check DOCKER_HOST format and parameters.",
        )
        results.append(res)
        return results

    ping_res = check_daemon_ping(client, host or "default socket")
    results.append(ping_res)
    if not ping_res.passed:
        return results

    # 3. Engine Version
    ver_res = check_engine_version(client)
    results.append(ver_res)

    # 4. Host Resources
    res_res = check_host_resources(client)
    results.append(res_res)

    # 5. Sandbox Image
    img_res = check_sandbox_image(client, image_name)
    results.append(img_res)

    # 6. Container Lifecycle (only if image exists and not skipped)
    if not skip_container_test:
        if img_res.passed:
            life_res = check_container_lifecycle(client, image_name)
            results.append(life_res)
        else:
            skip_res = DiagnosticResult("container_lifecycle", "Container Lifecycle Verification")
            skip_res.mark_warn(
                "Skipped container lifecycle check because sandbox image is not present",
                "Image missing",
                f"Pull '{image_name}' to enable full lifecycle verification.",
            )
            results.append(skip_res)

    # 7. Network Configuration
    net_res = check_network_configuration(client)
    results.append(net_res)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify remote Docker connectivity and sandbox runtime for AI-VAPT.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("DOCKER_HOST", ""),
        help="Docker host endpoint (default: $DOCKER_HOST or local socket).",
    )
    parser.add_argument(
        "--cert-path",
        default=os.environ.get("DOCKER_CERT_PATH", ""),
        help="Path to directory containing ca.pem, cert.pem, key.pem (default: $DOCKER_CERT_PATH).",
    )
    parser.add_argument(
        "--tls-verify",
        action="store_true",
        default=os.environ.get("DOCKER_TLS_VERIFY", "0").strip() in ("1", "true", "True"),
        help="Enable TLS verification (default: $DOCKER_TLS_VERIFY == 1).",
    )
    parser.add_argument(
        "--image",
        default=os.environ.get("STRIX_IMAGE", "ghcr.io/usestrix/strix-sandbox:1.3.0"),
        help="Target sandbox container image (default: $STRIX_IMAGE or ghcr.io/usestrix/strix-sandbox:1.3.0).",
    )
    parser.add_argument(
        "--skip-container-test",
        action="store_true",
        help="Skip spawning a temporary test container.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Connection timeout in seconds (default: 5.0).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format.",
    )

    args = parser.parse_args()

    host = args.host.strip()
    cert_path_str = args.cert_path.strip()
    cert_dir = Path(cert_path_str).expanduser() if cert_path_str else None
    tls_verify = bool(args.tls_verify)
    image_name = args.image.strip()

    is_remote = bool(host and not host.startswith("unix://"))
    use_color = sys.stdout.isatty() and not args.json

    if not args.json:
        print(f"\n{BOLD}{CYAN}=== AI-VAPT Remote Docker Runtime Diagnostic ==={RESET}\n")
        print(f"Target Endpoint : {host or 'Local Unix Socket (/var/run/docker.sock)'}")
        print(f"Runtime Mode    : {'Remote Docker (TLS)' if is_remote else 'Local Docker'}")
        if is_remote:
            print(f"TLS Verify      : {tls_verify}")
            print(f"Cert Directory  : {cert_dir or 'Not configured'}")
        print(f"Sandbox Image   : {image_name}\n")

    results = run_diagnostics(
        host=host,
        cert_dir=cert_dir,
        tls_verify=tls_verify,
        image_name=image_name,
        skip_container_test=args.skip_container_test,
        timeout=args.timeout,
    )

    total = len(results)
    passed_count = sum(1 for r in results if r.status == "PASS")
    warn_count = sum(1 for r in results if r.status == "WARN")
    fail_count = sum(1 for r in results if r.status == "FAIL")

    all_passed = fail_count == 0

    if args.json:
        report = {
            "timestamp": dt.datetime.now(dt.UTC).isoformat(),
            "target_host": host or "local",
            "is_remote": is_remote,
            "overall_ready": all_passed,
            "summary": {
                "total_checks": total,
                "passed": passed_count,
                "warnings": warn_count,
                "failed": fail_count,
            },
            "checks": [r.to_dict() for r in results],
        }
        print(json.dumps(report, indent=2))
        return 0 if all_passed else 1

    # Pretty console output
    for r in results:
        if r.status == "PASS":
            tag = _color("[PASS]", GREEN, use_color)
        elif r.status == "WARN":
            tag = _color("[WARN]", YELLOW, use_color)
        else:
            tag = _color("[FAIL]", RED, use_color)

        print(f"  {tag} {BOLD}{r.title}{RESET}")
        print(f"         {r.summary}")
        if r.error:
            print(f"         {_color('Error/Note:', GRAY, use_color)} {r.error}")
        if r.remediation:
            print(f"         {_color('Remediation:', CYAN, use_color)} {r.remediation}")
        print()

    print("-" * 60)
    if all_passed:
        if warn_count > 0:
            print(
                _color(
                    f"Result: PASS WITH WARNINGS ({passed_count} passed, {warn_count} warning, 0 failed). Ready for autonomous execution.",
                    YELLOW,
                    use_color,
                )
            )
        else:
            print(
                _color(
                    f"Result: ALL CHECKS PASSED ({passed_count}/{total}). Remote Docker is fully ready for Strix autonomous execution.",
                    GREEN,
                    use_color,
                )
            )
        return 0
    print(
        _color(
            f"Result: READINESS FAILED ({fail_count} failed, {warn_count} warning, {passed_count} passed).",
            RED,
            use_color,
        )
    )
    print("Please address the remediations above before launching autonomous scans.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
