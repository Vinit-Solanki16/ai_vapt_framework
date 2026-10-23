"""API request/response models for the decision engine backend."""
from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    """Request to start a new decision engine run.

    Security: the runtime OpenRouter credential is NOT carried in this body.
    It arrives in the ``X-OpenRouter-API-Key`` request header and is read
    directly off the FastAPI request, so a serialized request payload — which
    may be logged, stored or replayed — never contains a secret.
    ``assessor_api_key`` remains only for CLI/automation callers that
    deliberately pass a key in-body; it is never persisted or echoed back.
    """
    scenario: str = Field("failure_pivot", description="Scenario name")
    max_attempts: int = Field(2, ge=1, le=10, description="Max attempts per candidate before pivot")
    mode: Literal["simulation", "lab", "web"] = Field("simulation", description="Execution mode")
    target: Optional[str] = Field(None, description="Lab target IP (required for lab mode)")
    port: int = Field(8080, ge=1, le=65535, description="Lab target port")
    path: str = Field("/vuln", description="Lab target path")
    assessor: Literal["deterministic", "llm"] = Field("deterministic", description="Assessor type")
    assessor_provider: Literal["ollama", "openrouter", "openai"] = Field(
        "ollama",
        description="AI provider. 'ollama' is the local/default path; "
        "'openrouter' and 'openai' are optional hosted providers that "
        "require their respective API key to be set.",
    )
    assessor_api_key: Optional[str] = Field(
        None,
        description="Hosted-provider API key (openrouter/openai). Optional "
        "for ollama. Prefer the X-OpenRouter-API-Key header instead: it keeps "
        "the secret out of the request body. Never persisted or echoed back "
        "in responses.",
    )
    assessor_model: Optional[str] = Field(
        None,
        description="Explicit assessor model name (optional). None -> provider "
        "default (llama3.2:3b for ollama, the official thesis baseline; the "
        "configured hosted default for openrouter/openai). "
        "qwen2.5:3b is the Phase 33A experimental comparison arm.",
    )
    scan_file: Optional[str] = Field(None, description="Path to scan file (overrides scenario)")
    assessment_type: Literal["scenario", "web"] = Field("scenario", description="Assessment type")
    target_url: Optional[str] = Field(None, description="Authorized web target URL (required for web assessments)")
    target_scope_acknowledged: bool = Field(
        False,
        description="Explicit per-assessment acknowledgement that an EXTERNAL "
        "(non-local) web target is covered by the operator's authorization. "
        "Required for external VAPT_AUTHORIZED_WEB_SCOPES targets. Supplements "
        "— never replaces — the configured backend allowlist.",
    )
    use_nmap: bool = Field(True, description="Run Nmap discovery for web assessments")
    use_nuclei: bool = True
    engagement_id: Optional[str] = Field(None, description="Optional saved engagement profile ID")


class OpenRouterValidateRequest(BaseModel):
    """Optional body for the OpenRouter credential check.

    Carries the model to check for availability. Deliberately has NO API-key
    field: the credential arrives in the ``X-OpenRouter-API-Key`` header.
    """
    model: Optional[str] = Field(
        None,
        description="Model ID to check against the live catalogue (optional).",
    )


class OpenRouterModelInfo(BaseModel):
    """One catalogue entry, shaped for the selector (never contains a key)."""
    id: str
    name: str
    free: bool
    paid: bool = False
    context_length: Optional[int] = None
    pricing: dict = Field(default_factory=dict)


class OpenRouterValidateResponse(BaseModel):
    """Result of validating a runtime OpenRouter credential.

    Never contains the key itself — only configuration state, an actionable
    message, and catalogue data for the model selector.
    """
    status: Literal[
        "not_configured", "validating", "configured", "invalid_credentials",
        "model_unavailable", "rate_limited", "unreachable",
    ]
    message: str = ""
    model: Optional[str] = None
    model_available: Optional[bool] = None
    catalogue_count: int = 0
    models: List[OpenRouterModelInfo] = []


