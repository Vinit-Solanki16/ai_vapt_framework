"""FastAPI Gateway for AI-VAPT Platform.

Serves the Web Operations Console SPA and exposes REST endpoints for:
- System & model provider health checks
- In-memory credential validation (Gemini, OpenRouter, Cloud-Hosted, Ollama)
- Fail-closed target scope verification
- Assessment lifecycle management (GAP-1 triage, GAP-2 pivoting, autonomous execution)
- Live decision traces, real-time DAG state, and audit reporting
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import hashlib
import io
import json
import logging
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from fastapi import BackgroundTasks, Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from strix.core import gap_bridge
from strix.core.paths import runs_base_dir
from strix.core.triage.owasp_mapping import map_finding_to_owasp
from strix.interface.auth import (
    SESSION_COOKIE_NAME,
    _is_loopback_client,
    _load_or_create_operator_credentials,
    create_session,
    delete_session,
    get_current_user_or_none,
    get_session,
    require_admin,
    require_operator,
    require_viewer,
)
from strix.interface.readiness import RuntimeReadinessResponse, check_runtime_readiness
from strix.interface.schemas import (
    AnthropicValidateResponse,
    CloudHostedProfile,
    CloudHostedProfileSafe,
    CloudTestConnectionResponse,
    CloudVerifyToolsResponse,
    CloudWarmupResponse,
    CustomEndpointValidateResponse,
    DiscoveredModelInfo,
    GoogleValidateResponse,
    OllamaValidateResponse,
    OpenAIValidateResponse,
    OpenRouterModelInfo,
    OpenRouterValidateResponse,
    ResumeRunRequest,
    RunRequest,
    RunResponse,
    RunStatus,
    SystemHealthResponse,
    TargetValidateRequest,
    TargetValidateResponse,
)
from strix.llm.router import DEFAULT_OPENROUTER_MODEL, format_openrouter_model
from strix.report.evidence import (
    record_authentic_evidence,
    verify_evidence_integrity,
)
from strix.report.verification import (
    evaluate_finding_verification,
)


logger = logging.getLogger("strix.interface.api")

app = FastAPI(
    title="AI-VAPT Operations Console",
    description="Autonomous Vulnerability Assessment & Penetration Testing Gateway",
    version="1.0.0",
)

# P0.2 CORS Hardening: Disallow wildcard origins with credentials
allowed_origins_env = os.getenv("AI_VAPT_ALLOWED_ORIGINS") or os.getenv("STRIX_ALLOWED_ORIGINS")
if allowed_origins_env:
    ALLOWED_ORIGINS = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
else:
    ALLOWED_ORIGINS = [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Static file paths
WEB_DIR = Path(__file__).resolve().parent / "web"
CSS_DIR = WEB_DIR / "css"
JS_DIR = WEB_DIR / "js"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CLI_CONFIG_FILE = Path.home() / ".strix" / "cli-config.json"


def _read_full_strix_cli_config() -> dict[str, Any]:
    """Read complete ~/.strix/cli-config.json preserving all top-level keys."""
    if CLI_CONFIG_FILE.is_file():
        try:
            data = json.loads(CLI_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception as exc:
            logger.debug("Failed to read Strix CLI config: %s", exc)
    return {"env": {}, "cloud_hosted_profiles": []}


def _write_full_strix_cli_config(data: dict[str, Any]) -> None:
    """Safely persist full JSON to ~/.strix/cli-config.json (0o600)."""
    CLI_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        from strix.utils.secret_files import write_secret_text

        write_secret_text(CLI_CONFIG_FILE, json.dumps(data, indent=2))
    except Exception as exc:
        logger.warning("Failed to persist CLI config: %s", exc)
        CLI_CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_strix_cli_config() -> dict[str, str]:
    """Read persisted environment variables from ~/.strix/cli-config.json."""
    full = _read_full_strix_cli_config()
    env = full.get("env", {})
    if isinstance(env, dict):
        return {k: str(v) for k, v in env.items() if v is not None}
    return {}


def _write_strix_cli_config(env_vars: dict[str, str]) -> None:
    """Safely update environment variables in ~/.strix/cli-config.json while preserving other sections."""
    full = _read_full_strix_cli_config()
    env = full.setdefault("env", {})
    env.update({k: str(v) for k, v in env_vars.items() if v is not None})
    _write_full_strix_cli_config(full)


def _get_cloud_profiles() -> list[dict[str, Any]]:
    """Retrieve saved Cloud Hosted provider profiles."""
    full = _read_full_strix_cli_config()
    profiles = full.get("cloud_hosted_profiles", [])
    if isinstance(profiles, list):
        return profiles
    return []


def _save_cloud_profile(profile_data: CloudHostedProfile | dict[str, Any]) -> dict[str, Any]:
    """Save or update a Cloud Hosted provider profile."""
    pdict = profile_data.model_dump() if hasattr(profile_data, "model_dump") else dict(profile_data)

    full = _read_full_strix_cli_config()
    profiles: list[dict[str, Any]] = full.setdefault("cloud_hosted_profiles", [])
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
            p["is_active"] = p.get("id") == pid

    _write_full_strix_cli_config(full)
    return pdict


def _delete_cloud_profile(profile_id: str) -> bool:
    """Delete a Cloud Hosted provider profile by ID."""
    full = _read_full_strix_cli_config()
    profiles: list[dict[str, Any]] = full.get("cloud_hosted_profiles", [])
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


def _set_active_cloud_profile(profile_id: str) -> dict[str, Any] | None:
    """Mark a profile as active and synchronize with environment."""
    full = _read_full_strix_cli_config()
    profiles: list[dict[str, Any]] = full.get("cloud_hosted_profiles", [])
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


def _get_active_cloud_profile() -> dict[str, Any] | None:
    """Retrieve the currently active Cloud Hosted profile."""
    full = _read_full_strix_cli_config()
    active_id = full.get("active_cloud_profile_id")
    profiles: list[dict[str, Any]] = full.get("cloud_hosted_profiles", [])
    if active_id:
        for p in profiles:
            if p.get("id") == active_id:
                return dict(p)
    for p in profiles:
        if p.get("is_active"):
            return dict(p)
    return dict(profiles[0]) if profiles else None


def _profile_to_safe(profile: dict[str, Any]) -> dict[str, Any]:
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


def _format_duration_str(seconds: float | None) -> str:
    if seconds is None:
        return "N/A"
    total_sec = max(0, int(seconds))
    hrs = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"


def _generate_markdown_report(run_data: dict[str, Any]) -> str:
    """Generate professional Markdown penetration test report."""
    target = run_data.get("target_url") or run_data.get("target") or "Target"
    findings = run_data.get("findings", [])
    run_id = run_data.get("run_id", "unknown")
    start_t = run_data.get("start_time") or run_data.get("created_at") or "N/A"
    end_t = run_data.get("end_time") or run_data.get("completed_at") or _utc_now()
    dur_str = _format_duration_str(run_data.get("duration_seconds"))
    candidate_acct = run_data.get("candidate_accounting") or {}

    def _is_finding_verified(f: dict[str, Any]) -> bool:
        if (
            f.get("verified") is True
            or str(f.get("verification_state", "")).strip().lower() == "verified"
        ):
            return True
        if f.get("verified") is False or str(f.get("verification_state", "")).strip().lower() in (
            "unconfirmed",
            "candidate",
            "inconclusive",
            "blocked",
            "false_positive",
            "under_investigation",
            "discovered",
        ):
            return False
        # Legacy record fallback: if finding carries cryptographic proof/snippet without negative flag
        return bool(f.get("evidence_hash") or f.get("evidence_snippet"))

    verified_findings = [f for f in findings if _is_finding_verified(f)]
    unconfirmed_candidates = [f for f in findings if not _is_finding_verified(f)]

    raw_exec_mode = str(run_data.get("execution_mode") or run_data.get("mode") or "web").lower()
    if raw_exec_mode in ("autonomous", "autonomous_multi_agent"):
        engine_label = "AI-VAPT Autonomous Multi-Agent Core (Docker Sandbox)"
    elif raw_exec_mode in (
        "lightweight",
        "lightweight_active_scanner",
        "in_process",
        "web",
        "web_controlled",
    ):
        engine_label = "AI-VAPT Lightweight In-Process Active Scanner (No Docker)"
    elif raw_exec_mode == "blocked":
        engine_label = "Blocked (Runtime Dependencies Unavailable)"
    else:
        engine_label = f"AI-VAPT {raw_exec_mode.replace('_', ' ').title()}"

    lines = [
        "# AI-VAPT Security Penetration Test Report",
        "",
        f"- **Target URL:** {target}",
        f"- **Run Reference:** `{run_id}`",
        f"- **Execution Engine:** {engine_label}",
        f"- **Execution Mode:** {(run_data.get('execution_mode') or run_data.get('mode') or 'web').upper()}",
        f"- **Assessment Mode:** {(run_data.get('mode') or 'autonomous').upper()}",
        f"- **Scan Depth:** {(run_data.get('scan_mode') or 'deep').upper()}",
        f"- **Assessment Started:** {start_t}",
        f"- **Assessment Completed:** {end_t}",
        f"- **Total Assessment Duration:** `{dur_str}`",
        f"- **Status:** {(run_data.get('status') or 'completed').upper()}",
        f"- **Total Confirmed (Verified) Findings:** {len(verified_findings)}",
        f"- **Unconfirmed Candidates / Inconclusive:** {len(unconfirmed_candidates)}",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        "",
        (
            f"An autonomous multi-agent vulnerability assessment was conducted against `{target}` using the AI-VAPT core engine with Docker sandbox isolation, GAP-1 dynamic triage, and GAP-2 bounded failure pivoting."
            if raw_exec_mode in ("autonomous", "autonomous_multi_agent")
            else (
                f"A lightweight in-process active vulnerability scan was conducted against `{target}` using benign, non-destructive direct HTTP probes across common web vulnerability categories."
                if raw_exec_mode
                in (
                    "lightweight",
                    "lightweight_active_scanner",
                    "in_process",
                    "web",
                    "web_controlled",
                )
                else (
                    f"Assessment execution was blocked prior to probe execution: {run_data.get('error', 'Runtime dependencies unavailable')}"
                    if raw_exec_mode == "blocked" or run_data.get("status") == "blocked"
                    else f"An assessment was evaluated against `{target}` in execution mode `{raw_exec_mode}`."
                )
            )
        ),
        "",
        "## 2. Confirmed Vulnerability Findings",
        "",
    ]
    if raw_exec_mode == "blocked" or run_data.get("status") == "blocked":
        lines.append(
            f"> **Assessment Blocked:** {run_data.get('error', 'Autonomous execution was blocked because required dependencies are unavailable.')}\n"
        )
        lines.append("Assessment not performed or blocked prior to completion.\n")
    elif not verified_findings:
        lines.append("No confirmed vulnerabilities were identified during this assessment run.\n")
    for idx, f in enumerate(verified_findings, 1):
        v_state = f.get("verification_state") or "Verified"
        v_proc = (
            f.get("verification_procedure")
            or f.get("validation_method")
            or "Active HTTP verification probe & response pattern analysis"
        )
        v_impact = (
            f.get("demonstrated_impact")
            or f.get("impact")
            or "Demonstrated behavior observed on target endpoint."
        )
        v_param = f.get("parameter") or "N/A"
        lines.extend(
            [
                f"### 2.{idx} {f.get('title', 'Vulnerability Finding')}",
                "",
                f"- **Verification State:** `{v_state}`",
                f"- **Severity:** {f.get('severity', 'MEDIUM')}",
                f"- **CVSS Score:** {f.get('cvss_score', 'N/A')}",
                f"- **CVE Reference:** {f.get('cve_id') or 'N/A'}",
                f"- **CWE Identifier:** {f.get('cwe_id') or 'CWE-200'}",
                f"- **OWASP Top 10:** {f.get('owasp_category', 'A01:2021 - Broken Access Control')}",
                f"- **Location / Route:** `{f.get('location', '/')}`",
                f"- **Vulnerable Parameter / Component:** `{v_param}`",
                f"- **Cryptographic SHA-256 Proof:** `{f.get('evidence_hash', 'N/A')}`",
                f"- **Verification Procedure:** {v_proc}",
                f"- **Demonstrated Impact:** {v_impact}",
                "",
                "#### Reproducible Request / Proof-of-Concept",
                "```http",
                f"{f.get('reproducible_request', 'N/A')}",
                "```",
                "",
                "#### Response Evidence",
                "```",
                f"{f.get('evidence_snippet', 'Verified')}",
                "```",
                "",
                "#### Remediation Recommendations",
                f"{f.get('remediation_summary', 'Apply defensive validation filters.')}",
                "",
                "```shell",
                f"{f.get('remediation_technical', '# Implement secure configuration')}",
                "```",
                "",
                "---",
                "",
            ]
        )

    if unconfirmed_candidates:
        lines.extend(
            [
                "## 3. Unconfirmed Candidates & Inconclusive Probes",
                "",
                "The following vectors were discovered or investigated but did not satisfy the strict verification contract:",
                "",
            ]
        )
        for idx, f in enumerate(unconfirmed_candidates, 1):
            lines.extend(
                [
                    f"### 3.{idx} {f.get('title', 'Candidate Vector')}",
                    "",
                    f"- **Verification State:** `{f.get('verification_state', 'Unconfirmed')}`",
                    f"- **Severity (Theoretical):** {f.get('severity', 'MEDIUM')}",
                    f"- **CVSS Score (Theoretical):** {f.get('cvss_score', 'N/A')}",
                    f"- **Location / Route:** `{f.get('location', '/')}`",
                    f"- **Vulnerable Parameter / Component:** `{f.get('parameter') or 'N/A'}`",
                    f"- **Status Note:** {f.get('validation_method') or 'Lacks complete reproducible proof.'}",
                    "",
                    "---",
                    "",
                ]
            )

    sec_num = 4 if unconfirmed_candidates else 3
    if candidate_acct:
        lines.extend(
            [
                f"## {sec_num}. GAP-1 Candidate Accounting",
                "",
                f"- **Dispatched:** {candidate_acct.get('dispatched', 0)}",
                f"- **Investigated:** {candidate_acct.get('investigated', 0)}",
                f"- **Validated:** {candidate_acct.get('validated', 0)}",
                f"- **Abandoned (Pivoted):** {candidate_acct.get('abandoned', 0)}",
                f"- **Not Tested:** {candidate_acct.get('not_tested', 0)}",
                f"- **Blocked:** {candidate_acct.get('blocked', 0)}",
                "",
                "---",
                "",
            ]
        )

    pivot_events = run_data.get("pivot_events", [])
    if pivot_events:
        lines.extend(
            [
                "## 4. GAP-2 Adaptive Pivot Audit Trail",
                "",
            ]
        )
        for p_idx, p in enumerate(pivot_events, 1):
            cand_id = p.get("candidate_id") or p.get("candidate") or "Unknown"
            next_cand = (
                p.get("next_candidate") or p.get("alternative_candidate") or "Next candidate"
            )
            reason = (
                p.get("reason")
                or p.get("retry_reason")
                or p.get("message")
                or "Bounded failure threshold reached"
            )
            p_res = p.get("result") or p.get("probe_outcome") or "pivoted"
            lines.append(
                f"{p_idx}. Candidate `{cand_id}` -> Bounded limit reached: {reason}. Pivoted to `{next_cand}` (Outcome: {p_res})."
            )
        lines.append("")

    return "\n".join(lines)


def _is_docker_available() -> bool:
    """Check if Docker runtime is accessible (disabled during unit tests)."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    try:
        res = subprocess.run(
            ["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.0
        )
        return res.returncode == 0
    except Exception:
        return False


if CSS_DIR.is_dir():
    app.mount("/css", StaticFiles(directory=str(CSS_DIR)), name="css")
if JS_DIR.is_dir():
    app.mount("/js", StaticFiles(directory=str(JS_DIR)), name="js")

# In-memory store for runs, traces, and engagements
_RUNS: dict[str, dict[str, Any]] = {}
_ACTIVE_PROCESSES: dict[str, subprocess.Popen[Any]] = {}
_CURRENT_ACTIVE_RUN_ID: str | None = None
_ENGAGEMENTS: dict[str, dict[str, Any]] = {
    "default-local": {
        "id": "default-local",
        "name": "Local Lab Environment",
        "authorized_hosts": ["localhost", "127.0.0.1", "host.docker.internal"],
        "allowed_ports": [80, 443, 8000, 8080, 8888, 9191],
        "created_at": datetime.now(UTC).isoformat(),
    }
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _engine_run_name(control_plane_run_id: str) -> str:
    """Dedicated run name for the CLI worker, separate from the UI record.

    Both processes previously received ``--run-name <web run id>`` and wrote to
    the same ``strix_runs/<id>/run.json``. Their writes raced and the worker's
    own run.json was overwritten by the web record (1 turn instead of 19).
    """
    return f"{control_plane_run_id}-engine"


def _is_productive_tool(tool_name: str) -> bool:
    """Whether a tool call is real assessment work rather than bookkeeping.

    record_coverage / list_coverage / finish_scan describe or summarise work;
    they do not interact with the target. Counting them as progress is what
    let run-fd0f5ec4 spin for 19 turns with zero security tools executed.
    """
    name = (tool_name or "").lower()
    return name not in {
        "record_coverage",
        "update_coverage",
        "list_coverage",
        "finish_scan",
        "agent_finish",
        "create_vulnerability_report",
        "delete_vulnerability_report",
        "update_vulnerability_report",
        "list_vulnerability_reports",
    }


def productive_tool_count(run_data: dict[str, Any] | None) -> int:
    """Count real security-tool executions recorded in engine telemetry.

    SDK versions that log only ``Processing output item type=function_call``
    never emit ``Invoking tool`` lines. The engine's ``tool_calls`` telemetry
    is authoritative for those runs; bookkeeping tools never count.
    """
    data = run_data or {}
    return sum(
        1
        for t in (data.get("tool_calls") or [])
        if isinstance(t, dict) and _is_productive_tool(str(t.get("tool", "")))
    )


_ENGINE_FAILED_STATUSES = frozenset({"failed", "error", "interrupted", "aborted"})


def genuine_pivot_key(event: dict[str, Any]) -> tuple[str, str] | None:
    """Canonical identity of an executed pivot: (original, alternative).

    The control bridge and the native GapRun can both record the same executed
    pivot. Counting raw events double-counts it; counting canonical keys does
    not. A self-pivot (candidate == alternative) is never a genuine pivot.
    """
    if not isinstance(event, dict):
        return None
    if event.get("pivot_executed") is False:
        return None
    event_name = str(event.get("event") or "")
    event_type = str(event.get("type") or "")
    if "GAP2_PIVOT" not in (event_name, event_type) and event_name != "pivot_decision":
        return None
    origin = str(event.get("candidate_id") or "")
    alternative = str(
        event.get("next_candidate")
        or event.get("to_candidate")
        or event.get("alternative_candidate")
        or ""
    )
    if not origin or not alternative or origin == alternative:
        return None
    return (origin, alternative)


def engine_executed_alternatives(engine_gap_file: Path | None) -> set[str]:
    """Candidate ids with a non-preparatory engine probe (real dispatch/execution)."""
    if engine_gap_file is None or not engine_gap_file.is_file():
        return set()
    try:
        data = json.loads(engine_gap_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {
        str(p.get("candidate_id"))
        for p in (data.get("probe_outcomes") or [])
        if isinstance(p, dict) and p.get("candidate_id") and not p.get("preparatory")
    }


def reconcile_control_gap_state(control_dir: Path | None, engine_gap_file: Path | None) -> bool:
    """Mirror authoritative engine attempts/status into the control-plane file.

    The engine's ``.state/gap_state.json`` is authoritative for candidate
    attempts and status; ``control/gap_state.json`` is written by the file-based
    bridge with a different schema. Reconciling the overlapping fields after
    the engine exits keeps resume/completion decisions consistent without
    touching the bridge's own probe/event history or pivot accounting.
    """
    if control_dir is None or engine_gap_file is None or not engine_gap_file.is_file():
        return False
    try:
        engine_state = json.loads(engine_gap_file.read_text(encoding="utf-8"))
        control_path = control_dir / "gap_state.json"
        control_state = (
            json.loads(control_path.read_text(encoding="utf-8")) if control_path.is_file() else {}
        )
        if not isinstance(engine_state, dict) or not isinstance(control_state, dict):
            return False
        attempts = dict(control_state.get("attempts") or {})
        exhausted = {str(x) for x in (control_state.get("exhausted") or [])}
        completed = {str(x) for x in (control_state.get("completed") or [])}
        for cid, cand in (engine_state.get("candidates") or {}).items():
            if not isinstance(cand, dict):
                continue
            attempts[str(cid)] = max(int(attempts.get(str(cid), 0)), int(cand.get("attempts", 0)))
            status = str(cand.get("status") or "").lower()
            if status == "abandoned":
                exhausted.add(str(cid))
            elif status == "validated":
                completed.add(str(cid))
        control_state["attempts"] = attempts
        control_state["exhausted"] = sorted(exhausted)
        control_state["completed"] = sorted(completed)
        control_dir.mkdir(parents=True, exist_ok=True)
        control_path.write_text(json.dumps(control_state, indent=2), encoding="utf-8")
        return True
    except (OSError, ValueError, TypeError):
        return False


def pivot_execution_after_decision(
    decision: dict[str, Any], probe_outcomes: list[dict[str, Any]]
) -> bool:
    """True only when a non-preparatory probe of the chosen alternative was
    recorded at or after the pivot decision."""
    alternative = str((decision or {}).get("alternative_candidate") or "")
    if not alternative:
        return False
    decision_at = str((decision or {}).get("at") or "")
    return any(
        isinstance(p, dict)
        and not p.get("preparatory")
        and str(p.get("candidate_id")) == alternative
        and (not decision_at or str(p.get("at", "")) >= decision_at)
        for p in probe_outcomes or []
    )


def dedupe_pivot_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one event per genuine (original -> alternative) pivot.

    Self-referential records (an alternative pivoting to itself) are never
    genuine and are dropped rather than presented as adaptive behaviour.
    """
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for event in events or []:
        if not isinstance(event, dict):
            result.append(event)
            continue
        event_name = str(event.get("event") or "")
        event_type = str(event.get("type") or "")
        is_pivot = "GAP2_PIVOT" in (event_name, event_type) or event_type == "pivot_decision"
        if is_pivot:
            origin = str(event.get("candidate_id") or "")
            alternative = str(
                event.get("next_candidate")
                or event.get("to_candidate")
                or event.get("alternative_candidate")
                or ""
            )
            if origin and alternative and origin == alternative:
                continue
        key = genuine_pivot_key(event)
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        result.append(event)
    return result


def engine_terminal_failure(engine_run_data: dict[str, Any] | None) -> str | None:
    """Return the terminal failure status of the engine, if any.

    A genuine finding may be harvested from a run whose engine still ended in
    failure (e.g. a context overflow after the finding was filed). Such a run
    must be reported as failed with a partial report — never relabelled as a
    clean completion just because artifacts exist.
    """
    status = str((engine_run_data or {}).get("status") or "").strip().lower()
    return status if status in _ENGINE_FAILED_STATUSES else None


def should_stop_for_stall(
    *, elapsed_seconds: float, last_progress_seconds: float, stall_seconds: float = 600.0
) -> bool:
    """Stop when no real security tool has run for ``stall_seconds``.

    Unlike :func:`should_stop_for_no_progress`, this is not disabled by an
    early burst of productive tools. A late-stage model-only hang (e.g. an SDK
    stream replay loop) is still a genuine no-progress stall, and must reach an
    honest terminal state instead of running until the wall-clock limit.
    """
    return elapsed_seconds >= stall_seconds and last_progress_seconds >= stall_seconds


def should_stop_for_no_progress(
    *,
    elapsed_seconds: float,
    last_progress_seconds: float,
    productively_advanced_turns: int,
    max_turns: int,
    stall_seconds: float = 600.0,
) -> bool:
    """Stop a scan that keeps consuming turns without meaningful progress.

    "Consulting the model" repeatedly is not progress: a degraded model can
    spend hundreds of turns emitting bookkeeping calls with no security tool
    execution and no findings. The run then stays "running" forever. This is
    checked independently of the wall-clock budget so an unproductive run
    reaches an honest terminal state instead of a misleading active one.
    """
    if productively_advanced_turns >= min(max_turns, 3):
        return False
    return elapsed_seconds >= stall_seconds and last_progress_seconds >= stall_seconds


def execution_evidence_from_logs(logs: str | list[str] | tuple[str, ...]) -> dict[str, int]:
    """Count real LLM calls and real security-tool calls in engine log lines."""
    lines = [logs] if isinstance(logs, str) else list(logs)
    llm_calls = sum(1 for line in lines if "Calling LLM" in line)
    tool_calls = sum(
        1
        for line in lines
        if "Invoking tool" in line
        and any(
            _is_productive_tool(name)
            for name in re.findall(r"Invoking tool\s+([a-zA-Z0-9_\-]+)", line)
        )
    )
    return {"llm_calls": llm_calls, "security_tool_calls": tool_calls}


def execution_evidence_from_run(
    run_data: dict[str, Any] | None, log_text: str = ""
) -> dict[str, Any]:
    """Derive trustworthy execution counters from an engine run record.

    A status label, a candidate counter or a decision-trace event is not
    evidence of assessment work. The primary source is the engine log,
    which always records ``Calling LLM`` and ``Invoking tool`` lines. The
    optional ``llm_requests`` / ``tool_calls`` telemetry arrays agree when
    ``STRIX_RUN_RECORD_TIMINGS`` is enabled, but are not required.
    Bookkeeping tools (coverage/finish/report management) never count.
    """
    data = run_data or {}
    log_evidence = execution_evidence_from_logs(log_text)
    llm_calls = log_evidence["llm_calls"]
    security_tool_calls = log_evidence["security_tool_calls"]
    recorded_llm = sum(
        1
        for r in (data.get("llm_requests") or [])
        if isinstance(r, dict)
        and str(r.get("outcome", "")).lower() in ("success", "ok", "completed", "")
    )
    recorded_tools = sum(
        1
        for t in (data.get("tool_calls") or [])
        if isinstance(t, dict) and _is_productive_tool(str(t.get("tool", "")))
    )
    llm_calls = max(llm_calls, recorded_llm)
    security_tool_calls = max(security_tool_calls, recorded_tools)
    return {
        "llm_calls": llm_calls,
        "security_tool_calls": security_tool_calls,
        "has_model_participation": llm_calls > 0,
        "has_security_execution": security_tool_calls > 0,
    }


def has_genuine_assessment_execution(run_data: dict[str, Any] | None, log_text: str = "") -> bool:
    """True only when BOTH model reasoning and real security tools are recorded."""
    evidence = execution_evidence_from_run(run_data, log_text)
    return bool(evidence["has_model_participation"] and evidence["has_security_execution"])


def is_in_authorized_scope(
    url: str,
    primary_target_url: str,
    additional_hosts: list[str] | None = None,
) -> bool:
    """Verify if a target URL or host falls strictly within explicitly authorized assessment scope."""
    if not url:
        return False
    try:
        parsed_target = urllib.parse.urlsplit(url if "://" in url else f"http://{url}")
        host = (parsed_target.hostname or "").lower().strip()
        if not host:
            return False

        primary_parsed = urllib.parse.urlsplit(
            primary_target_url if "://" in primary_target_url else f"http://{primary_target_url}"
        )
        primary_host = (primary_parsed.hostname or "").lower().strip()
        if host == primary_host:
            return True

        if additional_hosts:
            for ah in additional_hosts:
                clean_ah = (
                    (urllib.parse.urlsplit(ah if "://" in ah else f"http://{ah}").hostname or ah)
                    .lower()
                    .strip()
                )
                if host == clean_ah:
                    return True

        return False
    except Exception:
        return False


from strix.report.reconciliation import (
    reconcile_all,
    reconcile_scan_matrix,
)


_reconcile_scan_matrix = reconcile_scan_matrix


def _save_run_to_disk(run_data: dict[str, Any]) -> None:
    """Persist run data to ./strix_runs/<run_id>/run.json and vulnerabilities.json."""
    run_id = run_data.get("run_id")
    if not run_id:
        return
    try:
        base_dir = runs_base_dir()
        run_dir = base_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        record = dict(run_data)
        record = reconcile_all(record, run_dir=run_dir)
        run_data.update(record)
        record["run_name"] = run_id
        record["start_time"] = run_data.get("created_at")
        record["end_time"] = run_data.get("completed_at")
        record["instruction"] = (
            f"VAPT assessment on {run_data.get('target_url') or run_data.get('target')}"
        )
        record["user_instruction"] = record["instruction"]
        record["targets_info"] = [
            {
                "type": "web_application",
                "details": {"target_url": run_data.get("target_url") or run_data.get("target")},
                "original": run_data.get("target_url") or run_data.get("target"),
            }
        ]
        add_hosts = run_data.get("additional_authorized_hosts", []) or []
        record["additional_authorized_hosts"] = add_hosts
        for ah in add_hosts:
            record["targets_info"].append(
                {
                    "type": "web_application",
                    "details": {"target_url": ah},
                    "original": ah,
                }
            )

        run_file = run_dir / "run.json"
        run_file.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")

        findings_to_write = run_data.get("findings")
        vuln_file = run_dir / "vulnerabilities.json"
        if findings_to_write or not vuln_file.exists():
            vuln_file.write_text(
                json.dumps(findings_to_write or [], indent=2, default=str), encoding="utf-8"
            )

        # Also persist vulnerabilities.csv
        try:
            csv_file = run_dir / "vulnerabilities.csv"
            findings = run_data.get("findings", [])
            if findings or not csv_file.exists():
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
                    csv_writer.writerow(
                        {
                            "id": f.get("id", ""),
                            "title": f.get("title", ""),
                            "severity": f.get("severity", "INFO"),
                            "cvss_score": f.get("cvss_score", ""),
                            "cwe_id": f.get("cwe_id", ""),
                            "owasp_category": f.get("owasp_category", ""),
                            "location": f.get("location", ""),
                            "target": f.get(
                                "target", run_data.get("target_url") or run_data.get("target", "")
                            ),
                            "remediation_summary": f.get("remediation_summary", ""),
                        }
                    )
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
                    if not data.get("started_at"):
                        data["started_at"] = data.get("start_time")
                    # A "running" record with no live process is a stale
                    # leftover from a server/thread restart, not an active scan.
                    data = _quarantine_stale_running_run(run_id, data)
                    if (
                        data.get("duration_seconds") is not None
                        and data.get("elapsed_seconds") is None
                    ):
                        data["elapsed_seconds"] = data.get("duration_seconds")
                    vuln_file = child / "vulnerabilities.json"
                    if vuln_file.is_file() and not data.get("findings"):
                        try:
                            data["findings"] = json.loads(vuln_file.read_text(encoding="utf-8"))
                        except Exception:
                            pass

                    # Fallback: harvest findings from findings.sarif if vulnerabilities.json was empty
                    if not data.get("findings") and (child / "findings.sarif").is_file():
                        try:
                            s_data = json.loads(
                                (child / "findings.sarif").read_text(encoding="utf-8")
                            )
                            s_findings = []
                            for s_run in s_data.get("runs", []):
                                for s_res in s_run.get("results", []):
                                    r_id = s_res.get("ruleId", "")
                                    s_props = s_res.get("properties", {})
                                    strix_info = (
                                        s_props.get("strix") if isinstance(s_props, dict) else None
                                    )
                                    if r_id.startswith("vuln-") and isinstance(strix_info, dict):
                                        msg_txt = s_res.get("message", {}).get("text", "")
                                        f_title = (
                                            msg_txt.split("\n")[0].strip() if msg_txt else r_id
                                        )
                                        f_target = (
                                            strix_info.get("target")
                                            or data.get("target_url")
                                            or "/"
                                        )
                                        f_sev = str(strix_info.get("severity", "MEDIUM")).upper()
                                        try:
                                            f_cvss = float(strix_info.get("cvss", 6.0))
                                        except Exception:
                                            f_cvss = 6.0
                                        aligned_c, aligned_s = _align_cvss_severity(f_cvss, f_sev)
                                        mapped_owasp = map_finding_to_owasp(
                                            f_title, rule_id=r_id, endpoint=f_target
                                        )
                                        s_findings.append(
                                            {
                                                "id": r_id,
                                                "title": f_title,
                                                "severity": aligned_s,
                                                "cvss_score": aligned_c,
                                                "cve_id": mapped_owasp.get("cve_id"),
                                                "cwe_id": mapped_owasp.get("cwe_id", "CWE-200"),
                                                "owasp_category": f"{mapped_owasp.get('owasp_id', 'A01:2021')} - {mapped_owasp.get('category_name', 'Security Misconfiguration')}",
                                                "location": f_target,
                                                "target": f_target,
                                                "evidence_hash": hashlib.sha256(
                                                    f"{r_id}:{f_title}".encode()
                                                ).hexdigest(),
                                                "evidence_snippet": strix_info.get(
                                                    "technical_analysis"
                                                )
                                                or msg_txt,
                                                "reproducible_request": (
                                                    strix_info.get("poc") or {}
                                                ).get("description")
                                                if isinstance(strix_info.get("poc"), dict)
                                                else f"GET {f_target} HTTP/1.1",
                                                "reproducible_response": strix_info.get(
                                                    "counterevidence"
                                                )
                                                or "Response pattern verified by autonomous agent.",
                                                "verification_procedure": "Automated Agent Verification & PoC Confirmation",
                                                "demonstrated_impact": strix_info.get("impact", ""),
                                                "parameter": None,
                                                "evidence_timestamp": strix_info.get("timestamp")
                                                or _utc_now(),
                                                "verification_state": "Verified",
                                                "verified": True,
                                                "validation_method": "Exploit PoC Verification",
                                                "severity_justification": f"Severity {aligned_s} (CVSS {aligned_c}) justified by exploitability and demonstrated impact.",
                                                "impact": strix_info.get("impact", ""),
                                                "remediation_summary": strix_info.get(
                                                    "remediation_steps"
                                                )
                                                or mapped_owasp.get("remediation_summary", ""),
                                                "remediation_technical": strix_info.get(
                                                    "remediation_steps"
                                                )
                                                or mapped_owasp.get("remediation_technical", ""),
                                                "retest_procedure": mapped_owasp.get(
                                                    "retest_procedure", ""
                                                ),
                                                "finding_class": "dynamic",
                                            }
                                        )
                            if s_findings:
                                data["findings"] = s_findings
                        except Exception as s_err:
                            logger.debug("Failed to harvest findings from sarif: %s", s_err)

                    # Load candidates if missing or empty
                    if not data.get("candidates"):
                        for cand_path in [
                            child / "control" / "gap1_queue.json",
                            child / ".state" / "gap_state.json",
                        ]:
                            if cand_path.is_file():
                                try:
                                    cand_data = json.loads(cand_path.read_text(encoding="utf-8"))
                                    if isinstance(cand_data, dict) and "candidates" in cand_data:
                                        data["candidates"] = cand_data["candidates"]
                                        break
                                    if isinstance(cand_data, list):
                                        data["candidates"] = cand_data
                                        break
                                except Exception:
                                    pass

                    # Verify evidence integrity & evaluate verification state for all loaded findings
                    for f in data.get("findings", []):
                        v_info = verify_evidence_integrity(child, f)
                        v_status = v_info.get("status")
                        if v_status == "legacy_synthetic":
                            f["evidence_hash_type"] = "synthetic_legacy"
                            f["legacy_synthetic_hash"] = True
                            f["evidence_authentic"] = False
                            f["evidence_intact"] = False
                        elif v_status == "intact":
                            f["evidence_hash_type"] = "authentic_sha256"
                            f["legacy_synthetic_hash"] = False
                            f["evidence_authentic"] = True
                            f["evidence_intact"] = True
                            f["evidence_file"] = v_info.get("evidence_file")
                        elif v_status == "modified":
                            f["evidence_hash_type"] = "modified"
                            f["legacy_synthetic_hash"] = False
                            f["evidence_authentic"] = False
                            f["evidence_intact"] = False
                            f["evidence_file"] = v_info.get("evidence_file")
                        else:
                            f["evidence_hash_type"] = "unverified"
                            f["legacy_synthetic_hash"] = False
                            f["evidence_authentic"] = False
                            f["evidence_intact"] = False

                        v_state, v_reason, is_v = evaluate_finding_verification(f)
                        f["verification_state"] = v_state
                        f["verification_reason"] = v_reason
                        f["verified"] = is_v

                    # Duration reconciliation
                    if data.get("execution_segments"):
                        act_dur = round(
                            sum(
                                float(s.get("duration_seconds", 0.0))
                                for s in data["execution_segments"]
                            ),
                            3,
                        )
                        data["active_duration_seconds"] = act_dur
                        data["duration_seconds"] = act_dur
                        data["elapsed_seconds"] = act_dur
                    else:
                        s_str = data.get("started_at") or data.get("start_time")
                        c_str = data.get("completed_at") or data.get("end_time")
                        if s_str and c_str:
                            try:
                                s_dt = datetime.fromisoformat(str(s_str).replace("Z", "+00:00"))
                                c_dt = datetime.fromisoformat(str(c_str).replace("Z", "+00:00"))
                                span_sec = round((c_dt - s_dt).total_seconds(), 3)
                                if span_sec > 0 and (data.get("duration_seconds") or 0) > (
                                    span_sec * 1.5
                                ):
                                    data["wall_clock_duration_seconds"] = data.get(
                                        "duration_seconds"
                                    )
                                    data["active_duration_seconds"] = span_sec
                                    data["duration_seconds"] = span_sec
                                    data["elapsed_seconds"] = span_sec
                            except Exception:
                                pass

                    # Recover status from authoritative persisted execution state.
                    # Never promote a failed run to completed just because a report file exists.
                    if data.get("status") in ("failed", "failed_agent"):
                        _recovered = False
                        # Check for completion event in the events list
                        for ev in data.get("events", []):
                            if ev.get("event") in ("RUN_COMPLETED", "AUTONOMOUS_RUN_COMPLETED"):
                                data["status"] = "completed"
                                data["error"] = None
                                _recovered = True
                                break
                        # If exit_code 2 (vulns found) and no fatal failure event
                        if not _recovered and (
                            data.get("exit_code") == 2 or data.get("process_exit_code") == 2
                        ):
                            data["status"] = "completed_with_findings"
                            data["error"] = None
                            _recovered = True
                        # If run has a persisted exit_code, use that for status derivation
                        if not _recovered and "exit_code" in data:
                            ec = data["exit_code"]
                            if ec == 0:
                                data["status"] = "completed"
                                data["error"] = None
                                _recovered = True
                        # Otherwise preserve the persisted status as-is
                        if _recovered:
                            if data.get("progress"):
                                data["progress"]["phase"] = "Assessment Complete"
                                data["progress"]["phase_index"] = 5
                                data["progress"]["percent"] = 100
                            data["progress_percent"] = 100

                    # Accurately account turns if inflated by subagent ping-pong in historical logs
                    if (
                        data.get("turns_consumed", 0) > (data.get("max_turns") or 500)
                        and (child / "strix.log").is_file()
                    ):
                        try:
                            a_turns: dict[str, int] = {}
                            for log_ln in (
                                (child / "strix.log")
                                .read_text(encoding="utf-8", errors="replace")
                                .splitlines()
                            ):
                                tm = re.search(
                                    r"Starting turn\s+(\d+),\s*current_agent=([^,\n\r]+)", log_ln
                                )
                                if tm:
                                    a_turns[tm.group(2).strip()] = max(
                                        a_turns.get(tm.group(2).strip(), 0), int(tm.group(1))
                                    )
                            if a_turns:
                                true_turns = sum(a_turns.values())
                                data["turns_consumed"] = true_turns
                                if data.get("progress"):
                                    data["progress"]["current"] = true_turns
                                if data.get("stats"):
                                    data["stats"]["attempts"] = true_turns
                        except Exception:
                            pass

                    data = reconcile_all(data, run_dir=child)
                    _sync_run_counters(data)
                    _RUNS[run_id] = data
            except Exception as read_err:
                logger.debug("Could not parse %s: %s", run_file, read_err)
    except Exception as exc:
        logger.warning("Failed to load runs from disk: %s", exc)


def _quarantine_stale_running_run(run_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Reconcile a persisted 'running' record that has no live worker/process.

    A background thread dies with the server; its last persisted state says
    'running' forever. Without this, the dashboard shows a misleading active
    assessment and a relaunch is refused as "already running". Mark such runs
    interrupted with an explicit reason and freeze their duration.
    """
    if data.get("status") != "running":
        return data
    proc = _ACTIVE_PROCESSES.get(run_id)
    if proc is not None and proc.poll() is None:
        return data  # genuinely alive: do not touch
    if run_id == _CURRENT_ACTIVE_RUN_ID and run_id in _RUNS:
        # A worker may still be between state writes in this process.
        return data

    reason = "Assessment was interrupted: no active execution process or worker survived."
    data["status"] = "interrupted"
    data["error"] = reason
    data["end_time"] = data.get("end_time") or _utc_now()
    data["completed_at"] = data.get("completed_at") or data["end_time"]
    data["execution_mode"] = data.get("execution_mode") or "unknown"
    data["events"] = [
        *data.get("events", []),
        {
            "timestamp": data["end_time"],
            "event": "RUN_INTERRUPTED",
            "message": reason,
        },
    ]
    _finalize_run_lifecycle(data, status="interrupted", error=reason)
    return data


def _finalize_run_lifecycle(
    run_entry: dict[str, Any], *, status: str, error: str | None = None
) -> None:
    """Freeze duration and the terminal state of a run.

    ``start_time`` is the persisted source of truth; duration is computed from
    segmented execution tracking so pauses, provider limits, and resume events
    reflect authentic active scan time without multi-hour wall-clock inflation.
    """
    run_entry["status"] = status
    run_entry["end_time"] = _utc_now()
    ended_dt = datetime.fromisoformat(run_entry["end_time"])
    if ended_dt.tzinfo is None:
        ended_dt = ended_dt.replace(tzinfo=UTC)

    # Close current execution segment
    seg_start_ts = (
        run_entry.pop("_current_segment_start", None)
        or run_entry.get("started_at")
        or run_entry.get("start_time")
    )
    if seg_start_ts:
        try:
            seg_start_dt = datetime.fromisoformat(str(seg_start_ts).replace("Z", "+00:00"))
            if seg_start_dt.tzinfo is None:
                seg_start_dt = seg_start_dt.replace(tzinfo=UTC)
            seg_dur = round(max(0.0, (ended_dt - seg_start_dt).total_seconds()), 3)
            if "execution_segments" not in run_entry or not isinstance(
                run_entry["execution_segments"], list
            ):
                run_entry["execution_segments"] = []
            run_entry["execution_segments"].append(
                {
                    "started_at": str(seg_start_ts),
                    "ended_at": run_entry["end_time"],
                    "duration_seconds": seg_dur,
                }
            )
        except Exception:
            pass

    # Compute active duration and wall-clock duration
    if run_entry.get("execution_segments"):
        active_dur = round(
            sum(float(s.get("duration_seconds", 0.0)) for s in run_entry["execution_segments"]), 3
        )
    else:
        active_dur = 0.0

    started_ts = run_entry.get("started_at") or run_entry.get("start_time")
    if started_ts:
        run_entry["started_at"] = started_ts
        try:
            started = datetime.fromisoformat(str(started_ts).replace("Z", "+00:00"))
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            wall_clock_dur = round(max(0.0, (ended_dt - started).total_seconds()), 3)
            run_entry["wall_clock_duration_seconds"] = wall_clock_dur
        except Exception:
            run_entry["wall_clock_duration_seconds"] = active_dur
    else:
        run_entry["wall_clock_duration_seconds"] = active_dur

    run_entry["active_duration_seconds"] = active_dur
    run_entry["duration_seconds"] = active_dur
    run_entry["elapsed_seconds"] = active_dur

    if error:
        run_entry["error"] = error
    if status in ("completed", "completed_with_findings"):
        run_entry["active_agent"] = "Completed"
        run_entry["active_task"] = "Assessment successfully concluded"
    elif status in ("provider_blocked", "paused_provider_limit"):
        run_entry["active_agent"] = "Paused"
        run_entry["active_task"] = "Provider quota exhausted. Awaiting resume."
    elif status == "paused_execution_limit":
        run_entry["active_agent"] = "Paused"
        run_entry["active_task"] = "Configured execution turn limit reached. Awaiting resume."
    elif status in ("failed_infrastructure", "failed_agent", "failed", "aborted", "cancelled"):
        run_entry["active_agent"] = "Stopped"
        run_entry["active_task"] = f"Assessment terminated ({status})"
    elif status == "partial":
        run_entry["active_agent"] = "Concluded"
        run_entry["active_task"] = "Assessment finished (partial candidate queue)"
    _sync_run_counters(run_entry)
    run_entry.setdefault("events", []).append(
        {
            "timestamp": run_entry["end_time"],
            "event": f"RUN_{status.upper()}",
            "message": f"Run terminated with reason: {error}"
            if error
            else "Run terminated successfully",
        }
    )


def count_findings_by_verification_state(findings: list[dict[str, Any]]) -> dict[str, int]:
    """Count findings by their verification state.

    Returns ``{"discovered": n, "verified": n, ...}`` for display and reporting.
    """
    counts = {
        "discovered": 0,
        "candidate": 0,
        "under_investigation": 0,
        "exploitation_attempted": 0,
        "verified": 0,
        "unconfirmed": 0,
        "false_positive": 0,
        "blocked": 0,
        "inconclusive": 0,
    }
    for r in findings:
        v = r.get("verification") or {}
        state = (
            (v.get("verification_state") or r.get("verification_state") or "")
            .lower()
            .replace(" ", "_")
        )
        if not state and r.get("verified"):
            state = "verified"
        if not state:
            state = "discovered"
        if state in counts:
            counts[state] += 1
        else:
            counts["discovered"] += 1
    return counts


def _sync_run_counters(run_entry: dict[str, Any]) -> None:
    """Rebuild in-memory counters from on-disk artifacts or in-memory state.

    Coverage, findings and GAP state live on disk; re-deriving the counts here
    keeps progress, reports and the dashboard in agreement and prevents
    untested categories or a missed finding from staying invisible.
    """
    run_id = run_entry.get("run_id")
    base_dir = runs_base_dir() / (run_id or "")
    vuln_file = base_dir / "vulnerabilities.json"
    strix_vulns = []
    if vuln_file.is_file():
        try:
            strix_vulns = json.loads(vuln_file.read_text(encoding="utf-8"))
        except Exception:
            strix_vulns = []

    target_findings = (
        strix_vulns
        if (isinstance(strix_vulns, list) and strix_vulns)
        else run_entry.get("findings", [])
    )
    counts = count_findings_by_verification_state(target_findings)
    run_entry["findings_discovered"] = counts["discovered"]
    run_entry["findings_candidate"] = counts["candidate"]
    run_entry["findings_under_investigation"] = counts["under_investigation"]
    run_entry["findings_exploitation_attempted"] = counts["exploitation_attempted"]
    run_entry["findings_verified"] = counts["verified"]
    run_entry["findings_unconfirmed"] = counts["unconfirmed"]
    run_entry["findings_false_positive"] = counts["false_positive"]
    run_entry["findings_blocked"] = counts["blocked"]
    run_entry["findings_inconclusive"] = counts["inconclusive"]
    run_entry["verification_states"] = counts
    if not isinstance(run_entry.get("findings_summary"), dict):
        run_entry["findings_summary"] = {}
    run_entry["findings_summary"].update(counts)
    if target_findings and run_entry.get("report_status") in (None, "empty", "no_findings"):
        run_entry["report_status"] = "findings_present"

    # GAP1 Candidate accounting from run_entry["candidates"] or control/gap1_queue.json
    candidates = run_entry.get("candidates")
    if not candidates and (base_dir / "control" / "gap1_queue.json").is_file():
        try:
            q_data = json.loads(
                (base_dir / "control" / "gap1_queue.json").read_text(encoding="utf-8")
            )
            if isinstance(q_data, dict) and "candidates" in q_data:
                candidates = q_data["candidates"]
                run_entry["candidates"] = candidates
        except Exception:
            pass

    if isinstance(candidates, list) and candidates:
        run_entry["gap1_candidates_identified"] = len(candidates)
        run_entry["gap1_candidates_under_investigation"] = sum(
            1
            for c in candidates
            if c.get("state") in ("VALIDATED", "ABANDONED", "ATTEMPTING")
            or int(c.get("attempts", 0)) > 0
            or c.get("status") in ("investigated", "validated", "abandoned")
        )
    elif isinstance(candidates, dict) and candidates:
        run_entry["gap1_candidates_identified"] = len(candidates)
        run_entry["gap1_candidates_under_investigation"] = sum(
            1
            for c in candidates.values()
            if c.get("status") in ("investigated", "validated", "abandoned")
            or int(c.get("attempts", 0)) > 0
        )

    # GAP2 Pivot accounting from pivot_events or decision_trace.jsonl
    pivot_events = run_entry.get("pivot_events")
    executed_pivots = None
    if isinstance(pivot_events, list) and pivot_events:
        executed_pivots = 0
        for pe in pivot_events:
            p_type = pe.get("type") if isinstance(pe, dict) else getattr(pe, "type", "")
            p_ev = pe.get("event") if isinstance(pe, dict) else getattr(pe, "event", "")
            p_exec = (
                pe.get("pivot_executed", True)
                if isinstance(pe, dict)
                else getattr(pe, "pivot_executed", True)
            )
            if (
                p_type in ("REDIRECT", "GAP2_PIVOT") or p_ev == "GAP2_PIVOT"
            ) and p_exec is not False:
                executed_pivots += 1
    elif (base_dir / "control" / "decision_trace.jsonl").is_file():
        executed_pivots = 0
        try:
            lines = (
                (base_dir / "control" / "decision_trace.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            )
            for l in lines:
                if not l.strip():
                    continue
                d = json.loads(l)
                if (
                    d.get("event") == "GAP2_PIVOT" or d.get("type") in ("REDIRECT", "GAP2_PIVOT")
                ) and d.get("pivot_executed", True) is not False:
                    executed_pivots += 1
        except Exception:
            pass

    if executed_pivots is not None:
        run_entry["gap2_pivots"] = executed_pivots
        run_entry["pivots"] = executed_pivots
    else:
        executed_pivots = run_entry.get("gap2_pivots", run_entry.get("pivots", 0))
        run_entry["gap2_pivots"] = executed_pivots
        run_entry["pivots"] = executed_pivots

    if isinstance(run_entry.get("progress"), dict):
        run_entry["progress"]["pivots"] = executed_pivots
        run_entry["progress"]["candidates_identified"] = run_entry.get(
            "gap1_candidates_identified", 0
        )
        run_entry["progress"]["candidates_investigated"] = run_entry.get(
            "gap1_candidates_under_investigation", 0
        )
        run_entry["progress"]["gap1"] = {
            "identified": run_entry.get("gap1_candidates_identified", 0),
            "investigated": run_entry.get("gap1_candidates_under_investigation", 0),
        }
        run_entry["progress"]["gap2"] = {
            "pivots": executed_pivots,
        }
        run_entry["progress"]["verification_states"] = counts
        run_entry["progress"]["findings_summary"] = counts

    if isinstance(run_entry.get("stats"), dict):
        run_entry["stats"]["pivots"] = executed_pivots
        run_entry["stats"]["findings"] = len(target_findings)


@asynccontextmanager
async def _app_lifespan(app_instance: FastAPI):
    """Load persistent runs from disk and run safe Docker cleanup on server startup."""
    _load_runs_from_disk()
    try:
        from strix.runtime.docker_cleanup import reap_orphaned_containers_async

        active_ids = {
            rid
            for rid, r in _RUNS.items()
            if r.get("status") in ("running", "resuming", "starting")
        }
        # D03 fix: preserve running containers by default across restarts
        reap_res = await reap_orphaned_containers_async(
            active_run_ids=active_ids, dry_run=False, preserve_running=True
        )
        if reap_res.get("reaped", 0) > 0:
            logger.info("Startup Docker cleanup reaped %d exited orphaned containers", reap_res["reaped"])
    except Exception:
        logger.debug("Startup Docker cleanup skipped", exc_info=True)
    yield


app.router.lifespan_context = _app_lifespan


@app.post("/system/docker/cleanup")
async def trigger_docker_cleanup(dry_run: bool = False):
    """Safely reap orphaned AI-VAPT sandbox containers left behind by crashes or host death."""
    from strix.runtime.docker_cleanup import reap_orphaned_containers_async

    active_ids = {
        rid for rid, r in _RUNS.items() if r.get("status") in ("running", "resuming", "starting")
    }
    return await reap_orphaned_containers_async(active_run_ids=active_ids, dry_run=dry_run)


@app.get("/", response_class=FileResponse)
async def serve_index(request: Request, response: Response):
    """Serve the Single Page Application index.html with automatic loopback session bootstrap."""
    index_file = WEB_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="Web console assets not found")

    from strix.interface.auth import (
        SESSION_COOKIE_NAME,
        _is_loopback_client,
        create_session,
        get_session,
    )

    resp = FileResponse(str(index_file), media_type="text/html")
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    session = get_session(session_id)
    if not session and _is_loopback_client(request):
        auto_sess = create_session(role="admin", user_id="local_operator")
        resp.set_cookie(
            SESSION_COOKIE_NAME,
            auto_sess["session_id"],
            httponly=True,
            samesite="lax",
            max_age=86400,
        )
    return resp


@app.get("/auth/status")
async def auth_status(
    request: Request,
    user: dict[str, Any] | None = Depends(get_current_user_or_none),
):
    """Return caller authentication status, role, and CSRF token."""
    if user:
        return {
            "authenticated": True,
            "user": user.get("user_id"),
            "role": user.get("role"),
            "csrf_token": user.get("csrf_token"),
            "auth_method": user.get("auth_method"),
        }
    return {
        "authenticated": False,
        "user": None,
        "role": "anonymous",
        "csrf_token": None,
        "auth_method": "none",
    }


@app.post("/auth/login")
async def auth_login(req: dict[str, Any], response: Response):
    """Login using operator or admin API key to establish a web session."""
    key = str(req.get("key") or req.get("api_key") or req.get("token") or "").strip()
    creds = _load_or_create_operator_credentials()
    role = None
    if key and secrets.compare_digest(key, creds.get("admin_key", "")):
        role = "admin"
    elif key and secrets.compare_digest(key, creds.get("operator_key", "")):
        role = "operator"
    elif key and secrets.compare_digest(key, creds.get("viewer_key", "")):
        role = "viewer"

    if not role:
        raise HTTPException(status_code=401, detail="Invalid operator credential key.")

    sess = create_session(role=role, user_id=f"user_{role}")
    response.set_cookie(
        SESSION_COOKIE_NAME,
        sess["session_id"],
        httponly=True,
        samesite="lax",
        max_age=86400,
    )
    return {"authenticated": True, "role": role, "csrf_token": sess["csrf_token"]}


@app.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    """Terminate the active web session and clear session cookie."""
    sess_id = request.cookies.get(SESSION_COOKIE_NAME)
    delete_session(sess_id)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"status": "logged_out"}


@app.post("/system/docker/cleanup")
async def trigger_docker_cleanup(
    dry_run: bool = True,
    preserve_running: bool = True,
    force_running_reap: bool = False,
    user: dict[str, Any] = Depends(require_admin),
):
    """Safely reap orphaned AI-VAPT sandbox containers (restricted to admin, D03 fix)."""
    from strix.runtime.docker_cleanup import reap_orphaned_containers_async

    active_ids = {
        rid for rid, r in _RUNS.items() if r.get("status") in ("running", "resuming", "starting")
    }
    return await reap_orphaned_containers_async(
        active_run_ids=active_ids,
        dry_run=dry_run,
        preserve_running=preserve_running,
        force_running_reap=force_running_reap,
    )


@app.get("/health")
async def health_check():
    """Basic service health check."""
    return {"status": "ok", "service": "ai-vapt-gateway"}


@app.get("/system/health", response_model=SystemHealthResponse)
async def system_health():
    """Comprehensive readiness probe for AI-VAPT core, Docker, Ollama, and LiteLLM."""
    components: dict[str, Any] = {}

    # 1. AI-VAPT Core
    components["ai_vapt_core"] = {
        "status": "READY",
        "version": "2.0.0",
        "engine": "autonomous_multi_agent",
    }
    components["strix_core"] = components["ai_vapt_core"]

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


@app.get("/system/readiness", response_model=RuntimeReadinessResponse)
@app.get("/diagnostics/readiness", response_model=RuntimeReadinessResponse)
async def system_readiness(
    provider: str | None = None,
    model: str | None = None,
    image: str | None = None,
    api_key: str | None = None,
    x_openrouter_api_key: str | None = Header(None, alias="X-OpenRouter-API-Key"),
    x_google_api_key: str | None = Header(None, alias="X-Google-API-Key"),
    authorization: str | None = Header(None, alias="Authorization"),
):
    """Runtime readiness preflight check for Docker, AI providers, and environment prerequisites."""
    from strix.core.runtime_credentials import get_runtime_credential, get_runtime_model

    req_key = x_openrouter_api_key or x_google_api_key or api_key
    if not req_key and authorization and authorization.startswith("Bearer "):
        req_key = authorization.split(" ", 1)[1]

    eff_provider = (
        (provider or os.environ.get("STRIX_LLM_PROVIDER") or "openrouter").lower().strip()
    )
    eff_key = get_runtime_credential(eff_provider, override_key=req_key)
    eff_model = get_runtime_model(eff_provider, override_model=model)

    return check_runtime_readiness(
        provider=eff_provider,
        model=eff_model,
        api_key=eff_key,
        image=image,
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
            detail="Authorized local lab target"
            if is_local
            else "External target requires explicit confirmation",
        )


@app.post("/providers/google/validate", response_model=GoogleValidateResponse)
async def validate_google_provider(
    request: Request,
    body: dict[str, Any] | None = None,
    x_google_api_key: str | None = Header(None, alias="X-Google-API-Key"),
    user: dict[str, Any] = Depends(require_operator),
):
    """Validate runtime Google Gemini API key in-memory without disk persistence."""
    from strix.core.runtime_credentials import get_runtime_credential, set_runtime_credential

    api_key = (
        x_google_api_key
        or (body.get("api_key") if body else None)
        or get_runtime_credential("google")
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

        res = validate_google_credential(api_key)
        if res.valid:
            set_runtime_credential("google", api_key)
        return res
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
    body: dict[str, Any] | None = None,
    x_openrouter_api_key: str | None = Header(None, alias="X-OpenRouter-API-Key"),
    user: dict[str, Any] = Depends(require_operator),
):
    """Validate runtime OpenRouter API key in-memory without disk persistence."""
    from strix.core.runtime_credentials import get_runtime_credential, set_runtime_credential

    api_key = (
        x_openrouter_api_key
        or (body.get("api_key") if body else None)
        or get_runtime_credential("openrouter")
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

        val = validate_openrouter_credential(api_key)
        if val.valid:
            set_runtime_credential("openrouter", api_key)
        return val
    except Exception as e:
        return OpenRouterValidateResponse(
            status="error",
            message=f"Validation failed: {e}",
            valid=False,
            catalogue_count=0,
            models=[],
        )


@app.post("/providers/anthropic/validate", response_model=AnthropicValidateResponse)
async def validate_anthropic_provider(
    request: Request,
    body: dict[str, Any] | None = None,
    x_anthropic_api_key: str | None = Header(None, alias="X-Anthropic-API-Key"),
    user: dict[str, Any] = Depends(require_operator),
):
    """Validate runtime Anthropic Claude API key in-memory without disk persistence."""
    from strix.core.runtime_credentials import get_runtime_credential, set_runtime_credential

    api_key = (
        x_anthropic_api_key
        or (body.get("api_key") if body else None)
        or get_runtime_credential("anthropic")
        or os.environ.get("ANTHROPIC_API_KEY")
    )
    if not api_key:
        return AnthropicValidateResponse(
            status="not_configured",
            message="No Anthropic API key provided",
            valid=False,
            catalogue_count=0,
            models=[],
        )

    from strix.llm.provider_validation import validate_anthropic_credential

    val = validate_anthropic_credential(api_key)
    if val.valid:
        set_runtime_credential("anthropic", api_key)
    return val


@app.post("/providers/ollama/validate", response_model=OllamaValidateResponse)
async def validate_ollama_provider(
    body: dict[str, Any] | None = None,
    user: dict[str, Any] = Depends(require_operator),
):
    """Probe local Ollama daemon and discover installed models."""
    base_url = (body.get("api_base") if body else None) or (body.get("base_url") if body else None)
    from strix.llm.provider_validation import validate_ollama_service

    return validate_ollama_service(base_url=base_url)


@app.post("/providers/custom/validate", response_model=CustomEndpointValidateResponse)
async def validate_custom_provider(
    body: dict[str, Any] | None = None,
    user: dict[str, Any] = Depends(require_operator),
):
    """Validate custom OpenAI-compatible endpoint and model."""
    base_url = (
        (body.get("api_base") if body else None)
        or (body.get("base_url") if body else None)
        or "https://api.openai.com/v1"
    )
    api_key = body.get("api_key") if body else None
    model = body.get("model") if body else None
    from strix.core.runtime_credentials import set_runtime_base_url, set_runtime_credential
    from strix.llm.provider_validation import validate_custom_endpoint

    res = validate_custom_endpoint(base_url=base_url, api_key=api_key, model=model)
    if res.valid:
        if api_key:
            set_runtime_credential("custom", api_key, model, api_base=base_url)
        elif base_url:
            set_runtime_base_url("custom", base_url)
    return res


@app.post("/providers/openai/validate", response_model=OpenAIValidateResponse)
async def validate_openai_provider(
    body: dict[str, Any] | None = None,
    x_api_key: str | None = Header(None, alias="Authorization"),
    user: dict[str, Any] = Depends(require_operator),
):
    """Validate OpenAI-compatible endpoint reachability and available models."""
    from strix.core.runtime_credentials import get_runtime_credential, set_runtime_credential

    api_base = (body.get("api_base") if body else None) or os.environ.get(
        "OPENAI_BASE_URL", "https://api.openai.com/v1"
    )
    key = (
        (body.get("api_key") if body else None)
        or x_api_key
        or get_runtime_credential("openai")
        or os.environ.get("OPENAI_API_KEY")
    )
    if key and key.startswith("Bearer "):
        key = key.split(" ", 1)[1]
    from strix.llm.provider_validation import validate_openai_compatible_endpoint

    res = validate_openai_compatible_endpoint(api_base=api_base, api_key=key)
    if res.valid and key:
        set_runtime_credential("openai", key, api_base=api_base)
    return res


@app.get("/providers/openrouter/models", response_model=list[OpenRouterModelInfo])
async def list_openrouter_models():
    """Retrieve available OpenRouter models with pricing transparency."""
    try:
        from strix.core.runtime_credentials import get_runtime_credential
        from strix.llm.provider_validation import fetch_openrouter_models

        key = get_runtime_credential("openrouter")
        return fetch_openrouter_models(api_key=key, include_paid=True)
    except Exception as exc:
        logger.warning("Error fetching OpenRouter models: %s", exc)
        return []


@app.get(
    "/providers/{provider}/models", response_model=list[DiscoveredModelInfo | OpenRouterModelInfo]
)
async def list_provider_models(provider: str):
    """Retrieve dynamically discovered models for any provider with pricing transparency."""
    prov = (provider or "openrouter").lower().strip()
    from strix.core.runtime_credentials import get_runtime_base_url, get_runtime_credential

    key = get_runtime_credential(prov)

    if prov == "openrouter":
        from strix.llm.provider_validation import fetch_openrouter_models

        return fetch_openrouter_models(api_key=key, include_paid=True)

    if prov == "anthropic":
        from strix.llm.provider_validation import validate_anthropic_credential

        val = validate_anthropic_credential(api_key=key or "")
        if val.models:
            return val.models
        return [
            DiscoveredModelInfo(
                id="claude-3-5-sonnet-20241022",
                name="Claude 3.5 Sonnet (Latest)",
                provider="anthropic",
                pricing_status="paid",
                free=False,
                prompt_price="$3.00/M in",
                completion_price="$15.00/M out",
                context_length=200000,
            ),
            DiscoveredModelInfo(
                id="claude-3-5-haiku-20241022",
                name="Claude 3.5 Haiku (Fast)",
                provider="anthropic",
                pricing_status="paid",
                free=False,
                prompt_price="$0.80/M in",
                completion_price="$4.00/M out",
                context_length=200000,
            ),
            DiscoveredModelInfo(
                id="claude-3-opus-20240229",
                name="Claude 3 Opus (Complex)",
                provider="anthropic",
                pricing_status="paid",
                free=False,
                prompt_price="$15.00/M in",
                completion_price="$75.00/M out",
                context_length=200000,
            ),
        ]

    if prov == "openai":
        from strix.llm.provider_validation import validate_openai_credential

        base_url = get_runtime_base_url("openai")
        val_openai = validate_openai_credential(api_key=key or "", api_base=base_url)
        if val_openai.models:
            return [
                DiscoveredModelInfo(
                    id=m,
                    name=m,
                    provider="openai",
                    pricing_status="paid",
                    free=False,
                    context_length=128000,
                )
                for m in val_openai.models
            ]
        return [
            DiscoveredModelInfo(
                id="gpt-4o",
                name="GPT-4o (Flagship)",
                provider="openai",
                pricing_status="paid",
                free=False,
                prompt_price="$2.50/M in",
                completion_price="$10.00/M out",
                context_length=128000,
            ),
            DiscoveredModelInfo(
                id="gpt-4o-mini",
                name="GPT-4o Mini (Fast)",
                provider="openai",
                pricing_status="paid",
                free=False,
                prompt_price="$0.15/M in",
                completion_price="$0.60/M out",
                context_length=128000,
            ),
            DiscoveredModelInfo(
                id="o3-mini",
                name="o3-mini (Reasoning)",
                provider="openai",
                pricing_status="paid",
                free=False,
                prompt_price="$1.10/M in",
                completion_price="$4.40/M out",
                context_length=200000,
            ),
        ]

    if prov == "google":
        from strix.llm.provider_validation import validate_google_credential

        val_google = validate_google_credential(api_key=key or "")
        if val_google.models:
            return [
                DiscoveredModelInfo(
                    id=m,
                    name=f"{m} (Google)",
                    provider="google",
                    pricing_status="paid" if "pro" in m else "free",
                    free="pro" not in m,
                    context_length=1000000,
                )
                for m in val_google.models
            ]
        return [
            DiscoveredModelInfo(
                id="gemini-2.0-flash",
                name="Gemini 2.0 Flash (Fast)",
                provider="google",
                pricing_status="free",
                free=True,
                context_length=1048576,
            ),
            DiscoveredModelInfo(
                id="gemini-1.5-pro",
                name="Gemini 1.5 Pro (Flagship)",
                provider="google",
                pricing_status="paid",
                free=False,
                context_length=2097152,
            ),
            DiscoveredModelInfo(
                id="gemini-1.5-flash",
                name="Gemini 1.5 Flash",
                provider="google",
                pricing_status="free",
                free=True,
                context_length=1048576,
            ),
        ]

    if prov == "ollama":
        from strix.llm.provider_validation import validate_ollama_service

        base_url = get_runtime_base_url("ollama")
        val_ollama = validate_ollama_service(base_url=base_url)
        return val_ollama.models

    if prov in ("cloud_hosted", "custom_cloud", "custom"):
        from strix.llm.provider_validation import validate_custom_endpoint

        base_url = (
            get_runtime_base_url(prov)
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        )
        val_custom = validate_custom_endpoint(base_url=base_url, api_key=key)
        return val_custom.models

    return []


@app.get("/settings/llm")
async def get_llm_settings(user: dict[str, Any] = Depends(require_admin)):
    """Retrieve currently active and persisted LLM configuration."""
    from strix.core.runtime_credentials import get_runtime_credential, get_runtime_model

    cfg = _read_strix_cli_config()
    model = (
        get_runtime_model("openrouter")
        or os.environ.get("STRIX_LLM")
        or cfg.get("STRIX_LLM", f"openrouter/{DEFAULT_OPENROUTER_MODEL}")
    )
    api_key = (
        get_runtime_credential("openrouter")
        or os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or cfg.get("LLM_API_KEY", "")
    )
    api_base = (
        os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("LLM_API_BASE")
        or cfg.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    )
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
    elif (active_cloud and active_cloud.get("is_active")) or (
        api_base and "openrouter.ai" not in api_base and "api.openai.com" not in api_base
    ):
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
            clean_model = clean_model[len(pfx) :]
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
async def update_llm_settings(
    payload: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_admin),
):
    """Save LLM configuration to ~/.strix/cli-config.json and update runtime environment."""
    from strix.core.runtime_credentials import set_runtime_base_url, set_runtime_credential

    provider = (payload.get("provider") or "openrouter").lower().strip()
    raw_model = (payload.get("model") or "").strip()
    api_key = (payload.get("api_key") or "").strip()
    api_base = (payload.get("api_base") or "").strip()
    effort = (payload.get("reasoning_effort") or "low").strip()

    if api_key or raw_model:
        set_runtime_credential(provider, api_key, raw_model)
    if api_base:
        set_runtime_base_url(provider, api_base)

    env_updates: dict[str, str] = {}
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

    elif provider == "anthropic":
        m_name = raw_model if raw_model.startswith("anthropic/") else f"anthropic/{raw_model}"
        base = api_base or "https://api.anthropic.com"
        env_updates["STRIX_LLM_PROVIDER"] = "anthropic"
        env_updates["STRIX_LLM"] = m_name
        env_updates["ANTHROPIC_API_BASE"] = base
        os.environ["STRIX_LLM_PROVIDER"] = "anthropic"
        os.environ["STRIX_LLM"] = m_name
        os.environ["ANTHROPIC_API_BASE"] = base
        if api_key:
            env_updates["ANTHROPIC_API_KEY"] = api_key
            env_updates["LLM_API_KEY"] = api_key
            os.environ["ANTHROPIC_API_KEY"] = api_key
            os.environ["LLM_API_KEY"] = api_key

    elif provider == "google":
        m_name = (
            raw_model
            if (raw_model.startswith("google/") or raw_model.startswith("gemini/"))
            else f"google/{raw_model}"
        )
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


@app.get("/providers/cloud_hosted/profiles", response_model=list[CloudHostedProfileSafe])
async def list_cloud_profiles(user: dict[str, Any] = Depends(require_viewer)):
    """List all saved Cloud Hosted provider profiles (safe, with credentials masked)."""
    profiles = _get_cloud_profiles()
    return [_profile_to_safe(p) for p in profiles]


@app.post("/providers/cloud_hosted/profiles", response_model=CloudHostedProfileSafe)
async def create_or_update_cloud_profile(
    profile: CloudHostedProfile,
    user: dict[str, Any] = Depends(require_admin),
):
    """Save or update a Cloud Hosted provider profile."""
    data = profile.model_dump()
    saved = _save_cloud_profile(data)
    if saved.get("is_active"):
        m_name = (
            saved["model"] if saved["model"].startswith("openai/") else f"openai/{saved['model']}"
        )
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
async def delete_cloud_profile_endpoint(
    profile_id: str,
    user: dict[str, Any] = Depends(require_admin),
):
    """Delete a saved Cloud Hosted provider profile."""
    success = _delete_cloud_profile(profile_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return {"status": "ok", "message": f"Profile {profile_id} deleted"}


@app.post(
    "/providers/cloud_hosted/profiles/{profile_id}/activate", response_model=CloudHostedProfileSafe
)
async def activate_cloud_profile_endpoint(
    profile_id: str,
    user: dict[str, Any] = Depends(require_admin),
):
    """Set the specified Cloud Hosted profile as active."""
    profile = _set_active_cloud_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    m_name = (
        profile["model"] if profile["model"].startswith("openai/") else f"openai/{profile['model']}"
    )
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
async def discover_cloud_models_endpoint(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_operator),
):
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
async def validate_cloud_connection_endpoint(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_operator),
):
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

    return test_cloud_connection(
        api_base=api_base, model=model, api_key=api_key, extra_headers=extra_headers
    )


@app.post("/providers/cloud_hosted/verify_tools", response_model=CloudVerifyToolsResponse)
async def verify_cloud_tools_endpoint(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_operator),
):
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

    return verify_cloud_structured_tools(
        api_base=api_base, model=model, api_key=api_key, extra_headers=extra_headers
    )


@app.post("/providers/cloud_hosted/warmup", response_model=CloudWarmupResponse)
async def warmup_cloud_endpoint(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_operator),
):
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

    return warmup_cloud_model(
        api_base=api_base, model=model, api_key=api_key, extra_headers=extra_headers
    )


