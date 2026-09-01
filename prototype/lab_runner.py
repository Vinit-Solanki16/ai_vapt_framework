"""Lab runner — executes scenarios against the Docker vulnerability emulator.

The emulator (lab/emulator/app.py) runs a Flask app with:
  GET /vuln  -> 200, body "VULNERABLE"      (observable success)
  GET /fail  -> 200, body "NOT_VULNERABLE: ..." (observable non-success)
  GET /health -> 200, {"status": "healthy"}

This module maps those real HTTP responses to decision_engine Outcome values,
giving an OBSERVED (not simulated) signal for the research contribution.

Safety: only allowlisted targets (127.0.0.1, 172.28.0.2) are permitted.
Anything else is refused before any socket is opened.
"""
from __future__ import annotations

import socket
from typing import Tuple

from decision_engine.core.schemas import Outcome

# Fail-closed allowlist: ONLY these targets may be lab-attacked.
LAB_TARGET_ALLOWLIST = {"127.0.0.1", "172.28.0.2"}

# HTTP success tokens parsed from the emulator response body.
_SUCCESS_TOKENS = ("VULNERABLE",)
_FAIL_TOKENS = ("NOT_VULNERABLE",)


def _validate_target(target: str) -> str:
    """Normalize and validate the target against the allowlist.

    Raises ValueError for any non-allowlisted target (fail-closed).
    """
    normalized = target.strip().casefold()
    allowed_normalized = {h.strip().casefold() for h in LAB_TARGET_ALLOWLIST}
    if normalized not in allowed_normalized:
        raise ValueError(
            f"Target {target!r} is not in the lab allowlist. "
            f"Allowed: {sorted(LAB_TARGET_ALLOWLIST)}. "
            "Add the target to LAB_TARGET_ALLOWLIST to authorise it."
        )
    return target.strip()


def http_get(target: str, port: int, path: str = "/vuln", timeout: float = 5.0) -> Tuple[int, str]:
    """Perform a raw HTTP GET to http://{target}:{port}{path}.

    Returns (status_code, body). On any network error, returns (0, "").
    """
    _validate_target(target)
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {target}:{port}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((target, int(port)))
        sock.sendall(request.encode())
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
        sock.close()
        response_text = response.decode(errors="replace")
        # Split headers from body
        if "\r\n\r\n" in response_text:
            _, body = response_text.split("\r\n\r\n", 1)
        else:
            body = ""
        # Parse status code
        status_line = response_text.split("\r\n", 1)[0]
        parts = status_line.split(" ")
        status_code = int(parts[1]) if len(parts) >= 2 else 0
        return status_code, body
    except Exception:
        return 0, ""


def outcome_from_response(status_code: int, body: str) -> Outcome:
    """Map an HTTP response to a decision_engine Outcome.

    - HTTP 200 + "NOT_VULNERABLE" in body -> FAIL_TIMEOUT
    - HTTP 200 + "VULNERABLE" in body     -> SUCCESS
    - Any other status / no body            -> FAIL_TIMEOUT
    """
    if status_code != 200:
        return Outcome.FAIL_TIMEOUT
    body_upper = body.upper()
    # Check fail tokens FIRST (NOT_VULNERABLE contains VULNERABLE as substring)
    for tok in _FAIL_TOKENS:
        if tok.upper() in body_upper:
            return Outcome.FAIL_TIMEOUT
    for tok in _SUCCESS_TOKENS:
        if tok.upper() in body_upper:
            return Outcome.SUCCESS
    return Outcome.FAIL_TIMEOUT


def run_lab_attempt(target: str, port: int, path: str = "/vuln") -> Outcome:
    """Single lab attempt: HTTP GET -> Outcome. This is the OBSERVED path.

    Args:
        target: IP/hostname (must be in LAB_TARGET_ALLOWLIST)
        port: TCP port
        path: HTTP path (e.g., /vuln, /fail)

    Returns:
        Outcome from parsing the real HTTP response.

    Raises:
        ValueError: if target is not allowlisted.
    """
    status_code, body = http_get(target, port, path=path)
    return outcome_from_response(status_code, body )