class TargetValidateRequest(BaseModel):
    """Request to preflight an authorized web target (no scanning)."""
    target_url: str = Field(..., description="Web application URL to validate")
    engagement_id: Optional[str] = Field(None, description="Optional engagement profile ID to validate against")


class TargetValidateResponse(BaseModel):
    """Preflight result for a web target.

    Populated only after the BACKEND has completed hostname authorization,
    port authorization and resolved-address validation — the UI never
    shows an authorized state that the backend has not confirmed.
    """
    authorized: bool
    authorization_status: str
    preflight_status: str
    reachable: bool
    target_url: Optional[str] = None
    resolved_host: Optional[str] = None
    port: Optional[int] = None
    http_status: Optional[int] = None
    detail: str = ""
    # Scope transparency (configurable authorized web scopes).
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
    redirect: Optional[dict] = None
    engagement_id: Optional[str] = None
    engagement_name: Optional[str] = None
    authorization_reference: Optional[str] = None
    engagement_snapshot: Optional[dict] = None


class RunResponse(BaseModel):
    """Immediate response after a run is accepted by the worker queue."""
    run_id: str
    status: Literal["queued", "running", "completed", "failed"]
    message: str


class RunStatus(BaseModel):
    """Observable asynchronous run state and completed-run data."""
    run_id: str
    status: Literal["queued", "running", "completed", "failed"]
    scenario: Optional[str] = None
    mode: str = "simulation"
    final_status: Optional[str] = None
    total_attempts: int = 0
    pivot_count: int = 0
    candidates_processed: List[str] = Field(default_factory=list)
    evidence_tier: Optional[str] = None
    assessment: dict = Field(default_factory=dict)
    candidates: List[dict] = Field(default_factory=list)
    execution_results: List[dict] = Field(default_factory=list)
    decision_trace: List[str] = Field(default_factory=list)
    service_discovery: List[dict] = Field(default_factory=list)
    report: dict = Field(default_factory=dict)
    error: Optional[str] = None
    updated_at: Optional[str] = None


class TraceEvent(BaseModel):
    """A single event in the decision trace."""
    phase: str
    candidate_id: Optional[str] = None
    attempt: Optional[int] = None
    max_attempts: Optional[int] = None
    outcome: Optional[str] = None
    detail: Optional[str] = None


class RunTrace(BaseModel):
    """Full decision trace for a run."""
    run_id: str
    events: List[TraceEvent] = []


class ReportResponse(BaseModel):
    """JSON report for a run."""
    run_id: str
    scenario: Optional[str] = None
    execution_mode: str = "simulation"
    final_status: Optional[str] = None
    candidates: List[dict] = []
    execution_results: List[dict] = []
    decision_trace: List[str] = []
    total_attempts: int = 0
    pivot_count: int = 0
    candidates_processed: List[str] = []
    safety_notice: str = ""


class CheckpointResponse(BaseModel):
    """Response after saving a checkpoint."""
    run_id: str
    path: str
    message: str


class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    detail: Optional[str] = None


class EngagementProfileSchema(BaseModel):
    """Schema for creating or updating an engagement profile."""
    id: Optional[str] = Field(None, description="Unique profile ID (generated if omitted)")
    name: str = Field(..., description="Engagement name")
    description: str = Field("", description="Description of the engagement")
    authorized_hosts: List[str] = Field(..., description="List of authorized hostnames or IP addresses")
    allowed_ports: List[int] = Field(..., description="List of allowed TCP ports")
    permitted_paths: List[str] = Field(default_factory=list, description="Optional permitted URL path prefixes")
    authorization_reference: str = Field(..., description="Authorization document, ticket or RoE reference")
    expires_at: Optional[str] = Field(None, description="Optional scope expiry ISO timestamp")
    scanner_policy: str = Field("safe_non_destructive", description="Scanner profile policy")
    status: str = Field("active", description="Status: 'active' or 'inactive'")


class TargetValidationRequest(BaseModel):
    """Request to validate a target URL against scopes and engagements."""
    target_url: str = Field(..., description="Target URL to validate")
    engagement_id: Optional[str] = Field(None, description="Optional engagement profile ID to validate against")
