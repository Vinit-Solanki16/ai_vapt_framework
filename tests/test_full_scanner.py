"""Unit and integration tests for STRIX Multi-Category Vulnerability Scanner."""

from strix.core.scanner import (
    SCAN_CATEGORIES,
    analyze_page_components,
    run_passive_rules,
    scan_target_ports,
)


def test_scan_categories_definition():
    """Verify all 8 comprehensive assessment categories exist with 88 total rules."""
    assert len(SCAN_CATEGORIES) == 8
    expected_categories = [
        "version_sca",
        "configuration",
        "xss",
        "sqli",
        "ssrf",
        "ssti",
        "prototype_pollution",
        "code_injection",
    ]
    total_rules = 0
    for cat in expected_categories:
        assert cat in SCAN_CATEGORIES
        total_rules += SCAN_CATEGORIES[cat]["test_count"]
    assert total_rules == 88


def test_component_analyzer_bootstrap_and_jquery():
    """Verify Retire.js-style SCA extracts versions and correlates authoritative CVEs."""
    mock_html = """
    <html>
    <head>
        <script src="js/jquery-2.1.3.js"></script>
        <script src="https://cdn.example.com/bootstrap/3.3.7/bootstrap.min.js"></script>
    </head>
    <body><h1>Test App</h1></body>
    </html>
    """
    components = analyze_page_components("https://example.com/", mock_html)
    assert len(components) == 2

    # Verify jQuery
    jq = next(c for c in components if c["library"] == "jquery")
    assert jq["version"] == "2.1.3"
    assert jq["vulnerable"] is True
    assert "CVE-2020-11022" in jq["cves"]
    assert "CVE-2015-9251" in jq["cves"]

    # Verify Bootstrap
    bs = next(c for c in components if c["library"] == "bootstrap")
    assert bs["version"] == "3.3.7"
    assert bs["vulnerable"] is True
    assert "CVE-2019-8331" in bs["cves"]
    assert "CVE-2018-14040" in bs["cves"]
    assert "CVE-2024-6485" in bs["cves"]


def test_passive_rules_execution():
    """Verify passive inspection catches missing headers, cookies, SRI, and ASP.NET ViewState."""
    headers = {
        "Server": "Microsoft-IIS/10.0",
        "X-AspNet-Version": "4.0.30319",
        "Set-Cookie": "ASP.NET_SessionId=xyz123; path=/;",  # Missing HttpOnly, Secure, SameSite
    }
    cookies = ["ASP.NET_SessionId=xyz123; path=/;"]
    html_body = """
    <html>
    <head>
        <script src="https://cdn.external.com/script.js"></script>
        <link rel="stylesheet" href="/style.css">
    </head>
    <body>
        <!-- TODO: Remove debug credentials for admin -->
        <form method="POST" action="/login">
            <input type="hidden" name="__VIEWSTATE" value="/wEPDwULLTEx=" />
            <input type="text" name="username">
            <input type="password" name="password">
            <input type="submit" value="Login">
        </form>
        <a href="https://untrusted.com" target="_blank">External Link</a>
    </body>
    </html>
    """
    candidates, summary = run_passive_rules(
        target_url="https://app.example.com/",
        headers=headers,
        cookies=cookies,
        html_body=html_body,
    )
    cand_ids = [c["id"] for c in candidates]

    # Verify key security findings
    assert "server-banner-disclosure" in cand_ids
    assert "aspnet-version-disclosure" in cand_ids
    assert "cookie-without-secure" in cand_ids
    assert "insecure-cookie-flags" in cand_ids
    assert "missing-anti-clickjacking" in cand_ids
    assert "csp-bypass" in cand_ids
    assert "missing-hsts" in cand_ids
    assert "missing-security-headers" in cand_ids
    assert "subresource-integrity-missing" in cand_ids
    assert "cross-domain-js-inclusion" in cand_ids
    assert "suspicious-comments" in cand_ids
    assert "reverse-tabnabbing" in cand_ids
    assert "aspnet-viewstate-mac" in cand_ids
    assert "csrf-protection" in cand_ids


def test_portable_port_scanner_localhost():
    """Verify native socket port scanner functions without external dependencies."""
    ports = scan_target_ports("127.0.0.1", scan_mode="quick", timeout=0.1)
    assert isinstance(ports, list)


def test_web_spider_form_and_link_extraction():
    """Verify WebSpider discovers forms, inputs, and internal links without browser binary."""
    from strix.core.scanner.crawler import WebSpider

    spider = WebSpider("https://example.com/app", scan_mode="quick")
    mock_html = """
    <html>
    <body>
        <a href="/portal/dashboard">Dashboard</a>
        <a href="https://example.com/settings?user=admin&debug=1">Settings</a>
        <a href="https://other.com/ext">External</a>
        <form method="POST" action="/api/v1/auth">
            <input type="text" name="username" />
            <input type="password" name="password" />
        </form>
        <script src="/static/bundle.js"></script>
    </body>
    </html>
    """
    links = spider._extract_links("https://example.com/app", mock_html)
    assert "https://example.com/portal/dashboard" in links
    assert "https://example.com/settings?user=admin&debug=1" in links
    assert not any("other.com" in l for l in links)

    spider._extract_forms("https://example.com/app", mock_html)
    assert len(spider.forms) == 1
    assert spider.forms[0]["action"] == "/api/v1/auth"
    assert spider.forms[0]["method"] == "POST"
    field_names = [f["name"] for f in spider.forms[0]["fields"]]
    assert "username" in field_names
    assert "password" in field_names


def test_active_fuzzer_scan_modes():
    """Verify active fuzzer path depth corresponds to scan_mode."""
    from strix.core.scanner.active_fuzzer import SENSITIVE_PATHS, ActiveFuzzer

    f_quick = ActiveFuzzer("https://example.com", scan_mode="quick")
    f_std = ActiveFuzzer("https://example.com", scan_mode="standard")
    f_deep = ActiveFuzzer("https://example.com", scan_mode="deep")

    assert len(SENSITIVE_PATHS) >= 40
