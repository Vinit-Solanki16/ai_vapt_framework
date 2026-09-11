"""Tests for execution event system."""
from __future__ import annotations

import pytest

from vapt_platform.events import (
    RunState,
    Event,
    EventType,
    EventBus,
    EventPublisher,
    get_event_bus,
    set_event_bus,
)
from vapt_platform.events.models import is_valid_transition


# ---------------------------------------------------------------------------
# RunState tests
# ---------------------------------------------------------------------------

class TestRunState:
    def test_create_state(self):
        state = RunState.CREATED
        assert state == RunState.CREATED

    def test_all_states_exist(self):
        assert RunState.CREATED
        assert RunState.INGESTING
        assert RunState.NORMALIZING
        assert RunState.ASSESSING
        assert RunState.PLANNING
        assert RunState.EXECUTING
        assert RunState.VERIFYING
        assert RunState.REPORTING
        assert RunState.COMPLETED
        assert RunState.FAILED
        assert RunState.CANCELLED


# ---------------------------------------------------------------------------
# Event tests
# ---------------------------------------------------------------------------

class TestEvent:
    def test_create_event(self):
        event = Event(
            run_id="run-123",
            event_type=EventType.RUN_CREATED,
        )
        assert event.run_id == "run-123"
        assert event.event_type == EventType.RUN_CREATED
        assert event.event_id is not None
        assert event.timestamp is not None

    def test_event_with_payload(self):
        event = Event(
            run_id="run-123",
            event_type=EventType.EXECUTION_STARTED,
            payload={"candidate_count": 5},
        )
        assert event.payload["candidate_count"] == 5

    def test_to_dict(self):
        event = Event(
            run_id="run-123",
            event_type=EventType.RUN_CREATED,
        )
        d = event.to_dict()
        assert d["run_id"] == "run-123"
        assert d["event_type"] == EventType.RUN_CREATED.value
        assert "event_id" in d
        assert "timestamp" in d


# ---------------------------------------------------------------------------
# State transition tests
# ---------------------------------------------------------------------------

class TestStateTransitions:
    def test_valid_transitions(self):
        assert is_valid_transition(RunState.CREATED, RunState.INGESTING)
        assert is_valid_transition(RunState.INGESTING, RunState.NORMALIZING)
        assert is_valid_transition(RunState.NORMALIZING, RunState.ASSESSING)
        assert is_valid_transition(RunState.ASSESSING, RunState.PLANNING)
        assert is_valid_transition(RunState.PLANNING, RunState.EXECUTING)
        assert is_valid_transition(RunState.EXECUTING, RunState.VERIFYING)
        assert is_valid_transition(RunState.VERIFYING, RunState.REPORTING)
        assert is_valid_transition(RunState.REPORTING, RunState.COMPLETED)

    def test_invalid_transitions(self):
        # Cannot skip states
        assert not is_valid_transition(RunState.CREATED, RunState.EXECUTING)
        # Cannot go backwards
        assert not is_valid_transition(RunState.EXECUTING, RunState.INGESTING)
        # Terminal states have no outgoing transitions
        assert not is_valid_transition(RunState.COMPLETED, RunState.EXECUTING)
        assert not is_valid_transition(RunState.FAILED, RunState.EXECUTING)

    def test_failure_transitions(self):
        # Can fail from any non-terminal state
        assert is_valid_transition(RunState.CREATED, RunState.FAILED)
        assert is_valid_transition(RunState.EXECUTING, RunState.FAILED)
        assert is_valid_transition(RunState.REPORTING, RunState.FAILED)


# ---------------------------------------------------------------------------
# EventBus tests
# ---------------------------------------------------------------------------

