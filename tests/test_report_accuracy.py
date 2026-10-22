"""Tests for Report Accuracy, Truthful Evidence Provenance, and AI Outcome Semantics.

Verifies:
  - EvidenceTier.OBSERVED_EXTERNAL applied to authorized external targets.
  - Dynamic, truthful target application labeling (never claims OWASP Juice Shop
    for pentest-ground.com).
  - Truthful safety notices (never claims 'no external systems were targeted' for
    external runs).
  - Explicit AI outcome semantics (DETERMINISTIC ASSESSMENT vs MODEL ASSESSED vs
    DETERMINISTIC FALLBACK).
  - Accurate candidate counters and inventory accounting (Nmap vs Nuclei vs
    actionable vs informational).
  - HTML, Markdown, and TXT report rendering of OBSERVED_EXTERNAL badge and
    provenance details.
"""
from __future__ import annotations

import pytest

from vapt_platform.reporting.models import (
    CandidateReport,
    EvidenceTier,
    ExecutionReport,
    ReportMetadata,
    ReportModel,
)
from vapt_platform.reporting.builder import ReportBuilder
from vapt_platform.reporting.renderers import (
    HTMLRenderer,
    JSONRenderer,
    MarkdownRenderer,
    TXTRenderer,
)


class TestReportEvidenceTierAndProvenance:
    def test_observed_external_tier_for_external_web_target(self):
        builder = ReportBuilder()
        run_record = {
            "run_id": "run-ext-001",
            "scenario": "web_target",
            "mode": "web",
            "assessment_type": "web",
            "target_url": "https://pentest-ground.com:4280/",
            "evidence_tier": "OBSERVED_EXTERNAL",
            "assessor_provider": "deterministic",
            "assessor_mode": "deterministic",
            "web": {
                "target_url": "https://pentest-ground.com:4280/",
                "is_external": True,
                "engagement_name": "Pentest Ground Authorized Lab",
                "authorization_reference": "ROE-2026-PG4280",
                "nmap": {"status": "COMPLETED", "finding_count": 2},
                "nuclei": {"status": "NOT AVAILABLE", "finding_count": 0},
            },
        }

        report = builder.from_persisted_run(run_record)
        assert report.evidence_tier == "OBSERVED_EXTERNAL"
        prov = report.web_provenance
        assert prov["environment"] == "AUTHORIZED EXTERNAL TARGET"
        # Never claims OWASP Juice Shop for pentest-ground.com
        assert "OWASP Juice Shop" not in prov["application"]
        assert "External" in prov["application"] or "Pentest Ground" in prov["application"]
        # Safety notice must state external systems were targeted under authorization
        assert "no external systems were targeted" not in report.safety_notice.lower()
        assert "authorized external target" in report.safety_notice.lower() or "external" in report.safety_notice.lower()

    def test_observed_local_tier_for_juice_shop(self):
        builder = ReportBuilder()
        run_record = {
            "run_id": "run-local-001",
            "scenario": "web_target",
            "mode": "web",
            "assessment_type": "web",
            "target_url": "http://127.0.0.1:9191",
            "evidence_tier": "OBSERVED_LOCAL",
            "assessor_provider": "deterministic",
            "assessor_mode": "deterministic",
            "web": {
                "target_url": "http://127.0.0.1:9191",
                "is_external": False,
                "nmap": {"status": "COMPLETED", "finding_count": 1},
                "nuclei": {"status": "NOT AVAILABLE", "finding_count": 0},
            },
        }

        report = builder.from_persisted_run(run_record)
        assert report.evidence_tier == "OBSERVED_LOCAL"
        prov = report.web_provenance
        assert "OWASP Juice Shop" in prov["application"]
        assert "LOCAL CONTROLLED" in prov["environment"]
        assert "no external systems were targeted" in report.safety_notice.lower()


class TestAiOutcomeSemantics:
    def test_deterministic_assessment_outcome(self):
        builder = ReportBuilder()
        run_record = {
            "run_id": "run-det-001",
            "scenario": "web_target",
            "mode": "web",
            "assessor_provider": "deterministic",
            "assessor_mode": "deterministic",
            "candidates": [
                {"id": "c1", "title": "Finding 1", "quality_rank": "HIGH", "fallback": False},
            ],
            "assessment": {
                "mode": "deterministic",
                "provider": "deterministic",
                "details": [
                    {"candidate_id": "c1", "fallback": False},
                ],
            },
            "web": {
                "target_url": "https://pentest-ground.com:4280/",
            },
        }
        report = builder.from_persisted_run(run_record)
        # Must be DETERMINISTIC ASSESSMENT, NEVER MODEL ASSESSED!
        assert report.metadata.final_status is not None
        prov = report.web_provenance
        assert prov.get("ai", {}).get("outcome") == "DETERMINISTIC ASSESSMENT"

    def test_deterministic_fallback_when_llm_failed(self):
        builder = ReportBuilder()
        run_record = {
            "run_id": "run-fb-001",
            "scenario": "web_target",
            "mode": "web",
            "assessor_provider": "ollama",
            "assessor_mode": "llm",
            "candidates": [
                {"id": "c1", "title": "Finding 1", "fallback": True},
            ],
            "assessment": {
                "mode": "llm",
                "provider": "ollama",
                "model": "llama3.2:3b",
                "details": [
                    {"candidate_id": "c1", "fallback": True},
                ],
            },
            "web": {
                "target_url": "https://pentest-ground.com:4280/",
            },
        }
        report = builder.from_persisted_run(run_record)
        prov = report.web_provenance
        assert prov.get("ai", {}).get("outcome") == "DETERMINISTIC FALLBACK"

    def test_model_assessed_when_llm_succeeded(self):
        builder = ReportBuilder()
        run_record = {
            "run_id": "run-llm-001",
            "scenario": "web_target",
            "mode": "web",
            "assessor_provider": "openrouter",
            "assessor_mode": "llm",
            "candidates": [
                {"id": "c1", "title": "Finding 1", "fallback": False},
            ],
            "assessment": {
                "mode": "llm",
                "provider": "openrouter",
                "model": "meta-llama/llama-3.3-70b-instruct",
                "details": [
                    {"candidate_id": "c1", "fallback": False},
                ],
            },
            "web": {
                "target_url": "https://pentest-ground.com:4280/",
            },
        }
        report = builder.from_persisted_run(run_record)
        prov = report.web_provenance
        assert prov.get("ai", {}).get("outcome") == "MODEL ASSESSED"


