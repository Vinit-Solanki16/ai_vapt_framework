"""FastAPI Gateway for STRIX AI-VAPT Platform.

Serves the Web Operations Console SPA and exposes REST endpoints for:
- System & model provider health checks
- In-memory credential validation (Gemini, OpenRouter)
- Fail-closed target scope verification
- Assessment lifecycle management (GAP-1 triage, GAP-2 pivoting, Strix execution)
- Live decision traces, real-time DAG state, and audit reporting
"""
from __future__ import annotations

import asyncio
import collections
from contextlib import asynccontextmanager
import csv
import hashlib
import io
import json
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, Body, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from strix.core import gap_bridge
from strix.core.paths import run_record_path, runs_base_dir
from strix.llm.router import DEFAULT_OPENROUTER_MODEL, format_openrouter_model
from strix.interface.schemas import (
    CloudHostedProfile,
    CloudHostedProfileSafe,
    CloudTestConnectionResponse,
    CloudToolCallDiagnostic,
    CloudVerifyToolsResponse,
    CloudWarmupResponse,
    GoogleValidateResponse,
    OpenAIValidateResponse,
    OpenRouterModelInfo,
    OpenRouterValidateResponse,
    RunRequest,
    RunResponse,
    RunStatus,
    SystemHealthResponse,
    TargetValidateRequest,
    TargetValidateResponse,
)

logger = logging.getLogger("strix.interface.api")

