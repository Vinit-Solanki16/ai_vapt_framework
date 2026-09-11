"""Tests for professional reporting pipeline."""
from __future__ import annotations

import json
import pytest

from vapt_platform.reporting.models import (
    ReportModel,
    ReportMetadata,
    CandidateReport,
    ExecutionReport,
    PivotEvent,
    EvidenceTier,
)
from vapt_platform.reporting.builder import ReportBuilder
from vapt_platform.reporting.renderers import (
    JSONRenderer,
    HTMLRenderer,
    MarkdownRenderer,
    TXTRenderer,
    get_renderer,
)


# ---------------------------------------------------------------------------
# ReportModel tests
# ---------------------------------------------------------------------------

class TestReportModel:
    def test_create_report(self):
        report = ReportModel()
        assert report.metadata is not None
        assert report.evidence_tier == EvidenceTier.SIMULATED.value

    def test_to_dict(self):
        report = ReportModel(
            metadata=ReportMetadata(run_id="test-123", scenario="success"),
        )
        d = report.to_dict()
        assert d["metadata"]["run_id"] == "test-123"
        assert d["metadata"]["scenario"] == "success"

    def test_to_dict_with_candidates(self):
        report = ReportModel(
            candidates=[
                CandidateReport(candidate_id="c1", probability=0.9),
            ],
        )
        d = report.to_dict()
        assert len(d["candidates"]) == 1
        assert d["candidates"][0]["candidate_id"] == "c1"


# ---------------------------------------------------------------------------
# ReportBuilder tests
# ---------------------------------------------------------------------------

