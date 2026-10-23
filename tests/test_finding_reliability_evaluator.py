"""Tests for the ground-truth finding reliability evaluation suite and verifiers."""
from __future__ import annotations

import pytest

from vapt_platform.evaluation.fixtures import eval_fixture_client, run_eval_server
from vapt_platform.evaluation.reliability_evaluator import (
    ReliabilityEvaluator,
    build_evaluation_test_suite,
)
from vapt_platform.verification import (
    ValidationStatus,
    normalize_validation_status,
    verify_candidate,
    verify_cookie_security,
    verify_phpinfo,
)


def test_validation_status_normalization():
    assert normalize_validation_status("SCANNER-DETECTED") == "SCANNER_DETECTED"
    assert normalize_validation_status("VALIDATION NOT AVAILABLE") == "VALIDATION_NOT_AVAILABLE"
    assert normalize_validation_status("VALIDATED") == "VALIDATED_TRUE_POSITIVE"
    assert normalize_validation_status("VALIDATED_TRUE_POSITIVE") == "VALIDATED_TRUE_POSITIVE"
    assert normalize_validation_status("FALSE_POSITIVE") == "FALSE_POSITIVE"
    assert normalize_validation_status("INCONCLUSIVE") == "INCONCLUSIVE"


def test_phpinfo_verifier():
    # Positive case
    ev_pos = verify_phpinfo("http://testserver/phpinfo-vuln", client=eval_fixture_client)
    assert ev_pos.status == ValidationStatus.VALIDATED_TRUE_POSITIVE
    assert ev_pos.http_status == 200
    assert "Confirmed PHPInfo disclosure" in ev_pos.evidence_summary

    # Negative case (404)
    ev_neg = verify_phpinfo("http://testserver/phpinfo-clean", client=eval_fixture_client)
    assert ev_neg.status == ValidationStatus.FALSE_POSITIVE
    assert ev_neg.http_status == 404
    assert "not exposed" in ev_neg.evidence_summary


def test_cookie_security_verifier():
    # Vulnerable to missing HttpOnly
    ev_vuln_httponly = verify_cookie_security(
        "http://testserver/cookie-vuln-httponly", check_httponly=True, client=eval_fixture_client,
    )
    assert ev_vuln_httponly.status == ValidationStatus.VALIDATED_TRUE_POSITIVE
    assert "Confirmed missing HttpOnly" in ev_vuln_httponly.evidence_summary

    # Clean (has HttpOnly) -> Scanner detection is a False Positive!
    ev_clean_httponly = verify_cookie_security(
        "http://testserver/cookie-clean-httponly", check_httponly=True, client=eval_fixture_client,
    )
    assert ev_clean_httponly.status == ValidationStatus.FALSE_POSITIVE
    assert "false positive" in ev_clean_httponly.evidence_summary

    # Vulnerable to missing Secure
    ev_vuln_secure = verify_cookie_security(
        "http://testserver/cookie-vuln-secure", check_httponly=False, check_secure=True, client=eval_fixture_client,
    )
    assert ev_vuln_secure.status == ValidationStatus.VALIDATED_TRUE_POSITIVE
    assert "Confirmed missing Secure" in ev_vuln_secure.evidence_summary

    # Clean (has Secure) -> Scanner detection is a False Positive!
    ev_clean_secure = verify_cookie_security(
        "http://testserver/cookie-clean-secure", check_httponly=False, check_secure=True, client=eval_fixture_client,
    )
    assert ev_clean_secure.status == ValidationStatus.FALSE_POSITIVE
    assert "false positive" in ev_clean_secure.evidence_summary


def test_verifier_error_and_timeout_handling():
    # HTTP 500
    ev_500 = verify_phpinfo("http://testserver/error-500", client=eval_fixture_client)
    assert ev_500.status == ValidationStatus.INCONCLUSIVE
    assert ev_500.http_status == 500

    # Timeout
    ev_timeout = verify_phpinfo("http://testserver/timeout", timeout=0.1, client=eval_fixture_client)
    assert ev_timeout.status == ValidationStatus.INCONCLUSIVE


def test_verify_candidate_external_safeguard():
    candidate = {
        "id": "phpinfo-cand",
        "rule_id": "phpinfo-disclosure",
        "title": "PHPInfo Exposure",
        "path": "/phpinfo-vuln",
    }
    # External target must fail closed to assessment-only
    evidence = verify_candidate(
        candidate,
        target_url="http://example.com/phpinfo-vuln",
        external=True,
    )
    assert evidence.status == ValidationStatus.VALIDATION_NOT_AVAILABLE
    assert "External target safety policy" in evidence.evidence_summary