class TestCandidateAccountingAndInventory:
    def test_candidate_counters_accurate(self):
        builder = ReportBuilder()
        run_record = {
            "run_id": "run-acct-001",
            "scenario": "web_target",
            "mode": "web",
            "candidates": [
                {"id": "c1", "title": "SQL Injection", "candidate_eligibility": "ACTIONABLE", "validation_status": "VALIDATED"},
                {"id": "c2", "title": "XSS", "candidate_eligibility": "ACTIONABLE", "validation_status": "VALIDATION NOT AVAILABLE"},
            ],
            "candidates_processed": ["c1"],
            "service_discovery": [
                {"title": "Open Port 4280", "candidate_eligibility": "INFORMATIONAL / DISCOVERY"},
            ],
            "web": {
                "nmap": {"finding_count": 1},
                "nuclei": {"finding_count": 2},
                "service_discovery_count": 1,
                "finding_count": 2,
                "total_findings": 3,
            },
        }
        report = builder.from_persisted_run(run_record)
        assert report.metadata.candidates_assessed == 2
        assert report.metadata.candidates_eligible == 2
        assert report.metadata.candidates_validated == 1

        summary = report.web_provenance.get("findings_summary", {})
        assert summary["nmap_raw"] == 1
        assert summary["nuclei_raw"] == 2
        assert summary["actionable_candidates"] == 2
        assert summary["service_discovery"] == 1


class TestReportRenderersObservedExternal:
    def test_html_renderer_observed_external(self):
        report = ReportModel(
            metadata=ReportMetadata(
                run_id="run-ext-render",
                scenario="web_target",
            ),
            evidence_tier="OBSERVED_EXTERNAL",
            target="https://pentest-ground.com:4280/",
            safety_notice="Real controlled web assessment conducted against authorized external target.",
            web_provenance={
                "target_url": "https://pentest-ground.com:4280/",
                "application": "Pentest Ground Authorized Lab",
                "environment": "AUTHORIZED EXTERNAL TARGET",
                "scanners": [],
                "ai": {"mode": "deterministic", "provider": "deterministic", "outcome": "DETERMINISTIC ASSESSMENT"},
            },
        )
        html = HTMLRenderer().render(report)
        assert "OBSERVED_EXTERNAL" in html
        assert "Pentest Ground Authorized Lab" in html
        assert "AUTHORIZED EXTERNAL TARGET" in html
        assert "OWASP Juice Shop" not in html

    def test_markdown_renderer_observed_external(self):
        report = ReportModel(
            metadata=ReportMetadata(
                run_id="run-ext-render",
                scenario="web_target",
            ),
            evidence_tier="OBSERVED_EXTERNAL",
            target="https://pentest-ground.com:4280/",
            web_provenance={
                "target_url": "https://pentest-ground.com:4280/",
                "application": "Pentest Ground Authorized Lab",
                "environment": "AUTHORIZED EXTERNAL TARGET",
                "scanners": [],
                "ai": {"mode": "deterministic", "provider": "deterministic", "outcome": "DETERMINISTIC ASSESSMENT"},
            },
        )
        md = MarkdownRenderer().render(report)
        assert "OBSERVED_EXTERNAL" in md
        assert "Pentest Ground Authorized Lab" in md
        assert "AUTHORIZED EXTERNAL TARGET" in md

    def test_txt_renderer_observed_external(self):
        report = ReportModel(
            metadata=ReportMetadata(
                run_id="run-ext-render",
                scenario="web_target",
            ),
            evidence_tier="OBSERVED_EXTERNAL",
            target="https://pentest-ground.com:4280/",
            web_provenance={
                "target_url": "https://pentest-ground.com:4280/",
                "application": "Pentest Ground Authorized Lab",
                "environment": "AUTHORIZED EXTERNAL TARGET",
                "scanners": [],
                "ai": {"mode": "deterministic", "provider": "deterministic", "outcome": "DETERMINISTIC ASSESSMENT"},
            },
        )
        txt = TXTRenderer().render(report)
        assert "OBSERVED_EXTERNAL" in txt
        assert "Pentest Ground Authorized Lab" in txt
        assert "AUTHORIZED EXTERNAL TARGET" in txt