class TestEventBus:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.bus = EventBus()
        set_event_bus(self.bus)
        yield
        self.bus.clear()

    def test_subscribe_and_publish(self):
        received = []
        self.bus.subscribe(EventType.RUN_CREATED, lambda e: received.append(e))
        
        event = Event(run_id="run-1", event_type=EventType.RUN_CREATED)
        self.bus.publish(event)
        
        assert len(received) == 1
        assert received[0].run_id == "run-1"

    def test_multiple_subscribers(self):
        received1 = []
        received2 = []
        self.bus.subscribe(EventType.RUN_CREATED, lambda e: received1.append(e))
        self.bus.subscribe(EventType.RUN_CREATED, lambda e: received2.append(e))
        
        event = Event(run_id="run-1", event_type=EventType.RUN_CREATED)
        self.bus.publish(event)
        
        assert len(received1) == 1
        assert len(received2) == 1

    def test_subscribe_all(self):
        received = []
        self.bus.subscribe_all(lambda e: received.append(e))
        
        event1 = Event(run_id="run-1", event_type=EventType.RUN_CREATED)
        event2 = Event(run_id="run-1", event_type=EventType.EXECUTION_STARTED)
        self.bus.publish(event1)
        self.bus.publish(event2)
        
        assert len(received) == 2

    def test_unsubscribe(self):
        received = []
        handler = lambda e: received.append(e)
        self.bus.subscribe(EventType.RUN_CREATED, handler)
        self.bus.unsubscribe(EventType.RUN_CREATED, handler)
        
        event = Event(run_id="run-1", event_type=EventType.RUN_CREATED)
        self.bus.publish(event)
        
        assert len(received) == 0

    def test_get_events(self):
        event1 = Event(run_id="run-1", event_type=EventType.RUN_CREATED)
        event2 = Event(run_id="run-2", event_type=EventType.RUN_CREATED)
        self.bus.publish(event1)
        self.bus.publish(event2)
        
        all_events = self.bus.get_events()
        assert len(all_events) == 2
        
        run1_events = self.bus.get_events("run-1")
        assert len(run1_events) == 1

    def test_handler_failure_isolation(self):
        """Handler failures should not break the bus."""
        received_good = []
        
        def bad_handler(e):
            raise RuntimeError("Handler error")
        
        def good_handler(e):
            received_good.append(e)
        
        self.bus.subscribe(EventType.RUN_CREATED, bad_handler)
        self.bus.subscribe(EventType.RUN_CREATED, good_handler)
        
        event = Event(run_id="run-1", event_type=EventType.RUN_CREATED)
        self.bus.publish(event)
        
        # Good handler should still receive event
        assert len(received_good) == 1

    def test_run_state(self):
        self.bus.set_run_state("run-1", RunState.CREATED)
        assert self.bus.get_run_state("run-1") == RunState.CREATED
        
        self.bus.set_run_state("run-1", RunState.EXECUTING)
        assert self.bus.get_run_state("run-1") == RunState.EXECUTING

    def test_clear(self):
        event = Event(run_id="run-1", event_type=EventType.RUN_CREATED)
        self.bus.publish(event)
        self.bus.set_run_state("run-1", RunState.CREATED)
        
        self.bus.clear()
        
        assert len(self.bus.get_events()) == 0
        assert self.bus.get_run_state("run-1") is None


# ---------------------------------------------------------------------------
# EventPublisher tests
# ---------------------------------------------------------------------------

class TestEventPublisher:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.bus = EventBus()
        set_event_bus(self.bus)
        yield
        self.bus.clear()

    def test_emit(self):
        publisher = EventPublisher("run-1", self.bus)
        event = publisher.emit(EventType.RUN_CREATED, {"scenario": "success"})
        
        assert event.run_id == "run-1"
        assert event.event_type == EventType.RUN_CREATED
        assert event.payload["scenario"] == "success"

    def test_transition_to(self):
        publisher = EventPublisher("run-1", self.bus)
        publisher.transition_to(RunState.CREATED)
        
        assert self.bus.get_run_state("run-1") == RunState.CREATED


# ---------------------------------------------------------------------------
# Application integration tests
# ---------------------------------------------------------------------------

class TestApplicationEvents:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.bus = EventBus()
        set_event_bus(self.bus)
        yield
        self.bus.clear()

    def test_run_emits_events(self):
        from vapt_platform.application import VAPTApplication, VAPTRequest
        
        app = VAPTApplication()
        req = VAPTRequest(
            scenario="success",
            mode="simulation",
            max_attempts=2,
            assessor_mode="deterministic",
        )
        result = app.run(req)
        
        # Should have emitted events
        events = self.bus.get_events(result.domain.run_id)
        assert len(events) > 0
        
        # First event should be RUN_CREATED
        assert events[0].event_type == EventType.RUN_CREATED
        
        # Last event should be RUN_COMPLETED or RUN_FAILED
        assert events[-1].event_type in (EventType.RUN_COMPLETED, EventType.RUN_FAILED)

    def test_run_state_transitions(self):
        from vapt_platform.application import VAPTApplication, VAPTRequest
        
        app = VAPTApplication()
        req = VAPTRequest(
            scenario="success",
            mode="simulation",
            max_attempts=2,
            assessor_mode="deterministic",
        )
        result = app.run(req)
        
        # Final state should be COMPLETED or FAILED
        final_state = self.bus.get_run_state(result.domain.run_id)
        assert final_state in (RunState.COMPLETED, RunState.FAILED)

    def test_event_ordering(self):
        from vapt_platform.application import VAPTApplication, VAPTRequest
        
        app = VAPTApplication()
        req = VAPTRequest(
            scenario="success",
            mode="simulation",
            max_attempts=2,
            assessor_mode="deterministic",
        )
        result = app.run(req)
        
        events = self.bus.get_events(result.domain.run_id)
        event_types = [e.event_type for e in events]
        
        # RUN_CREATED should come before RUN_COMPLETED
        created_idx = event_types.index(EventType.RUN_CREATED)
        completed_idx = event_types.index(EventType.RUN_COMPLETED)
        assert created_idx < completed_idx