def test_full_reliability_evaluation():
    evaluator = ReliabilityEvaluator()
    report = evaluator.run_evaluation()

    # Scanner layer has false positives (detection without proof)
    assert report.scanner_metrics.false_positives > 0
    assert report.scanner_metrics.true_positives == 4

    # Active validation layer eliminates false positives!
    assert report.validation_metrics.false_positives == 0
    assert report.validation_metrics.true_positives == 3
    assert report.validation_metrics.precision == 1.0
    assert report.validation_metrics.inconclusive == 2  # 500 error and timeout

    # AI evaluations report models honestly
    prov_names = [a.provider for a in report.ai_evaluations]
    assert "deterministic" in prov_names
    assert "ollama" in prov_names

    # Check GAP-2 pivot evaluation
    assert report.gap2_evaluation["passed"] is True
    assert report.gap2_evaluation["total_attempts"] == 3
    assert report.gap2_evaluation["pivot_count"] >= 1


def test_deduplication_and_informational_split():
    from vapt_platform.normalization import (
        CanonicalFinding,
        deduplicate,
        split_findings,
    )

    # 1. Deduplication merges evidence and tags
    f1 = CanonicalFinding(
        source="nuclei",
        host="127.0.0.1",
        port=80,
        protocol="tcp",
        rule_id="phpinfo-detect",
        target="http://127.0.0.1/phpinfo.php",
        evidence=["found title"],
        tags=["php"],
    )
    f2 = CanonicalFinding(
        source="nuclei",
        host="127.0.0.1",
        port=80,
        protocol="tcp",
        rule_id="phpinfo-detect",
        target="http://127.0.0.1/phpinfo.php",
        evidence=["found php version"],
        tags=["cve"],
    )
    deduped = deduplicate([f1, f2])
    assert len(deduped) == 1
    assert "found title" in deduped[0].evidence
    assert "found php version" in deduped[0].evidence
    assert "php" in deduped[0].tags
    assert "cve" in deduped[0].tags

    # 2. Informational split separates tech detection from actionable candidates
    f_info = CanonicalFinding(
        source="nuclei",
        host="127.0.0.1",
        port=80,
        protocol="tcp",
        rule_id="tech-detect",
        title="Apache Server Detected",
        severity="informational",
    )
    actionable, discovery = split_findings([f1, f_info])
    assert len(actionable) == 1
    assert actionable[0].rule_id == "phpinfo-detect"
    assert len(discovery) == 1
    assert discovery[0].rule_id == "tech-detect"


def test_malformed_model_response_and_fallback():
    from core.schemas import ExploitAssessment
    from decision_engine.core.schemas import ActionCandidate
    from vapt_platform.assessment import create_assessor
    from vapt_platform.ollama_service import query_ollama_structured

    # Test query_ollama_structured with invalid JSON string directly
    from unittest.mock import MagicMock, patch
    import io

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"message": {"content": "This is plain text with no json"}}'

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res, response_received, err = query_ollama_structured(
            prompt="Analyze CVE",
            schema_cls=ExploitAssessment,
        )
        assert res is None
        assert response_received is True
        assert "Malformed structured output" in str(err)


def test_evidence_redaction():
    from vapt_platform.verification import redact_sensitive_evidence

    raw = "Set-Cookie: session_id=super_secret_session_token_12345; Path=/; Secure"
    redacted = redact_sensitive_evidence(raw)
    assert "super_secret_session_token_12345" not in redacted
    assert "session_id=***REDACTED***" in redacted

    bearer_raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz"
    bearer_redacted = redact_sensitive_evidence(bearer_raw)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz" not in bearer_redacted
    assert "Bearer ***REDACTED***" in bearer_redacted


def test_ollama_configurable_options(monkeypatch):
    from vapt_platform.ollama_service import (
        get_ollama_base_url,
        get_ollama_num_ctx,
        get_ollama_num_predict,
        get_ollama_request_timeout,
    )

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.internal:11434/")
    monkeypatch.setenv("OLLAMA_TIMEOUT_S", "120.0")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "8192")
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", "512")

    assert get_ollama_base_url() == "http://ollama.internal:11434"
    assert get_ollama_request_timeout() == 120.0
    assert get_ollama_num_ctx() == 8192
    assert get_ollama_num_predict() == 512

