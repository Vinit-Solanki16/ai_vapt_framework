# Phase 5: Audit Reporting, Cryptographic Evidence & Scope Safeguards

## 1. Objective

Integrate **Audit-Ready Reporting**, **Cryptographic Proof-of-Concept Hashing**, and **Fail-Closed Target Authorization** into Strix (`/home/vinit/STRIX/strix`).  
This ensures that Strix operates with strict ethical security boundaries (preventing SSRF and accidental attacks on unauthorized networks) and outputs verifiable, tamper-proof reports with concrete remediation configurations.

> **CRITICAL RULE:** All modifications and new files are created **strictly inside `/home/vinit/STRIX/strix`**. The code in `/home/vinit/AI_VAPT` is only copied and adapted.

---

## 2. Target File Structure in STRIX

```
/home/vinit/STRIX/strix/
├── strix/
│   ├── core/
│   │   └── safety/                   # NEW: Scope authorization & safety controls
│   │       ├── __init__.py
│   │       ├── scope_validator.py    # Ported from AI_VAPT/vapt_platform/web_target.py
│   │       └── engagements.py        # Ported from AI_VAPT/vapt_platform/engagements.py
│   ├── tools/
│   │   └── validators/               # NEW: Active controlled non-destructive validators
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── phpinfo.py            # Exposed phpinfo() validator
│   │       ├── headers.py            # Security headers validator
│   │       ├── cookies.py            # Insecure cookie flags validator
│   │       └── files.py              # Sensitive file exposure validator
│   ├── report/
│   │   ├── builder.py                # Ported from AI_VAPT/vapt_platform/reporting/builder.py
│   │   └── renderers.py              # HTML & Markdown report templating
│   └── interface/
│       └── api.py                    # UPDATED: Report download and validation endpoints
```

---

## 3. Technical Implementation Specification

### Step 3.1: Fail-Closed Scope Gatekeeper (`strix/core/safety/scope_validator.py`)
Port and adapt from `AI_VAPT/vapt_platform/web_target.py`:
- `validate_web_target(target_url, engagement_id) -> TargetValidation`:
  1. **Parses Target**: Extracts scheme (`http`/`https`), host, and port.
  2. **DNS & IP Resolution**: Resolves host to IP addresses.
  3. **NAT64 / DNS64 Support**: Unwraps RFC 6052 prefixes (`64:ff9b::/96`) and extracts the embedded IPv4 address.
  4. **Strict IP Range Filtering**:
     - Automatically rejects RFC 1918 (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).
     - Automatically rejects Link-Local (`169.254.0.0/16` / `fe80::/10`).
     - Automatically rejects CGNAT (`100.64.0.0/10`).
     - Automatically rejects Loopback (`127.0.0.0/8`) unless explicitly authorized under a local lab profile.
  5. **Engagement Authorization**: Verifies target against saved profile (`authorized_hosts` and `allowed_ports`).
  6. **Operator Acknowledgement**: Requires explicit confirmation checkbox for external targets.

### Step 3.2: Non-Destructive Active Validators (`strix/tools/validators/`)
Port from `AI_VAPT/vapt_platform/validators/`:
- `BaseValidator.validate(candidate, base_url) -> ValidationResult`:
  - Issues controlled HTTP request without payload corruption.
  - Checks positive signatures (e.g., PHP Version header, missing CSP).
  - Computes cryptographic SHA-256 evidence hash of response:
    ```python
    evidence_hash = hashlib.sha256(response.content).hexdigest()
    ```
  - Records reproduction command (e.g. `curl -k -s -I https://target/path`).
  - Sets validation status: `CONFIRMED`, `NOT_REPRODUCIBLE`, or `INCONCLUSIVE`.

