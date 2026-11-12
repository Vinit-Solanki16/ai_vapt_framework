"""Runtime readiness diagnostics and preflight evaluation for AI-VAPT.

Inspects:
1. Python environment and core package dependencies.
2. Docker CLI availability.
3. Docker daemon connectivity.
4. Required sandbox image availability (e.g. strix-sandbox:latest).
5. Sandbox initialization capability.
6. Configured LLM provider and model identifier.
7. Provider credential configuration and safe connectivity preflight.
8. Application storage and directory permissions.

Returns structured readiness reports classified into:
- ready
- missing_dependency
- configuration_required
- provider_unavailable
- runtime_unavailable

Never prints or returns sensitive API keys, tokens, or credentials.
"""

from __future__ import annotations

import enum
import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from strix.config.loader import load_settings
from strix.core.paths import runs_base_dir


logger = logging.getLogger(__name__)


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


class ReadinessStatus(str, enum.Enum):
    READY = "ready"
    MISSING_DEPENDENCY = "missing_dependency"
    CONFIGURATION_REQUIRED = "configuration_required"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"


class DiagnosticCheck(BaseModel):
    id: str
    name: str
    category: str  # "runtime", "environment", "provider", "model", "storage"
    status: ReadinessStatus
    passed: bool
    details: str
    remediation: str | None = None


class RuntimeReadinessReport(BaseModel):
    status: ReadinessStatus
    ready_for_autonomous: bool
    ready_for_lightweight: bool
    timestamp: str = Field(default_factory=_utc_now)
    checks: list[DiagnosticCheck] = Field(default_factory=list)
    summary: str
    recommendations: list[str] = Field(default_factory=list)
    environment_info: dict[str, Any] = Field(default_factory=dict)


def _mask_credential_summary(key: str | None) -> str:
    """Return a non-sensitive summary of a credential string without revealing characters."""
    if not key:
        return "Not configured"
    clean = str(key).strip()
    if not clean:
        return "Not configured"
    length = len(clean)
    prefix = clean[:5] if length > 8 else "set"
    return f"Configured ({prefix}...[{length} chars])"


def _read_strix_cli_config() -> dict[str, str]:
    """Read stored Strix CLI settings."""
    cfg_path = Path.home() / ".strix" / "cli-config.json"
    if cfg_path.is_file():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data.get("env", {}) if "env" in data else data
        except Exception:
            pass
    return {}


