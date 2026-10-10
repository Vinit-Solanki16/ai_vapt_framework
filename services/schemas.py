"""API request/response models for the decision engine backend."""
from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    """Request to start a new decision engine run."""
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
        "for ollama. Never persisted or echoed back in responses.",
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
    use_nmap: bool = Field(True, description="Run Nmap discovery for web assessments")
    use_nuclei: bool = Field(True, description="Run Nuclei scan for web assessments")


class TargetValidateRequest(BaseModel):
    """Request to preflight an authorized web target (no scanning)."""
    target_url: str = Field(..., description="Web application URL to validate")


class TargetValidateResponse(BaseModel):
    """Preflight result for a web target."""
    authorized: bool
    authorization_status: str
    preflight_status: str
    reachable: bool
    target_url: Optional[str] = None
    resolved_host: Optional[str] = None
    port: Optional[int] = None
    http_status: Optional[int] = None
    detail: str = ""


class RunResponse(BaseModel):
    """Response after starting a run."""
    run_id: str
    status: str
    message: str


class RunStatus(BaseModel):
    """Status of a run."""
    run_id: str
    status: Literal["pending", "running", "completed", "failed", "paused"]
    scenario: Optional[str] = None
    mode: str = "simulation"
    final_status: Optional[str] = None
    total_attempts: int = 0
    pivot_count: int = 0
    candidates_processed: List[str] = []


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
