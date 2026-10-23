"""Isolated local HTTP test fixtures with intentionally vulnerable and negative-control endpoints.

Used for the reproducible ground-truth finding reliability evaluation suite.
No external network calls; runs in-process on an ephemeral loopback socket.
"""
from __future__ import annotations

import http.server
import socketserver
import threading
import time
from contextlib import contextmanager
from typing import Generator


class EvalFixtureHTTPHandler(http.server.BaseHTTPRequestHandler):
    """HTTP Request handler providing positive and negative control endpoints."""

    def log_message(self, format: str, *args: object) -> None:
        """Suppress standard HTTP server stderr logging in test output."""
        pass

    def do_GET(self) -> None:
        path = self.path.split("?")[0]

        # 1. PHPInfo Positive Endpoint (Intentionally Vulnerable)
        if path == "/phpinfo-vuln":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            body = (
                "<!DOCTYPE html><html><head><title>phpinfo()</title></head><body>"
                "<h1 class='p'>PHP Version 8.1.2-1ubuntu2.14</h1>"
                "<table><tr><td class='e'>Configuration File (php.ini) Path</td>"
                "<td class='v'>/etc/php/8.1/cli</td></tr>"
                "<tr><td class='e'>Zend Extension Build</td><td class='v'>API420210902,NTS</td></tr>"
                "</table></body></html>"
            )
            self.wfile.write(body.encode("utf-8"))
            return

        # 2. PHPInfo Negative Control (Not Vulnerable - 404 or Clean Page)
        if path == "/phpinfo-clean":
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<!DOCTYPE html><html><body><h1>404 Not Found</h1></body></html>")
            return

        # 3. Cookie Positive Control: Missing HttpOnly Flag (Intentionally Vulnerable)
        if path == "/cookie-vuln-httponly":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            # Set cookie WITHOUT HttpOnly
            self.send_header("Set-Cookie", "session_id=insecure_token_123; Path=/; Secure; SameSite=Lax")
            self.end_headers()
            self.wfile.write(b"Cookie set without HttpOnly flag.")
            return

        # 4. Cookie Negative Control: With HttpOnly Flag (Clean, Not Vulnerable)
        if path == "/cookie-clean-httponly":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            # Set cookie WITH HttpOnly
            self.send_header("Set-Cookie", "session_id=secure_token_456; Path=/; HttpOnly; Secure; SameSite=Lax")
            self.end_headers()
            self.wfile.write(b"Cookie set with HttpOnly flag.")
            return

        # 5. Cookie Positive Control: Missing Secure Flag (Intentionally Vulnerable)
        if path == "/cookie-vuln-secure":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            # Set cookie WITHOUT Secure
            self.send_header("Set-Cookie", "auth_token=plaintext_auth_789; Path=/; HttpOnly; SameSite=Lax")
            self.end_headers()
            self.wfile.write(b"Cookie set without Secure flag.")
            return

        # 6. Cookie Negative Control: With Secure Flag (Clean, Not Vulnerable)
        if path == "/cookie-clean-secure":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            # Set cookie WITH Secure
            self.send_header("Set-Cookie", "auth_token=secure_auth_999; Path=/; HttpOnly; Secure; SameSite=Lax")
            self.end_headers()
            self.wfile.write(b"Cookie set with Secure flag.")
            return

        # 7. HTTP Error 500 Endpoint (Inconclusive Trigger)
        if path == "/error-500":
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"500 Internal Server Error (Database connection failed)")
            return

        # 8. Redirect 302 Endpoint
        if path == "/redirect-302":
            self.send_response(302)
            self.send_header("Location", "/login")
            self.end_headers()
            return

        # 9. Timeout Endpoint (Simulates unresponsive server)
        if path == "/timeout":
            time.sleep(1.0)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Slow response")
            return

        # 10. Default clean fallback
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")


class ThreadedTCPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Threaded HTTP Server that allows immediate port reuse."""
    allow_reuse_address = True
    daemon_threads = True


@contextmanager
def run_eval_server(host: str = "127.0.0.1", port: int = 0) -> Generator[str, None, None]:
    """Launch an in-process evaluation HTTP server on an ephemeral port.

    Yields:
        Base URL string, e.g. 'http://127.0.0.1:45678'
    """
    server = ThreadedTCPServer((host, port), EvalFixtureHTTPHandler)
    assigned_port = server.server_address[1]
    base_url = f"http://{host}:{assigned_port}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()


def eval_fixture_client(url: str, timeout: float = 5.0) -> Any:
    """In-memory client for evaluation fixtures, bypassing OS sockets in offline tests."""
    import urllib.error
    from urllib.parse import urlparse
    from vapt_platform.verification import HttpResponse

    path = urlparse(url).path
    if path == "/phpinfo-vuln":
        body = (
            "<!DOCTYPE html><html><head><title>phpinfo()</title></head><body>"
            "<h1 class='p'>PHP Version 8.1.2-1ubuntu2.14</h1>"
            "<table><tr><td class='e'>Configuration File (php.ini) Path</td>"
            "<td class='v'>/etc/php/8.1/cli</td></tr>"
            "<tr><td class='e'>Zend Extension Build</td><td class='v'>API420210902,NTS</td></tr>"
            "</table></body></html>"
        )
        return HttpResponse(status=200, headers={"content-type": ["text/html; charset=utf-8"]}, body=body)

    if path == "/phpinfo-clean":
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    if path == "/cookie-vuln-httponly":
        return HttpResponse(
            status=200,
            headers={
                "content-type": ["text/html"],
                "set-cookie": ["session_id=insecure_token_123; Path=/; Secure; SameSite=Lax"],
            },
            body="Cookie set without HttpOnly flag.",
        )

    if path == "/cookie-clean-httponly":
        return HttpResponse(
            status=200,
            headers={
                "content-type": ["text/html"],
                "set-cookie": ["session_id=secure_token_456; Path=/; HttpOnly; Secure; SameSite=Lax"],
            },
            body="Cookie set with HttpOnly flag.",
        )

    if path == "/cookie-vuln-secure":
        return HttpResponse(
            status=200,
            headers={
                "content-type": ["text/html"],
                "set-cookie": ["auth_token=plaintext_auth_789; Path=/; HttpOnly; SameSite=Lax"],
            },
            body="Cookie set without Secure flag.",
        )

    if path == "/cookie-clean-secure":
        return HttpResponse(
            status=200,
            headers={
                "content-type": ["text/html"],
                "set-cookie": ["auth_token=secure_auth_999; Path=/; HttpOnly; Secure; SameSite=Lax"],
            },
            body="Cookie set with Secure flag.",
        )

    if path == "/error-500":
        raise urllib.error.HTTPError(url, 500, "Internal Server Error", {}, None)

    if path == "/redirect-302":
        return HttpResponse(status=302, headers={"location": ["/login"]}, body="")

    if path == "/timeout":
        raise TimeoutError("Connection timed out after 0.2s")

    return HttpResponse(status=200, headers={"content-type": ["text/plain"]}, body="OK")