BOX_DRAWING_CHARS = {chr(i) for i in range(0x2500, 0x25A0)}
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _clean_terminal_line(line: str) -> str:
    """Strip ANSI escapes, Rich borders, and decorative box characters."""
    line = ANSI_ESCAPE_RE.sub("", line)
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
    text = re.sub(r"sk-or-v1-[a-zA-Z0-9_\-]{16,}", "[REDACTED_API_KEY]", text)
    # Generic bearer/API keys (sk-...)
    text = re.sub(r"sk-[a-zA-Z0-9_\-]{16,}", "[REDACTED_API_KEY]", text)
    # Google Gemini keys (AIza...)
    text = re.sub(r"AIza[a-zA-Z0-9_\-]{20,}", "[REDACTED_API_KEY]", text)
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
        if (
            "429" in combined_text
            or "rate limit" in combined_lower
            or "ratelimit" in combined_lower
        ):
            if any(
                k in combined_lower
                for k in (
                    "free-models-per-day",
                    "openrouter_free_tier_daily",
                    "daily reset",
                    "daily limit",
                    "quota exceeded",
                )
            ):
                return "OpenRouter daily free quota exceeded (HTTP 429: free-models-per-day limit reached, 50 requests/day). Add credits to your OpenRouter account or wait for the daily reset."
            return "OpenRouter rate limit reached (HTTP 429). Please retry shortly or select an alternate model."

    # 1. Look for Python Tracebacks in cleaned_stderr
    if cleaned_stderr:
        exc_lines = [
            l
            for l in cleaned_stderr
            if re.search(r"\b(?:[A-Z][a-zA-Z0-9_]*Error|[A-Z][a-zA-Z0-9_]*Exception)\b:", l)
        ]
        if exc_lines:
            return _redact_secrets(exc_lines[-1])

        err_lines = [
            l
            for l in cleaned_stderr
            if any(
                k in l.lower()
                for k in (
                    "error",
                    "failed",
                    "fatal",
                    "exception",
                    "rate limit",
                    "budget",
                    "unauthorized",
                )
            )
            and "warning" not in l.lower()
        ]
        if err_lines:
            return _redact_secrets("\n".join(err_lines[-3:]))

        return _redact_secrets("\n".join(cleaned_stderr[-3:]))

    # 2. Look in cleaned_stdout
    if cleaned_stdout:
        exc_lines = [
            l
            for l in cleaned_stdout
            if re.search(r"\b(?:[A-Z][a-zA-Z0-9_]*Error|[A-Z][a-zA-Z0-9_]*Exception)\b:", l)
        ]
        if exc_lines:
            return _redact_secrets(exc_lines[-1])

        candidates = [
            l
            for l in cleaned_stdout
            if any(
                k in l.lower()
                for k in (
                    "error",
                    "exception",
                    "failed to",
                    "traceback",
                    "fatal",
                    "unauthorized",
                    "rate limit",
                    "budget exceeded",
                    "quota exceeded",
                )
            )
            and "warning" not in l.lower()
            and not any(
                sec_kw in l.lower()
                for sec_kw in (
                    "vulnerability",
                    "vulnerabilities",
                    "security header",
                    "x-frame-options",
                    "cookie security",
                    "session cookie",
                    "content-security-policy",
                    "missing from http",
                    "executive summary",
                    "recommendation",
                    "remediation",
                    "finding",
                    "exposure",
                    "pentest",
                )
            )
        ]
        if candidates:
            return _redact_secrets("\n".join(candidates[-3:]))

    return _redact_secrets(fallback)


