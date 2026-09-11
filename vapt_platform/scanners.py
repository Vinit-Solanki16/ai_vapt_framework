"""Scanner adapter abstraction for recon/scanning integration.

Provides a unified interface for multiple scanner output formats:
- Nmap XML
- Nmap JSON
- Custom JSON
- Nuclei JSON/JSONL

All adapters are offline-safe (no live API calls).
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from typing import Any, Optional

from vapt_platform.normalization import CanonicalFinding


# ---------------------------------------------------------------------------
# Scanner adapter base
# ---------------------------------------------------------------------------

class ScannerAdapter(ABC):
    """Base class for scanner output adapters."""

    @abstractmethod
    def parse(self, file_path: str) -> list[CanonicalFinding]:
        """Parse scanner output file into canonical findings."""
        ...

    @abstractmethod
    def can_parse(self, file_path: str) -> bool:
        """Check if this adapter can parse the given file."""
        ...


# ---------------------------------------------------------------------------
# Nmap XML adapter
# ---------------------------------------------------------------------------

class NmapXmlAdapter(ScannerAdapter):
    """Parser for Nmap XML output."""

    def can_parse(self, file_path: str) -> bool:
        return file_path.endswith(".xml")

    def parse(self, file_path: str) -> list[CanonicalFinding]:
        findings = []
        tree = ET.parse(file_path)
        root = tree.getroot()
        for host in root.findall("host"):
            addr_el = host.find("address")
            host_ip = addr_el.get("addr") if addr_el is not None else "unknown"
            for port in host.findall(".//port"):
                if port.find("state") is None or port.find("state").get("state") != "open":
                    continue
                portid = int(port.get("portid", 0))
                svc = port.find("service")
                service = svc.get("name") if svc is not None else ""
                product = (svc.get("product") or "") if svc is not None else ""
                version = (svc.get("version") or "") if svc is not None else ""
                cpes = [c.text for c in port.findall(".//cpe") if c.text]
                desc = " ".join(filter(None, [product, version])).strip() or service or "open port"
                findings.append(CanonicalFinding(
                    finding_id=f"nmap-{host_ip}-{portid}",
                    source="nmap-xml",
                    host=host_ip,
                    target=host_ip,
                    port=portid,
                    protocol="tcp",
                    title=service or "open port",
                    severity="unknown",
                    rule_id=f"port-{portid}",
                    description=desc,
                    evidence=cpes,
                    tags=["nmap", "port-scan"],
                    metadata={
                        "service": service,
                        "product": product,
                        "version": version,
                        "cpe": cpes,
                    },
                ))
        return findings


# ---------------------------------------------------------------------------
# Nmap JSON adapter
# ---------------------------------------------------------------------------

class NmapJsonAdapter(ScannerAdapter):
    """Parser for Nmap JSON output."""

    def can_parse(self, file_path: str) -> bool:
        if not file_path.endswith(".json"):
            return False
        try:
            with open(file_path) as f:
                data = json.load(f)
            # Nmap JSON has "hosts" key
            return isinstance(data, dict) and "hosts" in data
        except Exception:
            return False

    def parse(self, file_path: str) -> list[CanonicalFinding]:
        findings = []
        with open(file_path) as f:
            data = json.load(f)
        for host in data.get("hosts", []):
            host_ip = host.get("addr") or host.get("ip") or "unknown"
            for port in host.get("ports", []):
                if port.get("state") != "open":
                    continue
                portid = port.get("port", 0)
                findings.append(CanonicalFinding(
                    finding_id=f"nmap-{host_ip}-{portid}",
                    source="nmap-json",
                    host=host_ip,
                    target=host_ip,
                    port=portid,
                    protocol="tcp",
                    title=port.get("service", "open port"),
                    severity="unknown",
                    rule_id=f"port-{portid}",
                    description=port.get("product", ""),
                    evidence=[],
                    tags=["nmap", "port-scan"],
                    metadata={
                        "service": port.get("service"),
                        "product": port.get("product"),
                        "cve": port.get("cve"),
                    },
                ))
        return findings


# ---------------------------------------------------------------------------
# Custom JSON adapter
# ---------------------------------------------------------------------------

class CustomJsonAdapter(ScannerAdapter):
    """Parser for custom JSON schema."""

    def can_parse(self, file_path: str) -> bool:
        if not file_path.endswith(".json"):
            return False
        try:
            with open(file_path) as f:
                data = json.load(f)
            # Custom JSON has "findings" key
            return isinstance(data, dict) and "findings" in data
        except Exception:
            return False

    def parse(self, file_path: str) -> list[CanonicalFinding]:
        findings = []
        with open(file_path) as f:
            data = json.load(f)
        for item in data.get("findings", []):
            host = item.get("host", data.get("target", "unknown"))
            port = item.get("port", 0)
            findings.append(CanonicalFinding(
                finding_id=item.get("id", f"custom-{host}-{port}"),
                source="custom",
                host=host,
                target=host,
                port=port,
                protocol=item.get("protocol", "tcp"),
                title=item.get("service", item.get("title", "finding")),
                severity=item.get("severity", "unknown"),
                rule_id=item.get("rule_id", item.get("id", "")),
                description=item.get("description", ""),
                evidence=item.get("evidence", []),
                tags=item.get("tags", ["custom"]),
                metadata={
                    "service": item.get("service"),
                    "cve": item.get("cve"),
                },
            ))
        return findings


# ---------------------------------------------------------------------------
# Nuclei adapter (delegates to existing parser)
# ---------------------------------------------------------------------------

class NucleiAdapter(ScannerAdapter):
    """Parser for Nuclei JSON/JSONL output."""

    def can_parse(self, file_path: str) -> bool:
        return file_path.endswith(".json") or file_path.endswith(".jsonl")

    def parse(self, file_path: str) -> list[CanonicalFinding]:
        from vapt_platform.parsers.nuclei_parser import parse_nuclei_json
        from vapt_platform.normalization import from_nuclei_finding

        nuclei_findings = parse_nuclei_json(open(file_path).read())
        return [from_nuclei_finding(nf) for nf in nuclei_findings]


# ---------------------------------------------------------------------------
# Scanner registry
# ---------------------------------------------------------------------------

class ScannerRegistry:
    """Registry of scanner adapters."""

    def __init__(self) -> None:
        self._adapters: list[ScannerAdapter] = [
            NmapXmlAdapter(),
            NmapJsonAdapter(),
            CustomJsonAdapter(),
            NucleiAdapter(),
        ]

    def register(self, adapter: ScannerAdapter) -> None:
        """Register a new scanner adapter."""
        self._adapters.append(adapter)

    def get_adapter(self, file_path: str) -> Optional[ScannerAdapter]:
        """Get the appropriate adapter for a file."""
        for adapter in self._adapters:
            if adapter.can_parse(file_path):
                return adapter
        return None

    def parse(self, file_path: str) -> list[CanonicalFinding]:
        """Parse a scan file using the appropriate adapter."""
        adapter = self.get_adapter(file_path)
        if adapter is None:
            raise ValueError(f"No adapter found for file: {file_path}")
        return adapter.parse(file_path)


# Singleton registry
_registry = ScannerRegistry()


def get_scanner_registry() -> ScannerRegistry:
    """Get the singleton scanner registry."""
    return _registry
