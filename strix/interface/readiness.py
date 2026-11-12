"""Runtime readiness diagnostics and preflight validation for AI-VAPT.

Inspects the host environment across five core readiness domains:
1. Python environment and core package dependencies.
2. Docker CLI presence, daemon connectivity, and sandbox container image availability.
3. Configured LLM provider, model settings, and safe credential validation.
4. Application storage directories and permissions.
5. Autonomous vs. Lightweight execution path feasibility.

Categorizes each domain into one of five canonical readiness states:
- 'ready': Fully operational and verified.
- 'missing_dependency': Required Python packages or tools are absent.
- 'configuration_required': Settings, models, or images need operator setup.
- 'provider_unavailable': Configured AI provider endpoint or quota check failed.
- 'runtime_unavailable': Required virtualization/container runtime (Docker) is down.

SECURITY: Never returns, logs, or prints raw API keys, tokens, or secrets.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from strix.config import load_settings
from strix.core.paths import runs_base_dir


logger = logging.getLogger(__name__)

ReadinessState = Literal[
    "ready",
    "missing_dependency",
    "configuration_required",
    "provider_unavailable",
    "runtime_unavailable",
]


class ComponentReadiness(BaseModel):
    """Readiness status for an individual subsystem."""

    name: str
    status: ReadinessState
    available: bool = False
    actionable_message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class RuntimeReadinessResponse(BaseModel):
    """Aggregate preflight diagnostic report for AI-VAPT."""

    overall_status: ReadinessState
    autonomous_ready: bool = False
    lightweight_ready: bool = True
    timestamp: str = Field(default_factory=lambda: _dt.datetime.now(_dt.UTC).isoformat())
    components: dict[str, ComponentReadiness] = Field(default_factory=dict)
    actionable_recommendations: list[str] = Field(default_factory=list)


def _check_python_environment() -> ComponentReadiness:
    """Inspect Python runtime and essential package dependencies."""
    py_ver = sys.version_info
    ver_str = f"{py_ver.major}.{py_ver.minor}.{py_ver.micro}"
    details: dict[str, Any] = {"python_version": ver_str}

    if py_ver < (3, 12):
        return ComponentReadiness(
            name="python_environment",
            status="missing_dependency",
            available=False,
            actionable_message=f"Python 3.12+ is required (found {ver_str}). Upgrade Python to continue.",
            details=details,
        )

    # Core required import checks
    missing_pkgs: list[str] = []
    for mod in ("pydantic", "fastapi", "rich", "litellm"):
        try:
            __import__(mod)
        except ImportError:
            missing_pkgs.append(mod)

    details["missing_packages"] = missing_pkgs
    if missing_pkgs:
        return ComponentReadiness(
            name="python_environment",
            status="missing_dependency",
            available=False,
            actionable_message=f"Missing essential packages: {', '.join(missing_pkgs)}. Run `uv sync` or install dependencies.",
            details=details,
        )

    return ComponentReadiness(
        name="python_environment",
        status="ready",
        available=True,
        actionable_message="Python 3.12+ runtime and required dependencies are installed.",
        details=details,
    )


def _check_docker_runtime(target_image: str | None = None) -> ComponentReadiness:
    """Inspect Docker CLI, Docker daemon accessibility, and sandbox container image."""
    cli_path = shutil.which("docker")
    docker_host = os.environ.get("DOCKER_HOST", "").strip()
    is_remote = bool(docker_host and not docker_host.startswith("unix://"))
    tls_verify = os.environ.get("DOCKER_TLS_VERIFY", "0").strip() in ("1", "true", "True")
    cert_path = os.environ.get("DOCKER_CERT_PATH", "").strip()

    details: dict[str, Any] = {
        "cli_available": bool(cli_path),
        "cli_path": cli_path or "not_found",
        "daemon_connected": False,
        "image_available": False,
        "is_remote": is_remote,
        "docker_host": docker_host or "local_socket",
        "tls_verify": tls_verify,
    }
    if cert_path:
        details["cert_path"] = cert_path

    if not cli_path:
        return ComponentReadiness(
            name="docker_runtime",
            status="runtime_unavailable",
            available=False,
            actionable_message="Docker CLI is not found on PATH. Install Docker to enable autonomous multi-agent pentesting, or use lightweight scanning mode.",
            details=details,
        )

    # In unit tests, honor PYTEST_CURRENT_TEST to avoid hanging
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return ComponentReadiness(
            name="docker_runtime",
            status="runtime_unavailable",
            available=False,
            actionable_message="Docker daemon connectivity is disabled during automated unit test harness.",
            details=details,
        )

    # Check daemon connectivity
    try:
        proc = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        )
        daemon_ok = proc.returncode == 0
    except Exception:
        daemon_ok = False

    details["daemon_connected"] = daemon_ok
    if not daemon_ok:
        if is_remote:
            msg = (
                f"Remote Docker daemon at '{docker_host}' is not reachable. "
                f"Verify remote host is running, port 2376 is open in firewall/security groups, "
                f"and TLS certificates in '{cert_path or '~/.docker/certs-client'}' are valid."
            )
        else:
            msg = (
                "Docker daemon is not running or socket is inaccessible. "
                "Start local Docker daemon or configure remote Docker via DOCKER_HOST for Codespaces."
            )
        return ComponentReadiness(
            name="docker_runtime",
            status="runtime_unavailable",
            available=False,
            actionable_message=msg,
            details=details,
        )

    # Check container image availability
    resolved_image = (
        target_image or load_settings().runtime.image or "ghcr.io/usestrix/strix-sandbox:1.3.0"
    )
    details["image_name"] = resolved_image
    try:
        img_proc = subprocess.run(
            ["docker", "image", "inspect", resolved_image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3.0,
        )
        img_ok = img_proc.returncode == 0
    except Exception:
        img_ok = False

    details["image_available"] = img_ok
    if not img_ok:
        if is_remote:
            msg = (
                f"Connected to remote Docker daemon at '{docker_host}', but sandbox image '{resolved_image}' is not found. "
                f"Pull it on the remote host with `docker pull {resolved_image}`."
            )
        else:
            msg = (
                f"Docker daemon is running, but sandbox image '{resolved_image}' is not found locally. "
                f"Pull it with `docker pull {resolved_image}`."
            )
        return ComponentReadiness(
            name="docker_runtime",
            status="configuration_required",
            available=False,
            actionable_message=msg,
            details=details,
        )

    ready_msg = (
        f"Remote Docker runtime ({docker_host}) and sandbox image '{resolved_image}' are ready for autonomous execution."
        if is_remote
        else f"Docker runtime and sandbox image '{resolved_image}' are ready for autonomous execution."
    )
    return ComponentReadiness(
        name="docker_runtime",
        status="ready",
        available=True,
        actionable_message=ready_msg,
        details=details,
    )


def _check_llm_provider(
    provider_override: str | None = None,
    model_override: str | None = None,
    api_key_override: str | None = None,
) -> ComponentReadiness:
    """Safely inspect configured LLM provider, model, and credentials format."""
    settings = load_settings()

    provider = (
        (provider_override or os.environ.get("STRIX_LLM_PROVIDER") or "openrouter").lower().strip()
    )
    model = (model_override or settings.llm.model or os.environ.get("STRIX_LLM") or "").strip()

    # Determine key presence without storing or exposing key value
    key = (
        api_key_override
        or settings.llm.api_key
        or os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("LLM_API_KEY")
        or ""
    )
    has_key = bool(key and str(key).strip())

    details: dict[str, Any] = {
        "provider": provider,
        "model": model or "not_configured",
        "credential_configured": has_key,
        "credential_length": len(key) if has_key else 0,
    }

    if not model:
        return ComponentReadiness(
            name="llm_provider",
            status="configuration_required",
            available=False,
            actionable_message="No AI model configured. Set STRIX_LLM in environment or select a model in Settings > AI Models.",
            details=details,
        )

    if provider in ("openrouter", "openai", "google", "cloud_hosted", "custom"):
        if not has_key:
            return ComponentReadiness(
                name="llm_provider",
                status="configuration_required",
                available=False,
                actionable_message=f"Provider '{provider}' requires an API credential. Enter an API key in Settings > AI Models.",
                details=details,
            )

        # Check format or test validity where applicable
        if provider == "openrouter":
            if key.startswith("sk-or-v1-test") or "placeholder" in key.lower():
                return ComponentReadiness(
                    name="llm_provider",
                    status="configuration_required",
                    available=False,
                    actionable_message="OpenRouter API key is set to a placeholder test token. Provide a live key for production assessments.",
                    details=details,
                )
            if not key.startswith("sk-or-"):
                details["format_warning"] = "Key does not match standard 'sk-or-...' prefix."

            try:
                from strix.llm.provider_validation import validate_openrouter_credential

                val = validate_openrouter_credential(key)
                if val.status == "quota_exceeded":
                    return ComponentReadiness(
                        name="llm_provider",
                        status="provider_unavailable",
                        available=False,
                        actionable_message=f"OpenRouter daily quota exhausted: {val.message}",
                        details=details,
                    )
                if val.status == "invalid_credentials":
                    return ComponentReadiness(
                        name="llm_provider",
                        status="configuration_required",
                        available=False,
                        actionable_message=f"OpenRouter credential validation failed: {val.message}",
                        details=details,
                    )
            except Exception:
                pass

        elif provider == "google":
            if not key.startswith("AIza"):
                details["format_warning"] = "Key does not match standard 'AIza...' prefix."

    elif provider == "ollama":
        details["api_base"] = os.environ.get("OLLAMA_API_BASE", "http://127.0.0.1:11434")

    return ComponentReadiness(
        name="llm_provider",
        status="ready",
        available=True,
        actionable_message=f"AI provider '{provider}' and model '{model}' configured.",
        details=details,
    )


def _check_application_storage() -> ComponentReadiness:
    """Inspect local run artifacts and configuration storage paths."""
    details: dict[str, Any] = {}
    runs_dir = runs_base_dir()
    details["runs_directory"] = str(runs_dir)

    try:
        runs_dir.mkdir(parents=True, exist_ok=True)
        test_file = runs_dir / ".readiness_probe"
        test_file.write_text("probe", encoding="utf-8")
        test_file.unlink()
        details["runs_directory_writable"] = True
    except Exception as exc:
        details["runs_directory_writable"] = False
        return ComponentReadiness(
            name="application_storage",
            status="configuration_required",
            available=False,
            actionable_message=f"Storage directory '{runs_dir}' is not writable: {exc}",
            details=details,
        )

    # Check ~/.strix/
    strix_home = Path.home() / ".strix"
    details["config_directory"] = str(strix_home)
    try:
        strix_home.mkdir(parents=True, exist_ok=True)
        details["config_directory_writable"] = True
    except Exception:
        details["config_directory_writable"] = False

    return ComponentReadiness(
        name="application_storage",
        status="ready",
        available=True,
        actionable_message="Application storage and configuration directories are accessible and writable.",
        details=details,
    )


def check_runtime_readiness(
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    image: str | None = None,
) -> RuntimeReadinessResponse:
    """Run full diagnostic preflight checks across all subsystems."""
    py_check = _check_python_environment()
    docker_check = _check_docker_runtime(target_image=image)
    llm_check = _check_llm_provider(
        provider_override=provider,
        model_override=model,
        api_key_override=api_key,
    )
    storage_check = _check_application_storage()

    components = {
        "python_environment": py_check,
        "docker_runtime": docker_check,
        "llm_provider": llm_check,
        "application_storage": storage_check,
    }

    recs: list[str] = []
    for c in components.values():
        if c.status != "ready" and c.actionable_message:
            recs.append(c.actionable_message)

    # Autonomous execution strictly requires Docker and LLM
    autonomous_ready = bool(
        py_check.available
        and docker_check.available
        and llm_check.available
        and storage_check.available
    )
    # Lightweight active scanning works even if Docker runtime is unavailable
    lightweight_ready = bool(py_check.available and storage_check.available)

    # Determine overall status
    if autonomous_ready:
        overall_status: ReadinessState = "ready"
    elif not docker_check.available:
        overall_status = docker_check.status
    elif not llm_check.available:
        overall_status = llm_check.status
    elif not py_check.available:
        overall_status = py_check.status
    else:
        overall_status = "configuration_required"

    return RuntimeReadinessResponse(
        overall_status=overall_status,
        autonomous_ready=autonomous_ready,
        lightweight_ready=lightweight_ready,
        components=components,
        actionable_recommendations=recs,
    )
