"""Master Multi-Category Vulnerability Scanner & Reconnaissance Engine.

Orchestrates:
1. Pure-Python Web Spidering (depth 1 in quick, 2 in standard, 3 in deep)
2. Pure-Python TCP Port Scanner (15 ports in quick, 40 in standard, 85+ in deep)
3. Software Component Analysis (Retire.js-style CVE mapping)
4. Comprehensive 8-Category Passive Rule Engine (88 tests)
5. Active Endpoint Prober, HTTP Verb Tampering & Parameter Fuzzing
"""

from __future__ import annotations

import logging
import ssl
import urllib.parse
import urllib.request
from typing import Any

from .active_fuzzer import ActiveFuzzer
from .component_analyzer import analyze_page_components
from .crawler import WebSpider
from .passive_rules import SCAN_CATEGORIES, run_passive_rules
from .port_scanner import scan_target_ports


logger = logging.getLogger("strix.core.scanner")


class FullScanner:
    """Orchestrates comprehensive multi-category scanning across web and network layers."""

    @classmethod
    def scan_target(
        cls,
        target_url: str,
        scan_mode: str = "quick",
        timeout: float = 7.0,
    ) -> dict[str, Any]:
        """Perform full multi-category assessment against target URL."""
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        headers_dict: dict[str, str] = {}
        cookies_list: list[str] = []
        body_text = ""
        status_code = 200

        parsed_target = urllib.parse.urlsplit(target_url)
        base_endpoint = parsed_target.path or "/"

        # 1. Fetch Target Landing Page
        try:
            req = urllib.request.Request(
                target_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 STRIX-VAPT/2.0",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                headers_dict = {k.lower(): v for k, v in resp.headers.items()}
                cookies_list = resp.headers.get_all("Set-Cookie") or []
                raw_bytes = resp.read(150000)
                body_text = raw_bytes.decode("utf-8", errors="ignore")
                status_code = resp.status
        except Exception as exc:
            logger.warning("Target request error on %s: %s", target_url, exc)

        # 2. Web Spidering (depth 1 in quick, 2 in standard, 3 in deep)
        spider = WebSpider(base_url=target_url, scan_mode=scan_mode, timeout=min(timeout, 3.5))
        spider_results = spider.crawl()

        # 3. Run Comprehensive Passive Audit Rules across all 6 categories
        candidates, category_summary = run_passive_rules(
            target_url=target_url,
            headers=headers_dict,
            cookies=cookies_list,
            html_body=body_text,
            status_code=status_code,
        )

        # 4. Run Software Component Analysis (SCA) for vulnerable libraries (e.g. Bootstrap, jQuery)
        components = analyze_page_components(base_url=target_url, html_body=body_text, timeout=3.0)
        for comp in components:
            if comp["vulnerable"]:
                cve_list = comp["cves"]
                cve_str = ", ".join(cve_list)
                cve_primary = cve_list[0] if cve_list else None
                candidates.append(
                    {
                        "id": f"vuln-lib-{comp['library']}",
                        "name": f"Vulnerable JS Library: {comp['library']} {comp['version']}",
                        "category": "version_sca",
                        "severity": comp["severity"],
                        "cvss": comp["cvss"],
                        "exposure": 0.9,
                        "cve_id": cve_primary,
                        "cve_list": cve_list,
                        "cwe_id": "CWE-1104",  # Use of Unmaintained/Vulnerable Third-Party Component
                        "endpoint": comp["source_file"],
                        "detail": f"Identified library {comp['library']} v{comp['version']} contains known public vulnerabilities: {cve_str}.",
                    }
                )
                if "version_sca" in category_summary:
                    category_summary["version_sca"]["found"] += 1

        # 5. Active Probing, Directory Enumeration & Parameter Fuzzing
        fuzzer = ActiveFuzzer(base_url=target_url, scan_mode=scan_mode, timeout=2.0)

        # 5a. Sensitive path enumeration
        path_findings = fuzzer.probe_paths()
        for pf in path_findings:
            candidates.append(pf)
            cat_k = pf.get("category", "configuration")
            if cat_k in category_summary:
                category_summary[cat_k]["found"] += 1

        # 5b. HTTP verb tampering (TRACE / Insecure PUT)
        verb_findings = fuzzer.test_http_verbs()
        for vf in verb_findings:
            candidates.append(vf)
            cat_k = vf.get("category", "configuration")
            if cat_k in category_summary:
                category_summary[cat_k]["found"] += 1

        # 5c. Parameter injection fuzzing on spidered endpoints
        fuzz_findings = fuzzer.fuzz_parameters(
            parameters=spider_results.get("parameters", {}),
            forms=spider_results.get("forms", []),
        )
        for ff in fuzz_findings:
            candidates.append(ff)
            cat_k = ff.get("category", "sqli")
            if cat_k in category_summary:
                category_summary[cat_k]["found"] += 1

        # 6. Native TCP Port Discovery (Mode-aware socket scan)
        open_ports = scan_target_ports(
            target_host_or_url=target_url,
            scan_mode=scan_mode,
            timeout=1.0,
            max_workers=20,
        )
        environmental_observations = []
        for p_info in open_ports:
            # Network scope enforcement:
            # Only in-scope application ports can become attack candidates.
            # Other host/docker infrastructure ports on localhost (e.g. port 8000 Strix console, port 9090 Prometheus)
            # are classified as out-of-scope environmental observations and never attributed to the target application.
            if not p_info.get("in_scope", True):
                environmental_observations.append(
                    {
                        "port": p_info["port"],
                        "service": p_info["service"],
                        "severity": p_info["severity"],
                        "risk": p_info["risk"],
                        "scope": "environmental",
                    }
                )
                continue

            # If non-standard port is exposed (e.g. 1720 H.323 or database port)
            if p_info["severity"] in ("medium", "high", "critical"):
                candidates.append(
                    {
                        "id": f"open-port-{p_info['port']}",
                        "name": f"Open TCP Port: {p_info['port']} ({p_info['service']})",
                        "category": "configuration",
                        "severity": p_info["severity"],
                        "cvss": 5.3 if p_info["severity"] == "medium" else 7.5,
                        "exposure": 0.9,
                        "cwe_id": "CWE-200",
                        "endpoint": f"tcp://{p_info['ip']}:{p_info['port']}",
                        "detail": f"Port {p_info['port']} is open running {p_info['service']}. {p_info['risk']}",
                        "is_recon_only": True,
                        "finding_class": "reconnaissance",
                    }
                )

        # 7. Build Category Scan Matrix
        scan_matrix = []
        for cat_key, cat_meta in SCAN_CATEGORIES.items():
            found_count = category_summary.get(cat_key, {}).get("found", 0)
            scan_matrix.append(
                {
                    "category_key": cat_key,
                    "title": cat_meta["title"],
                    "description": cat_meta["description"],
                    "test_count": cat_meta["test_count"],
                    "capability": cat_meta["capability"],
                    "findings_count": found_count,
                    "status": "VULNERABILITIES_IDENTIFIED" if found_count > 0 else "PASSED",
                }
            )

        return {
            "candidates": candidates,
            "open_ports": open_ports,
            "environmental_observations": environmental_observations,
            "components": components,
            "scan_matrix": scan_matrix,
            "category_summary": category_summary,
            "spider_stats": {
                "visited_count": spider_results.get("visited_count", 1),
                "discovered_paths": spider_results.get("discovered_paths", [base_endpoint]),
                "forms_count": len(spider_results.get("forms", [])),
                "parameters_count": sum(
                    len(p) for p in spider_results.get("parameters", {}).values()
                ),
            },
        }
