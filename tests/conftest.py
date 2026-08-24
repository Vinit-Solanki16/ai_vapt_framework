"""Shared pytest fixtures for the AI VAPT Framework regression suite.

Guarantees every test runs OFFLINE: any accidental network or subprocess call
is either stubbed deterministically or made to fail loudly. The subprocess.run
mock is exposed so individual tests can assert it was NOT invoked (T-SAFE).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Make the project root importable so `import core...` works when pytest is
# launched from anywhere (tests/ is also a valid cwd).
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core.scanner  # noqa: E402  (needs ROOT on path first)
import requests       # noqa: E402
import socket         # noqa: E402


@pytest.fixture(autouse=True)
def offline_guard(monkeypatch):
    """Block network + record subprocess so offline behaviour is enforced.

    Returns the MagicMock standing in for subprocess.run so tests can assert
    call_count == 0 (the executor must never shell out to a corpus PoC in the
    modes under test).
    """
    # EPSS live API -> deterministic offline stub
    monkeypatch.setattr(
        core.scanner, "fetch_epss_score",
        lambda cve_id, timeout=5: 0.0,
    )
    # Any stray HTTP request fails loudly (no Ollama / no EPSS / no GitHub)
    monkeypatch.setattr(
        requests, "get",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("NETWORK BLOCKED in test")),
    )
    # Any stray TCP probe fails loudly
    monkeypatch.setattr(
        socket, "create_connection",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("NETWORK BLOCKED in test")),
    )
    # Subprocess is recorded (not raised) so tests can assert call_count == 0
    run_mock = MagicMock(name="subprocess.run")
    monkeypatch.setattr(subprocess, "run", run_mock)
    yield run_mock
