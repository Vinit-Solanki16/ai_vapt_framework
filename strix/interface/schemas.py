"""API request/response schemas for STRIX AI-VAPT Gateway."""

from __future__ import annotations

import re
import urllib.parse
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


_HOSTNAME_REGEX = re.compile(
    r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)


def _normalize_host_entry(raw: str) -> str:
    h = str(raw).strip().lower()
    if not h:
        raise ValueError("Authorized host entry cannot be empty.")
    if "*" in h:
        raise ValueError(f"Wildcards are not permitted in authorized hosts: '{raw}'")
    if "://" in h:
        parsed = urllib.parse.urlsplit(h)
        h = parsed.hostname or ""
    elif "/" in h:
        h = h.split("/")[0]
    if ":" in h:
        if not h.startswith("["):
            h = h.split(":")[0]
    h = h.strip()
    if not h:
        raise ValueError(f"Invalid host format in '{raw}'")
    if not _HOSTNAME_REGEX.match(h):
        raise ValueError(f"Invalid hostname or domain format: '{raw}'")
    return h


class RunRequest(BaseModel):
    """Request to start a new assessment run."""

    scenario: str = Field("default", description="Scenario or assessment name")
    max_attempts: int = Field(
        2, ge=1, le=10, description="Max attempts per candidate before pivot (GAP-2)"
    )
    mode: Literal[
        "simulation",
        "lab",
        "web",
        "web_controlled",
        "autonomous",
        "lightweight",
        "in_process",
    ] = Field("simulation", description="Execution mode")
    target: str | None = Field(None, description="Target host or IP")
    port: int = Field(8080, ge=1, le=65535, description="Target port")
    path: str = Field("/", description="Target path")
    target_url: str | None = Field(None, description="Authorized target URL for web assessments")
    target_scope_acknowledged: bool = Field(
        False, description="Explicit operator acknowledgement of target authorization"
    )
    assessor: Literal["deterministic", "llm"] = Field(default="llm", description="Assessor type")
    assessor_provider: Literal[
        "ollama", "google", "openrouter", "openai", "anthropic", "cloud_hosted", "custom"
    ] = Field(default="openrouter", description="AI provider")
    provider: str | None = Field(default=None, description="Provider identifier alias")
    assessor_model: str | None = Field(default=None, description="Model identifier")
    model: str | None = Field(default=None, description="Model identifier alias")
    assessor_api_key: str | None = Field(
        default=None, description="Runtime API key (in-memory only, never persisted)"
    )
    api_key: str | None = Field(default=None, description="Runtime API key alias")
    assessor_api_base: str | None = Field(
        default=None, description="Optional base URL for local or custom endpoints"
    )
    api_base: str | None = Field(default=None, description="Optional base URL alias")
    scan_file: str | None = Field(None, description="Optional scan file override")
    assessment_type: Literal["scenario", "web", "strix_autonomous"] = Field(
        "scenario", description="Assessment type"
    )
    use_nmap: bool = Field(True, description="Run Nmap discovery")
    use_nuclei: bool = Field(True, description="Run Nuclei scanner")
    engagement_id: str | None = Field(None, description="Optional engagement profile ID")
    scan_mode: str | None = Field("deep", description="Strix scan mode (quick, standard, deep)")
    max_turns: int | None = Field(
        500,
        description="Max execution turns for autonomous scanning (50=quick, 100=standard, 250=deep, 500=default, 1000=thorough, or custom 1-1000)",
    )
    instruction: str | None = Field(
        None, description="Optional custom penetration testing instruction or objective"
    )
    auth_config: dict[str, Any] | None = Field(
        None, description="Optional target authentication configuration"
    )
    additional_authorized_hosts: list[str] = Field(
        default_factory=list,
        description="Explicitly authorized additional hostnames or subdomains in scope",
    )

    @field_validator("additional_authorized_hosts", mode="before")
    @classmethod
    def validate_additional_authorized_hosts(cls, v: Any) -> list[str]:
        if not v:
            return []
        items: list[str] = []
        if isinstance(v, str):
            parts = [p.strip() for p in re.split(r"[\n,]+", v) if p.strip()]
            items = parts
        elif isinstance(v, (list, tuple, set)):
            items = [str(x).strip() for x in v if str(x).strip()]
        else:
            return []

        normalized: list[str] = []
        for item in items:
            norm = _normalize_host_entry(item)
            if norm not in normalized:
                normalized.append(norm)
        return normalized

    @field_validator("max_turns", mode="before")
    @classmethod
    def validate_max_turns(cls, v: Any) -> Any:
        if v is not None:
            try:
                iv = int(v)
            except (ValueError, TypeError):
                raise ValueError("max_turns must be a valid integer.")
            if iv < 1 or iv > 1000:
                raise ValueError("Execution turn limit must be between 1 and 1000 turns.")
            return iv
        return v


