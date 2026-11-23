# Third-Party Notices & Attribution

AI-VAPT incorporates software and assets from open-source projects under permissive licenses. This document acknowledges the upstream authors, copyright holders, and relevant license notices.

---

## 1. Upstream Strix Engine

AI-VAPT is derived in part from the open-source Strix framework (`usestrix/strix`), developed by OmniSecure Inc. and community contributors.

* **Project:** Strix
* **Copyright:** Copyright 2025 OmniSecure Inc.
* **License:** Apache License, Version 2.0 (http://www.apache.org/licenses/LICENSE-2.0)
* **Upstream Repository:** https://github.com/usestrix/strix

AI-VAPT includes substantial original additions and derivative architectural enhancements, including:
* GAP-1 dynamic vulnerability candidate prioritization and triage engine.
* GAP-2 bounded adaptive pivoting state machine ($k \le 2$).
* Multi-provider LLM routing and custom OpenAI-compatible endpoint integration.
* Containerized Docker sandbox cleanup backstop and process lifecycle management.
* Comprehensive Web Operations Console (SPA) and multi-format report generators (SARIF v2.1.0, executive PDF, HTML with cryptographic SHA-256 evidence digests).

---

## 2. OWASP Juice Shop

The OWASP Juice Shop project is used as an authorized demonstration and validation testbed target in documentation, automated tests, and local evaluation scripts (`juice-shop.sh`).

* **Project:** OWASP Juice Shop
* **Copyright:** Copyright (c) 2014-2024 Bjoern Kimminich & the OWASP Juice Shop contributors
* **License:** MIT License (https://opensource.org/licenses/MIT)
* **Project Repository:** https://github.com/juice-shop/juice-shop

The OWASP Juice Shop is an intentionally vulnerable web application maintained by the OWASP Foundation for security training and educational purposes.

---

## 3. Runtime & Build Dependencies

All runtime Python dependencies installed via `uv.lock` and specified in `pyproject.toml` are licensed under permissive open-source licenses, including:

| Package | Upstream License | Purpose |
|---|---|---|
| `fastapi` | MIT License | REST Gateway & Control Plane |
| `uvicorn` | BSD-3-Clause | ASGI Server |
| `docker` | Apache License 2.0 | Docker Sandbox Orchestration |
| `litellm` | MIT License | Multi-Provider LLM Integration |
| `openai-agents` | MIT License | Autonomous Agent Framework |
| `pydantic` | MIT License | Data Validation & Schemas |
| `reportlab` | BSD License | PDF Report Generation |
| `pypdf` | BSD-3-Clause | PDF Processing |
| `jinja2` | BSD-3-Clause | HTML Report Templating |
| `ruff` | MIT / Apache-2.0 | Linter & Formatter |
| `mypy` | MIT License | Static Type Checking |
| `bandit` | Apache License 2.0 | Static Security Analysis |
| `pytest` | MIT License | Test Framework |

---

## 4. License Compliance Notice

This technical review confirms license compatibility for open-source research, academic evaluation, and professional engineering usage under the terms of the Apache License, Version 2.0.
