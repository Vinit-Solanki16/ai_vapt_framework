# Role: Cyber-AI Engineer
Refactor `core/scanner.py` to ingest both raw Nmap XML files (`nmap -sV -oX`) and custom JSON scan logs, enriching each finding with live EPSS exploit probabilities (Paul et al., 2024).

## Technical Requirements
1. `parse_nmap_xml(xml_file: str) -> list[dict]` using `xml.etree.ElementTree`: extract host IP, open ports, service names/banners, and CPEs.
2. `fetch_epss_score(cve_id: str) -> float` hitting `https://api.first.org/data/v1/epss?cve={cve_id}` with timeout + offline-safe failure (return 0.0).
3. Return findings sorted in DESCENDING order of EPSS probability.
4. Error handling for network timeouts and missing CVE identifiers.
5. Unified `process_scan(file_path)` that auto-detects XML vs JSON and dispatches.

## Done criteria
- `python -m core.scanner data/live_scan.xml` and `data/sample_scan.json` both run.
- Output is a list of `Finding` objects ranked by EPSS.
- Verified: CVE-2021-44228 -> EPSS ~0.99999.