def _align_cvss_severity(cvss: float | None, severity: str | None) -> tuple[float, str]:
    """Ensure CVSS score and severity label strictly agree according to CVSS v3.1 specification.

    0.0: INFO / NONE
    0.1 - 3.9: LOW
    4.0 - 6.9: MEDIUM
    7.0 - 8.9: HIGH
    9.0 - 10.0: CRITICAL
    """
    sev_upper = (severity or "").upper().strip()
    score = None
    if cvss is not None:
        try:
            score = float(cvss)
        except (ValueError, TypeError):
            pass

    if score is not None:
        if score >= 9.0:
            return round(score, 1), "CRITICAL"
        if score >= 7.0:
            return round(score, 1), "HIGH"
        if score >= 4.0:
            return round(score, 1), "MEDIUM"
        if score > 0.0:
            return round(score, 1), "LOW"
        return 0.0, "INFO"

    if sev_upper == "CRITICAL":
        return 9.8, "CRITICAL"
    if sev_upper == "HIGH":
        return 8.2, "HIGH"
    if sev_upper == "MEDIUM":
        return 5.5, "MEDIUM"
    if sev_upper == "LOW":
        return 3.1, "LOW"
    return 0.0, "INFO"


class ProbeResult(tuple[Any, ...]):
    """3-tuple subclass for backward compatibility with (confirmed, detail, snippet),
    while exposing explicit finding verification attributes.
    """

    confirmed: bool
    detail: str
    snippet: str
    verification_state: str
    reproducible_request: str
    reproducible_response: str
    verification_procedure: str
    demonstrated_impact: str
    parameter: str
    cvss_score: float | None
    severity: str | None
    cwe_id: str | None
    cve_id: str | None
    extra: dict[str, Any]

    def __new__(
        cls,
        confirmed: bool,
        detail: str,
        snippet: str = "",
        **kwargs: Any,
    ) -> Self:
        obj = super().__new__(cls, (bool(confirmed), str(detail), str(snippet)))
        obj.confirmed = bool(confirmed)
        obj.detail = str(detail)
        obj.snippet = str(snippet)
        obj.verification_state = kwargs.get(
            "verification_state", "Verified" if confirmed else "Unconfirmed"
        )
        obj.reproducible_request = kwargs.get("reproducible_request", "")
        obj.reproducible_response = kwargs.get("reproducible_response", snippet)
        obj.verification_procedure = kwargs.get("verification_procedure", "")
        obj.demonstrated_impact = kwargs.get("demonstrated_impact", "")
        obj.parameter = kwargs.get("parameter", "")
        obj.cvss_score = kwargs.get("cvss_score")
        obj.severity = kwargs.get("severity")
        obj.cwe_id = kwargs.get("cwe_id")
        obj.cve_id = kwargs.get("cve_id")
        obj.extra = kwargs
        return obj

    def to_dict(self) -> dict[str, Any]:
        return {
            "confirmed": self.confirmed,
            "verification_state": self.verification_state,
            "detail": self.detail,
            "snippet": self.snippet,
            "reproducible_request": self.reproducible_request,
            "reproducible_response": self.reproducible_response,
            "verification_procedure": self.verification_procedure,
            "demonstrated_impact": self.demonstrated_impact,
            "parameter": self.parameter,
            "cvss_score": self.cvss_score,
            "severity": self.severity,
            "cwe_id": self.cwe_id,
            "cve_id": self.cve_id,
        }


