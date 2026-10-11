"""Regression tests for configurable authorized web target scopes.

Covers VAPT_AUTHORIZED_WEB_SCOPES enforcement end to end:
configuration parsing, hostname/port/address authorization, DNS-rebinding
defense, redirect policy, scanner dispatch, API/GUI state agreement,
report provenance and credential hygiene.

All DNS and scanner execution is MOCKED. No live network access, no live
scan of Pentest-Ground or any other external host, and no dependency on
installed scanner binaries. Existing tests are never weakened.

Required coverage map (task section 7):
    1. Localhost remains accepted.
    2. pentest-ground.com:4280 accepted when exactly configured.
    3. Rejected when external scopes are empty.
    4. Same hostname, unauthorized port -> rejected.
    5. Another public hostname -> rejected until configured.
    6. Lookalike names rejected.
    7. User-info / malformed / ambiguous URLs rejected.
    8. Mixed safe/unsafe DNS results rejected.
    9. Private/loopback/link-local resolutions rejected for external scope.
   10. DNS rebinding cannot bypass validation.
   11. Out-of-scope redirects are blocked (never followed).
   12. Nmap receives only the validated scope and selected port.
   13. Scanner execution does not begin when authorization fails.
   14. Nuclei cannot silently expand the target scope.
   15. GUI/API target-validation states agree.
   16. OpenRouter and Ollama configurations continue to work.
   17. Reports accurately record target and authorization outcome.
   18. No API keys or credentials appear in logs or reports.
"""
from __future__ import annotations

import json
import socket
from types import SimpleNamespace

import pytest

