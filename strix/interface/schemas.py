"""API request/response schemas for STRIX AI-VAPT Gateway."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


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
    assessor_provider: Literal["ollama", "google", "openrouter", "openai"] = Field("ollama", description="AI provider")
    assessor_model: Optional[str] = Field("qwen2.5:1.5b", description="Model identifier")
    assessor_api_key: Optional[str] = Field(None, description="Runtime API key (in-memory only, never persisted)")
    scan_file: Optional[str] = Field(None, description="Optional scan file override")
    assessment_type: Literal["scenario", "web", "strix_autonomous"] = Field("scenario", description="Assessment type")
    use_nmap: bool = Field(True, description="Run Nmap discovery")
    use_nuclei: bool = Field(True, description="Run Nuclei scanner")
    engagement_id: Optional[str] = Field(None, description="Optional engagement profile ID")
    scan_mode: Optional[str] = Field("deep", description="Strix scan mode (quick, standard, deep)")
    max_turns: Optional[int] = Field(100, description="Max execution turns for deep/autonomous scanning (up to 500)")


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
    status: Literal["not_configured", "validating", "configured", "invalid_credentials", "rate_limited", "unreachable", "error"]
    message: str = ""
    valid: bool = False
    catalogue_count: int = 0
    models: List[OpenRouterModelInfo] = Field(default_factory=list)


class SystemHealthResponse(BaseModel):
    """System components health report."""
    status: Literal["READY", "DEGRADED", "OFFLINE"]
    timestamp: str = Field(default_factory=_utc_now)
    components: Dict[str, Any] = Field(default_factory=dict)
