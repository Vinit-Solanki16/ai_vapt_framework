"""API request/response schemas for STRIX AI-VAPT Gateway."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
import uuid
from pydantic import BaseModel, Field, field_validator


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunRequest(BaseModel):
    """Request to start a new assessment run."""
    scenario: str = Field("default", description="Scenario or assessment name")
    max_attempts: int = Field(2, ge=1, le=10, description="Max attempts per candidate before pivot (GAP-2)")
    mode: Literal["simulation", "lab", "web", "web_controlled", "autonomous"] = Field("simulation", description="Execution mode")
    target: Optional[str] = Field(None, description="Target host or IP")
    port: int = Field(8080, ge=1, le=65535, description="Target port")
    path: str = Field("/", description="Target path")
    target_url: Optional[str] = Field(None, description="Authorized target URL for web assessments")
    target_scope_acknowledged: bool = Field(False, description="Explicit operator acknowledgement of target authorization")
    assessor: Literal["deterministic", "llm"] = Field("llm", description="Assessor type")
    assessor_provider: Literal["ollama", "google", "openrouter", "openai", "cloud_hosted", "custom"] = Field("ollama", description="AI provider")
    assessor_model: Optional[str] = Field("qwen2.5:1.5b", description="Model identifier")
    assessor_api_key: Optional[str] = Field(None, description="Runtime API key (in-memory only, never persisted)")
    scan_file: Optional[str] = Field(None, description="Optional scan file override")
    assessment_type: Literal["scenario", "web", "strix_autonomous"] = Field("scenario", description="Assessment type")
    use_nmap: bool = Field(True, description="Run Nmap discovery")
    use_nuclei: bool = Field(True, description="Run Nuclei scanner")
    engagement_id: Optional[str] = Field(None, description="Optional engagement profile ID")
    scan_mode: Optional[str] = Field("deep", description="Strix scan mode (quick, standard, deep)")
    max_turns: Optional[int] = Field(500, description="Max execution turns for autonomous scanning (50=quick, 100=standard, 250=deep, 500=default, 1000=thorough, or custom 1-1000)")
    instruction: Optional[str] = Field(None, description="Optional custom penetration testing instruction or objective")
    auth_config: Optional[Dict[str, Any]] = Field(None, description="Optional target authentication configuration")

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
    status: Literal["queued", "running", "completed", "failed", "aborted"] = "running"
    message: str = "Assessment initialized"
    created_at: str = Field(default_factory=_utc_now)


class PivotEventSchema(BaseModel):
    """GAP-2 decision pivot event."""
    timestamp: str = Field(default_factory=_utc_now)
    type: str  # INIT, ADVANCE, REDIRECT, ABANDON, COMPLETE
    candidate_id: Optional[str] = None
    attempt: Optional[int] = None
    max_attempts: Optional[int] = None
    reason: Optional[str] = None
    to_candidate: Optional[str] = None


class CandidateSchema(BaseModel):
    """Candidate vulnerability or exploit target (GAP-1 / GAP-2)."""
    id: str
    name: str
    target: str = ""
    severity: str = "medium"
    cvss_score: Optional[float] = None
    owasp_category: Optional[str] = None
    cwe_id: Optional[str] = None
    usability_rank: Optional[str] = None  # HIGH, MEDIUM, LOW
    exploit_viable: Optional[bool] = None
    reasoning: Optional[str] = None
    composite_score: Optional[float] = None
    attempts: int = 0
    max_attempts: int = 2
    state: str = "PENDING"  # PENDING, ATTEMPTING, VALIDATED, ABANDONED
    evidence_hash: Optional[str] = None


class RunStatus(BaseModel):
    """Observable asynchronous run state and real-time outputs."""
    run_id: str
    status: Literal["queued", "running", "completed", "failed", "aborted"]
    scenario: Optional[str] = None
    mode: Optional[str] = None
    target_url: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    events: List[Dict[str, Any]] = Field(default_factory=list)
    decision_trace: List[str] = Field(default_factory=list)
    pivot_events: List[Dict[str, Any]] = Field(default_factory=list)
    candidates: List[Dict[str, Any]] = Field(default_factory=list)
    findings: List[Dict[str, Any]] = Field(default_factory=list)
    stats: Dict[str, Any] = Field(default_factory=dict)
    summary: Dict[str, Any] = Field(default_factory=dict)
    progress: Optional[Dict[str, Any]] = None
    tech_stack: Optional[str] = None
    evidence_tier: Optional[str] = None
    safety_notice: Optional[str] = None
    target_ip: Optional[str] = None
    open_ports: List[Dict[str, Any]] = Field(default_factory=list)
    components: List[Dict[str, Any]] = Field(default_factory=list)
    scan_matrix: List[Dict[str, Any]] = Field(default_factory=list)
    spider_stats: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    max_turns: Optional[int] = None
    scan_mode: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    report_status: Optional[str] = None


class TargetValidateRequest(BaseModel):
    """Request to preflight an authorized web target."""
    target_url: str = Field(..., description="Web application URL to validate")
    engagement_id: Optional[str] = Field(None, description="Optional engagement profile ID")


class TargetValidateResponse(BaseModel):
    """Preflight target scope validation result."""
    authorized: bool
    authorization_status: str
    preflight_status: str
    reachable: bool
    target_url: Optional[str] = None
    resolved_host: Optional[str] = None
    port: Optional[int] = None
    http_status: Optional[int] = None
    detail: str = ""
    scheme: Optional[str] = None
    hostname: Optional[str] = None
    normalized_host: Optional[str] = None
    in_scope: Optional[bool] = None
    scope_kind: Optional[str] = None
    scope_entry: Optional[str] = None
    external_scope: Optional[bool] = None
    acknowledgement_required: Optional[bool] = None
    address_validation: Optional[str] = None
    resolved_ips: List[str] = Field(default_factory=list)
    engagement_id: Optional[str] = None
    engagement_name: Optional[str] = None


class GoogleValidateResponse(BaseModel):
    """Result of validating runtime Google Gemini credentials."""
    status: Literal["not_configured", "validating", "configured", "invalid_credentials", "unreachable", "error"]
    message: str
    valid: bool
    models: List[str] = Field(default_factory=list)


class OpenRouterModelInfo(BaseModel):
    """Catalogue entry for OpenRouter model selection."""
    id: str
    name: str
    free: bool = False
    context_length: Optional[int] = None


class OpenRouterValidateResponse(BaseModel):
    """Result of validating runtime OpenRouter credentials."""
    status: Literal["not_configured", "validating", "configured", "invalid_credentials", "rate_limited", "quota_exceeded", "unreachable", "error"]
    message: str = ""
    valid: bool = False
    catalogue_count: int = 0
    models: List[OpenRouterModelInfo] = Field(default_factory=list)


class OpenAIValidateResponse(BaseModel):
    """Result of validating custom OpenAI-compatible endpoint."""
    status: Literal["not_configured", "configured", "invalid_credentials", "rate_limited", "quota_exceeded", "unreachable", "error"] = "configured"
    message: str = ""
    valid: bool = False
    models: List[str] = Field(default_factory=list)


class SystemHealthResponse(BaseModel):
    """System components health report."""
    status: Literal["READY", "DEGRADED", "OFFLINE"]
    timestamp: str = Field(default_factory=_utc_now)
    components: Dict[str, Any] = Field(default_factory=dict)


class CloudHostedProfile(BaseModel):
    """Configuration profile for a Generic Cloud Hosted OpenAI-compatible provider."""
    id: Optional[str] = Field(default_factory=lambda: f"cloud-{uuid.uuid4().hex[:6]}", description="Unique profile identifier")
    name: str = Field("Cloud Hosted Endpoint", description="Friendly provider display name")
    api_base: str = Field(..., description="OpenAI-compatible Base URL")
    api_key: Optional[str] = Field(None, description="API Key or Bearer token (optional)")
    model: str = Field(..., description="Model identifier on server")
    model_alias: Optional[str] = Field(None, description="Friendly model display alias")
    extra_headers: Optional[Dict[str, str]] = Field(default_factory=dict, description="Custom HTTP headers")
    context_window: Optional[int] = Field(None, description="Context window tokens")
    max_output_tokens: Optional[int] = Field(None, description="Max output generation tokens")
    timeout: Optional[int] = Field(300, description="Request timeout seconds")
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
    def _validate_api_key(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        val = str(v).strip()
        return val if val else None

    @field_validator("model_alias", mode="before")
    @classmethod
    def _validate_model_alias(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        val = str(v).strip()
        return val if val else None

    @field_validator("extra_headers", mode="before")
    @classmethod
    def _validate_extra_headers(cls, v: Any) -> Dict[str, str]:
        if not v:
            return {}
        if isinstance(v, dict):
            return {str(k): str(val) for k, val in v.items()}
        return {}

    @field_validator("context_window", "max_output_tokens", mode="before")
    @classmethod
    def _validate_optional_ints(cls, v: Any) -> Optional[int]:
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
    def _validate_bools(cls, v: Any, info) -> bool:
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
    model_alias: Optional[str] = None
    extra_headers: Optional[Dict[str, str]] = Field(default_factory=dict)
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    timeout: Optional[int] = 300
    streaming: bool = True
    is_active: bool = False


class CloudToolCallDiagnostic(BaseModel):
    """Diagnostic detail for structured tool/function calling verification."""
    supported: bool = False
    tool_call_generated: bool = False
    tool_name: Optional[str] = None
    arguments_parsed: bool = False
    arguments: Optional[Dict[str, Any]] = None
    multi_turn_continuation: bool = False
    error_recovery: bool = False
    streaming_compatible: bool = False
    error: Optional[str] = None
    details: Optional[str] = None


class CloudTestConnectionResponse(BaseModel):
    """Result of validating cloud hosted endpoint reachability and latency."""
    status: Literal["configured", "invalid_credentials", "unreachable", "error"] = "configured"
    message: str = ""
    valid: bool = False
    models: List[str] = Field(default_factory=list)
    chat_completion_ok: bool = False
    latency_ms: Optional[float] = None
    ttft_ms: Optional[float] = None
    duration_ms: Optional[float] = None
    tokens_per_second: Optional[float] = None
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


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
    latency_ms: Optional[float] = None
    duration_ms: Optional[float] = None
    tokens_generated: Optional[int] = None
    tokens_per_second: Optional[float] = None

