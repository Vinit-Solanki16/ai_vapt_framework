"""Engagement profile management for authorized assessment scopes."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class EngagementProfile:
    id: str
    name: str
    authorized_hosts: List[str]
    allowed_ports: List[int]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_PROFILES: Dict[str, EngagementProfile] = {
    "default-local": EngagementProfile(
        id="default-local",
        name="Local Development & Lab",
        authorized_hosts=["localhost", "127.0.0.1", "::1", "host.docker.internal"],
        allowed_ports=[80, 443, 8000, 8080, 8888, 9191],
    )
}


def list_engagements() -> List[EngagementProfile]:
    return list(_PROFILES.values())


def load_engagement(engagement_id: str) -> Optional[EngagementProfile]:
    return _PROFILES.get(engagement_id)

