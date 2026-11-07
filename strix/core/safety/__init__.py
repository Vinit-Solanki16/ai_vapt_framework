"""Safety controls, fail-closed scope validation, and engagement profiles."""

from __future__ import annotations

from .engagements import EngagementProfile, list_engagements, load_engagement
from .scope_validator import TargetValidationResult, validate_web_target


__all__ = [
    "EngagementProfile",
    "TargetValidationResult",
    "list_engagements",
    "load_engagement",
    "validate_web_target",
]
