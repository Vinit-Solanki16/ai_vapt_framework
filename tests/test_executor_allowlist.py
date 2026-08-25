"""T-DOCKER Stage B: danger_mode target_allowlist enforcement (fail-closed).

Contract under test (core/executor.py ONLY):
  * Executor(target_allowlist=[...]) authorises EXACTLY those hosts for
    danger_mode exploitation.
  * DEFAULT allowlist is EMPTY -> danger_mode refuses EVERYTHING until an
    operator explicitly authorises targets (fail-closed).
  * A disallowed host yields FAIL_NO_TARGET with a "target not allowlisted"
    detail and NEVER reaches subprocess.run.
  * An allowed host proceeds into the dangerous path (subprocess IS invoked)
    and the outcome is parsed from REAL module output -- labels.json is NOT
    trusted there.
  * All pre-existing behaviour is preserved: the honest connectivity probe
    still runs first, LOW-usability exploits are still skipped before any
    dangerous path is considered.

All tests are OFFLINE: conftest.py stubs sockets and records subprocess.run,
and the connectivity probe is additionally stubbed where reachability must
be simulated.
"""
from __future__ import annotations

import os
import warnings
from unittest.mock import MagicMock

from core.executor import CORPUS_DIR, Executor
from core.schemas import ExecutionOutcome, Finding, UsabilityRank


def _high_finding(cve: str = "CVE-2021-44228", port: int = 8080) -> Finding:
    """A HIGH-usability finding: passes every pre-existing safety gate."""
    return Finding(cve=cve, port=port, usability_rank=UsabilityRank.HIGH)


def _danger_executor(target_allowlist=None) -> Executor:
    """Build a real-mode danger_mode Executor, suppressing the expected
    opt-in warning emitted at construction time."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        kwargs = {"mode": "real", "danger_mode": True}
        if target_allowlist is not None:
            kwargs["target_allowlist"] = target_allowlist
        return Executor(**kwargs)


def _reachable_probe(monkeypatch):
    """Stub the TCP probe as 'reachable' so tests stay fully offline."""
    probe = MagicMock(return_value=(True, "reachable (stubbed)"))
    monkeypatch.setattr(Executor, "_connectivity_probe", probe)
    return probe


# ---------------------------------------------------------------------------
# Fail-closed default: empty allowlist refuses EVERYTHING
# ---------------------------------------------------------------------------
def test_default_empty_allowlist_refuses_everything(monkeypatch, offline_guard):
    """Default construction: danger_mode=True but NO allowlist -> every
    target refused, nothing executed."""
    probe = _reachable_probe(monkeypatch)

    ex = _danger_executor()
    r = ex.execute(_high_finding(), "127.0.0.1")

    assert r.outcome == ExecutionOutcome.FAIL_NO_TARGET
    assert "target not allowlisted" in r.detail
    # The honest connectivity probe still ran exactly once before refusal.
    assert probe.call_count == 1
    assert r.request_count == 1
    # And critically: NO exploit module was ever spawned.
    assert offline_guard.call_count == 0


def test_disallowed_target_refused_never_reaches_subprocess(
        monkeypatch, offline_guard):
    """An allowlist that does NOT contain the host -> refused even though
    danger_mode=True and other targets ARE authorised."""
    probe = _reachable_probe(monkeypatch)

    ex = _danger_executor(target_allowlist=["10.53.0.7", "lab-host.internal"])
    r = ex.execute(_high_finding(), "127.0.0.1")

    assert r.outcome == ExecutionOutcome.FAIL_NO_TARGET
    assert "target not allowlisted" in r.detail
    assert probe.call_count == 1
    assert offline_guard.call_count == 0


# ---------------------------------------------------------------------------
# Allowed target: proceeds INTO the dangerous path (subprocess reached)
# ---------------------------------------------------------------------------
def test_allowed_target_proceeds_to_subprocess(monkeypatch, offline_guard):
    """An explicitly allowlisted host goes all the way into the corpus-PoC
    subprocess; outcome parsed from the module's real output."""
    probe = _reachable_probe(monkeypatch)
    offline_guard.return_value = MagicMock(
        stdout=b"[+] EXPLOIT_SUCCESS root shell", stderr=b"", returncode=0,
    )

    ex = _danger_executor(target_allowlist=["127.0.0.1"])
    r = ex.execute(_high_finding(cve="CVE-2021-44228", port=8080), "127.0.0.1")

    # The dangerous path WAS taken: exactly one subprocess invocation.
    assert offline_guard.call_count == 1
    cmd = offline_guard.call_args.args[0]
    assert cmd[0] == "python"
    assert cmd[1] == os.path.join(CORPUS_DIR, "CVE-2021-44228.py")
    assert cmd[2:] == ["127.0.0.1", "8080"]
    # Outcome derived from REAL module output (success token), not labels.
    assert r.outcome == ExecutionOutcome.SUCCESS
    assert "danger_mode" in r.detail
    assert r.request_count == 1
    assert probe.call_count == 1