class TestReportBuilder:
    def test_from_domain_result(self):
        from vapt_platform.application import DomainResult, VAPTRequest
        
        domain = DomainResult(
            run_id="test-123",
            scenario="success",
            mode="simulation",
            final_status="SUCCESS",
            candidates=[{"id": "c1", "probability": 0.9}],
            decision_trace=["[INIT] Engine started"],
            total_attempts=2,
            pivot_count=1,
            evidence_tier="SIMULATED",
        )
        request = VAPTRequest(scenario="success", mode="simulation")
        
        builder = ReportBuilder()
        report = builder.from_domain_result(domain, request)
        
        assert report.metadata.run_id == "test-123"
        assert report.metadata.scenario == "success"
        assert report.evidence_tier == EvidenceTier.SIMULATED.value
        assert len(report.candidates) == 1
        assert report.metadata.total_attempts == 2

    def test_from_persisted_run(self):
        from vapt_platform.persistence.models import PersistentRun
        
        run = PersistentRun(
            run_id="test-456",
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
        
        assert report.metadata.run_id == "test-456"
        assert report.metadata.scenario == "docker_vuln"
        assert report.evidence_tier == EvidenceTier.DOCKER_OBSERVED.value
        assert report.target == "172.28.0.2"
        assert len(report.execution_results) == 1

    def test_evidence_tier_simulated(self):
        from vapt_platform.application import DomainResult
        
        domain = DomainResult(mode="simulation")
        builder = ReportBuilder()
        report = builder.from_domain_result(domain)
        
        assert report.evidence_tier == EvidenceTier.SIMULATED.value
        assert "SIMULATION" in report.safety_notice

    def test_evidence_tier_docker(self):
        from vapt_platform.application import DomainResult
        
        domain = DomainResult(mode="lab")
        builder = ReportBuilder()
        report = builder.from_domain_result(domain)
        
        assert report.evidence_tier == EvidenceTier.DOCKER_OBSERVED.value
        assert "DOCKER" in report.safety_notice

    def test_limitations_present(self):
        from vapt_platform.application import DomainResult
        
        domain = DomainResult(mode="simulation")
        builder = ReportBuilder()
        report = builder.from_domain_result(domain)
        
        assert len(report.limitations) > 0
        assert any("research prototype" in lim for lim in report.limitations)


# ---------------------------------------------------------------------------
# Renderer tests
# ---------------------------------------------------------------------------

class TestRenderers:
    @pytest.fixture
    def sample_report(self):
        return ReportModel(
            metadata=ReportMetadata(
                run_id="test-123",
                scenario="success",
                mode="simulation",
                final_status="SUCCESS",
                max_attempts=2,
                total_attempts=2,
                pivot_count=1,
                candidates_processed=["c1"],
            ),
            executive_summary="Test run completed successfully.",
            candidates=[
                CandidateReport(
                    candidate_id="c1",
                    probability=0.9,
                    quality_rank="HIGH",
                    assessed=True,
                    attempted=True,
                    execution_outcome="SUCCESS",
                ),
            ],
            execution_results=[
                ExecutionReport(
                    candidate_id="c1",
                    outcome="SUCCESS",
                    detail="VULNERABLE",
                    attempt_number=1,
                ),
            ],
            decision_trace=["[INIT] Engine started", "[Pivot] Threshold reached"],
            pivot_events=[PivotEvent(event_type="ABANDON", details="Threshold reached")],
            attempts_per_candidate={"c1": 1},
            evidence_tier=EvidenceTier.SIMULATED.value,
            evidence_description="Simulated run",
            safety_notice="SIMULATION MODE",
            limitations=["This is a research prototype."],
        )

    def test_json_renderer(self, sample_report):
        renderer = JSONRenderer()
        output = renderer.render(sample_report)
        
        # Should be valid JSON
        data = json.loads(output)
        assert data["metadata"]["run_id"] == "test-123"
        assert data["evidence_tier"] == EvidenceTier.SIMULATED.value

    def test_html_renderer(self, sample_report):
        renderer = HTMLRenderer()
        output = renderer.render(sample_report)
        
        assert "<html" in output.lower()
        assert "success" in output  # scenario name
        assert EvidenceTier.SIMULATED.value in output

    def test_markdown_renderer(self, sample_report):
        renderer = MarkdownRenderer()
        output = renderer.render(sample_report)
        
        assert "# AI VAPT" in output
        assert "success" in output  # scenario name
        assert EvidenceTier.SIMULATED.value in output

    def test_txt_renderer(self, sample_report):
        renderer = TXTRenderer()
        output = renderer.render(sample_report)
        
        assert "AI VAPT" in output
        assert "success" in output  # scenario name
        assert EvidenceTier.SIMULATED.value in output

    def test_get_renderer(self):
        assert isinstance(get_renderer("json"), JSONRenderer)
        assert isinstance(get_renderer("html"), HTMLRenderer)
        assert isinstance(get_renderer("markdown"), MarkdownRenderer)
        assert isinstance(get_renderer("md"), MarkdownRenderer)
        assert isinstance(get_renderer("txt"), TXTRenderer)
        assert isinstance(get_renderer("text"), TXTRenderer)

    def test_get_renderer_invalid(self):
        with pytest.raises(ValueError):
            get_renderer("invalid")


# ---------------------------------------------------------------------------
# Evidence provenance tests
# ---------------------------------------------------------------------------

class TestEvidenceProvenance:
    def test_simulated_not_real(self):
        """SIMULATED runs must not claim real-world validation."""
        from vapt_platform.application import DomainResult
        
        domain = DomainResult(mode="simulation")
        builder = ReportBuilder()
        report = builder.from_domain_result(domain)
        
        # Should not contain real-world claims in executive summary
        assert "real-world" not in report.executive_summary.lower()
        # Safety notice should clarify no real vulnerabilities were validated
        assert "no real vulnerabilities" in report.safety_notice.lower()

    def test_docker_not_real_target(self):
        """DOCKER_OBSERVED runs must not claim real-world targets."""
        from vapt_platform.application import DomainResult
        
        domain = DomainResult(mode="lab")
        builder = ReportBuilder()
        report = builder.from_domain_result(domain)
        
        # Should clarify no external targets
        assert "no external" in report.safety_notice.lower() or "emulator" in report.safety_notice.lower()

    def test_no_fabricated_timestamps(self):
        """Reports should not fabricate timestamps that don't exist."""
        from vapt_platform.application import DomainResult
        
        domain = DomainResult(
            mode="simulation",
            decision_trace=[],  # No trace
        )
        builder = ReportBuilder()
        report = builder.from_domain_result(domain)
        
        # Should not invent execution details
        assert report.metadata.total_attempts == 0

    def test_missing_fields_handled(self):
        """Reports should handle missing/optional fields gracefully."""
        from vapt_platform.application import DomainResult
        
        domain = DomainResult(
            mode="simulation",
            candidates=[],
            execution_results=[],
            decision_trace=[],
        )
        builder = ReportBuilder()
        report = builder.from_domain_result(domain)
        
        # Should not raise
        assert len(report.candidates) == 0
        assert len(report.execution_results) == 0
        json_output = JSONRenderer().render(report)
        assert json_output is not None


# ---------------------------------------------------------------------------
# Persisted run reporting tests
# ---------------------------------------------------------------------------

class TestPersistedRunReporting:
    def test_report_from_persisted_run(self):
        """Reports should be generatable from persisted runs."""
        from vapt_platform.persistence.models import PersistentRun
        from vapt_platform.reporting.builder import ReportBuilder
        from vapt_platform.reporting.renderers import JSONRenderer
        
        run = PersistentRun(
            run_id="persisted-123",
            scenario="docker_vuln",
            mode="lab",
            final_status="SUCCESS",
            candidates=[{"id": "c1", "probability": 0.9}],
            execution_results=[{"candidate_id": "c1", "outcome": "SUCCESS", "detail": "VULNERABLE"}],
            decision_trace=["[INIT] Engine started"],
            total_attempts=1,
            pivot_count=0,
            evidence_tier="DOCKER_OBSERVED",
            target="172.28.0.2",
            port=8080,
            path="/vuln",
        )
        
        builder = ReportBuilder()
        report = builder.from_persisted_run(run)
        
        assert report.metadata.run_id == "persisted-123"
        assert report.target == "172.28.0.2"
        assert report.evidence_tier == EvidenceTier.DOCKER_OBSERVED.value
        
        # Should render without error
        json_output = JSONRenderer().render(report)
        data = json.loads(json_output)
        assert data["metadata"]["run_id"] == "persisted-123"

    def test_evidence_tier_preserved_after_reload(self):
        """Evidence tier must survive persist → reload → report cycle."""
        from vapt_platform.persistence.models import PersistentRun
        from vapt_platform.reporting.builder import ReportBuilder
        
        # Simulate a Docker run
        run = PersistentRun(
            run_id="docker-run-1",
            scenario="docker_vuln",
            mode="lab",
            evidence_tier="DOCKER_OBSERVED",
            final_status="SUCCESS",
        )
        
        # Build report from persisted run
        builder = ReportBuilder()
        report = builder.from_persisted_run(run)
        
        # Evidence tier must be preserved
        assert report.evidence_tier == EvidenceTier.DOCKER_OBSERVED.value
        assert "DOCKER" in report.safety_notice
