#!/usr/bin/env python3
"""
Lab PoC Module B - Controlled dead-end for GAP-1 ordering (S1 candidate).

This module connects to the lab emulator's /fail endpoint.
Always prints FAIL_TIMEOUT (simulates non-exploitable path).

Behaviourally identical to C.py; exists as a separate candidate so Scenario
S1 presents [A(/vuln, HIGH usability), B(/fail, LOW usability)] per the
T-DOCKER experiment protocol (Part D, Scenario S1). Its LOW usability rank
means the executor's pre-existing safety gate skips it BEFORE any dangerous
path - demonstrating pre-execution assessment suppressing a dead-end.

This is a behavioral emulator, NOT a weapon. No offensive payload.
"""

import sys
import socket


def run(target: str, port: int) -> str:
    """
    Connect to emulator /fail endpoint.
    Always returns FAIL_TIMEOUT (controlled failure).

    Args:
        target: Target IP/hostname (emulator IP, e.g., 127.0.0.1)
        port: Target port (emulator port, e.g., 8080)

    Returns:
        Always "FAIL_TIMEOUT" - simulates non-exploitable path.
    """
    # Build HTTP GET request for /fail endpoint
    request = (
        f"GET /fail HTTP/1.1\r\n"
        f"Host: {target}:{port}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )

    try:
        # Create socket with timeout
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)

        # Connect to target
        sock.connect((target, port))

        # Send HTTP request
        sock.sendall(request.encode())

        # Receive response (consume it)
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break

        sock.close()

        # Always return FAIL_TIMEOUT for controlled failure
        return "FAIL_TIMEOUT"

    except socket.timeout:
        return "FAIL_TIMEOUT"
    except ConnectionRefusedError:
        return "FAIL_TIMEOUT"
    except OSError:
        return "FAIL_TIMEOUT"
    except Exception:
        return "FAIL_TIMEOUT"


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python B.py <target> <port>")
        sys.exit(1)
    target = sys.argv[1]
    port = int(sys.argv[2])
    print(run(target, port))
