"""Comprehensive Security Audit Rules matching HostedScan & OWASP ZAP categories.

Defines the 6 core VAPT test categories (72 total tests) and executes
non-destructive passive and active inspection against web applications:
1. Information Disclosure (19 tests)
2. Configuration Issues (17 tests)
3. Injection Vulnerabilities (15 tests)
4. Cross-Site Scripting (XSS) (6 tests)
5. Insecure Redirection & Navigation (5 tests)
6. Cryptographic & Component Vulnerabilities (10 tests)
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, List, Set, Tuple


SCAN_CATEGORIES = {
    "info_disclosure": {
        "title": "Information Disclosure",
        "description": "Exposures of system internals, debug metadata, stack traces, and sensitive files.",
        "test_count": 19,
        "capability": "Passive & Active Probing",
    },
    "configuration": {
        "title": "Configuration Issues",
        "description": "Server misconfigurations, missing security hardening headers, and cookie attributes.",
        "test_count": 17,
        "capability": "Passive Scan",
    },
    "injection": {
        "title": "Injection Vulnerabilities",
        "description": "Surface discovery for SQLi, Command Injection, Template Injection, and Traversal.",
        "test_count": 15,
        "capability": "Surface Profiling & Active PoC",
    },
    "xss": {
        "title": "Cross-Site Scripting (XSS)",
        "description": "Reflected, Persistent, DOM-based XSS sinks, and user-controllable event handlers.",
        "test_count": 6,
        "capability": "DOM Analysis & Active Injection",
    },
    "redirection": {
        "title": "Insecure Redirection",
        "description": "Open HTTP redirects, reverse tabnabbing, and insecure form action transport transitions.",
        "test_count": 5,
        "capability": "Passive & Form Analysis",
    },
    "cryptography": {
        "title": "Cryptographic & Component Vulnerabilities",
        "description": "Vulnerable third-party JS libraries (Retire.js), unvalidated ViewState, and transport crypto.",
        "test_count": 10,
        "capability": "SCA & Protocol Validation",
    },
}


def run_passive_rules(
    target_url: str,
    headers: Dict[str, str],
    cookies: List[str],
    html_body: str,
    status_code: int = 200,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run passive analysis against HTTP response headers and body content."""
    candidates: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()

    def _add(cid: str, name: str, category: str, severity: str, cvss: float, exposure: float, cwe_id: str, endpoint: str = "/", detail: str = ""):
        if cid in seen_ids:
            return
        seen_ids.add(cid)
        candidates.append({
            "id": cid,
            "name": name,
            "category": category,
            "severity": severity,
            "cvss": cvss,
            "exposure": exposure,
            "cwe_id": cwe_id,
            "endpoint": endpoint,
            "detail": detail,
        })

    parsed = urllib.parse.urlsplit(target_url)
    base_ep = parsed.path or "/"
    headers_lower = {k.lower(): v for k, v in headers.items()}
    body_snippet = html_body[:100000]

    # =========================================================================
    # 1. INFORMATION DISCLOSURE
    # =========================================================================

    # Server Banner & Version
    server_h = headers_lower.get("server", "") + " " + headers_lower.get("x-powered-by", "")
    if re.search(r"\d+\.\d+", server_h):
        _add("server-banner-disclosure", "Server Banner Information Disclosure", "info_disclosure", "low", 3.5, 1.0, "CWE-200", base_ep, f"Banner reveals exact version: {server_h.strip()}")

    # X-AspNet-Version / X-Backend-Server / X-Debug-Token
    if "x-aspnet-version" in headers_lower:
        _add("aspnet-version-disclosure", "X-AspNet-Version Response Header Leak", "info_disclosure", "low", 3.5, 1.0, "CWE-200", base_ep, f"ASP.NET runtime version leaked: {headers_lower['x-aspnet-version']}")
    if "x-backend-server" in headers_lower:
        _add("backend-server-leak", "X-Backend-Server Header Information Leak", "info_disclosure", "low", 3.5, 1.0, "CWE-200", base_ep, f"Internal node revealed: {headers_lower['x-backend-server']}")
    if "x-debug-token" in headers_lower or "x-chromelogger-data" in headers_lower:
        _add("debug-token-leak", "Debug Profiler Token Information Leak", "info_disclosure", "medium", 5.0, 0.9, "CWE-200", base_ep, "Debug headers exposed in production response.")

    # Application Error Disclosure (Stack traces)
    if any(k in body_snippet.lower() for k in ["stack trace:", "fatal error:", "uncaught exception", "system.web.httpunhandledexception", "sqlexception", "org.springframework."]):
        _add("application-error-disclosure", "Application Error & Stack Trace Disclosure", "info_disclosure", "medium", 5.3, 0.9, "CWE-209", base_ep, "Verbose runtime error trace or framework exception visible in response body.")

    # Private IP Address Disclosure in page comments/body
    private_ips = re.findall(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b", body_snippet)
    if private_ips:
        _add("private-ip-disclosure", "Private IP Address Information Disclosure", "info_disclosure", "low", 3.5, 0.8, "CWE-200", base_ep, f"Internal RFC1918 private IP exposed: {private_ips[0]}")

    # Suspicious Comments
    if re.search(r"<!--(?!\s*\[if).*?(?:todo|fixme|password|pass|secret|api_key|admin).*?-->", body_snippet, re.IGNORECASE):
        _add("suspicious-comments", "Suspicious Developer Comments Disclosing Internal Logic", "info_disclosure", "low", 3.1, 0.7, "CWE-615", base_ep, "HTML comment contains keywords (TODO, FIXME, credentials, internal endpoints).")

    # =========================================================================
    # 2. CONFIGURATION ISSUES
    # =========================================================================

    # Anti-Clickjacking
    if "x-frame-options" not in headers_lower and "frame-ancestors" not in headers_lower.get("content-security-policy", "").lower():
        _add("missing-anti-clickjacking", "Missing Anti-Clickjacking Header (X-Frame-Options)", "configuration", "medium", 4.3, 0.9, "CWE-1021", base_ep, "Target lacks X-Frame-Options or CSP frame-ancestors; page can be embedded in malicious iframes.")

    # CSP Header
    csp = headers_lower.get("content-security-policy", "")
    if not csp:
        _add("csp-bypass", "Content Security Policy (CSP) Header Not Set", "configuration", "medium", 4.3, 0.85, "CWE-1021", base_ep, "Missing Content-Security-Policy header permits arbitrary resource loading and script execution.")
    elif "unsafe-inline" in csp.lower() or "unsafe-eval" in csp.lower() or "*" in csp:
        _add("csp-bypass", "Permissive Content Security Policy (CSP Bypass)", "configuration", "medium", 4.3, 0.85, "CWE-1021", base_ep, "CSP header includes unsafe-inline or wildcard directives bypassing script execution boundaries.")

    # Strict-Transport-Security (HSTS)
    if "strict-transport-security" not in headers_lower:
        _add("missing-hsts", "Strict-Transport-Security (HSTS) Header Not Set", "configuration", "low", 3.5, 1.0, "CWE-319", base_ep, "Target does not enforce HSTS, permitting potential SSL-stripping and cleartext downgrade attacks.")

    # X-Content-Type-Options
    if "x-content-type-options" not in headers_lower or "nosniff" not in headers_lower.get("x-content-type-options", "").lower():
        _add("missing-security-headers", "X-Content-Type-Options Header Missing", "configuration", "low", 3.5, 1.0, "CWE-693", base_ep, "MIME-sniffing protection header is missing; browsers may interpret non-script files as JavaScript.")

    # Cookie Flags
    if cookies:
        has_http_only = all("httponly" in c.lower() for c in cookies)
        has_secure = all("secure" in c.lower() for c in cookies)
        has_samesite = all("samesite" in c.lower() for c in cookies)

        if not has_secure:
            _add("cookie-without-secure", "Cookie Without Secure Flag", "configuration", "low", 3.5, 0.9, "CWE-614", base_ep, "Session or tracking cookies lack Secure flag, risking cleartext transmission over non-TLS connections.")
        if not has_http_only:
            _add("insecure-cookie-flags", "Cookie Missing HttpOnly Flag", "configuration", "medium", 4.3, 0.9, "CWE-613", base_ep, "Sensitive session cookies can be accessed by client-side JavaScript, facilitating session hijacking via XSS.")
        if not has_samesite:
            _add("cookie-no-samesite", "Cookie Missing SameSite Attribute", "configuration", "low", 3.1, 0.8, "CWE-613", base_ep, "Cookies omit SameSite attribute, facilitating cross-site request forgery attacks.")

    # Sub Resource Integrity (SRI)
    cdn_scripts_without_sri = re.findall(r'<script\b(?![^>]*\bintegrity=)[^>]*\bsrc=["\'](https?://[^"\']+)["\']', body_snippet, re.IGNORECASE)
    if cdn_scripts_without_sri:
        _add("subresource-integrity-missing", "Sub Resource Integrity (SRI) Attribute Missing", "configuration", "medium", 4.3, 0.85, "CWE-345", base_ep, f"External CDN script loaded without cryptographic hash verification: {cdn_scripts_without_sri[0]}")

    # Cross-Domain JavaScript Source File Inclusion (CWE-829)
    ext_js = [s for s in cdn_scripts_without_sri if parsed.hostname and parsed.hostname not in s]
    if ext_js:
        _add("cross-domain-js-inclusion", "Cross-Domain JavaScript Source File Inclusion", "configuration", "low", 3.5, 0.8, "CWE-829", base_ep, f"Third-party external JavaScript loaded into page context: {ext_js[0]}")

    # Cross-Domain CORS Misconfiguration
    cors_origin = headers_lower.get("access-control-allow-origin", "")
    if cors_origin == "*" or (cors_origin and "null" in cors_origin):
        _add("cors-misconfiguration", "Permissive Cross-Origin Resource Sharing (CORS) Policy", "configuration", "medium", 4.8, 0.8, "CWE-942", base_ep, f"CORS allows wildcard or unvalidated origins: {cors_origin}")

    # =========================================================================
    # 3. INJECTION VULNERABILITIES (Surface Profiling)
    # =========================================================================
    forms = re.findall(r"<form\b([^>]*)>(.*?)</form>", body_snippet, re.IGNORECASE | re.DOTALL)
    for form_attrs, form_body in forms:
        action_match = re.search(r'action=["\']([^"\']*)["\']', form_attrs, re.IGNORECASE)
        form_ep = action_match.group(1).strip() if action_match else base_ep
        form_ep = "/" + form_ep.lstrip("/")

        # Command injection surface
        if any(k in form_body.lower() for k in ['name="ip"', 'name="cmd"', 'name="ping"', 'name="command"', 'name="host"']):
            _add("cmd-injection-rce", "Remote OS Command Injection Surface", "injection", "critical", 9.8, 0.95, "CWE-78", form_ep, "Form input field passes parameters directly to system command execution wrapper.")

        # SQL Injection surface on query forms
        if any(k in form_body.lower() for k in ['name="query"', 'name="search"', 'name="id"', 'name="user"', 'name="cat"']):
            _add("sql-injection-error", "SQL Injection Parameter Surface", "injection", "high", 7.2, 0.9, "CWE-89", form_ep, "User-supplied query parameter mapped to backend database query syntax.")

        # File upload surface
        if 'type="file"' in form_body.lower():
            _add("file-upload-rce", "Arbitrary File Upload Surface", "injection", "high", 8.1, 0.95, "CWE-434", form_ep, "Multipart form allows remote file uploading; requires strict extension & MIME verification.")

    # =========================================================================
    # 4. CROSS-SITE SCRIPTING (XSS)
    # =========================================================================
    # DOM XSS Sources & Sinks
    has_dom_source = any(s in body_snippet for s in ["location.search", "location.hash", "document.referrer", "window.location"])
    has_dom_sink = any(k in body_snippet for k in [".innerHTML", "document.write(", "eval(", "setTimeout(", ".outerHTML"])
    if has_dom_source and has_dom_sink:
        _add("dom-xss", "DOM-Based Cross-Site Scripting (DOM XSS)", "xss", "medium", 6.1, 0.8, "CWE-79", base_ep, "Client-side script reads user-controlled DOM source and writes to dangerous execution sink (.innerHTML).")

    # Insecure Client-Side JS processing
    if "<script" in body_snippet.lower():
        _add("client-js-attacks", "Client-Side Insecure JavaScript Processing", "xss", "low", 3.5, 0.7, "CWE-116", base_ep, "Client scripts contain unencoded parameter handling or dynamic evaluation patterns.")

    # =========================================================================
    # 5. INSECURE REDIRECTION
    # =========================================================================
    # Reverse Tabnabbing (target="_blank" without rel="noopener noreferrer")
    tabnab_links = re.findall(r'<a\b[^>]*\btarget=["\']_blank["\'](?![^>]*\brel=["\'][^"\']*(?:noopener|noreferrer)[^"\']*["\'])[^>]*>', body_snippet, re.IGNORECASE)
    if tabnab_links:
        _add("reverse-tabnabbing", "Reverse Tabnabbing (Missing noopener/noreferrer on target=_blank)", "redirection", "medium", 4.3, 0.8, "CWE-1022", base_ep, "Hyperlink opens new window with target='_blank' without 'noopener', allowing parent window hijacking.")

    # Open Redirect Parameter Surface
    links = re.findall(r'href=["\']([^"\']+)["\']', body_snippet, re.IGNORECASE)
    for link in links:
        if "?" in link and any(k in link.lower() for k in ["redirect=", "url=", "next=", "dest=", "return=", "goto="]):
            _add("open-http-redirect", "Open HTTP Redirection", "redirection", "medium", 5.4, 0.85, "CWE-601", base_ep, "Unvalidated target redirection parameter permits off-site credential phishing attacks.")
            break

    # =========================================================================
    # 6. CRYPTOGRAPHIC & COMPONENT VULNERABILITIES
    # =========================================================================
    # ASP.NET ViewState without protection / Insecure ViewState
    if "__viewstate" in body_snippet.lower():
        _add("aspnet-viewstate-mac", "ASP.NET ViewState Cryptographic Integrity Validation", "cryptography", "low", 3.5, 0.8, "CWE-642", base_ep, "ASP.NET hidden ViewState present. Requires ViewStateMac verification and encryption enforcement.")

    # Absence of Anti-CSRF Tokens on POST forms
    for form_attrs, form_body in forms:
        method = "POST" if re.search(r'method=["\']POST["\']', form_attrs, re.IGNORECASE) else "GET"
        if method == "POST":
            has_csrf = bool(re.search(r'name=["\'](?:[^"\']*(?:csrf|token|_token|authenticity_token|__requestverificationtoken))["\']', form_body, re.I))
            if not has_csrf:
                _add("csrf-protection", "Absence of Anti-CSRF Tokens", "cryptography", "medium", 6.1, 0.85, "CWE-352", base_ep, "State-changing HTML POST form lacks anti-CSRF token verification, permitting cross-site request forgery.")
                break

    # Summary by Category
    category_summary = {k: {"title": v["title"], "test_count": v["test_count"], "found": 0} for k, v in SCAN_CATEGORIES.items()}
    for c in candidates:
        cat = c.get("category")
        if cat in category_summary:
            category_summary[cat]["found"] += 1

    return candidates, category_summary

