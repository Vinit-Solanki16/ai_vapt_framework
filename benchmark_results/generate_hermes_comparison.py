import csv

fieldnames = [
    "finding_id", "title", "severity", "endpoint", "hermes_status",
    "strix_autonomous_deep", "strix_fast_web", "root_cause_difference", "validation_evidence"
]

rows = [
    {
        "finding_id": "F-01",
        "title": "Broken access control: unprivileged user enumeration and admin-role disclosure",
        "severity": "High",
        "endpoint": "GET /api/Users",
        "hermes_status": "CONFIRMED",
        "strix_autonomous_deep": "RULED_OUT_UNAUTHENTICATED",
        "strix_fast_web": "NOT_TESTED",
        "root_cause_difference": "Hermes authenticated with customer token (demo/demo) to probe /api/Users; Strix blackbox assessment operates unauthenticated by default unless credential context is supplied.",
        "validation_evidence": "GET /api/Users with Bearer demo JWT returns 23 accounts including 8 admin roles."
    },
    {
        "finding_id": "F-02",
        "title": "Sensitive data exposure: password hash in JWT payload",
        "severity": "High",
        "endpoint": "POST /rest/user/login",
        "hermes_status": "CONFIRMED",
        "strix_autonomous_deep": "RULED_OUT_UNAUTHENTICATED",
        "strix_fast_web": "NOT_TESTED",
        "root_cause_difference": "Requires authenticating session and inspecting client JWT claims (password: MD5). Strix passive header rules inspect transport headers but do not decode application JWT payloads without active token capture.",
        "validation_evidence": "JWT data payload embeds raw unsalted MD5 hash of password (fe01ce2a...)."
    },
    {
        "finding_id": "F-03",
        "title": "Publicly accessible user-level data (Feedbacks / Memories / Hints)",
        "severity": "Medium",
        "endpoint": "GET /api/Feedbacks, /rest/memories",
        "hermes_status": "CONFIRMED",
        "strix_autonomous_deep": "CANDIDATE_EXPLORED_NO_ISSUE",
        "strix_fast_web": "VALIDATED_SENSITIVE_DIRECTORY",
        "root_cause_difference": "Spider discovered endpoints; Strix classified /api/Feedbacks and /rest/memories as valid API schema endpoints rather than PII leakage because no direct secret credentials were leaked.",
        "validation_evidence": "HTTP 200 returns user email addresses and UserId fields without authentication."
    },
    {
        "finding_id": "F-04",
        "title": "Cross-authorization boundary: object-level authorization absent (IDOR)",
        "severity": "Medium",
        "endpoint": "GET /api/BasketItems/1",
        "hermes_status": "CONFIRMED",
        "strix_autonomous_deep": "RULED_OUT_UNAUTHENTICATED",
        "strix_fast_web": "NOT_TESTED",
        "root_cause_difference": "Requires authenticated session (Bearer token) with horizontal basket traversal. Without valid customer token, endpoint returns 401 Unauthorized.",
        "validation_evidence": "Authenticated demo token successfully retrieves BasketId: 1 belonging to another user."
    },
    {
        "finding_id": "F-05",
        "title": "Weak transport / browser security headers (Missing CSP, CORS *)",
        "severity": "Low",
        "endpoint": "GET /",
        "hermes_status": "CONFIRMED",
        "strix_autonomous_deep": "INVESTIGATED_RULED_OUT",
        "strix_fast_web": "VALIDATED_AS_OBSERVATION",
        "root_cause_difference": "Phase 13 Guard 3 correctly calibrated missing headers to observation tier; prevents synthetic critical CVSS 9.4 without DOM exploit PoC.",
        "validation_evidence": "GET / response headers lack CSP, Referrer-Policy, Permissions-Policy; Access-Control-Allow-Origin: *."
    },
    {
        "finding_id": "F-06",
        "title": "Weak credentials / default password for administrative account",
        "severity": "High",
        "endpoint": "POST /rest/user/login",
        "hermes_status": "CONFIRMED",
        "strix_autonomous_deep": "NOT_TESTED",
        "strix_fast_web": "NOT_TESTED",
        "root_cause_difference": "Strix safety policy excludes brute force or credential guessing unless explicit dictionary attack is configured in scan profile.",
        "validation_evidence": "POST /rest/user/login with admin@juice-sh.op / admin123 succeeds with HTTP 200 and administrative JWT."
    },
    {
        "finding_id": "F-07",
        "title": "Error/information disclosure through exception pages",
        "severity": "Low",
        "endpoint": "GET /rest/order-history",
        "hermes_status": "CONFIRMED",
        "strix_autonomous_deep": "INVESTIGATED_RULED_OUT",
        "strix_fast_web": "NOT_TESTED",
        "root_cause_difference": "Returns HTTP 500 with proxy error string; Strix active scanner treats 500 error as server-side error rather than exploitable disclosure unless stack trace leaks secrets.",
        "validation_evidence": "GET /rest/order-history returns HTTP 500 with 'Blocked illegal activity by ::ffff:172.17.0.1'."
    }
]

out_path = "/home/vinit/STRIX/strix/benchmark_results/hermes_comparison.csv"
with open(out_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
print(f"Wrote {len(rows)} findings to {out_path}")
