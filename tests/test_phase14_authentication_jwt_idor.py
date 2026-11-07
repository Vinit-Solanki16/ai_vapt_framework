"""Unit and integration tests for Phase 14.1 improvements:
- Explicit Authenticated Assessment Support
- Safe Non-Destructive JWT Token Inspection
- Object-Level Authorization and IDOR Validation
- Controlled Default Credential Validation
- Finding Handoff, Classification and Precision/Recall Metrics
"""

import base64
import json
from unittest.mock import MagicMock, patch

from strix.core.scanner.auth_manager import AuthSession, redact_credential, redact_dict
from strix.core.scanner.credential_validator import CredentialValidator
from strix.core.scanner.idor_validator import IDORValidator
from strix.core.scanner.jwt_inspector import JWTInspector
from strix.core.triage.exploit_assessor import run_gap1_triage


def test_redact_credential():
    """Test sensitive string masking."""
    assert redact_credential("") == "***[REDACTED]***"
    assert redact_credential("short") == "***[REDACTED]***"
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doNotLeakThisSecretSignature"
    masked = redact_credential(token)
    assert masked.startswith("eyJh")
    assert masked.endswith("ture")
    assert "[REDACTED]" in masked


def test_redact_dict():
    """Test recursive dict masking for credentials and tokens."""
    data = {
        "username": "admin@juice-sh.op",
        "password": "supersecretpassword123",
        "auth": {
            "token": "eyJhbGciOiJIUzI1NiJ9.eyJkYXRhIjp7fX0.signature",
            "api_key": "sk-1234567890abcdef",
        },
        "safe_field": 42,
    }
    redacted = redact_dict(data)
    assert redacted["username"] == "admin@juice-sh.op"
    assert "[REDACTED]" in redacted["password"]
    assert "[REDACTED]" in redacted["auth"]["token"]
    assert "[REDACTED]" in redacted["auth"]["api_key"]
    assert redacted["safe_field"] == 42


def test_jwt_inspector_non_jwt():
    """Test that malformed/non-JWT strings are handled gracefully."""
    res = JWTInspector.inspect("not-a-jwt")
    assert not res.is_jwt
    assert not res.vulnerable

    res2 = JWTInspector.inspect("header.only")
    assert not res2.is_jwt
    assert not res2.vulnerable


def test_jwt_inspector_sensitive_md5_hash_leak():
    """Test safe decoding and detection of password hash in JWT."""
    header = {"alg": "RS256", "typ": "JWT"}
    # Simulate Juice Shop token embedding MD5 hash of 'demo'
    payload = {
        "status": "success",
        "data": {
            "id": 6,
            "username": "demo",
            "email": "demo",
            "password": "fe01ce2a7fbac8fafaed7c982a04e229",
            "role": "customer",
        },
    }
    sig = "simulated_signature_blob"
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    simulated_jwt = f"{h_b64}.{p_b64}.{sig}"

    result = JWTInspector.inspect(simulated_jwt)
    assert result.is_jwt
    assert result.vulnerable
    assert result.algorithm == "RS256"
    assert len(result.sensitive_claims) == 1
    claim = result.sensitive_claims[0]
    assert claim["claim_path"] == "data.password"
    assert "MD5" in claim["type"]
    assert "[REDACTED]" in claim["masked_value"]
    assert "fe01ce2a7fbac8fafaed7c982a04e229" not in claim["masked_value"]
    # Explicit disclaimer
    r_dict = result.to_dict()
    assert not r_dict["signature_verified"]
    assert "RFC 7519" in r_dict["signature_disclaimer"]


