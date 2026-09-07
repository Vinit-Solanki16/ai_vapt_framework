"""Executor HTTP API for the Docker-based lab environment.

This service acts as the bridge between the host framework and the isolated
vuln-lab-network. It:
1. Accepts HTTP POST /execute with {"target": str, "port": int, "path": str}
2. Validates target against an allowlist (127.0.0.1, 172.28.0.2)
3. Performs HTTP GET to the target
4. Maps response to Outcome (SUCCESS/FAIL_TIMEOUT)
5. Returns JSON {"outcome": "...", "detail": "..."}

The service runs INSIDE the lab network and can reach 172.28.0.2:8080,
while exposing port 9090 to the host for development.
"""

from __future__ import annotations

import logging
import socket
from typing import Optional

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

# Configuration
ALLOWED_TARGETS = {"127.0.0.1", "172.28.0.2"}
DEFAULT_TIMEOUT = 5.0  # seconds

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def validate_target(target: str) -> Optional[str]:
    """Validate target against allowlist. Returns None if allowed, error message if not."""
    if not target:
        return "Target cannot be empty"
    # Resolve hostname to IP for allowlist check
    try:
        resolved_ip = socket.gethostbyname(target)
    except socket.gaierror:
        return f"Cannot resolve target: {target}"
    if resolved_ip not in ALLOWED_TARGETS:
        return f"Target {target} ({resolved_ip}) is not in the allowlist"
    return None


def execute_target(target: str, port: int, path: str = "/") -> tuple[str, str]:
    """
    Perform HTTP GET to target and map response to Outcome.

    Returns:
        Tuple of (outcome, detail)
        outcome: "SUCCESS" or "FAIL_TIMEOUT"
        detail: Human-readable description

    Mapping logic:
        - HTTP 200 with "VULNERABLE" in response body -> SUCCESS
        - All other responses (non-200, timeout, or non-vulnerable body) -> FAIL_TIMEOUT
    """
    url = f"http://{target}:{port}{path}"
    try:
        response = requests.get(
            url,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=False,
        )
        if response.status_code == 200:
            # Check response body for vulnerability indicator
            # The emulator returns either "VULNERABLE" (success) or
            # "NOT_VULNERABLE: <reason>" (failure)
            body = response.text.strip()
            if body.startswith("VULNERABLE"):
                log.info(f"GET {url} -> 200 OK, body: {body[:50]}")
                return "SUCCESS", f"{body} from {url}"
            else:
                log.info(f"GET {url} -> 200 OK, body: {body[:50]}")
                return "FAIL_TIMEOUT", f"{body} from {url}"
        else:
            log.info(f"GET {url} -> {response.status_code}")
            return "FAIL_TIMEOUT", f"HTTP {response.status_code} from {url}"
    except requests.Timeout:
        log.info(f"GET {url} -> TIMEOUT")
        return "FAIL_TIMEOUT", f"Request to {url} timed out after {DEFAULT_TIMEOUT}s"
    except requests.ConnectionError as e:
        log.info(f"GET {url} -> CONNECTION ERROR: {e}")
        return "FAIL_TIMEOUT", f"Connection to {url} failed: {e}"
    except Exception as e:
        log.info(f"GET {url} -> ERROR: {e}")
        return "FAIL_TIMEOUT", f"Unexpected error reaching {url}: {e}"


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"}), 200


@app.route("/execute", methods=["POST"])
def execute():
    """
    Execute HTTP GET against target and return outcome.

    Request body:
        {
            "target": str,   # IP or hostname (must be in allowlist)
            "port": int,     # Target port
            "path": str      # URL path (default: "/")
        }

    Response:
        {
            "outcome": "SUCCESS" | "FAIL_TIMEOUT",
            "detail": str
        }

    Returns 403 if target is not in allowlist.
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json()

    # Validate required fields
    target = data.get("target")
    port = data.get("port")
    path = data.get("path", "/")

    if not target:
        return jsonify({"error": "Missing required field: target"}), 400
    if port is None:
        return jsonify({"error": "Missing required field: port"}), 400

    # Validate target against allowlist
    validation_error = validate_target(target)
    if validation_error:
        log.warning(f"Blocked request to disallowed target: {validation_error}")
        return jsonify({"error": validation_error}), 403

    # Execute the request
    outcome, detail = execute_target(target, port, path)

    return jsonify({
        "outcome": outcome,
        "detail": detail,
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9090, debug=False)
