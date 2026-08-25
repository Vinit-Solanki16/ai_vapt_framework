#!/usr/bin/env python3
"""
Flask vulnerability emulator for controlled validation testing.

This application provides two endpoints:
- GET /vuln: Returns HTTP 200 with body containing "VULNERABLE" (success signal)
- GET /fail: Returns HTTP 200 with body NOT containing success tokens (non-exploit simulation)

All requests are logged to stdout with timestamp, path, and client IP.
"""

import logging
import sys
from datetime import datetime
from flask import Flask, request, jsonify

# Configure logging to stdout with timestamp
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def log_request(path: str):
    """Log request details: timestamp, path, client IP."""
    client_ip = request.remote_addr
    # Also check for X-Forwarded-For header in case of proxy
    if request.headers.get('X-Forwarded-For'):
        client_ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    logger.info(f"path={path} client_ip={client_ip}")


@app.route('/vuln', methods=['GET'])
def vuln():
    """
    Vulnerable endpoint - returns success signal.
    This is the OBSERVABLE success signal for validation.
    """
    log_request('/vuln')
    return "VULNERABLE", 200


@app.route('/fail', methods=['GET'])
def fail():
    """
    Non-vulnerable endpoint - simulates non-exploit.
    Returns HTTP 200 but body does NOT contain success tokens.
    """
    log_request('/fail')
    return "NOT_VULNERABLE: This endpoint simulates a non-exploitable path", 200


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for container orchestration."""
    return jsonify({"status": "healthy"}), 200


if __name__ == '__main__':
    # Run on all interfaces, port 8080 (internal only, not published to host)
    app.run(host='0.0.0.0', port=8080)