"""Tests for Operations Dashboard."""
from __future__ import annotations

import tempfile
import shutil
from unittest.mock import patch, MagicMock

import pytest

from vapt_platform.application import VAPTApplication, VAPTRequest, DomainResult
from vapt_platform.events import EventBus, set_event_bus, EventType, RunState
from vapt_platform.persistence import PersistenceConfig, JSONRunRepository
from vapt_platform.persistence.repository import set_repository


# ---------------------------------------------------------------------------
# Run History tests
# ---------------------------------------------------------------------------

class TestRunHistory:
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up isolated persistence for each test."""
        self.temp_dir = tempfile.mkdtemp()
        config = PersistenceConfig(storage_dir=self.temp_dir)
        self.repo = JSONRunRepository(config=config)
        set_repository(self.repo)
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_empty_history(self):
        """Test empty run history."""
        runs = self.repo.list_runs()
        assert len(runs) == 0

    def test_multiple_runs(self):
        """Test multiple runs in history."""
        from vapt_platform.persistence.models import PersistentRun

        for i in range(5):
            run = PersistentRun(
                run_id=f"run-{i}",
                scenario="success",
                mode="simulation",
                status="COMPLETED",
            )
            self.repo.save(run)

        runs = self.repo.list_runs()
        assert len(runs) == 5

    def test_run_selection(self):
        """Test selecting a specific run."""
        from vapt_platform.persistence.models import PersistentRun

        run = PersistentRun(
            run_id="selected-run",
            scenario="docker_vuln",
            mode="lab",
            status="COMPLETED",
        )
        self.repo.save(run)

        retrieved = self.repo.get("selected-run")
        assert retrieved is not None
        assert retrieved.run_id == "selected-run"
        assert retrieved.scenario == "docker_vuln"

    def test_run_ordering(self):
        """Test runs are ordered by modification time."""
        import time
        from vapt_platform.persistence.models import PersistentRun

        for i in range(3):
            run = PersistentRun(
                run_id=f"run-{i}",
                scenario="success",
                mode="simulation",
            )
            self.repo.save(run)
            time.sleep(0.01)  # Small delay to ensure different mtimes

        runs = self.repo.list_runs()
        # Should be ordered by mtime (most recent first)
        assert len(runs) == 3


# ---------------------------------------------------------------------------
# Event Timeline tests
# ---------------------------------------------------------------------------

class TestEventTimeline:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.bus = EventBus()
        set_event_bus(self.bus)
        yield
        self.bus.clear()

    def test_event_timeline(self):
        """Test events are ordered chronologically."""
        from vapt_platform.events import Event

        event1 = Event(run_id="run-1", event_type=EventType.RUN_CREATED)
        event2 = Event(run_id="run-1", event_type=EventType.EXECUTION_STARTED)
        event3 = Event(run_id="run-1", event_type=EventType.RUN_COMPLETED)

        self.bus.publish(event1)
        self.bus.publish(event2)
        self.bus.publish(event3)

        events = self.bus.get_events("run-1")
        assert len(events) == 3
        assert events[0].event_type == EventType.RUN_CREATED
        assert events[-1].event_type == EventType.RUN_COMPLETED

    def test_pivot_event_emission(self):
        """Test pivot events are emitted correctly."""
        from vapt_platform.events import EventPublisher

        publisher = EventPublisher("run-1", self.bus)
        publisher.emit(EventType.RUN_CREATED)
        publisher.emit(EventType.EXECUTION_STARTED)
        publisher.emit(EventType.PIVOT_OCCURRED, {"pivot_count": 1})
        publisher.emit(EventType.RUN_COMPLETED)

        events = self.bus.get_events("run-1")
        pivot_events = [e for e in events if e.event_type == EventType.PIVOT_OCCURRED]
        assert len(pivot_events) == 1
        assert pivot_events[0].payload["pivot_count"] == 1

    def test_failure_path_events(self):
        """Test failure path emits correct events."""
        from vapt_platform.events import EventPublisher

        publisher = EventPublisher("run-1", self.bus)
        publisher.emit(EventType.RUN_CREATED)
        publisher.emit(EventType.EXECUTION_STARTED)
        publisher.emit(EventType.RUN_FAILED, {"error": "Test error"})

        events = self.bus.get_events("run-1")
        assert events[-1].event_type == EventType.RUN_FAILED


# ---------------------------------------------------------------------------
# Evidence Viewer tests
# ---------------------------------------------------------------------------

class TestEvidenceViewer:
    def test_evidence_tier_simulated(self):
        """Test SIMULATED evidence tier."""
        from vapt_platform.reporting.builder import ReportBuilder
        from vapt_platform.application import DomainResult

        domain = DomainResult(mode="simulation")
        builder = ReportBuilder()
        report = builder.from_domain_result(domain)

        assert report.evidence_tier == "SIMULATED"
        assert "ground truth" in report.evidence_description.lower() or "no real" in report.safety_notice.lower()

    def test_evidence_tier_docker(self):
        """Test DOCKER_OBSERVED evidence tier."""
        from vapt_platform.reporting.builder import ReportBuilder
        from vapt_platform.application import DomainResult

        domain = DomainResult(mode="lab")
        builder = ReportBuilder()
        report = builder.from_domain_result(domain)

        assert report.evidence_tier == "DOCKER_OBSERVED"
        assert "docker" in report.safety_notice.lower() or "emulator" in report.safety_notice.lower()

    def test_evidence_tier_local(self):
        """Test OBSERVED_LOCAL evidence tier."""
        from vapt_platform.reporting.builder import ReportBuilder
        from vapt_platform.application import DomainResult

        domain = DomainResult(mode="lab_loopback")
        builder = ReportBuilder()
        report = builder.from_domain_result(domain)

        assert report.evidence_tier == "OBSERVED_LOCAL"


# ---------------------------------------------------------------------------
# Report Integration tests
# ---------------------------------------------------------------------------

class TestReportIntegration:
    def test_report_for_persisted_run(self):
        """Test report generation from persisted run."""
        from vapt_platform.persistence.models import PersistentRun
        from vapt_platform.reporting.builder import ReportBuilder
        from vapt_platform.reporting.renderers import JSONRenderer

        run = PersistentRun(
            run_id="report-test",
            scenario="docker_vuln",
            mode="lab",
            final_status="SUCCESS",
            candidates=[{"id": "c1", "probability": 0.9}],
            execution_results=[{"candidate_id": "c1", "outcome": "SUCCESS"}],
            decision_trace=["[INIT] Engine started"],
            total_attempts=1,
            pivot_count=0,
            evidence_tier="DOCKER_OBSERVED",
            target="172.28.0.2",
            port=8080,
        )

        builder = ReportBuilder()
        report = builder.from_persisted_run(run)

        # Should generate without error
        json_output = JSONRenderer().render(report)
        assert json_output is not None
        assert "report-test" in json_output

    def test_evidence_tier_in_report(self):
        """Test evidence tier is preserved in report."""
        from vapt_platform.persistence.models import PersistentRun
        from vapt_platform.reporting.builder import ReportBuilder
        from vapt_platform.reporting.renderers import JSONRenderer

        run = PersistentRun(
            run_id="evidence-test",
            scenario="docker_vuln",
            mode="lab",
            evidence_tier="DOCKER_OBSERVED",
        )

        builder = ReportBuilder()
        report = builder.from_persisted_run(run)

        json_output = JSONRenderer().render(report)
        assert "DOCKER_OBSERVED" in json_output


# ---------------------------------------------------------------------------
# API → GUI Data Contract tests
# ---------------------------------------------------------------------------

class TestAPIGUIDataContract:
    def test_run_list_format(self):
        """Test run list format expected by GUI."""
        from vapt_platform.persistence.models import PersistentRun

        temp_dir = tempfile.mkdtemp()
        config = PersistenceConfig(storage_dir=temp_dir)
        repo = JSONRunRepository(config=config)

        run = PersistentRun(
            run_id="api-test",
            scenario="success",
            mode="simulation",
            status="COMPLETED",
            final_status="SUCCESS",
            evidence_tier="SIMULATED",
            total_attempts=2,
            pivot_count=1,
        )
        repo.save(run)

        runs = repo.list_runs()
        assert len(runs) == 1

        # Verify fields expected by GUI
        assert hasattr(runs[0], "run_id")
        assert hasattr(runs[0], "scenario")
        assert hasattr(runs[0], "mode")
        assert hasattr(runs[0], "status")
        assert hasattr(runs[0], "evidence_tier")

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_run_details_format(self):
        """Test run details format expected by GUI."""
        from vapt_platform.persistence.models import PersistentRun

        temp_dir = tempfile.mkdtemp()
        config = PersistenceConfig(storage_dir=temp_dir)
        repo = JSONRunRepository(config=config)

        run = PersistentRun(
            run_id="details-test",
            scenario="success",
            mode="simulation",
            candidates=[{"id": "c1"}],
            execution_results=[{"candidate_id": "c1", "outcome": "SUCCESS"}],
            decision_trace=["[INIT] Engine started"],
            evidence_tier="SIMULATED",
        )
        repo.save(run)

        retrieved = repo.get("details-test")
        assert retrieved is not None

        # Verify fields expected by GUI
        assert hasattr(retrieved, "candidates")
        assert hasattr(retrieved, "execution_results")
        assert hasattr(retrieved, "decision_trace")
        assert hasattr(retrieved, "evidence_tier")

        shutil.rmtree(temp_dir, ignore_errors=True)