class RunResponse(BaseModel):
    """Immediate response when a run is dispatched."""

    run_id: str
    status: Literal["queued", "running", "completed", "failed", "aborted", "blocked"] = "running"
    message: str = "Assessment initialized"
    created_at: str = Field(default_factory=_utc_now)
    execution_mode: str | None = None
    mode: str | None = None


class PivotEventSchema(BaseModel):
    """GAP-2 decision pivot event."""

    model_config = ConfigDict(extra="allow")

    timestamp: str = Field(default_factory=_utc_now)
    type: str = "GAP2_PIVOT"  # INIT, ADVANCE, REDIRECT, ABANDON, COMPLETE, GAP2_PIVOT
    event: str | None = None
    candidate_id: str | None = None
    attempt: int | None = None
    max_attempts: int | None = None
    reason: str | None = None
    to_candidate: str | None = None
    next_candidate: str | None = None
    probe_outcome: str | None = None
    pivot_executed: bool = True
    result: str | None = None
    message: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_gap2_event(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "type" not in data and "event" in data:
                data["type"] = data.get("event") or "GAP2_PIVOT"
            if "event" not in data and "type" in data:
                data["event"] = data.get("type") or "GAP2_PIVOT"
            if "to_candidate" not in data and "next_candidate" in data:
                data["to_candidate"] = data["next_candidate"]
            if "next_candidate" not in data and "to_candidate" in data:
                data["next_candidate"] = data["to_candidate"]
        return data


class CandidateSchema(BaseModel):
    """Candidate vulnerability or exploit target (GAP-1 / GAP-2)."""

    id: str
    name: str
    target: str = ""
    severity: str = "medium"
    cvss_score: float | None = None
    owasp_category: str | None = None
    cwe_id: str | None = None
    usability_rank: str | None = None  # HIGH, MEDIUM, LOW
    exploit_viable: bool | None = None
    reasoning: str | None = None
    composite_score: float | None = None
    attempts: int = 0
    max_attempts: int = 2
    state: str = "PENDING"  # DISCOVERED, CANDIDATE, UNDER_INVESTIGATION, PROBE_EXECUTED, VALIDATED_OBSERVATION, EXPLOITATION_ATTEMPTED, VERIFIED_VULNERABILITY, RULED_OUT, ABANDONED, INCONCLUSIVE, BLOCKED, FALSE_POSITIVE, NOT_TESTED, PENDING, IDENTIFIED, ATTEMPTING, VALIDATED
    evidence_hash: str | None = None
    # Probe & Execution Audit Fields
    tool_selected: str | None = None
    tool_invocation_id: str | None = None
    sanitized_request: str | None = None
    tool_result: str | None = None
    http_status: int | None = None
    evidence_reference: str | None = None
    verification_contract: str | None = None
    verification_result: str | None = None
    retry_eligibility: bool = False
    state_transition_reason: str | None = None
    dispatched_at: str | None = None
    agent_assignment: str | None = None


class RunStatus(BaseModel):
    """Observable asynchronous run state and real-time outputs."""

    run_id: str
    status: Literal[
        "queued",
        "running",
        "completed",
        "completed_with_findings",
        "failed",
        "aborted",
        "provider_blocked",
        "interrupted",
        "partial",
        "blocked",
        "paused_provider_limit",
        "paused_execution_limit",
        "failed_infrastructure",
        "failed_agent",
        "cancelled",
        "stopped",
    ]
    scenario: str | None = None
    mode: str | None = None
    execution_mode: str | None = None
    target_url: str | None = None
    created_at: str | None = None
    completed_at: str | None = None
    start_time: str | None = None
    started_at: str | None = None
    end_time: str | None = None
    duration_seconds: float | int | None = None
    elapsed_seconds: float | int | None = None
    active_duration_seconds: float | int | None = None
    wall_clock_duration_seconds: float | int | None = None
    process_exit_code: int | None = None
    exit_code_interpretation: str | None = None
    execution_segments: list[dict[str, Any]] = Field(default_factory=list)
    active_agent: str | None = None
    active_task: str | None = None
    last_progress_at: str | None = None
    turns_consumed: int | None = None
    progress_percent: float | int | None = None
    gap1_candidates_identified: int | None = None
    gap2_pivots: int | None = None
    pivots: int | None = None
    verification_states: dict[str, int] | None = None
    candidate_accounting: dict[str, Any] | None = None
    findings_summary: dict[str, Any] | None = None
    auth_context: dict[str, Any] | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    decision_trace: list[str | dict[str, Any]] = Field(default_factory=list)
    pivot_events: list[dict[str, Any]] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    progress: dict[str, Any] | None = None
    tech_stack: str | None = None
    evidence_tier: str | None = None
    safety_notice: str | None = None
    target_ip: str | None = None
    open_ports: list[dict[str, Any]] = Field(default_factory=list)
    components: list[dict[str, Any]] = Field(default_factory=list)
    scan_matrix: list[dict[str, Any]] = Field(default_factory=list)
    spider_stats: dict[str, Any] | None = None
    error: str | None = None
    max_turns: int | None = None
    scan_mode: str | None = None
    provider: str | None = None
    model: str | None = None
    report_status: str | None = None
    run_lifecycle_status: str | None = None
    configured_turn_limit: int | None = None
    actual_probe_count: int | None = None
    candidate_completion_percent: float | int | None = None
    category_coverage_percent: float | int | None = None
    assessment_completeness_percent: float | int | None = None
    termination_reason: str | None = None


class TargetValidateRequest(BaseModel):
    """Request to preflight an authorized web target."""

    target_url: str = Field(..., description="Web application URL to validate")
    engagement_id: str | None = Field(None, description="Optional engagement profile ID")


class TargetValidateResponse(BaseModel):
    """Preflight target scope validation result."""

    authorized: bool
    authorization_status: str
    preflight_status: str
    reachable: bool
    target_url: str | None = None
    resolved_host: str | None = None
    port: int | None = None
    http_status: int | None = None
    detail: str = ""
    scheme: str | None = None
    hostname: str | None = None
    normalized_host: str | None = None
    in_scope: bool | None = None
    scope_kind: str | None = None
    scope_entry: str | None = None
    external_scope: bool | None = None
    acknowledgement_required: bool | None = None
    address_validation: str | None = None
    resolved_ips: list[str] = Field(default_factory=list)
    engagement_id: str | None = None
    engagement_name: str | None = None


class GoogleValidateResponse(BaseModel):
    """Result of validating runtime Google Gemini credentials."""

    status: Literal[
        "not_configured", "validating", "configured", "invalid_credentials", "unreachable", "error"
    ]
    message: str
    valid: bool
    models: list[str] = Field(default_factory=list)


class DiscoveredModelInfo(BaseModel):
    """Universal model information across all AI providers."""

    id: str
    name: str
    provider: str = "openrouter"
    pricing_status: Literal["free", "paid", "unknown"] = "unknown"
    free: bool = False
    prompt_price: str | None = None
    completion_price: str | None = None
    context_length: int | None = None
    is_custom: bool = False


class OpenRouterModelInfo(DiscoveredModelInfo):
    """Catalogue entry for OpenRouter model selection."""

    provider: str = "openrouter"


class OpenRouterValidateResponse(BaseModel):
    """Result of validating runtime OpenRouter credentials."""

    status: Literal[
        "not_configured",
        "validating",
        "configured",
        "invalid_credentials",
        "rate_limited",
        "quota_exceeded",
        "unreachable",
        "error",
    ]
    message: str = ""
    valid: bool = False
    catalogue_count: int = 0
    models: list[OpenRouterModelInfo] = Field(default_factory=list)


class AnthropicValidateResponse(BaseModel):
    """Result of validating runtime Anthropic Claude credentials."""

    status: Literal[
        "not_configured",
        "validating",
        "configured",
        "invalid_credentials",
        "rate_limited",
        "quota_exceeded",
        "unreachable",
        "error",
    ] = "configured"
    message: str = ""
    valid: bool = False
    catalogue_count: int = 0
    models: list[DiscoveredModelInfo] = Field(default_factory=list)


class OllamaValidateResponse(BaseModel):
    """Result of probing local Ollama instance and discovering installed models."""

    status: Literal["not_configured", "configured", "unreachable", "error"] = "configured"
    message: str = ""
    valid: bool = False
    catalogue_count: int = 0
    models: list[DiscoveredModelInfo] = Field(default_factory=list)


class CustomEndpointValidateResponse(BaseModel):
    """Result of validating custom OpenAI-compatible endpoint."""

    status: Literal[
        "not_configured",
        "configured",
        "invalid_credentials",
        "rate_limited",
        "quota_exceeded",
        "unreachable",
        "error",
    ] = "configured"
    message: str = ""
    valid: bool = False
    catalogue_count: int = 0
    models: list[DiscoveredModelInfo] = Field(default_factory=list)


class OpenAIValidateResponse(BaseModel):
    """Result of validating custom OpenAI-compatible endpoint."""

    status: Literal[
        "not_configured",
        "configured",
        "invalid_credentials",
        "rate_limited",
        "quota_exceeded",
        "unreachable",
        "error",
    ] = "configured"
    message: str = ""
    valid: bool = False
    models: list[str] = Field(default_factory=list)


class SystemHealthResponse(BaseModel):
    """System components health report."""

    status: Literal["READY", "DEGRADED", "OFFLINE"]
    timestamp: str = Field(default_factory=_utc_now)
    components: dict[str, Any] = Field(default_factory=dict)


class CloudHostedProfile(BaseModel):
    """Configuration profile for a Generic Cloud Hosted OpenAI-compatible provider."""

    id: str | None = Field(
        default_factory=lambda: f"cloud-{uuid.uuid4().hex[:6]}",
        description="Unique profile identifier",
    )
    name: str = Field("Cloud Hosted Endpoint", description="Friendly provider display name")
    api_base: str = Field(..., description="OpenAI-compatible Base URL")
    api_key: str | None = Field(None, description="API Key or Bearer token (optional)")
    model: str = Field(..., description="Model identifier on server")
    model_alias: str | None = Field(None, description="Friendly model display alias")
    extra_headers: dict[str, str] | None = Field(
        default_factory=dict, description="Custom HTTP headers"
    )
    context_window: int | None = Field(None, description="Context window tokens")
    max_output_tokens: int | None = Field(None, description="Max output generation tokens")
    timeout: int | None = Field(300, description="Request timeout seconds")
    streaming: bool = Field(True, description="Enable streaming inference")
    is_active: bool = Field(False, description="Whether this profile is currently active")

    @field_validator("id", mode="before")
    @classmethod
    def _validate_id(cls, v: Any) -> str:
        if not v or not str(v).strip():
            return f"cloud-{uuid.uuid4().hex[:6]}"
        return str(v).strip()

    @field_validator("name", mode="before")
    @classmethod
    def _validate_name(cls, v: Any) -> str:
        if not v or not str(v).strip():
            return "Cloud Hosted Endpoint"
        return str(v).strip()

    @field_validator("api_base", mode="before")
    @classmethod
    def _validate_api_base(cls, v: Any) -> str:
        val = str(v or "").strip()
        if not val:
            raise ValueError("API Base URL is required")
        return val

    @field_validator("model", mode="before")
    @classmethod
    def _validate_model(cls, v: Any) -> str:
        val = str(v or "").strip()
        if not val:
            raise ValueError("Model identifier is required")
        return val

    @field_validator("api_key", mode="before")
    @classmethod
    def _validate_api_key(cls, v: Any) -> str | None:
        if v is None:
            return None
        val = str(v).strip()
        return val if val else None

    @field_validator("model_alias", mode="before")
    @classmethod
    def _validate_model_alias(cls, v: Any) -> str | None:
        if v is None:
            return None
        val = str(v).strip()
        return val if val else None

    @field_validator("extra_headers", mode="before")
    @classmethod
    def _validate_extra_headers(cls, v: Any) -> dict[str, str]:
        if not v:
            return {}
        if isinstance(v, dict):
            return {str(k): str(val) for k, val in v.items()}
        return {}

    @field_validator("context_window", "max_output_tokens", mode="before")
    @classmethod
    def _validate_optional_ints(cls, v: Any) -> int | None:
        if v is None or v == "":
            return None
        try:
            val = int(v)
            return val if val > 0 else None
        except (ValueError, TypeError):
            return None

    @field_validator("timeout", mode="before")
    @classmethod
    def _validate_timeout(cls, v: Any) -> int:
        if v is None or v == "":
            return 300
        try:
            val = int(v)
            return val if val > 0 else 300
        except (ValueError, TypeError):
            return 300

    @field_validator("streaming", "is_active", mode="before")
    @classmethod
    def _validate_bools(cls, v: Any, info: Any) -> bool:
        if v is None:
            return True if info.field_name == "streaming" else False
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return bool(v)


class CloudHostedProfileSafe(BaseModel):
    """Safe representation of Cloud Hosted profile with credentials masked."""

    id: str
    name: str
    api_base: str
    has_api_key: bool
    masked_api_key: str
    model: str
    model_alias: str | None = None
    extra_headers: dict[str, str] | None = Field(default_factory=dict)
    context_window: int | None = None
    max_output_tokens: int | None = None
    timeout: int | None = 300
    streaming: bool = True
    is_active: bool = False


class CloudToolCallDiagnostic(BaseModel):
    """Diagnostic detail for structured tool/function calling verification."""

    supported: bool = False
    tool_call_generated: bool = False
    tool_name: str | None = None
    arguments_parsed: bool = False
    arguments: dict[str, Any] | None = None
    multi_turn_continuation: bool = False
    error_recovery: bool = False
    streaming_compatible: bool = False
    error: str | None = None
    details: str | None = None


class CloudTestConnectionResponse(BaseModel):
    """Result of validating cloud hosted endpoint reachability and latency."""

    status: Literal["configured", "invalid_credentials", "unreachable", "error"] = "configured"
    message: str = ""
    valid: bool = False
    models: list[str] = Field(default_factory=list)
    chat_completion_ok: bool = False
    latency_ms: float | None = None
    ttft_ms: float | None = None
    duration_ms: float | None = None
    tokens_per_second: float | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class ResumeRunRequest(BaseModel):
    """Request to resume an interrupted or provider-blocked run."""

    model: str | None = None
    provider: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    max_turns: int | None = None
    additional_authorized_hosts: list[str] | None = Field(
        default=None,
        description="Optional additional authorized hostnames or subdomains to add to scope on resume",
    )

    @field_validator("additional_authorized_hosts", mode="before")
    @classmethod
    def validate_additional_authorized_hosts(cls, v: Any) -> list[str] | None:
        if v is None:
            return None
        items: list[str] = []
        if isinstance(v, str):
            parts = [p.strip() for p in re.split(r"[\n,]+", v) if p.strip()]
            items = parts
        elif isinstance(v, (list, tuple, set)):
            items = [str(x).strip() for x in v if str(x).strip()]
        else:
            return None

        normalized: list[str] = []
        for item in items:
            norm = _normalize_host_entry(item)
            if norm not in normalized:
                normalized.append(norm)
        return normalized


class CloudVerifyToolsResponse(BaseModel):
    """Result of structured tool calling compatibility test."""

    status: Literal["supported", "unsupported", "error"] = "supported"
    message: str = ""
    valid: bool = False
    tool_diagnostics: CloudToolCallDiagnostic = Field(default_factory=CloudToolCallDiagnostic)


class CloudWarmupResponse(BaseModel):
    """Result of manual model warm-up action."""

    success: bool = False
    message: str = ""
    latency_ms: float | None = None
    duration_ms: float | None = None
    tokens_generated: int | None = None
    tokens_per_second: float | None = None
