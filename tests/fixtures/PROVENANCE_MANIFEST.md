# AI-VAPT Test Fixtures — Provenance & Sanitization Manifest

This directory contains sanitized historical output runs used as golden files and structural fixtures for regression testing across the AI-VAPT platform.

## Sanitization Attestation
- **No Private Keys:** All RSA, EC, and OpenSSH private keys are excluded.
- **No API Credentials:** OpenAI, OpenRouter, Gemini, Anthropic, and custom provider API keys have been removed or replaced with synthetic mocks (`sk-mock-...`).
- **No Target Authentication Tokens:** Target session cookies and authorization tokens have been sanitized.
- **Controlled Targets Only:** All recorded network endpoints point exclusively to local loopback (`127.0.0.1`, `localhost`) or synthetic mock hosts (`http://target`).

## Fixture Catalog

| Run ID | Purpose | Formats Included | Sanitization Status |
|---|---|---|---|
| `run-14ee778a` | Baseline scan run data for report generation tests | JSON, SARIF, HTML, PDF, Markdown, CSV | Verified Sanitized |
| `run-3ef51eab` | Candidate lifecycle & multi-turn evaluation fixture | JSON, SARIF, Markdown, CSV | Verified Sanitized |
| `run-8ae38b46` | HTML & PDF report formatting golden files | JSON, SARIF, HTML, PDF, Markdown, CSV | Verified Sanitized |
| `run-95c0f177` | SARIF v2.1.0 & CWE/OWASP mapping validation | JSON, SARIF, Markdown, CSV | Verified Sanitized |
| `run-b9a3b0b2` | Multi-vulnerability state hydration & finding verification | JSON, SARIF, Markdown, CSV, vuln details | Verified Sanitized |
| `run-fd0f5ec4` | Bounded dynamic pivoting (GAP-2) and queue state | JSON, SARIF, Markdown, CSV | Verified Sanitized |