### Step 3.3: Audit-Ready Report Builder (`strix/report/builder.py`)
Port from `AI_VAPT/vapt_platform/reporting/`:
- Formats complete assessment reports:
  - **Executive Summary**: Target URL, duration, finding counts, risk summary.
  - **OWASP Breakdown**: Findings mapped to OWASP Top 10 (2021) with severity badges.
  - **Evidence Table**: Technical matched signatures, HTTP status, and cryptographic SHA-256 evidence hashes.
  - **Decision Trace**: Chronological log of GAP-1 quality scoring, attempts, and GAP-2 pivot events.
  - **Target-Specific Mitigations**: Actionable Nginx, Apache, or framework configuration snippets.
  - **Retest Procedures**: Step-by-step curl commands for post-remediation verification.
- Output Formats: Downloadable HTML (`GET /runs/{id}/report?format=html`), structured JSON, Markdown, and SARIF 2.1.0.

---

## 4. Agent Development Prompt for Phase 5

```markdown
# TASK: Phase 5 — Implement Audit Reporting, Cryptographic Proof & Scope Safeguards in STRIX

## Strict Boundaries
- Work EXCLUSIVELY inside `/home/vinit/STRIX/strix`.
- DO NOT edit any files in `/home/vinit/AI_VAPT`. Read files from `/home/vinit/AI_VAPT` as read-only reference.

## Objective
Implement fail-closed target scope enforcement, non-destructive cryptographic evidence gathering, and comprehensive HTML/JSON audit reporting inside STRIX.

## Detailed Tasks
1. Create directory `/home/vinit/STRIX/strix/strix/core/safety/`.
2. Port `/home/vinit/AI_VAPT/vapt_platform/web_target.py` into `/home/vinit/STRIX/strix/strix/core/safety/scope_validator.py`:
   - Implement `validate_web_target()` with multi-tier address checks, NAT64 unwrapping, and RFC 1918 blocking.
3. Port `/home/vinit/AI_VAPT/vapt_platform/validators/` into `/home/vinit/STRIX/strix/strix/tools/validators/`:
   - Implement `BaseValidator`, `PhpInfoValidator`, `HeadersValidator`, and `CookieValidator`.
   - Ensure every positive validation computes a SHA-256 hash of response content.
4. Port `/home/vinit/AI_VAPT/vapt_platform/reporting/` into `/home/vinit/STRIX/strix/strix/report/`:
   - Implement `builder.py` and `renderers.py` generating styled HTML and structured JSON.
   - Include OWASP categories, CVEs, CWEs, cryptographic proof hashes, decision traces, and Nginx/Apache remediation snippets.
5. Update `strix/interface/api.py`:
   - Connect `POST /targets/validate` to `validate_web_target()`.
   - Connect `GET /runs/{run_id}/report` to the report builder (supporting `format=html` and `format=json`).
6. In `strix/interface/web/js/app.js`: Ensure clicking "Validate" on the New Assessment page calls the scope validator, and clicking "View Report" renders the HTML report.
7. Write tests in `tests/test_scope_and_reporting.py` verifying:
   - Private IP (192.168.1.1) is rejected with `authorized == False`.
   - Legitimate target validates successfully.
   - HTML report generates containing SHA-256 evidence hashes and OWASP categories.
```

---

## 5. Verification & Testing Commands

```bash
# 1. Run Scope and Reporting Tests
cd /home/vinit/STRIX/strix
uv run pytest tests/test_scope_and_reporting.py -v

# 2. Test Fail-Closed Scope Rejection for Private IP
curl -s -X POST http://127.0.0.1:8000/targets/validate \
  -H "Content-Type: application/json" \
  -d '{"target_url":"http://192.168.1.1"}'
# Expected: {"authorized":false,"authorization_status":"REJECTED",...}

# 3. Test Authorized Loopback Validation
curl -s -X POST http://127.0.0.1:8000/targets/validate \
  -H "Content-Type: application/json" \
  -d '{"target_url":"http://127.0.0.1:9191"}'
# Expected: {"authorized":true,"in_scope":true,...}

# 4. Test HTML Report Generation
curl -s "http://127.0.0.1:8000/runs/latest/report?format=html" | grep -o "<title>AI VAPT Report"
# Expected: Matches HTML report title
```

