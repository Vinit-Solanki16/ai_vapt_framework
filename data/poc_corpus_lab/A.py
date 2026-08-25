#!/usr/bin/env python3
"""
Lab PoC Module A - Behavioral emulator for controlled validation.

This module connects to the lab emulator's /vuln endpoint.
On HTTP 200 with "VULNERABLE" in body, prints VULNERABLE (success token).
Otherwise prints FAIL_TIMEOUT.

This is a behavioral emulator, NOT a weapon. No offensive payload.
"""

import sys
import socket
import re


def run(target: str, port: int) -> str:
    """
    Connect to emulator /vuln endpoint and check for success token.

    Args:
        target: Target IP/hostname (emulator IP, e.g., 172.28.0.2)
        port: Target port (emulator port, e.g., 8080)

    Returns:
        "VULNERABLE" if success token found in response body,
        "FAIL_TIMEOUT" otherwise.
    """
    # Build HTTP GET request for /vuln endpoint
    request = (
        f"GET /vuln HTTP/1.1\r\n"
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

        # Receive response
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk

        sock.close()

        # Decode response
        response_text = response.decode(errors="replace")

        # Parse HTTP status code
        status_match = re.search(r"HTTP/\d\.\d\s+(\d{3})", response_text)
        if not status_match:
            return "FAIL_TIMEOUT"

        status_code = int(status_match.group(1))

        # Check for HTTP 200 and VULNERABLE in body
        if status_code == 200 and "VULNERABLE" in response_text:
            return "VULNERABLE"

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
        print("Usage: python A.py <target> <port>")
        sys.exit(1)
    target = sys.argv[1]
    port = int(sys.argv[2])
    print(run(target, port))