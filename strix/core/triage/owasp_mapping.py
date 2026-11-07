"""OWASP Top 10 (2021) Vulnerability Classification and Remediation Engine.

Enriches vulnerability observations and candidates with authoritative OWASP Top-10
categories, CWE identifiers, CVE references, and specialized remediation instructions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class OWASPProfile:
    """OWASP Top 10 Category Definition with Technical Remediation Standards."""

    category_id: str
    name: str
    title: str
    default_cwes: list[str]
    default_cve: str
    impact: str
    remediation_summary: str
    remediation_technical: str
    retest_procedure: str


# Granular catalog of tailored vulnerability remediation profiles
VULN_SPECIFIC_CATALOG: dict[str, dict[str, Any]] = {
    "command-injection": {
        "title": "Command Injection (Remote Code Execution)",
        "owasp_id": "A03:2021",
        "category_name": "Injection",
        "cwe_id": "CWE-78",
        "cve_id": None,
        "cvss": 9.8,
        "severity": "CRITICAL",
        "impact": "Arbitrary OS command execution with web server privileges, leading to full host compromise, webshell deployment, and internal pivoting.",
        "remediation_summary": "Disallow direct shell command invocation and enforce strict character whitelist regex validation.",
        "remediation_technical": (
            "# Nginx WAF / Rule: Block common shell metacharacters in query parameters\n"
            'if ($query_string ~* "[;|`$&<>\\(\\)]") {\n'
            "    return 403;\n"
            "}\n\n"
            "// Application Code Patch (PHP):\n"
            '// AVOID: system("ping -c 4 " . $ip);\n'
            "// SECURE: Strict input validation and non-shell API\n"
            "if (!filter_var($ip, FILTER_VALIDATE_IP)) {\n"
            "    http_response_code(400);\n"
            "    die('Invalid target IP address');\n"
            "}\n"
            "$escaped_ip = escapeshellarg($ip);\n"
            'exec("/bin/ping -c 2 {$escaped_ip}", $output, $return_var);'
        ),
        "retest_procedure": 'curl -s -k -X POST "https://<target>/vulnerabilities/exec/" --data-urlencode "ip=127.0.0.1;id" -o /dev/null -w "HTTP %{http_code}"',
    },
    "sql-injection": {
        "title": "SQL Injection (Error-Based & Blind)",
        "owasp_id": "A03:2021",
        "category_name": "Injection",
        "cwe_id": "CWE-89",
        "cve_id": None,
        "cvss": 7.2,
        "severity": "HIGH",
        "impact": "Direct manipulation of backend database structure, full data exfiltration from user tables, credential theft, and authentication bypass.",
        "remediation_summary": "Enforce PDO parameterized prepared statements and disable error output display.",
        "remediation_technical": (
            "# PHP Configuration (php.ini): Hide verbose database errors\n"
            "display_errors = Off\n"
            "log_errors = On\n\n"
            "// Application Code Patch (PHP PDO):\n"
            "// AVOID: $query = \"SELECT * FROM users WHERE user_id = '$id'\";\n"
            "// SECURE: Prepared statements with bound parameters\n"
            "$stmt = $pdo->prepare('SELECT first_name, last_name FROM users WHERE user_id = :id');\n"
            "$stmt->execute(['id' => $id]);\n"
            "$user = $stmt->fetch();"
        ),
        "retest_procedure": 'curl -s -k "https://<target>/vulnerabilities/sqli/?id=1\'&Submit=Submit" | grep -i "error in your SQL syntax"',
    },
    "reflected-xss": {
        "title": "Reflected Cross-Site Scripting (XSS)",
        "owasp_id": "A03:2021",
        "category_name": "Injection",
        "cwe_id": "CWE-79",
        "cve_id": None,
        "cvss": 6.1,
        "severity": "HIGH",
        "impact": "Execution of arbitrary client-side JavaScript in victim browser, enabling session cookie theft, credential harvesting, and DOM defacement.",
        "remediation_summary": "Enforce context-aware HTML entity output encoding and strict Content Security Policy.",
        "remediation_technical": (
            "# Nginx Hardening Header:\n"
            "add_header Content-Security-Policy \"default-src 'self'; script-src 'self'; object-src 'none';\" always;\n\n"
            "// Application Code Patch (PHP):\n"
            "// AVOID: echo '<pre>Hello ' . $_GET['name'] . '</pre>';\n"
            "// SECURE: HTML entity encode user-controlled reflection\n"
            "$safe_name = htmlspecialchars($_GET['name'] ?? '', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');\n"
            "echo '<pre>Hello ' . $safe_name . '</pre>';"
        ),
        "retest_procedure": 'curl -s -k "https://<target>/vulnerabilities/xss_r/?name=%3Cscript%3Ealert(1)%3C%2Fscript%3E&Submit=Submit" | grep -i "<script>alert(1)</script>"',
    },
    "file-upload": {
        "title": "Unrestricted Arbitrary File Upload",
        "owasp_id": "A04:2021",
        "category_name": "Insecure Design",
        "cwe_id": "CWE-434",
        "cve_id": None,
        "cvss": 8.1,
        "severity": "HIGH",
        "impact": "Upload of PHP/webshell payloads executing directly within the web document root, leading to unauthenticated remote code execution.",
        "remediation_summary": "Validate server-side MIME type and extension whitelist; store files in a non-executable directory outside webroot.",
        "remediation_technical": (
            "# Nginx Server Patch: Disable execution of scripts in uploads folder\n"
            "location ^~ /hackable/uploads/ {\n"
            "    types { text/plain php; }\n"
            "    default_type application/octet-stream;\n"
            "    location ~ \\.php$ { deny all; return 404; }\n"
            "}\n\n"
            "// Application Code Patch (PHP):\n"
            "$allowed_mimes = ['image/jpeg', 'image/png'];\n"
            "$finfo = new finfo(FILEINFO_MIME_TYPE);\n"
            "$mime = $finfo->file($_FILES['uploaded']['tmp_name']);\n"
            "if (!in_array($mime, $allowed_mimes)) { die('Invalid file type'); }\n"
            "$safe_name = bin2hex(random_bytes(16)) . '.jpg';\n"
            "move_uploaded_file($_FILES['uploaded']['tmp_name'], '/var/storage/uploads/' . $safe_name);"
        ),
        "retest_procedure": 'curl -s -k -F "uploaded=@shell.php" https://<target>/vulnerabilities/upload/ -o /dev/null -w "HTTP %{http_code}"',
    },
    "file-inclusion": {
        "title": "Local File Inclusion (LFI) & Path Traversal",
        "owasp_id": "A01:2021",
        "category_name": "Broken Access Control",
        "cwe_id": "CWE-98",
        "cve_id": None,
        "cvss": 7.5,
        "severity": "HIGH",
        "impact": "Arbitrary reading of sensitive server system files (/etc/passwd, configuration scripts) and source code via directory traversal sequences.",
        "remediation_summary": "Enforce strict allowlist mapping of permissible file inclusion targets and disable remote inclusion.",
        "remediation_technical": (
            "# PHP Configuration (php.ini):\n"
            "allow_url_include = Off\n"
            "allow_url_fopen = Off\n\n"
            "// Application Code Patch (PHP):\n"
            "// AVOID: include($_GET['page']);\n"
            "// SECURE: Whitelist lookup\n"
            "$allowed_pages = [\n"
            "    'include.php' => 'include.php',\n"
            "    'file1.php'   => 'file1.php',\n"
            "    'file2.php'   => 'file2.php',\n"
            "];\n"
            "$page = $_GET['page'] ?? 'include.php';\n"
            "if (!array_key_exists($page, $allowed_pages)) {\n"
            "    http_response_code(404);\n"
            "    die('File not found');\n"
            "}\n"
            "include($allowed_pages[$page]);"
        ),
        "retest_procedure": 'curl -s -k "https://<target>/vulnerabilities/fi/?page=../../../../etc/passwd" | grep "root:x:0:0"',
    },
    "weak-session": {
        "title": "Weak Session ID Generation & Fixation",
        "owasp_id": "A07:2021",
        "category_name": "Identification and Authentication Failures",
        "cwe_id": "CWE-384",
        "cve_id": None,
        "cvss": 5.3,
        "severity": "MEDIUM",
        "impact": "Predictable or long-lived session tokens permit session hijacking, session fixation, and unauthorized identity impersonation.",
        "remediation_summary": "Use cryptographically secure PRNG session generators, regenerate IDs upon login, and enforce short session lifetimes.",
        "remediation_technical": (
            "# PHP Session Configuration (php.ini):\n"
            "session.entropy_length = 32\n"
            "session.hash_function = sha256\n"
            "session.cookie_lifetime = 1800\n"
            "session.use_strict_mode = 1\n\n"
            "// Application Code Patch (PHP):\n"
            "session_start();\n"
            "// On successful login:\n"
            "session_regenerate_id(true);"
        ),
        "retest_procedure": 'curl -s -k -I "https://<target>/vulnerabilities/weak_id/" | grep -i "Set-Cookie"',
    },
    "csrf": {
        "title": "Cross-Site Request Forgery (CSRF)",
        "owasp_id": "A01:2021",
        "category_name": "Broken Access Control",
        "cwe_id": "CWE-352",
        "cve_id": None,
        "cvss": 6.1,
        "severity": "MEDIUM",
        "impact": "Third-party attacker websites can forge sensitive state-changing operations (such as password modification) without user consent.",
        "remediation_summary": "Enforce cryptographically random anti-CSRF synchronization tokens and SameSite cookie attributes.",
        "remediation_technical": (
            "# Nginx Cookie Policy:\n"
            'proxy_cookie_path / "/; SameSite=Strict; Secure";\n\n'
            "// Application Code Patch (PHP Synchronizer Token Pattern):\n"
            "if ($_SERVER['REQUEST_METHOD'] === 'POST') {\n"
            "    if (!hash_equals($_SESSION['csrf_token'] ?? '', $_POST['user_token'] ?? '')) {\n"
            "        http_response_code(403);\n"
            "        die('CSRF token validation failed');\n"
            "    }\n"
            "}"
        ),
        "retest_procedure": 'curl -s -k -X POST "https://<target>/vulnerabilities/csrf/" --data "password_new=test&password_conf=test&Change=Change" | grep "Password has been changed"',
    },
    "open-redirect": {
        "title": "Open HTTP Redirection",
        "owasp_id": "A01:2021",
        "category_name": "Broken Access Control",
        "cwe_id": "CWE-601",
        "cve_id": None,
        "cvss": 5.4,
        "severity": "MEDIUM",
        "impact": "Legitimate application domain abused as an open proxy trampoline for phishing campaigns and credential harvesting.",
        "remediation_summary": "Restrict redirect targets to relative internal paths or an approved destination allowlist.",
        "remediation_technical": (
            "// Application Code Patch (PHP):\n"
            "$redirect = $_GET['redirect_url'] ?? '/';\n"
            "// Enforce relative path or strict domain allowlist\n"
            "if (!preg_match('#^/(?!/)#', $redirect)) {\n"
            "    $redirect = '/';\n"
            "}\n"
            "header('Location: ' . $redirect, true, 302);\n"
            "exit();"
        ),
        "retest_procedure": 'curl -s -k -I "https://<target>/vulnerabilities/open_redirect/?redirect_url=https://evil.com" | grep -i "Location: https://evil.com"',
    },
    "cookie-flags": {
        "title": "Insecure Session Cookie Configuration",
        "owasp_id": "A07:2021",
        "category_name": "Identification and Authentication Failures",
        "cwe_id": "CWE-613",
        "cve_id": None,
        "cvss": 4.3,
        "severity": "MEDIUM",
        "impact": "Session tokens vulnerable to client-side script theft via XSS (missing HttpOnly) and transmission across unencrypted HTTP channels.",
        "remediation_summary": "Add HttpOnly, Secure, and SameSite=Strict/Lax flags to all authentication cookies.",
        "remediation_technical": (
            "# Nginx Cookie Enforcement:\n"
            'proxy_cookie_path / "/; HttpOnly; Secure; SameSite=Strict";\n\n'
            "// PHP Configuration (php.ini or session setup):\n"
            "session_set_cookie_params([\n"
            "    'lifetime' => 1800,\n"
            "    'path' => '/',\n"
            "    'secure' => true,\n"
            "    'httponly' => true,\n"
            "    'samesite' => 'Strict'\n"
            "]);"
        ),
        "retest_procedure": 'curl -s -k -I "https://<target>/" | grep -i "Set-Cookie" | grep -E "(HttpOnly|Secure|SameSite)"',
    },
    "insecure-captcha": {
        "title": "Insecure / Missing CAPTCHA Verification",
        "owasp_id": "A07:2021",
        "category_name": "Identification and Authentication Failures",
        "cwe_id": "CWE-307",
        "cve_id": None,
        "cvss": 5.0,
        "severity": "MEDIUM",
        "impact": "Missing backend challenge verification permits automated brute-force attacks, rate limit evasion, and credential stuffing.",
        "remediation_summary": "Enforce verified server-side CAPTCHA tokens combined with IP-based exponential backoff rate limiting.",
        "remediation_technical": (
            "# Nginx Rate Limiting:\n"
            "limit_req_zone $binary_remote_addr zone=login_limit:10m rate=5r/m;\n"
            "location /vulnerabilities/captcha/ {\n"
            "    limit_req zone=login_limit burst=3 nodelay;\n"
            "}\n\n"
            "// Application Code Patch: Verify challenge with upstream API\n"
            "$resp = file_get_contents(\"https://www.google.com/recaptcha/api/siteverify?secret={$secret}&response=\" . $_POST['g-recaptcha-response']);\n"
            "$data = json_decode($resp, true);\n"
            "if (!$data['success']) { die('CAPTCHA failed'); }"
        ),
        "retest_procedure": 'curl -s -k -X POST "https://<target>/vulnerabilities/captcha/" --data "step=1" | grep -i "reCAPTCHA key: Missing"',
    },
    "csp-bypass": {
        "title": "Permissive Content Security Policy (CSP Bypass)",
        "owasp_id": "A05:2021",
        "category_name": "Security Misconfiguration",
        "cwe_id": "CWE-1021",
        "cve_id": None,
        "cvss": 4.3,
        "severity": "MEDIUM",
        "impact": "Permissive or missing CSP policies (e.g. 'unsafe-inline') permit unauthorized script loading and cross-site framing.",
        "remediation_summary": "Enforce strict, nonce-based Content-Security-Policy disallowing unsafe-inline and wildcard sources.",
        "remediation_technical": (
            "# Nginx Hardening Header:\n"
            "add_header Content-Security-Policy \"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; object-src 'none'; frame-ancestors 'none'; base-uri 'self';\" always;"
        ),
        "retest_procedure": 'curl -s -k -I "https://<target>/vulnerabilities/csp/" | grep -i "Content-Security-Policy"',
    },
    "client-js": {
        "title": "Client-Side Insecure JavaScript Processing",
        "owasp_id": "A03:2021",
        "category_name": "Injection",
        "cwe_id": "CWE-116",
        "cve_id": None,
        "cvss": 3.5,
        "severity": "LOW",
        "impact": "Unescaped client-side DOM manipulation or evaluation allows client state corruption and DOM property overrides.",
        "remediation_summary": "Avoid dangerous dynamic APIs (eval, innerHTML) and enforce strict schema validation for client inputs.",
        "remediation_technical": (
            "// Client JavaScript Patch:\n"
            "// AVOID: eval(untrusted_code) or el.innerHTML = payload;\n"
            "// SECURE: Use element.textContent\n"
            "document.getElementById('result').textContent = sanitizedInput;"
        ),
        "retest_procedure": 'curl -s -k -X POST "https://<target>/vulnerabilities/javascript/" --data "phrase=success" -o /dev/null -w "HTTP %{http_code}"',
    },
    "dom-xss": {
        "title": "DOM-Based Cross-Site Scripting (DOM XSS)",
        "owasp_id": "A03:2021",
        "category_name": "Injection",
        "cwe_id": "CWE-79",
        "cve_id": None,
        "cvss": 6.1,
        "severity": "MEDIUM",
        "impact": "Client-side scripts process untrusted inputs (e.g. document.location.href) into execution sinks without sanitization.",
        "remediation_summary": "Sanitize client-side parameters using DOMPurify before DOM insertion and avoid document.write.",
        "remediation_technical": (
            "// Client JavaScript Patch:\n"
            "const urlParams = new URLSearchParams(window.location.search);\n"
            "const defaultVal = urlParams.get('default');\n"
            "// SECURE: Use safe assignment\n"
            "document.getElementById('select-menu').value = encodeURIComponent(defaultVal || '');"
        ),
        "retest_procedure": 'curl -s -k "https://<target>/vulnerabilities/xss_d/?default=English" | grep -i "document.location.href"',
    },
    "stored-xss": {
        "title": "Stored Cross-Site Scripting (Persistent XSS)",
        "owasp_id": "A03:2021",
        "category_name": "Injection",
        "cwe_id": "CWE-79",
        "cve_id": None,
        "cvss": 7.2,
        "severity": "HIGH",
        "impact": "Persistent malicious payloads stored in database tables execute automatically in every administrator or user browser loading the feed.",
        "remediation_summary": "HTML entity encode all stored data upon output and validate inputs with strict length and character constraints.",
        "remediation_technical": (
            "// Application Code Patch (PHP):\n"
            "$msg = htmlspecialchars($_POST['mtxMessage'] ?? '', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');\n"
            "$name = htmlspecialchars($_POST['txtName'] ?? '', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');\n"
            "// Store parameterized, output encoded\n"
            "$stmt = $pdo->prepare('INSERT INTO guestbook (comment, name) VALUES (:comment, :name)');\n"
            "$stmt->execute(['comment' => $msg, 'name' => $name]);"
        ),
        "retest_procedure": 'curl -s -k "https://<target>/vulnerabilities/xss_s/" | grep -i "guestbook"',
    },
    "phpinfo": {
        "title": "PHPInfo Diagnostic Configuration Disclosure",
        "owasp_id": "A01:2021",
        "category_name": "Broken Access Control",
        "cwe_id": "CWE-497",
        "cve_id": None,
        "cvss": 5.3,
        "severity": "MEDIUM",
        "impact": "Public exposure of PHP runtime parameters, active modules, server OS architecture, environmental variables, and directory structure.",
        "remediation_summary": "Delete diagnostic scripts from production docroots and block debug endpoints at the reverse proxy.",
        "remediation_technical": (
            "# Nginx Hardening Configuration:\n"
            "location ~* (phpinfo|info|test|diag)\\.php$ {\n"
            "    deny all;\n"
            "    return 404;\n"
            "}\n\n"
            "# Shell cleanup command:\n"
            "rm -f /var/www/html/phpinfo.php"
        ),
        "retest_procedure": 'curl -s -k -I "https://<target>/phpinfo.php" | grep -E "(HTTP/.* 404|HTTP/.* 403)"',
    },
    "hsts": {
        "title": "Missing HTTP Strict Transport Security (HSTS)",
        "owasp_id": "A02:2021",
        "category_name": "Cryptographic Failures",
        "cwe_id": "CWE-319",
        "cve_id": None,
        "cvss": 4.0,
        "severity": "LOW",
        "impact": "Unencrypted transport or missing HSTS header allows interception over insecure communication channels.",
        "remediation_summary": "Enforce HTTP Strict Transport Security with max-age=31536000.",
        "remediation_technical": 'add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;',
        "retest_procedure": 'curl -s -k -I "https://<target>/" | grep -i "Strict-Transport-Security"',
        "default_cwes": ["CWE-319", "CWE-310", "CWE-326"],
    },
    "missing-headers": {
        "title": "Missing Security Hardening Headers",
        "owasp_id": "A05:2021",
        "category_name": "Security Misconfiguration",
        "cwe_id": "CWE-693",
        "cve_id": None,
        "cvss": 3.5,
        "severity": "LOW",
        "impact": "Absence of defensive response headers leaves application exposed to clickjacking, MIME-type confusion sniffing, and protocol downgrade attacks.",
        "remediation_summary": "Deploy complete suite of defensive HTTP headers across all virtual host responses.",
        "remediation_technical": (
            "# Nginx Defensive Header Block:\n"
            "add_header X-Frame-Options SAMEORIGIN always;\n"
            "add_header X-Content-Type-Options nosniff always;\n"
            'add_header X-XSS-Protection "1; mode=block" always;\n'
            'add_header Referrer-Policy "strict-origin-when-cross-origin" always;\n'
            'add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;'
        ),
        "retest_procedure": 'curl -s -k -I "https://<target>/" | grep -E "(X-Frame-Options|X-Content-Type-Options|Strict-Transport-Security)"',
    },
    "cors-misconfiguration": {
        "title": "Permissive Cross-Origin Resource Sharing (CORS) Policy",
        "owasp_id": "A01:2021",
        "category_name": "Broken Access Control",
        "cwe_id": "CWE-942",
        "cve_id": None,
        "cvss": 5.4,
        "severity": "MEDIUM",
        "impact": "Permissive Access-Control-Allow-Origin headers allow malicious third-party origins to access authenticated data and issue cross-origin requests.",
        "remediation_summary": "Do not reflect untrusted request Origin headers and restrict Access-Control-Allow-Origin to explicit trusted domains.",
        "remediation_technical": (
            "# Nginx Strict CORS Configuration:\n"
            "map $http_origin $cors_origin {\n"
            '    default "";\n'
            '    "~^https://(www\\.)?yourdomain\\.com$" "$http_origin";\n'
            "}\n"
            "add_header Access-Control-Allow-Origin $cors_origin always;\n"
            'add_header Access-Control-Allow-Credentials "true" always;\n'
            'add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;'
        ),
        "retest_procedure": 'curl -s -k -I -H "Origin: https://evil.com" "https://<target><endpoint>" | grep -i "Access-Control-Allow-Origin"',
    },
    "banner-disclosure": {
        "title": "Server Diagnostic Banner Information Disclosure",
        "owasp_id": "A05:2021",
        "category_name": "Security Misconfiguration",
        "cwe_id": "CWE-200",
        "cve_id": None,
        "cvss": 4.0,
        "severity": "LOW",
        "impact": "Exposing specific web server versions simplifies reconnaissance for automated attack frameworks searching for unpatched CVEs.",
        "remediation_summary": "Suppress software version tokens in HTTP response headers (e.g. server_tokens off in Nginx, ServerTokens Prod in Apache).",
        "remediation_technical": (
            "# Nginx Hardening (nginx.conf):\n"
            "server_tokens off;\n\n"
            "# Apache Hardening (apache2.conf / httpd.conf):\n"
            "ServerTokens Prod\n"
            "ServerSignature Off"
        ),
        "retest_procedure": 'curl -s -k -I "https://<target><endpoint>" | grep -E -i "(Server|X-Powered-By)"',
    },
    "robots-exposure": {
        "title": "Sensitive Directory Information Disclosure (robots.txt)",
        "owasp_id": "A05:2021",
        "category_name": "Security Misconfiguration",
        "cwe_id": "CWE-200",
        "cve_id": None,
        "cvss": 3.5,
        "severity": "LOW",
        "impact": "Direct listing of administrative portals, staging subdirectories, and restricted paths in robots.txt guides attacker reconnaissance.",
        "remediation_summary": "Do not rely on robots.txt for access control. Enforce server-side authentication and authorization on restricted paths.",
        "remediation_technical": (
            "# Nginx Access Control for Administrative Paths:\n"
            "location ~* ^/(admin|staging|private)/ {\n"
            "    allow 10.0.0.0/8;\n"
            "    deny all;\n"
            '    auth_basic "Restricted Area";\n'
            "    auth_basic_user_file /etc/nginx/.htpasswd;\n"
            "}"
        ),
        "retest_procedure": 'curl -s -k "https://<target>/robots.txt"',
    },
    "git-exposure": {
        "title": "Exposed Git Source Code Repository Metadata",
        "owasp_id": "A05:2021",
        "category_name": "Security Misconfiguration",
        "cwe_id": "CWE-538",
        "cve_id": None,
        "cvss": 7.5,
        "severity": "HIGH",
        "impact": "Direct public access to .git metadata enables attackers to reconstruct full application source code, configuration files, and embedded credentials.",
        "remediation_summary": "Block public web access to .git directories and sensitive version control metadata.",
        "remediation_technical": (
            "# Nginx Access Control:\n"
            "location ~ /\\.git {\n"
            "    deny all;\n"
            "    return 404;\n"
            "}\n\n"
            "<!-- web.config (IIS Hidden Segments) -->\n"
            "<system.webServer>\n"
            "  <security>\n"
            "    <requestFiltering>\n"
            "      <hiddenSegments>\n"
            '        <add segment=".git" />\n'
            "      </hiddenSegments>\n"
            "    </requestFiltering>\n"
            "  </security>\n"
            "</system.webServer>"
        ),
        "retest_procedure": 'curl -s -k -I "https://<target>/.git/HEAD" | grep "HTTP"',
    },
    "web-config-exposure": {
        "title": "Sensitive Server Configuration Exposure (web.config)",
        "owasp_id": "A05:2021",
        "category_name": "Security Misconfiguration",
        "cwe_id": "CWE-200",
        "cve_id": None,
        "cvss": 7.5,
        "severity": "HIGH",
        "impact": "Public exposure of web.config discloses database connection strings, encryption keys, and internal routing logic.",
        "remediation_summary": "Enforce IIS request filtering to disallow direct downloads of configuration XML files.",
        "remediation_technical": (
            "<!-- web.config (IIS Request Filtering for Configuration Files) -->\n"
            "<system.webServer>\n"
            "  <security>\n"
            "    <requestFiltering>\n"
            "      <fileExtensions>\n"
            '        <add fileExtension=".config" allowed="false" />\n'
            "      </fileExtensions>\n"
            "    </requestFiltering>\n"
            "  </security>\n"
            "</system.webServer>"
        ),
        "retest_procedure": 'curl -s -k -I "https://<target>/web.config" | grep "HTTP"',
    },
    "trace-exposure": {
        "title": "ASP.NET Diagnostic Tracing & Error Log Exposure",
        "owasp_id": "A05:2021",
        "category_name": "Security Misconfiguration",
        "cwe_id": "CWE-200",
        "cve_id": None,
        "cvss": 5.3,
        "severity": "MEDIUM",
        "impact": "Exposed trace.axd or elmah.axd discloses detailed execution traces, HTTP request headers, session cookies, and internal exceptions.",
        "remediation_summary": "Disable diagnostic tracing or restrict handler access to authenticated administrators.",
        "remediation_technical": (
            "<!-- web.config (Disable Trace Handler in Production) -->\n"
            "<configuration>\n"
            "  <system.web>\n"
            '    <trace enabled="false" localOnly="true" pageOutput="false" />\n'
            "  </system.web>\n"
            "</configuration>"
        ),
        "retest_procedure": 'curl -s -k -I "https://<target>/trace.axd" | grep "HTTP"',
    },
    "vuln-component": {
        "title": "Vulnerable Third-Party JavaScript Library (SCA)",
        "owasp_id": "A06:2021",
        "category_name": "Vulnerable and Outdated Components",
        "cwe_id": "CWE-1104",
        "cve_id": None,
        "cvss": 6.1,
        "severity": "MEDIUM",
        "impact": "Inclusion of outdated client-side libraries with published CVE advisories enables Cross-Site Scripting (XSS), prototype pollution, and DOM hijacking.",
        "remediation_summary": "Upgrade the vulnerable library to the latest patched stable version or replace with supported alternative.",
        "remediation_technical": (
            "<!-- Upgrade Script Inclusions to Modern Patched Releases -->\n"
            '<!-- AVOID: <script src="js/jquery-2.1.3.js"></script> -->\n'
            '<script src="https://code.jquery.com/jquery-3.7.1.min.js"\n'
            '        integrity="sha256-/JqT3SQfawRcv/BIHPThkBvs0OEvtFFmqPF/lYI/Cxo="\n'
            '        crossorigin="anonymous"></script>\n\n'
            '<!-- AVOID: <script src="js/bootstrap-3.3.7.min.js"></script> -->\n'
            '<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"\n'
            '        integrity="sha384-YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz"\n'
            '        crossorigin="anonymous"></script>'
        ),
        "retest_procedure": 'curl -s "https://<target><endpoint>" | grep -Ei "(jquery|bootstrap)[.-][0-9]"',
    },
    "open-port": {
        "title": "Exposed Non-Standard TCP Network Port",
        "owasp_id": "A05:2021",
        "category_name": "Security Misconfiguration",
        "cwe_id": "CWE-200",
        "cve_id": None,
        "cvss": 5.3,
        "severity": "MEDIUM",
        "impact": "Unnecessary open TCP ports increase the accessible external attack surface and may expose unauthenticated diagnostic or telephony protocols.",
        "remediation_summary": "Close or firewall non-essential network services; restrict port access to authorized management VPNs.",
        "remediation_technical": (
            "# Linux iptables / UFW firewall rule to drop unneeded public ports:\n"
            "sudo ufw deny 1720/tcp\n"
            "sudo iptables -A INPUT -p tcp --dport 1720 -j DROP\n\n"
            "# Windows Server Advanced Firewall PowerShell command:\n"
            'New-NetFirewallRule -DisplayName "Block Port 1720 Inbound" -Direction Inbound -LocalPort 1720 -Protocol TCP -Action Block'
        ),
        "retest_procedure": "nc -zv -w 2 <target_host> <port>",
    },
    "subresource-integrity": {
        "title": "Sub Resource Integrity (SRI) Attribute Missing",
        "owasp_id": "A08:2021",
        "category_name": "Software and Data Integrity Failures",
        "cwe_id": "CWE-345",
        "cve_id": None,
        "cvss": 4.8,
        "severity": "MEDIUM",
        "impact": "External CDN-hosted scripts lacking cryptographic hash validation can be weaponized if the upstream CDN or DNS is compromised.",
        "remediation_summary": "Add cryptographic sha384 or sha512 integrity hashes and crossorigin='anonymous' attributes to all externally loaded scripts.",
        "remediation_technical": (
            "<!-- Enforce Subresource Integrity on External CDN Resources -->\n"
            '<script src="https://example-cdn.com/lib.js"\n'
            '        integrity="sha384-oqVuAfXRKap7fdgcCY5uykM6+R9GqQ8K/uxy9rx7HNQlGYl1kPzQho1wx4JwY8wC"\n'
            '        crossorigin="anonymous"></script>'
        ),
        "retest_procedure": 'curl -s "https://<target><endpoint>" | grep -E "<script.*src=.*http" | grep -v "integrity="',
    },
    "cross-domain-js": {
        "title": "Cross-Domain JavaScript Source File Inclusion",
        "owasp_id": "A08:2021",
        "category_name": "Software and Data Integrity Failures",
        "cwe_id": "CWE-829",
        "cve_id": None,
        "cvss": 4.3,
        "severity": "LOW",
        "impact": "Loading scripts directly from third-party domains introduces supply chain risk and circumvents origin boundary isolation.",
        "remediation_summary": "Host external script dependencies locally on first-party domains or enforce strict CSP script-src whitelists.",
        "remediation_technical": (
            "<!-- Host vendor scripts locally within the application asset tree -->\n"
            '<script src="/static/js/vendor/library.min.js"></script>'
        ),
        "retest_procedure": 'curl -s "https://<target><endpoint>" | grep -E "<script.*src=.*https?://"',
    },
    "aspnet-viewstate": {
        "title": "ASP.NET ViewState Cryptographic Integrity Validation",
        "owasp_id": "A08:2021",
        "category_name": "Software and Data Integrity Failures",
        "cwe_id": "CWE-642",
        "cve_id": None,
        "cvss": 3.5,
        "severity": "LOW",
        "impact": "Unencrypted or unvalidated ASP.NET ViewState data can be tampered with by clients, leading to state injection or deserialization attacks.",
        "remediation_summary": "Enforce EnableViewStateMac and ViewStateEncryptionMode in web.config.",
        "remediation_technical": (
            "<!-- web.config (Enforce ViewState Cryptographic Integrity) -->\n"
            "<configuration>\n"
            "  <system.web>\n"
            '    <pages enableViewStateMac="true" viewStateEncryptionMode="Always" />\n'
            "  </system.web>\n"
            "</configuration>"
        ),
        "retest_procedure": 'curl -s "https://<target><endpoint>" | grep -i "__VIEWSTATE"',
    },
    "reverse-tabnabbing": {
        "title": "Reverse Tabnabbing (Insecure Target Blank)",
        "owasp_id": "A01:2021",
        "category_name": "Broken Access Control",
        "cwe_id": "CWE-1022",
        "cve_id": None,
        "cvss": 5.3,
        "severity": "MEDIUM",
        "impact": "Hyperlinks opening external sites in new tabs without rel='noopener noreferrer' allow the target page to execute window.opener redirection attacks.",
        "remediation_summary": "Ensure all anchor tags with target='_blank' specify rel='noopener noreferrer'.",
        "remediation_technical": (
            "<!-- Secure External Links -->\n"
            '<!-- AVOID: <a href="https://external.test" target="_blank">Link</a> -->\n'
            '<a href="https://external.test" target="_blank" rel="noopener noreferrer">Link</a>'
        ),
        "retest_procedure": 'curl -s "https://<target><endpoint>" | grep -i \'target="_blank"\' | grep -v \'rel="noopener\'',
    },
    "ssrf": {
        "title": "Server-Side Request Forgery (SSRF)",
        "owasp_id": "A10:2021",
        "category_name": "Server-Side Request Forgery",
        "cwe_id": "CWE-918",
        "cve_id": None,
        "cvss": 8.6,
        "severity": "HIGH",
        "impact": "Induces server to make unauthorized outbound requests to loopback, local network, or cloud metadata endpoints (e.g. AWS/GCP IMDS).",
        "remediation_summary": "Enforce strict IP and domain whitelisting; block requests to 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, and 169.254.169.254.",
        "remediation_technical": (
            "// Node.js / Python SSRF Defense:\n"
            "import ipaddress, socket, urllib.parse\n"
            "def safe_fetch(url):\n"
            "    parsed = urllib.parse.urlsplit(url)\n"
            "    ip = socket.gethostbyname(parsed.hostname)\n"
            "    ip_obj = ipaddress.ip_address(ip)\n"
            "    if ip_obj.is_private or ip_obj.is_loopback:\n"
            "        raise ValueError('Access to internal/private network is restricted')\n"
            "    # Proceed with outbound request"
        ),
        "retest_procedure": 'curl -s "https://<target><endpoint>?dest=http://127.0.0.1:80"',
    },
    "ssti": {
        "title": "Server-Side Template Injection (SSTI)",
        "owasp_id": "A03:2021",
        "category_name": "Injection",
        "cwe_id": "CWE-1336",
        "cve_id": None,
        "cvss": 9.0,
        "severity": "CRITICAL",
        "impact": "Unsanitized user input evaluated by server template engine (Jinja2, Twig, Freemarker) enabling remote code execution.",
        "remediation_summary": "Never concatenate user input directly into template strings; use parameterized template context variables.",
        "remediation_technical": (
            "# Python / Jinja2 Patch:\n"
            "# AVOID: jinja2.Template('Hello ' + user_input).render()\n"
            "# SECURE:\n"
            "jinja2.Template('Hello {{ name }}').render(name=user_input)"
        ),
        "retest_procedure": 'curl -s "https://<target><endpoint>?q=%7B%7B7*7%7D%7D" | grep "49"',
    },
    "prototype-pollution": {
        "title": "Client-Side Prototype Pollution",
        "owasp_id": "A03:2021",
        "category_name": "Injection",
        "cwe_id": "CWE-1321",
        "cve_id": None,
        "cvss": 6.5,
        "severity": "MEDIUM",
        "impact": "Modification of Object.prototype enables DOM XSS, application logic alteration, and property injection across client JavaScript execution.",
        "remediation_summary": "Freeze Object.prototype via Object.freeze() or validate keys against __proto__ and constructor.",
        "remediation_technical": (
            "// Secure Object Merge Patch:\n"
            "function safeMerge(target, source) {\n"
            "    for (let key of Object.keys(source)) {\n"
            "        if (key === '__proto__' || key === 'constructor' || key === 'prototype') continue;\n"
            "        target[key] = source[key];\n"
            "    }\n"
            "    return target;\n"
            "}"
        ),
        "retest_procedure": 'curl -s "https://<target><endpoint>#__proto__[polluted]=true"',
    },
    "code-injection": {
        "title": "Server-Side Code Injection (PHP, Python, JS eval)",
        "owasp_id": "A03:2021",
        "category_name": "Injection",
        "cwe_id": "CWE-94",
        "cve_id": None,
        "cvss": 9.8,
        "severity": "CRITICAL",
        "impact": "Direct arbitrary language construct execution inside the running process, leading to host takeover and data compromise.",
        "remediation_summary": "Completely remove eval(), create_function(), and exec() language constructs from dynamic input pathways.",
        "remediation_technical": (
            "// Secure Code Pattern:\n"
            "// AVOID: eval($_POST['code']);\n"
            "// SECURE: Use strict mapping dictionaries or state machines without dynamic evaluation"
        ),
        "retest_procedure": 'curl -s "https://<target><endpoint>?code=phpinfo()"',
    },
}


def map_finding_to_owasp(
    title: str,
    rule_id: str | None = None,
    tags: list[str] | None = None,
    endpoint: str | None = None,
    tech_stack: str | None = None,
) -> dict[str, Any]:
    """Map a vulnerability finding or candidate to its authoritative profile with tailored remediation."""
    text = f"{title} {rule_id or ''} {' '.join(tags or [])}".lower()

    found = None
    if any(k in text for k in ["cors"]):
        found = VULN_SPECIFIC_CATALOG["cors-misconfiguration"]
    elif any(k in text for k in ["robots"]):
        found = VULN_SPECIFIC_CATALOG["robots-exposure"]
    elif any(k in text for k in ["banner", "version disclosure"]):
        found = VULN_SPECIFIC_CATALOG["banner-disclosure"]
    elif any(k in text for k in ["command", "exec", "ping", "cmd-injection"]):
        found = VULN_SPECIFIC_CATALOG["command-injection"]
    elif any(k in text for k in ["upload", "webshell"]):
        found = VULN_SPECIFIC_CATALOG["file-upload"]
    elif any(
        k in text
        for k in ["lfi", "file-inclusion", "path traversal", "directory traversal", "inclusion"]
    ):
        found = VULN_SPECIFIC_CATALOG["file-inclusion"]
    elif any(k in text for k in ["sqli", "sql injection", "mysql", "syntax error"]):
        found = VULN_SPECIFIC_CATALOG["sql-injection"]
    elif any(k in text for k in ["stored", "xss_s", "guestbook"]):
        found = VULN_SPECIFIC_CATALOG["stored-xss"]
    elif any(k in text for k in ["dom", "xss_d"]):
        found = VULN_SPECIFIC_CATALOG["dom-xss"]
    elif any(k in text for k in ["reflected", "xss_r", "<script>"]):
        found = VULN_SPECIFIC_CATALOG["reflected-xss"]
    elif any(k in text for k in ["git"]):
        found = VULN_SPECIFIC_CATALOG["git-exposure"]
    elif any(k in text for k in ["web.config", "web-config"]):
        found = VULN_SPECIFIC_CATALOG["web-config-exposure"]
    elif any(k in text for k in ["trace", "elmah"]):
        found = VULN_SPECIFIC_CATALOG["trace-exposure"]
    elif any(k in text for k in ["phpinfo", "php info", "diagnostic"]):
        found = VULN_SPECIFIC_CATALOG["phpinfo"]
    elif any(k in text for k in ["csrf", "cross-site request"]):
        found = VULN_SPECIFIC_CATALOG["csrf"]
    elif any(k in text for k in ["redirect", "open_redirect"]):
        found = VULN_SPECIFIC_CATALOG["open-redirect"]
    elif any(
        k in text for k in ["weak_id", "weak-session", "session fixation", "predictable session"]
    ):
        found = VULN_SPECIFIC_CATALOG["weak-session"]
    elif any(k in text for k in ["cookie", "httponly", "samesite"]):
        found = VULN_SPECIFIC_CATALOG["cookie-flags"]
    elif any(k in text for k in ["captcha", "recaptcha"]):
        found = VULN_SPECIFIC_CATALOG["insecure-captcha"]
    elif any(k in text for k in ["csp", "content security"]):
        found = VULN_SPECIFIC_CATALOG["csp-bypass"]
    elif any(k in text for k in ["client-side", "client-js", "javascript"]):
        found = VULN_SPECIFIC_CATALOG["client-js"]
    elif any(k in text for k in ["hsts", "strict-transport", "tls"]):
        found = VULN_SPECIFIC_CATALOG["hsts"]
    elif any(k in text for k in ["vuln-lib", "vulnerable js", "component", "retire"]):
        found = VULN_SPECIFIC_CATALOG["vuln-component"]
    elif any(k in text for k in ["open-port", "open tcp port", "port:"]):
        found = VULN_SPECIFIC_CATALOG["open-port"]
    elif any(k in text for k in ["subresource-integrity", "sub resource integrity", "sri"]):
        found = VULN_SPECIFIC_CATALOG["subresource-integrity"]
    elif any(k in text for k in ["cross-domain", "cross domain"]):
        found = VULN_SPECIFIC_CATALOG["cross-domain-js"]
    elif any(k in text for k in ["viewstate", "aspnet-viewstate"]):
        found = VULN_SPECIFIC_CATALOG["aspnet-viewstate"]
    elif any(k in text for k in ["tabnabbing", "reverse-tabnabbing"]):
        found = VULN_SPECIFIC_CATALOG["reverse-tabnabbing"]
    elif any(k in text for k in ["ssrf", "server-side request forgery"]):
        found = VULN_SPECIFIC_CATALOG["ssrf"]
    elif any(k in text for k in ["ssti", "template injection"]):
        found = VULN_SPECIFIC_CATALOG["ssti"]
    elif any(k in text for k in ["prototype-pollution", "prototype pollution", "__proto__"]):
        found = VULN_SPECIFIC_CATALOG["prototype-pollution"]
    elif any(k in text for k in ["code-injection", "code injection", "php-code", "eval"]):
        found = VULN_SPECIFIC_CATALOG["code-injection"]
    elif any(k in text for k in ["header", "hardening", "nosniff", "x-frame"]):
        found = VULN_SPECIFIC_CATALOG["missing-headers"]
    else:
        found = VULN_SPECIFIC_CATALOG["missing-headers"]

    res = dict(found)

    # Technology-Aware Remediation Customization
    t_low = (tech_stack or "").lower()
    if "aspnet" in t_low or "iis" in t_low:
        if "header" in text:
            res["remediation_technical"] = (
                "<!-- web.config (IIS / ASP.NET Security Hardening Headers) -->\n"
                "<configuration>\n"
                "  <system.webServer>\n"
                "    <httpProtocol>\n"
                "      <customHeaders>\n"
                '        <add name="X-Frame-Options" value="SAMEORIGIN" />\n'
                '        <add name="X-Content-Type-Options" value="nosniff" />\n'
                '        <add name="Strict-Transport-Security" value="max-age=31536000; includeSubDomains" />\n'
                '        <add name="Referrer-Policy" value="strict-origin-when-cross-origin" />\n'
                "        <add name=\"Content-Security-Policy\" value=\"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';\" />\n"
                "      </customHeaders>\n"
                "    </httpProtocol>\n"
                "  </system.webServer>\n"
                "</configuration>"
            )
        elif "cookie" in text:
            res["remediation_technical"] = (
                "<!-- web.config (IIS / ASP.NET Session Cookie Hardening) -->\n"
                "<configuration>\n"
                "  <system.web>\n"
                "    <!-- Enforce HttpOnly, RequireSSL, and SameSite across all issued session cookies -->\n"
                '    <httpCookies httpOnlyCookies="true" requireSSL="true" sameSite="Lax" />\n'
                '    <sessionState cookieSameSite="Lax" />\n'
                "  </system.web>\n"
                "</configuration>"
            )
        elif "csp" in text:
            res["remediation_technical"] = (
                "<!-- web.config (IIS / ASP.NET Content-Security-Policy) -->\n"
                "<configuration>\n"
                "  <system.webServer>\n"
                "    <httpProtocol>\n"
                "      <customHeaders>\n"
                "        <add name=\"Content-Security-Policy\" value=\"default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'self';\" />\n"
                "      </customHeaders>\n"
                "    </httpProtocol>\n"
                "  </system.webServer>\n"
                "</configuration>"
            )
        elif "csrf" in text:
            res["remediation_technical"] = (
                "// ASP.NET Web Forms Anti-CSRF Token Validation (Global.asax.cs or Page Base):\n"
                "protected void Page_Init(object sender, EventArgs e) {\n"
                "    if (User.Identity.IsAuthenticated) {\n"
                "        ViewStateUserKey = Session.SessionID;\n"
                "    }\n"
                "}"
            )

    if endpoint:
        ep_clean = "/" + endpoint.lstrip("/")
        res["retest_procedure"] = res.get("retest_procedure", "").replace("<endpoint>", ep_clean)
    else:
        res["retest_procedure"] = res.get("retest_procedure", "").replace("<endpoint>", "/")

    cve_match = re.search(r"\b(cve-\d{4}-\d{4,7})\b", text, re.I)
    if cve_match:
        res["cve_id"] = cve_match.group(1).upper()
    else:
        res["cve_id"] = found.get("cve_id") or None

    if "default_cwes" not in res:
        res["default_cwes"] = [res.get("cwe_id", "CWE-200")]
        if "CWE-200" not in res["default_cwes"]:
            res["default_cwes"].append("CWE-200")
    return res
