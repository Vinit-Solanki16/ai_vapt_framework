"""Canonical execution event system for VAPT platform.

Provides:
- RunState: canonical run lifecycle states
- Event: immutable event records
- EventBus: in-process pub/sub for lifecycle events
- EventPublisher: helper for publishing events from application code

Architecture:
    VAPTApplication ──> EventBus ──> subscribers
"""
from __future__ import annotations

from .models import RunState, Event, EventType
from .event_bus import EventBus, get_event_bus, set_event_bus
from .publisher import EventPublisher

__all__ = [
    "RunState",
    "Event",
    "EventType",
    "EventBus",
    "get_event_bus",
    "set_event_bus",
    "EventPublisher",
]
