"""Phase 17 safety tests: strict web-target authorization (Phase 32).

Backend validation is security enforcement (frontend validation is UX only).
Every case here must fail closed.
"""
from __future__ import annotations

import pytest

from vapt_platform.web_target import (
    WebTargetAuthorizationError,
    parse_web_target,
    validate_web_target,
)


# ---------------------------------------------------------------------------
# Accept cases (mentor demo scope)
# ---------------------------------------------------------------------------

def test_accept_juice_shop_url():
    v = validate_web_target("http://127.0.0.1:9191")
    assert v.authorized is True
    assert v.target is not None
    assert v.target.scheme == "http"
    assert v.target.host == "127.0.0.1"
    assert v.target.port == 9191
    assert v.target.normalized_url == "http://127.0.0.1:9191"
    assert v.target.resolved_host == "127.0.0.1"


def test_accept_localhost_normalized_to_loopback():
    v = validate_web_target("http://localhost:9191")
    assert v.authorized is True
    assert v.target is not None
    assert v.target.resolved_host == "127.0.0.1"


def test_fragment_stripped_from_scanner_target():
    target = parse_web_target("http://127.0.0.1:9191/#/some-page")
    assert "#" not in target.normalized_url
    assert "#" not in target.base_url
    assert target.normalized_url == "http://127.0.0.1:9191"


def test_query_not_preserved_in_scanner_target():
    target = parse_web_target("http://127.0.0.1:9191/?x=1")
    assert target.normalized_url == "http://127.0.0.1:9191"


# ---------------------------------------------------------------------------
# Reject cases (fail closed)
# ---------------------------------------------------------------------------

def test_reject_public_domain():
    v = validate_web_target("https://example.com")
    assert v.authorized is False
    assert "not authorized" in v.reason


def test_reject_public_ip():
    v = validate_web_target("http://8.8.8.8")
    assert v.authorized is False


def test_reject_malformed_url():
    for bad in ["", "   ", "not a url", "://missing-scheme", "http://", "http:///"]:
        v = validate_web_target(bad)
        assert v.authorized is False, bad


def test_reject_embedded_credentials():
    v = validate_web_target("http://user:pass@127.0.0.1:9191")
    assert v.authorized is False
    assert "credentials" in v.reason.lower() or "userinfo" in v.reason.lower()


def test_reject_userinfo_without_password():
    v = validate_web_target("http://user@127.0.0.1:9191")
    assert v.authorized is False


def test_reject_unauthorized_port():
    v = validate_web_target("http://127.0.0.1:8080")
    assert v.authorized is False
    assert "Port 8080" in v.reason


def test_reject_non_http_scheme():
    for bad in ["ftp://127.0.0.1:9191", "file:///etc/passwd", "gopher://127.0.0.1:9191"]:
        v = validate_web_target(bad)
        assert v.authorized is False, bad


def test_reject_non_loopback_even_if_spelled_differently():
    # Numeric tricks must not bypass the explicit host allowlist.
    for bad in ["http://2130706433:9191", "http://0x7f.0.0.1:9191", "http://127.1:9191"]:
        v = validate_web_target(bad)
        assert v.authorized is False, bad


def test_parse_raises_authorization_error():
    with pytest.raises(WebTargetAuthorizationError):
        parse_web_target("https://example.com")


def test_parse_requires_url():
    with pytest.raises(WebTargetAuthorizationError):
        parse_web_target("")
    with pytest.raises(WebTargetAuthorizationError):
        parse_web_target(None)  # type: ignore[arg-type]