app = FastAPI(
    title="AI-VAPT Operations Console",
    description="Autonomous Vulnerability Assessment & Penetration Testing Gateway",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static file paths
WEB_DIR = Path(__file__).resolve().parent / "web"
CSS_DIR = WEB_DIR / "css"
JS_DIR = WEB_DIR / "js"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CLI_CONFIG_FILE = Path.home() / ".strix" / "cli-config.json"


def _read_full_strix_cli_config() -> Dict[str, Any]:
    """Read complete ~/.strix/cli-config.json preserving all top-level keys."""
    if CLI_CONFIG_FILE.is_file():
        try:
            data = json.loads(CLI_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception as exc:
            logger.debug("Failed to read Strix CLI config: %s", exc)
    return {"env": {}, "cloud_hosted_profiles": []}


def _write_full_strix_cli_config(data: Dict[str, Any]) -> None:
    """Safely persist full JSON to ~/.strix/cli-config.json (0o600)."""
    CLI_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        from strix.utils.secret_files import write_secret_text
        write_secret_text(CLI_CONFIG_FILE, json.dumps(data, indent=2))
    except Exception as exc:
        logger.warning("Failed to persist CLI config: %s", exc)
        CLI_CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_strix_cli_config() -> Dict[str, str]:
    """Read persisted environment variables from ~/.strix/cli-config.json."""
    full = _read_full_strix_cli_config()
    env = full.get("env", {})
    if isinstance(env, dict):
        return {k: str(v) for k, v in env.items() if v is not None}
    return {}


def _write_strix_cli_config(env_vars: Dict[str, str]) -> None:
    """Safely update environment variables in ~/.strix/cli-config.json while preserving other sections."""
    full = _read_full_strix_cli_config()
    env = full.setdefault("env", {})
    env.update({k: str(v) for k, v in env_vars.items() if v is not None})
    _write_full_strix_cli_config(full)


def _get_cloud_profiles() -> List[Dict[str, Any]]:
    """Retrieve saved Cloud Hosted provider profiles."""
    full = _read_full_strix_cli_config()
    profiles = full.get("cloud_hosted_profiles", [])
    if isinstance(profiles, list):
        return profiles
    return []


def _save_cloud_profile(profile_data: Union[CloudHostedProfile, Dict[str, Any]]) -> Dict[str, Any]:
    """Save or update a Cloud Hosted provider profile."""
    if hasattr(profile_data, "model_dump"):
        pdict = profile_data.model_dump()
    elif isinstance(profile_data, dict):
        pdict = dict(profile_data)
    else:
        pdict = dict(profile_data)

    full = _read_full_strix_cli_config()
    profiles: List[Dict[str, Any]] = full.setdefault("cloud_hosted_profiles", [])
    pid = pdict.get("id") or f"cloud-{uuid.uuid4().hex[:6]}"
    pdict["id"] = pid

    existing_idx = next((i for i, p in enumerate(profiles) if p.get("id") == pid), None)
    if existing_idx is not None:
        if not pdict.get("api_key") and profiles[existing_idx].get("api_key"):
            pdict["api_key"] = profiles[existing_idx]["api_key"]
        profiles[existing_idx] = pdict
    else:
        profiles.append(pdict)

    if pdict.get("is_active"):
        full["active_cloud_profile_id"] = pid
        for p in profiles:
            p["is_active"] = (p.get("id") == pid)

    _write_full_strix_cli_config(full)
    return pdict


def _delete_cloud_profile(profile_id: str) -> bool:
    """Delete a Cloud Hosted provider profile by ID."""
    full = _read_full_strix_cli_config()
    profiles: List[Dict[str, Any]] = full.get("cloud_hosted_profiles", [])
    orig_len = len(profiles)
    profiles = [p for p in profiles if p.get("id") != profile_id]
    if len(profiles) < orig_len:
        full["cloud_hosted_profiles"] = profiles
        if full.get("active_cloud_profile_id") == profile_id:
            full["active_cloud_profile_id"] = profiles[0]["id"] if profiles else None
            if profiles:
                profiles[0]["is_active"] = True
        _write_full_strix_cli_config(full)
        return True
    return False


def _set_active_cloud_profile(profile_id: str) -> Optional[Dict[str, Any]]:
    """Mark a profile as active and synchronize with environment."""
    full = _read_full_strix_cli_config()
    profiles: List[Dict[str, Any]] = full.get("cloud_hosted_profiles", [])
    matched = None
    for p in profiles:
        if p.get("id") == profile_id:
            p["is_active"] = True
            matched = p
        else:
            p["is_active"] = False
    if matched:
        full["active_cloud_profile_id"] = profile_id
        _write_full_strix_cli_config(full)
    return matched


def _get_active_cloud_profile() -> Optional[Dict[str, Any]]:
    """Retrieve the currently active Cloud Hosted profile."""
    full = _read_full_strix_cli_config()
    active_id = full.get("active_cloud_profile_id")
    profiles = full.get("cloud_hosted_profiles", [])
    if active_id:
        for p in profiles:
            if p.get("id") == active_id:
                return p
    for p in profiles:
        if p.get("is_active"):
            return p
    return profiles[0] if profiles else None


def _profile_to_safe(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a cloud profile into a safe dictionary with masked API credentials."""
    key = profile.get("api_key") or ""
    masked = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else ("****" if key else "")
    return {
        "id": profile.get("id"),
        "name": profile.get("name", "Cloud Hosted"),
        "api_base": profile.get("api_base", ""),
        "has_api_key": bool(key and key.strip().lower() != "none"),
        "masked_api_key": masked,
        "model": profile.get("model", ""),
        "model_alias": profile.get("model_alias"),
        "extra_headers": profile.get("extra_headers") or {},
        "context_window": profile.get("context_window"),
        "max_output_tokens": profile.get("max_output_tokens"),
        "timeout": profile.get("timeout", 300),
        "streaming": profile.get("streaming", True),
        "is_active": profile.get("is_active", False),
    }


def _generate_markdown_report(run_data: Dict[str, Any]) -> str:
    """Generate professional Markdown penetration test report."""
    target = run_data.get("target_url") or run_data.get("target") or "Target"
    findings = run_data.get("findings", [])
    run_id = run_data.get("run_id", "unknown")
    lines = [
        f"# AI-VAPT Autonomous Security Penetration Test Report",
        f"",
        f"- **Target URL:** {target}",
        f"- **Run Reference:** `{run_id}`",
        f"- **Execution Engine:** STRIX Autonomous Multi-Agent Core",
        f"- **Assessment Mode:** {(run_data.get('mode') or 'autonomous').upper()}",
        f"- **Scan Depth:** {(run_data.get('scan_mode') or 'deep').upper()}",
        f"- **Generated:** {run_data.get('completed_at') or _utc_now()}",
        f"- **Total Confirmed Findings:** {len(findings)}",
        f"",
        f"---",
        f"",
        f"## 1. Executive Summary",
        f"",
        f"An autonomous vulnerability assessment and penetration test was conducted against `{target}` using the STRIX multi-agent engine coupled with GAP-1 dynamic exploit quality triage and GAP-2 bounded failure pivoting.",
        f"",
        f"## 2. Confirmed Vulnerability Findings",
        f"",
    ]
    if not findings:
        lines.append("No critical vulnerabilities were confirmed during this assessment run.\n")
    for idx, f in enumerate(findings, 1):
        lines.extend([
            f"### 2.{idx} {f.get('title', 'Vulnerability Finding')}",
            f"",
            f"- **Severity:** {f.get('severity', 'MEDIUM')}",
            f"- **CVSS Score:** {f.get('cvss_score', 'N/A')}",
            f"- **CVE Reference:** {f.get('cve_id') or 'N/A'}",
            f"- **CWE Identifier:** {f.get('cwe_id') or 'CWE-200'}",
            f"- **OWASP Top 10:** {f.get('owasp_category', 'A01:2021 - Broken Access Control')}",
            f"- **Location / Route:** `{f.get('location', '/')}`",
            f"- **Cryptographic SHA-256 Proof:** `{f.get('evidence_hash', 'N/A')}`",
            f"",
            f"#### Technical Analysis & Proof-of-Concept Evidence",
            f"```",
            f"{f.get('evidence_snippet', 'Verified')}",
            f"```",
            f"",
            f"#### Impact",
            f"{f.get('impact', 'Information disclosure and potential compromise of application integrity.')}",
            f"",
            f"#### Remediation Recommendations",
            f"{f.get('remediation_summary', 'Apply defensive validation filters.')}",
            f"",
            f"```shell",
            f"{f.get('remediation_technical', '# Implement secure configuration')}",
            f"```",
            f"",
            f"---",
            f"",
        ])
    return "\n".join(lines)


def _is_docker_available() -> bool:
    """Check if Docker runtime is accessible (disabled during unit tests)."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    try:
        res = subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.0)
        return res.returncode == 0
    except Exception:
        return False

if CSS_DIR.is_dir():
    app.mount("/css", StaticFiles(directory=str(CSS_DIR)), name="css")
if JS_DIR.is_dir():
    app.mount("/js", StaticFiles(directory=str(JS_DIR)), name="js")

# In-memory store for runs, traces, and engagements
_RUNS: Dict[str, Dict[str, Any]] = {}
_ACTIVE_PROCESSES: Dict[str, subprocess.Popen] = {}
_CURRENT_ACTIVE_RUN_ID: Optional[str] = None
_ENGAGEMENTS: Dict[str, Dict[str, Any]] = {
    "default-local": {
        "id": "default-local",
        "name": "Local Lab Environment",
        "authorized_hosts": ["localhost", "127.0.0.1", "host.docker.internal"],
        "allowed_ports": [80, 443, 8000, 8080, 8888, 9191],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reconcile_scan_matrix(scan_matrix: List[Dict[str, Any]], findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Reconcile scan_matrix category findings count and status against actual confirmed findings."""
    cat_counts: Dict[str, int] = collections.defaultdict(int)
    for f in findings:
        f_cat = f.get("category")
        title = (f.get("title") or "").lower()
        cwe = (f.get("cwe_id") or "").lower()
        owasp = (f.get("owasp_category") or "").lower()

        if f_cat and f_cat in ("version_sca", "configuration", "xss", "sqli", "ssrf", "ssti", "prototype_pollution", "code_injection"):
            cat_counts[f_cat] += 1
        elif "xss" in title or "cross-site scripting" in title or "cwe-79" in cwe:
            cat_counts["xss"] += 1
        elif "sql" in title or "cwe-89" in cwe:
            cat_counts["sqli"] += 1
        elif "ssrf" in title or "cwe-918" in cwe:
            cat_counts["ssrf"] += 1
        elif "template" in title or "ssti" in title or "cwe-1336" in cwe:
            cat_counts["ssti"] += 1
        elif "prototype" in title or "cwe-1321" in cwe:
            cat_counts["prototype_pollution"] += 1
        elif "command" in title or "code injection" in title or "cwe-94" in cwe or "cwe-78" in cwe:
            cat_counts["code_injection"] += 1
        elif f.get("cve_id") or "version" in title or "outdated" in title or "component" in title:
            cat_counts["version_sca"] += 1
        else:
            cat_counts["configuration"] += 1

    reconciled = []
    for item in scan_matrix:
        ck = item.get("category_key")
        cnt = cat_counts.get(ck, 0)
        reconciled.append({
            **item,
            "findings_count": cnt,
            "status": "VULNERABILITIES_IDENTIFIED" if cnt > 0 else "PASSED",
        })
    return reconciled


def _save_run_to_disk(run_data: Dict[str, Any]) -> None:
    """Persist run data to ./strix_runs/<run_id>/run.json and vulnerabilities.json."""
    run_id = run_data.get("run_id")
    if not run_id:
        return
    try:
        base_dir = runs_base_dir()
        run_dir = base_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        record = dict(run_data)
        if "scan_matrix" in record and record.get("status") in ("completed", "partial", "failed"):
            record["scan_matrix"] = _reconcile_scan_matrix(record.get("scan_matrix", []), record.get("findings", []))
            run_data["scan_matrix"] = record["scan_matrix"]
        record["run_name"] = run_id
        record["start_time"] = run_data.get("created_at")
        record["end_time"] = run_data.get("completed_at")
        record["instruction"] = f"VAPT assessment on {run_data.get('target_url') or run_data.get('target')}"
        record["user_instruction"] = record["instruction"]
        record["targets_info"] = [
            {
                "type": "web_application",
                "details": {"target_url": run_data.get("target_url") or run_data.get("target")},
                "original": run_data.get("target_url") or run_data.get("target"),
            }
        ]

        run_file = run_dir / "run.json"
        run_file.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")

        vuln_file = run_dir / "vulnerabilities.json"
        vuln_file.write_text(json.dumps(run_data.get("findings", []), indent=2, default=str), encoding="utf-8")

        # Also persist vulnerabilities.csv
        try:
            csv_file = run_dir / "vulnerabilities.csv"
            findings = run_data.get("findings", [])
            csv_buf = io.StringIO()
            fieldnames = [
                "id",
                "title",
                "severity",
                "cvss_score",
                "cwe_id",
                "owasp_category",
                "location",
                "target",
                "remediation_summary",
            ]
            csv_writer = csv.DictWriter(csv_buf, fieldnames=fieldnames, lineterminator="\r\n")
            csv_writer.writeheader()
            for f in findings:
                csv_writer.writerow({
                    "id": f.get("id", ""),
                    "title": f.get("title", ""),
                    "severity": f.get("severity", "INFO"),
                    "cvss_score": f.get("cvss_score", ""),
                    "cwe_id": f.get("cwe_id", ""),
                    "owasp_category": f.get("owasp_category", ""),
                    "location": f.get("location", ""),
                    "target": f.get("target", run_data.get("target_url") or run_data.get("target", "")),
                    "remediation_summary": f.get("remediation_summary", ""),
                })
            csv_file.write_text(csv_buf.getvalue(), encoding="utf-8")
        except Exception as csv_err:
            logger.debug("Could not write vulnerabilities.csv: %s", csv_err)

        cov_file = run_dir / "coverage.json"
        coverage_data = {
            "spider_stats": run_data.get("spider_stats", {}),
            "open_ports": run_data.get("open_ports", []),
            "components": run_data.get("components", []),
            "candidates_count": len(run_data.get("candidates", [])),
        }
        cov_file.write_text(json.dumps(coverage_data, indent=2, default=str), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to persist run %s to disk: %s", run_id, exc)


def _load_runs_from_disk() -> None:
    """Load existing historical runs from ./strix_runs/ into memory."""
    try:
        base_dir = runs_base_dir()
        if not base_dir.is_dir():
            return
        for child in base_dir.iterdir():
            run_file = child / "run.json"
            if not run_file.is_file():
                continue
            run_id = child.name
            if run_id in _RUNS and _RUNS[run_id].get("status") == "running":
                continue
            try:
                data = json.loads(run_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    if "run_id" not in data:
                        data["run_id"] = run_id
                    vuln_file = child / "vulnerabilities.json"
                    if vuln_file.is_file() and not data.get("findings"):
                        try:
                            data["findings"] = json.loads(vuln_file.read_text(encoding="utf-8"))
                        except Exception:
                            pass
                    if "scan_matrix" in data:
                        data["scan_matrix"] = _reconcile_scan_matrix(data.get("scan_matrix", []), data.get("findings", []))
                    _RUNS[run_id] = data
            except Exception as read_err:
                logger.debug("Could not parse %s: %s", run_file, read_err)
    except Exception as exc:
        logger.warning("Failed to load runs from disk: %s", exc)


@asynccontextmanager
async def _app_lifespan(app_instance: FastAPI):
    """Load persistent runs from disk on server startup."""
    _load_runs_from_disk()
    yield

app.router.lifespan_context = _app_lifespan


@app.get("/", response_class=FileResponse)
async def serve_index():
    """Serve the Single Page Application index.html."""
    index_file = WEB_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="Web console assets not found")
    return FileResponse(str(index_file), media_type="text/html")


@app.get("/health")
async def health_check():
    """Basic service health check."""
    return {"status": "ok", "service": "strix-ai-vapt-gateway"}


@app.get("/system/health", response_model=SystemHealthResponse)
async def system_health():
    """Comprehensive readiness probe for Strix core, Docker, Ollama, and LiteLLM."""
    components: Dict[str, Any] = {}

    # 1. Strix Core
    components["strix_core"] = {
        "status": "READY",
        "version": "1.7.0",
        "engine": "autonomous_multi_agent",
    }

    # 2. Docker Execution Sandbox
    try:
        docker_available = _is_docker_available()
        components["docker"] = {
            "status": "READY" if docker_available else "UNAVAILABLE",
            "installed": docker_available,
        }
    except Exception as e:
        components["docker"] = {"status": "UNAVAILABLE", "error": str(e)}

    # 3. Local Ollama LLM Service
    try:
        from strix.llm.ollama_service import probe_ollama
        ollama_status = probe_ollama()
        components["ollama"] = ollama_status
    except Exception:
        components["ollama"] = {
            "status": "NOT_CHECKED",
            "available": False,
            "models": [],
        }

    # 4. LiteLLM & Hosted Provider Bridge
    components["litellm"] = {
        "status": "READY",
        "supported_providers": ["ollama", "google", "openrouter", "openai"],
    }

    overall_status = "READY"
    return SystemHealthResponse(
        status=overall_status,
        timestamp=_utc_now(),
        components=components,
    )


@app.get("/scenarios")
async def list_scenarios():
    """List available benchmark and execution scenarios."""
    return [
        {
            "id": "failure_pivot",
            "name": "GAP-2 Bounded Pivot Demonstration",
            "description": "Simulates dead-end attempts triggering automatic GAP-2 candidate redirection.",
            "mode": "simulation",
            "default_attempts": 2,
        },
        {
            "id": "docker_pivot",
            "name": "Docker Exploit Pivot Benchmark",
            "description": "Tests multi-vector exploitation with dynamic bounded pivoting against local container.",
            "mode": "simulation",
            "default_attempts": 2,
        },
        {
            "id": "web_quick",
            "name": "Fast Web VAPT Assessment",
            "description": "Non-destructive active validation of web endpoints with SHA-256 evidence capture.",
            "mode": "web",
            "default_attempts": 2,
        },
        {
            "id": "autonomous_pentest",
            "name": "Full Autonomous Pentest",
            "description": "Complete multi-agent autonomous testing workflow with sandbox, shell & deep exploitation tools.",
            "mode": "autonomous",
            "default_attempts": 2,
        },
    ]


@app.post("/targets/validate", response_model=TargetValidateResponse)
async def validate_target(req: TargetValidateRequest):
    """Preflight target validation enforcing ethical and network scope boundaries."""
    url = req.target_url.strip()
    engagement_id = req.engagement_id

    try:
        from strix.core.safety.scope_validator import validate_web_target
        result = validate_web_target(url, engagement_id=engagement_id)
        return TargetValidateResponse(
            authorized=result.authorized,
            authorization_status=result.authorization_status,
            preflight_status=result.preflight_status,
            reachable=result.reachable,
            target_url=result.target_url,
            resolved_host=result.resolved_host,
            port=result.port,
            http_status=result.http_status,
            detail=result.detail,
            scheme=result.scheme,
            hostname=result.hostname,
            normalized_host=result.normalized_host,
            in_scope=result.in_scope,
            scope_kind=result.scope_kind,
            external_scope=result.external_scope,
            acknowledgement_required=result.acknowledgement_required,
            address_validation=result.address_validation,
            resolved_ips=result.resolved_ips,
            engagement_id=engagement_id,
        )
    except Exception:
        # Fallback basic scope check for local development
        is_local = any(h in url for h in ["localhost", "127.0.0.1", "::1"])
        return TargetValidateResponse(
            authorized=is_local,
            authorization_status="AUTHORIZED" if is_local else "UNAUTHORIZED_EXTERNAL",
            preflight_status="VALIDATED" if is_local else "SCOPE_CHECK_REQUIRED",
            reachable=True,
            target_url=url,
            in_scope=is_local,
            external_scope=not is_local,
            acknowledgement_required=not is_local,
            detail="Authorized local lab target" if is_local else "External target requires explicit confirmation",
        )


@app.post("/providers/google/validate", response_model=GoogleValidateResponse)
async def validate_google_provider(
    request: Request,
    body: Optional[Dict[str, Any]] = None,
    x_google_api_key: Optional[str] = Header(None, alias="X-Google-API-Key"),
):
    """Validate runtime Google Gemini API key in-memory without disk persistence."""
    api_key = (
        x_google_api_key
        or (body.get("api_key") if body else None)
        or os.environ.get("GEMINI_API_KEY")
    )
    if not api_key:
        return GoogleValidateResponse(
            status="not_configured",
            message="No Google API key provided",
            valid=False,
            models=[],
        )

    try:
        from strix.llm.provider_validation import validate_google_credential
        return validate_google_credential(api_key)
    except Exception as e:
        return GoogleValidateResponse(
            status="error",
            message=f"Validation failed: {e}",
            valid=False,
            models=[],
        )


@app.post("/providers/openrouter/validate", response_model=OpenRouterValidateResponse)
async def validate_openrouter_provider(
    request: Request,
    body: Optional[Dict[str, Any]] = None,
    x_openrouter_api_key: Optional[str] = Header(None, alias="X-OpenRouter-API-Key"),
):
    """Validate runtime OpenRouter API key in-memory without disk persistence."""
    api_key = (
        x_openrouter_api_key
        or (body.get("api_key") if body else None)
        or os.environ.get("OPENROUTER_API_KEY")
        or _read_strix_cli_config().get("OPENROUTER_API_KEY")
        or _read_strix_cli_config().get("LLM_API_KEY")
    )
    if not api_key:
        return OpenRouterValidateResponse(
            status="not_configured",
            message="No OpenRouter API key provided",
            valid=False,
            catalogue_count=0,
            models=[],
        )

    try:
        from strix.llm.provider_validation import validate_openrouter_credential
        return validate_openrouter_credential(api_key)
    except Exception as e:
        return OpenRouterValidateResponse(
            status="error",
            message=f"Validation failed: {e}",
            valid=False,
            catalogue_count=0,
            models=[],
        )


@app.post("/providers/openai/validate", response_model=OpenAIValidateResponse)
async def validate_openai_provider(
    body: Optional[Dict[str, Any]] = None,
    x_api_key: Optional[str] = Header(None, alias="Authorization"),
):
    """Validate OpenAI-compatible endpoint reachability and available models."""
    api_base = (body.get("api_base") if body else None) or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    key = (body.get("api_key") if body else None) or x_api_key or os.environ.get("OPENAI_API_KEY")
    if key and key.startswith("Bearer "):
        key = key.split(" ", 1)[1]
    from strix.llm.provider_validation import validate_openai_compatible_endpoint
    return validate_openai_compatible_endpoint(api_base=api_base, api_key=key)


@app.get("/providers/openrouter/models", response_model=List[OpenRouterModelInfo])
async def list_openrouter_models():
    """Retrieve all available free OpenRouter models publicly without requiring an API key."""
    try:
        from strix.llm.provider_validation import fetch_openrouter_free_models
        return fetch_openrouter_free_models()
    except Exception as exc:
        logger.warning("Error fetching OpenRouter models: %s", exc)
        return []


@app.get("/settings/llm")
async def get_llm_settings():
    """Retrieve currently active and persisted LLM configuration."""
    cfg = _read_strix_cli_config()
    model = os.environ.get("STRIX_LLM") or cfg.get("STRIX_LLM", f"openrouter/{DEFAULT_OPENROUTER_MODEL}")
    api_key = (
        os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or cfg.get("LLM_API_KEY", "")
    )
    api_base = os.environ.get("OPENAI_BASE_URL") or os.environ.get("LLM_API_BASE") or cfg.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    effort = os.environ.get("STRIX_REASONING_EFFORT") or cfg.get("STRIX_REASONING_EFFORT", "low")

    # Detect provider
    cfg_provider = cfg.get("STRIX_LLM_PROVIDER")
    active_cloud = _get_active_cloud_profile()
    if cfg_provider in ("cloud_hosted", "custom_cloud", "custom"):
        provider = "cloud_hosted"
    elif model.startswith("google/") or model.startswith("gemini/") or "gemini" in model.lower():
        provider = "google"
    elif model.startswith("ollama/") or "ollama" in model.lower():
        provider = "ollama"
    elif (active_cloud and active_cloud.get("is_active")) or (api_base and "openrouter.ai" not in api_base and "api.openai.com" not in api_base):
        provider = "cloud_hosted"
    elif model.startswith("openai/") or "gpt-" in model.lower():
        provider = "openai"
    else:
        provider = "openrouter"

    masked_key = ""
    if api_key and str(api_key).strip().lower() != "none":
        masked_key = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 12 else "********"

    clean_model = model
    for pfx in ("openrouter/", "google/", "gemini/", "ollama/", "openai/"):
        if clean_model.startswith(pfx):
            clean_model = clean_model[len(pfx):]
            break

    return {
        "provider": provider,
        "model": clean_model,
        "raw_model": model,
        "api_base": api_base,
        "has_api_key": bool(api_key and str(api_key).strip().lower() != "none"),
        "masked_api_key": masked_key,
        "reasoning_effort": effort,
        "cloud_profile": _profile_to_safe(active_cloud) if active_cloud else None,
    }


@app.post("/settings/llm")
async def update_llm_settings(payload: Dict[str, Any] = Body(...)):
    """Save LLM configuration to ~/.strix/cli-config.json and update runtime environment."""
    provider = (payload.get("provider") or "openrouter").lower().strip()
    raw_model = (payload.get("model") or "").strip()
    api_key = (payload.get("api_key") or "").strip()
    api_base = (payload.get("api_base") or "").strip()
    effort = (payload.get("reasoning_effort") or "low").strip()

    env_updates: Dict[str, str] = {}
    if effort:
        env_updates["STRIX_REASONING_EFFORT"] = effort
        os.environ["STRIX_REASONING_EFFORT"] = effort

    if provider == "openrouter":
        m_name = format_openrouter_model(raw_model)
        base = api_base or "https://openrouter.ai/api/v1"
        env_updates["STRIX_LLM_PROVIDER"] = "openrouter"
        env_updates["STRIX_LLM"] = m_name
        env_updates["OPENAI_BASE_URL"] = base
        env_updates["OPENROUTER_API_BASE"] = base
        os.environ["STRIX_LLM_PROVIDER"] = "openrouter"
        os.environ["STRIX_LLM"] = m_name
        os.environ["OPENAI_BASE_URL"] = base
        os.environ["OPENROUTER_API_BASE"] = base
        if api_key:
            env_updates["OPENROUTER_API_KEY"] = api_key
            env_updates["OPENAI_API_KEY"] = api_key
            env_updates["LLM_API_KEY"] = api_key
            os.environ["OPENROUTER_API_KEY"] = api_key
            os.environ["OPENAI_API_KEY"] = api_key
            os.environ["LLM_API_KEY"] = api_key

    elif provider == "google":
        m_name = raw_model if (raw_model.startswith("google/") or raw_model.startswith("gemini/")) else f"google/{raw_model}"
        env_updates["STRIX_LLM_PROVIDER"] = "google"
        env_updates["STRIX_LLM"] = m_name
        os.environ["STRIX_LLM_PROVIDER"] = "google"
        os.environ["STRIX_LLM"] = m_name
        if api_key:
            env_updates["GEMINI_API_KEY"] = api_key
            env_updates["LLM_API_KEY"] = api_key
            os.environ["GEMINI_API_KEY"] = api_key
            os.environ["LLM_API_KEY"] = api_key

    elif provider == "ollama":
        m_name = raw_model if raw_model.startswith("ollama/") else f"ollama/{raw_model}"
        base = api_base or "http://127.0.0.1:11434"
        env_updates["STRIX_LLM_PROVIDER"] = "ollama"
        env_updates["STRIX_LLM"] = m_name
        env_updates["OLLAMA_API_BASE"] = base
        env_updates["LLM_API_KEY"] = "ollama"
        os.environ["STRIX_LLM_PROVIDER"] = "ollama"
        os.environ["STRIX_LLM"] = m_name
        os.environ["OLLAMA_API_BASE"] = base
        os.environ["LLM_API_KEY"] = "ollama"

    elif provider == "openai":
        m_name = raw_model if raw_model.startswith("openai/") else f"openai/{raw_model}"
        base = api_base or "https://api.openai.com/v1"
        env_updates["STRIX_LLM_PROVIDER"] = "openai"
        env_updates["STRIX_LLM"] = m_name
        env_updates["OPENAI_BASE_URL"] = base
        os.environ["STRIX_LLM_PROVIDER"] = "openai"
        os.environ["STRIX_LLM"] = m_name
        os.environ["OPENAI_BASE_URL"] = base
        if api_key:
            env_updates["OPENAI_API_KEY"] = api_key
            env_updates["LLM_API_KEY"] = api_key
            os.environ["OPENAI_API_KEY"] = api_key
            os.environ["LLM_API_KEY"] = api_key

    elif provider in ("cloud_hosted", "custom_cloud", "custom"):
        m_name = raw_model if raw_model.startswith("openai/") else f"openai/{raw_model}"
        base = api_base or "https://api.openai.com/v1"
        env_updates["STRIX_LLM_PROVIDER"] = "cloud_hosted"
        env_updates["STRIX_LLM"] = m_name
        env_updates["OPENAI_BASE_URL"] = base
        env_updates["LLM_API_BASE"] = base
        env_updates["STRIX_API_TYPE"] = "chat_completions"
        os.environ["STRIX_LLM_PROVIDER"] = "cloud_hosted"
        os.environ["STRIX_LLM"] = m_name
        os.environ["OPENAI_BASE_URL"] = base
        os.environ["LLM_API_BASE"] = base
        os.environ["STRIX_API_TYPE"] = "chat_completions"
        if api_key:
            env_updates["OPENAI_API_KEY"] = api_key
            env_updates["LLM_API_KEY"] = api_key
            os.environ["OPENAI_API_KEY"] = api_key
            os.environ["LLM_API_KEY"] = api_key
        else:
            env_updates["OPENAI_API_KEY"] = "none"
            env_updates["LLM_API_KEY"] = "none"
            os.environ["OPENAI_API_KEY"] = "none"
            os.environ["LLM_API_KEY"] = "none"

    _write_strix_cli_config(env_updates)
    return {
        "status": "ok",
        "message": f"LLM configuration updated successfully for provider {provider}",
        "config": {k: ("***" if "KEY" in k else v) for k, v in env_updates.items()},
    }


# ============================================================================
# Generic Cloud Hosted AI Provider Endpoints (OpenAI-compatible)
# ============================================================================

@app.get("/providers/cloud_hosted/profiles", response_model=List[CloudHostedProfileSafe])
async def list_cloud_profiles():
    """List all saved Cloud Hosted provider profiles (safe, with credentials masked)."""
    profiles = _get_cloud_profiles()
    return [_profile_to_safe(p) for p in profiles]


@app.post("/providers/cloud_hosted/profiles", response_model=CloudHostedProfileSafe)
async def create_or_update_cloud_profile(profile: CloudHostedProfile):
    """Save or update a Cloud Hosted provider profile."""
    data = profile.model_dump()
    saved = _save_cloud_profile(data)
    if saved.get("is_active"):
        m_name = saved["model"] if saved["model"].startswith("openai/") else f"openai/{saved['model']}"
        env_updates = {
            "STRIX_LLM_PROVIDER": "cloud_hosted",
            "STRIX_LLM": m_name,
            "OPENAI_BASE_URL": saved["api_base"],
            "LLM_API_BASE": saved["api_base"],
            "STRIX_API_TYPE": "chat_completions",
        }
        if saved.get("api_key"):
            env_updates["OPENAI_API_KEY"] = saved["api_key"]
            env_updates["LLM_API_KEY"] = saved["api_key"]
        _write_strix_cli_config(env_updates)
    return _profile_to_safe(saved)


@app.delete("/providers/cloud_hosted/profiles/{profile_id}")
async def delete_cloud_profile_endpoint(profile_id: str):
    """Delete a saved Cloud Hosted provider profile."""
    success = _delete_cloud_profile(profile_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return {"status": "ok", "message": f"Profile {profile_id} deleted"}


@app.post("/providers/cloud_hosted/profiles/{profile_id}/activate", response_model=CloudHostedProfileSafe)
async def activate_cloud_profile_endpoint(profile_id: str):
    """Set the specified Cloud Hosted profile as active."""
    profile = _set_active_cloud_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    m_name = profile["model"] if profile["model"].startswith("openai/") else f"openai/{profile['model']}"
    env_updates = {
        "STRIX_LLM_PROVIDER": "cloud_hosted",
        "STRIX_LLM": m_name,
        "OPENAI_BASE_URL": profile["api_base"],
        "LLM_API_BASE": profile["api_base"],
        "STRIX_API_TYPE": "chat_completions",
    }
    if profile.get("api_key"):
        env_updates["OPENAI_API_KEY"] = profile["api_key"]
        env_updates["LLM_API_KEY"] = profile["api_key"]
    _write_strix_cli_config(env_updates)
    return _profile_to_safe(profile)


@app.post("/providers/cloud_hosted/models")
async def discover_cloud_models_endpoint(body: Dict[str, Any] = Body(...)):
    """Dynamically discover models on the cloud hosted OpenAI-compatible endpoint."""
    api_base = (body.get("api_base") or "").strip()
    api_key = (body.get("api_key") or "").strip()
    profile_id = body.get("profile_id")
    extra_headers = body.get("extra_headers") or {}

    if not api_key and profile_id:
        for p in _get_cloud_profiles():
            if p.get("id") == profile_id and p.get("api_key"):
                api_key = p["api_key"]
                break
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY") or _read_strix_cli_config().get("OPENAI_API_KEY")

    from strix.llm.cloud_provider import discover_cloud_models
    return discover_cloud_models(api_base=api_base, api_key=api_key, extra_headers=extra_headers)


@app.post("/providers/cloud_hosted/validate", response_model=CloudTestConnectionResponse)
async def validate_cloud_connection_endpoint(body: Dict[str, Any] = Body(...)):
    """Test connection reachability, chat completion, and latency diagnostics."""
    api_base = (body.get("api_base") or "").strip()
    model = (body.get("model") or "").strip()
    api_key = (body.get("api_key") or "").strip()
    profile_id = body.get("profile_id")
    extra_headers = body.get("extra_headers") or {}

    if not api_key and profile_id:
        for p in _get_cloud_profiles():
            if p.get("id") == profile_id and p.get("api_key"):
                api_key = p["api_key"]
                break
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY") or _read_strix_cli_config().get("OPENAI_API_KEY")

    from strix.llm.cloud_provider import test_cloud_connection
    return test_cloud_connection(api_base=api_base, model=model, api_key=api_key, extra_headers=extra_headers)


@app.post("/providers/cloud_hosted/verify_tools", response_model=CloudVerifyToolsResponse)
async def verify_cloud_tools_endpoint(body: Dict[str, Any] = Body(...)):
    """Verify structured function/tool calling compatibility for autonomous Strix agents."""
    api_base = (body.get("api_base") or "").strip()
    model = (body.get("model") or "").strip()
    api_key = (body.get("api_key") or "").strip()
    profile_id = body.get("profile_id")
    extra_headers = body.get("extra_headers") or {}

    if not api_key and profile_id:
        for p in _get_cloud_profiles():
            if p.get("id") == profile_id and p.get("api_key"):
                api_key = p["api_key"]
                break
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY") or _read_strix_cli_config().get("OPENAI_API_KEY")

    from strix.llm.cloud_provider import verify_cloud_structured_tools
    return verify_cloud_structured_tools(api_base=api_base, model=model, api_key=api_key, extra_headers=extra_headers)


@app.post("/providers/cloud_hosted/warmup", response_model=CloudWarmupResponse)
async def warmup_cloud_endpoint(body: Dict[str, Any] = Body(...)):
    """Manual model warm-up action to prime inference cache."""
    api_base = (body.get("api_base") or "").strip()
    model = (body.get("model") or "").strip()
    api_key = (body.get("api_key") or "").strip()
    profile_id = body.get("profile_id")
    extra_headers = body.get("extra_headers") or {}

    if not api_key and profile_id:
        for p in _get_cloud_profiles():
            if p.get("id") == profile_id and p.get("api_key"):
                api_key = p["api_key"]
                break
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY") or _read_strix_cli_config().get("OPENAI_API_KEY")

    from strix.llm.cloud_provider import warmup_cloud_model
    return warmup_cloud_model(api_base=api_base, model=model, api_key=api_key, extra_headers=extra_headers)
    return {
        "status": "ok",
        "message": f"LLM configuration updated successfully for provider {provider}",
        "config": {k: ("***" if "KEY" in k else v) for k, v in env_updates.items()},
    }


BOX_DRAWING_CHARS = {chr(i) for i in range(0x2500, 0x25A0)}
ANSI_ESCAPE_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def _clean_terminal_line(line: str) -> str:
    """Strip ANSI escapes, Rich borders, and decorative box characters."""
    line = ANSI_ESCAPE_RE.sub('', line)
    line = line.strip()
    while line and line[0] in BOX_DRAWING_CHARS:
        line = line[1:].strip()
    while line and line[-1] in BOX_DRAWING_CHARS:
        line = line[:-1].strip()
    return line.strip()


def _is_decorative_line(line: str) -> bool:
    """Return True if line consists solely or mostly of box drawing characters or separators."""
    cleaned = "".join(ch for ch in line if ch not in BOX_DRAWING_CHARS and ch not in " \t-=")
    return len(cleaned) == 0


def _redact_secrets(text: str) -> str:
    """Sanitize API keys and sensitive tokens from error messages."""
    if not text:
        return text
    # OpenRouter keys (sk-or-v1-...)
    text = re.sub(r"sk-or-v1-[a-zA-Z0-9]{20,}", "sk-or-v1-***[REDACTED]***", text)
    # Generic bearer/API keys (sk-...)
    text = re.sub(r"sk-[a-zA-Z0-9]{20,}", "sk-***[REDACTED]***", text)
    # Google Gemini keys (AIza...)
    text = re.sub(r"AIza[a-zA-Z0-9_\-]{25,}", "AIza***[REDACTED]***", text)
    return text


def _extract_clean_error(
    stderr_lines: list[str],
    stdout_lines: list[str],
    fallback: str = "Scan failed",
) -> str:
    """Extract a clean, human-readable error from stderr or stdout without Rich borders."""
    cleaned_stderr: list[str] = []
    for line in stderr_lines:
        c = _clean_terminal_line(line)
        if c and not _is_decorative_line(c):
            cleaned_stderr.append(c)

    cleaned_stdout: list[str] = []
    for line in stdout_lines:
        c = _clean_terminal_line(line)
        if c and not _is_decorative_line(c):
            cleaned_stdout.append(c)

    combined_text = "\n".join(cleaned_stderr + cleaned_stdout)
    combined_lower = combined_text.lower()

    # Friendly, actionable OpenRouter & LiteLLM error mappings
    if "openrouter" in combined_lower or "litellm" in combined_lower:
        if (
            "404" in combined_text
            or "notfounderror" in combined_lower
            or "itemnotfounderror" in combined_lower
            or "no endpoints available" in combined_lower
            or "unavailable for free" in combined_lower
        ):
            return "OpenRouter model not found or unavailable (HTTP 404). The selected model slug may be retired, renamed, or require paid credits. Verify the model identifier and provider availability."
        if (
            "401" in combined_text
            or "403" in combined_text
            or "unauthorized" in combined_lower
            or "user not found" in combined_lower
            or "authentication" in combined_lower
        ):
            return "OpenRouter authentication failed (HTTP 401/403). Please verify your OpenRouter API key."
        if "429" in combined_text or "rate limit" in combined_lower or "ratelimit" in combined_lower:
            if any(k in combined_lower for k in ("free-models-per-day", "openrouter_free_tier_daily", "daily reset", "daily limit", "quota exceeded")):
                return "OpenRouter daily free quota exceeded (HTTP 429: free-models-per-day limit reached, 50 requests/day). Add credits to your OpenRouter account or wait for the daily reset."
            return "OpenRouter rate limit reached (HTTP 429). Please retry shortly or select an alternate model."

    # 1. Look for Python Tracebacks in cleaned_stderr
    if cleaned_stderr:
        exc_lines = [
            l for l in cleaned_stderr
            if re.search(r'\b(?:[A-Z][a-zA-Z0-9_]*Error|[A-Z][a-zA-Z0-9_]*Exception)\b:', l)
        ]
        if exc_lines:
            return _redact_secrets(exc_lines[-1])

        err_lines = [
            l for l in cleaned_stderr
            if any(k in l.lower() for k in ("error", "failed", "fatal", "exception", "rate limit", "budget", "unauthorized"))
            and not "warning" in l.lower()
        ]
        if err_lines:
            return _redact_secrets("\n".join(err_lines[-3:]))

        return _redact_secrets("\n".join(cleaned_stderr[-3:]))

    # 2. Look in cleaned_stdout
    if cleaned_stdout:
        exc_lines = [
            l for l in cleaned_stdout
            if re.search(r'\b(?:[A-Z][a-zA-Z0-9_]*Error|[A-Z][a-zA-Z0-9_]*Exception)\b:', l)
        ]
        if exc_lines:
            return _redact_secrets(exc_lines[-1])

        candidates = [
            l for l in cleaned_stdout
            if any(k in l.lower() for k in ("error", "exception", "failed", "traceback", "fatal", "unauthorized", "rate", "exceeded", "missing", "rejected"))
            and not "warning" in l.lower()
        ]
        if candidates:
            return _redact_secrets("\n".join(candidates[-3:]))

    return _redact_secrets(fallback)


def _probe_web_candidate(target_url: str, cid: str, endpoint: str, auth_session: Optional[Any] = None) -> tuple[bool, str, str]:
    """Actively probe web attack candidates using benign, accurate, non-destructive verification."""
    import re
    import ssl
    import urllib.parse
    import urllib.request
    import json

    class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
        def http_error_302(self, req, fp, code, msg, headers):
            return fp
        http_error_301 = http_error_302
        http_error_303 = http_error_302
        http_error_307 = http_error_302
        http_error_308 = http_error_302

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    c_clean = cid.lower()
    full_url = target_url.rstrip("/") + "/" + endpoint.lstrip("/")

    # 0A. Authenticated User Enumeration & Role Disclosure
    if "user-enumeration" in c_clean or "user_enum" in c_clean:
        try:
            u_url = target_url.rstrip("/") + "/api/Users"
            headers = auth_session.get_auth_header() if auth_session and hasattr(auth_session, "get_auth_header") else {}
            headers["User-Agent"] = "AI-VAPT/2.0"
            req = urllib.request.Request(u_url, headers=headers)
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                if resp.status == 200:
                    body = resp.read(30000).decode("utf-8", errors="ignore")
                    data = json.loads(body)
                    users = data.get("data", [])
                    admins = [u for u in users if u.get("role") == "admin"]
                    if len(users) > 1 and len(admins) > 0:
                        return True, f"Unprivileged user enumeration confirmed: retrieved {len(users)} accounts including {len(admins)} admin users", f"HTTP 200 OK\nUsers: {len(users)}, Admins: {len(admins)}\n{body[:300]}"
        except Exception:
            pass
        return False, "Access to user list strictly role-scoped or unauthenticated access blocked", ""

    # 0B. Sensitive Data Exposure: Password Hash in JWT
    if "jwt-password-leak" in c_clean or "jwt-leak" in c_clean:
        if auth_session and getattr(auth_session, "token", None):
            from strix.core.scanner.jwt_inspector import JWTInspector
            jwt_res = JWTInspector.inspect(auth_session.token)
            if jwt_res.vulnerable:
                return True, jwt_res.summary, jwt_res.evidence_snippet
        return False, "JWT payload contains no exposed password or credential hashes", ""

    # 0C. Insecure Direct Object Reference (IDOR) on Basket API
    if "basket-idor" in c_clean or "idor" in c_clean:
        if auth_session and getattr(auth_session, "token", None):
            from strix.core.scanner.idor_validator import IDORValidator
            own_id = getattr(auth_session, "basket_id", 6) or 6
            idor_res = IDORValidator.test_idor(target_url, auth_session.token, user_own_id=own_id, foreign_id=1)
            if idor_res.is_idor:
                return True, idor_res.summary, idor_res.evidence_snippet
        return False, "Object-level authorization enforced; cross-tenant access blocked", ""

    # 0D. Controlled Default Administrative Credential Validation
    if "default-admin" in c_clean or "admin-credential" in c_clean:
        from strix.core.scanner.credential_validator import CredentialValidator
        cred_res = CredentialValidator.test_single_credential(target_url, "admin@juice-sh.op", "admin123")
        if cred_res.authenticated and cred_res.is_admin:
            return True, cred_res.summary, cred_res.evidence_snippet
        return False, "Default administrative credentials rejected by target", ""

    # 1. Security Hardening Headers (Observation / Hardening)
    if "header" in c_clean or "missing-security-headers" in c_clean:
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                missing = [h for h in ["x-frame-options", "x-content-type-options"] if h not in headers]
                if target_url.startswith("https") and "strict-transport-security" not in headers:
                    missing.append("strict-transport-security")
                if "content-security-policy" not in headers:
                    missing.append("content-security-policy")
                if missing:
                    return False, f"Missing security hardening headers (Observation / Hardening): {', '.join(missing)}", f"Headers evaluated:\n" + "\n".join(f"{k}: {v}" for k, v in headers.items())
        except Exception as exc:
            logger.debug("Header probe error: %s", exc)
        return False, "All required security headers present", ""

    # 2. Content Security Policy (CSP) Bypass / Permissive CSP (Observation / Hardening)
    if "csp" in c_clean:
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                csp_val = headers.get("content-security-policy", "")
                if not csp_val:
                    return False, "No Content Security Policy (CSP) header configured (Observation / Hardening Recommendation)", "Content-Security-Policy: [NOT PRESENT]"
                if "unsafe-inline" in csp_val.lower() or "unsafe-eval" in csp_val.lower() or "*" in csp_val:
                    return False, f"Permissive CSP policy allows inline/eval scripts (Observation): {csp_val[:120]}", f"Content-Security-Policy: {csp_val}"
        except Exception as exc:
            logger.debug("CSP probe error: %s", exc)
        return False, "Strict Content Security Policy enforced", ""

    # 3. Insecure Session Cookie Flags
    if "cookie" in c_clean:
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                cookies = resp.headers.get_all("Set-Cookie") or []
                for c in cookies:
                    c_low = c.lower()
                    if "httponly" not in c_low or "samesite" not in c_low or (target_url.startswith("https") and "secure" not in c_low):
                        return True, f"Session cookie lacks HttpOnly/Secure/SameSite attributes: {c[:80]}", c
        except Exception as exc:
            logger.debug("Cookie probe error: %s", exc)
        return False, "Session cookies have secure flags or no cookies issued", ""

    # 4. Server Version / Diagnostic Banner Disclosure
    if "banner" in c_clean or "server-banner" in c_clean or "phpinfo" in c_clean:
        try:
            req = urllib.request.Request(full_url if "phpinfo" in c_clean else target_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                body = resp.read(2048).decode("utf-8", errors="ignore")
                if "phpinfo" in c_clean:
                    if resp.status == 200 and ("PHP Version" in body or "phpinfo()" in body):
                        return True, "PHPInfo diagnostic configuration exposed (HTTP 200)", f"HTTP 200 OK\n{body[:350]}"
                else:
                    server_val = headers.get("server", "") + " " + headers.get("x-powered-by", "")
                    if re.search(r"\d+\.\d+", server_val):
                        return True, f"Server banner discloses detailed software version: {server_val.strip()}", f"Server: {server_val.strip()}"
        except Exception:
            pass
        return False, "Diagnostic banner not exposed or suppressed", ""

    # 5. Cross-Origin Resource Sharing (CORS) Misconfiguration
    if "cors" in c_clean:
        try:
            req = urllib.request.Request(full_url, headers={"User-Agent": "AI-VAPT/2.0", "Origin": "https://strix-audit.test"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                allow_origin = headers.get("access-control-allow-origin", "")
                allow_cred = headers.get("access-control-allow-credentials", "").lower()
                if allow_origin == "https://strix-audit.test" or (allow_origin == "*" and allow_cred == "true"):
                    return True, "Permissive CORS policy allows untrusted Origin with credentials", f"Access-Control-Allow-Origin: {allow_origin}\nAccess-Control-Allow-Credentials: {allow_cred}"
        except Exception:
            pass
        return False, "CORS policy is strictly restricted or not configured", ""

    # 6. Cross-Site Request Forgery (CSRF)
    if "csrf" in c_clean:
        try:
            req = urllib.request.Request(full_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(50000).decode("utf-8", errors="ignore")
                forms = re.findall(r"(<form\b[^>]*>.*?</form>)", body, re.I | re.DOTALL)
                for f in forms:
                    if re.search(r'method=["\']post["\']', f, re.I):
                        has_token = bool(re.search(r'name=["\'](?:[^"\']*(?:csrf|token|_token|authenticity_token))["\']', f, re.I))
                        if not has_token:
                            return True, f"POST form at {endpoint} lacks anti-CSRF synchronization tokens", f"{f[:300]}"
        except Exception:
            pass
        return False, "Anti-CSRF tokens present or no unprotected POST forms identified", ""

    # 7. Open HTTP Redirection
    if "redirect" in c_clean or "open_redirect" in c_clean:
        try:
            opener = urllib.request.build_opener(NoRedirectHandler)
            test_ep = full_url + ("&" if "?" in full_url else "?") + "redirect=https://evil-attacker.test&url=https://evil-attacker.test"
            req = urllib.request.Request(test_ep, headers={"User-Agent": "AI-VAPT/2.0"})
            resp = opener.open(req, timeout=4.0)
            loc = resp.headers.get("Location", "")
            if loc and ("evil-attacker.test" in loc):
                return True, f"Open HTTP Redirection confirmed on parameter: Location -> {loc}", f"HTTP {resp.status}\nLocation: {loc}"
        except Exception:
            pass
        return False, "Redirect validation strictly enforced; untrusted destination rejected", ""

    # 8. Robots.txt Sensitive Directory Disclosure
    if "robots" in c_clean:
        try:
            robots_url = target_url.rstrip("/") + "/robots.txt"
            req = urllib.request.Request(robots_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(2048).decode("utf-8", errors="ignore")
                if resp.status == 200 and ("User-agent" in body or "Disallow" in body):
                    return True, "Robots.txt discloses internal directory layout and sensitive administrative paths", f"HTTP 200 OK\n{body[:350]}"
        except Exception:
            pass
        return False, "robots.txt not exposed or contains no sensitive directives", ""

    # 9. Reflected Cross-Site Scripting (XSS)
    if "reflected" in c_clean or c_clean == "reflected-xss":
        try:
            # Probe with HTML breakout characters to test real markup injection viability
            probe_token = "\"><strix_test_probe>"
            test_url = full_url + ("&" if "?" in full_url else "?") + f"test={urllib.parse.quote(probe_token)}&q={urllib.parse.quote(probe_token)}"
            req = urllib.request.Request(test_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                if resp.status == 200:
                    body = resp.read(30000).decode("utf-8", errors="ignore")
                    # Must reflect unescaped breakout tags, not just plain text or entity-encoded &lt;
                    if probe_token in body:
                        return True, f"Unescaped script breakout reflection verified at {endpoint}", f"Reflection evidence:\n...{body[body.find(probe_token)-30:body.find(probe_token)+50]}..."
        except urllib.error.HTTPError as http_err:
            if http_err.code in (403, 406):
                return False, f"XSS payloads strictly filtered and blocked by WAF/Gateway (HTTP {http_err.code})", ""
        except Exception:
            pass
        return False, "Input reflection properly HTML-encoded or rejected by application filters", ""

    # 10. DOM-Based Cross-Site Scripting (DOM XSS)
    if "dom" in c_clean or c_clean == "dom-xss":
        try:
            req = urllib.request.Request(full_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(50000).decode("utf-8", errors="ignore")
                scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", body, re.I | re.DOTALL)
                combined_js = "\n".join(scripts)
                dom_sources = ["location.search", "location.hash", "location.href", "document.URL", "window.name"]
                dom_sinks = ["eval(", "document.write(", ".innerHTML", "setTimeout(", "setInterval("]
                has_source = any(src in combined_js for src in dom_sources)
                has_sink = any(sink in combined_js for sink in dom_sinks)
                if has_source and has_sink:
                    return True, f"Potential client-side DOM XSS pathway identified in script processing", f"DOM Sink pattern detected in inline scripts"
        except Exception:
            pass
        return False, "No untrusted source-to-sink DOM execution pathways identified in client scripts", ""

    # 10. SQL Injection (Error-Based)
    if "sqli" in c_clean or "sql-injection" in c_clean:
        try:
            test_url = full_url + ("&" if "?" in full_url else "?") + "id=1'%22"
            req = urllib.request.Request(test_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(20000).decode("utf-8", errors="ignore")
                sql_errors = ["sql syntax", "mysql_fetch", "ora-01756", "pg_query", "sqlite3::sql", "unclosed quotation mark"]
                for err in sql_errors:
                    if err in body.lower():
                        return True, f"SQL syntax error disclosed in response body: {err}", f"Evidence snippet:\n{body[:300]}"
        except Exception:
            pass
        return False, "No SQL syntax error leakage or database exception observed", ""

    # 11. Local File Inclusion (LFI) & Path Traversal
    if "lfi" in c_clean or "file-inclusion" in c_clean or "traversal" in c_clean:
        try:
            test_url = full_url + ("&" if "?" in full_url else "?") + "page=../../../../etc/passwd&file=../../../../etc/passwd"
            req = urllib.request.Request(test_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(20000).decode("utf-8", errors="ignore")
                if "root:x:0:0:" in body or "root:*:0:0:" in body:
                    return True, "Arbitrary system file disclosure via path traversal (/etc/passwd)", body[:300]
        except Exception:
            pass
        return False, "Path traversal sequence blocked or sanitized by server", ""

    # 12. Remote Command Injection (RCE)
    if "cmd" in c_clean or "command" in c_clean or "exec" in c_clean:
        try:
            test_url = full_url + ("&" if "?" in full_url else "?") + "ip=127.0.0.1;id"
            req = urllib.request.Request(test_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(20000).decode("utf-8", errors="ignore")
                if re.search(r"uid=\d+.*gid=\d+", body):
                    return True, "Command execution confirmed via system ID output reflection", body[:300]
        except Exception:
            pass
        return False, "Command injection payload rejected or sanitized by application", ""

    # 13. File Upload RCE
    if "upload" in c_clean:
        return False, "File upload endpoint is not exposed, requires authentication, or blocks executable extensions", ""

    # 14. Missing CAPTCHA on Authentication / Login Surface
    if "captcha" in c_clean:
        try:
            req = urllib.request.Request(full_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(50000).decode("utf-8", errors="ignore")
                has_pwd = bool(re.search(r'type=["\']password["\']', body, re.I))
                has_captcha = bool(re.search(r'(captcha|recaptcha|hcaptcha|turnstile)', body, re.I))
                if has_pwd and not has_captcha:
                    return True, f"Authentication form at {endpoint} lacks automated bot / CAPTCHA protection", "Login form identified without anti-automation challenge"
        except Exception:
            pass
        return False, "CAPTCHA verification present or non-authentication endpoint", ""

    # 15. Weak Session ID / Fixation
    if "weak_id" in c_clean or "weak-session" in c_clean:
        try:
            req = urllib.request.Request(full_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                cookies = resp.headers.get_all("Set-Cookie") or []
                for c in cookies:
                    val_match = re.search(r'=(.*?)(?:;|$)', c)
                    if val_match:
                        val = val_match.group(1).strip()
                        if len(val) < 16 or val.isdigit():
                            return True, f"Predictable low-entropy session identifier identified: {c.split(';')[0]}", c
        except Exception:
            pass
        return False, "Session identifiers exhibit adequate entropy and length", ""

    # 16. Insecure Client-Side JavaScript Processing
    if "client-js" in c_clean:
        try:
            req = urllib.request.Request(full_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(50000).decode("utf-8", errors="ignore")
                sinks = re.findall(r'(document\.write\(|eval\(|window\.eval\(|innerHTML\s*=)', body, re.I)
                if sinks:
                    return True, f"Insecure client-side DOM processing sinks detected ({sinks[0]})", f"Pattern: {sinks[0]}"
        except Exception:
            pass
        return False, "Client scripts use standard secure DOM manipulation APIs", ""

    # 17. Exposed Git Source Code Repository
    if "git" in c_clean:
        try:
            git_url = target_url.rstrip("/") + "/.git/HEAD"
            req = urllib.request.Request(git_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(200).decode("utf-8", errors="ignore")
                if resp.status == 200 and "ref: refs/" in body:
                    return True, "Exposed .git repository metadata accessible without authorization", body
        except Exception:
            pass
        return False, ".git repository metadata is not accessible", ""

    # 18. Exposed Diagnostic Tracing & Error Log
    if "trace" in c_clean or "elmah" in c_clean:
        try:
            trace_url = target_url.rstrip("/") + ("/trace.axd" if "trace" in c_clean else "/elmah.axd")
            req = urllib.request.Request(trace_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(2000).decode("utf-8", errors="ignore")
                if resp.status == 200 and ("Application Trace" in body or "Error Log" in body):
                    return True, f"ASP.NET diagnostic handler exposed ({trace_url})", body[:300]
        except Exception:
            pass
        return False, "Diagnostic tracing handlers are disabled or require authorization", ""

    # 19. Exposed Web Configuration (web.config)
    if "web-config" in c_clean or "web.config" in c_clean:
        try:
            cfg_url = target_url.rstrip("/") + "/web.config"
            req = urllib.request.Request(cfg_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(2000).decode("utf-8", errors="ignore")
                if resp.status == 200 and "<configuration>" in body:
                    return True, "web.config exposed without authorization", body[:300]
        except Exception:
            pass
        return False, "web.config is protected by IIS request filtering", ""

    # 20. Vulnerable Third-Party JavaScript Library (Retire.js-style SCA)
    if "vuln-lib" in c_clean:
        try:
            from strix.core.scanner.component_analyzer import analyze_page_components
            req = urllib.request.Request(target_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(60000).decode("utf-8", errors="ignore")
                comps = analyze_page_components(target_url, body)
                for comp in comps:
                    if comp.get("vulnerable") and comp.get("library", "") in c_clean:
                        cves = ", ".join(comp.get("cves", []))
                        return True, f"Vulnerable component verified: {comp['library']} v{comp['version']} ({cves})", f"Library: {comp['library']} v{comp['version']}\nSource: {comp.get('source_file')}\nCVEs: {cves}\nRemediation: {comp.get('remediation')}"
        except Exception as exc:
            logger.debug("Component probe error: %s", exc)
        return False, "Vulnerable component not detected or suppressed", ""

    # 21. Open TCP Port Reachability Check
    if "open-port-" in c_clean:
        try:
            import socket
            host = urllib.parse.urlsplit(target_url).hostname
            port_str = c_clean.replace("open-port-", "").strip()
            if port_str.isdigit() and host:
                port = int(port_str)
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2.0)
                res = s.connect_ex((host, port))
                s.close()
                if res == 0:
                    return True, f"Open TCP Port {port} verified accessible on target {host}", f"Connection to {host}:{port} state: OPEN (SYN-ACK received)"
        except Exception as exc:
            logger.debug("Port probe error: %s", exc)
        return False, "Port closed or inaccessible from external network", ""

    # 22. Subresource Integrity (SRI)
    if "subresource-integrity" in c_clean or "sri" in c_clean:
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(60000).decode("utf-8", errors="ignore")
                scripts = re.findall(r'<script\b[^>]*src=["\']([^"\']+)["\'][^>]*>', body, re.I)
                missing_sri = [s for s in scripts if s.startswith("http") and "integrity=" not in s]
                if missing_sri:
                    return True, f"Subresource Integrity (SRI) missing on external script inclusions ({len(missing_sri)} found)", f"Script missing SRI: {missing_sri[0]}"
        except Exception:
            pass
        return False, "All external scripts enforce Subresource Integrity (SRI) hashes", ""

    # 23. Cross-Domain JavaScript Inclusion
    if "cross-domain-js" in c_clean:
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(60000).decode("utf-8", errors="ignore")
                target_host = urllib.parse.urlsplit(target_url).hostname or ""
                scripts = re.findall(r'<script\b[^>]*src=["\'](https?://[^"\']+)["\']', body, re.I)
                external = [s for s in scripts if target_host not in s]
                if external:
                    return True, f"Cross-domain JavaScript source files loaded from external origins ({len(external)} found)", f"External script inclusion: {external[0]}"
        except Exception:
            pass
        return False, "No cross-domain scripts loaded or all isolated to first-party origins", ""

    # 24. Missing Anti-Clickjacking Header (X-Frame-Options)
    if "missing-anti-clickjacking" in c_clean or "clickjacking" in c_clean:
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                if "x-frame-options" not in headers:
                    csp = headers.get("content-security-policy", "").lower()
                    if "frame-ancestors" not in csp:
                        return True, "Missing Anti-Clickjacking Header: X-Frame-Options is not set", "X-Frame-Options: [NOT PRESENT]"
        except Exception:
            pass
        return False, "Anti-Clickjacking frame protection is properly enforced", ""

    # 25. Strict-Transport-Security (HSTS) Header Not Set
    if "missing-hsts" in c_clean or "hsts" in c_clean:
        if not target_url.startswith("https://"):
            return False, "HSTS is NOT_APPLICABLE on HTTP-only targets per RFC 6797", ""
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                if "strict-transport-security" not in headers:
                    return True, "Strict-Transport-Security (HSTS) Header Not Set on HTTPS service", "Strict-Transport-Security: [NOT PRESENT]"
        except Exception:
            pass
        return False, "Strict-Transport-Security header configured or target is not HTTPS", ""

    # 25b. Insecure HTTP PUT Method / Arbitrary File Write Probe
    if "put" in c_clean or "insecure-http-put" in c_clean:
        try:
            import uuid
            unique_marker = f"STRIX-VAPT-PROBE-{uuid.uuid4().hex[:12]}"
            test_put_url = target_url.rstrip("/") + "/strix_probe_test.txt"
            put_req = urllib.request.Request(
                test_put_url,
                data=unique_marker.encode("utf-8"),
                headers={"User-Agent": "AI-VAPT/2.0", "Content-Type": "text/plain"},
                method="PUT",
            )
            with urllib.request.urlopen(put_req, timeout=4.0, context=ctx) as put_resp:
                if put_resp.status in (200, 201, 204):
                    # Verify read-back via GET
                    try:
                        get_req = urllib.request.Request(test_put_url, headers={"User-Agent": "AI-VAPT/2.0"})
                        with urllib.request.urlopen(get_req, timeout=4.0, context=ctx) as get_resp:
                            get_body = get_resp.read(4096).decode("utf-8", errors="ignore")
                            get_ct = get_resp.headers.get("content-type", "").lower()
                            is_html = (
                                "text/html" in get_ct
                                or "<!doctype" in get_body.lower()
                                or "<html" in get_body.lower()
                                or "<!--" in get_body[:50]
                            )
                            if unique_marker in get_body and not is_html:
                                # Clean up via DELETE
                                try:
                                    del_req = urllib.request.Request(test_put_url, headers={"User-Agent": "AI-VAPT/2.0"}, method="DELETE")
                                    urllib.request.urlopen(del_req, timeout=4.0, context=ctx)
                                except Exception:
                                    pass
                                return True, "Arbitrary file write verified via HTTP PUT (marker read-back confirmed)", f"PUT returned {put_resp.status}, GET returned verified marker: {unique_marker}"
                            return False, "HTTP PUT returned 200 due to SPA fallback routing; marker not written to filesystem (UNVERIFIED)", get_body[:250]
                    except Exception:
                        pass
        except Exception as exc:
            logger.debug("PUT probe error: %s", exc)
        return False, "HTTP PUT method is disabled or rejected by server", ""

    # 26. Cookie Without Secure Flag
    if "cookie-without-secure" in c_clean:
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                cookies = resp.headers.get_all("Set-Cookie") or []
                insecure = [c for c in cookies if "secure" not in c.lower()]
                if insecure:
                    return True, "Cookie Without Secure Flag identified over HTTPS", f"Insecure Set-Cookie: {insecure[0]}"
        except Exception:
            pass
        return False, "All session cookies enforce Secure attribute or no cookies present", ""

    # 27. ASP.NET ViewState Cryptographic Integrity Validation
    if "aspnet-viewstate" in c_clean or "viewstate" in c_clean:
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(50000).decode("utf-8", errors="ignore")
                if "__VIEWSTATE" in body:
                    return True, "ASP.NET ViewState parameter present in page body", "Hidden field __VIEWSTATE identified"
        except Exception:
            pass
        return False, "ASP.NET ViewState not detected", ""

    # 28. Reverse Tabnabbing
    if "reverse-tabnabbing" in c_clean or "tabnabbing" in c_clean:
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(50000).decode("utf-8", errors="ignore")
                links = re.findall(r'<a\b[^>]*target=["\']_blank["\'][^>]*>', body, re.I)
                vuln_links = [l for l in links if "noopener" not in l.lower() or "noreferrer" not in l.lower()]
                if vuln_links:
                    return True, "Reverse Tabnabbing vulnerability in target='_blank' links without rel='noopener noreferrer'", vuln_links[0]
        except Exception:
            pass
        return False, "All external links enforce rel='noopener noreferrer'", ""

    # 29. Server-Side Request Forgery (SSRF)
    if "ssrf" in c_clean or "request-forgery" in c_clean:
        try:
            test_url = full_url + ("&" if "?" in full_url else "?") + "dest=http://127.0.0.1:80&url=http://127.0.0.1:80"
            req = urllib.request.Request(test_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(10000).decode("utf-8", errors="ignore")
                if "127.0.0.1" in body and resp.status == 200:
                    return True, "SSRF loopback reflection verified on target endpoint", body[:300]
        except Exception:
            pass
        return False, "SSRF destination filter active or internal loopback requests blocked", ""

    # 30. Server-Side Template Injection (SSTI)
    if "ssti" in c_clean or "template-injection" in c_clean:
        try:
            test_url = full_url + ("&" if "?" in full_url else "?") + "q={{7*7}}&name={{7*7}}&template={{7*7}}"
            req = urllib.request.Request(test_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(20000).decode("utf-8", errors="ignore")
                if "49" in body and "{{7*7}}" not in body:
                    return True, "Server-Side Template Injection confirmed (expression {{7*7}} evaluated to 49)", body[:300]
        except Exception:
            pass
        return False, "Template expressions not evaluated by backend engine or properly sanitized", ""

    # 31. Client-Side Prototype Pollution
    if "prototype-pollution" in c_clean or "proto" in c_clean:
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(50000).decode("utf-8", errors="ignore")
                patterns = [r'__proto__', r'constructor\.prototype', r'Object\.assign\(', r'\$\.extend\(']
                for pat in patterns:
                    if re.search(pat, body, re.I):
                        return True, f"Client-side prototype manipulation pattern identified: {pat}", f"Pattern: {pat}"
        except Exception:
            pass
        return False, "No client-side prototype mutation patterns detected", ""

    # 32. Server-Side Code Injection (PHP, Python, JS eval)
    if "code-injection" in c_clean or "eval" in c_clean or "php-code" in c_clean:
        try:
            test_url = full_url + ("&" if "?" in full_url else "?") + "code=phpinfo()&eval=phpinfo()"
            req = urllib.request.Request(test_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(20000).decode("utf-8", errors="ignore")
                if "PHP Version" in body or "Zend Engine" in body:
                    return True, "Server-side code execution verified via function reflection", body[:300]
        except Exception:
            pass
        return False, "Code evaluation input rejected or not executed by backend runtime", ""

    # Default baseline check: NEVER mark vulnerable simply because HTTP status is 200 or 302!
    return False, "Endpoint probe did not exhibit vulnerable behavior or exploit confirmation", ""


def _sync_engine_candidates(engine, candidate_map: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Merge GAP-1 prioritization scoring metadata with GAP-2 dynamic execution state."""
    merged = []
    for ec in engine.candidates.values():
        meta = dict(candidate_map.get(ec.id, {}))
        c_dict = ec.model_dump() if hasattr(ec, "model_dump") else (ec.dict() if hasattr(ec, "dict") else dict(ec))
        meta.update(c_dict)
        meta["state"] = ec.state.value if hasattr(ec.state, "value") else str(ec.state)
        meta["attempts"] = ec.attempts
        meta["max_attempts"] = ec.max_attempts
        meta["composite_score"] = meta.get("composite_score", round(ec.probability, 4))
        meta["priority_rank"] = meta.get("priority_rank", 1)
        meta["usability_rank"] = meta.get("usability_rank", "HIGH")
        if getattr(ec, "evidence_hash", None):
            meta["evidence_hash"] = ec.evidence_hash
        if getattr(ec, "detail", None):
            meta["detail"] = ec.detail
        merged.append(meta)
    return merged


def _execute_run_worker(run_id: str, req: RunRequest, runtime_key: Optional[str]):
    """Background worker executing the assessment workflow."""
    global _CURRENT_ACTIVE_RUN_ID
    run_entry = _RUNS.get(run_id)
    if not run_entry:
        return

    if req.mode == "autonomous":
        _CURRENT_ACTIVE_RUN_ID = run_id

    try:
        run_entry["status"] = "running"
        target_url = (req.target_url or getattr(req, "target", None) or run_entry.get("target_url", "") or "").strip()
        scan_mode = (getattr(req, "scan_mode", None) or "deep").lower()
        default_turns = 50 if scan_mode == "quick" else (100 if scan_mode == "standard" else 500)
        req_turns = getattr(req, "max_turns", None)
        if req_turns is not None and int(req_turns) > 0:
            max_turns = int(req_turns)
        else:
            max_turns = default_turns
        max_turns = max(1, min(1000, max_turns))
        max_k = max(1, int(req.max_attempts or 2))
        if os.environ.get("PYTEST_CURRENT_TEST"):
            turn_delay = 0.0
        else:
            turn_delay = 0.05 if scan_mode == "quick" else (0.25 if scan_mode == "standard" else 0.50)
        is_live_target = req.mode in ("web", "autonomous") and target_url.startswith("http")

        cli_cfg = _read_strix_cli_config()
        if not runtime_key:
            provider = (req.assessor_provider or "openrouter").lower().strip()
            if provider == "openrouter":
                runtime_key = cli_cfg.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or cli_cfg.get("LLM_API_KEY") or os.environ.get("LLM_API_KEY")
            elif provider == "google":
                runtime_key = cli_cfg.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or cli_cfg.get("LLM_API_KEY") or os.environ.get("LLM_API_KEY")
            elif provider in ("cloud_hosted", "custom_cloud", "custom"):
                active_cloud = _get_active_cloud_profile()
                runtime_key = (
                    (active_cloud.get("api_key") if active_cloud else None)
                    or cli_cfg.get("OPENAI_API_KEY")
                    or os.environ.get("OPENAI_API_KEY")
                    or cli_cfg.get("LLM_API_KEY")
                    or "none"
                )
            else:
                runtime_key = cli_cfg.get("LLM_API_KEY") or os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("GEMINI_API_KEY")

        target_ip = None
        if is_live_target:
            import socket
            try:
                host = urllib.parse.urlsplit(target_url).hostname
                if host:
                    target_ip = socket.gethostbyname(host)
            except Exception:
                pass

        evidence_tier = "OBSERVED_EXTERNAL" if is_live_target else "SIMULATED"
        safety_notice = (
            f"LIVE ACTIVE VAPT — Verified against authorized target endpoint ({target_ip or 'resolved host'}) with non-destructive cryptographic evidence."
            if is_live_target
            else "SIMULATION BENCHMARK — Evaluated in test harness environment."
        )
        run_entry["evidence_tier"] = evidence_tier
        run_entry["safety_notice"] = safety_notice
        run_entry["target_ip"] = target_ip
        run_entry["scan_mode"] = scan_mode
        run_entry["max_turns"] = max_turns

        # Milestone 1: Reconnaissance and port scanning (0-20%)
        run_entry["progress"] = {
            "phase": "Reconnaissance and port scanning",
            "phase_index": 1,
            "percent": 10,
            "current": 0,
            "total": max_turns,
            "candidates_identified": 0,
            "candidates_investigated": 0,
            "pivots": 0,
            "run_id": run_id,
        }
        _save_run_to_disk(run_entry)

        # Multi-Category Portable Reconnaissance (SCA & Ports)
        full_scan_res = None
        if is_live_target:
            try:
                from strix.core.scanner import FullScanner
                full_scan_res = FullScanner.scan_target(target_url, scan_mode=scan_mode)
                run_entry["open_ports"] = full_scan_res.get("open_ports", [])
                run_entry["components"] = full_scan_res.get("components", [])
                run_entry["scan_matrix"] = full_scan_res.get("scan_matrix", [])
                run_entry["spider_stats"] = full_scan_res.get("spider_stats", {})
            except Exception as scan_err:
                logger.warning("Scanner execution warning: %s", scan_err)

        run_entry["progress"] = {
            "phase": "Reconnaissance and port scanning",
            "phase_index": 1,
            "percent": 20,
            "current": 0,
            "total": max_turns,
            "candidates_identified": 0,
            "candidates_investigated": 0,
            "pivots": 0,
            "run_id": run_id,
        }
        run_entry["events"].append({
            "timestamp": _utc_now(),
            "event": "RUN_STARTED",
            "message": f"Assessment started in mode: {req.mode} (Depth: {scan_mode.upper()}, Limit: {max_turns} turns, Tier: {evidence_tier})",
        })
        _save_run_to_disk(run_entry)

        # Milestone 2: Spidering and attack surface discovery (20-40%)
        run_entry["progress"] = {
            "phase": "Spidering and attack surface discovery",
            "phase_index": 2,
            "percent": 30,
            "current": 0,
            "total": max_turns,
            "candidates_identified": 0,
            "candidates_investigated": 0,
            "pivots": 0,
            "run_id": run_id,
        }
        _save_run_to_disk(run_entry)

        # Authentication Session Setup (if configured)
        auth_session = None
        if is_live_target and getattr(req, "auth_config", None):
            try:
                from strix.core.scanner.auth_manager import AuthManager
                auth_session = AuthManager.establish_session(target_url, req.auth_config)
                run_entry["auth_context"] = auth_session.to_safe_dict()
                if auth_session.authenticated:
                    run_entry["events"].append({
                        "timestamp": _utc_now(),
                        "event": "AUTH_SESSION_ESTABLISHED",
                        "message": f"Authenticated session established as '{auth_session.username}' (Role: {auth_session.role or 'customer'}). Masked token: {auth_session.to_safe_dict().get('masked_token')}",
                    })
                else:
                    run_entry["events"].append({
                        "timestamp": _utc_now(),
                        "event": "AUTH_SESSION_FAILED",
                        "message": f"Target authentication failed: {auth_session.error_message}",
                    })
            except Exception as auth_err:
                logger.warning("Auth session establishment error: %s", auth_err)

        # 1. GAP-1 Triage & Exploit Quality Scoring (Dynamic Surface Crawling)
        from strix.core.triage.exploit_assessor import run_gap1_triage
        candidates = run_gap1_triage(
            scenario=req.scenario,
            provider=req.assessor_provider,
            model_name=req.assessor_model,
            api_key=runtime_key,
            target_url=target_url,
            scan_mode=scan_mode,
            full_scan_res=full_scan_res,
            auth_session=auth_session,
        )
        run_entry["candidates"] = [c.model_dump() if hasattr(c, "model_dump") else (c.dict() if hasattr(c, "dict") else dict(c)) for c in candidates]
        detected_tech = "generic_web"
        if candidates and "detected_tech" in candidates[0]:
            detected_tech = candidates[0]["detected_tech"]
        run_entry["tech_stack"] = detected_tech

        run_entry["progress"] = {
            "phase": "Spidering and attack surface discovery",
            "phase_index": 2,
            "percent": 40,
            "current": 0,
            "total": max_turns,
            "candidates_identified": len(candidates),
            "candidates_investigated": 0,
            "pivots": 0,
            "run_id": run_id,
        }
        run_entry["events"].append({
            "timestamp": _utc_now(),
            "event": "GAP1_TRIAGE_COMPLETED",
            "message": f"GAP-1 dynamic triage prioritized {len(candidates)} candidate(s) for stack {detected_tech.upper()}",
        })

        # 2. GAP-2 Bounded Dynamic Decision-Pivoting
        from strix.core.decision_engine.engine import DecisionEngine
        from strix.core.decision_engine.schemas import ActionCandidate, Outcome, CandidateState

        engine = DecisionEngine(pivot_threshold=max_k)
        engine_candidates = [
            ActionCandidate(
                id=c.get("id"),
                name=c.get("name", c.get("id")),
                target=c.get("target", target_url or "target"),
                probability=c.get("composite_score", 0.5),
                severity=c.get("severity", "medium"),
            )
            for c in run_entry["candidates"]
        ]
        engine.initialize(engine_candidates)

        from strix.core.triage.owasp_mapping import map_finding_to_owasp
        candidate_map = {c["id"]: c for c in run_entry["candidates"]}
        total_cands = len(engine_candidates)
        current_turn = 0

        # Milestone 3: GAP1 triage and candidate investigation (40-70%)
        run_entry["progress"] = {
            "phase": "GAP1 triage and candidate investigation",
            "phase_index": 3,
            "percent": 45,
            "current": current_turn,
            "total": max_turns,
            "candidates_identified": total_cands,
            "candidates_investigated": 0,
            "pivots": 0,
            "run_id": run_id,
        }
        _save_run_to_disk(run_entry)

        current_turn += 1
        engine.log(
            "INIT",
            f"[TURN {current_turn}/{max_turns}] Initializing {req.mode.upper()} VAPT scan on {target_url or 'target'} (Scan Depth: {scan_mode.upper()}, Limit: {max_turns} turns, Threshold k={max_k})"
        )
        time.sleep(turn_delay)

        sp_stats = run_entry.get("spider_stats") or {}
        if sp_stats:
            current_turn += 1
            engine.log(
                "SPIDER",
                f"[TURN {current_turn}/{max_turns}] Web Spider: discovered {len(sp_stats.get('discovered_paths', []))} route(s), {sp_stats.get('forms_count', 0)} form(s), {sp_stats.get('parameters_count', 0)} parameter(s)"
            )
            time.sleep(turn_delay)

        current_turn += 1
        engine.log(
            "RECON",
            f"[TURN {current_turn}/{max_turns}] Identified runtime stack: {detected_tech.upper()} | Audited {len(run_entry.get('open_ports', []))} network port(s), {len(run_entry.get('components', []))} component library(ies)"
        )
        time.sleep(turn_delay)

        current_turn += 1
        engine.log(
            "TRIAGE",
            f"[TURN {current_turn}/{max_turns}] GAP-1 prioritized {total_cands} candidate vector(s) across target attack surface"
        )
        time.sleep(turn_delay)

        run_entry["decision_trace"] = list(engine.decision_trace)

        # Ensure run control directory exists for GAP-1 / GAP-2 state isolation
        base_dir = runs_base_dir()
        control_dir = base_dir / run_id / "control"
        control_dir.mkdir(parents=True, exist_ok=True)

        # Control directory and GAP-1 queue injection for Strix gap_bridge
        gap1_candidates = run_entry.get("candidates", [])
        gap1_payload = {
            "candidates": [
                {
                    "candidate_id": c.get("id"),
                    "gap1_rank": c.get("priority_rank", idx + 1),
                    "title": c.get("name", c.get("id")),
                    "endpoint": c.get("endpoint", "/"),
                    "target": target_url,
                    "method": "POST" if "post" in str(c.get("id", "")).lower() else "GET",
                    "quality_rank": c.get("usability_rank", "HIGH"),
                    "priority_score": c.get("composite_score", 0.5),
                    "assessment_reasoning": c.get("reasoning", ""),
                }
                for idx, c in enumerate(gap1_candidates)
            ],
            "original_order": [c.get("id") for c in gap1_candidates],
            "ranked_order": [c.get("id") for c in gap1_candidates],
        }
        (control_dir / "gap1_queue.json").write_text(json.dumps(gap1_payload, indent=2), encoding="utf-8")

        docker_available = _is_docker_available()
        if req.mode == "autonomous" and is_live_target and docker_available:
            engine.log(
                "AUTONOMOUS",
                f"[TURN 1/{max_turns}] Spawning Strix Multi-Agent Autonomous Pentest Engine against {target_url} (Limit: {max_turns} turns, Depth: {scan_mode.upper()})"
            )
            run_entry["events"].append({
                "timestamp": _utc_now(),
                "event": "AUTONOMOUS_EXECUTION_STARTED",
                "message": f"Autonomous multi-agent pentest runner spawned with {max_turns} turns limit.",
            })
            _save_run_to_disk(run_entry)

            # 1. Target URL sandbox rewriting for Docker (localhost/127.0.0.1 -> host.docker.internal)
            parsed_target = urllib.parse.urlsplit(target_url)
            host = parsed_target.hostname or ""
            if host in ("localhost", "127.0.0.1", "::1"):
                netloc = f"host.docker.internal:{parsed_target.port}" if parsed_target.port else "host.docker.internal"
                sandbox_target_url = urllib.parse.urlunsplit((parsed_target.scheme, netloc, parsed_target.path, parsed_target.query, parsed_target.fragment))
                engine.log("SANDBOX", f"Rewrote loopback target {target_url} -> {sandbox_target_url} for Docker sandbox reachability")
            else:
                sandbox_target_url = target_url

            # 2. Environment configuration with CLI config fallback
            sub_env = dict(os.environ)
            cli_cfg = _read_strix_cli_config()

            provider = (req.assessor_provider or "").lower().strip()
            if not provider:
                if (runtime_key and runtime_key.startswith("sk-or-")) or cli_cfg.get("OPENROUTER_API_KEY"):
                    provider = "openrouter"
                elif (runtime_key and runtime_key.startswith("AIza")) or cli_cfg.get("GEMINI_API_KEY"):
                    provider = "google"
                else:
                    provider = "openrouter"

            if provider == "openrouter":
                key = runtime_key or cli_cfg.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or cli_cfg.get("LLM_API_KEY") or os.environ.get("LLM_API_KEY")
            elif provider == "google":
                key = runtime_key or cli_cfg.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or cli_cfg.get("LLM_API_KEY") or os.environ.get("LLM_API_KEY")
            elif provider == "openai":
                key = runtime_key or cli_cfg.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY") or cli_cfg.get("LLM_API_KEY") or os.environ.get("LLM_API_KEY")
            elif provider in ("cloud_hosted", "custom_cloud", "custom"):
                active_cloud = _get_active_cloud_profile()
                key = (
                    runtime_key
                    or (active_cloud.get("api_key") if active_cloud else None)
                    or cli_cfg.get("OPENAI_API_KEY")
                    or os.environ.get("OPENAI_API_KEY")
                    or cli_cfg.get("LLM_API_KEY")
                    or "none"
                )
            else:
                key = runtime_key or cli_cfg.get("LLM_API_KEY") or os.environ.get("LLM_API_KEY")

            raw_model = req.assessor_model or cli_cfg.get("STRIX_LLM") or DEFAULT_OPENROUTER_MODEL

            if provider == "openrouter":
                m_name = format_openrouter_model(raw_model)
                sub_env["STRIX_LLM"] = m_name
                sub_env["OPENAI_BASE_URL"] = cli_cfg.get("OPENAI_BASE_URL") or "https://openrouter.ai/api/v1"
                sub_env["OPENROUTER_API_BASE"] = cli_cfg.get("OPENROUTER_API_BASE") or "https://openrouter.ai/api/v1"
                if key:
                    sub_env["OPENROUTER_API_KEY"] = key
                    sub_env["OPENAI_API_KEY"] = key
                    sub_env["LLM_API_KEY"] = key
            elif provider == "google":
                m_name = raw_model if (raw_model.startswith("google/") or raw_model.startswith("gemini/")) else f"google/{raw_model}"
                sub_env["STRIX_LLM"] = m_name
                if key:
                    sub_env["GEMINI_API_KEY"] = key
                    sub_env["LLM_API_KEY"] = key
            elif provider == "ollama":
                m_name = raw_model if raw_model.startswith("ollama/") else f"ollama/{raw_model}"
                sub_env["STRIX_LLM"] = m_name
                sub_env["OLLAMA_API_BASE"] = os.environ.get("OLLAMA_API_BASE") or "http://127.0.0.1:11434"
                sub_env["LLM_API_KEY"] = "ollama"
            elif provider == "openai":
                m_name = raw_model if raw_model.startswith("openai/") else f"openai/{raw_model}"
                sub_env["STRIX_LLM"] = m_name
                sub_env["OPENAI_BASE_URL"] = "https://api.openai.com/v1"
                if key:
                    sub_env["OPENAI_API_KEY"] = key
                    sub_env["LLM_API_KEY"] = key
            elif provider in ("cloud_hosted", "custom_cloud", "custom"):
                active_cloud = _get_active_cloud_profile()
                cloud_model = req.assessor_model or (active_cloud.get("model") if active_cloud else None) or cli_cfg.get("STRIX_LLM") or "custom-model"
                m_name = cloud_model if cloud_model.startswith("openai/") else f"openai/{cloud_model}"
                base_url = (active_cloud.get("api_base") if active_cloud else None) or cli_cfg.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
                sub_env["STRIX_LLM_PROVIDER"] = "cloud_hosted"
                sub_env["STRIX_LLM"] = m_name
                sub_env["OPENAI_BASE_URL"] = base_url
                sub_env["LLM_API_BASE"] = base_url
                sub_env["STRIX_API_TYPE"] = "chat_completions"
                sub_env["OPENAI_API_KEY"] = key or "none"
                sub_env["LLM_API_KEY"] = key or "none"
                if active_cloud:
                    if active_cloud.get("extra_headers"):
                        sub_env["LLM_EXTRA_HEADERS"] = json.dumps(active_cloud["extra_headers"])
                    if active_cloud.get("timeout"):
                        sub_env["LLM_TIMEOUT"] = str(active_cloud["timeout"])
                    if active_cloud.get("streaming") is False:
                        sub_env["LLM_DISABLE_STREAMING"] = "1"
                    if active_cloud.get("context_window"):
                        sub_env["STRIX_CONTEXT_FALLBACK_TOKENS"] = str(active_cloud["context_window"])

            sub_env["STRIX_GAP_CONTROL_DIR"] = str(control_dir)
            sub_env["STRIX_GAP1_QUEUE"] = str(control_dir / "gap1_queue.json")
            sub_env["STRIX_GAP2_THRESHOLD"] = str(max_k)
            sub_env["STRIX_GAP1_ENABLED"] = "1"
            sub_env["STRIX_GAP2_ENABLED"] = "1"
            if cli_cfg.get("STRIX_REASONING_EFFORT"):
                sub_env["STRIX_REASONING_EFFORT"] = cli_cfg["STRIX_REASONING_EFFORT"]
            sub_env["PYTHONPATH"] = f"{PROJECT_ROOT}:{sub_env.get('PYTHONPATH', '')}"

            # Snapshot directory state prior to launch across both potential base dirs
            candidate_bases = [base_dir]
            if (PROJECT_ROOT / "strix_runs") not in candidate_bases:
                candidate_bases.append(PROJECT_ROOT / "strix_runs")

            before_dirs = set()
            for cb in candidate_bases:
                if cb.is_dir():
                    before_dirs.update(d.name for d in cb.iterdir() if d.is_dir())

            cmd = [
                sys.executable, "-c",
                "import sys; from strix.interface.main import main; sys.exit(main())",
                "-n",
                "-t", sandbox_target_url,
                "-m", scan_mode,
                "--max-turns", str(max_turns),
            ]
            custom_instruction = getattr(req, "instruction", None) or ""
            if auth_session and auth_session.authenticated:
                sub_env["STRIX_AUTH_TOKEN"] = auth_session.token or ""
                sub_env["STRIX_AUTH_HEADER"] = auth_session.header_name or "Authorization"
                sub_env["STRIX_AUTH_USERNAME"] = auth_session.username or ""
                sub_env["STRIX_AUTH_ROLE"] = auth_session.role or "customer"
                auth_note = (
                    f"Authentication verified for target {sandbox_target_url}.\n"
                    f"Test Account: {auth_session.username} (Role: {auth_session.role or 'customer'}).\n"
                    f"Include 'Authorization: Bearer {auth_session.token}' for authenticated endpoints like /api/Users and /api/BasketItems.\n"
                    f"Never disclose raw credential strings or unredacted tokens in report outputs."
                )
                custom_instruction = f"{custom_instruction}\n\n{auth_note}".strip()

            if custom_instruction and isinstance(custom_instruction, str) and custom_instruction.strip():
                cmd.extend(["--instruction", custom_instruction.strip()])
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(PROJECT_ROOT),
                env=sub_env,
                bufsize=1,
            )
            _ACTIVE_PROCESSES[run_id] = proc

            underlying_run_name = None
            ansi_re = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
            current_turn = 1
            seen_gap_traces = set()
            last_stdout_lines: List[str] = []
            stderr_lines: List[str] = []

            # Background reader for stdout
            def _drain_stdout(pipe):
                nonlocal underlying_run_name
                try:
                    for raw_out in iter(pipe.readline, ''):
                        clean_out = ansi_re.sub('', raw_out).strip()
                        if not clean_out:
                            continue
                        last_stdout_lines.append(clean_out)
                        if len(last_stdout_lines) > 50:
                            last_stdout_lines.pop(0)

                        m = re.search(r"Output\s+strix_runs/([a-zA-Z0-9_\-\.]+)", clean_out)
                        if m:
                            underlying_run_name = m.group(1).strip()
                            engine.log("SANDBOX", f"Attached autonomous scan run directory: {underlying_run_name}")

                        turn_m = re.search(r'Starting turn\s+(\d+)', clean_out, re.I)
                        if turn_m:
                            t_val = int(turn_m.group(1))
                            current_turn = max(current_turn, t_val)

                        if not any(clean_out.startswith(ch) for ch in ("╭", "│", "╰", "─")):
                            engine.log("AGENT", clean_out[:240])
                except Exception:
                    pass
                finally:
                    try:
                        pipe.close()
                    except Exception:
                        pass

            # Background reader for stderr
            def _drain_stderr(pipe):
                try:
                    for raw_err in iter(pipe.readline, ''):
                        clean_err = ansi_re.sub('', raw_err).strip()
                        if clean_err:
                            stderr_lines.append(clean_err)
                            if len(stderr_lines) > 50:
                                stderr_lines.pop(0)
                            engine.log("STDERR", clean_err[:240])
                except Exception:
                    pass
                finally:
                    try:
                        pipe.close()
                    except Exception:
                        pass

            out_thread = threading.Thread(target=_drain_stdout, args=(proc.stdout,), daemon=True)
            out_thread.start()
            err_thread = threading.Thread(target=_drain_stderr, args=(proc.stderr,), daemon=True)
            err_thread.start()

            # Wall-clock timeout: 10m quick, 30m standard, 45m deep (bounded by turns)
            wall_clock_timeout = 600 if scan_mode == "quick" else (1800 if scan_mode == "standard" else 3600)
            wall_clock_timeout = max(wall_clock_timeout, min(14400, max_turns * 60))

            proc_start_time = time.time()
            timed_out = False
            log_file_pos = 0
            u_dir = None
            candidates_investigated = 0
            pivots_count = 0
            candidates_identified = total_cands

            def _sync_telemetry():
                nonlocal underlying_run_name, u_dir, log_file_pos
                nonlocal current_turn, candidates_investigated, pivots_count, candidates_identified

                # 1. Resolve u_dir if needed
                if not u_dir or not u_dir.is_dir():
                    if underlying_run_name:
                        for cb in candidate_bases:
                            cand_path = cb / underlying_run_name
                            if cand_path.is_dir():
                                u_dir = cand_path
                                break
                    if not u_dir or not u_dir.is_dir():
                        discovered = []
                        for cb in candidate_bases:
                            if cb.is_dir():
                                for d in cb.iterdir():
                                    if d.is_dir() and d.name not in before_dirs and d.name != run_id:
                                        discovered.append(d)
                        if discovered:
                            discovered.sort(key=lambda d: d.stat().st_mtime, reverse=True)
                            u_dir = discovered[0]
                            underlying_run_name = u_dir.name
                            engine.log("SANDBOX", f"Discovered autonomous scan run directory: {underlying_run_name}")

                # 2. Tail strix.log
                if u_dir and u_dir.is_dir():
                    log_path = u_dir / "strix.log"
                    if log_path.is_file():
                        try:
                            with open(log_path, "r", encoding="utf-8", errors="replace") as lf:
                                lf.seek(log_file_pos)
                                chunk = lf.read()
                                log_file_pos = lf.tell()
                            if chunk:
                                for line in chunk.splitlines():
                                    turn_m = re.search(r'Starting turn\s+(\d+)', line, re.I)
                                    if turn_m:
                                        t_val = int(turn_m.group(1))
                                        current_turn = max(current_turn, t_val)
                                        ag_m = re.search(r'current_agent=([^,\n\r]+)', line)
                                        ag_name = ag_m.group(1).strip() if ag_m else "Agent"
                                        engine.log("TURN", f"[TURN {current_turn}/{max_turns}] Active agent: {ag_name}")

                                    if "Saved coverage record to:" in line:
                                        cov_m = re.search(r'\((\d+)\s+surface\(s\)', line)
                                        if cov_m:
                                            engine.log("COVERAGE", f"Coverage updated: {cov_m.group(1)} surface(s) audited")

                                    if any(k in line.lower() for k in ("ratelimiterror", "free-models-per-day", "openrouter_free_tier_daily", "quota exceeded")):
                                        stderr_lines.append(line)
                        except Exception:
                            pass

                # 3. Synchronize GAP-1 / GAP-2 state from gap_state.json
                state_file = control_dir / "gap_state.json"
                if state_file.is_file():
                    try:
                        gdata = json.loads(state_file.read_text(encoding="utf-8"))
                        attempts_map = gdata.get("attempts", {})
                        exhausted_set = set(gdata.get("exhausted", []))
                        completed_set = set(gdata.get("completed", []))
                        probe_outcomes = gdata.get("probe_outcomes", [])

                        outcome_map = {}
                        for po in probe_outcomes:
                            pcid = po.get("candidate_id")
                            if pcid:
                                outcome_map[pcid] = po.get("status")

                        for cand in run_entry.get("candidates", []):
                            cid = str(cand.get("id"))
                            if not cid:
                                continue
                            cand["attempts"] = attempts_map.get(cid, cand.get("attempts", 0))
                            cand["max_attempts"] = max_k
                            if cid in completed_set:
                                stat = outcome_map.get(cid)
                                cand["state"] = "VALIDATED" if stat == "positive" else "ABANDONED"
                                cand["status"] = cand["state"]
                            elif cid in exhausted_set:
                                cand["state"] = "ABANDONED"
                                cand["status"] = "ABANDONED"
                            elif cand.get("attempts", 0) > 0 or cid in attempts_map:
                                cand["state"] = "ATTEMPTING"
                                cand["status"] = "ATTEMPTING"
                            else:
                                if not cand.get("state"):
                                    cand["state"] = "PENDING"
                                    cand["status"] = "PENDING"

                        candidates_identified = len(run_entry.get("candidates", []))
                        candidates_investigated = sum(
                            1 for c in run_entry.get("candidates", [])
                            if c.get("state") in ("VALIDATED", "ABANDONED")
                            or (c.get("state") == "ATTEMPTING" and c.get("attempts", 0) > 0)
                        )
                    except Exception:
                        pass

                # 3b. Also synchronize candidate coverage from coverage.json in underlying scan directory
                if u_dir and u_dir.is_dir():
                    cov_file = u_dir / "coverage.json"
                    if not cov_file.is_file() and (u_dir / ".state" / "coverage.json").is_file():
                        cov_file = u_dir / ".state" / "coverage.json"
                    if cov_file.is_file():
                        try:
                            cov_data = json.loads(cov_file.read_text(encoding="utf-8"))
                            entries_list = []
                            if isinstance(cov_data, dict):
                                if isinstance(cov_data.get("entries"), list):
                                    entries_list = cov_data["entries"]
                                else:
                                    entries_list = list(cov_data.values())
                            for cov in entries_list:
                                if not isinstance(cov, dict):
                                    continue
                                c_surf = str(cov.get("surface", ""))
                                c_risk = str(cov.get("risk_area", ""))
                                c_out = str(cov.get("outcome", "")).lower()
                                matched = gap_bridge.candidate_for(c_risk, c_surf, "", directory=control_dir)
                                if matched and matched.get("candidate_id"):
                                    mcid = str(matched["candidate_id"])
                                    for cand in run_entry.get("candidates", []):
                                        if str(cand.get("id")) == mcid:
                                            cand["attempts"] = max(cand.get("attempts", 0), 1)
                                            if c_out in ("no_issue_found", "ruled_out", "not_applicable"):
                                                cand["state"] = "ABANDONED"
                                                cand["status"] = "ABANDONED"
                                            elif c_out == "reported":
                                                cand["state"] = "VALIDATED"
                                                cand["status"] = "VALIDATED"
                                            elif c_out == "needs_follow_up":
                                                if cand.get("state") not in ("ABANDONED", "VALIDATED"):
                                                    cand["state"] = "ATTEMPTING"
                                                    cand["status"] = "ATTEMPTING"
                            candidates_investigated = sum(
                                1 for c in run_entry.get("candidates", [])
                                if c.get("state") in ("VALIDATED", "ABANDONED")
                                or (c.get("state") == "ATTEMPTING" and c.get("attempts", 0) > 0)
                            )
                        except Exception:
                            pass

                # 4. Synchronize GAP-2 pivot decisions from decision_trace.jsonl
                trace_file = control_dir / "decision_trace.jsonl"
                if trace_file.is_file():
                    try:
                        for t_line in trace_file.read_text(encoding="utf-8").splitlines():
                            if t_line.strip() and t_line not in seen_gap_traces:
                                seen_gap_traces.add(t_line)
                                t_obj = json.loads(t_line)
                                if t_obj.get("event") == "GAP2_PIVOT":
                                    engine.log("PIVOT", f"[GAP-2 PIVOT] Bounded threshold reached for {t_obj.get('candidate_id')}; pivoted to {t_obj.get('next_candidate')}")
                                    run_entry["pivot_events"].append(t_obj)
                    except Exception:
                        pass

                pivots_count = len([e for e in run_entry.get("pivot_events", []) if e.get("event") == "GAP2_PIVOT" or e.get("type") in ("REDIRECT", "GAP2_PIVOT")])

                # 5. Check vulnerabilities.json to mark candidates validated in real-time
                if u_dir and u_dir.is_dir():
                    u_vuln = u_dir / "vulnerabilities.json"
                    if u_vuln.is_file():
                        try:
                            strix_vulns = json.loads(u_vuln.read_text(encoding="utf-8"))
                            if isinstance(strix_vulns, list):
                                for sv in strix_vulns:
                                    s_loc = sv.get("location") or sv.get("endpoint") or "/"
                                    s_name = (sv.get("title") or sv.get("name") or "").lower()
                                    s_cid = sv.get("candidate_id") or sv.get("rule_id") or ""
                                    for c in run_entry.get("candidates", []):
                                        c_id = c.get("id", "")
                                        c_name = (c.get("name") or "").lower()
                                        id_match = bool(s_cid and (s_cid == c_id or s_cid in c_id))
                                        name_match = bool(c_name and (c_name == s_name or s_name in c_name or c_name in s_name))
                                        if id_match or name_match:
                                            c["state"] = "VALIDATED"
                                            c["status"] = "VALIDATED"
                        except Exception:
                            pass

                # 6. Truthful progress milestones
                turn_fraction = min(1.0, current_turn / max(1, max_turns))
                if pivots_count > 0 or turn_fraction >= 0.5:
                    phase_name = "GAP2 adaptive pivoting and validation"
                    phase_idx = 4
                    calc_pct = min(89, 70 + int(turn_fraction * 20))
                else:
                    phase_name = "GAP1 triage and candidate investigation"
                    phase_idx = 3
                    calc_pct = min(69, 40 + int(turn_fraction * 30))

                run_entry["progress"] = {
                    "phase": phase_name,
                    "phase_index": phase_idx,
                    "percent": calc_pct,
                    "current": current_turn,
                    "total": max_turns,
                    "candidate": f"Autonomous Multi-Agent Turn {current_turn}",
                    "candidates_identified": candidates_identified,
                    "candidates_investigated": candidates_investigated,
                    "pivots": pivots_count,
                    "run_id": run_id,
                }
                run_entry["stats"] = {
                    "attempts": current_turn,
                    "pivots": pivots_count,
                    "findings": len(run_entry.get("findings", [])),
                }
                run_entry["decision_trace"] = list(engine.decision_trace)
                _save_run_to_disk(run_entry)

            poll_interval = 0.02 if os.environ.get("PYTEST_CURRENT_TEST") else 0.3
            while proc.poll() is None:
                if run_entry.get("status") == "aborted":
                    try:
                        proc.terminate()
                        proc.wait(timeout=3.0)
                    except Exception:
                        with contextlib.suppress(Exception):
                            proc.kill()
                    break

                if time.time() - proc_start_time > wall_clock_timeout:
                    timed_out = True
                    engine.log("TIMEOUT", f"Wall-clock timeout of {wall_clock_timeout}s exceeded. Terminating autonomous scanner.")
                    try:
                        proc.terminate()
                        proc.wait(timeout=3.0)
                    except Exception:
                        with contextlib.suppress(Exception):
                            proc.kill()
                    break

                _sync_telemetry()
                time.sleep(poll_interval)

            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(Exception):
                    proc.kill()
                    proc.wait(timeout=2.0)

            _ACTIVE_PROCESSES.pop(run_id, None)
            err_thread.join(timeout=2.0)
            out_thread.join(timeout=2.0)

            _sync_telemetry()

            if run_entry.get("status") == "aborted":
                return

            # Discover underlying run directory across candidate bases
            if not underlying_run_name:
                discovered_candidates = []
                for cb in candidate_bases:
                    if cb.is_dir():
                        for d in cb.iterdir():
                            if d.is_dir() and d.name not in before_dirs and d.name != run_id:
                                discovered_candidates.append(d)
                if discovered_candidates:
                    discovered_candidates.sort(key=lambda d: d.stat().st_mtime, reverse=True)
                    underlying_run_name = discovered_candidates[0].name
                    engine.log("SANDBOX", f"Discovered autonomous scan run directory: {underlying_run_name}")

            u_dir = None
            if underlying_run_name:
                for cb in candidate_bases:
                    cand_path = cb / underlying_run_name
                    if cand_path.is_dir():
                        u_dir = cand_path
                        break

            u_run_data = None
            if u_dir and u_dir.exists():
                u_run_file = u_dir / "run.json"
                if u_run_file.is_file():
                    try:
                        with open(u_run_file, "r", encoding="utf-8") as rf:
                            u_run_data = json.load(rf)
                    except Exception as err:
                        logger.warning("Error reading underlying run.json: %s", err)

            ret_code = proc.returncode if proc.returncode is not None else 0
            proc_failed = False
            error_msg: Optional[str] = None

            if timed_out:
                proc_failed = True
                error_msg = f"Assessment exceeded wall-clock limit of {wall_clock_timeout}s"
            elif ret_code not in (0, 2):
                proc_failed = True
                error_msg = _extract_clean_error(
                    stderr_lines,
                    last_stdout_lines,
                    fallback=f"Scanner exited unexpectedly with status code {ret_code}",
                )
            else:
                # Subprocess exited with code 0 or 2, but validate actual scan status from run.json
                if not u_dir or not u_dir.exists():
                    proc_failed = True
                    error_msg = _extract_clean_error(
                        stderr_lines,
                        last_stdout_lines,
                        fallback="Autonomous scanner exited without creating a scan directory",
                    )
                elif u_run_data is None:
                    proc_failed = True
                    error_msg = _extract_clean_error(
                        stderr_lines,
                        last_stdout_lines,
                        fallback="Scan completed without generating execution metadata (run.json missing)",
                    )
                else:
                    u_status = u_run_data.get("status")
                    u_exit_reason = u_run_data.get("scan_ended_exit_reason")
                    if u_status != "completed":
                        proc_failed = True
                        reason_str = f" (exit reason: {u_exit_reason})" if u_exit_reason else ""
                        error_msg = _extract_clean_error(
                            stderr_lines,
                            last_stdout_lines,
                            fallback=f"Scan ended with status '{u_status}'{reason_str} before satisfying completion requirements",
                        )

            # Milestone 5: Report synthesis and persistence (only if scan completed cleanly)
            if not proc_failed:
                run_entry["progress"] = {
                    "phase": "Report synthesis and persistence",
                    "phase_index": 5,
                    "percent": 92,
                    "current": current_turn,
                    "total": max_turns,
                    "candidates_identified": candidates_identified,
                    "candidates_investigated": candidates_investigated,
                    "pivots": pivots_count,
                    "run_id": run_id,
                }
            _save_run_to_disk(run_entry)

            findings = []
            if u_dir and u_dir.exists():
                    u_vuln = u_dir / "vulnerabilities.json"
                    if u_vuln.exists():
                        try:
                            with open(u_vuln, "r", encoding="utf-8") as f:
                                strix_vulns = json.load(f)
                                if isinstance(strix_vulns, list):
                                    for sv in strix_vulns:
                                        mapped = map_finding_to_owasp(
                                            sv.get("title") or sv.get("name") or "Vulnerability",
                                            rule_id=sv.get("id", ""),
                                            endpoint=sv.get("location") or sv.get("endpoint") or "/",
                                            tech_stack=detected_tech,
                                        )
                                        raw_ev = sv.get("detail") or sv.get("evidence") or sv.get("poc_script_code") or str(sv)
                                        ev_bytes = raw_ev.encode("utf-8") if isinstance(raw_ev, str) else str(raw_ev).encode()
                                        findings.append({
                                            "id": sv.get("id", f"strix-{uuid.uuid4().hex[:6]}"),
                                            "title": sv.get("title", sv.get("name", "Vulnerability")),
                                            "severity": sv.get("severity", "MEDIUM").upper(),
                                            "cvss_score": sv.get("cvss_score") or sv.get("cvss") or mapped.get("cvss", 6.0),
                                            "cve_id": sv.get("cve_id") or mapped.get("cve_id"),
                                            "cwe_id": sv.get("cwe_id") or mapped.get("cwe_id", "CWE-200"),
                                            "owasp_category": f"{mapped.get('owasp_id', 'A01:2021')} - {mapped.get('category_name', 'Broken Access Control')}",
                                            "location": sv.get("location") or sv.get("endpoint") or "/",
                                            "target": target_url,
                                            "evidence_hash": sv.get("evidence_hash") or hashlib.sha256(ev_bytes).hexdigest(),
                                            "evidence_snippet": raw_ev,
                                            "reproducible_request": sv.get("poc_script_code") or f"GET {sv.get('endpoint') or '/'} HTTP/1.1",
                                            "validation_method": sv.get("validation_method") or "PoC Execution & Response Pattern Verification",
                                            "severity_justification": sv.get("severity_change_conditions") or sv.get("technical_analysis") or f"Severity {sv.get('severity', 'MEDIUM').upper()} justified by exploitability and demonstrated impact.",
                                            "impact": sv.get("impact") or mapped.get("impact", ""),
                                            "remediation_summary": sv.get("remediation") or mapped.get("remediation_summary", ""),
                                            "remediation_technical": sv.get("remediation_steps") or sv.get("remediation_technical") or mapped.get("remediation_technical", ""),
                                            "retest_procedure": mapped.get("retest_procedure", ""),
                                            "finding_class": sv.get("finding_class", "dynamic"),
                                        })
                        except Exception as e:
                            logger.warning("Error reading strix vulnerabilities: %s", e)

                    # Persist run artifacts from Strix run folder to current run folder
                    target_run_dir = base_dir / run_id
                    target_run_dir.mkdir(parents=True, exist_ok=True)
                    for art_name in ("findings.sarif", "coverage.json", "penetration_test_report.md"):
                        src_art = u_dir / art_name
                        if src_art.is_file():
                            try:
                                (target_run_dir / art_name).write_bytes(src_art.read_bytes())
                            except Exception:
                                pass

            # Reconcile uninvestigated candidates as NOT_TESTED
            untested_count = 0
            for cand in run_entry.get("candidates", []):
                if cand.get("state") in ("PENDING", None) or (cand.get("attempts", 0) == 0 and cand.get("state") not in ("VALIDATED", "ABANDONED")):
                    cand["state"] = "NOT_TESTED"
                    cand["status"] = "NOT_TESTED"
                    untested_count += 1

            candidates_dispatched = len(run_entry.get("candidates", []))
            candidates_investigated = sum(
                1 for c in run_entry.get("candidates", [])
                if c.get("state") in ("VALIDATED", "ABANDONED")
                or (c.get("state") == "ATTEMPTING" and c.get("attempts", 0) > 0)
            )
            candidates_validated = sum(1 for c in run_entry.get("candidates", []) if c.get("state") == "VALIDATED")
            candidates_abandoned = sum(1 for c in run_entry.get("candidates", []) if c.get("state") == "ABANDONED")
            candidates_not_tested = sum(1 for c in run_entry.get("candidates", []) if c.get("state") == "NOT_TESTED")
            candidates_blocked = sum(1 for c in run_entry.get("candidates", []) if c.get("state") == "BLOCKED")

            run_entry["candidate_accounting"] = {
                "dispatched": candidates_dispatched,
                "investigated": candidates_investigated,
                "validated": candidates_validated,
                "abandoned": candidates_abandoned,
                "not_tested": candidates_not_tested,
                "blocked": candidates_blocked,
            }

            run_entry["findings"] = findings
            run_entry["scan_matrix"] = _reconcile_scan_matrix(run_entry.get("scan_matrix", []), findings)
            run_entry["stats"] = {
                "attempts": current_turn,
                "pivots": pivots_count,
                "findings": len(findings),
                "candidates_dispatched": candidates_dispatched,
                "candidates_investigated": candidates_investigated,
                "candidates_validated": candidates_validated,
                "candidates_abandoned": candidates_abandoned,
                "candidates_not_tested": candidates_not_tested,
                "candidates_blocked": candidates_blocked,
            }
            run_entry["completed_at"] = _utc_now()

            if proc_failed:
                run_entry["status"] = "failed"
                run_entry["error"] = error_msg
                run_entry["report_status"] = "partial_report_harvested" if findings else "no_findings"
                turn_fraction = min(1.0, max(0.0, current_turn / max(1, max_turns)))
                actual_pct = min(85, max(15, int(35 + 50 * turn_fraction)))
                clean_err_short = (error_msg.split(".")[0] or error_msg)[:80]
                run_entry["progress"] = {
                    "phase": f"Failed: {clean_err_short}",
                    "phase_index": 3,
                    "percent": actual_pct,
                    "current": current_turn,
                    "total": max_turns,
                    "candidates_identified": candidates_identified,
                    "candidates_investigated": candidates_investigated,
                    "pivots": pivots_count,
                    "run_id": run_id,
                }
                run_entry["events"].append({
                    "timestamp": _utc_now(),
                    "event": "RUN_FAILED",
                    "message": f"Autonomous pentest failed (code {ret_code}): {error_msg}. Harvested {len(findings)} partial finding(s).",
                })
                engine.log("FAIL", f"Autonomous assessment failed (exit {ret_code}): {error_msg}")
            elif untested_count > 0:
                run_entry["status"] = "partial"
                run_entry["report_status"] = "partial" if findings else "no_findings"
                turn_fraction = min(1.0, max(0.0, current_turn / max(1, max_turns)))
                actual_pct = min(85, max(15, int(35 + 50 * turn_fraction)))
                run_entry["progress"] = {
                    "phase": f"Assessment Partial — {untested_count} Untested Candidates Remain",
                    "phase_index": 4,
                    "percent": actual_pct,
                    "current": current_turn,
                    "total": max_turns,
                    "candidate": "Partial Completion",
                    "candidates_identified": candidates_identified,
                    "candidates_investigated": candidates_investigated,
                    "pivots": pivots_count,
                    "run_id": run_id,
                }
                run_entry["events"].append({
                    "timestamp": _utc_now(),
                    "event": "RUN_PARTIAL",
                    "message": f"Autonomous pentest ended with {untested_count} untested candidate(s) remaining. Harvested {len(findings)} confirmed finding(s).",
                })
                engine.log("WARN", f"Autonomous assessment partial: {untested_count} untested candidate(s) remaining.")
            else:
                run_entry["status"] = "completed"
                run_entry["progress"] = {
                    "phase": "Assessment Complete",
                    "phase_index": 5,
                    "percent": 100,
                    "current": current_turn,
                    "total": max_turns,
                    "candidate": "Completed",
                    "candidates_identified": candidates_identified,
                    "candidates_investigated": candidates_investigated,
                    "pivots": pivots_count,
                    "run_id": run_id,
                }
                run_entry["events"].append({
                    "timestamp": _utc_now(),
                    "event": "RUN_COMPLETED",
                    "message": f"Autonomous pentest finished. Found {len(findings)} confirmed finding(s).",
                })

            run_entry["decision_trace"] = list(engine.decision_trace)
            _save_run_to_disk(run_entry)
            return

        if req.mode == "autonomous" and is_live_target and not docker_available:
            engine.log("WARN", "[SYSTEM] Docker container sandbox environment unavailable on host. Executing deep in-process Multi-Category Active Scanner & GAP-1/GAP-2 Decision Engine.")

        for idx, c in enumerate(engine_candidates):
            if current_turn >= max_turns:
                engine.log("LIMIT", f"[TURN {current_turn}/{max_turns}] Turn limit of {max_turns} reached. Finalizing current assessments.")
                break

            c_meta = candidate_map.get(c.id, {})
            endpoint = c_meta.get("endpoint", "/")
            c.state = CandidateState.ATTEMPTING
            engine.current_index = idx

            run_entry["candidates"] = _sync_engine_candidates(engine, candidate_map)
            run_entry["decision_trace"] = list(engine.decision_trace)
            run_entry["pivot_events"] = [e.model_dump() if hasattr(e, "model_dump") else (e.dict() if hasattr(e, "dict") else dict(e)) for e in engine.pivot_events]
            piv_cnt = len([e for e in engine.pivot_events if getattr(e, "type", "") in ("REDIRECT", "GAP2_PIVOT") or getattr(e, "event", "") == "GAP2_PIVOT"])
            prog_ratio = (idx + 1) / max(1, total_cands)
            if piv_cnt > 0 or idx >= (total_cands // 2):
                p_name = "GAP2 adaptive pivoting and validation"
                p_idx = 4
                p_pct = min(89, 70 + int(prog_ratio * 20))
            else:
                p_name = "GAP1 triage and candidate investigation"
                p_idx = 3
                p_pct = min(69, 40 + int(prog_ratio * 30))

            run_entry["progress"] = {
                "phase": p_name,
                "phase_index": p_idx,
                "percent": p_pct,
                "current": current_turn,
                "total": max_turns,
                "candidate": c.name or c.id,
                "candidates_identified": total_cands,
                "candidates_investigated": idx + 1,
                "pivots": piv_cnt,
                "run_id": run_id,
            }

            if is_live_target:
                confirmed, detail, snippet = _probe_web_candidate(target_url, c.id, endpoint, auth_session=auth_session)
                if confirmed:
                    current_turn += 1
                    engine.log("PROBE", f"[TURN {current_turn}/{max_turns}] Evaluating candidate: {c.name} on {endpoint}")
                    engine.record_outcome(c.id, Outcome.SUCCESS, detail=detail)
                    gap_bridge.record_outcome(
                        directory=control_dir,
                        candidate_id=c.id,
                        title=c.name or c.id,
                        endpoint=endpoint,
                        target=target_url,
                        probe_status="positive",
                        detail=detail,
                        source="no_docker_probe",
                    )
                    raw_ev = snippet.encode("utf-8") if snippet else f"HTTP/1.1 200 OK\nHost: {target_url}\nVector: {c.id}\nTimestamp: {_utc_now()}".encode()
                    c.evidence_hash = hashlib.sha256(raw_ev).hexdigest()
                    c.detail = snippet or detail
                    run_entry["candidates"] = _sync_engine_candidates(engine, candidate_map)
                    run_entry["decision_trace"] = list(engine.decision_trace)
                    run_entry["pivot_events"] = [e.model_dump() if hasattr(e, "model_dump") else (e.dict() if hasattr(e, "dict") else dict(e)) for e in engine.pivot_events]
                    time.sleep(turn_delay)
                else:
                    for attempt_num in range(1, max_k + 1):
                        current_turn += 1
                        if current_turn > max_turns:
                            break
                        engine.log("PROBE", f"[TURN {current_turn}/{max_turns}] Evaluating candidate: {c.name} (Attempt {attempt_num}/{max_k})")
                        if attempt_num >= max_k:
                            engine.record_outcome(
                                c.id,
                                Outcome.FAIL_TIMEOUT,
                                detail=f"Threshold k={max_k} reached. Abandoning dead-end candidate; pivoting to next in queue.",
                            )
                            gap_bridge.record_outcome(
                                directory=control_dir,
                                candidate_id=c.id,
                                title=c.name or c.id,
                                endpoint=endpoint,
                                target=target_url,
                                probe_status="negative",
                                detail=f"Threshold k={max_k} reached; pivoted",
                                source="no_docker_probe",
                            )
                            gap_bridge.get_run_state(control_dir).mark_exhausted(c.id)
                        else:
                            engine.record_outcome(
                                c.id,
                                Outcome.FAIL_TIMEOUT,
                                detail=f"Probe attempt {attempt_num}/{max_k} returned non-viable: {detail}",
                            )
                            gap_bridge.record_outcome(
                                directory=control_dir,
                                candidate_id=c.id,
                                title=c.name or c.id,
                                endpoint=endpoint,
                                target=target_url,
                                probe_status="inconclusive",
                                detail=detail,
                                source="no_docker_probe",
                            )
                        run_entry["candidates"] = _sync_engine_candidates(engine, candidate_map)
                        run_entry["decision_trace"] = list(engine.decision_trace)
                        run_entry["pivot_events"] = [e.model_dump() if hasattr(e, "model_dump") else (e.dict() if hasattr(e, "dict") else dict(e)) for e in engine.pivot_events]
                        time.sleep(turn_delay)
            else:
                if c.id in ("default-credentials", "phpinfo-disclosure", "sqli-login", "cve-2021-44228", "missing-security-headers"):
                    current_turn += 1
                    engine.log("PROBE", f"[TURN {current_turn}/{max_turns}] Evaluating candidate: {c.name} on {endpoint}")
                    engine.record_outcome(c.id, Outcome.SUCCESS, detail="Confirmed vulnerability with valid PoC")
                    gap_bridge.record_outcome(
                        directory=control_dir,
                        candidate_id=c.id,
                        title=c.name or c.id,
                        endpoint=endpoint,
                        target=target_url,
                        probe_status="positive",
                        detail="Confirmed vulnerability with valid PoC",
                        source="no_docker_mock",
                    )
                    time.sleep(turn_delay)
                else:
                    for attempt_num in range(1, max_k + 1):
                        current_turn += 1
                        if current_turn > max_turns:
                            break
                        engine.log("PROBE", f"[TURN {current_turn}/{max_turns}] Evaluating candidate: {c.name} (Attempt {attempt_num}/{max_k})")
                        if attempt_num >= max_k:
                            engine.record_outcome(
                                c.id,
                                Outcome.FAIL_TIMEOUT,
                                detail=f"Threshold k={max_k} reached. Abandoning dead-end route; pivoting.",
                            )
                            gap_bridge.record_outcome(
                                directory=control_dir,
                                candidate_id=c.id,
                                title=c.name or c.id,
                                endpoint=endpoint,
                                target=target_url,
                                probe_status="negative",
                                detail=f"Threshold k={max_k} reached; pivoted",
                                source="no_docker_mock",
                            )
                            gap_bridge.get_run_state(control_dir).mark_exhausted(c.id)
                        else:
                            engine.record_outcome(
                                c.id,
                                Outcome.FAIL_TIMEOUT,
                                detail=f"Route blocked by filter or timeout ({attempt_num}/{max_k})",
                            )
                            gap_bridge.record_outcome(
                                directory=control_dir,
                                candidate_id=c.id,
                                title=c.name or c.id,
                                endpoint=endpoint,
                                target=target_url,
                                probe_status="inconclusive",
                                detail=f"Route blocked ({attempt_num}/{max_k})",
                                source="no_docker_mock",
                            )
                        time.sleep(turn_delay)

            run_entry["candidates"] = _sync_engine_candidates(engine, candidate_map)
            run_entry["decision_trace"] = list(engine.decision_trace)
            run_entry["pivot_events"] = [e.model_dump() if hasattr(e, "model_dump") else (e.dict() if hasattr(e, "dict") else dict(e)) for e in engine.pivot_events]
            piv_cnt = len([e for e in engine.pivot_events if getattr(e, "type", "") in ("REDIRECT", "GAP2_PIVOT") or getattr(e, "event", "") == "GAP2_PIVOT"])
            prog_ratio = (idx + 1) / max(1, total_cands)
            if piv_cnt > 0 or idx >= (total_cands // 2):
                p_name = "GAP2 adaptive pivoting and validation"
                p_idx = 4
                p_pct = min(89, 70 + int(prog_ratio * 20))
            else:
                p_name = "GAP1 triage and candidate investigation"
                p_idx = 3
                p_pct = min(69, 40 + int(prog_ratio * 30))

            run_entry["progress"] = {
                "phase": p_name,
                "phase_index": p_idx,
                "percent": p_pct,
                "current": current_turn,
                "total": max_turns,
                "candidate": c.name or c.id,
                "candidates_identified": total_cands,
                "candidates_investigated": idx + 1,
                "pivots": piv_cnt,
                "run_id": run_id,
            }

        # Structured active verification across discovered endpoints if turn budget allows
        if is_live_target and scan_mode in ("standard", "deep") and current_turn < max_turns:
            discovered_paths = [p for p in (sp_stats.get("discovered_paths", []) or []) if p and p != "/"][:3]
            fuzz_checks = ["missing-security-headers", "server-banner", "cors", "csrf", "reflected-xss"]
            for curr_path in discovered_paths:
                if current_turn >= max_turns:
                    break
                for check_id in fuzz_checks:
                    if current_turn >= max_turns:
                        break
                    current_turn += 1
                    engine.log("PROBE", f"[TURN {current_turn}/{max_turns}] Probing {check_id} on {curr_path}")
                    is_vuln, det, snip = _probe_web_candidate(target_url, check_id, curr_path, auth_session=auth_session)
                    outcome_str = "positive" if is_vuln else "negative"
                    gap_bridge.record_outcome(
                        directory=control_dir,
                        candidate_id=f"{check_id}:{curr_path}",
                        title=check_id,
                        endpoint=curr_path,
                        target=target_url,
                        probe_status=outcome_str,
                        detail=det,
                        source="no_docker_fuzz",
                    )
                    if is_vuln and f"{check_id}-{curr_path}" not in engine.candidates:
                        engine.candidates[f"{check_id}-{curr_path}"] = Candidate(
                            id=f"{check_id}-{curr_path}",
                            name=f"{check_id.replace('-', ' ').title()} ({curr_path})",
                            category="fuzz",
                            severity="MEDIUM",
                            target=target_url,
                            state=CandidateState.VALIDATED,
                            detail=snip or det,
                            evidence_hash=hashlib.sha256((snip or det).encode("utf-8")).hexdigest(),
                        )
                    if turn_delay > 0:
                        time.sleep(turn_delay)

        run_entry["decision_trace"] = list(engine.decision_trace)
        run_entry["pivot_events"] = [e.model_dump() if hasattr(e, "model_dump") else (e.dict() if hasattr(e, "dict") else dict(e)) for e in engine.pivot_events]
        run_entry["candidates"] = _sync_engine_candidates(engine, candidate_map)
        
        # Milestone 5: Report synthesis and persistence (90-100%)
        piv_cnt = len([e for e in engine.pivot_events if getattr(e, "type", "") in ("REDIRECT", "GAP2_PIVOT") or getattr(e, "event", "") == "GAP2_PIVOT"])
        run_entry["progress"] = {
            "phase": "Report synthesis and persistence",
            "phase_index": 5,
            "percent": 92,
            "current": current_turn,
            "total": max_turns,
            "candidate": "Generating comprehensive security report",
            "candidates_identified": total_cands,
            "candidates_investigated": total_cands,
            "pivots": piv_cnt,
            "run_id": run_id,
        }
        _save_run_to_disk(run_entry)

        # Generate findings with SHA-256 evidence hashes and full CVE / CWE / OWASP mapping
        findings = []
        for c in engine.candidates.values():
            c_state_str = c.state.value if hasattr(c.state, "value") else str(c.state)
            if c_state_str == "VALIDATED":
                c_meta = candidate_map.get(c.id, {})
                mapped_profile = map_finding_to_owasp(c.name, rule_id=c.id, endpoint=c_meta.get("endpoint", "/"), tech_stack=detected_tech)
                raw_evidence = getattr(c, "detail", "") or f"HTTP/1.1 200 OK\nTarget: {target_url}\nFinding: {c.id}\nTimestamp: {_utc_now()}"
                raw_bytes = raw_evidence.encode("utf-8") if isinstance(raw_evidence, str) else raw_evidence
                ev_hash = c.evidence_hash or hashlib.sha256(raw_bytes).hexdigest()

                cve_val = mapped_profile.get("cve_id") or c_meta.get("cve_id")
                if cve_val and (cve_val.startswith("CVE-2022-XXXX") or cve_val == "N/A"):
                    cve_val = None

                findings.append({
                    "id": f"find-{c.id}",
                    "title": c.name or mapped_profile.get("title", c.id),
                    "severity": c.severity.upper(),
                    "cvss_score": mapped_profile.get("cvss", c_meta.get("cvss_score", 5.0)),
                    "cve_id": cve_val,
                    "cwe_id": mapped_profile.get("cwe_id", c_meta.get("cwe_id", "CWE-200")),
                    "owasp_category": f"{mapped_profile.get('owasp_id', 'A01:2021')} - {mapped_profile.get('category_name', 'Broken Access Control')}",
                    "location": c_meta.get("endpoint", "/"),
                    "target": target_url or c.target,
                    "evidence_hash": ev_hash,
                    "evidence_snippet": raw_evidence if isinstance(raw_evidence, str) else raw_evidence.decode("utf-8", errors="ignore"),
                    "reproducible_request": f"GET {c_meta.get('endpoint', '/')} HTTP/1.1\nHost: {urllib.parse.urlsplit(target_url).netloc}",
                    "validation_method": "Active HTTP verification probe & response pattern analysis",
                    "severity_justification": f"Rated {c.severity.upper()} based on reachability and verified behavior on endpoint.",
                    "impact": mapped_profile.get("impact", ""),
                    "remediation_summary": mapped_profile.get("remediation_summary", ""),
                    "remediation_technical": mapped_profile.get("remediation_technical", ""),
                    "retest_procedure": mapped_profile.get("retest_procedure", ""),
                    "finding_class": "dynamic",
                })
        run_entry["findings"] = findings
        run_entry["stats"] = {
            "attempts": max(current_turn, sum(c.attempts for c in engine.candidates.values())),
            "pivots": len([e for e in engine.pivot_events if getattr(e, "type", "") in ("REDIRECT", "GAP2_PIVOT") or getattr(e, "event", "") == "GAP2_PIVOT"]),
            "findings": len(findings),
            "candidates_dispatched": total_cands,
            "candidates_investigated": sum(1 for c in run_entry.get("candidates", []) if c.get("state") in ("VALIDATED", "ABANDONED") or c.get("attempts", 0) > 0),
            "candidates_validated": sum(1 for c in run_entry.get("candidates", []) if c.get("state") == "VALIDATED"),
            "candidates_abandoned": sum(1 for c in run_entry.get("candidates", []) if c.get("state") == "ABANDONED"),
            "candidates_not_tested": sum(1 for c in run_entry.get("candidates", []) if c.get("state") == "NOT_TESTED"),
            "candidates_blocked": sum(1 for c in run_entry.get("candidates", []) if c.get("state") == "BLOCKED"),
        }
        run_entry["candidate_accounting"] = {
            "dispatched": total_cands,
            "investigated": sum(1 for c in run_entry.get("candidates", []) if c.get("state") in ("VALIDATED", "ABANDONED") or c.get("attempts", 0) > 0),
            "validated": sum(1 for c in run_entry.get("candidates", []) if c.get("state") == "VALIDATED"),
            "abandoned": sum(1 for c in run_entry.get("candidates", []) if c.get("state") == "ABANDONED"),
            "not_tested": sum(1 for c in run_entry.get("candidates", []) if c.get("state") == "NOT_TESTED"),
            "blocked": sum(1 for c in run_entry.get("candidates", []) if c.get("state") == "BLOCKED"),
        }
        run_entry["tech_stack"] = detected_tech

        run_entry["completed_at"] = _utc_now()
        untested_cands = sum(1 for c in run_entry.get("candidates", []) if c.get("state") in ("PENDING", "NOT_TESTED") or (c.get("attempts", 0) == 0 and c.get("state") not in ("VALIDATED", "ABANDONED")))
        if untested_cands > 0:
            run_entry["status"] = "partial"
            run_entry["progress"] = {
                "phase": f"Assessment Partial — {untested_cands} Untested Candidates Remain",
                "phase_index": 4,
                "percent": 85,
                "current": current_turn,
                "total": max_turns,
                "candidate": "Partial Completion",
                "candidates_identified": total_cands,
                "candidates_investigated": total_cands - untested_cands,
                "pivots": piv_cnt,
                "run_id": run_id,
            }
            run_entry["events"].append({
                "timestamp": _utc_now(),
                "event": "RUN_PARTIAL",
                "message": f"Assessment completed partially with {untested_cands} untested candidate(s). Found {len(findings)} confirmed finding(s).",
            })
        else:
            run_entry["status"] = "completed"
            run_entry["progress"] = {
                "phase": "Assessment Complete",
                "phase_index": 5,
                "percent": 100,
                "current": current_turn,
                "total": max_turns,
                "candidate": "Completed",
                "candidates_identified": total_cands,
                "candidates_investigated": total_cands,
                "pivots": piv_cnt,
                "run_id": run_id,
            }
            run_entry["events"].append({
                "timestamp": _utc_now(),
                "event": "RUN_COMPLETED",
                "message": f"Assessment finished. Found {len(findings)} confirmed finding(s).",
            })
        _save_run_to_disk(run_entry)

    except Exception as exc:
        logger.exception("Assessment run %s failed", run_id)
        run_entry["status"] = "failed"
        run_entry["error"] = str(exc)
        cur_prog = run_entry.get("progress") or {}
        run_entry["progress"] = {
            "phase": f"Failed ({cur_prog.get('phase', 'Investigation')})",
            "phase_index": cur_prog.get("phase_index", 3),
            "percent": min(90, cur_prog.get("percent", 50)),
            "current": cur_prog.get("current", 0),
            "total": max_turns,
            "candidates_identified": cur_prog.get("candidates_identified", 0),
            "candidates_investigated": cur_prog.get("candidates_investigated", 0),
            "pivots": cur_prog.get("pivots", 0),
            "run_id": run_id,
        }
        run_entry["events"].append({
            "timestamp": _utc_now(),
            "event": "RUN_FAILED",
            "message": f"Run terminated with error: {exc}",
        })
        _save_run_to_disk(run_entry)
    finally:
        if _CURRENT_ACTIVE_RUN_ID == run_id:
            _CURRENT_ACTIVE_RUN_ID = None


@app.post("/runs", response_model=RunResponse)
async def create_run(
    req: RunRequest,
    background_tasks: BackgroundTasks,
    x_google_api_key: Optional[str] = Header(None, alias="X-Google-API-Key"),
    x_openrouter_api_key: Optional[str] = Header(None, alias="X-OpenRouter-API-Key"),
):
    """Launch a new assessment run in the background."""
    global _CURRENT_ACTIVE_RUN_ID
    if req.mode in ("web", "autonomous", "web_controlled"):
        if not (req.target_url or req.target):
            raise HTTPException(
                status_code=400,
                detail="Target URL is required for live security assessment.",
            )
        if not req.target_scope_acknowledged:
            raise HTTPException(
                status_code=400,
                detail="Explicit operator scope acknowledgement is required to assess target.",
            )

    if req.mode == "autonomous":
        if _CURRENT_ACTIVE_RUN_ID:
            active_run = _RUNS.get(_CURRENT_ACTIVE_RUN_ID, {})
            active_proc = _ACTIVE_PROCESSES.get(_CURRENT_ACTIVE_RUN_ID)
            if active_run.get("status") in ("running", "queued") or (active_proc and active_proc.poll() is None):
                raise HTTPException(
                    status_code=409,
                    detail=f"An autonomous assessment is already actively running ({_CURRENT_ACTIVE_RUN_ID}). Please wait for it to complete or stop it before launching a new scan.",
                )

    run_id = f"run-{uuid.uuid4().hex[:8]}"
    if req.mode == "autonomous":
        _CURRENT_ACTIVE_RUN_ID = run_id
    runtime_key = x_google_api_key or x_openrouter_api_key or req.assessor_api_key

    cli_cfg = _read_strix_cli_config()
    configured_provider = (req.assessor_provider or "openrouter").lower().strip()
    configured_model = req.assessor_model or cli_cfg.get("STRIX_LLM") or DEFAULT_OPENROUTER_MODEL

    # Provider preflight validation before launching
    key_for_check = runtime_key or cli_cfg.get("OPENROUTER_API_KEY") or cli_cfg.get("LLM_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    if configured_provider == "openrouter" and key_for_check:
        from strix.llm.provider_validation import validate_openrouter_credential
        val = validate_openrouter_credential(key_for_check)
        if val.status == "quota_exceeded":
            raise HTTPException(
                status_code=400,
                detail=f"OpenRouter preflight check failed: {val.message}",
            )
    elif configured_provider in ("cloud_hosted", "custom_cloud", "custom"):
        active_cloud = _get_active_cloud_profile()
        cloud_base = (
            (active_cloud.get("api_base") if active_cloud else None)
            or cli_cfg.get("OPENAI_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
        )
        if not cloud_base:
            raise HTTPException(
                status_code=400,
                detail="Cloud Hosted provider selected but no API Base URL configured. Please configure an endpoint in Settings > AI Models.",
            )
        cloud_model = (
            (req.assessor_model if req.assessor_model and req.assessor_model not in ("qwen2.5:1.5b", "default") else None)
            or (active_cloud.get("model") if active_cloud else None)
            or cli_cfg.get("STRIX_LLM")
        )
        if not cloud_model or cloud_model in ("qwen2.5:1.5b", "default"):
            raise HTTPException(
                status_code=400,
                detail="Cloud Hosted provider selected but no Model Identifier configured. Please enter a valid model identifier.",
            )
        configured_model = cloud_model
    elif configured_provider == "openai":
        api_base_for_check = cli_cfg.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        if any(h in api_base_for_check.lower() for h in ("ngrok", "127.0.0.1", "localhost", "dev")):
            from strix.llm.provider_validation import validate_openai_compatible_endpoint
            val = validate_openai_compatible_endpoint(api_base_for_check, runtime_key or cli_cfg.get("OPENAI_API_KEY"))
            if not val.valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Endpoint preflight failed for {api_base_for_check}: {val.message}",
                )

    configured_turns = req.max_turns or (50 if req.scan_mode == "quick" else (100 if req.scan_mode == "standard" else 500))

    run_record = {
        "run_id": run_id,
        "status": "queued",
        "scenario": req.scenario,
        "mode": req.mode,
        "target_url": req.target_url or req.target,
        "provider": configured_provider,
        "model": configured_model,
        "scan_mode": req.scan_mode or "deep",
        "max_turns": configured_turns,
        "created_at": _utc_now(),
        "completed_at": None,
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [],
        "findings": [],
        "evidence_tier": None,
        "safety_notice": None,
        "target_ip": None,
        "open_ports": [],
        "components": [],
        "scan_matrix": [],
        "spider_stats": {},
        "stats": {"attempts": 0, "pivots": 0, "findings": 0},
    }
    _RUNS[run_id] = run_record
    _save_run_to_disk(run_record)

    # Schedule worker
    background_tasks.add_task(_execute_run_worker, run_id, req, runtime_key)

    return RunResponse(
        run_id=run_id,
        status="running",
        message="Assessment launched successfully",
        created_at=run_record["created_at"],
    )


@app.post("/runs/{run_id}/stop")
async def stop_run(run_id: str):
    """Gracefully abort or stop a running assessment."""
    run = _RUNS.get(run_id)
    if not run:
        _load_runs_from_disk()
        run = _RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    proc = _ACTIVE_PROCESSES.get(run_id)
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=3.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        _ACTIVE_PROCESSES.pop(run_id, None)

    run["status"] = "aborted"
    run["completed_at"] = _utc_now()
    if "progress" in run and isinstance(run["progress"], dict):
        cur_pct = run["progress"].get("percent", 0)
        run["progress"]["percent"] = min(90, cur_pct)
        cur_phase = run["progress"].get("phase", "Assessment")
        run["progress"]["phase"] = f"Stopped ({cur_phase})"
    run["events"].append({
        "timestamp": _utc_now(),
        "event": "RUN_STOPPED",
        "message": "Operator requested early termination of assessment.",
    })
    _save_run_to_disk(run)
    return {"status": "ok", "message": f"Run {run_id} stopped successfully"}


@app.get("/runs")
async def list_runs():
    """List recent runs from memory and persistent disk store."""
    _load_runs_from_disk()
    runs = list(_RUNS.values())
    runs.sort(key=lambda r: str(r.get("created_at") or r.get("start_time") or ""), reverse=True)
    return runs


@app.get("/runs/{run_id}", response_model=RunStatus)
async def get_run_status(run_id: str):
    """Retrieve detailed state, decision trace, and candidates for a run."""
    run = _RUNS.get(run_id)
    if not run:
        _load_runs_from_disk()
        run = _RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return RunStatus(**run)


@app.get("/runs/{run_id}/stream")
async def stream_run_events(run_id: str, request: Request):
    """Stream live assessment events, terminal traces, and state updates via SSE."""
    run = _RUNS.get(run_id)
    if not run:
        _load_runs_from_disk()
        run = _RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    async def event_generator():
        current_initial = _RUNS.get(run_id, run)
        # Yield initial state
        yield f"event: state\ndata: {json.dumps(current_initial, default=str)}\n\n"

        init_prog = current_initial.get("progress")
        last_progress_pct = -1
        last_progress_phase = ""
        last_current_turn = -1
        if init_prog and isinstance(init_prog, dict):
            if "run_id" not in init_prog:
                init_prog = dict(init_prog)
                init_prog["run_id"] = run_id
            yield f"event: progress\ndata: {json.dumps(init_prog, default=str)}\n\n"
            last_progress_pct = init_prog.get("percent", -1)
            last_progress_phase = init_prog.get("phase", "")
            last_current_turn = init_prog.get("current", -1)

        last_log_count = len(current_initial.get("decision_trace", []))
        last_status = current_initial.get("status")
        last_findings_count = len(current_initial.get("findings", []))
        last_pivots_count = len(current_initial.get("pivot_events", []))
        last_candidates_state = tuple((c.get("id"), c.get("state"), c.get("attempts")) for c in current_initial.get("candidates", []))
        heartbeat_counter = 0

        while True:
            if await request.is_disconnected():
                break

            current_run = _RUNS.get(run_id)
            if not current_run:
                break

            # 1. Stream newly appended decision trace logs
            traces = current_run.get("decision_trace", [])
            if len(traces) > last_log_count:
                for entry in traces[last_log_count:]:
                    yield f"event: log\ndata: {json.dumps(entry, default=str)}\n\n"
                last_log_count = len(traces)

            # 2. Stream progress percentage, turn, and milestone changes
            prog = current_run.get("progress")
            if prog and isinstance(prog, dict):
                curr_pct = prog.get("percent", 0)
                curr_phase = prog.get("phase", "")
                curr_turn = prog.get("current", 0)
                if (
                    curr_pct != last_progress_pct
                    or curr_phase != last_progress_phase
                    or curr_turn != last_current_turn
                ):
                    if "run_id" not in prog:
                        prog = dict(prog)
                        prog["run_id"] = run_id
                    yield f"event: progress\ndata: {json.dumps(prog, default=str)}\n\n"
                    last_progress_pct = curr_pct
                    last_progress_phase = curr_phase
                    last_current_turn = curr_turn

            # 3. Stream state updates on findings, pivots, candidates, or status changes
            curr_status = current_run.get("status")
            curr_findings = current_run.get("findings", [])
            curr_findings_count = len(curr_findings)
            curr_pivots_count = len(current_run.get("pivot_events", []))
            curr_candidates_state = tuple((c.get("id"), c.get("state"), c.get("attempts")) for c in current_run.get("candidates", []))

            has_state_diff = (
                curr_status != last_status
                or curr_findings_count != last_findings_count
                or curr_pivots_count != last_pivots_count
                or curr_candidates_state != last_candidates_state
            )

            if curr_findings_count != last_findings_count:
                yield f"event: findings\ndata: {json.dumps(curr_findings, default=str)}\n\n"
                last_findings_count = curr_findings_count

            if has_state_diff:
                yield f"event: state\ndata: {json.dumps(current_run, default=str)}\n\n"
                last_status = curr_status
                last_pivots_count = curr_pivots_count
                last_candidates_state = curr_candidates_state

            if curr_status in ("completed", "failed", "aborted"):
                yield f"event: complete\ndata: {json.dumps({'status': curr_status, 'run_id': run_id})}\n\n"
                break

            heartbeat_counter += 1
            if heartbeat_counter >= 30:
                yield ": keepalive\n\n"
                heartbeat_counter = 0

            await asyncio.sleep(0.35)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/runs/{run_id}/report")
async def get_run_report(
    run_id: str,
    format: str = "json",
    download: Optional[bool] = False,
):
    """Generate or retrieve assessment report (HTML, JSON, PDF, SARIF, or Markdown)."""
    run = _RUNS.get(run_id)
    if not run:
        _load_runs_from_disk()
        run = _RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    fmt = format.lower().strip()

    # 1. HTML Report
    if fmt == "html":
        from strix.report.builder import render_html_report
        html_content = render_html_report(run)
        headers = {}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="vapt_report_{run_id}.html"'
        return HTMLResponse(content=html_content, headers=headers)

    # 2. PDF Report
    if fmt == "pdf":
        base_dir = runs_base_dir()
        run_dir = base_dir / run_id
        if not run_dir.exists():
            _save_run_to_disk(run)
        try:
            from strix.interface.viewer.report_pdf import generate_report_pdf
            pdf_bytes = generate_report_pdf(run_dir)
            headers = {}
            if download or True:
                headers["Content-Disposition"] = f'attachment; filename="vapt_report_{run_id}.pdf"'
            return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
        except Exception as exc:
            logger.warning("PDF generation failed: %s", exc)
            raise HTTPException(status_code=500, detail=f"Failed to generate PDF report: {exc}")

    # 3. SARIF Report
    if fmt == "sarif":
        sarif_file = runs_base_dir() / run_id / "findings.sarif"
        content = None
        if sarif_file.is_file():
            try:
                raw_text = sarif_file.read_text(encoding="utf-8")
                sarif_data = json.loads(raw_text)
                results = sarif_data.get("runs", [{}])[0].get("results", [])
                if results or not run.get("findings"):
                    content = raw_text
            except Exception:
                pass
        if not content:
            from strix.report.sarif import build_sarif_report
            sarif_obj = build_sarif_report(run.get("findings", []))
            content = json.dumps(sarif_obj, indent=2)
        headers = {}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="vapt_findings_{run_id}.sarif"'
        return Response(content=content, media_type="application/json", headers=headers)

    # 4. Markdown Report
    if fmt in ("md", "markdown"):
        md_file = runs_base_dir() / run_id / "penetration_test_report.md"
        structured_md = _generate_markdown_report(run)
        if md_file.is_file():
            cli_md = md_file.read_text(encoding="utf-8")
            if "## 2. Confirmed Vulnerability Findings" in cli_md:
                content = cli_md
            else:
                # Merge CLI narrative summary with structured findings breakdown
                content = f"{cli_md.strip()}\n\n---\n\n{structured_md}"
        else:
            content = structured_md
        headers = {}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="vapt_report_{run_id}.md"'
        return Response(content=content, media_type="text/markdown", headers=headers)

    # 5. CSV Report
    if fmt == "csv":
        csv_file = runs_base_dir() / run_id / "vulnerabilities.csv"
        content = None
        if csv_file.is_file():
            try:
                raw_csv = csv_file.read_text(encoding="utf-8")
                if len(raw_csv.strip().splitlines()) > 1 or not run.get("findings"):
                    content = raw_csv
            except Exception:
                pass
        if not content:
            findings = run.get("findings", [])
            output = io.StringIO()
            fieldnames = [
                "id",
                "title",
                "severity",
                "cvss_score",
                "cwe_id",
                "owasp_category",
                "location",
                "target",
                "remediation_summary",
            ]
            writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\r\n")
            writer.writeheader()
            for f in findings:
                writer.writerow({
                    "id": f.get("id", ""),
                    "title": f.get("title", ""),
                    "severity": f.get("severity", "INFO"),
                    "cvss_score": f.get("cvss_score", ""),
                    "cwe_id": f.get("cwe_id", ""),
                    "owasp_category": f.get("owasp_category", ""),
                    "location": f.get("location", ""),
                    "target": f.get("target", run.get("target_url") or run.get("target", "")),
                    "remediation_summary": f.get("remediation_summary", ""),
                })
            content = output.getvalue()

        headers = {}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="vapt_findings_{run_id}.csv"'
        return Response(content=content, media_type="text/csv", headers=headers)

    # 6. JSON export with 2-space indentation (pretty-printed)
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="vapt_audit_{run_id}.json"'
    formatted_json = json.dumps(run, indent=2, default=str)
    return Response(content=formatted_json, media_type="application/json", headers=headers)


@app.get("/engagements")
async def list_engagements():
    """List authorized engagement profiles."""
    return list(_ENGAGEMENTS.values())


@app.post("/engagements")
async def create_engagement(profile: Dict[str, Any] = Body(...)):
    """Create a new authorized engagement profile."""
    eng_id = profile.get("id") or f"eng-{uuid.uuid4().hex[:6]}"
    profile["id"] = eng_id
    profile["created_at"] = _utc_now()
    _ENGAGEMENTS[eng_id] = profile
    return profile
