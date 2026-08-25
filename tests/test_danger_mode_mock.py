"""T-DOCKER: danger_mode parser integration test (no live target).

Verifies ``Executor._parse_module_output`` END-TO-END by driving the full
``Executor.execute()`` danger_mode path with ``subprocess.run`` MONKEYPATCHED
to return canned ``CompletedProcess`` objects. No corpus module is ever
executed and no target is touched -- the parse contract is exercised purely
from the mocked module stdout/stderr/returncode.

Three contracts (the placeholders defined until T-DOCKER formalises a spec):
  * stdout contains a success token ("VULNERABLE")  -> SUCCESS
  * stdout has no success token, clean exit (rc=0)    -> FAIL_TIMEOUT
  * non-zero exit (rc=1)                              -> FAIL_SYNTAX

The danger_mode safety gates are exercised as part of the same path (the test
must authorise the target, pass the reachability probe, and use a non-LOW
finding) so the assertion is genuinely end-to-end, not just a unit call on the
static method.
"""
from __future__ import annotations

import subprocess
import warnings
from unittest.mock import MagicMock

from core.executor import CORPUS_DIR, Executor
from core.schemas import ExecutionOutcome, Finding, UsabilityRank

# An existing corpus module so the module-exists check passes without running
# anything (subprocess.run is mocked the whole way down).
_CVE = "CVE-2021-44228"
_HOST = "127.0.0.1"
_PORT = 8080


def _high_finding() -> Finding:
    return Finding(cve=_CVE, port=_PORT, usability_rank=UsabilityRank.HIGH)


def _danger_executor() -> Executor:
    """real + danger_mode + fail-closed allowlist containing only the test host."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # construction opt-in warning expected
        return Executor(
            mode="real", danger_mode=True, target_allowlist=[_HOST],
        )


def _fake_run(stdout: bytes, stderr: bytes, returncode: int):
    """A recording subprocess.run stand-in returning a canned CompletedProcess.

    Returns a MagicMock (spy) so the test can assert the danger path reached
    subprocess.run exactly once. Its side_effect returns the canned result
    regardless of arguments.
    """
    proc = subprocess.CompletedProcess(
        args=["python"], returncode=returncode,
        stdout=stdout, stderr=stderr,
    )
    return MagicMock(side_effect=lambda *a, **k: proc)


def _patch_run(monkeypatch, stdout: bytes, stderr: bytes, returncode: int):
    """Install the canned subprocess.run spy and return it for assertions."""
    spy = _fake_run(stdout, stderr, returncode)
    monkeypatch.setattr(subprocess, "run", spy)
    return spy


def _reachable(monkeypatch):
    """Stub the TCP probe as reachable so the path proceeds to subprocess.run."""
    probe = MagicMock(return_value=(True, "reachable (stubbed)"))
    monkeypatch.setattr(Executor, "_connectivity_probe", probe)
    return probe


# ---------------------------------------------------------------------------
# stdout="VULNERABLE"  ->  SUCCESS
# ---------------------------------------------------------------------------
def test_parse_vulnerable_token_is_success(monkeypatch, offline_guard):
    _reachable(monkeypatch)
    spy = _patch_run(monkeypatch, b"VULNERABLE", b"", 0)

    ex = _danger_executor()
    r = ex.execute(_high_finding(), _HOST)

    # End-to-end: the dangerous path WAS reached (subprocess invoked once).
    assert spy.call_count == 1
    assert CORPUS_DIR  # sanity: the module path resolved against real corpus
    assert r.outcome == ExecutionOutcome.SUCCESS
    assert "danger_mode" in r.detail
    assert r.request_count == 1
    # offline_guard still untouched (T-SAFE: no stray network/subprocess).
    assert offline_guard.call_count == 0


# ---------------------------------------------------------------------------
# stdout="x" (no success token, clean exit)  ->  FAIL_TIMEOUT
# ---------------------------------------------------------------------------
def test_parse_no_token_clean_exit_is_timeout(monkeypatch, offline_guard):
    _reachable(monkeypatch)
    spy = _patch_run(monkeypatch, b"x", b"", 0)

    ex = _danger_executor()
    r = ex.execute(_high_finding(), _HOST)

    assert spy.call_count == 1
    assert r.outcome == ExecutionOutcome.FAIL_TIMEOUT
    assert "danger_mode" in r.detail
    assert offline_guard.call_count == 0


# ---------------------------------------------------------------------------
# rc=1 (non-zero exit)  ->  FAIL_SYNTAX
# ---------------------------------------------------------------------------
def test_parse_nonzero_return_is_syntax(monkeypatch, offline_guard):
    _reachable(monkeypatch)
    spy = _patch_run(monkeypatch, b"", b"boom", 1)

    ex = _danger_executor()
    r = ex.execute(_high_finding(), _HOST)

    assert spy.call_count == 1
    assert r.outcome == ExecutionOutcome.FAIL_SYNTAX
    assert "danger_mode" in r.detail
    assert offline_guard.call_count == 0