def test_outcome_parsed_from_module_output_not_labels(monkeypatch,
                                                      offline_guard):
    """Label-ignoring parse preserved: labels.json says CVE-2021-44228 is a
    'success', but a module that exits 0 WITHOUT a success token must be
    reported as FAIL_TIMEOUT (unconfirmed) -- labels are NOT trusted."""
    _reachable_probe(monkeypatch)
    offline_guard.return_value = MagicMock(
        stdout=b"ran fine, nothing confirmed", stderr=b"", returncode=0,
    )

    ex = _danger_executor(target_allowlist=["127.0.0.1"])
    r = ex.execute(_high_finding(cve="CVE-2021-44228"), "127.0.0.1")

    assert offline_guard.call_count == 1
    assert r.outcome == ExecutionOutcome.FAIL_TIMEOUT


# ---------------------------------------------------------------------------
# Pre-existing behaviour preserved around the new gate
# ---------------------------------------------------------------------------
def test_low_usability_skipped_before_danger_path(monkeypatch, offline_guard):
    """LOW-usability skip still happens BEFORE the danger path: even an
    explicitly ALLOWLISTED host is not attacked with a LOW-rank PoC."""
    probe = _reachable_probe(monkeypatch)

    ex = _danger_executor(target_allowlist=["127.0.0.1"])
    f = Finding(cve="CVE-2021-44228", port=8080,
                usability_rank=UsabilityRank.LOW)
    r = ex.execute(f, "127.0.0.1")

    assert r.outcome == ExecutionOutcome.SKIPPED
    assert "LOW usability" in r.detail
    assert offline_guard.call_count == 0


def test_unreachable_disallowed_host_reports_unreachable(monkeypatch,
                                                         offline_guard):
    """Existing FAIL_NO_TARGET semantics intact: with the socket blocked
    (conftest), an unauthorised host fails at the PROBE with an
    'unreachable' detail -- identical to pre-Stage-B behaviour."""
    ex = _danger_executor(target_allowlist=["10.53.0.7"])
    r = ex.execute(_high_finding(), "203.0.113.1")   # TEST-NET-3, unused

    assert r.outcome == ExecutionOutcome.FAIL_NO_TARGET
    assert "unreachable" in r.detail.lower()
    assert "target not allowlisted" not in r.detail
    assert offline_guard.call_count == 0


# ---------------------------------------------------------------------------
# Allowlist matching robustness (no accidental bypass / no false refusal)
# ---------------------------------------------------------------------------
def test_allowlist_matching_strips_and_casefolds(monkeypatch, offline_guard):
    """Whitespace/case differences on either side must neither bypass the
    gate nor cause a false refusal."""
    _reachable_probe(monkeypatch)
    offline_guard.return_value = MagicMock(
        stdout=b"VULNERABLE", stderr=b"", returncode=0,
    )

    ex = _danger_executor(target_allowlist=["  LocalHost  "])
    r = ex.execute(_high_finding(), "localhost")

    assert r.outcome == ExecutionOutcome.SUCCESS
    assert offline_guard.call_count == 1
