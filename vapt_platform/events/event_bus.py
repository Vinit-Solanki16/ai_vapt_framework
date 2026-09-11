"""EventBus for VAPT platform.

In-process pub/sub for lifecycle events.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Callable, Optional

from .models import Event, EventType, RunState, is_valid_transition


class EventBus:
    """In-process event bus for lifecycle events.
    
    Supports:
    - Publishing events
    - Subscribing handlers
    - Deterministic ordering
    - Run association
    - Safe handler failure behavior
    - Testability
    """

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[Callable[[Event], None]]] = defaultdict(list)
        self._global_subscribers: list[Callable[[Event], None]] = []
        self._events: list[Event] = []
        self._run_states: dict[str, RunState] = {}
        self._lock = threading.Lock()

    def subscribe(
        self,
        event_type: EventType,
        handler: Callable[[Event], None],
    ) -> None:
        """Subscribe a handler to a specific event type.
        
        Args:
            event_type: The event type to subscribe to
            handler: Callback function that receives Event
        """
        with self._lock:
            self._subscribers[event_type].append(handler)

    def subscribe_all(self, handler: Callable[[Event], None]) -> None:
        """Subscribe a handler to all events.
        
        Args:
            handler: Callback function that receives Event
        """
        with self._lock:
            self._global_subscribers.append(handler)

    def unsubscribe(
        self,
        event_type: EventType,
        handler: Callable[[Event], None],
    ) -> None:
        """Unsubscribe a handler from a specific event type.
        
        Args:
            event_type: The event type to unsubscribe from
            handler: The handler to remove
        """
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type] = [
                    h for h in self._subscribers[event_type] if h != handler
                ]

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers.
        
        Args:
            event: The event to publish
        """
        with self._lock:
            self._events.append(event)
            
            # Notify type-specific subscribers
            handlers = list(self._subscribers.get(event.event_type, []))
            global_handlers = list(self._global_subscribers)
        
        # Call handlers outside lock to prevent deadlocks
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                # Handler failures should not break the event bus
                pass
        
        for handler in global_handlers:
            try:
                handler(event)
            except Exception:
                pass

    def get_events(self, run_id: str | None = None) -> list[Event]:
        """Get all events, optionally filtered by run_id.
        
        Args:
            run_id: Optional run ID to filter by
            
        Returns:
            List of events
        """
        with self._lock:
            if run_id is None:
                return list(self._events)
            return [e for e in self._events if e.run_id == run_id]

    def get_run_state(self, run_id: str) -> Optional[RunState]:
        """Get the current state of a run.
        
        Args:
            run_id: The run ID
            
        Returns:
            Current run state, or None if run not found
        """
        with self._lock:
            return self._run_states.get(run_id)

    def set_run_state(self, run_id: str, state: RunState) -> None:
        """Set the state of a run.
        
        Args:
            run_id: The run ID
            state: The new state
        """
        with self._lock:
            self._run_states[run_id] = state

    def clear(self) -> None:
        """Clear all events and state. Useful for testing."""
        with self._lock:
            self._events.clear()
            self._run_states.clear()


# Global event bus instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def set_event_bus(event_bus: EventBus) -> None:
    """Set the global event bus instance."""
    global _event_bus
    _event_bus = event_bus
