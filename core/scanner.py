"""Scan ingestion + risk scoring (Phase 1, Task 1.1).

Ingests three formats so the framework is reproducible in any lab:
  1. Nmap XML  (``nmap -sV -oX scan.xml <target>``)
  2. Nmap JSON (``nmap -sV -oJ scan.json <target>``)
  3. The project's own custom JSON schema (data/sample_scan.json)

Every finding is enriched with a live EPSS exploitation-probability score
(Paul et al., 2024 — enriching static scans with real-time threat intel)
and returned sorted in descending order of real-world risk.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

import requests

from core.schemas import Finding, finding_from_dict


# ---------------------------------------------------------------------------
# EPSS enrichment
# ---------------------------------------------------------------------------
def fetch_epss_score(cve_id: str, timeout: int = 5) -> float:
    """Query the FIRST.org EPSS API for real-world exploitation probability.

    Returns a float in [0, 1]; defaults to 0.0 on any failure (offline-safe).
    """
    cve = cve_id.strip().upper()
    if not cve.startswith("CVE-"):
        return 0.0
    url = f"https://api.first.org/data/v1/epss?cve={cve}"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "OK" and data.get("data"):
                return float(data["data"][0]["epss"])
    except Exception as e:  # pragma: no cover - network dependent
        print(f"[-] EPSS lookup failed for {cve}: {e}")
    return 0.0


# ---------------------------------------------------------------------------
# Raw parsers
# ---------------------------------------------------------------------------
def parse_nmap_xml(xml_file: str) -> List[Dict]:
    """Extract host, open ports, service banners and CPEs from Nmap XML."""
    findings: List[Dict] = []
    tree = ET.parse(xml_file)
    root = tree.getroot()
    for host in root.findall("host"):
        addr_el = host.find("address")
        host_ip = addr_el.get("addr") if addr_el is not None else "unknown"
        for port in host.findall(".//port"):
            if port.find("state") is None or port.find("state").get("state") != "open":
                continue
            portid = int(port.get("portid", 0))
            svc = port.find("service")
            service = svc.get("name") if svc is not None else None
            product = (svc.get("product") or "") if svc is not None else ""
            version = (svc.get("version") or "") if svc is not None else ""
            cpes = [c.text for c in port.findall(".//cpe") if c.text]
            # Derive a best-guess description from banner
            desc = " ".join(filter(None, [product, version])).strip() or service or "open port"
            findings.append({
                "host": host_ip,
                "port": portid,
                "service": service,
                "description": desc,
                "cpe": cpes,
                "cve": None,  # Nmap XML rarely carries CVEs; set externally or via script
            })
    return findings


def parse_nmap_json(json_file: str) -> List[Dict]:
    """Parse Nmap JSON output (``-oJ``) into finding dicts."""
    findings: List[Dict] = []
    with open(json_file, "r") as f:
        data = json.load(f)
    for host in data.get("hosts", data if isinstance(data, list) else []):
        host_ip = host.get("addr") or host.get("ip") or "unknown"
        for port in host.get("ports", []):
            if port.get("state") != "open":
                continue
            findings.append({
                "host": host_ip,
                "port": port.get("port"),
                "service": port.get("service"),
                "description": port.get("product", ""),
                "cve": port.get("cve"),
            })
    return findings


def parse_custom_json(json_file: str) -> List[Dict]:
    """Parse the project's own schema (sample_scan.json)."""
    with open(json_file, "r") as f:
        data = json.load(f)
    out = []
    for item in data.get("findings", []):
        item = dict(item)
        item.setdefault("host", data.get("target", "unknown"))
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Enrichment + sorting
# ---------------------------------------------------------------------------
def enrich(findings: List[Dict], timeout: int = 5) -> List[Finding]:
    """Attach EPSS scores and build typed Finding objects."""
    enriched: List[Finding] = []
    for item in findings:
        cve = (item.get("cve") or "UNKNOWN").strip().upper()
        if cve and cve != "UNKNOWN":
            epss = fetch_epss_score(cve, timeout=timeout)
        else:
            epss = 0.0
        f = finding_from_dict(item)
        f.epss_score = epss
        enriched.append(f)
    # Highest real-world risk first
    enriched.sort(key=lambda x: x.epss_score, reverse=True)
    return enriched


def process_scan(file_path: str, timeout: int = 5) -> List[Finding]:
    """Unified entry point: detect format and return enriched findings."""
    if file_path.endswith(".xml"):
        print(f"[+] Parsing Nmap XML: {file_path}")
        raw = parse_nmap_xml(file_path)
    elif file_path.endswith(".json"):
        # sniff: does it look like Nmap JSON or custom?
        with open(file_path) as f:
            peek = json.load(f)
        if isinstance(peek, dict) and "findings" in peek:
            raw = parse_custom_json(file_path)
        else:
            raw = parse_nmap_json(file_path)
    else:
        raise ValueError("Unsupported scan file type (use .xml or .json)")

    findings = enrich(raw, timeout=timeout)
    print(f"[+] Identified {len(findings)} findings, ranked by EPSS:")
    for f in findings:
        print(f"    - {f.cve} | port {f.port} | EPSS {f.epss_score:.4f}")
    return findings


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/sample_scan.json"
    res = process_scan(path)
    print(f"\n[+] Complete. {len(res)} vulnerabilities ranked.")