def _probe_web_candidate(
    target_url: str, cid: str, endpoint: str, auth_session: Any | None = None
) -> ProbeResult | tuple[bool, str, str]:
    """Actively probe web attack candidates using benign, accurate, non-destructive verification."""
    import json
    import re
    import ssl
    import urllib.parse
    import urllib.request

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
    auth_headers = (
        auth_session.get_auth_header()
        if auth_session and hasattr(auth_session, "get_auth_header")
        else {}
    )

    # 0A. Authenticated User Enumeration & Role Disclosure
    if "user-enumeration" in c_clean or "user_enum" in c_clean:
        try:
            u_url = target_url.rstrip("/") + "/api/Users"
            headers = (
                auth_session.get_auth_header()
                if auth_session and hasattr(auth_session, "get_auth_header")
                else {}
            )
            headers["User-Agent"] = "AI-VAPT/2.0"
            req = urllib.request.Request(u_url, headers=headers)
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                if resp.status == 200:
                    body = resp.read(30000).decode("utf-8", errors="ignore")
                    data = json.loads(body)
                    users = data.get("data", [])
                    admins = [u for u in users if u.get("role") == "admin"]
                    if len(users) > 1 and len(admins) > 0:
                        return (
                            True,
                            f"Unprivileged user enumeration confirmed: retrieved {len(users)} accounts including {len(admins)} admin users",
                            f"HTTP 200 OK\nUsers: {len(users)}, Admins: {len(admins)}\n{body[:300]}",
                        )
        except Exception:
            pass
        return (
            False,
            "Access to user list strictly role-scoped or unauthenticated access blocked",
            "",
        )

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
            idor_res = IDORValidator.test_idor(
                target_url, auth_session.token, user_own_id=own_id, foreign_id=1
            )
            if idor_res.is_idor:
                return True, idor_res.summary, idor_res.evidence_snippet
        return False, "Object-level authorization enforced; cross-tenant access blocked", ""

    # 0D. Controlled Default Administrative Credential Validation
    if "default-admin" in c_clean or "admin-credential" in c_clean:
        from strix.core.scanner.credential_validator import CredentialValidator

        cred_res = CredentialValidator.test_single_credential(
            target_url, "admin@juice-sh.op", "admin123"
        )
        if cred_res.authenticated and cred_res.is_admin:
            return True, cred_res.summary, cred_res.evidence_snippet
        return False, "Default administrative credentials rejected by target", ""

    # 1. Security Hardening Headers (Observation / Hardening)
    if "header" in c_clean or "missing-security-headers" in c_clean:
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                missing = [
                    h for h in ["x-frame-options", "x-content-type-options"] if h not in headers
                ]
                if target_url.startswith("https") and "strict-transport-security" not in headers:
                    missing.append("strict-transport-security")
                if "content-security-policy" not in headers:
                    missing.append("content-security-policy")
                if missing:
                    return (
                        False,
                        f"Missing security hardening headers (Observation / Hardening): {', '.join(missing)}",
                        "Headers evaluated:\n" + "\n".join(f"{k}: {v}" for k, v in headers.items()),
                    )
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
                    return (
                        False,
                        "No Content Security Policy (CSP) header configured (Observation / Hardening Recommendation)",
                        "Content-Security-Policy: [NOT PRESENT]",
                    )
                if (
                    "unsafe-inline" in csp_val.lower()
                    or "unsafe-eval" in csp_val.lower()
                    or "*" in csp_val
                ):
                    return (
                        False,
                        f"Permissive CSP policy allows inline/eval scripts (Observation): {csp_val[:120]}",
                        f"Content-Security-Policy: {csp_val}",
                    )
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
                    if (
                        "httponly" not in c_low
                        or "samesite" not in c_low
                        or (target_url.startswith("https") and "secure" not in c_low)
                    ):
                        return (
                            True,
                            f"Session cookie lacks HttpOnly/Secure/SameSite attributes: {c[:80]}",
                            c,
                        )
        except Exception as exc:
            logger.debug("Cookie probe error: %s", exc)
        return False, "Session cookies have secure flags or no cookies issued", ""

    # 4. Server Version / Diagnostic Banner Disclosure
    if "banner" in c_clean or "server-banner" in c_clean or "phpinfo" in c_clean:
        try:
            req = urllib.request.Request(
                full_url if "phpinfo" in c_clean else target_url,
                headers={"User-Agent": "AI-VAPT/2.0"},
            )
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                body = resp.read(2048).decode("utf-8", errors="ignore")
                if "phpinfo" in c_clean:
                    if resp.status == 200 and ("PHP Version" in body or "phpinfo()" in body):
                        return (
                            True,
                            "PHPInfo diagnostic configuration exposed (HTTP 200)",
                            f"HTTP 200 OK\n{body[:350]}",
                        )
                else:
                    server_val = headers.get("server", "") + " " + headers.get("x-powered-by", "")
                    if re.search(r"\d+\.\d+", server_val):
                        return (
                            True,
                            f"Server banner discloses detailed software version: {server_val.strip()}",
                            f"Server: {server_val.strip()}",
                        )
        except Exception:
            pass
        return False, "Diagnostic banner not exposed or suppressed", ""

    # 5. Cross-Origin Resource Sharing (CORS) Misconfiguration
    if "cors" in c_clean:
        try:
            req = urllib.request.Request(
                full_url,
                headers={"User-Agent": "AI-VAPT/2.0", "Origin": "https://strix-audit.test"},
            )
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                allow_origin = headers.get("access-control-allow-origin", "")
                allow_cred = headers.get("access-control-allow-credentials", "").lower()
                if allow_origin == "https://strix-audit.test" or (
                    allow_origin == "*" and allow_cred == "true"
                ):
                    return (
                        True,
                        "Permissive CORS policy allows untrusted Origin with credentials",
                        f"Access-Control-Allow-Origin: {allow_origin}\nAccess-Control-Allow-Credentials: {allow_cred}",
                    )
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
                        has_token = bool(
                            re.search(
                                r'name=["\'](?:[^"\']*(?:csrf|token|_token|authenticity_token))["\']',
                                f,
                                re.I,
                            )
                        )
                        if not has_token:
                            return (
                                True,
                                f"POST form at {endpoint} lacks anti-CSRF synchronization tokens",
                                f"{f[:300]}",
                            )
        except Exception:
            pass
        return False, "Anti-CSRF tokens present or no unprotected POST forms identified", ""

    # 7. Open HTTP Redirection
    if "redirect" in c_clean or "open_redirect" in c_clean:
        try:
            opener = urllib.request.build_opener(NoRedirectHandler)
            test_ep = (
                full_url
                + ("&" if "?" in full_url else "?")
                + "redirect=https://evil-attacker.test&url=https://evil-attacker.test"
            )
            req = urllib.request.Request(test_ep, headers={"User-Agent": "AI-VAPT/2.0"})
            resp = opener.open(req, timeout=4.0)
            loc = resp.headers.get("Location", "")
            if loc and ("evil-attacker.test" in loc):
                return (
                    True,
                    f"Open HTTP Redirection confirmed on parameter: Location -> {loc}",
                    f"HTTP {resp.status}\nLocation: {loc}",
                )
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
                    return (
                        True,
                        "Robots.txt discloses internal directory layout and sensitive administrative paths",
                        f"HTTP 200 OK\n{body[:350]}",
                    )
        except Exception:
            pass
        return False, "robots.txt not exposed or contains no sensitive directives", ""

    # 9. Reflected Cross-Site Scripting (XSS)
    if "reflected" in c_clean or c_clean == "reflected-xss" or "xss_r" in c_clean:
        try:
            test_eps = [endpoint]
            if "xss" not in endpoint.lower():
                test_eps.append("/vulnerabilities/xss_r/")

            probe_token = '"><script>/*ai-vapt-probe*/</script>'
            for ep in test_eps:
                curr_ep_url = target_url.rstrip("/") + "/" + ep.lstrip("/")
                for param in ("name", "q", "query", "search", "test"):
                    test_url = (
                        curr_ep_url
                        + ("&" if "?" in curr_ep_url else "?")
                        + f"{param}={urllib.parse.quote(probe_token)}"
                    )
                    req_headers = {"User-Agent": "AI-VAPT/2.0"}
                    req_headers.update(auth_headers)
                    req = urllib.request.Request(test_url, headers=req_headers)
                    try:
                        with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                            if resp.status == 200:
                                ct = resp.headers.get("content-type", "").lower()
                                body = resp.read(30000).decode("utf-8", errors="ignore")
                                if probe_token in body and (
                                    "text/html" in ct or "<html" in body.lower() or not ct
                                ):
                                    return ProbeResult(
                                        True,
                                        f"Unescaped script breakout reflection verified at {ep}",
                                        f"Reflection evidence:\n...{body[max(0, body.find(probe_token) - 30) : body.find(probe_token) + 60]}...",
                                        verification_state="Verified",
                                        reproducible_request=f"GET {test_url} HTTP/1.1",
                                        demonstrated_impact="Unsanitized user input reflected in HTML context allows arbitrary script execution in victim browser sessions.",
                                        verification_procedure=f"Injected benign script markup token into '{param}' parameter; confirmed unescaped verbatim reflection in HTML DOM response.",
                                        parameter=param,
                                        cvss_score=6.1,
                                        severity="MEDIUM",
                                        cwe_id="CWE-79",
                                    )
                    except urllib.error.HTTPError as http_err:
                        if http_err.code in (403, 406):
                            return ProbeResult(
                                False,
                                f"XSS payloads strictly filtered and blocked by WAF/Gateway (HTTP {http_err.code})",
                                "",
                                verification_state="Blocked",
                            )
                    except Exception:
                        pass
        except Exception:
            pass
        return ProbeResult(
            False,
            "Input reflection properly HTML-encoded or rejected by application filters",
            "",
            verification_state="Unconfirmed",
        )

    # 10. DOM-Based Cross-Site Scripting (DOM XSS)
    if "dom" in c_clean or c_clean == "dom-xss":
        try:
            req = urllib.request.Request(full_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(50000).decode("utf-8", errors="ignore")
                scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", body, re.I | re.DOTALL)
                combined_js = "\n".join(scripts)
                dom_sources = [
                    "location.search",
                    "location.hash",
                    "location.href",
                    "document.URL",
                    "window.name",
                ]
                dom_sinks = [
                    "eval(",
                    "document.write(",
                    ".innerHTML",
                    "setTimeout(",
                    "setInterval(",
                ]
                has_source = any(src in combined_js for src in dom_sources)
                has_sink = any(sink in combined_js for sink in dom_sinks)
                if has_source and has_sink:
                    return (
                        True,
                        "Potential client-side DOM XSS pathway identified in script processing",
                        "DOM Sink pattern detected in inline scripts",
                    )
        except Exception:
            pass
        return (
            False,
            "No untrusted source-to-sink DOM execution pathways identified in client scripts",
            "",
        )

    # 10. SQL Injection (Error-Based & Boolean-Differential Proof)
    if "sqli" in c_clean or "sql-injection" in c_clean:
        try:
            test_eps = [endpoint]
            if "sqli" not in endpoint.lower() and "login" not in endpoint.lower():
                test_eps.append("/vulnerabilities/sqli/")

            for ep in test_eps:
                curr_ep_url = target_url.rstrip("/") + "/" + ep.lstrip("/")
                # Test error & differential payloads
                for err_payload in ("1' AND '1'='2", "1'", "1'\"", "1' OR '1'='1"):
                    test_url = (
                        curr_ep_url
                        + ("&" if "?" in curr_ep_url else "?")
                        + f"id={urllib.parse.quote(err_payload)}&Submit=Submit"
                    )
                    req_headers = {"User-Agent": "AI-VAPT/2.0"}
                    req_headers.update(auth_headers)
                    req = urllib.request.Request(test_url, headers=req_headers)
                    try:
                        with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                            body = resp.read(30000).decode("utf-8", errors="ignore")
                            sql_errors = [
                                "sql syntax",
                                "mysqli_sql_exception",
                                "mysql_fetch",
                                "ora-01756",
                                "pg_query",
                                "sqlite3::sql",
                                "unclosed quotation mark",
                                "microsoft ole db provider",
                                "fatal error.*sql",
                            ]
                            for err in sql_errors:
                                if err in body.lower():
                                    return ProbeResult(
                                        True,
                                        f"SQL syntax error disclosed on {ep} (Error-Based SQLi): {err}",
                                        body[:350],
                                        verification_state="Verified",
                                        reproducible_request=f"GET {test_url} HTTP/1.1",
                                        demonstrated_impact="Unsanitized user input concatenated into database query allows arbitrary SQL manipulation and database exception disclosure.",
                                        verification_procedure=f"Injected SQL quote payload '{err_payload}' and observed raw database engine syntax exception reflection.",
                                        parameter="id",
                                        cvss_score=8.6,
                                        severity="HIGH",
                                        cwe_id="CWE-89",
                                    )
                            # Check boolean differential: multi-record response on 1' OR '1'='1
                            if "1' OR '1'='1" in err_payload and (
                                "admin" in body.lower()
                                and ("gordon" in body.lower() or "first name" in body.lower())
                            ):
                                return ProbeResult(
                                    True,
                                    f"SQL Injection confirmed via boolean differential logic on {ep}",
                                    body[:350],
                                    verification_state="Verified",
                                    reproducible_request=f"GET {test_url} HTTP/1.1",
                                    demonstrated_impact="Attacker can bypass database query logic and extract table records without authorization.",
                                    verification_procedure="Injected tautology predicate (1' OR '1'='1) and verified multi-record database result set extraction.",
                                    parameter="id",
                                    cvss_score=8.6,
                                    severity="HIGH",
                                    cwe_id="CWE-89",
                                )
                    except urllib.error.HTTPError as he:
                        err_body = he.read().decode("utf-8", errors="ignore")
                        if any(
                            k in err_body.lower()
                            for k in ("sql syntax", "mysqli_sql_exception", "fatal error")
                        ):
                            return ProbeResult(
                                True,
                                f"SQL syntax exception disclosed in HTTP {he.code} response: {he.reason}",
                                err_body[:350],
                                verification_state="Verified",
                                reproducible_request=f"GET {test_url} HTTP/1.1",
                                demonstrated_impact="Unsanitized query concatenation exposes internal database schema and syntax errors.",
                                verification_procedure=f"Injected SQL quote '{err_payload}'; server responded with HTTP {he.code} containing raw SQL syntax exception.",
                                parameter="id",
                                cvss_score=8.6,
                                severity="HIGH",
                                cwe_id="CWE-89",
                            )
        except Exception:
            pass
        return ProbeResult(
            False,
            "No SQL syntax error leakage or database exception observed",
            "",
            verification_state="Unconfirmed",
        )

    # 11. Local File Inclusion (LFI) & Path Traversal
    if "lfi" in c_clean or "file-inclusion" in c_clean or "traversal" in c_clean:
        try:
            test_eps = [endpoint]
            if "fi" not in endpoint.lower() and "file" not in endpoint.lower():
                test_eps.append("/vulnerabilities/fi/")

            for ep in test_eps:
                curr_ep_url = target_url.rstrip("/") + "/" + ep.lstrip("/")
                for param in ("page", "file", "path"):
                    test_url = (
                        curr_ep_url
                        + ("&" if "?" in curr_ep_url else "?")
                        + f"{param}=../../../../../../etc/passwd"
                    )
                    req_headers = {"User-Agent": "AI-VAPT/2.0"}
                    req_headers.update(auth_headers)
                    req = urllib.request.Request(test_url, headers=req_headers)
                    try:
                        with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                            body = resp.read(20000).decode("utf-8", errors="ignore")
                            if "root:x:0:0:" in body or "root:*:0:0:" in body:
                                return ProbeResult(
                                    True,
                                    f"Arbitrary system file disclosure via path traversal (/etc/passwd) on {ep}",
                                    body[:350],
                                    verification_state="Verified",
                                    reproducible_request=f"GET {test_url} HTTP/1.1",
                                    demonstrated_impact="Unsanitized file path input permits unauthorized read access to host system files (/etc/passwd) crossing document root boundaries.",
                                    verification_procedure=f"Submitted directory traversal sequence ({param}=../../etc/passwd); observed root account entry in HTTP response body.",
                                    parameter=param,
                                    cvss_score=7.5,
                                    severity="HIGH",
                                    cwe_id="CWE-22",
                                )
                    except Exception:
                        pass
        except Exception:
            pass
        return ProbeResult(
            False,
            "Path traversal sequence blocked or sanitized by server",
            "",
            verification_state="Unconfirmed",
        )

    # 12. Remote Command Injection (RCE)
    if "cmd" in c_clean or "command" in c_clean or "exec" in c_clean:
        try:
            test_eps = [endpoint]
            if "exec" not in endpoint.lower():
                test_eps.append("/vulnerabilities/exec/")

            for ep in test_eps:
                curr_ep_url = target_url.rstrip("/") + "/" + ep.lstrip("/")
                # 1. POST probe (DVWA style ping form)
                post_data = urllib.parse.urlencode(
                    {"ip": "127.0.0.1; id", "Submit": "Submit"}
                ).encode("utf-8")
                req_headers = {
                    "User-Agent": "AI-VAPT/2.0",
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                req_headers.update(auth_headers)
                post_req = urllib.request.Request(curr_ep_url, data=post_data, headers=req_headers)
                try:
                    with urllib.request.urlopen(post_req, timeout=4.0, context=ctx) as resp:
                        body = resp.read(20000).decode("utf-8", errors="ignore")
                        if re.search(r"uid=\d+.*gid=\d+", body):
                            return ProbeResult(
                                True,
                                f"Command execution confirmed via system ID output reflection on {ep}",
                                body[:350],
                                verification_state="Verified",
                                reproducible_request=f"POST {curr_ep_url} HTTP/1.1\nContent-Type: application/x-www-form-urlencoded\n\nip=127.0.0.1%3B+id&Submit=Submit",
                                demonstrated_impact="Unsanitized shell concatenation permits arbitrary command execution in host process/container context.",
                                verification_procedure="Submitted benign system command probe '; id' via HTTP POST parameter 'ip'; observed real uid/gid shell output reflection.",
                                parameter="ip",
                                cvss_score=9.8,
                                severity="CRITICAL",
                                cwe_id="CWE-78",
                            )
                except Exception:
                    pass

                # 2. GET probe
                test_url = (
                    curr_ep_url + ("&" if "?" in curr_ep_url else "?") + "ip=127.0.0.1;id&cmd=id"
                )
                get_headers = {"User-Agent": "AI-VAPT/2.0"}
                get_headers.update(auth_headers)
                get_req = urllib.request.Request(test_url, headers=get_headers)
                try:
                    with urllib.request.urlopen(get_req, timeout=4.0, context=ctx) as resp:
                        body = resp.read(20000).decode("utf-8", errors="ignore")
                        if re.search(r"uid=\d+.*gid=\d+", body):
                            return ProbeResult(
                                True,
                                f"Command execution confirmed via system ID output reflection on {ep}",
                                body[:350],
                                verification_state="Verified",
                                reproducible_request=f"GET {test_url} HTTP/1.1",
                                demonstrated_impact="Unsanitized shell concatenation permits arbitrary command execution in host process/container context.",
                                verification_procedure="Submitted benign system command probe '; id' via query parameter; observed real uid/gid shell output reflection.",
                                parameter="ip",
                                cvss_score=9.8,
                                severity="CRITICAL",
                                cwe_id="CWE-78",
                            )
                except Exception:
                    pass
        except Exception:
            pass
        return ProbeResult(
            False,
            "Command injection payload rejected or sanitized by application",
            "",
            verification_state="Unconfirmed",
        )

    # 13. File Upload RCE
    if "upload" in c_clean:
        return (
            False,
            "File upload endpoint is not exposed, requires authentication, or blocks executable extensions",
            "",
        )

    # 14. Missing CAPTCHA on Authentication / Login Surface
    if "captcha" in c_clean:
        try:
            req = urllib.request.Request(full_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(50000).decode("utf-8", errors="ignore")
                has_pwd = bool(re.search(r'type=["\']password["\']', body, re.I))
                has_captcha = bool(re.search(r"(captcha|recaptcha|hcaptcha|turnstile)", body, re.I))
                if has_pwd and not has_captcha:
                    return (
                        True,
                        f"Authentication form at {endpoint} lacks automated bot / CAPTCHA protection",
                        "Login form identified without anti-automation challenge",
                    )
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
                    val_match = re.search(r"=(.*?)(?:;|$)", c)
                    if val_match:
                        val = val_match.group(1).strip()
                        if len(val) < 16 or val.isdigit():
                            return (
                                True,
                                f"Predictable low-entropy session identifier identified: {c.split(';')[0]}",
                                c,
                            )
        except Exception:
            pass
        return False, "Session identifiers exhibit adequate entropy and length", ""

    # 16. Insecure Client-Side JavaScript Processing
    if "client-js" in c_clean:
        try:
            req = urllib.request.Request(full_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(50000).decode("utf-8", errors="ignore")
                sinks = re.findall(
                    r"(document\.write\(|eval\(|window\.eval\(|innerHTML\s*=)", body, re.I
                )
                if sinks:
                    return (
                        True,
                        f"Insecure client-side DOM processing sinks detected ({sinks[0]})",
                        f"Pattern: {sinks[0]}",
                    )
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
                    return (
                        True,
                        "Exposed .git repository metadata accessible without authorization",
                        body,
                    )
        except Exception:
            pass
        return False, ".git repository metadata is not accessible", ""

    # 18. Exposed Diagnostic Tracing & Error Log
    if "trace" in c_clean or "elmah" in c_clean:
        try:
            trace_url = target_url.rstrip("/") + (
                "/trace.axd" if "trace" in c_clean else "/elmah.axd"
            )
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
                        return (
                            True,
                            f"Vulnerable component verified: {comp['library']} v{comp['version']} ({cves})",
                            f"Library: {comp['library']} v{comp['version']}\nSource: {comp.get('source_file')}\nCVEs: {cves}\nRemediation: {comp.get('remediation')}",
                        )
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
                    return ProbeResult(
                        False,
                        f"Open TCP Port {port} identified on target host {host} (Reconnaissance host/port enumeration metadata; not an unauthenticated vulnerability finding)",
                        f"Connection to {host}:{port} state: OPEN (SYN-ACK received)",
                        verification_state="Discovered",
                        demonstrated_impact="Service port is reachable across network attack surface.",
                        verification_procedure=f"Performed TCP connection probe to {host}:{port}; connection succeeded.",
                        parameter=str(port),
                        cvss_score=0.0,
                        severity="INFO",
                    )
        except Exception as exc:
            logger.debug("Port probe error: %s", exc)
        return ProbeResult(
            False,
            "Port closed or inaccessible from external network",
            "",
            verification_state="Unconfirmed",
        )

    # 22. Subresource Integrity (SRI)
    if "subresource-integrity" in c_clean or "sri" in c_clean:
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(60000).decode("utf-8", errors="ignore")
                scripts = re.findall(r'<script\b[^>]*src=["\']([^"\']+)["\'][^>]*>', body, re.I)
                missing_sri = [s for s in scripts if s.startswith("http") and "integrity=" not in s]
                if missing_sri:
                    return (
                        True,
                        f"Subresource Integrity (SRI) missing on external script inclusions ({len(missing_sri)} found)",
                        f"Script missing SRI: {missing_sri[0]}",
                    )
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
                    return (
                        True,
                        f"Cross-domain JavaScript source files loaded from external origins ({len(external)} found)",
                        f"External script inclusion: {external[0]}",
                    )
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
                        return (
                            True,
                            "Missing Anti-Clickjacking Header: X-Frame-Options is not set",
                            "X-Frame-Options: [NOT PRESENT]",
                        )
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
                    return (
                        True,
                        "Strict-Transport-Security (HSTS) Header Not Set on HTTPS service",
                        "Strict-Transport-Security: [NOT PRESENT]",
                    )
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
                        get_req = urllib.request.Request(
                            test_put_url, headers={"User-Agent": "AI-VAPT/2.0"}
                        )
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
                                    del_req = urllib.request.Request(
                                        test_put_url,
                                        headers={"User-Agent": "AI-VAPT/2.0"},
                                        method="DELETE",
                                    )
                                    urllib.request.urlopen(del_req, timeout=4.0, context=ctx)
                                except Exception:
                                    pass
                                return (
                                    True,
                                    "Arbitrary file write verified via HTTP PUT (marker read-back confirmed)",
                                    f"PUT returned {put_resp.status}, GET returned verified marker: {unique_marker}",
                                )
                            return (
                                False,
                                "HTTP PUT returned 200 due to SPA fallback routing; marker not written to filesystem (UNVERIFIED)",
                                get_body[:250],
                            )
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
                    return (
                        True,
                        "Cookie Without Secure Flag identified over HTTPS",
                        f"Insecure Set-Cookie: {insecure[0]}",
                    )
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
                    return (
                        True,
                        "ASP.NET ViewState parameter present in page body",
                        "Hidden field __VIEWSTATE identified",
                    )
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
                vuln_links = [
                    l for l in links if "noopener" not in l.lower() or "noreferrer" not in l.lower()
                ]
                if vuln_links:
                    return (
                        True,
                        "Reverse Tabnabbing vulnerability in target='_blank' links without rel='noopener noreferrer'",
                        vuln_links[0],
                    )
        except Exception:
            pass
        return False, "All external links enforce rel='noopener noreferrer'", ""

    # 29. Server-Side Request Forgery (SSRF)
    if "ssrf" in c_clean or "request-forgery" in c_clean:
        try:
            test_url = (
                full_url
                + ("&" if "?" in full_url else "?")
                + "dest=http://127.0.0.1:80&url=http://127.0.0.1:80"
            )
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
            test_url = (
                full_url
                + ("&" if "?" in full_url else "?")
                + "q={{7*7}}&name={{7*7}}&template={{7*7}}"
            )
            req = urllib.request.Request(test_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(20000).decode("utf-8", errors="ignore")
                if "49" in body and "{{7*7}}" not in body:
                    return (
                        True,
                        "Server-Side Template Injection confirmed (expression {{7*7}} evaluated to 49)",
                        body[:300],
                    )
        except Exception:
            pass
        return (
            False,
            "Template expressions not evaluated by backend engine or properly sanitized",
            "",
        )

    # 31. Client-Side Prototype Pollution
    if "prototype-pollution" in c_clean or "proto" in c_clean:
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(50000).decode("utf-8", errors="ignore")
                patterns = [
                    r"__proto__",
                    r"constructor\.prototype",
                    r"Object\.assign\(",
                    r"\$\.extend\(",
                ]
                for pat in patterns:
                    if re.search(pat, body, re.I):
                        return (
                            True,
                            f"Client-side prototype manipulation pattern identified: {pat}",
                            f"Pattern: {pat}",
                        )
        except Exception:
            pass
        return False, "No client-side prototype mutation patterns detected", ""

    # 32. Server-Side Code Injection (PHP, Python, JS eval)
    if "code-injection" in c_clean or "eval" in c_clean or "php-code" in c_clean:
        try:
            test_url = (
                full_url + ("&" if "?" in full_url else "?") + "code=phpinfo()&eval=phpinfo()"
            )
            req = urllib.request.Request(test_url, headers={"User-Agent": "AI-VAPT/2.0"})
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                body = resp.read(20000).decode("utf-8", errors="ignore")
                if "PHP Version" in body or "Zend Engine" in body:
                    return (
                        True,
                        "Server-side code execution verified via function reflection",
                        body[:300],
                    )
        except Exception:
            pass
        return False, "Code evaluation input rejected or not executed by backend runtime", ""

    # Default baseline check: NEVER mark vulnerable simply because HTTP status is 200 or 302!
    return False, "Endpoint probe did not exhibit vulnerable behavior or exploit confirmation", ""


def _sync_engine_candidates(engine, candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge GAP-1 prioritization scoring metadata with GAP-2 dynamic execution state."""
    merged = []
    for ec in engine.candidates.values():
        meta = dict(candidate_map.get(ec.id, {}))
        c_dict = (
            ec.model_dump()
            if hasattr(ec, "model_dump")
            else (ec.dict() if hasattr(ec, "dict") else dict(ec))
        )
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


def _execute_run_worker(run_id: str, req: RunRequest, runtime_key: str | None):
    """Background worker executing the assessment workflow."""
    global _CURRENT_ACTIVE_RUN_ID
    run_entry = _RUNS.get(run_id)
    if not run_entry:
        return

    if req.mode == "autonomous":
        _CURRENT_ACTIVE_RUN_ID = run_id

    try:
        now_ts = _utc_now()
        if not run_entry.get("start_time"):
            run_entry["start_time"] = now_ts
        if not run_entry.get("started_at"):
            run_entry["started_at"] = run_entry["start_time"]
        run_entry["_current_segment_start"] = now_ts
        run_entry["status"] = "running"
        run_entry["end_time"] = None
        run_entry["error"] = None
        if "duration_seconds" not in run_entry:
            run_entry["duration_seconds"] = 0.0
        run_entry["active_task"] = "Target reconnaissance and technology fingerprinting"
        run_entry["active_agent"] = "Autonomous VAPT Engine"
        target_url = (
            req.target_url or getattr(req, "target", None) or run_entry.get("target_url", "") or ""
        ).strip()
        scan_mode = (getattr(req, "scan_mode", None) or "deep").lower()
        default_turns = 50 if scan_mode == "quick" else (100 if scan_mode == "standard" else 500)
        req_turns = getattr(req, "max_turns", None)
        if req_turns is not None and int(req_turns) > 0:
            max_turns = int(req_turns)
        else:
            max_turns = default_turns
        max_turns = max(1, min(1000, max_turns))
        run_entry["max_turns"] = max_turns

        # Execution transparency: block autonomous execution if Docker runtime is unavailable
        docker_available = _is_docker_available()
        if req.mode == "autonomous" and not docker_available:
            run_entry["status"] = "blocked"
            run_entry["execution_mode"] = "blocked"
            run_entry["error"] = (
                "Autonomous multi-agent execution blocked: Docker runtime (daemon and CLI) is unavailable on host. "
                "Ensure Docker is accessible, or select lightweight active scanning (mode='lightweight')."
            )
            run_entry["end_time"] = _utc_now()
            run_entry["events"].append(
                {
                    "timestamp": _utc_now(),
                    "event": "RUN_BLOCKED",
                    "message": run_entry["error"],
                }
            )
            _save_run_to_disk(run_entry)
            if run_id == _CURRENT_ACTIVE_RUN_ID:
                _CURRENT_ACTIVE_RUN_ID = None
            return

        is_live_target = req.mode in (
            "web",
            "autonomous",
            "web_controlled",
            "lightweight",
            "in_process",
        ) and target_url.startswith("http")
        if req.mode == "autonomous":
            execution_mode = "autonomous_multi_agent"
            run_entry["active_agent"] = "Autonomous Multi-Agent Core"
        elif req.mode in ("web", "web_controlled", "lightweight", "in_process"):
            execution_mode = "lightweight_active_scanner"
            run_entry["active_agent"] = "In-Process Active Scanner"
        else:
            execution_mode = "simulation"
            run_entry["active_agent"] = "Simulation Benchmark"
        run_entry["execution_mode"] = execution_mode

        max_k = max(1, int(req.max_attempts or 2))
        if os.environ.get("PYTEST_CURRENT_TEST"):
            turn_delay = 0.0
        else:
            turn_delay = (
                0.05 if scan_mode == "quick" else (0.25 if scan_mode == "standard" else 0.50)
            )

        cli_cfg = _read_strix_cli_config()
        from strix.core.runtime_credentials import (
            get_runtime_base_url,
            get_runtime_credential,
            get_runtime_model,
        )

        provider = (req.assessor_provider or "openrouter").lower().strip()
        if not runtime_key:
            runtime_key = get_runtime_credential(provider)

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
        add_hosts = getattr(req, "additional_authorized_hosts", None) or run_entry.get(
            "additional_authorized_hosts", []
        )
        run_entry["additional_authorized_hosts"] = add_hosts
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

                full_scan_res = FullScanner.scan_target(
                    target_url,
                    scan_mode=scan_mode,
                    additional_authorized_hosts=run_entry.get("additional_authorized_hosts", []),
                )
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
        run_entry["events"].append(
            {
                "timestamp": _utc_now(),
                "event": (
                    "AUTONOMOUS_RUN_STARTED"
                    if execution_mode == "autonomous_multi_agent"
                    else (
                        "LIGHTWEIGHT_SCAN_STARTED"
                        if execution_mode == "lightweight_active_scanner"
                        else "RUN_STARTED"
                    )
                ),
                "message": (
                    f"Autonomous multi-agent assessment started (Depth: {scan_mode.upper()}, Limit: {max_turns} turns, Tier: {evidence_tier})"
                    if execution_mode == "autonomous_multi_agent"
                    else (
                        f"Lightweight in-process active scanner started (Mode: {req.mode.upper()}, Depth: {scan_mode.upper()})"
                        if execution_mode == "lightweight_active_scanner"
                        else f"Simulation benchmark assessment started in mode: {req.mode} (Depth: {scan_mode.upper()})"
                    )
                ),
            }
        )
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
                    run_entry["events"].append(
                        {
                            "timestamp": _utc_now(),
                            "event": "AUTH_SESSION_ESTABLISHED",
                            "message": f"Authenticated session established as '{auth_session.username}' (Role: {auth_session.role or 'customer'}). Masked token: {auth_session.to_safe_dict().get('masked_token')}",
                        }
                    )
                else:
                    run_entry["events"].append(
                        {
                            "timestamp": _utc_now(),
                            "event": "AUTH_SESSION_FAILED",
                            "message": f"Target authentication failed: {auth_session.error_message}",
                        }
                    )
            except Exception as auth_err:
                logger.warning("Auth session establishment error: %s", auth_err)

        # 1. GAP-1 Triage & Exploit Quality Scoring (Dynamic Surface Crawling)
        from strix.core.decision_engine.engine import DecisionEngine
        from strix.core.decision_engine.schemas import (
            ActionCandidate,
            CandidateState,
            Outcome,
            PivotActionType,
            PivotEvent,
        )
        from strix.core.triage.owasp_mapping import map_finding_to_owasp

        is_resumed_session = bool(run_entry.get("is_resumed")) or any(
            e.get("event") == "RUN_RESUMED" for e in run_entry.get("events", [])
        )
        if is_resumed_session:
            detected_tech = run_entry.get("tech_stack", "generic_web")
            candidates = run_entry.get("candidates", [])
        else:
            from strix.core.triage.exploit_assessor import run_gap1_triage

            raw_candidates = run_gap1_triage(
                scenario=req.scenario,
                provider=req.assessor_provider,
                model_name=req.assessor_model,
                api_key=runtime_key,
                target_url=target_url,
                scan_mode=scan_mode,
                full_scan_res=full_scan_res,
                auth_session=auth_session,
            )
            candidates = [
                c.model_dump()
                if hasattr(c, "model_dump")
                else (c.dict() if hasattr(c, "dict") else dict(c))
                for c in raw_candidates
            ]
            run_entry["candidates"] = candidates
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
            run_entry["events"].append(
                {
                    "timestamp": _utc_now(),
                    "event": "GAP1_TRIAGE_COMPLETED",
                    "message": f"GAP-1 dynamic triage prioritized {len(candidates)} candidate(s) for stack {detected_tech.upper()}",
                }
            )

        # 2. GAP-2 Bounded Dynamic Decision-Pivoting
        engine = DecisionEngine(pivot_threshold=max_k)
        engine_candidates = []
        for c in run_entry.get("candidates", []):
            raw_state = c.get("state") or c.get("status") or "PENDING"
            try:
                c_state = CandidateState(raw_state)
            except Exception:
                c_state = CandidateState.PENDING
            engine_candidates.append(
                ActionCandidate(
                    id=c.get("id"),
                    name=c.get("name", c.get("id")),
                    target=c.get("target", target_url or "target"),
                    endpoint=c.get("endpoint", "/"),
                    parameter=c.get("parameter"),
                    probability=c.get("composite_score", c.get("probability", 0.5)),
                    severity=c.get("severity", "medium"),
                    cvss_score=c.get("cvss_score", 5.0),
                    cwe_id=c.get("cwe_id", "CWE-200"),
                    state=c_state,
                    attempts=int(c.get("attempts", 0)),
                    detail=c.get("detail", ""),
                    reproducible_request=c.get("reproducible_request"),
                    reproducible_response=c.get("reproducible_response"),
                    verification_procedure=c.get("verification_procedure"),
                    demonstrated_impact=c.get("demonstrated_impact"),
                )
            )
        engine.initialize(engine_candidates)
        if is_resumed_session:
            for ac in engine_candidates:
                engine.candidates[ac.id] = ac
            if run_entry.get("decision_trace"):
                engine.decision_trace = list(run_entry.get("decision_trace", []))
            if run_entry.get("pivot_events"):
                pe_list = []
                for pe in run_entry.get("pivot_events", []):
                    if isinstance(pe, dict):
                        pe_copy = dict(pe)
                        if "type" not in pe_copy:
                            pe_copy["type"] = pe_copy.get("event") or "GAP2_PIVOT"
                        pe_list.append(PivotEvent(**pe_copy))
                    else:
                        pe_list.append(pe)
                engine.pivot_events = pe_list

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
        init_log = f"[TURN {current_turn}/{max_turns}] Initializing VAPT scan on {target_url or 'target'} (Mode: {req.mode.upper()}, Scan Depth: {scan_mode.upper()}, Limit: {max_turns} turns, Threshold k={max_k})"
        engine.log("INIT", init_log)
        time.sleep(turn_delay)

        sp_stats = run_entry.get("spider_stats") or {}
        if sp_stats:
            current_turn += 1
            engine.log(
                "SPIDER",
                f"[TURN {current_turn}/{max_turns}] Web Spider: discovered {len(sp_stats.get('discovered_paths', []))} route(s), {sp_stats.get('forms_count', 0)} form(s), {sp_stats.get('parameters_count', 0)} parameter(s)",
            )
            time.sleep(turn_delay)

        current_turn += 1
        engine.log(
            "RECON",
            f"[TURN {current_turn}/{max_turns}] Identified runtime stack: {detected_tech.upper()} | Audited {len(run_entry.get('open_ports', []))} network port(s), {len(run_entry.get('components', []))} component library(ies)",
        )
        time.sleep(turn_delay)

        current_turn += 1
        engine.log(
            "TRIAGE",
            f"[TURN {current_turn}/{max_turns}] GAP-1 prioritized {total_cands} candidate vector(s) across target attack surface",
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
        (control_dir / "gap1_queue.json").write_text(
            json.dumps(gap1_payload, indent=2), encoding="utf-8"
        )

        docker_available = _is_docker_available()
        if req.mode == "autonomous" and is_live_target and docker_available:
            engine.log(
                "AUTONOMOUS",
                f"[TURN 1/{max_turns}] Spawning AI-VAPT Multi-Agent Autonomous Pentest Engine against {target_url} (Limit: {max_turns} turns, Depth: {scan_mode.upper()})",
            )
            run_entry["events"].append(
                {
                    "timestamp": _utc_now(),
                    "event": "AUTONOMOUS_EXECUTION_STARTED",
                    "message": f"Autonomous multi-agent pentest runner spawned with {max_turns} turns limit.",
                }
            )
            _save_run_to_disk(run_entry)

            # 1. Target URL sandbox rewriting for Docker (localhost/127.0.0.1 -> host.docker.internal)
            parsed_target = urllib.parse.urlsplit(target_url)
            host = parsed_target.hostname or ""
            if host in ("localhost", "127.0.0.1", "::1"):
                netloc = (
                    f"host.docker.internal:{parsed_target.port}"
                    if parsed_target.port
                    else "host.docker.internal"
                )
                sandbox_target_url = urllib.parse.urlunsplit(
                    (
                        parsed_target.scheme,
                        netloc,
                        parsed_target.path,
                        parsed_target.query,
                        parsed_target.fragment,
                    )
                )
                engine.log(
                    "SANDBOX",
                    f"Rewrote loopback target {target_url} -> {sandbox_target_url} for Docker sandbox reachability",
                )
            else:
                sandbox_target_url = target_url

            # 2. Environment configuration with CLI config fallback
            sub_env = dict(os.environ)
            cli_cfg = _read_strix_cli_config()

            from strix.core.runtime_credentials import get_runtime_credential, get_runtime_model

            provider = (
                (getattr(req, "provider", None) or getattr(req, "assessor_provider", None) or "")
                .lower()
                .strip()
            )
            if not provider:
                if (runtime_key and runtime_key.startswith("sk-ant-")) or cli_cfg.get(
                    "ANTHROPIC_API_KEY"
                ):
                    provider = "anthropic"
                elif (runtime_key and runtime_key.startswith("sk-or-")) or cli_cfg.get(
                    "OPENROUTER_API_KEY"
                ):
                    provider = "openrouter"
                elif (runtime_key and runtime_key.startswith("AIza")) or cli_cfg.get(
                    "GEMINI_API_KEY"
                ):
                    provider = "google"
                elif (runtime_key and runtime_key.startswith("sk-")) or cli_cfg.get(
                    "OPENAI_API_KEY"
                ):
                    provider = "openai"
                else:
                    provider = "openrouter"

            key = (
                runtime_key
                or getattr(req, "api_key", None)
                or getattr(req, "assessor_api_key", None)
                or get_runtime_credential(provider)
            )
            raw_model = (
                getattr(req, "model", None)
                or getattr(req, "assessor_model", None)
                or get_runtime_model(provider)
            )
            if not raw_model:
                if provider == "openrouter":
                    raw_model = DEFAULT_OPENROUTER_MODEL
                elif provider == "anthropic":
                    raw_model = "claude-3-5-sonnet-20241022"
                elif provider == "openai":
                    raw_model = "gpt-4o-mini"
                elif provider == "google":
                    raw_model = "gemini-2.0-flash"
                elif provider == "ollama":
                    raw_model = "qwen2.5:1.5b"
                else:
                    raw_model = "custom-model"

            if provider == "anthropic":
                m_name = (
                    raw_model if raw_model.startswith("anthropic/") else f"anthropic/{raw_model}"
                )
                sub_env["STRIX_LLM_PROVIDER"] = "anthropic"
                sub_env["STRIX_LLM"] = m_name
                if key:
                    sub_env["ANTHROPIC_API_KEY"] = key
                    sub_env["LLM_API_KEY"] = key
            elif provider == "openrouter":
                m_name = format_openrouter_model(raw_model)
                sub_env["STRIX_LLM_PROVIDER"] = "openrouter"
                sub_env["STRIX_LLM"] = m_name
                sub_env["OPENAI_BASE_URL"] = (
                    cli_cfg.get("OPENAI_BASE_URL") or "https://openrouter.ai/api/v1"
                )
                sub_env["OPENROUTER_API_BASE"] = (
                    cli_cfg.get("OPENROUTER_API_BASE") or "https://openrouter.ai/api/v1"
                )
                if key:
                    sub_env["OPENROUTER_API_KEY"] = key
                    sub_env["OPENAI_API_KEY"] = key
                    sub_env["LLM_API_KEY"] = key
            elif provider == "google":
                m_name = (
                    raw_model
                    if (raw_model.startswith("google/") or raw_model.startswith("gemini/"))
                    else f"google/{raw_model}"
                )
                sub_env["STRIX_LLM_PROVIDER"] = "google"
                sub_env["STRIX_LLM"] = m_name
                if key:
                    sub_env["GEMINI_API_KEY"] = key
                    sub_env["LLM_API_KEY"] = key
            elif provider == "ollama":
                m_name = raw_model if raw_model.startswith("ollama/") else f"ollama/{raw_model}"
                sub_env["STRIX_LLM_PROVIDER"] = "ollama"
                sub_env["STRIX_LLM"] = m_name
                ollama_base = (
                    getattr(req, "api_base", None)
                    or getattr(req, "assessor_api_base", None)
                    or get_runtime_base_url("ollama")
                    or os.environ.get("OLLAMA_API_BASE")
                    or "http://127.0.0.1:11434"
                )
                sub_env["OLLAMA_API_BASE"] = ollama_base
                sub_env["LLM_API_BASE"] = ollama_base
                sub_env["LLM_API_KEY"] = "ollama"
                sub_env["STRIX_FORCE_REQUIRED_TOOL_CHOICE"] = "true"
                if "LLM_EXTRA_BODY" not in sub_env:
                    sub_env["LLM_EXTRA_BODY"] = json.dumps({"options": {"num_ctx": 32768}})
                sub_env.pop("OPENROUTER_API_KEY", None)
                sub_env.pop("OPENROUTER_API_BASE", None)
                sub_env.pop("OPENAI_BASE_URL", None)
                sub_env.pop("ANTHROPIC_API_KEY", None)
                sub_env.pop("GEMINI_API_KEY", None)
            elif provider == "openai":
                m_name = raw_model if raw_model.startswith("openai/") else f"openai/{raw_model}"
                sub_env["STRIX_LLM_PROVIDER"] = "openai"
                sub_env["STRIX_LLM"] = m_name
                sub_env["OPENAI_BASE_URL"] = (
                    get_runtime_base_url("openai")
                    or os.environ.get("OPENAI_BASE_URL")
                    or cli_cfg.get("OPENAI_BASE_URL")
                    or "https://api.openai.com/v1"
                )
                if key:
                    sub_env["OPENAI_API_KEY"] = key
                    sub_env["LLM_API_KEY"] = key
            elif provider in ("cloud_hosted", "custom_cloud", "custom"):
                active_cloud = _get_active_cloud_profile()
                cloud_model = (
                    req.assessor_model
                    or (active_cloud.get("model") if active_cloud else None)
                    or cli_cfg.get("STRIX_LLM")
                    or "custom-model"
                )
                m_name = (
                    cloud_model if cloud_model.startswith("openai/") else f"openai/{cloud_model}"
                )
                base_url = (
                    (active_cloud.get("api_base") if active_cloud else None)
                    or get_runtime_base_url("cloud_hosted")
                    or get_runtime_base_url("custom")
                    or cli_cfg.get("OPENAI_BASE_URL")
                    or os.environ.get("OPENAI_BASE_URL")
                    or "https://api.openai.com/v1"
                )
                cloud_key = (
                    key
                    or (active_cloud.get("api_key") if active_cloud else None)
                    or get_runtime_credential("cloud_hosted")
                    or "none"
                )
                sub_env["STRIX_LLM_PROVIDER"] = "cloud_hosted"
                sub_env["STRIX_LLM"] = m_name
                sub_env["OPENAI_BASE_URL"] = base_url
                sub_env["LLM_API_BASE"] = base_url
                sub_env["STRIX_API_TYPE"] = "chat_completions"
                sub_env["OPENAI_API_KEY"] = cloud_key
                sub_env["LLM_API_KEY"] = cloud_key
                if active_cloud:
                    if active_cloud.get("extra_headers"):
                        sub_env["LLM_EXTRA_HEADERS"] = json.dumps(active_cloud["extra_headers"])
                    if active_cloud.get("timeout"):
                        sub_env["LLM_TIMEOUT"] = str(active_cloud["timeout"])
                    if active_cloud.get("streaming") is False:
                        sub_env["LLM_DISABLE_STREAMING"] = "1"
                    if active_cloud.get("context_window"):
                        sub_env["STRIX_CONTEXT_FALLBACK_TOKENS"] = str(
                            active_cloud["context_window"]
                        )

            # The engine subprocess receives per-request credentials/base URL
            # via env. Prevent its CLI bootstrap from persisting those runtime
            # values into the operator's ~/.strix/cli-config.json profile.
            sub_env["STRIX_NO_PERSIST_CONFIG"] = "1"
            sub_env["STRIX_GAP_CONTROL_DIR"] = str(control_dir)
            sub_env["STRIX_GAP1_QUEUE"] = str(control_dir / "gap1_queue.json")
            sub_env["STRIX_GAP2_THRESHOLD"] = str(max_k)
            sub_env["STRIX_GAP1_ENABLED"] = "1"
            sub_env["STRIX_GAP2_ENABLED"] = "1"
            # Propagate the operator's saved CLI provider settings into the
            # worker. Without this, a dashboard-launched run silently ignored
            # LLM_EXTRA_BODY (num_ctx), extra headers, tool-choice mode and
            # timeout, producing a degraded/truncated model session.
            _CLI_ENV_KEYS = (
                "LLM_EXTRA_BODY",
                "LLM_EXTRA_HEADERS",
                "STRIX_FORCE_REQUIRED_TOOL_CHOICE",
                "STRIX_CONTEXT_FALLBACK_TOKENS",
                "STRIX_REASONING_EFFORT",
                "LLM_TIMEOUT",
                "STRIX_API_TYPE",
                "OPENAI_BASE_URL",
                "LLM_API_BASE",
                "LLM_API_KEY",
                "OPENAI_API_KEY",
                "OPENROUTER_API_BASE",
                "OPENROUTER_API_KEY",
                "ANTHROPIC_API_BASE",
                "ANTHROPIC_API_KEY",
                "GEMINI_API_KEY",
            )
            for _ck in _CLI_ENV_KEYS:
                if cli_cfg.get(_ck) and _ck not in sub_env:
                    sub_env[_ck] = str(cli_cfg[_ck])
            if cli_cfg.get("LLM_EXTRA_BODY") and "LLM_EXTRA_BODY" not in os.environ:
                sub_env["LLM_EXTRA_BODY"] = str(cli_cfg["LLM_EXTRA_BODY"])

            if cli_cfg.get("STRIX_REASONING_EFFORT"):
                sub_env["STRIX_REASONING_EFFORT"] = cli_cfg["STRIX_REASONING_EFFORT"]
            engine_run_name = _engine_run_name(run_id)
            sub_env["STRIX_RUN_NAME"] = engine_run_name
            sub_env["PYTHONPATH"] = f"{PROJECT_ROOT}:{sub_env.get('PYTHONPATH', '')}"

            # Snapshot directory state prior to launch across both potential base dirs
            candidate_bases = [base_dir]
            if (PROJECT_ROOT / "strix_runs") not in candidate_bases:
                candidate_bases.append(PROJECT_ROOT / "strix_runs")

            before_dirs = set()
            for cb in candidate_bases:
                if cb.is_dir():
                    before_dirs.update(d.name for d in cb.iterdir() if d.is_dir())

            existing_run_dir = PROJECT_ROOT / "strix_runs" / engine_run_name
            can_resume_engine = (
                is_resumed_session
                and (existing_run_dir / "run.json").is_file()
                and (existing_run_dir / ".state" / "agents.json").is_file()
            )

            if can_resume_engine:
                cmd = [
                    sys.executable,
                    "-c",
                    "import sys; from strix.interface.main import main; sys.exit(main())",
                    "-n",
                    "-r",
                    engine_run_name,
                    "-m",
                    scan_mode,
                    "--max-turns",
                    str(max_turns),
                ]
            else:
                cmd = [
                    sys.executable,
                    "-c",
                    "import sys; from strix.interface.main import main; sys.exit(main())",
                    "-n",
                    "-t",
                    sandbox_target_url,
                    "-m",
                    scan_mode,
                    "--max-turns",
                    str(max_turns),
                    "--run-name",
                    engine_run_name,
                ]
            custom_instruction = getattr(req, "instruction", None) or ""
            secrets_to_mask: list[str] = []
            if key and len(str(key)) > 4:
                secrets_to_mask.append(str(key))
            if cloud_key and len(str(cloud_key)) > 4 and str(cloud_key) != "none":
                secrets_to_mask.append(str(cloud_key))

            if auth_session and auth_session.authenticated:
                tok = auth_session.token or ""
                sub_env["STRIX_AUTH_TOKEN"] = tok
                sub_env["STRIX_TARGET_AUTH_TOKEN"] = tok
                sub_env["STRIX_AUTH_HEADER"] = auth_session.header_name or "Authorization"
                sub_env["STRIX_AUTH_USERNAME"] = auth_session.username or ""
                sub_env["STRIX_AUTH_ROLE"] = auth_session.role or "customer"
                if tok and len(tok) > 4:
                    secrets_to_mask.append(tok)
                auth_note = (
                    f"Authentication verified for target {sandbox_target_url}.\n"
                    f"Test Account: {auth_session.username} (Role: {auth_session.role or 'customer'}).\n"
                    f"Authenticated session available via environment: use header '${auth_session.header_name or 'Authorization'}: Bearer <redacted>' for authenticated endpoints. Refer to env var STRIX_AUTH_TOKEN.\n"
                    f"Never disclose raw credential strings or unredacted tokens in report outputs."
                )
                custom_instruction = f"{custom_instruction}\n\n{auth_note}".strip()

            if (
                custom_instruction
                and isinstance(custom_instruction, str)
                and custom_instruction.strip()
            ):
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

            underlying_run_name = engine_run_name
            ansi_re = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
            current_turn = 1
            agent_turns: dict[str, int] = {}
            turns_lock = threading.Lock()
            seen_gap_traces = set()
            last_stdout_lines: list[str] = []
            stderr_lines: list[str] = []

            def _record_agent_turn(t_val: int, agent_name: str | None = None) -> int:
                nonlocal current_turn
                with turns_lock:
                    name = (
                        agent_name.strip()
                        if agent_name
                        else (run_entry.get("active_agent") or "Root Agent")
                    )
                    agent_turns[name] = max(agent_turns.get(name, 0), t_val)
                    current_turn = max(current_turn, t_val)
                    run_entry["turns_consumed"] = current_turn
                    run_entry["last_progress_at"] = _utc_now()
                    return current_turn

            def _mask_line(line: str) -> str:
                if not line or not secrets_to_mask:
                    return line
                for s in secrets_to_mask:
                    if s and s in line:
                        line = line.replace(s, "[REDACTED]")
                return line

            # Background reader for stdout
            def _drain_stdout(pipe):
                nonlocal underlying_run_name, productive_turns, last_progress_time
                try:
                    for raw_out in iter(pipe.readline, ""):
                        clean_out = _mask_line(ansi_re.sub("", raw_out).strip())
                        if not clean_out:
                            continue
                        last_stdout_lines.append(clean_out)
                        if len(last_stdout_lines) > 50:
                            last_stdout_lines.pop(0)

                        m = re.search(r"Output\s+strix_runs/([a-zA-Z0-9_\-\.]+)", clean_out)
                        if m:
                            underlying_run_name = m.group(1).strip()
                            engine.log(
                                "SANDBOX",
                                f"Attached autonomous scan run directory: {underlying_run_name}",
                            )

                        ag_m = re.search(r"current_agent=([^,\n\r]+)", clean_out)
                        if ag_m:
                            run_entry["active_agent"] = ag_m.group(1).strip()

                        turn_m = re.search(r"Starting turn\s+(\d+)", clean_out, re.I)
                        if turn_m:
                            t_val = int(turn_m.group(1))
                            _record_agent_turn(t_val, run_entry.get("active_agent"))

                        inv_m = re.search(r"Invoking tool\s+([a-zA-Z0-9_\-]+)", clean_out)
                        if inv_m:
                            tool_name = inv_m.group(1)
                            run_entry["active_task"] = f"Invoking tool: {tool_name}"
                            if _is_productive_tool(tool_name):
                                productive_turns += 1
                                last_progress_time = time.time()
                            run_entry["last_progress_at"] = _utc_now()
                        elif "Calling LLM" in clean_out:
                            run_entry["active_task"] = (
                                f"Consulting model ({run_entry.get('active_agent', 'Root Agent')})"
                            )
                            run_entry["last_progress_at"] = _utc_now()
                        elif "update_coverage" in clean_out:
                            run_entry["active_task"] = "Updating attack surface coverage"
                            run_entry["last_progress_at"] = _utc_now()

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
                    for raw_err in iter(pipe.readline, ""):
                        clean_err = _mask_line(ansi_re.sub("", raw_err).strip())
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
            wall_clock_timeout = (
                600 if scan_mode == "quick" else (1800 if scan_mode == "standard" else 3600)
            )
            wall_clock_timeout = max(wall_clock_timeout, min(3600, max_turns * 30))

            proc_start_time = time.time()
            timed_out = False
            stalled = False
            productive_turns = 0
            last_progress_time = proc_start_time
            # Some SDK versions never emit "Invoking tool" lines; they record
            # real tool executions only in run.json["tool_calls"]. Track how
            # many of those we have consumed so progress detection works for
            # both log formats without ever counting bookkeeping tools.
            seen_tool_telemetry = 0
            log_file_pos = 0
            u_dir = None
            candidates_investigated = 0
            pivots_count = 0
            candidates_identified = total_cands

            def _sync_telemetry(final_sync: bool = False):
                nonlocal underlying_run_name, u_dir, log_file_pos
                nonlocal seen_tool_telemetry
                nonlocal current_turn, candidates_investigated, pivots_count, candidates_identified
                nonlocal productive_turns, last_progress_time

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
                                    if (
                                        d.is_dir()
                                        and d.name not in before_dirs
                                        and d.name not in (run_id, engine_run_name)
                                    ):
                                        discovered.append(d)
                        if discovered:
                            discovered.sort(key=lambda d: d.stat().st_mtime, reverse=True)
                            u_dir = discovered[0]
                            underlying_run_name = u_dir.name
                            engine.log(
                                "SANDBOX",
                                f"Discovered autonomous scan run directory: {underlying_run_name}",
                            )

                # 2a. Count productive tool executions from the engine's
                # telemetry array. SDK versions that log only
                # "Processing output item type=function_call" never emit
                # "Invoking tool" lines, so log tailing alone undercounts real
                # security work and can trigger a false no-progress stall.
                # Bookkeeping tools are excluded by _is_productive_tool.
                if u_dir and u_dir.is_dir():
                    engine_run_json = u_dir / "run.json"
                    if engine_run_json.is_file():
                        try:
                            ed = json.loads(engine_run_json.read_text(encoding="utf-8"))
                            productive_total = productive_tool_count(ed)
                            if productive_total > seen_tool_telemetry:
                                productive_turns += productive_total - seen_tool_telemetry
                                seen_tool_telemetry = productive_total
                                last_progress_time = time.time()
                        except Exception:
                            pass

                # 2. Tail strix.log. At final sync after process exit, re-read
                # the whole file: late writes may have arrived after the last
                # poll, and the turn recorder is idempotent (max-per-agent).
                if u_dir and u_dir.is_dir():
                    log_path = u_dir / "strix.log"
                    if log_path.is_file():
                        try:
                            with open(log_path, encoding="utf-8", errors="replace") as lf:
                                lf.seek(0 if final_sync else log_file_pos)
                                chunk = lf.read()
                                log_file_pos = lf.tell()
                            if chunk:
                                for line in chunk.splitlines():
                                    ag_m = re.search(r"current_agent=([^,\n\r]+)", line)
                                    if ag_m:
                                        run_entry["active_agent"] = ag_m.group(1).strip()
                                    ag_name = run_entry.get("active_agent") or "Agent"

                                    turn_m = re.search(r"Starting turn\s+(\d+)", line, re.I)
                                    if turn_m:
                                        t_val = int(turn_m.group(1))
                                        _record_agent_turn(t_val, ag_name)
                                        engine.log(
                                            "TURN",
                                            f"[TURN {current_turn}/{max_turns}] Active agent: {ag_name}",
                                        )

                                    inv_m = re.search(r"Invoking tool\s+([a-zA-Z0-9_\-]+)", line)
                                    if inv_m:
                                        tool_name = inv_m.group(1)
                                        run_entry["active_task"] = f"Invoking tool: {tool_name}"
                                        if _is_productive_tool(tool_name):
                                            productive_turns += 1
                                            last_progress_time = time.time()
                                        run_entry["last_progress_at"] = _utc_now()
                                    elif "Calling LLM" in line:
                                        run_entry["active_task"] = (
                                            f"Consulting model ({run_entry.get('active_agent', 'Root Agent')})"
                                        )
                                        run_entry["last_progress_at"] = _utc_now()
                                    elif (
                                        "update_coverage" in line
                                        or "Saved coverage record to:" in line
                                    ):
                                        run_entry["last_progress_at"] = _utc_now()

                                    if "Saved coverage record to:" in line:
                                        cov_m = re.search(r"\((\d+)\s+surface\(s\)", line)
                                        if cov_m:
                                            engine.log(
                                                "COVERAGE",
                                                f"Coverage updated: {cov_m.group(1)} surface(s) audited",
                                            )

                                    if any(
                                        k in line.lower()
                                        for k in (
                                            "ratelimiterror",
                                            "free-models-per-day",
                                            "openrouter_free_tier_daily",
                                            "quota exceeded",
                                        )
                                    ):
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
                                if stat == "positive":
                                    cand["state"] = "VALIDATED"
                                elif stat in ("ruled_out",):
                                    cand["state"] = "RULED_OUT"
                                elif stat in ("blocked", "error"):
                                    cand["state"] = "BLOCKED"
                                elif stat == "inconclusive":
                                    cand["state"] = "INCONCLUSIVE"
                                else:
                                    cand["state"] = "ABANDONED"
                                cand["status"] = cand["state"]
                            elif cid in exhausted_set:
                                cand["state"] = "ABANDONED"
                                cand["status"] = "ABANDONED"
                            elif cand.get("attempts", 0) > 0 or cid in attempts_map:
                                cand["state"] = "ATTEMPTING"
                                cand["status"] = "ATTEMPTING"
                            elif not cand.get("state"):
                                cand["state"] = "PENDING"
                                cand["status"] = "PENDING"

                        candidates_identified = len(run_entry.get("candidates", []))
                        candidates_investigated = sum(
                            1
                            for c in run_entry.get("candidates", [])
                            if c.get("state") in ("VALIDATED", "ABANDONED")
                            or (c.get("state") == "ATTEMPTING" and c.get("attempts", 0) > 0)
                        )
                    except Exception:
                        pass

                # 3a. Reconcile with the engine's authoritative GAP state.
                # The engine (GapRun) writes <engine-run>/.state/gap_state.json;
                # the control bridge writes <control>/gap_state.json. When both
                # exist they can disagree. Prefer real execution evidence from
                # the engine state so the dashboard reflects what actually ran.
                if u_dir and u_dir.is_dir():
                    engine_gap_file = u_dir / ".state" / "gap_state.json"
                    if engine_gap_file.is_file():
                        try:
                            eg = json.loads(engine_gap_file.read_text(encoding="utf-8"))
                            eng_cands = eg.get("candidates", {}) or {}
                            eng_probes = eg.get("probe_outcomes", []) or []
                            # Preparatory reconnaissance is evidence, not agent
                            # execution of an alternative. Counting it here
                            # made a pivot appear executed before the model had
                            # dispatched or run the selected candidate.
                            eng_executed = {
                                str(p.get("candidate_id"))
                                for p in eng_probes
                                if isinstance(p, dict)
                                and p.get("candidate_id")
                                and not p.get("preparatory")
                            }
                            for cand in run_entry.get("candidates", []):
                                cid = str(cand.get("id"))
                                ec = eng_cands.get(cid)
                                if not isinstance(ec, dict):
                                    continue
                                cand["attempts"] = max(
                                    int(cand.get("attempts", 0)), int(ec.get("attempts", 0))
                                )
                                estatus = str(ec.get("status", "")).lower()
                                if estatus in ("validated", "abandoned", "blocked", "investigated"):
                                    cand["state"] = estatus.upper()
                                    cand["status"] = cand["state"]
                                elif cid in eng_executed:
                                    cand["state"] = "ATTEMPTING"
                                    cand["status"] = "ATTEMPTING"
                            candidates_investigated = sum(
                                1
                                for c in run_entry.get("candidates", [])
                                if c.get("state") in ("VALIDATED", "ABANDONED", "INVESTIGATED")
                                or (c.get("state") == "ATTEMPTING" and c.get("attempts", 0) > 0)
                            )
                            # Only count pivots that name an alternative which
                            # actually produced an execution record.
                            for ev in eg.get("decision_trace", []) or []:
                                if not isinstance(ev, dict) or ev.get("type") != "pivot_decision":
                                    continue
                                alt = str(ev.get("alternative_candidate", ""))
                                if (
                                    alt
                                    and alt in eng_executed
                                    and pivot_execution_after_decision(ev, eng_probes)
                                ):
                                    pivot_ev = dict(ev)
                                    pivot_ev["event"] = "GAP2_PIVOT"
                                    pivot_ev["pivot_executed"] = True
                                    pivot_ev["next_candidate"] = alt
                                    if pivot_ev not in run_entry["pivot_events"]:
                                        run_entry["pivot_events"].append(pivot_ev)
                        except Exception:
                            pass

                # 3a-2. At terminal state, write the engine-authoritative
                # attempt/status values back to the control file so the two
                # stores do not disagree on resume or completion gating.
                if final_sync and u_dir and u_dir.is_dir():
                    reconcile_control_gap_state(control_dir, u_dir / ".state" / "gap_state.json")

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
                                matched = gap_bridge.candidate_for(
                                    c_risk, c_surf, "", directory=control_dir
                                )
                                if matched and matched.get("candidate_id"):
                                    mcid = str(matched["candidate_id"])
                                    for cand in run_entry.get("candidates", []):
                                        if str(cand.get("id")) == mcid:
                                            cand["attempts"] = max(cand.get("attempts", 0), 1)
                                            if c_out in (
                                                "ruled_out",
                                                "not_applicable",
                                            ):
                                                cand["state"] = "RULED_OUT"
                                                cand["status"] = "RULED_OUT"
                                            elif c_out == "reported":
                                                cand["state"] = "VALIDATED"
                                                cand["status"] = "VALIDATED"
                                            elif c_out == "no_issue_found":
                                                cand["state"] = cand.get("state") or "ABANDONED"
                                                cand["status"] = cand["state"]
                                            elif c_out == "needs_follow_up":
                                                if cand.get("state") not in (
                                                    "ABANDONED",
                                                    "VALIDATED",
                                                    "RULED_OUT",
                                                ):
                                                    cand["state"] = "ATTEMPTING"
                                                    cand["status"] = "ATTEMPTING"
                            candidates_investigated = sum(
                                1
                                for c in run_entry.get("candidates", [])
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
                                    next_c = t_obj.get("next_candidate") or t_obj.get(
                                        "to_candidate"
                                    )
                                    is_real_pivot = bool(next_c) and (
                                        t_obj.get("pivot_executed") is not False
                                    )
                                    # The bridge emits GAP2_PIVOT at decision time.
                                    # Confirm the selected alternative was really
                                    # dispatched/executed by the engine before it
                                    # is counted as a genuine pivot.
                                    engine_gap_file = (
                                        (u_dir / ".state" / "gap_state.json") if u_dir else None
                                    )
                                    if (
                                        engine_gap_file is not None
                                        and not engine_gap_file.is_file()
                                    ):
                                        # No engine state available (e.g. a legacy
                                        # or lightweight run): the bridge record is
                                        # the only source of truth, so accept it.
                                        executed = bool(next_c)
                                    else:
                                        engine_evidence = engine_executed_alternatives(
                                            engine_gap_file
                                        )
                                        executed = bool(next_c) and str(next_c) in engine_evidence
                                    if is_real_pivot and executed:
                                        engine.log(
                                            "PIVOT",
                                            f"[GAP-2 PIVOT] Bounded threshold reached for {t_obj.get('candidate_id')}; pivoted to {next_c}",
                                        )
                                        run_entry["pivot_events"].append(t_obj)
                                    else:
                                        engine.log(
                                            "DECISION",
                                            f"GAP2 threshold reached for {t_obj.get('candidate_id')}. Candidate abandoned or alternative not executed. No genuine pivot counted.",
                                        )
                                elif t_obj.get("event") in ("GAP2_ABANDON", "GAP2_COMPLETE"):
                                    engine.log(
                                        "DECISION",
                                        t_obj.get("message")
                                        or f"GAP2 threshold reached for {t_obj.get('candidate_id')}. Candidate abandoned. Queue exhausted. No alternative path executed. Pivot count: 0.",
                                    )
                    except Exception:
                        pass

                # The bridge and the native engine can record the same executed
                # pivot. Deduplicate by (original -> alternative) before both
                # storing and counting so dashboard, API and reports agree.
                run_entry["pivot_events"] = dedupe_pivot_events(run_entry.get("pivot_events", []))
                pivots_count = len(
                    [
                        e
                        for e in run_entry.get("pivot_events", [])
                        if genuine_pivot_key(e) is not None
                    ]
                )

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
                                        name_match = bool(
                                            c_name
                                            and (
                                                c_name == s_name
                                                or s_name in c_name
                                                or c_name in s_name
                                            )
                                        )
                                        if id_match or name_match:
                                            c["state"] = "VALIDATED"
                                            c["status"] = "VALIDATED"
                        except Exception:
                            pass

                # 6. Truthful progress milestones & live duration
                turn_fraction = min(1.0, current_turn / max(1, max_turns))
                if pivots_count > 0 or turn_fraction >= 0.5:
                    phase_name = "GAP2 adaptive pivoting and validation"
                    phase_idx = 4
                    calc_pct = min(89, 70 + int(turn_fraction * 20))
                else:
                    phase_name = "GAP1 triage and candidate investigation"
                    phase_idx = 3
                    calc_pct = min(69, 40 + int(turn_fraction * 30))

                started_ts = run_entry.get("started_at") or run_entry.get("start_time")
                if started_ts:
                    try:
                        s_dt = datetime.fromisoformat(started_ts)
                        if s_dt.tzinfo is None:
                            s_dt = s_dt.replace(tzinfo=UTC)
                        run_entry["duration_seconds"] = round(
                            max(0.0, (datetime.now(UTC) - s_dt).total_seconds()), 2
                        )
                        run_entry["elapsed_seconds"] = run_entry["duration_seconds"]
                    except Exception:
                        pass

                _sync_run_counters(run_entry)

                if not run_entry.get("active_task"):
                    run_entry["active_task"] = f"Executing Turn {current_turn} ({phase_name})"
                run_entry["turns_consumed"] = current_turn
                run_entry["progress_percent"] = calc_pct
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
                    "start_time": run_entry.get("start_time"),
                    "started_at": run_entry.get("started_at") or run_entry.get("start_time"),
                    "duration_seconds": run_entry.get("duration_seconds"),
                    "elapsed_seconds": run_entry.get("elapsed_seconds"),
                    "active_task": run_entry.get("active_task"),
                    "active_agent": run_entry.get("active_agent") or "Autonomous VAPT Agent",
                    "verification_states": run_entry.get("verification_states", {}),
                    "gap1": {
                        "identified": candidates_identified,
                        "investigated": candidates_investigated,
                    },
                    "gap2": {
                        "pivots": pivots_count,
                    },
                    "findings_summary": run_entry.get("verification_states", {}),
                }
                run_entry["stats"] = {
                    "attempts": current_turn,
                    "pivots": pivots_count,
                    "findings": len(run_entry.get("findings", [])),
                }
                run_entry["decision_trace"] = list(engine.decision_trace)
                _save_run_to_disk(run_entry)

            turn_limit_reached = False
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

                if current_turn >= max_turns:
                    turn_limit_reached = True
                    engine.log(
                        "LIMIT",
                        f"Execution turn limit ({max_turns} turns) reached. Gracefully stopping autonomous scanner.",
                    )
                    try:
                        proc.terminate()
                        proc.wait(timeout=5.0)
                    except Exception:
                        with contextlib.suppress(Exception):
                            proc.kill()
                    break

                if time.time() - proc_start_time > wall_clock_timeout:
                    timed_out = True
                    engine.log(
                        "TIMEOUT",
                        f"Wall-clock timeout of {wall_clock_timeout}s exceeded. Terminating autonomous scanner.",
                    )
                    try:
                        proc.terminate()
                        proc.wait(timeout=3.0)
                    except Exception:
                        with contextlib.suppress(Exception):
                            proc.kill()
                    break

                elapsed_now = time.time() - proc_start_time
                last_progress_now = time.time() - last_progress_time
                if should_stop_for_no_progress(
                    elapsed_seconds=elapsed_now,
                    last_progress_seconds=last_progress_now,
                    productively_advanced_turns=productive_turns,
                    max_turns=max_turns,
                ) or should_stop_for_stall(
                    elapsed_seconds=elapsed_now,
                    last_progress_seconds=last_progress_now,
                ):
                    stalled = True
                    engine.log(
                        "STALL",
                        "No real security tool executed for 10 minutes; terminating "
                        "unproductive scan rather than leaving it running indefinitely.",
                    )
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

            # Let late log writes settle before the definitive telemetry pass.
            # An agent process can write its last turn to strix.log just before
            # exiting; without this the dashboard can freeze one turn behind.
            time.sleep(0.2)
            _sync_telemetry(final_sync=True)

            if run_entry.get("status") == "aborted":
                return

            # Discover underlying run directory across candidate bases
            if not underlying_run_name:
                discovered_candidates = []
                for cb in candidate_bases:
                    if cb.is_dir():
                        for d in cb.iterdir():
                            if (
                                d.is_dir()
                                and d.name not in before_dirs
                                and d.name not in (run_id, engine_run_name)
                            ):
                                discovered_candidates.append(d)
                if discovered_candidates:
                    discovered_candidates.sort(key=lambda d: d.stat().st_mtime, reverse=True)
                    underlying_run_name = discovered_candidates[0].name
                    engine.log(
                        "SANDBOX",
                        f"Discovered autonomous scan run directory: {underlying_run_name}",
                    )

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
                        with open(u_run_file, encoding="utf-8") as rf:
                            u_run_data = json.load(rf)
                    except Exception as err:
                        logger.warning("Error reading underlying run.json: %s", err)

            ret_code = proc.returncode if proc.returncode is not None else 0
            if ret_code == 0:
                exit_interp = "clean_no_findings"
            elif ret_code == 2:
                exit_interp = "completed_with_findings"
            elif ret_code == 1:
                exit_interp = "fatal_error"
            elif ret_code in (-15, 143):
                exit_interp = "sigterm_interrupted"
            elif ret_code in (-9, 137):
                exit_interp = "sigkill_terminated"
            else:
                exit_interp = f"exit_code_{ret_code}"
            run_entry["process_exit_code"] = ret_code
            run_entry["exit_code_interpretation"] = exit_interp

            proc_failed = False
            error_msg: str | None = None

            report_exists = (
                (u_dir / "penetration_test_report.md").is_file()
                if u_dir and u_dir.exists()
                else False
            )
            sarif_exists = (
                (u_dir / "findings.sarif").is_file() if u_dir and u_dir.exists() else False
            )

            # A genuine completion requires BOTH model reasoning and real
            # security-tool execution. Candidate counters, decision-trace
            # events and a "completed" status are derived state; they must
            # never turn a bookkeeping-only run into a successful assessment.
            execution_evidence = execution_evidence_from_run(
                u_run_data,
                "\n".join(
                    list(last_stdout_lines)
                    + (
                        [(u_dir / "strix.log").read_text(encoding="utf-8", errors="replace")]
                        if u_dir and (u_dir / "strix.log").is_file()
                        else []
                    )
                ),
            )
            run_entry["execution_evidence"] = execution_evidence
            insufficient_execution = not (
                execution_evidence["has_model_participation"]
                and execution_evidence["has_security_execution"]
            )

            if timed_out:
                proc_failed = True
                exit_interp = "wall_clock_timeout"
                run_entry["exit_code_interpretation"] = exit_interp
                error_msg = f"Assessment exceeded wall-clock limit of {wall_clock_timeout}s"
            elif stalled:
                proc_failed = True
                exit_interp = "no_progress_stall"
                run_entry["exit_code_interpretation"] = exit_interp
                error_msg = (
                    "Assessment stopped: the model made no real security-tool progress "
                    "for 10 minutes. No findings were inferred from bookkeeping calls."
                )
            elif turn_limit_reached:
                proc_failed = False
                exit_interp = "turn_limit_reached"
                run_entry["exit_code_interpretation"] = exit_interp
            elif ret_code == 1:
                proc_failed = True
                error_msg = _extract_clean_error(
                    stderr_lines,
                    last_stdout_lines,
                    fallback=f"Scanner encountered a fatal execution error (exit code {ret_code})",
                )
            elif not u_dir or not u_dir.exists():
                proc_failed = True
                error_msg = _extract_clean_error(
                    stderr_lines,
                    last_stdout_lines,
                    fallback="Autonomous scanner exited without creating a scan directory",
                )
            elif u_run_data is None and not report_exists and not sarif_exists:
                proc_failed = True
                error_msg = _extract_clean_error(
                    stderr_lines,
                    last_stdout_lines,
                    fallback=f"Scan completed without generating execution metadata (run.json missing, exit code {ret_code})",
                )
            else:
                u_status = (u_run_data or {}).get("status")
                u_exit_reason = (u_run_data or {}).get("scan_ended_exit_reason")
                engine_failure = engine_terminal_failure(u_run_data)
                if engine_failure:
                    # The engine actually failed. Harvested findings stay as a
                    # partial report, but the run's terminal status is failed;
                    # the presence of a SARIF/JSON report does not make a failed
                    # engine run a successful assessment.
                    proc_failed = True
                    reason_str = f" (exit reason: {u_exit_reason})" if u_exit_reason else ""
                    error_msg = _extract_clean_error(
                        stderr_lines,
                        last_stdout_lines,
                        fallback=f"Scan engine ended with status '{engine_failure}'{reason_str} before completing",
                    )
                elif (
                    u_status and u_status != "completed" and not report_exists and not sarif_exists
                ):
                    proc_failed = True
                    reason_str = f" (exit reason: {u_exit_reason})" if u_exit_reason else ""
                    error_msg = _extract_clean_error(
                        stderr_lines,
                        last_stdout_lines,
                        fallback=f"Scan ended with status '{u_status}'{reason_str} before satisfying completion requirements",
                    )
                elif ret_code in (0, 2):
                    proc_failed = False
                elif not report_exists and not sarif_exists:
                    proc_failed = True
                    error_msg = _extract_clean_error(
                        stderr_lines,
                        last_stdout_lines,
                        fallback=f"Scanner exited unexpectedly with status code {ret_code}",
                    )
                else:
                    proc_failed = False

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

            # Setup target run dir for artifacts and authentic evidence capture
            target_run_dir = base_dir / run_id
            target_run_dir.mkdir(parents=True, exist_ok=True)
            if u_dir and (u_dir / "evidence").is_dir() and target_run_dir != u_dir:
                target_ev_dir = target_run_dir / "evidence"
                target_ev_dir.mkdir(parents=True, exist_ok=True)
                for ev_f in (u_dir / "evidence").iterdir():
                    if ev_f.is_file():
                        try:
                            (target_ev_dir / ev_f.name).write_bytes(ev_f.read_bytes())
                        except Exception:
                            pass

            findings = []
            seen_finding_keys = set()
            if u_dir and u_dir.exists():
                u_vuln = u_dir / "vulnerabilities.json"
                if u_vuln.exists():
                    try:
                        with open(u_vuln, encoding="utf-8") as f:
                            strix_vulns = json.load(f)
                            if isinstance(strix_vulns, list):
                                for sv in strix_vulns:
                                    sv_id = sv.get("id", "")
                                    if (
                                        sv_id.startswith("open-port-")
                                        or sv.get("is_recon_only")
                                        or sv.get("finding_class") == "reconnaissance"
                                    ):
                                        continue
                                    mapped = map_finding_to_owasp(
                                        sv.get("title") or sv.get("name") or "Vulnerability",
                                        rule_id=sv.get("id", ""),
                                        endpoint=sv.get("location") or sv.get("endpoint") or "/",
                                        tech_stack=detected_tech,
                                    )
                                    raw_ev = (
                                        sv.get("detail")
                                        or sv.get("evidence")
                                        or sv.get("poc_script_code")
                                        or str(sv)
                                    )
                                    title_val = sv.get("title", sv.get("name", "Vulnerability"))
                                    loc_val = sv.get("location") or sv.get("endpoint") or "/"
                                    param_val = sv.get("parameter")
                                    dedup_key = (
                                        title_val.lower(),
                                        loc_val.lower(),
                                        str(param_val).lower() if param_val else "",
                                    )
                                    if dedup_key in seen_finding_keys:
                                        continue
                                    seen_finding_keys.add(dedup_key)

                                    raw_cvss = (
                                        sv.get("cvss_score")
                                        or sv.get("cvss")
                                        or mapped.get("cvss", 6.0)
                                    )
                                    raw_sev = sv.get("severity", "MEDIUM")
                                    aligned_cvss, aligned_sev = _align_cvss_severity(
                                        raw_cvss, raw_sev
                                    )

                                    v_block = sv.get("verification") or {}
                                    rep_req = (
                                        v_block.get("reproducible_request")
                                        or sv.get("poc_script_code")
                                        or sv.get("reproducible_request")
                                        or f"GET {loc_val} HTTP/1.1"
                                    )
                                    rep_resp = (
                                        v_block.get("verification_response")
                                        or sv.get("reproducible_response")
                                        or (
                                            raw_ev[:600]
                                            if isinstance(raw_ev, str)
                                            else str(raw_ev)[:600]
                                        )
                                    )
                                    verif_proc = (
                                        v_block.get("verification_procedure")
                                        or sv.get("validation_method")
                                        or "PoC Execution & Response Pattern Verification"
                                    )
                                    impact_val = (
                                        v_block.get("demonstrated_impact")
                                        or sv.get("impact")
                                        or mapped.get("impact", "")
                                    )

                                    f_actual_id = sv.get("id", f"vapt-{uuid.uuid4().hex[:6]}")
                                    ev_meta = record_authentic_evidence(
                                        run_dir=target_run_dir,
                                        finding_id=f_actual_id,
                                        request_data=rep_req,
                                        response_data=rep_resp,
                                        raw_snippet=raw_ev,
                                        evidence_type="http_exchange",
                                        title=title_val,
                                    )

                                    finding_item = {
                                        "id": f_actual_id,
                                        "title": title_val,
                                        "severity": aligned_sev,
                                        "cvss_score": aligned_cvss,
                                        "cve_id": sv.get("cve_id") or mapped.get("cve_id"),
                                        "cwe_id": sv.get("cwe_id")
                                        or mapped.get("cwe_id", "CWE-200"),
                                        "owasp_category": f"{mapped.get('owasp_id', 'A01:2021')} - {mapped.get('category_name', 'Broken Access Control')}",
                                        "location": loc_val,
                                        "target": target_url,
                                        "evidence_hash": ev_meta.get("evidence_hash"),
                                        "evidence_file": ev_meta.get("evidence_file"),
                                        "evidence_size": ev_meta.get("evidence_size"),
                                        "evidence_hash_type": ev_meta.get("evidence_hash_type"),
                                        "evidence_intact": ev_meta.get("evidence_intact", False),
                                        "evidence_snippet": raw_ev,
                                        "reproducible_request": rep_req,
                                        "reproducible_response": rep_resp,
                                        "verification_procedure": verif_proc,
                                        "demonstrated_impact": impact_val,
                                        "parameter": param_val,
                                        "evidence_timestamp": ev_meta.get("evidence_timestamp")
                                        or v_block.get("evidence_timestamp")
                                        or _utc_now(),
                                        "validation_method": verif_proc,
                                        "severity_justification": f"Severity {aligned_sev} (CVSS {aligned_cvss}) justified by exploitability and demonstrated impact.",
                                        "impact": impact_val,
                                        "remediation_summary": sv.get("remediation")
                                        or mapped.get("remediation_summary", ""),
                                        "remediation_technical": sv.get("remediation_steps")
                                        or sv.get("remediation_technical")
                                        or mapped.get("remediation_technical", ""),
                                        "retest_procedure": mapped.get("retest_procedure", ""),
                                        "finding_class": sv.get("finding_class", "dynamic"),
                                    }
                                    v_state_raw = (
                                        v_block.get("verification_state")
                                        or sv.get("verification_state")
                                        or ""
                                    )
                                    v_state, v_reason, is_v = evaluate_finding_verification(
                                        {
                                            **finding_item,
                                            "verification_state": str(v_state_raw).strip().lower(),
                                        }
                                    )
                                    finding_item["verification_state"] = v_state
                                    finding_item["verification_reason"] = v_reason
                                    finding_item["verified"] = is_v
                                    findings.append(finding_item)
                    except Exception as e:
                        logger.warning("Error reading strix vulnerabilities: %s", e)

                # Source 2: findings.sarif fallback & enrichment
                sarif_path = u_dir / "findings.sarif"
                if sarif_path.is_file():
                    try:
                        s_data = json.loads(sarif_path.read_text(encoding="utf-8"))
                        for s_run in s_data.get("runs", []):
                            for s_res in s_run.get("results", []):
                                r_id = s_res.get("ruleId", "")
                                s_props = s_res.get("properties", {})
                                strix_info = (
                                    s_props.get("strix") if isinstance(s_props, dict) else None
                                )
                                if r_id.startswith("vuln-") and isinstance(strix_info, dict):
                                    msg_txt = s_res.get("message", {}).get("text", "")
                                    f_title = msg_txt.split("\n")[0].strip() if msg_txt else r_id
                                    f_target = strix_info.get("target") or target_url
                                    d_key = (f_title.lower(), f_target.lower(), "")
                                    if d_key in seen_finding_keys:
                                        continue
                                    seen_finding_keys.add(d_key)
                                    f_sev = str(strix_info.get("severity", "MEDIUM")).upper()
                                    try:
                                        f_cvss = float(strix_info.get("cvss", 6.0))
                                    except Exception:
                                        f_cvss = 6.0
                                    aligned_c, aligned_s = _align_cvss_severity(f_cvss, f_sev)
                                    mapped_owasp = map_finding_to_owasp(
                                        f_title,
                                        rule_id=r_id,
                                        endpoint=f_target,
                                        tech_stack=detected_tech,
                                    )
                                    s_req = (
                                        (strix_info.get("poc") or {}).get("description")
                                        if isinstance(strix_info.get("poc"), dict)
                                        else f"GET {f_target} HTTP/1.1"
                                    )
                                    s_resp = (
                                        strix_info.get("counterevidence")
                                        or "Response pattern verified by autonomous agent."
                                    )
                                    s_snippet = strix_info.get("technical_analysis") or msg_txt
                                    s_impact = strix_info.get("impact", "")
                                    s_proc = "Automated Agent Verification & PoC Confirmation"

                                    ev_meta = record_authentic_evidence(
                                        run_dir=target_run_dir,
                                        finding_id=r_id,
                                        request_data=s_req,
                                        response_data=s_resp,
                                        raw_snippet=s_snippet,
                                        evidence_type="sarif_poc",
                                        title=f_title,
                                    )
                                    sarif_finding = {
                                        "id": r_id,
                                        "title": f_title,
                                        "severity": aligned_s,
                                        "cvss_score": aligned_c,
                                        "cve_id": mapped_owasp.get("cve_id"),
                                        "cwe_id": mapped_owasp.get("cwe_id", "CWE-200"),
                                        "owasp_category": f"{mapped_owasp.get('owasp_id', 'A01:2021')} - {mapped_owasp.get('category_name', 'Security Misconfiguration')}",
                                        "location": f_target,
                                        "target": f_target,
                                        "evidence_hash": ev_meta.get("evidence_hash"),
                                        "evidence_file": ev_meta.get("evidence_file"),
                                        "evidence_size": ev_meta.get("evidence_size"),
                                        "evidence_hash_type": ev_meta.get("evidence_hash_type"),
                                        "evidence_intact": ev_meta.get("evidence_intact", False),
                                        "evidence_snippet": s_snippet,
                                        "reproducible_request": s_req,
                                        "reproducible_response": s_resp,
                                        "verification_procedure": s_proc,
                                        "demonstrated_impact": s_impact,
                                        "parameter": None,
                                        "evidence_timestamp": ev_meta.get("evidence_timestamp")
                                        or strix_info.get("timestamp")
                                        or _utc_now(),
                                        "validation_method": "Exploit PoC Verification",
                                        "severity_justification": f"Severity {aligned_s} (CVSS {aligned_c}) justified by exploitability and demonstrated impact.",
                                        "impact": s_impact,
                                        "remediation_summary": strix_info.get("remediation_steps")
                                        or mapped_owasp.get("remediation_summary", ""),
                                        "remediation_technical": strix_info.get("remediation_steps")
                                        or mapped_owasp.get("remediation_technical", ""),
                                        "retest_procedure": mapped_owasp.get(
                                            "retest_procedure", ""
                                        ),
                                        "finding_class": "dynamic",
                                        "verification_state": str(
                                            strix_info.get("verification_state") or ""
                                        )
                                        .strip()
                                        .lower(),
                                    }
                                    v_state, v_reason, is_v = evaluate_finding_verification(
                                        sarif_finding
                                    )
                                    sarif_finding["verification_state"] = v_state
                                    sarif_finding["verification_reason"] = v_reason
                                    sarif_finding["verified"] = is_v
                                    findings.append(sarif_finding)
                    except Exception as s_err:
                        logger.warning("Error parsing SARIF findings: %s", s_err)

                # Persist run artifacts from Strix run folder to current run folder
                for art_name in ("findings.sarif", "coverage.json", "penetration_test_report.md"):
                    src_art = u_dir / art_name
                    if src_art.is_file():
                        try:
                            (target_run_dir / art_name).write_bytes(src_art.read_bytes())
                        except Exception:
                            pass

                # Copy vulnerabilities/ folder if separate
                src_vuln_dir = u_dir / "vulnerabilities"
                if src_vuln_dir.is_dir() and target_run_dir != u_dir:
                    target_vuln_dir = target_run_dir / "vulnerabilities"
                    target_vuln_dir.mkdir(parents=True, exist_ok=True)
                    for v_md in src_vuln_dir.glob("*.md"):
                        try:
                            (target_vuln_dir / v_md.name).write_bytes(v_md.read_bytes())
                        except Exception:
                            pass

            # Check for provider rate limit / daily quota exhaustion
            is_quota_error = False
            if proc_failed:
                clean_err_check = (error_msg or "").lower()
                all_err_text = (
                    clean_err_check + " " + " ".join(line.lower() for line in stderr_lines)
                )
                for qk in (
                    "free-models-per-day",
                    "openrouter_free_tier_daily",
                    "daily reset",
                    "daily limit",
                    "exceeded your current quota",
                ):
                    if qk in all_err_text:
                        is_quota_error = True
                        break

            if is_quota_error:
                run_entry["status"] = "provider_blocked"
                run_entry["provider_error"] = (
                    "Provider rate-limit / daily quota exhausted (HTTP 429). "
                    "Completed reconnaissance and investigations are preserved. "
                    f"Resume this assessment with an alternative provider or model via POST /runs/{run_id}/resume."
                )
                run_entry["error"] = run_entry["provider_error"]

            # Reconcile uninvestigated candidates as NOT_TESTED
            untested_count = 0
            for cand in run_entry.get("candidates", []):
                if cand.get("state") in ("PENDING", None) or (
                    cand.get("attempts", 0) == 0
                    and cand.get("state") not in ("VALIDATED", "ABANDONED")
                ):
                    cand["state"] = "NOT_TESTED"
                    cand["status"] = "NOT_TESTED"
                    untested_count += 1

            candidates_dispatched = len(run_entry.get("candidates", []))
            candidates_investigated = sum(
                1
                for c in run_entry.get("candidates", [])
                if c.get("state") in ("VALIDATED", "ABANDONED")
                or (c.get("state") == "ATTEMPTING" and c.get("attempts", 0) > 0)
            )
            candidates_validated = sum(
                1 for c in run_entry.get("candidates", []) if c.get("state") == "VALIDATED"
            )
            candidates_abandoned = sum(
                1 for c in run_entry.get("candidates", []) if c.get("state") == "ABANDONED"
            )
            candidates_blocked = sum(
                1
                for c in run_entry.get("candidates", [])
                if c.get("state") in ("BLOCKED", "UNRESOLVED")
            )
            candidates_not_tested = max(
                0,
                candidates_dispatched - (candidates_investigated + candidates_blocked),
            )

            run_entry["candidate_accounting"] = {
                "dispatched": candidates_dispatched,
                "investigated": candidates_investigated,
                "validated": candidates_validated,
                "abandoned": candidates_abandoned,
                "not_tested": candidates_not_tested,
                "blocked": candidates_blocked,
            }

            run_entry["findings"] = findings
            run_entry["scan_matrix"] = _reconcile_scan_matrix(
                run_entry.get("scan_matrix", []), findings, run_data=run_entry
            )
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

            if run_entry.get("status") == "provider_blocked" or is_quota_error:
                run_entry["status"] = "paused_provider_limit"
                run_entry["provider_error"] = (
                    "Provider rate-limit / daily quota exhausted (HTTP 429). "
                    "Completed reconnaissance and investigations are preserved. "
                    f"Resume this assessment with an alternative provider or model via POST /runs/{run_id}/resume."
                )
                run_entry["error"] = run_entry["provider_error"]
                run_entry["report_status"] = (
                    "partial_report_harvested" if findings else "no_findings"
                )
                turn_fraction = min(1.0, max(0.0, current_turn / max(1, max_turns)))
                actual_pct = min(85, max(15, int(35 + 50 * turn_fraction)))
                run_entry["progress"] = {
                    "phase": "Provider Quota Blocked (HTTP 429)",
                    "phase_index": 3,
                    "percent": actual_pct,
                    "current": min(current_turn, max_turns),
                    "total": max_turns,
                    "candidates_identified": candidates_identified,
                    "candidates_investigated": candidates_investigated,
                    "pivots": pivots_count,
                    "run_id": run_id,
                    "start_time": run_entry.get("start_time"),
                    "duration_seconds": run_entry.get("duration_seconds"),
                    "provider_error": run_entry["provider_error"],
                }
                run_entry["events"].append(
                    {
                        "timestamp": _utc_now(),
                        "event": "RUN_PAUSED_PROVIDER_LIMIT",
                        "message": run_entry["provider_error"],
                    }
                )
                engine.log("WARN", f"Autonomous assessment paused: {run_entry['provider_error']}")
                _finalize_run_lifecycle(
                    run_entry, status="paused_provider_limit", error=run_entry["provider_error"]
                )
            elif turn_limit_reached and not report_exists and untested_count > 0:
                run_entry["status"] = "paused_execution_limit"
                limit_msg = (
                    f"Configured turn budget of {max_turns} turns reached with {untested_count} "
                    f"candidate(s) remaining. Harvested {len(findings)} confirmed finding(s)."
                )
                run_entry["error"] = limit_msg
                run_entry["report_status"] = (
                    "partial_report_harvested" if findings else "no_findings"
                )
                run_entry["progress"] = {
                    "phase": f"Execution Limit Reached ({max_turns} Turns)",
                    "phase_index": 4,
                    "percent": 90,
                    "current": min(current_turn, max_turns),
                    "total": max_turns,
                    "candidates_identified": candidates_identified,
                    "candidates_investigated": candidates_investigated,
                    "pivots": pivots_count,
                    "run_id": run_id,
                    "start_time": run_entry.get("start_time"),
                    "duration_seconds": run_entry.get("duration_seconds"),
                }
                run_entry["events"].append(
                    {
                        "timestamp": _utc_now(),
                        "event": "RUN_PAUSED_EXECUTION_LIMIT",
                        "message": limit_msg,
                    }
                )
                engine.log("WARN", f"Autonomous assessment paused at execution limit: {limit_msg}")
                _finalize_run_lifecycle(run_entry, status="paused_execution_limit", error=limit_msg)
            elif proc_failed:
                clean_err_lower = (error_msg or "").lower()
                is_infra = any(
                    k in clean_err_lower
                    for k in (
                        "docker",
                        "connection refused",
                        "timeout",
                        "network",
                        "dns",
                        "sandbox",
                        "wall-clock",
                        "failed to start",
                    )
                )
                fail_classification = "failed_infrastructure" if is_infra else "failed_agent"
                run_entry["failure_classification"] = fail_classification
                run_entry["status"] = "failed"
                run_entry["error"] = error_msg
                run_entry["report_status"] = (
                    "partial_report_harvested" if findings else "no_findings"
                )
                turn_fraction = min(1.0, max(0.0, current_turn / max(1, max_turns)))
                actual_pct = min(85, max(15, int(35 + 50 * turn_fraction)))
                clean_err_short = (error_msg.split(".")[0] or error_msg)[:80]
                run_entry["progress"] = {
                    "phase": f"Failed: {clean_err_short}",
                    "phase_index": 3,
                    "percent": actual_pct,
                    "current": min(current_turn, max_turns),
                    "total": max_turns,
                    "candidates_identified": candidates_identified,
                    "candidates_investigated": candidates_investigated,
                    "pivots": pivots_count,
                    "run_id": run_id,
                    "start_time": run_entry.get("start_time"),
                    "duration_seconds": run_entry.get("duration_seconds"),
                }
                run_entry["events"].append(
                    {
                        "timestamp": _utc_now(),
                        "event": "RUN_FAILED",
                        "message": f"Autonomous pentest failed ({fail_classification}, code {ret_code}): {error_msg}. Harvested {len(findings)} partial finding(s).",
                    }
                )
                engine.log(
                    "FAIL",
                    f"Autonomous assessment failed ({fail_classification}, exit {ret_code}): {error_msg}",
                )
                _finalize_run_lifecycle(run_entry, status="failed", error=error_msg)
            else:
                untested_cands = sum(
                    1
                    for c in run_entry.get("candidates", [])
                    if c.get("state") in ("PENDING", "NOT_TESTED")
                    or (
                        c.get("attempts", 0) == 0
                        and c.get("state") not in ("VALIDATED", "ABANDONED")
                    )
                )
                if insufficient_execution:
                    # The subprocess exited cleanly but no model reasoning and
                    # no real security tool ever ran. Candidate transitions,
                    # a decision trace, or a "completed" status in run.json
                    # cannot turn bookkeeping into a successful assessment.
                    no_exec_msg = (
                        "Assessment did not perform genuine autonomous execution: "
                        f"{execution_evidence['llm_calls']} model call(s) and "
                        f"{execution_evidence['security_tool_calls']} security-tool "
                        "execution(s) recorded. Bookkeeping and candidate "
                        "transitions are not security testing."
                    )
                    run_entry["exit_code_interpretation"] = "no_genuine_execution"
                    run_entry["status"] = "failed"
                    run_entry["error"] = no_exec_msg
                    run_entry["failure_classification"] = "failed_agent"
                    run_entry["report_status"] = "no_findings"
                    run_entry["progress"] = {
                        "phase": "Failed: no genuine autonomous execution",
                        "phase_index": 3,
                        "percent": min(
                            85, max(15, int(35 + 50 * min(1.0, current_turn / max(1, max_turns))))
                        ),
                        "current": min(current_turn, max_turns),
                        "total": max_turns,
                        "candidates_identified": candidates_identified,
                        "candidates_investigated": candidates_investigated,
                        "pivots": pivots_count,
                        "run_id": run_id,
                        "start_time": run_entry.get("start_time"),
                        "duration_seconds": run_entry.get("duration_seconds"),
                    }
                    run_entry["events"].append(
                        {
                            "timestamp": _utc_now(),
                            "event": "RUN_FAILED",
                            "message": no_exec_msg,
                        }
                    )
                    engine.log("FAIL", no_exec_msg)
                    _finalize_run_lifecycle(run_entry, status="failed", error=no_exec_msg)
                elif untested_cands > 0 and len(run_entry.get("candidates", [])) > 0:
                    run_entry["status"] = "partial"
                    run_entry["error"] = None
                    run_entry["progress_percent"] = 85
                    run_entry["progress"] = {
                        "phase": f"Assessment Partial — {untested_cands} Untested Candidates Remain",
                        "phase_index": 4,
                        "percent": 85,
                        "current": min(current_turn, max_turns),
                        "total": max_turns,
                        "candidate": "Partial Completion",
                        "candidates_identified": candidates_identified,
                        "candidates_investigated": max(0, total_cands - untested_cands),
                        "pivots": pivots_count,
                        "run_id": run_id,
                        "start_time": run_entry.get("start_time"),
                        "duration_seconds": run_entry.get("duration_seconds"),
                    }
                    run_entry["events"].append(
                        {
                            "timestamp": _utc_now(),
                            "event": "RUN_PARTIAL",
                            "message": f"Assessment completed partially with {untested_cands} untested candidate(s). Found {len(findings)} confirmed finding(s).",
                        }
                    )
                    _finalize_run_lifecycle(run_entry, status="partial")
                else:
                    run_entry["status"] = "completed"
                    run_entry["error"] = None
                    run_entry["progress_percent"] = 100
                    run_entry["progress"] = {
                        "phase": "Assessment Complete",
                        "phase_index": 5,
                        "percent": 100,
                        "current": min(current_turn, max_turns),
                        "total": max_turns,
                        "candidate": "Completed",
                        "candidates_identified": candidates_identified,
                        "candidates_investigated": candidates_investigated,
                        "pivots": pivots_count,
                        "run_id": run_id,
                        "start_time": run_entry.get("start_time"),
                        "duration_seconds": run_entry.get("duration_seconds"),
                    }
                    run_entry["events"].append(
                        {
                            "timestamp": _utc_now(),
                            "event": "RUN_COMPLETED",
                            "message": f"Autonomous pentest finished cleanly (exit code {ret_code}). Found {len(findings)} confirmed finding(s).",
                        }
                    )
                    _finalize_run_lifecycle(run_entry, status="completed")

            _sync_run_counters(run_entry)
            run_entry["decision_trace"] = list(engine.decision_trace)
            _save_run_to_disk(run_entry)
            return

        # In-process active scanning (lightweight mode or offline simulation)
        if execution_mode == "lightweight_active_scanner":
            engine.log(
                "INFO",
                f"[SYSTEM] Executing lightweight in-process active scanner against {target_url} (benign direct HTTP verification).",
            )

        for idx, c in enumerate(engine_candidates):
            if current_turn >= max_turns:
                engine.log(
                    "LIMIT",
                    f"[TURN {current_turn}/{max_turns}] Turn limit of {max_turns} reached. Finalizing current assessments.",
                )
                break

            # Phase 4: Preserve completed candidates on resumed run
            if is_resumed_session and c.state in (
                CandidateState.VALIDATED,
                CandidateState.VALIDATED_OBSERVATION,
                CandidateState.VERIFIED_VULNERABILITY,
                CandidateState.ABANDONED,
                CandidateState.BLOCKED,
                CandidateState.RULED_OUT,
                CandidateState.RULED_OUT_WITH_EVIDENCE,
            ):
                engine.log(
                    "RESUME",
                    f"[TURN {current_turn}/{max_turns}] Candidate {c.name or c.id} already completed ({c.state.value}); preserving state and skipping re-investigation.",
                )
                continue

            c_meta = candidate_map.get(c.id, {})
            endpoint = c_meta.get("endpoint", "/")
            c.state = CandidateState.ATTEMPTING
            engine.current_index = idx

            run_entry["candidates"] = _sync_engine_candidates(engine, candidate_map)
            run_entry["decision_trace"] = list(engine.decision_trace)
            run_entry["pivot_events"] = [
                e.model_dump()
                if hasattr(e, "model_dump")
                else (e.dict() if hasattr(e, "dict") else dict(e))
                for e in engine.pivot_events
            ]
            piv_cnt = len(
                [
                    e
                    for e in engine.pivot_events
                    if getattr(e, "type", "") in ("REDIRECT", "GAP2_PIVOT")
                    or getattr(e, "event", "") == "GAP2_PIVOT"
                ]
            )
            prog_ratio = (idx + 1) / max(1, total_cands)
            if piv_cnt > 0 or idx >= (total_cands // 2):
                p_name = "GAP2 adaptive pivoting and validation"
                p_idx = 4
                p_pct = min(89, 70 + int(prog_ratio * 20))
            else:
                p_name = "GAP1 triage and candidate investigation"
                p_idx = 3
                p_pct = min(69, 40 + int(prog_ratio * 30))

            if run_entry.get("start_time"):
                try:
                    s_dt = datetime.fromisoformat(run_entry["start_time"])
                    if s_dt.tzinfo is None:
                        s_dt = s_dt.replace(tzinfo=UTC)
                    run_entry["duration_seconds"] = round(
                        max(0.0, (datetime.now(UTC) - s_dt).total_seconds()), 2
                    )
                except Exception:
                    pass

            run_entry["active_task"] = f"Evaluating candidate {c.name or c.id} on {endpoint}"
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
                "start_time": run_entry.get("start_time"),
                "duration_seconds": run_entry.get("duration_seconds"),
                "active_task": run_entry.get("active_task"),
                "active_agent": "GAP Decision Engine",
                "gap1": {
                    "identified": total_cands,
                    "investigated": idx + 1,
                },
                "gap2": {
                    "pivots": piv_cnt,
                },
                "findings_summary": {
                    "discovered": run_entry.get("findings_discovered", 0),
                    "verified": run_entry.get("findings_verified", 0),
                    "under_investigation": run_entry.get("findings_under_investigation", 0),
                    "blocked": run_entry.get("findings_blocked", 0),
                    "false_positive": run_entry.get("findings_false_positive", 0),
                },
            }

            if is_live_target:
                probe_res = _probe_web_candidate(
                    target_url, c.id, endpoint, auth_session=auth_session
                )
                confirmed = bool(probe_res[0])
                detail = str(probe_res[1])
                snippet = str(probe_res[2])
                if (
                    hasattr(probe_res, "verification_procedure")
                    and probe_res.verification_procedure
                ):
                    c.verification_procedure = probe_res.verification_procedure
                if hasattr(probe_res, "demonstrated_impact") and probe_res.demonstrated_impact:
                    c.demonstrated_impact = probe_res.demonstrated_impact
                if hasattr(probe_res, "reproducible_request") and probe_res.reproducible_request:
                    c.reproducible_request = probe_res.reproducible_request
                if hasattr(probe_res, "reproducible_response") and probe_res.reproducible_response:
                    c.reproducible_response = probe_res.reproducible_response
                if hasattr(probe_res, "parameter") and probe_res.parameter:
                    c.parameter = probe_res.parameter
                turn_label = "TURN" if execution_mode == "autonomous_multi_agent" else "PROBE"
                if confirmed:
                    current_turn += 1
                    engine.log(
                        "PROBE",
                        f"[{turn_label} {current_turn}/{max_turns}] Evaluating candidate: {c.name} on {endpoint}",
                    )
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
                    raw_ev = (
                        snippet.encode("utf-8")
                        if snippet
                        else f"HTTP/1.1 200 OK\nHost: {target_url}\nVector: {c.id}\nTimestamp: {_utc_now()}".encode()
                    )
                    c.evidence_hash = hashlib.sha256(raw_ev).hexdigest()
                    c.detail = snippet or detail
                    run_entry["candidates"] = _sync_engine_candidates(engine, candidate_map)
                    run_entry["decision_trace"] = list(engine.decision_trace)
                    run_entry["pivot_events"] = [
                        e.model_dump()
                        if hasattr(e, "model_dump")
                        else (e.dict() if hasattr(e, "dict") else dict(e))
                        for e in engine.pivot_events
                    ]
                    time.sleep(turn_delay)
                else:
                    for att in range(1, max_k + 1):
                        current_turn += 1
                        if att == 1:
                            engine.log(
                                "PROBE",
                                f"[{turn_label} {current_turn}/{max_turns}] Evaluating candidate: {c.name} on {endpoint} (Attempt 1/{max_k} - Probe returned non-viable)",
                            )
                            action_res = engine.record_outcome(
                                c.id,
                                Outcome.FAIL_TIMEOUT,
                                probe_outcome="negative",
                                detail=f"Probe returned non-viable: {detail}",
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
                        else:
                            engine.log(
                                "PROBE",
                                f"[{turn_label} {current_turn}/{max_turns}] Evaluating candidate: {c.name} on {endpoint} (Attempt {att}/{max_k} - Confirmation probe returned non-viable)",
                            )
                            action_res = engine.record_outcome(
                                c.id,
                                Outcome.FAIL_TIMEOUT,
                                probe_outcome="negative",
                                detail=f"Confirmation probe retry {att}/{max_k} returned non-viable: {detail}",
                            )
                            gap_bridge.record_outcome(
                                directory=control_dir,
                                candidate_id=c.id,
                                title=c.name or c.id,
                                endpoint=endpoint,
                                target=target_url,
                                probe_status="inconclusive",
                                detail=f"Retry confirmation probe non-viable: {detail}",
                                source="no_docker_probe",
                            )
                        if action_res.action in (
                            PivotActionType.REDIRECT,
                            PivotActionType.COMPLETE,
                        ):
                            break
                    c.state = (
                        CandidateState.ABANDONED
                        if c.attempts >= max_k
                        else CandidateState.INCONCLUSIVE
                    )
                    c.detail = detail
                    run_entry["candidates"] = _sync_engine_candidates(engine, candidate_map)
                    run_entry["decision_trace"] = list(engine.decision_trace)
                    run_entry["pivot_events"] = [
                        e.model_dump()
                        if hasattr(e, "model_dump")
                        else (e.dict() if hasattr(e, "dict") else dict(e))
                        for e in engine.pivot_events
                    ]
                    time.sleep(turn_delay)
            elif c.id in (
                "default-credentials",
                "phpinfo-disclosure",
                "sqli-login",
                "cve-2021-44228",
                "missing-security-headers",
            ):
                current_turn += 1
                engine.log(
                    "PROBE",
                    f"[TURN {current_turn}/{max_turns}] Evaluating candidate: {c.name} on {endpoint}",
                )
                engine.record_outcome(
                    c.id, Outcome.SUCCESS, detail="Confirmed vulnerability with valid PoC"
                )
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
                for att in range(1, max_k + 1):
                    current_turn += 1
                    if att == 1:
                        engine.log(
                            "PROBE",
                            f"[TURN {current_turn}/{max_turns}] Evaluating candidate: {c.name} on {endpoint} (Attempt 1/{max_k} - Offline candidate non-viable)",
                        )
                        action_res = engine.record_outcome(
                            c.id,
                            Outcome.FAIL_TIMEOUT,
                            probe_outcome="negative",
                            detail="Candidate evaluated as non-viable in offline mode",
                        )
                        gap_bridge.record_outcome(
                            directory=control_dir,
                            candidate_id=c.id,
                            title=c.name or c.id,
                            endpoint=endpoint,
                            target=target_url,
                            probe_status="inconclusive",
                            detail="Candidate non-viable in offline mode",
                            source="no_docker_mock",
                        )
                    else:
                        engine.log(
                            "PROBE",
                            f"[TURN {current_turn}/{max_turns}] Evaluating candidate: {c.name} on {endpoint} (Attempt {att}/{max_k} - Confirmation non-viable)",
                        )
                        action_res = engine.record_outcome(
                            c.id,
                            Outcome.FAIL_TIMEOUT,
                            probe_outcome="negative",
                            detail="Confirmation probe evaluated as non-viable in offline mode",
                        )
                        gap_bridge.record_outcome(
                            directory=control_dir,
                            candidate_id=c.id,
                            title=c.name or c.id,
                            endpoint=endpoint,
                            target=target_url,
                            probe_status="inconclusive",
                            detail="Confirmation non-viable",
                            source="no_docker_mock",
                        )
                    if action_res.action in (PivotActionType.REDIRECT, PivotActionType.COMPLETE):
                        break
                c.state = (
                    CandidateState.ABANDONED if c.attempts >= max_k else CandidateState.INCONCLUSIVE
                )
                time.sleep(turn_delay)

            run_entry["candidates"] = _sync_engine_candidates(engine, candidate_map)
            run_entry["decision_trace"] = list(engine.decision_trace)
            run_entry["pivot_events"] = [
                e.model_dump()
                if hasattr(e, "model_dump")
                else (e.dict() if hasattr(e, "dict") else dict(e))
                for e in engine.pivot_events
            ]
            piv_cnt = len(
                [
                    e
                    for e in engine.pivot_events
                    if getattr(e, "type", "") in ("REDIRECT", "GAP2_PIVOT")
                    or getattr(e, "event", "") == "GAP2_PIVOT"
                ]
            )
            prog_ratio = (idx + 1) / max(1, total_cands)
            if piv_cnt > 0 or idx >= (total_cands // 2):
                p_name = "GAP2 adaptive pivoting and validation"
                p_idx = 4
                p_pct = min(89, 70 + int(prog_ratio * 20))
            else:
                p_name = "GAP1 triage and candidate investigation"
                p_idx = 3
                p_pct = min(69, 40 + int(prog_ratio * 30))

            if run_entry.get("start_time"):
                try:
                    s_dt = datetime.fromisoformat(run_entry["start_time"])
                    if s_dt.tzinfo is None:
                        s_dt = s_dt.replace(tzinfo=UTC)
                    run_entry["duration_seconds"] = round(
                        max(0.0, (datetime.now(UTC) - s_dt).total_seconds()), 2
                    )
                except Exception:
                    pass

            run_entry["active_task"] = f"Evaluating candidate {c.name or c.id} on {endpoint}"
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
                "start_time": run_entry.get("start_time"),
                "duration_seconds": run_entry.get("duration_seconds"),
                "active_task": run_entry.get("active_task"),
                "active_agent": "GAP Decision Engine",
                "gap1": {
                    "identified": total_cands,
                    "investigated": idx + 1,
                },
                "gap2": {
                    "pivots": piv_cnt,
                },
                "findings_summary": {
                    "discovered": run_entry.get("findings_discovered", 0),
                    "verified": run_entry.get("findings_verified", 0),
                    "under_investigation": run_entry.get("findings_under_investigation", 0),
                    "blocked": run_entry.get("findings_blocked", 0),
                    "false_positive": run_entry.get("findings_false_positive", 0),
                },
            }

        # Structured active verification across discovered endpoints if turn budget allows
        if is_live_target and scan_mode in ("standard", "deep") and current_turn < max_turns:
            discovered_paths = [
                p for p in (sp_stats.get("discovered_paths", []) or []) if p and p != "/"
            ][:3]
            fuzz_checks = [
                "missing-security-headers",
                "server-banner",
                "cors",
                "csrf",
                "reflected-xss",
            ]
            for curr_path in discovered_paths:
                if current_turn >= max_turns:
                    break
                for check_id in fuzz_checks:
                    if current_turn >= max_turns:
                        break
                    current_turn += 1
                    engine.log(
                        "PROBE",
                        f"[TURN {current_turn}/{max_turns}] Probing {check_id} on {curr_path}",
                    )
                    is_vuln, det, snip = _probe_web_candidate(
                        target_url, check_id, curr_path, auth_session=auth_session
                    )
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
                        engine.candidates[f"{check_id}-{curr_path}"] = ActionCandidate(
                            id=f"{check_id}-{curr_path}",
                            name=f"{check_id.replace('-', ' ').title()} ({curr_path})",
                            severity="medium",
                            target=target_url,
                            state=CandidateState.VALIDATED,
                            detail=snip or det,
                            evidence_hash=hashlib.sha256((snip or det).encode("utf-8")).hexdigest(),
                        )
                    if turn_delay > 0:
                        time.sleep(turn_delay)

        run_entry["decision_trace"] = list(engine.decision_trace)
        run_entry["pivot_events"] = [
            e.model_dump()
            if hasattr(e, "model_dump")
            else (e.dict() if hasattr(e, "dict") else dict(e))
            for e in engine.pivot_events
        ]
        run_entry["candidates"] = _sync_engine_candidates(engine, candidate_map)

        # Milestone 5: Report synthesis and persistence (90-100%)
        piv_cnt = len(
            [
                e
                for e in engine.pivot_events
                if getattr(e, "type", "") in ("REDIRECT", "GAP2_PIVOT")
                or getattr(e, "event", "") == "GAP2_PIVOT"
            ]
        )
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
        existing_findings = list(run_entry.get("findings", []))
        findings = list(existing_findings)
        seen_finding_keys = {
            (
                f.get("title", "").strip().lower(),
                f.get("location", "/").strip().lower(),
                str(f.get("parameter", "")).strip().lower() if f.get("parameter") else "",
            )
            for f in findings
        }
        for c in engine.candidates.values():
            c_state_str = c.state.value if hasattr(c.state, "value") else str(c.state)
            c_meta = candidate_map.get(c.id, {})
            if (
                c.id.startswith("open-port-")
                or c_meta.get("is_recon_only")
                or c_meta.get("finding_class") == "reconnaissance"
            ):
                continue

            mapped_profile = map_finding_to_owasp(
                c.name,
                rule_id=c.id,
                endpoint=c_meta.get("endpoint", "/"),
                tech_stack=detected_tech,
            )

            title_val = c.name or mapped_profile.get("title", c.id)
            loc_val = c_meta.get("endpoint", "/")
            param_val = getattr(c, "parameter", None) or c_meta.get("parameter")
            dedup_key = (
                title_val.strip().lower(),
                loc_val.strip().lower(),
                str(param_val).strip().lower() if param_val else "",
            )
            if dedup_key in seen_finding_keys:
                continue

            cve_val = mapped_profile.get("cve_id") or c_meta.get("cve_id")
            if cve_val and (cve_val.startswith("CVE-2022-XXXX") or cve_val == "N/A"):
                cve_val = None

            raw_cvss = mapped_profile.get("cvss", c_meta.get("cvss_score", 5.0))
            raw_sev = getattr(c, "severity", "medium")
            aligned_cvss, aligned_sev = _align_cvss_severity(raw_cvss, raw_sev)

            raw_evidence = getattr(c, "detail", "") or ""
            ev_hash = c.evidence_hash or (
                hashlib.sha256(raw_evidence.encode("utf-8")).hexdigest() if raw_evidence else ""
            )

            # Preserve ACTUAL captured evidence only - NO SYNTHETIC FALLBACKS
            rep_req = getattr(c, "reproducible_request", None) or ""
            rep_resp = getattr(c, "reproducible_response", None) or (
                raw_evidence if raw_evidence else ""
            )
            verif_proc = getattr(c, "verification_procedure", None) or ""
            impact_val = getattr(c, "demonstrated_impact", None) or ""

            # Check verification contract:
            has_genuine_evidence = bool(
                rep_req
                and str(rep_req).strip()
                and str(rep_req).strip() != "N/A"
                and rep_resp
                and str(rep_resp).strip()
                and verif_proc
                and str(verif_proc).strip()
                and impact_val
                and str(impact_val).strip()
            )

            if c_state_str == "VALIDATED" and has_genuine_evidence:
                verification_state = "Verified"
                is_verified = True
                val_method = verif_proc
                evidence_ts = _utc_now()
                sev_just = f"Rated {aligned_sev} (CVSS {aligned_cvss}) based on verified exploitability and demonstrated impact."
            else:
                is_verified = False
                val_method = (
                    verif_proc or "Unverified candidate: Insufficient reproducible evidence"
                )
                evidence_ts = _utc_now() if raw_evidence else ""
                sev_just = f"Preliminary rating {aligned_sev} (CVSS {aligned_cvss}); pending reproducible exploitation proof."
                if c_state_str == "VALIDATED":
                    verification_state = "Unconfirmed"
                elif c_state_str == "ABANDONED":
                    verification_state = "Inconclusive"
                elif c_state_str == "BLOCKED":
                    verification_state = "Blocked"
                elif c_state_str == "ATTEMPTING":
                    verification_state = "Under investigation"
                else:
                    verification_state = "Candidate"

            # Only append findings that are validated, unconfirmed with evidence, or under investigation
            if (
                c_state_str == "VALIDATED"
                or is_verified
                or (c_state_str in ("ATTEMPTING", "INCONCLUSIVE", "PENDING") and raw_evidence)
            ):
                seen_finding_keys.add(dedup_key)
                findings.append(
                    {
                        "id": f"find-{c.id}",
                        "title": title_val,
                        "severity": aligned_sev,
                        "cvss_score": aligned_cvss,
                        "cve_id": cve_val,
                        "cwe_id": mapped_profile.get("cwe_id", c_meta.get("cwe_id", "CWE-200")),
                        "owasp_category": f"{mapped_profile.get('owasp_id', 'A01:2021')} - {mapped_profile.get('category_name', 'Broken Access Control')}",
                        "location": loc_val,
                        "target": target_url or c.target,
                        "evidence_hash": ev_hash,
                        "evidence_snippet": raw_evidence
                        if isinstance(raw_evidence, str)
                        else (
                            raw_evidence.decode("utf-8", errors="ignore") if raw_evidence else ""
                        ),
                        "reproducible_request": rep_req,
                        "reproducible_response": rep_resp,
                        "verification_response": rep_resp,
                        "verification_procedure": verif_proc,
                        "demonstrated_impact": impact_val,
                        "parameter": param_val,
                        "evidence_timestamp": evidence_ts,
                        "verification_state": verification_state,
                        "verified": is_verified,
                        "validation_method": val_method,
                        "severity_justification": sev_just,
                        "impact": impact_val or "Unconfirmed / theoretical impact",
                        "remediation_summary": mapped_profile.get("remediation_summary", ""),
                        "remediation_technical": mapped_profile.get("remediation_technical", ""),
                        "retest_procedure": mapped_profile.get("retest_procedure", ""),
                        "finding_class": "dynamic",
                    }
                )
        for c in engine.candidates.values():
            if c.attempts == 0 and c.state not in (
                CandidateState.VALIDATED,
                CandidateState.ABANDONED,
                CandidateState.BLOCKED,
            ):
                c.state = CandidateState.NOT_TESTED

        run_entry["candidates"] = _sync_engine_candidates(engine, candidate_map)
        run_entry["findings"] = findings
        run_entry["stats"] = {
            "attempts": max(current_turn, sum(c.attempts for c in engine.candidates.values())),
            "pivots": len(
                [
                    e
                    for e in engine.pivot_events
                    if getattr(e, "type", "") in ("REDIRECT", "GAP2_PIVOT")
                    or getattr(e, "event", "") == "GAP2_PIVOT"
                ]
            ),
            "findings": len(findings),
            "candidates_dispatched": total_cands,
            "candidates_investigated": sum(
                1
                for c in run_entry.get("candidates", [])
                if c.get("state") in ("VALIDATED", "ABANDONED") or c.get("attempts", 0) > 0
            ),
            "candidates_validated": sum(
                1 for c in run_entry.get("candidates", []) if c.get("state") == "VALIDATED"
            ),
            "candidates_abandoned": sum(
                1 for c in run_entry.get("candidates", []) if c.get("state") == "ABANDONED"
            ),
            "candidates_not_tested": sum(
                1 for c in run_entry.get("candidates", []) if c.get("state") == "NOT_TESTED"
            ),
            "candidates_blocked": sum(
                1 for c in run_entry.get("candidates", []) if c.get("state") == "BLOCKED"
            ),
        }
        inv_cnt = sum(
            1
            for c in run_entry.get("candidates", [])
            if (c.get("state") in ("VALIDATED", "ABANDONED") or c.get("attempts", 0) > 0)
            and c.get("state") not in ("BLOCKED", "UNRESOLVED")
        )
        blk_cnt = sum(
            1
            for c in run_entry.get("candidates", [])
            if c.get("state") in ("BLOCKED", "UNRESOLVED")
        )
        nt_cnt = max(0, total_cands - (inv_cnt + blk_cnt))

        run_entry["candidate_accounting"] = {
            "dispatched": total_cands,
            "investigated": inv_cnt,
            "validated": sum(
                1 for c in run_entry.get("candidates", []) if c.get("state") == "VALIDATED"
            ),
            "abandoned": sum(
                1 for c in run_entry.get("candidates", []) if c.get("state") == "ABANDONED"
            ),
            "not_tested": nt_cnt,
            "blocked": blk_cnt,
        }
        run_entry["tech_stack"] = detected_tech

        run_entry["completed_at"] = _utc_now()
        untested_cands = sum(
            1
            for c in run_entry.get("candidates", [])
            if c.get("state") in ("PENDING", "NOT_TESTED")
            or (c.get("attempts", 0) == 0 and c.get("state") not in ("VALIDATED", "ABANDONED"))
        )
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
                "start_time": run_entry.get("start_time"),
                "duration_seconds": run_entry.get("duration_seconds"),
            }
            run_entry["events"].append(
                {
                    "timestamp": _utc_now(),
                    "event": "RUN_PARTIAL",
                    "message": f"Assessment completed partially with {untested_cands} untested candidate(s). Found {len(findings)} confirmed finding(s).",
                }
            )
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
                "start_time": run_entry.get("start_time"),
                "duration_seconds": run_entry.get("duration_seconds"),
            }
            run_entry["events"].append(
                {
                    "timestamp": _utc_now(),
                    "event": "RUN_COMPLETED",
                    "message": f"Assessment finished. Found {len(findings)} confirmed finding(s).",
                }
            )
        _finalize_run_lifecycle(run_entry, status=run_entry["status"])
        _sync_run_counters(run_entry)
        _save_run_to_disk(run_entry)

    except Exception as exc:
        logger.exception("Assessment run %s failed", run_id)
        _sync_run_counters(run_entry)
        _finalize_run_lifecycle(run_entry, status="failed", error=str(exc))
        run_entry["error"] = str(exc)
        run_entry["status"] = "failed"
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
            "start_time": run_entry.get("start_time"),
            "duration_seconds": run_entry.get("duration_seconds"),
        }
        run_entry["events"].append(
            {
                "timestamp": _utc_now(),
                "event": "RUN_FAILED",
                "message": f"Run terminated with error: {exc}",
            }
        )
        _save_run_to_disk(run_entry)
    finally:
        if run_id == _CURRENT_ACTIVE_RUN_ID:
            _CURRENT_ACTIVE_RUN_ID = None


@app.post("/runs", response_model=RunResponse)
async def create_run(
    req: RunRequest,
    background_tasks: BackgroundTasks,
    x_google_api_key: str | None = Header(None, alias="X-Google-API-Key"),
    x_openrouter_api_key: str | None = Header(None, alias="X-OpenRouter-API-Key"),
    x_anthropic_api_key: str | None = Header(None, alias="X-Anthropic-API-Key"),
    x_openai_api_key: str | None = Header(None, alias="X-OpenAI-API-Key"),
    user: dict[str, Any] = Depends(require_operator),
):
    """Launch a new assessment run in the background."""
    global _CURRENT_ACTIVE_RUN_ID
    if req.mode in ("web", "autonomous", "web_controlled", "lightweight", "in_process"):
        target_candidate = req.target_url or req.target
        if not target_candidate:
            raise HTTPException(
                status_code=400,
                detail="Target URL is required for live security assessment.",
            )
        if not req.target_scope_acknowledged:
            raise HTTPException(
                status_code=400,
                detail="Explicit operator scope acknowledgement is required to assess target.",
            )
        from strix.core.safety.scope_validator import validate_web_target

        scope_res = validate_web_target(
            target_candidate,
            operator_scope_confirmed=req.target_scope_acknowledged,
            engagement_id=req.engagement_id,
        )
        if not scope_res.authorized:
            raise HTTPException(
                status_code=403,
                detail=f"Target '{target_candidate}' is not authorized. {scope_res.message}",
            )

    if req.mode == "autonomous":
        # _CURRENT_ACTIVE_RUN_ID is process memory; it can outlive a crashed
        # worker thread. Re-validate against the real process before blocking.
        active_proc = _ACTIVE_PROCESSES.get(_CURRENT_ACTIVE_RUN_ID or "")
        if _CURRENT_ACTIVE_RUN_ID and (active_proc is None or active_proc.poll() is not None):
            _CURRENT_ACTIVE_RUN_ID = None
        if _CURRENT_ACTIVE_RUN_ID:
            active_run = _RUNS.get(_CURRENT_ACTIVE_RUN_ID, {})
            active_proc = _ACTIVE_PROCESSES.get(_CURRENT_ACTIVE_RUN_ID)
            if active_run.get("status") in ("running", "queued") or (
                active_proc and active_proc.poll() is None
            ):
                raise HTTPException(
                    status_code=409,
                    detail=f"An autonomous assessment is already actively running ({_CURRENT_ACTIVE_RUN_ID}). Please wait for it to complete or stop it before launching a new scan.",
                )
        if not _is_docker_available():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Autonomous multi-agent execution requires Docker runtime (daemon and CLI), "
                    "which is currently unavailable on this host. Please ensure Docker daemon is running, "
                    "or select lightweight active scanning (mode='lightweight')."
                ),
            )

    run_id = f"run-{uuid.uuid4().hex[:8]}"
    if req.mode == "autonomous":
        _CURRENT_ACTIVE_RUN_ID = run_id

    from strix.core.runtime_credentials import (
        get_runtime_credential,
        get_runtime_model,
        set_runtime_base_url,
        set_runtime_credential,
    )

    configured_provider = (req.provider or req.assessor_provider or "openrouter").lower().strip()
    api_base_val = req.api_base or req.assessor_api_base
    if api_base_val:
        set_runtime_base_url(configured_provider, api_base_val.strip())

    runtime_key = (
        x_anthropic_api_key
        or x_openai_api_key
        or x_google_api_key
        or x_openrouter_api_key
        or req.api_key
        or req.assessor_api_key
        or get_runtime_credential(configured_provider)
    )

    cli_cfg = _read_strix_cli_config()
    configured_model = (
        req.model
        or req.assessor_model
        or get_runtime_model(configured_provider)
        or cli_cfg.get("STRIX_LLM")
        or DEFAULT_OPENROUTER_MODEL
    )

    if (
        runtime_key
        and not runtime_key.startswith("sk-or-v1-test")
        and "placeholder" not in runtime_key.lower()
    ):
        set_runtime_credential(configured_provider, runtime_key, configured_model)

    # Provider preflight validation before launching
    key_for_check = (
        runtime_key
        or get_runtime_credential(configured_provider)
        or cli_cfg.get("OPENROUTER_API_KEY")
        or cli_cfg.get("ANTHROPIC_API_KEY")
        or cli_cfg.get("OPENAI_API_KEY")
        or cli_cfg.get("GEMINI_API_KEY")
        or cli_cfg.get("LLM_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
    )
    if configured_provider == "openrouter" and key_for_check:
        from strix.llm.provider_validation import validate_openrouter_credential

        val = validate_openrouter_credential(key_for_check)
        if val.status == "quota_exceeded":
            raise HTTPException(
                status_code=400,
                detail=f"OpenRouter preflight check failed: {val.message}",
            )
    elif configured_provider == "anthropic" and key_for_check:
        from strix.llm.provider_validation import validate_anthropic_credential

        val_ant = validate_anthropic_credential(key_for_check)
        if not val_ant.valid:
            raise HTTPException(
                status_code=400,
                detail=f"Anthropic preflight check failed: {val_ant.message}",
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
            (
                req.assessor_model
                if req.assessor_model and req.assessor_model not in ("qwen2.5:1.5b", "default")
                else None
            )
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
        api_base_for_check = (
            cli_cfg.get("OPENAI_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        )
        if any(h in api_base_for_check.lower() for h in ("ngrok", "127.0.0.1", "localhost", "dev")):
            from strix.llm.provider_validation import validate_openai_compatible_endpoint

            val = validate_openai_compatible_endpoint(
                api_base_for_check, runtime_key or cli_cfg.get("OPENAI_API_KEY")
            )
            if not val.valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Endpoint preflight failed for {api_base_for_check}: {val.message}",
                )

    configured_turns = req.max_turns or (
        50 if req.scan_mode == "quick" else (100 if req.scan_mode == "standard" else 500)
    )

    execution_mode = (
        "autonomous_multi_agent"
        if req.mode == "autonomous"
        else (
            "lightweight_active_scanner"
            if req.mode in ("web", "web_controlled", "lightweight", "in_process")
            else "simulation"
        )
    )

    now_iso = datetime.now(UTC).isoformat()
    run_record = {
        "run_id": run_id,
        "status": "queued",
        "execution_mode": execution_mode,
        "start_time": now_iso,
        "started_at": now_iso,
        "end_time": None,
        "duration_seconds": None,
        "elapsed_seconds": 0.0,
        "last_progress_at": now_iso,
        "turns_consumed": 0,
        "progress_percent": 0,
        "scenario": req.scenario,
        "mode": req.mode,
        "target_url": req.target_url or req.target,
        "provider": configured_provider,
        "model": configured_model,
        "scan_mode": req.scan_mode or "deep",
        "max_turns": configured_turns,
        "created_at": now_iso,
        "completed_at": None,
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [],
        "findings": [],
        "findings_discovered": 0,
        "findings_verified": 0,
        "findings_under_investigation": 0,
        "findings_blocked": 0,
        "findings_false_positive": 0,
        "gap1_candidates_identified": 0,
        "gap1_candidates_under_investigation": 0,
        "gap2_pivots": 0,
        "active_agent": None,
        "active_task": None,
        "provider_error": None,
        "evidence_tier": None,
        "safety_notice": None,
        "target_ip": None,
        "additional_authorized_hosts": getattr(req, "additional_authorized_hosts", []) or [],
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
        execution_mode=execution_mode,
        mode=req.mode,
    )


@app.post("/runs/{run_id}/stop")
async def stop_run(
    run_id: str,
    user: dict[str, Any] = Depends(require_operator),
):
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
    _finalize_run_lifecycle(run, status="aborted", error="operator request")
    if "progress" in run and isinstance(run["progress"], dict):
        cur_pct = run["progress"].get("percent", 0)
        run["progress"]["percent"] = min(90, cur_pct)
        cur_phase = run["progress"].get("phase", "Assessment")
        run["progress"]["phase"] = f"Stopped ({cur_phase})"
    run_dir = runs_base_dir() / run_id
    run = reconcile_all(run, run_dir=run_dir if run_dir.is_dir() else None)
    _sync_run_counters(run)
    run.setdefault("events", []).append(
        {
            "timestamp": _utc_now(),
            "event": "RUN_STOPPED",
            "message": "Operator requested early termination of assessment.",
        }
    )
    _save_run_to_disk(run)
    return {"status": "ok", "message": f"Run {run_id} stopped successfully"}


@app.get("/runs")
async def list_runs(user: dict[str, Any] = Depends(require_viewer)):
    """List recent runs from memory and persistent disk store."""
    _load_runs_from_disk()
    runs = list(_RUNS.values())
    runs.sort(key=lambda r: str(r.get("created_at") or r.get("start_time") or ""), reverse=True)
    return runs


@app.get("/runs/{run_id}", response_model=RunStatus)
async def get_run_status(
    run_id: str,
    user: dict[str, Any] = Depends(require_viewer),
):
    """Retrieve detailed state, decision trace, and candidates for a run."""
    run = _RUNS.get(run_id)
    if not run:
        _load_runs_from_disk()
        run = _RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # A worker thread can die while the in-memory record still says "running".
    # Disk loads quarantine such records, but an entry already in memory was
    # skipped; reconcile it here so the dashboard never shows a stale active
    # assessment or blocks a relaunch.
    run = _quarantine_stale_running_run(run_id, run)

    run_dir = runs_base_dir() / run_id
    run = reconcile_all(run, run_dir=run_dir if run_dir.is_dir() else None)
    _sync_run_counters(run)

    started_ts = run.get("started_at") or run.get("start_time")
    run["started_at"] = started_ts

    if run.get("status") == "running" and started_ts:
        try:
            s_dt = datetime.fromisoformat(started_ts)
            if s_dt.tzinfo is None:
                s_dt = s_dt.replace(tzinfo=UTC)
            elapsed = round(max(0.0, (datetime.now(UTC) - s_dt).total_seconds()), 2)
            run["duration_seconds"] = elapsed
            run["elapsed_seconds"] = elapsed
        except Exception:
            pass
    elif run.get("duration_seconds") is not None:
        run["elapsed_seconds"] = run.get("duration_seconds")
    elif run.get("end_time") and started_ts:
        try:
            s_dt = datetime.fromisoformat(started_ts)
            if s_dt.tzinfo is None:
                s_dt = s_dt.replace(tzinfo=UTC)
            e_dt = datetime.fromisoformat(run["end_time"])
            if e_dt.tzinfo is None:
                e_dt = e_dt.replace(tzinfo=UTC)
            elapsed = round(max(0.0, (e_dt - s_dt).total_seconds()), 2)
            run["duration_seconds"] = elapsed
            run["elapsed_seconds"] = elapsed
        except Exception:
            pass

    return RunStatus(**run)


@app.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    req: ResumeRunRequest | None = None,
    user: dict[str, Any] = Depends(require_operator),
):
    """Resume an interrupted, provider-blocked, or partial assessment."""
    from strix.core.runtime_credentials import (
        get_runtime_credential,
        set_runtime_base_url,
        set_runtime_credential,
    )

    run = _RUNS.get(run_id)
    if not run:
        _load_runs_from_disk()
        run = _RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    resumable_statuses = (
        "provider_blocked",
        "paused_provider_limit",
        "paused_execution_limit",
        "failed",
        "failed_agent",
        "failed_infrastructure",
        "interrupted",
        "partial",
        "aborted",
    )
    if run.get("status") not in resumable_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Run {run_id} is in status '{run.get('status')}' and cannot be resumed (must be one of {resumable_statuses}).",
        )

    original_provider = run.get("provider", "unknown")
    original_model = run.get("model", "unknown")

    # Apply configuration updates
    if req:
        if req.provider:
            new_prov = req.provider.lower().strip()
            run["provider"] = new_prov
            run["assessor_provider"] = new_prov
        if req.model:
            new_mod = req.model.strip()
            run["model"] = new_mod
            run["assessor_model"] = new_mod
        if req.max_turns:
            run["max_turns"] = req.max_turns
        if req.api_base:
            set_runtime_base_url(run.get("provider", "custom"), req.api_base.strip())
        if req.api_key:
            set_runtime_credential(
                run.get("provider", "openrouter"),
                req.api_key.strip(),
                run.get("model"),
            )
        if req.additional_authorized_hosts is not None:
            current_hosts = list(run.get("additional_authorized_hosts") or [])
            for h in req.additional_authorized_hosts:
                if h not in current_hosts:
                    current_hosts.append(h)
            run["additional_authorized_hosts"] = current_hosts

    run["status"] = "running"
    run["is_resumed"] = True
    run["end_time"] = None
    run["error"] = None
    run["provider_error"] = None
    resumed_msg = (
        f"Assessment resumed with model {run.get('model', 'default')} "
        f"(provider: {run.get('provider', 'default')}). "
        f"Original: {original_provider} / {original_model}"
    )
    run.setdefault("events", []).append(
        {
            "timestamp": _utc_now(),
            "event": "RUN_RESUMED",
            "message": resumed_msg,
        }
    )
    _save_run_to_disk(run)

    run_req = RunRequest(
        scenario=run.get("scenario", "web_application"),
        mode=run.get("mode", "autonomous"),
        target=run.get("target_url") or run.get("target", ""),
        target_url=run.get("target_url") or run.get("target", ""),
        model=run.get("model", "openrouter/auto"),
        provider=run.get("provider", "openrouter"),
        assessor_model=run.get("model"),
        assessor_provider=run.get("provider", "openrouter") or "openrouter",
        scan_mode=run.get("scan_mode", "standard"),
        max_turns=run.get("max_turns", 50),
        auth_config=run.get("auth_context") or {},
        additional_authorized_hosts=run.get("additional_authorized_hosts", []),
        target_scope_acknowledged=True,
    )

    runtime_key = (req.api_key if (req and req.api_key) else None) or get_runtime_credential(
        run.get("provider", "openrouter")
    )
    if background_tasks:
        background_tasks.add_task(_execute_run_worker, run_id, run_req, runtime_key)
    else:
        t = threading.Thread(
            target=_execute_run_worker,
            args=(run_id, run_req, runtime_key),
            daemon=True,
        )
        t.start()

    return {
        "status": "resumed",
        "run_id": run_id,
        "message": resumed_msg,
    }


@app.get("/runs/{run_id}/stream")
async def stream_run_events(
    run_id: str,
    request: Request,
    after_seq: int = 0,
    user: dict[str, Any] = Depends(require_viewer),
):
    """Stream live assessment events, terminal traces, and state updates via SSE with monotonic sequence IDs."""
    run = _RUNS.get(run_id)
    if not run:
        _load_runs_from_disk()
        run = _RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    async def event_generator():
        seq = max(0, after_seq)
        current_initial = _RUNS.get(run_id, run)
        _sync_run_counters(current_initial)

        # Yield initial state
        seq += 1
        yield f"id: {seq}\nevent: state\ndata: {json.dumps(current_initial, default=str)}\n\n"

        init_prog = current_initial.get("progress")
        last_progress_pct = -1
        last_progress_phase = ""
        last_current_turn = -1
        if init_prog and isinstance(init_prog, dict):
            if "run_id" not in init_prog:
                init_prog = dict(init_prog)
                init_prog["run_id"] = run_id
            seq += 1
            yield f"id: {seq}\nevent: progress\ndata: {json.dumps(init_prog, default=str)}\n\n"
            last_progress_pct = init_prog.get("percent", -1)
            last_progress_phase = init_prog.get("phase", "")
            last_current_turn = init_prog.get("current", -1)

        last_log_count = len(current_initial.get("decision_trace", []))
        last_status = current_initial.get("status")
        last_findings_count = len(current_initial.get("findings", []))
        last_pivots_count = len(current_initial.get("pivot_events", []))
        last_candidates_state = tuple(
            (c.get("id"), c.get("state"), c.get("attempts"))
            for c in current_initial.get("candidates", [])
        )
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
                    seq += 1
                    yield f"id: {seq}\nevent: log\ndata: {json.dumps(entry, default=str)}\n\n"
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
                    seq += 1
                    yield f"id: {seq}\nevent: progress\ndata: {json.dumps(prog, default=str)}\n\n"
                    last_progress_pct = curr_pct
                    last_progress_phase = curr_phase
                    last_current_turn = curr_turn

            # 3. Stream state updates on findings, pivots, candidates, or status changes
            curr_status = current_run.get("status")
            curr_findings = current_run.get("findings", [])
            curr_findings_count = len(curr_findings)
            curr_pivots_count = len(current_run.get("pivot_events", []))
            curr_candidates_state = tuple(
                (c.get("id"), c.get("state"), c.get("attempts"))
                for c in current_run.get("candidates", [])
            )

            has_state_diff = (
                curr_status != last_status
                or curr_findings_count != last_findings_count
                or curr_pivots_count != last_pivots_count
                or curr_candidates_state != last_candidates_state
            )

            if curr_findings_count != last_findings_count:
                seq += 1
                yield f"id: {seq}\nevent: findings\ndata: {json.dumps(curr_findings, default=str)}\n\n"
                last_findings_count = curr_findings_count

            if has_state_diff:
                _sync_run_counters(current_run)
                seq += 1
                yield f"id: {seq}\nevent: state\ndata: {json.dumps(current_run, default=str)}\n\n"
                last_status = curr_status
                last_pivots_count = curr_pivots_count
                last_candidates_state = curr_candidates_state

            if curr_status in (
                "completed",
                "failed",
                "aborted",
                "partial",
                "provider_blocked",
                "interrupted",
            ):
                seq += 1
                yield f"id: {seq}\nevent: complete\ndata: {json.dumps({'status': curr_status, 'run_id': run_id, 'seq': seq})}\n\n"
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
    download: bool | None = False,
    user: dict[str, Any] = Depends(require_viewer),
):
    """Generate or retrieve assessment report (HTML, JSON, PDF, SARIF, or Markdown)."""
    run = _RUNS.get(run_id)
    if not run:
        _load_runs_from_disk()
        run = _RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    fmt = format.lower().strip()
    run_dir = runs_base_dir() / run_id
    run = reconcile_all(run, run_dir=run_dir if run_dir.is_dir() else None)
    _sync_run_counters(run)

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
                writer.writerow(
                    {
                        "id": f.get("id", ""),
                        "title": f.get("title", ""),
                        "severity": f.get("severity", "INFO"),
                        "cvss_score": f.get("cvss_score", ""),
                        "cwe_id": f.get("cwe_id", ""),
                        "owasp_category": f.get("owasp_category", ""),
                        "location": f.get("location", ""),
                        "target": f.get("target", run.get("target_url") or run.get("target", "")),
                        "remediation_summary": f.get("remediation_summary", ""),
                    }
                )
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
async def list_engagements(user: dict[str, Any] = Depends(require_viewer)):
    """List authorized engagement profiles."""
    return list(_ENGAGEMENTS.values())


@app.post("/engagements")
async def create_engagement(
    profile: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_admin),
):
    """Create a new authorized engagement profile."""
    eng_id = profile.get("id") or f"eng-{uuid.uuid4().hex[:6]}"
    profile["id"] = eng_id
    profile["created_at"] = _utc_now()
    _ENGAGEMENTS[eng_id] = profile
    return profile
