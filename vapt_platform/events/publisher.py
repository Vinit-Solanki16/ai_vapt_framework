"""EventPublisher helper for VAPT platform.

Provides a convenient interface for publishing lifecycle events
from application code.
"""
from __future__ import annotations

from typing import Any, Optional

from .models import Event, EventType, RunState
from .event_bus import EventBus, get_event_bus


class EventPublisher:
    """Helper for publishing lifecycle events.
    
    Usage:
        publisher = EventPublisher(run_id="run-123", event_bus=get_event_bus())
        publisher.emit(EventType.RUN_CREATED)
        publisher.emit(EventType.EXECUTION_STARTED, {"candidate_id": "c1"})
    """

    def __init__(
        self,
        run_id: str,
        event_bus: EventBus | None = None,
    ) -> None:
        self._run_id = run_id
        self._event_bus = event_bus or get_event_bus()

    def emit(
        self,
        event_type: EventType,
        payload: dict[str, Any] | None = None,
    ) -> Event:
        """Emit an event.
        
        Args:
            event_type: The type of event
            payload: Optional event payload
            
        Returns:
            The emitted Event
        """
        event = Event(
            run_id=self._run_id,
            event_type=event_type,
            payload=payload or {},
        )
        self._event_bus.publish(event)
        return event

    def transition_to(self, state: RunState) -> None:
        """Transition the run to a new state.
        
        Args:
            state: The new state
        """
        self._event_bus.set_run_state(self._run_id, state)

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus
