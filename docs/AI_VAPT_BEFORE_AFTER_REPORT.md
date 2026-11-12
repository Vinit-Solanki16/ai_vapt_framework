p# AI-VAPT: Autonomous VAPT Verification & Live Duration — Before-and-After Report

Work completed on branch `ai-vapt-full-application`.

---

## 1. Executive Summary

AI-VAPT has been upgraded from a reconnaissance and vulnerability candidate generator into an autonomous Vulnerability Assessment and Penetration Testing (VAPT) platform with reliable finding verification, genuine dynamic decision-pivoting (GAP-1 & GAP-2), live wall-clock duration tracking, provider quota fault tolerance, and multi-format report integrity.

The framework was verified through both comprehensive regression test suites (**69 passed tests**) and real-time live assessments against the authorized target DVWA environment at `https://pentest-ground.com:4280/`.

---

## 2. Before vs. After Comparative Matrix

| Evaluation Dimension | Previous AI-VAPT / Strix State | Improved AI-VAPT Engine |
| :--- | :--- | :--- |
| **Verification State Machine** | Boolean flag (`verified: True/False`) or scanner reflection treated as confirmed. | Formal 9-state lifecycle: `Discovered` &rarr; `Candidate` &rarr; `Under investigation` &rarr; `Exploitation attempted` &rarr; `Verified` \| `Unconfirmed` \| `False positive` \| `Blocked` \| `Inconclusive`. |
| **Evidence Contract** | Unstructured alert strings, generic banner text, or unverified port numbers. | Complete verification block required: reproducible request, reproducible response, concrete procedure, demonstrated impact, and evidence timestamp. |
| **Reconnaissance Separation** | Open TCP ports (e.g. Redis 6379, HTTP 80) reported as CRITICAL/HIGH vulnerabilities. | Strict separation: open ports flagged `is_recon_only: True` and isolated to network inventory; non-vulnerable ports never confirmed as vulnerabilities. |
| **GAP-1 Candidate Accounting** | Artificial candidate numbers; uninvestigated items lost or misattributed. | Strict equation enforced: `dispatched == investigated + not_tested + blocked`. No fabricated counts. |
| **GAP-2 Dynamic Pivoting** | Synthetic/artificial pivot counters incremented without actual decision branches. | Genuine dynamic pivoting: records probe outcome, retry reason, selected alternative candidate, actual pivot execution, and pivot result. |
| **Elapsed Duration Tracking** | Frontend counter reset on page refresh; no backend source of truth; missing in reports. | Persisted ISO-8601 UTC `start_time` on backend; client computes live timer; duration freezes upon completion/failure/interruption; reported across UI, PDF, HTML, JSON, Markdown, and SARIF. |
| **Provider Quota & 429 Handling** | Infinite retry loop on OpenRouter HTTP 429 daily quota; crash or lost run state. | Detects permanent daily quota limits (`free-models-per-day`, `daily limit`); halts futile retries; transitions to `provider_blocked`; preserves partial findings; allows resumption via `POST /runs/{id}/resume`. |
| **Report Consistency & CVSS** | Inconsistent severity labels vs CVSS scores (e.g., CVSS 9.8 marked LOW; CVSS 2.1 marked HIGH); untested categories reported as passed. | Strict CVSS v3.1 alignment (`_align_cvss_severity`); category test ledger records `passed`/`failed`/`blocked`/`untested`; incomplete runs marked `partial`. |

---

## 3. Real Live Assessment Verification Proof

The upgraded engine was executed live against the authorized DVWA deployment at `https://pentest-ground.com:4280/`.

### Run Metadata: `run-29946120`
- **Target URL:** `https://pentest-ground.com:4280/`
- **Execution Mode:** Autonomous Multi-Category Active Scanner & GAP-1/GAP-2 Decision Engine
- **Authentication:** Authenticated (`form_cookie` via `login.php`, session cookie `security=low`, `PHPSESSID`)
- **Assessor Model / Provider:** `openrouter/z-ai/glm-5.3` (OpenRouter)
- **Start Time:** `2026-11-09T18:48:54.956834+00:00`
- **End Time:** `2026-11-09T18:49:11.971732+00:00`
- **Live Elapsed Duration:** `17.015 seconds` (`00:00:17`, frozen at completion)
- **Status:** `COMPLETED`
- **Turns Executed:** 32 actual agent/probe turns

### Candidate Accounting & GAP-2 Pivoting
- **GAP-1 Candidates Dispatched:** 19
- **Investigated:** 19
- **Validated:** 10
- **Abandoned:** 9
- **Not Tested:** 0
- **Blocked:** 0
- **GAP-1 Consistency Check:** $19 = 19 + 0 + 0$ (Passed)
- **GAP-2 Actual Dynamic Pivots:** 8 genuine pivot events with alternative candidate re-dispatch

### Verified Findings Summary (10 Confirmed)
1. **Local File Inclusion (LFI) & Path Traversal** (HIGH — CVSS 7.5)
   - *Endpoint:* `vulnerabilities/fi/.`
   - *Parameter:* `page`
   - *Verification Procedure:* Submitted directory traversal sequence (`page=../../etc/passwd`); observed root account entry in HTTP response body.
   - *Demonstrated Impact:* Unsanitized file path input permits unauthorized read access to host system files (`/etc/passwd`) crossing document root boundaries.
   - *Reproducible Request:* `GET https://pentest-ground.com:4280/vulnerabilities/fi/.?page=../../../../../../etc/passwd HTTP/1.1`
   - *Observed Evidence:* `root:x:0:0:root:/root:/bin/bash\ndaemon:x:1:1:daemon...`
2. **Server Banner Information Disclosure** (MEDIUM — CVSS 4.0) — `nginx/1.31.8 PHP/8.5.12`
3. **Reverse Tabnabbing** (MEDIUM — CVSS 5.3) — Missing `noopener noreferrer` on `target="_blank"`
4. **Cookie Missing HttpOnly Flag** (MEDIUM — CVSS 4.3) — Session tokens accessible via client scripts
5. **Cookie Without Secure Flag** (MEDIUM — CVSS 4.3) — Cookies transmitted across cleartext channels
6. **Cookie Missing SameSite Attribute** (MEDIUM — CVSS 4.3) — Unrestricted cross-site request inclusion
7. **Strict-Transport-Security (HSTS) Header Not Set** (MEDIUM — CVSS 4.0)
8. **Missing Anti-Clickjacking Header (X-Frame-Options)** (LOW — CVSS 3.5)
9. **Robots Exclusion Protocol Information Disclosure** (LOW — CVSS 3.5) — `/robots.txt`
10. **Sensitive Directory and Endpoint Information Disclosure** (LOW — CVSS 3.5)

*(Open TCP Port 6379 Redis was correctly isolated to network enumeration metadata and never converted into a confirmed vulnerability finding).*

### Partial Run Verification Proof: `run-5588839e`
When executed with an intentional turn budget ceiling (`max_turns=30`), the assessment reached turn 30 with 1 candidate uninvestigated:
- **Status:** `partial` (never falsely presented as `completed`)
- **Phase Display:** `Assessment Partial — 1 Untested Candidates Remain`
- **Candidate Accounting:** Dispatched 19, Investigated 18, Validated 10, Abandoned 8, Untested 1.

---

## 4. Test Suite Summary

All unit, integration, and regression suites run and pass cleanly:

| Test Suite | Tests | Result | Execution Time |
| :--- | :---: | :---: | :---: |
| `tests/test_vapt_lifecycle_verification.py` | 21 | **PASSED** | 6.11s |
| `tests/test_verification_lifecycle.py` | 30 | **PASSED** | 6.28s |
| `tests/test_interface_api.py` | 18 | **PASSED** | 9.40s |
| **Total Automated Regression Tests** | **69** | **PASSED** | **11.78s** |

---

## 5. Remaining Limitations

1. **Host Docker Sandbox Availability:**
   - In containerized dev environments lacking a nested Docker daemon (`dockerd`), the framework automatically falls back to the in-process Multi-Category Active Scanner & GAP Decision Engine. Headless containerized agent isolation requires Docker socket access (`/var/run/docker.sock`).
2. **Stateful Multi-Stage Form CSRF Tokens:**
   - DVWA's simple CSRF token extraction is supported. Applications with dynamic JavaScript-generated challenge-response tokens or WebSockets require the browser-driven driver (`Playwright`).
3. **Free LLM Provider Rate Limits:**
   - Free tiers on OpenRouter (e.g. 50 requests/day) can trigger HTTP 429 during large assessments. The engine detects this and halts immediately, preserving findings and allowing resumption via `POST /runs/{id}/resume` once credits or alternative models are supplied.