from vapt_platform import scanner_service
from vapt_platform.web_target import (
    AUTHORIZED_WEB_HOSTS,
    AuthorizedScopeConfigurationError,
    SCOPE_ENV_VAR,
    SCOPE_KIND_EXTERNAL,
    SCOPE_KIND_LOCAL,
    WebTargetAuthorizationError,
    _evaluate_redirect,
    authorize_hostname,
    authorize_port,
    authorized_external_scope_strings,
    parse_authorized_web_scopes,
    parse_web_target,
    validate_web_target,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PG = "pentest-ground.com"
PG_PORT = 4280
#: A definitely-public example address (old example.com block, is_global).
PUBLIC_IP = "93.184.216.34"
OTHER_PUBLIC_IP = "8.8.8.8"


def _addrinfo_for(ips: list[str]):
    """Build a socket.getaddrinfo replacement resolving to fixed IPs."""
    def fake(host, port, family=0, type=0, proto=0, flags=0):
        out = []
        for ip in ips:
            fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
            out.append((fam, socket.SOCK_STREAM, 0, "", (ip, 0)))
        return out
    return fake


def _set_scope(monkeypatch, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv(SCOPE_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(SCOPE_ENV_VAR, value)


def _mock_dns(monkeypatch, ips: list[str]) -> None:
    monkeypatch.setattr(
        "vapt_platform.web_target.socket.getaddrinfo", _addrinfo_for(ips)
    )


@pytest.fixture
def pentest_scope(monkeypatch):
    """Exact authorized scope for the Pentest-Ground training target."""
    _set_scope(monkeypatch, f"{PG}:{PG_PORT}")
    _mock_dns(monkeypatch, [PUBLIC_IP])
    return monkeypatch


@pytest.fixture(autouse=True)
def _no_accidental_scope(monkeypatch):
    """Every test starts from the local-only default unless it opts in."""
    _set_scope(monkeypatch, None)
    yield


# ---------------------------------------------------------------------------
# 1. Localhost remains accepted (existing local policy preserved)
# ---------------------------------------------------------------------------

def test_local_127_still_accepted(monkeypatch):
    _mock_dns(monkeypatch, ["127.0.0.1"])
    t = parse_web_target("http://127.0.0.1:9191/")
    assert t.scope_kind == SCOPE_KIND_LOCAL
    assert t.external is False
    assert t.host == "127.0.0.1"
    assert t.port == 9191
    assert t.resolved_host == "127.0.0.1"
    assert t.resolved_ips == ["127.0.0.1"]


def test_localhost_still_accepted_ipv6_first(monkeypatch):
    # Some resolvers return ::1 first; both must be accepted, IPv4 preferred.
    _mock_dns(monkeypatch, ["::1", "127.0.0.1"])
    t = parse_web_target("http://localhost:9191/")
    assert t.scope_kind == SCOPE_KIND_LOCAL
    assert t.resolved_host == "127.0.0.1"


# ---------------------------------------------------------------------------
# 2. pentest-ground.com:4280 accepted when exactly configured
# ---------------------------------------------------------------------------

def test_pentest_ground_accepted_when_exact_scope_configured(pentest_scope):
    v = validate_web_target(f"https://{PG}:{PG_PORT}/")
    assert v.authorized is True
    assert v.hostname_authorized and v.port_authorized and v.addresses_validated
    assert v.in_configured_scope is True
    t = v.target
    assert t.scope_kind == SCOPE_KIND_EXTERNAL
    assert t.external is True
    assert t.scope_entry == f"{PG}:{PG_PORT}"
    assert t.resolved_host == PUBLIC_IP
    assert t.normalized_url == f"https://{PG}:{PG_PORT}"


def test_scope_strings_and_parsing():
    scopes = parse_authorized_web_scopes(f"{PG}:{PG_PORT},app.example.org:8443")
    assert scopes == frozenset({(PG, PG_PORT), ("app.example.org", 8443)})


def test_ipv6_scope_entry_accepted():
    scopes = parse_authorized_web_scopes("[2001:db8::10]:8443")
    assert scopes == frozenset({("2001:db8::10", 8443)})


def test_empty_and_unset_scope_is_local_only():
    assert parse_authorized_web_scopes(None) == frozenset()
    assert parse_authorized_web_scopes("") == frozenset()
    assert parse_authorized_web_scopes("  ") == frozenset()


# ---------------------------------------------------------------------------
# 3. Rejected when external scopes are empty
# ---------------------------------------------------------------------------

def test_pentest_ground_rejected_when_scopes_empty(monkeypatch):
    _set_scope(monkeypatch, None)
    _mock_dns(monkeypatch, [PUBLIC_IP])
    with pytest.raises(WebTargetAuthorizationError, match="not authorized"):
        parse_web_target(f"https://{PG}:{PG_PORT}/")
    v = validate_web_target(f"https://{PG}:{PG_PORT}/")
    assert v.authorized is False
    assert v.target is None
    assert SCOPE_ENV_VAR in v.reason


def test_empty_string_scope_same_as_unset(monkeypatch):
    _set_scope(monkeypatch, "")
    _mock_dns(monkeypatch, [PUBLIC_IP])
    with pytest.raises(WebTargetAuthorizationError):
        parse_web_target(f"https://{PG}:{PG_PORT}/")


# ---------------------------------------------------------------------------
# 4. Same hostname, unauthorized port -> rejected (separate port check)
# ---------------------------------------------------------------------------

def test_same_host_unauthorized_port_rejected(pentest_scope):
    with pytest.raises(WebTargetAuthorizationError, match="Port"):
        parse_web_target(f"https://{PG}:443/")
    v = validate_web_target(f"https://{PG}:443/")
    assert v.authorized is False


def test_hostname_and_port_are_separate_checks(pentest_scope):
    # Hostname check passes...
    assert authorize_hostname(PG) == SCOPE_KIND_EXTERNAL
    # ...but the port check fails independently.
    with pytest.raises(WebTargetAuthorizationError):
        authorize_port(PG, 443, SCOPE_KIND_EXTERNAL)
    authorize_port(PG, PG_PORT, SCOPE_KIND_EXTERNAL)  # exact port OK


# ---------------------------------------------------------------------------
# 5. Another public hostname rejected until explicitly configured
# ---------------------------------------------------------------------------

def test_other_public_hostname_rejected_then_configured(monkeypatch):
    _mock_dns(monkeypatch, [OTHER_PUBLIC_IP])
    _set_scope(monkeypatch, f"{PG}:{PG_PORT}")
    with pytest.raises(WebTargetAuthorizationError, match="not authorized"):
        parse_web_target("https://evil.example.com:443/")
    _set_scope(monkeypatch, f"{PG}:{PG_PORT},evil.example.com:443")
    t = parse_web_target("https://evil.example.com:443/")
    assert t.scope_kind == SCOPE_KIND_EXTERNAL


def test_arbitrary_ip_rejected_unless_exact_ip_scope(monkeypatch):
    _mock_dns(monkeypatch, ["93.184.216.99"])
    _set_scope(monkeypatch, None)
    with pytest.raises(WebTargetAuthorizationError, match="not authorized"):
        parse_web_target("https://93.184.216.99:443/")
    _set_scope(monkeypatch, "93.184.216.99:443")
    t = parse_web_target("https://93.184.216.99:443/")
    assert t.external is True
    assert t.resolved_host == "93.184.216.99"


# ---------------------------------------------------------------------------
# 6. Lookalike names rejected
# ---------------------------------------------------------------------------

def test_lookalike_subdomain_rejected(pentest_scope):
    for evil in (
        f"{PG}.attacker.example",
        f"www.{PG}",
        f"{PG}.evil.com",
        "pentest-ground.co",  # different TLD
    ):
        with pytest.raises(WebTargetAuthorizationError):
            parse_web_target(f"https://{evil}:{PG_PORT}/")


# ---------------------------------------------------------------------------
# 7. User-info, malformed hostnames and ambiguous URLs rejected
# ---------------------------------------------------------------------------

def test_userinfo_and_ambiguous_urls_rejected(pentest_scope):
    bad_urls = [
        f"https://user:pass@{PG}:{PG_PORT}/",   # embedded credentials
        f"https://user@{PG}:{PG_PORT}/",        # userinfo without password
        "https://2130706433:9191/",             # decimal IP spelling
        "https://127.1:9191/",                  # short IPv4 spelling
        "https://0x7f000001:9191/",             # hex IP spelling
        "http://%45xample.com:9191/",           # percent-encoded host
        "http://exa mple.com:9191/",            # whitespace in host
        "http://ex%ample.com:9191/",            # percent in host
        "ftp://localhost:9191/",                # bad scheme
        "http://localhost:notaport/",           # invalid port
    ]
    for url in bad_urls:
        with pytest.raises(WebTargetAuthorizationError):
            parse_web_target(url)


def test_scope_entries_invalid_fail_clearly():
    bad_entries = [
        "pentest-ground.com",                    # missing port
        "https://pentest-ground.com:4280",       # scheme not allowed
        "pentest-ground.com:4280/admin",         # path not allowed
        "pentest-ground.com:4280?q=1",           # query not allowed
        "pentest-ground.com:4280#frag",          # fragment not allowed
        "*.pentest-ground.com:4280",             # wildcard
        "pentest-ground.com:0",                  # port out of range
        "pentest-ground.com:99999",              # port out of range
        "pentest-ground.com:abc",                # non-integer port
        ":4280",                                 # empty host
        "2130706433:4280",                       # ambiguous numeric host
        "127.1:4280",                            # ambiguous numeric host
    ]
    for entry in bad_entries:
        with pytest.raises(AuthorizedScopeConfigurationError):
            parse_authorized_web_scopes(entry)


def test_broken_allowlist_fails_closed_for_every_target(monkeypatch):
    """A malformed scope config must not be silently ignored."""
    _set_scope(monkeypatch, "pentest-ground.com")  # missing port
    _mock_dns(monkeypatch, ["127.0.0.1"])
    with pytest.raises(AuthorizedScopeConfigurationError):
        authorize_hostname("127.0.0.1")  # even localhost fails closed
    with pytest.raises(AuthorizedScopeConfigurationError):
        parse_web_target("http://127.0.0.1:9191/")


# ---------------------------------------------------------------------------
# 8. Mixed safe/unsafe DNS results rejected
# ---------------------------------------------------------------------------

def test_mixed_public_and_loopback_rejected(pentest_scope):
    _mock_dns(pentest_scope, [PUBLIC_IP, "127.0.0.1"])
    with pytest.raises(WebTargetAuthorizationError):
        parse_web_target(f"https://{PG}:{PG_PORT}/")


def test_mixed_public_and_private_rejected(pentest_scope):
    _mock_dns(pentest_scope, [PUBLIC_IP, "10.0.0.5"])
    with pytest.raises(WebTargetAuthorizationError):
        parse_web_target(f"https://{PG}:{PG_PORT}/")


# ---------------------------------------------------------------------------
# 9. Private, loopback, link-local resolutions rejected for external scope
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_ip", [
    "127.0.0.1",        # loopback
    "::1",              # IPv6 loopback
    "10.1.2.3",         # RFC1918
    "192.168.1.10",     # RFC1918
    "172.16.0.9",       # RFC1918
    "169.254.1.1",      # link-local
    "fe80::1",          # IPv6 link-local
    "100.64.0.1",       # CGNAT (is_global False)
    "0.0.0.0",          # unspecified
    "224.0.0.1",        # multicast (is_global True on 3.14 — explicit check)
    "ff02::1",          # IPv6 multicast
    "198.18.0.1",       # benchmarking/reserved
])
def test_external_scope_rejects_non_public_destinations(pentest_scope, bad_ip):
    _mock_dns(pentest_scope, [bad_ip])
    with pytest.raises(WebTargetAuthorizationError):
        parse_web_target(f"https://{PG}:{PG_PORT}/")


def test_local_scope_still_loopback_only(monkeypatch):
    """Localhost authorization must not broaden to any resolved IP."""
    _mock_dns(monkeypatch, ["93.184.216.34"])
    with pytest.raises(WebTargetAuthorizationError, match="loopback"):
        parse_web_target("http://localhost:9191/")


def test_dns_resolution_failure_rejected(pentest_scope):
    def boom(*a, **kw):
        raise socket.gaierror("resolution failed")
    pentest_scope.setattr("vapt_platform.web_target.socket.getaddrinfo", boom)
    with pytest.raises(WebTargetAuthorizationError, match="resolve"):
        parse_web_target(f"https://{PG}:{PG_PORT}/")


# ---------------------------------------------------------------------------
# 10. DNS rebinding cannot bypass validation
# ---------------------------------------------------------------------------

def test_scanner_refuses_when_resolution_changes_after_validation(
    pentest_scope, tmp_path, monkeypatch
):
    """Validated at authorization time, rebound at dispatch time -> no scan."""
    state = {"calls": 0}

    def flaky(host, port, family=0, type=0, proto=0, flags=0):
        state["calls"] += 1
        # First resolution (parse/authorize) is public; the scan-time
        # re-resolution sees a DIFFERENT public address (rebinding).
        ips = [PUBLIC_IP] if state["calls"] == 1 else [OTHER_PUBLIC_IP]
        return _addrinfo_for(ips)(host, port, family, type, proto, flags)

    monkeypatch.setattr("vapt_platform.web_target.socket.getaddrinfo", flaky)
    monkeypatch.setattr(scanner_service, "nmap_status",
                        lambda: {"available": True, "path": "/usr/bin/nmap"})

    def boom(argv, **kw):
        raise AssertionError("scanner must not run after a resolution change")

    monkeypatch.setattr(scanner_service.subprocess, "run", boom)
    result = scanner_service.run_nmap_discovery(
        f"https://{PG}:{PG_PORT}/", output_dir=str(tmp_path)
    )
    assert result.status == "UNSUPPORTED"
    assert "changed since authorization" in result.detail


def test_scanner_unsupported_when_revalidation_address_is_unsafe(
    pentest_scope, tmp_path, monkeypatch
):
    """Scan-time re-resolution to a private address -> UNSUPPORTED, no scan."""
    state = {"calls": 0}

    def flaky(host, port, family=0, type=0, proto=0, flags=0):
        state["calls"] += 1
        ips = [PUBLIC_IP] if state["calls"] == 1 else ["10.0.0.5"]
        return _addrinfo_for(ips)(host, port, family, type, proto, flags)

    monkeypatch.setattr("vapt_platform.web_target.socket.getaddrinfo", flaky)
    monkeypatch.setattr(scanner_service, "nmap_status",
                        lambda: {"available": True, "path": "/usr/bin/nmap"})

    def boom(argv, **kw):
        raise AssertionError("scanner must not run with an unsafe revalidation")

    monkeypatch.setattr(scanner_service.subprocess, "run", boom)
    result = scanner_service.run_nmap_discovery(
        f"https://{PG}:{PG_PORT}/", output_dir=str(tmp_path)
    )
    assert result.status == "UNSUPPORTED"
    assert "re-validation failed" in result.detail


def test_revalidate_detects_rebinding(pentest_scope, monkeypatch):
    from vapt_platform.scanner_service import _revalidate_for_scan
    from vapt_platform.web_target import parse_web_target as _pwt

    target = _pwt(f"https://{PG}:{PG_PORT}/")
    # Same resolution: OK.
    assert _revalidate_for_scan(target) is None
    # Changed resolution: refused.
    monkeypatch.setattr(
        "vapt_platform.web_target.socket.getaddrinfo",
        _addrinfo_for([OTHER_PUBLIC_IP]),
    )
    reason = _revalidate_for_scan(target)
    assert reason is not None
    assert "changed since authorization" in reason


# ---------------------------------------------------------------------------
# 11. Out-of-scope redirects are blocked (never followed)
# ---------------------------------------------------------------------------

def test_redirect_out_of_scope_marked_and_not_followed(pentest_scope):
    from vapt_platform.web_target import parse_web_target as _pwt
    t = _pwt(f"https://{PG}:{PG_PORT}/")
    info = _evaluate_redirect(t, "https://evil.example.com/login")
    assert info["followed"] is False
    assert info["in_scope"] is False
    assert "OUTSIDE" in info["note"]


def test_redirect_same_host_other_port_out_of_scope(pentest_scope):
    from vapt_platform.web_target import parse_web_target as _pwt
    t = _pwt(f"https://{PG}:{PG_PORT}/")
    info = _evaluate_redirect(t, f"https://{PG}:443/")
    assert info["followed"] is False
    assert info["in_scope"] is False


def test_redirect_in_scope_still_not_followed(pentest_scope):
    from vapt_platform.web_target import parse_web_target as _pwt
    t = _pwt(f"https://{PG}:{PG_PORT}/")
    info = _evaluate_redirect(t, f"/admin")
    assert info["followed"] is False
    assert info["in_scope"] is True


def test_preflight_never_follows_redirects(pentest_scope, monkeypatch):
    from vapt_platform import web_target as wt

    def fake_probe(target, timeout):
        return {"http_status": 302, "location": "https://evil.example.com/x"}

    monkeypatch.setattr(wt, "_probe_target", fake_probe)
    result = wt.preflight_web_target(f"https://{PG}:{PG_PORT}/")
    assert result["reachable"] is True
    assert result["redirect"]["followed"] is False
    assert result["redirect"]["in_scope"] is False
    assert result["redirect"]["location"] == "https://evil.example.com/x"


# ---------------------------------------------------------------------------
# 12. Nmap receives only the validated scope and selected port
# ---------------------------------------------------------------------------

def _stub_nmap(monkeypatch, tmp_path):
    calls = {"argv": []}

    def fake_run(argv, **kw):
        calls["argv"].append(list(argv))
        # Write a parseable empty nmap XML at -oX path.
        if "-oX" in argv:
            out = argv[argv.index("-oX") + 1]
            with open(out, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0"?><nmaprun></nmaprun>')
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(scanner_service, "nmap_status",
                        lambda: {"available": True, "path": "/usr/bin/nmap"})
    monkeypatch.setattr(scanner_service.subprocess, "run", fake_run)
    monkeypatch.setattr("vapt_platform.scanners.NmapXmlAdapter.parse",
                        lambda self, path: [])
    return calls


def test_nmap_argv_scoped_to_validated_host_and_port(pentest_scope, tmp_path, monkeypatch):
    calls = _stub_nmap(monkeypatch, tmp_path)
    result = scanner_service.run_nmap_discovery(
        f"https://{PG}:{PG_PORT}/", output_dir=str(tmp_path)
    )
    assert result.status == "COMPLETED"
    argv = calls["argv"][0]
    # Safe fixed profile, only the authorized port, no ranges / no -p-.
    assert "-Pn" in argv and "-sV" in argv and "-n" in argv
    assert "-p" in argv
    assert argv[argv.index("-p") + 1] == str(PG_PORT)
    assert "-p-" not in argv
    # Destination is the validated pinned IP — never a bare hostname that
    # Nmap could re-resolve to something else.
    assert argv[-1] == PUBLIC_IP
    assert PG not in argv
    assert len(calls["argv"]) == 1


def test_nmap_local_target_scans_only_authorized_port(monkeypatch, tmp_path):
    _mock_dns(monkeypatch, ["127.0.0.1"])
    calls = _stub_nmap(monkeypatch, tmp_path)
    result = scanner_service.run_nmap_discovery(
        "http://127.0.0.1:9191/", output_dir=str(tmp_path)
    )
    assert result.status == "COMPLETED"
    argv = calls["argv"][0]
    assert argv[argv.index("-p") + 1] == "9191"
    assert argv[-1] == "127.0.0.1"


# ---------------------------------------------------------------------------
# 13. Scanner execution does not begin when authorization fails
# ---------------------------------------------------------------------------

def test_nmap_never_dispatches_when_out_of_scope(monkeypatch, tmp_path):
    def boom(*a, **kw):
        raise AssertionError("scanner must not run for an out-of-scope target")
    monkeypatch.setattr(scanner_service.subprocess, "run", boom)
    monkeypatch.setattr(scanner_service, "nmap_status",
                        lambda: {"available": True, "path": "/usr/bin/nmap"})
    with pytest.raises(WebTargetAuthorizationError):
        scanner_service.run_nmap_discovery(
            "https://evil.example.com:443/", output_dir=str(tmp_path)
        )


def test_nuclei_never_dispatches_when_out_of_scope(monkeypatch, tmp_path):
    def boom(*a, **kw):
        raise AssertionError("scanner must not run for an out-of-scope target")
    monkeypatch.setattr(scanner_service.subprocess, "run", boom)
    monkeypatch.setattr(scanner_service, "nuclei_status",
                        lambda: {"available": True, "path": "/usr/bin/nuclei"})
    with pytest.raises(WebTargetAuthorizationError):
        scanner_service.run_nuclei_scan(
            "https://evil.example.com:443/", output_dir=str(tmp_path)
        )


def test_nmap_unsupported_when_scan_time_revalidation_fails(pentest_scope, tmp_path, monkeypatch):
    """Revalidation failure -> explicit UNSUPPORTED, zero subprocess calls."""
    from vapt_platform.scanner_service import _revalidate_for_scan
    from vapt_platform.web_target import parse_web_target as _pwt

    calls = []
    monkeypatch.setattr(scanner_service, "nmap_status",
                        lambda: {"available": True, "path": "/usr/bin/nmap"})
    monkeypatch.setattr(
        scanner_service.subprocess, "run",
        lambda argv, **kw: (calls.append(argv), SimpleNamespace(returncode=0))[1],
    )
    target = _pwt(f"https://{PG}:{PG_PORT}/")
    # Re-resolve to a private address: revalidation fails closed.
    monkeypatch.setattr(
        "vapt_platform.web_target.socket.getaddrinfo", _addrinfo_for(["10.0.0.5"])
    )
    reason = _revalidate_for_scan(target)
    assert reason is not None
    assert "re-validation failed" in reason
    assert calls == []


# ---------------------------------------------------------------------------
# 14. Nuclei cannot silently expand the target scope
# ---------------------------------------------------------------------------

def _stub_nuclei(monkeypatch, tmp_path):
    calls = {"argv": []}

    def fake_run(argv, **kw):
        calls["argv"].append(list(argv))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(scanner_service, "nuclei_status",
                        lambda: {"available": True, "path": "/usr/bin/nuclei"})
    monkeypatch.setattr(scanner_service, "nuclei_template_dirs",
                        lambda: ["/tmp/nuclei-templates"])
    monkeypatch.setattr(scanner_service.subprocess, "run", fake_run)
    return calls


def test_nuclei_target_is_normalized_base_url_only(pentest_scope, tmp_path, monkeypatch):
    calls = _stub_nuclei(monkeypatch, tmp_path)
    result = scanner_service.run_nuclei_scan(
        f"https://{PG}:{PG_PORT}/some/path?q=1#frag", output_dir=str(tmp_path)
    )
    assert result.status == "COMPLETED"
    argv = calls["argv"][0]
    target_value = argv[argv.index("-target") + 1]
    # Path, query and fragment never reach the scanner.
    assert target_value == f"https://{PG}:{PG_PORT}"


def test_nuclei_bounded_flags_include_no_redirects(pentest_scope, tmp_path, monkeypatch):
    calls = _stub_nuclei(monkeypatch, tmp_path)
    result = scanner_service.run_nuclei_scan(
        f"https://{PG}:{PG_PORT}/", output_dir=str(tmp_path)
    )
    argv = calls["argv"][0]
    # Redirects disabled; bounded rate/timeout/retries.
    assert "-dr" in argv
    assert "-timeout" in argv and "-rate-limit" in argv and "-retries" in argv
    # Exactly one -target, whose value is the in-scope base URL.
    assert argv.count("-target") == 1
    assert argv[argv.index("-target") + 1] == f"https://{PG}:{PG_PORT}"


# ---------------------------------------------------------------------------
# 15. GUI/API target-validation states agree
# ---------------------------------------------------------------------------

def test_api_and_validate_web_target_states_agree(pentest_scope, monkeypatch):
    from fastapi.testclient import TestClient
    from services.api import app
    from vapt_platform import web_target as wt

    monkeypatch.setattr(
        wt, "_probe_target", lambda t, timeout: {"http_status": 200, "location": ""}
    )
    client = TestClient(app)
    url = f"https://{PG}:{PG_PORT}/"
    api = client.post("/targets/validate", json={"target_url": url}).json()
    local_view = wt.validate_web_target(url)  # same function the Streamlit UI uses

    assert api["authorized"] is True
    assert api["authorized"] == local_view.authorized
    assert api["scope_kind"] == local_view.target.scope_kind
    assert api["normalized_host"] == local_view.target.host
    assert api["port"] == local_view.target.port
    assert api["external_scope"] == local_view.target.external
    assert api["acknowledgement_required"] == bool(local_view.target.external)
    assert api["in_scope"] == local_view.in_configured_scope
    assert api["address_validation"]


def test_api_rejects_out_of_scope_and_matches_gui(pentest_scope, monkeypatch):
    from fastapi.testclient import TestClient
    from services.api import app
    from vapt_platform import web_target as wt

    client = TestClient(app)
    url = "https://not-configured.example.org:443/"
    api = client.post("/targets/validate", json={"target_url": url}).json()
    local_view = wt.validate_web_target(url)
    assert api["authorized"] is False
    assert local_view.authorized is False
    assert api["in_scope"] is False
    assert api["authorization_status"] == "REJECTED"


def test_runs_endpoint_requires_ack_for_external_target(pentest_scope, monkeypatch):
    from fastapi.testclient import TestClient
    from services.api import app
    from vapt_platform import web_target as wt

    monkeypatch.setattr(
        wt, "_probe_target", lambda t, timeout: {"http_status": 200, "location": ""}
    )
    client = TestClient(app)
    body = {
        "scenario": "failure_pivot",
        "mode": "web",
        "assessment_type": "web",
        "target_url": f"https://{PG}:{PG_PORT}/",
        "assessor": "deterministic",
        "target_scope_acknowledged": False,
    }
    resp = client.post("/runs", json=body)
    assert resp.status_code == 400
    assert "acknowledgement" in resp.json()["detail"] or \
        "target_scope_acknowledged" in resp.json()["detail"]


def test_gui_sources_render_backend_scope_fields():
    """SPA + Streamlit only display backend-validated scope information."""
    from pathlib import Path

    spa = Path("frontend/web/js/app.js").read_text(encoding="utf-8")
    # The SPA renders the backend response fields, never invents them.
    for token in (
        "VAPT_AUTHORIZED_WEB_SCOPES",
        "web-scope-ack",
        "external_scope",
        "acknowledgement_required",
        "resolved_ips",
        "scope_kind",
        "OUT OF SCOPE",
    ):
        assert token in spa, f"SPA missing scope UI element: {token}"

    streamlit_src = Path("frontend/app.py").read_text(encoding="utf-8")
    for token in (
        "validate_web_target",
        "VAPT_AUTHORIZED_WEB_SCOPES",
        "web_acknowledged",
        "OUT OF SCOPE",
        "scope_kind",
    ):
        assert token in streamlit_src, f"Streamlit missing scope UI element: {token}"
    # The Streamlit web URL field must not be a free-text "target" input.
    for line in streamlit_src.splitlines():
        if "st.text_input" in line:
            assert "target" not in line.lower()


# ---------------------------------------------------------------------------
# 16. OpenRouter and Ollama configurations continue to work
# ---------------------------------------------------------------------------

def test_openrouter_and_ollama_config_uncoupled_from_scope(monkeypatch):
    from vapt_platform import model_config as mc

    # Provider/model selection API unchanged.
    assert "ollama" in mc.KNOWN_PROVIDERS
    assert "openrouter" in mc.KNOWN_PROVIDERS
    assert mc.DEFAULT_OLLAMA_MODEL == "llama3.2:3b"
    assert mc.api_key_env_for("openrouter") == "OPENROUTER_API_KEY"
    assert mc.api_key_env_for("ollama") is None
    assert "llama3.2:3b" in mc.models_for_provider("ollama")

    # Scope validation never reads hosted-provider credentials: setting a
    # key changes nothing about authorization, and no scope key exists.
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key-material")
    monkeypatch.setenv(SCOPE_ENV_VAR, f"{PG}:{PG_PORT}")
    assert authorized_external_scope_strings() == [f"{PG}:{PG_PORT}"]
    _mock_dns(monkeypatch, [PUBLIC_IP])
    assert parse_web_target(f"https://{PG}:{PG_PORT}/").external is True


def test_local_policy_constants_not_broadened():
    # The local host set must stay exactly loopback-only (existing
    # localhost-portability contract). External scope comes only from
    # VAPT_AUTHORIZED_WEB_SCOPES, never from widening this set.
    assert AUTHORIZED_WEB_HOSTS == {"127.0.0.1", "localhost"}


# ---------------------------------------------------------------------------
# 17. Reports accurately record target and authorization outcome
# ---------------------------------------------------------------------------

def test_report_records_authorization_outcome_and_target(pentest_scope):
    from vapt_platform.reporting.builder import _build_web_provenance

    t = parse_web_target(f"https://{PG}:{PG_PORT}/")
    pipeline_summary = {
        "web": {
            "authorization": {
                "status": "AUTHORIZED",
                "scope_kind": t.scope_kind,
                "scope_entry": t.scope_entry,
                "external": t.external,
                "scheme": t.scheme,
                "hostname": t.host,
                "port": t.port,
                "resolved_host": t.resolved_host,
                "resolved_ips": list(t.resolved_ips),
                "address_validation": "PUBLIC",
                "acknowledgement_required": True,
                "acknowledged": True,
            },
            "nmap": {"status": "COMPLETED", "finding_count": 3, "duration_s": 1.2},
            "nuclei": {"status": "NOT AVAILABLE", "finding_count": 0},
        }
    }
    prov = _build_web_provenance(pipeline_summary, {"details": []}, [])
    auth = prov["authorization"]
    assert auth["status"] == "AUTHORIZED"
    assert auth["scope_kind"] == SCOPE_KIND_EXTERNAL
    assert auth["scope_entry"] == f"{PG}:{PG_PORT}"
    assert auth["hostname"] == PG
    assert auth["port"] == PG_PORT
    assert auth["resolved_host"] == PUBLIC_IP
    assert auth["resolved_ips"] == [PUBLIC_IP]
    assert auth["acknowledgement_required"] is True
    assert auth["acknowledged"] is True


# ---------------------------------------------------------------------------
# 18. No API keys or credentials appear in logs or reports
# ---------------------------------------------------------------------------

def test_no_credentials_in_report_or_preflight(monkeypatch, pentest_scope):
    from vapt_platform.reporting.builder import _build_web_provenance
    from vapt_platform import web_target as wt

    secret = "sk-or-v1-super-secret-key-material"
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    monkeypatch.setattr(
        wt, "_probe_target", lambda t, timeout: {"http_status": 200, "location": ""}
    )

    # Preflight payload carries scope/authorization fields, no credentials.
    result = wt.preflight_web_target(f"https://{PG}:{PG_PORT}/")
    serialized = json.dumps(result, default=str)
    assert secret not in serialized
    assert "OPENROUTER" not in serialized
    assert "api_key" not in serialized.lower()

    # Report provenance carries the authorization outcome, no credentials.
    t = parse_web_target(f"https://{PG}:{PG_PORT}/")
    pipeline_summary = {
        "web": {
            "authorization": {
                "status": "AUTHORIZED",
                "scope_kind": t.scope_kind,
                "scope_entry": t.scope_entry,
                "external": t.external,
                "scheme": t.scheme,
                "hostname": t.host,
                "port": t.port,
                "resolved_host": t.resolved_host,
                "resolved_ips": list(t.resolved_ips),
                "address_validation": "PUBLIC",
                "acknowledgement_required": True,
                "acknowledged": True,
            },
        }
    }
    prov = _build_web_provenance(pipeline_summary, {"details": []}, [])
    serialized = json.dumps(prov, default=str)
    assert secret not in serialized
    assert "sk-or" not in serialized

    # /scanners/status exposes scope configuration, never credentials.
    from fastapi.testclient import TestClient
    from services.api import app
    status = TestClient(app).get("/scanners/status").json()
    assert status["scope_env_var"] == SCOPE_ENV_VAR
    assert status["authorized_external_scopes"] == [f"{PG}:{PG_PORT}"]
    assert secret not in json.dumps(status, default=str)


# ---------------------------------------------------------------------------
# Extra: default local-only configuration is preserved end to end
# ---------------------------------------------------------------------------

def test_scanners_status_reports_local_only_by_default(monkeypatch):
    from fastapi.testclient import TestClient
    from services.api import app

    status = TestClient(app).get("/scanners/status").json()
    assert status["authorized_external_scopes"] == []
    assert set(status["authorized_hosts"]) == {"127.0.0.1", "localhost"}