def evaluate_runtime_readiness(
    *,
    custom_target: str | None = None,
    custom_provider: str | None = None,
    custom_model: str | None = None,
    custom_api_key: str | None = None,
    test_network: bool = True,
) -> RuntimeReadinessReport:
    """Perform comprehensive runtime readiness diagnostics for autonomous and lightweight VAPT."""
    checks: list[DiagnosticCheck] = []
    recommendations: list[str] = []

    # ---------------------------------------------------------------------------
    # 1. Python Environment & Dependencies
    # ---------------------------------------------------------------------------
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 12)
    missing_pkgs: list[str] = []
    core_pkgs = ["fastapi", "pydantic", "litellm", "rich", "uvicorn", "docker"]
    for pkg in core_pkgs:
        if importlib.util.find_spec(pkg) is None:
            missing_pkgs.append(pkg)

    if not py_ok:
        checks.append(
            DiagnosticCheck(
                id="python_version",
                name="Python Version",
                category="environment",
                status=ReadinessStatus.MISSING_DEPENDENCY,
                passed=False,
                details=f"Python {py_version} detected. AI-VAPT requires Python 3.12+.",
                remediation="Upgrade Python to version 3.12 or newer.",
            )
        )
        recommendations.append("Upgrade Python environment to version 3.12 or newer.")
    elif missing_pkgs:
        checks.append(
            DiagnosticCheck(
                id="python_dependencies",
                name="Core Python Packages",
                category="environment",
                status=ReadinessStatus.MISSING_DEPENDENCY,
                passed=False,
                details=f"Missing required packages: {', '.join(missing_pkgs)}",
                remediation="Run 'uv sync' or 'pip install -e .' to install required dependencies.",
            )
        )
        recommendations.append(
            f"Install missing Python packages: {', '.join(missing_pkgs)} ('uv sync')."
        )
    else:
        checks.append(
            DiagnosticCheck(
                id="python_environment",
                name="Python Environment",
                category="environment",
                status=ReadinessStatus.READY,
                passed=True,
                details=f"Python {py_version} with all core dependencies installed.",
            )
        )

    # ---------------------------------------------------------------------------
    # 2. Docker CLI Availability
    # ---------------------------------------------------------------------------
    docker_bin = shutil.which("docker")
    docker_cli_ok = bool(docker_bin)
    docker_version_str = "Unavailable"

    if not docker_cli_ok:
        checks.append(
            DiagnosticCheck(
                id="docker_cli",
                name="Docker CLI Executable",
                category="runtime",
                status=ReadinessStatus.RUNTIME_UNAVAILABLE,
                passed=False,
                details="Docker CLI ('docker') was not found in system PATH.",
                remediation="Install Docker Engine or Docker Desktop and ensure 'docker' is in PATH.",
            )
        )
        recommendations.append(
            "Install Docker Engine and add the 'docker' command to PATH to enable autonomous multi-agent execution."
        )
    else:
        try:
            ver_res = subprocess.run(
                [docker_bin, "--version"],  # type: ignore[list-item]
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            docker_version_str = ver_res.stdout.strip() if ver_res.returncode == 0 else "Present"
        except Exception:
            docker_version_str = "Present (version query timed out)"

        checks.append(
            DiagnosticCheck(
                id="docker_cli",
                name="Docker CLI Executable",
                category="runtime",
                status=ReadinessStatus.READY,
                passed=True,
                details=f"Docker CLI located at '{docker_bin}' ({docker_version_str}).",
            )
        )

    # ---------------------------------------------------------------------------
    # 3. Docker Daemon Connectivity
    # ---------------------------------------------------------------------------
    daemon_ok = False
    if not docker_cli_ok:
        checks.append(
            DiagnosticCheck(
                id="docker_daemon",
                name="Docker Daemon Connectivity",
                category="runtime",
                status=ReadinessStatus.RUNTIME_UNAVAILABLE,
                passed=False,
                details="Docker daemon cannot be contacted: Docker CLI is absent.",
                remediation="Install Docker and start the Docker daemon ('sudo systemctl start docker').",
            )
        )
    else:
        try:
            info_res = subprocess.run(
                [docker_bin, "info"],  # type: ignore[list-item]
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3.0,
                check=False,
            )
            daemon_ok = info_res.returncode == 0
        except Exception:
            daemon_ok = False

        docker_host = os.environ.get("DOCKER_HOST", "").strip()
        is_remote = bool(docker_host and not docker_host.startswith("unix://"))
        tls_verify = os.environ.get("DOCKER_TLS_VERIFY", "0").strip() in ("1", "true", "True")
        cert_path = os.environ.get("DOCKER_CERT_PATH", "").strip()

        if not daemon_ok:
            if is_remote:
                d_msg = f"Remote Docker daemon at '{docker_host}' cannot be contacted."
                r_msg = f"Verify remote VM is running, port 2376 is open in firewall, and TLS certificates in '{cert_path or '~/.docker/certs-client'}' are valid."
                rec_msg = (
                    f"Verify remote Docker host '{docker_host}' connectivity and TLS configuration."
                )
            else:
                d_msg = "Docker daemon is not responding or /var/run/docker.sock is inaccessible."
                r_msg = "Start the Docker daemon service ('sudo systemctl start docker') or configure remote Docker via DOCKER_HOST."
                rec_msg = "Start the Docker daemon service or configure remote Docker access via DOCKER_HOST."

            checks.append(
                DiagnosticCheck(
                    id="docker_daemon",
                    name="Docker Daemon Connectivity",
                    category="runtime",
                    status=ReadinessStatus.RUNTIME_UNAVAILABLE,
                    passed=False,
                    details=d_msg,
                    remediation=r_msg,
                )
            )
            recommendations.append(rec_msg)
        else:
            conn_detail = (
                f"Remote Docker daemon connected at '{docker_host}' (TLS: {'enabled' if tls_verify else 'disabled'})."
                if is_remote
                else "Docker daemon connected and responsive."
            )
            checks.append(
                DiagnosticCheck(
                    id="docker_daemon",
                    name="Docker Daemon Connectivity",
                    category="runtime",
                    status=ReadinessStatus.READY,
                    passed=True,
                    details=conn_detail,
                )
            )

    # ---------------------------------------------------------------------------
    # 4. Sandbox Image Availability
    # ---------------------------------------------------------------------------
    image_ok = False
    settings = load_settings()
    required_image = (
        getattr(getattr(settings, "runtime", None), "image", None) or "strix-sandbox:latest"
    )

    if not daemon_ok:
        checks.append(
            DiagnosticCheck(
                id="sandbox_image",
                name="Sandbox Container Image",
                category="runtime",
                status=ReadinessStatus.RUNTIME_UNAVAILABLE,
                passed=False,
                details=f"Cannot verify image '{required_image}': Docker daemon is disconnected.",
                remediation="Ensure Docker daemon is running, then pull or build the sandbox image.",
            )
        )
    else:
        try:
            insp_res = subprocess.run(
                [docker_bin, "image", "inspect", required_image],  # type: ignore[list-item]
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3.0,
                check=False,
            )
            image_ok = insp_res.returncode == 0
        except Exception:
            image_ok = False

        if not image_ok:
            checks.append(
                DiagnosticCheck(
                    id="sandbox_image",
                    name="Sandbox Container Image",
                    category="runtime",
                    status=ReadinessStatus.RUNTIME_UNAVAILABLE,
                    passed=False,
                    details=f"Required sandbox image '{required_image}' is not found in local Docker cache.",
                    remediation=f"Build the image locally with 'docker build -t {required_image} -f containers/sandbox/Dockerfile .' or pull it.",
                )
            )
            recommendations.append(
                f"Build or pull the sandbox image '{required_image}' before launching autonomous assessments."
            )
        else:
            checks.append(
                DiagnosticCheck(
                    id="sandbox_image",
                    name="Sandbox Container Image",
                    category="runtime",
                    status=ReadinessStatus.READY,
                    passed=True,
                    details=f"Sandbox container image '{required_image}' is available locally.",
                )
            )

    # ---------------------------------------------------------------------------
    # 5. Configured LLM Provider & Model
    # ---------------------------------------------------------------------------
    cli_cfg = _read_strix_cli_config()
    provider = (
        (
            custom_provider
            or os.environ.get("STRIX_LLM_PROVIDER")
            or cli_cfg.get("STRIX_LLM_PROVIDER")
            or "openrouter"
        )
        .lower()
        .strip()
    )

    model_id = (
        custom_model
        or os.environ.get("STRIX_LLM")
        or getattr(getattr(settings, "llm", None), "model", None)
        or cli_cfg.get("STRIX_LLM")
        or ""
    ).strip()

    if not model_id:
        checks.append(
            DiagnosticCheck(
                id="model_configuration",
                name="AI Model Selection",
                category="model",
                status=ReadinessStatus.CONFIGURATION_REQUIRED,
                passed=False,
                details="No AI model identifier is configured in settings or environment.",
                remediation="Select or configure a model (e.g., 'openrouter/meta-llama/llama-3.3-70b-instruct' or 'anthropic/claude-opus-4-7').",
            )
        )
        recommendations.append(
            "Configure a valid AI model in Settings > AI Models or via STRIX_LLM."
        )
    else:
        checks.append(
            DiagnosticCheck(
                id="model_configuration",
                name="AI Model Selection",
                category="model",
                status=ReadinessStatus.READY,
                passed=True,
                details=f"Configured model: '{model_id}' (Provider: {provider.upper()}).",
            )
        )

    # ---------------------------------------------------------------------------
    # 6. Provider Credentials & Connectivity
    # ---------------------------------------------------------------------------
    # Resolve runtime key safely
    active_key: str | None = None
    if custom_api_key:
        active_key = custom_api_key
    elif provider == "openrouter":
        active_key = (
            os.environ.get("OPENROUTER_API_KEY")
            or cli_cfg.get("OPENROUTER_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or cli_cfg.get("LLM_API_KEY")
        )
    elif provider == "google":
        active_key = (
            os.environ.get("GEMINI_API_KEY")
            or cli_cfg.get("GEMINI_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or cli_cfg.get("LLM_API_KEY")
        )
    elif provider == "openai":
        active_key = (
            os.environ.get("OPENAI_API_KEY")
            or cli_cfg.get("OPENAI_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or cli_cfg.get("LLM_API_KEY")
        )
    else:
        active_key = os.environ.get("LLM_API_KEY") or cli_cfg.get("LLM_API_KEY")

    cred_summary = _mask_credential_summary(active_key)
    cred_configured = bool(active_key and str(active_key).strip())

    if not cred_configured and provider not in ("ollama", "local"):
        checks.append(
            DiagnosticCheck(
                id="provider_credential",
                name="AI Provider Credentials",
                category="provider",
                status=ReadinessStatus.CONFIGURATION_REQUIRED,
                passed=False,
                details=f"API key for provider '{provider.upper()}' is not configured.",
                remediation=f"Add your {provider.upper()} API key in Settings > AI Models or export {provider.upper()}_API_KEY.",
            )
        )
        recommendations.append(
            f"Provide an API key for {provider.upper()} in Settings > AI Models or via environment variable."
        )
    else:
        # Check safe connectivity if key is present
        provider_conn_ok = True
        provider_detail = f"Credentials configured: {cred_summary}."

        if cred_configured and provider == "openrouter" and test_network and active_key:
            try:
                from strix.llm.provider_validation import validate_openrouter_credential

                val = validate_openrouter_credential(active_key)
                if val.status == "quota_exceeded":
                    provider_conn_ok = False
                    provider_detail = f"OpenRouter daily quota exhausted: {val.message}"
                elif val.status == "invalid_credentials":
                    provider_conn_ok = False
                    provider_detail = f"OpenRouter credential validation failed: {val.message}"
                elif val.valid:
                    provider_detail = f"OpenRouter connectivity verified. {cred_summary}."
            except Exception:
                # Network or endpoint offline; report as warning
                pass

        if not provider_conn_ok:
            checks.append(
                DiagnosticCheck(
                    id="provider_credential",
                    name="AI Provider Credentials",
                    category="provider",
                    status=ReadinessStatus.PROVIDER_UNAVAILABLE,
                    passed=False,
                    details=provider_detail,
                    remediation="Update your API key with active credits or switch to a different provider.",
                )
            )
            recommendations.append(f"AI Provider error: {provider_detail}")
        else:
            checks.append(
                DiagnosticCheck(
                    id="provider_credential",
                    name="AI Provider Credentials",
                    category="provider",
                    status=ReadinessStatus.READY,
                    passed=True,
                    details=provider_detail,
                )
            )

    # ---------------------------------------------------------------------------
    # 7. Application Storage & Permissions
    # ---------------------------------------------------------------------------
    storage_ok = False
    try:
        base_dir = runs_base_dir()
        base_dir.mkdir(parents=True, exist_ok=True)
        probe_file = base_dir / f".probe_{os.getpid()}.tmp"
        probe_file.write_text("probe", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
        storage_ok = True
    except Exception:
        storage_ok = False

    if not storage_ok:
        checks.append(
            DiagnosticCheck(
                id="storage_permissions",
                name="Assessment Runs Directory",
                category="storage",
                status=ReadinessStatus.MISSING_DEPENDENCY,
                passed=False,
                details=f"Cannot write artifacts to directory: {base_dir}",
                remediation="Ensure write permissions on the project workspace and runs directory.",
            )
        )
        recommendations.append(f"Grant write permissions to runs directory '{base_dir}'.")
    else:
        checks.append(
            DiagnosticCheck(
                id="storage_permissions",
                name="Assessment Runs Directory",
                category="storage",
                status=ReadinessStatus.READY,
                passed=True,
                details=f"Runs artifact directory '{base_dir}' is writable.",
            )
        )

    # ---------------------------------------------------------------------------
    # 8. Overall Synthesis & Capability Matrix
    # ---------------------------------------------------------------------------
    runtime_checks = [c for c in checks if c.category == "runtime"]
    provider_checks = [c for c in checks if c.category in ("provider", "model")]
    env_checks = [c for c in checks if c.category == "environment"]

    ready_autonomous = all(c.passed for c in checks)
    # Lightweight scanner does not require Docker CLI, daemon, or sandbox image!
    ready_lightweight = (
        all(c.passed for c in env_checks) and storage_ok and all(c.passed for c in provider_checks)
    )

    # Determine overall status
    if ready_autonomous:
        overall_status = ReadinessStatus.READY
        summary = "All systems ready. Autonomous multi-agent core and lightweight scanner are operational."
    elif any(c.status == ReadinessStatus.MISSING_DEPENDENCY for c in checks):
        overall_status = ReadinessStatus.MISSING_DEPENDENCY
        summary = "Core dependencies are missing. Please install required packages."
    elif any(c.status == ReadinessStatus.CONFIGURATION_REQUIRED for c in checks):
        overall_status = ReadinessStatus.CONFIGURATION_REQUIRED
        summary = "Configuration required: AI Model or provider credentials must be specified."
    elif any(c.status == ReadinessStatus.PROVIDER_UNAVAILABLE for c in checks):
        overall_status = ReadinessStatus.PROVIDER_UNAVAILABLE
        summary = "Configured AI provider is unavailable or quota is exhausted."
    elif not daemon_ok or not docker_cli_ok or not image_ok:
        overall_status = ReadinessStatus.RUNTIME_UNAVAILABLE
        summary = (
            "Docker runtime is unavailable on host. Autonomous multi-agent mode is blocked; "
            "Lightweight active scanner is available."
            if ready_lightweight
            else "Docker runtime is unavailable and AI model configuration is incomplete."
        )
    else:
        overall_status = ReadinessStatus.RUNTIME_UNAVAILABLE
        summary = "Runtime environment is not ready for autonomous multi-agent execution."

    env_info = {
        "python_version": py_version,
        "docker_cli": docker_bin or "None",
        "docker_version": docker_version_str,
        "docker_daemon_connected": daemon_ok,
        "sandbox_image": required_image,
        "sandbox_image_present": image_ok,
        "provider": provider,
        "model": model_id or "Not configured",
        "credentials_configured": cred_configured,
        "runs_directory": str(base_dir),
    }

    return RuntimeReadinessReport(
        status=overall_status,
        ready_for_autonomous=ready_autonomous,
        ready_for_lightweight=ready_lightweight,
        checks=checks,
        summary=summary,
        recommendations=recommendations,
        environment_info=env_info,
    )