def test_jwt_inspector_clean_jwt():
    """Test JWT with non-sensitive standard claims."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": "user-123", "iss": "strix", "exp": 1793999999}
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    token = f"{h_b64}.{p_b64}.sig"

    result = JWTInspector.inspect(token)
    assert result.is_jwt
    assert not result.vulnerable
    assert len(result.sensitive_claims) == 0


def test_idor_validator_detection():
    """Test object-level authorization testing logic with mock responses."""
    target_url = "http://127.0.0.1:3000"
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(
        {"status": "success", "data": {"id": 1, "ProductId": 1, "BasketId": 1, "quantity": 2}}
    ).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_response):
        res = IDORValidator.test_idor(
            target_url,
            auth_token="test_token",
            endpoint_template="/api/BasketItems/{id}",
            user_own_id=6,
            foreign_id=1,
        )
        assert res.is_idor
        assert res.http_status == 200
        assert "Cross-authorization" in res.summary
        assert "[REDACTED]" in res.reproducible_request


def test_idor_validator_access_denied():
    """Test that HTTP 401/403 is correctly evaluated as enforced authorization (not IDOR)."""
    target_url = "http://127.0.0.1:3000"
    from urllib.error import HTTPError

    err = HTTPError(f"{target_url}/api/BasketItems/1", 403, "Forbidden", {}, None)

    with patch("urllib.request.urlopen", side_effect=err):
        res = IDORValidator.test_idor(
            target_url,
            auth_token="test_token",
            endpoint_template="/api/BasketItems/{id}",
            user_own_id=6,
            foreign_id=1,
        )
        assert not res.is_idor
        assert res.http_status == 403
        assert "authorization enforced" in res.summary.lower()


def test_credential_validator_default_admin():
    """Test controlled single default credential validation."""
    target_url = "http://127.0.0.1:3000"
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.status = 200
    # Simulate Juice Shop admin login payload
    token_header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').decode().rstrip("=")
    token_payload = (
        base64.urlsafe_b64encode(b'{"data":{"role":"admin","email":"admin@juice-sh.op"}}')
        .decode()
        .rstrip("=")
    )
    fake_token = f"{token_header}.{token_payload}.sig"

    mock_resp.read.return_value = json.dumps(
        {"authentication": {"token": fake_token, "bid": 1, "umail": "admin@juice-sh.op"}}
    ).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = CredentialValidator.test_single_credential(
            target_url, "admin@juice-sh.op", "admin123"
        )
        assert res.authenticated
        assert res.is_admin
        assert res.role == "admin"
        assert "HIGH SEVERITY" in res.summary


def test_auth_manager_session_propagation():
    """Test AuthSession helper methods."""
    session = AuthSession(
        authenticated=True,
        auth_type="login",
        token="test_secret_token_12345",
        username="demo",
        role="customer",
        basket_id=6,
    )
    headers = session.get_auth_header()
    assert headers["Authorization"] == "Bearer test_secret_token_12345"
    safe = session.to_safe_dict()
    assert safe["username"] == "demo"
    assert safe["role"] == "customer"
    assert "[REDACTED]" in safe["masked_token"]
    assert "test_secret_token_12345" not in safe["masked_token"]


def test_gap1_triage_with_auth_session():
    """Test that authenticated session injects high-priority authenticated attack vectors."""
    auth_session = AuthSession(
        authenticated=True, token="valid_jwt", username="demo", role="customer"
    )
    candidates = run_gap1_triage(
        scenario="default",
        target_url="http://127.0.0.1:3000/",
        scan_mode="deep",
        auth_session=auth_session,
    )
    c_ids = [c["id"] for c in candidates]
    assert "user-enumeration" in c_ids
    assert "jwt-password-leak" in c_ids
    assert "basket-idor" in c_ids
    assert "default-admin-credentials" in c_ids


def test_precision_recall_metric_math():
    """Verify mathematical correctness of precision, recall, and F1 calculations."""
    # Case 1: 0 findings reported (0 TP, 0 FP) -> Precision is undefined or N/A, NOT 100%!
    tp = 0
    fp = 0
    denominator = 34
    precision = None if (tp + fp == 0) else (tp / (tp + fp))
    recall = tp / denominator
    assert precision is None
    assert recall == 0.0

    # Case 2: 2 true findings reported (2 TP, 0 FP)
    tp = 2
    fp = 0
    precision = tp / (tp + fp)
    recall = tp / denominator
    f1 = 2 * (precision * recall) / (precision + recall)
    assert precision == 1.0
    assert round(recall, 4) == 0.0588
    assert round(f1, 4) == 0.1111
