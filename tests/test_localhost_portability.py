"""Codespaces portability regression tests: deterministic localhost resolution.

Ubuntu 24.04 / Codespaces resolves ``localhost`` to ``::1`` first via
``getaddrinfo`` (RFC 3484 sorting), while other systems return ``127.0.0.1``
first. Resolution must therefore be deterministic (prefer IPv4 loopback) and
must validate ALL resolved addresses (DNS-rebinding guard), without widening
the authorization allowlist.
"""
from __future__ import annotations

import socket
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from vapt_platform import web_target as wt
from vapt_platform.web_target import (
    AUTHORIZED_WEB_HOSTS,
    LOOPBACK_IPS,
    WebTargetAuthorizationError,
    parse_web_target,
    validate_web_target,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JUICE_XML = DATA_DIR / "juice_shop_nmap.xml"


def _fake_getaddrinfo(*ips: str):
    """Build a fake socket.getaddrinfo returning the given IPs in order."""
    def _fake(host, port, family=0, type=0, proto=0, flags=0):
        out = []
        for ip in ips:
            if ":" in ip and not ip.startswith("::ffff:"):
                out.append(
                    (socket.AF_INET6, socket.SOCK_STREAM, 6, "",
                     (ip, 0, 0, 0))
                )
            else:
                out.append(
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "",
                     (ip, 0))
                )
        return out
    return _fake


def _nmap_success(xml_text: str):
    def _run(argv, **kwargs):
        assert isinstance(argv, list)
        assert "-oX" in argv
        out_path = argv[argv.index("-oX") + 1]
        Path(out_path).write_text(xml_text)
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = ""
        proc.stderr = ""
        return proc
    return _run


# ---------------------------------------------------------------------------
# Allowlist must not be weakened
# ---------------------------------------------------------------------------

def test_allowlist_remains_loopback_only():
    assert AUTHORIZED_WEB_HOSTS == {"127.0.0.1", "localhost"}
    assert LOOPBACK_IPS == {"127.0.0.1", "::1"}


# ---------------------------------------------------------------------------
# Deterministic resolution regardless of getaddrinfo ordering
# ---------------------------------------------------------------------------

def test_localhost_prefers_ipv4_when_ipv6_first(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo("::1", "127.0.0.1")
    )
    v = validate_web_target("http://localhost:9191")
    assert v.authorized is True
    assert v.target is not None
    assert v.target.resolved_host == "127.0.0.1"


def test_localhost_prefers_ipv4_when_ipv4_first(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo("127.0.0.1", "::1")
    )
    v = validate_web_target("http://localhost:9191")
    assert v.authorized is True
    assert v.target is not None
    assert v.target.resolved_host == "127.0.0.1"


def test_literal_loopback_stable(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("127.0.0.1"))
    v = validate_web_target("http://127.0.0.1:9191")
    assert v.authorized is True
    assert v.target is not None
    assert v.target.resolved_host == "127.0.0.1"


def test_ipv6_only_falls_back_to_loopback(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("::1"))
    v = validate_web_target("http://localhost:9191")
    assert v.authorized is True
    assert v.target is not None
    assert v.target.resolved_host == "::1"


def test_mapped_ipv4_normalized_to_loopback(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo("::ffff:127.0.0.1")
    )
    v = validate_web_target("http://localhost:9191")
    assert v.authorized is True
    assert v.target is not None
    assert v.target.resolved_host == "127.0.0.1"


def test_normalize_resolved_ip_handles_mapped_and_zone():
    assert wt._normalize_resolved_ip("::FFFF:127.0.0.1") == "127.0.0.1"
    assert wt._normalize_resolved_ip("::1%lo") == "::1"
    assert wt._normalize_resolved_ip("127.0.0.1") == "127.0.0.1"


# ---------------------------------------------------------------------------
# DNS-rebinding guard covers ALL addresses, not just the first
# ---------------------------------------------------------------------------

def test_rejects_when_any_resolved_ip_not_loopback_first_is_loopback(monkeypatch):
    # Old first-result-only check would have accepted this; must fail closed.
    monkeypatch.setattr(
        socket, "getaddrinfo",
        _fake_getaddrinfo("127.0.0.1", "93.184.216.34"),
    )
    v = validate_web_target("http://localhost:9191")
    assert v.authorized is False
    assert "not loopback" in v.reason.lower()


def test_rejects_when_any_resolved_ip_not_loopback_second_order(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        _fake_getaddrinfo("93.184.216.34", "127.0.0.1"),
    )
    v = validate_web_target("http://localhost:9191")
    assert v.authorized is False


def test_rejects_single_non_loopback_for_allowlisted_name(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("8.8.8.8"))
    with pytest.raises(WebTargetAuthorizationError):
        parse_web_target("http://localhost:9191")


# ---------------------------------------------------------------------------
# Scanner uses the deterministic resolved IP (no DNS in argv)
# ---------------------------------------------------------------------------

def test_scanner_uses_resolved_ipv4_despite_ipv6_first(
    monkeypatch, tmp_path, offline_guard
):
    import vapt_platform.scanner_service as svc

    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo("::1", "127.0.0.1")
    )
    monkeypatch.setattr(
        subprocess, "run", _nmap_success(JUICE_XML.read_text())
    )
    result = svc.run_nmap_discovery("http://localhost:9191", output_dir=str(tmp_path))
    assert result.status == "COMPLETED"
    assert result.command[-1] == "127.0.0.1"


def test_scanner_rejects_non_loopback_resolution(
    monkeypatch, tmp_path, offline_guard
):
    import vapt_platform.scanner_service as svc

    monkeypatch.setattr(
        socket, "getaddrinfo",
        _fake_getaddrinfo("127.0.0.1", "93.184.216.34"),
    )
    with pytest.raises(WebTargetAuthorizationError):
        svc.run_nmap_discovery("http://localhost:9191", output_dir=str(tmp_path))
    assert offline_guard.call_count == 0
