"""Tests for scanner adapter integration."""
from __future__ import annotations

import json
import os
import tempfile
import pytest

from vapt_platform.scanners import (
    ScannerRegistry,
    NmapXmlAdapter,
    NmapJsonAdapter,
    CustomJsonAdapter,
    NucleiAdapter,
    get_scanner_registry,
)
from vapt_platform.normalization import CanonicalFinding


# ---------------------------------------------------------------------------
# Nmap XML adapter tests
# ---------------------------------------------------------------------------

class TestNmapXmlAdapter:
    def test_can_parse_xml(self):
        adapter = NmapXmlAdapter()
        assert adapter.can_parse("scan.xml")
        assert not adapter.can_parse("scan.json")

    def test_parse_nmap_xml(self):
        adapter = NmapXmlAdapter()
        xml_content = """<?xml version="1.0"?>
        <nmaprun>
            <host>
                <address addr="192.168.1.10"/>
                <ports>
                    <port protocol="tcp" portid="80">
                        <state state="open"/>
                        <service name="http" product="Apache httpd" version="2.4.25"/>
                    </port>
                </ports>
            </host>
        </nmaprun>"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(xml_content)
            f.flush()
            findings = adapter.parse(f.name)
            os.unlink(f.name)
        assert len(findings) == 1
        assert findings[0].host == "192.168.1.10"
        assert findings[0].port == 80


# ---------------------------------------------------------------------------
# Nmap JSON adapter tests
# ---------------------------------------------------------------------------

class TestNmapJsonAdapter:
    def test_can_parse_nmap_json(self):
        adapter = NmapJsonAdapter()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"hosts": [{"addr": "10.0.0.1", "ports": []}]}, f)
            f.flush()
            assert adapter.can_parse(f.name)
            os.unlink(f.name)

    def test_parse_nmap_json(self):
        adapter = NmapJsonAdapter()
        data = {
            "hosts": [
                {
                    "addr": "10.0.0.1",
                    "ports": [
                        {"port": 22, "state": "open", "service": "ssh", "product": "OpenSSH"},
                    ],
                }
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            findings = adapter.parse(f.name)
            os.unlink(f.name)
        assert len(findings) == 1
        assert findings[0].host == "10.0.0.1"
        assert findings[0].port == 22


# ---------------------------------------------------------------------------
# Custom JSON adapter tests
# ---------------------------------------------------------------------------

class TestCustomJsonAdapter:
    def test_can_parse_custom_json(self):
        adapter = CustomJsonAdapter()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"findings": [], "target": "10.0.0.1"}, f)
            f.flush()
            assert adapter.can_parse(f.name)
            os.unlink(f.name)

    def test_parse_custom_json(self):
        adapter = CustomJsonAdapter()
        data = {
            "target": "10.0.0.1",
            "findings": [
                {"id": "test-1", "port": 80, "service": "http", "cve": "CVE-2021-44228"},
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            findings = adapter.parse(f.name)
            os.unlink(f.name)
        assert len(findings) == 1
        assert findings[0].port == 80


# ---------------------------------------------------------------------------
# Nuclei adapter tests
# ---------------------------------------------------------------------------

class TestNucleiAdapter:
    def test_can_parse_nuclei(self):
        adapter = NucleiAdapter()
        assert adapter.can_parse("nuclei.json")
        assert adapter.can_parse("nuclei.jsonl")

    def test_parse_nuclei_json(self):
        adapter = NucleiAdapter()
        data = [
            {
                "template-id": "CVE-2021-44228",
                "type": "http",
                "host": "https://example.com",
                "info": {"name": "Log4j2 RCE", "severity": "critical"},
            }
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            findings = adapter.parse(f.name)
            os.unlink(f.name)
        assert len(findings) == 1
        assert findings[0].source == "nuclei"


# ---------------------------------------------------------------------------
# Scanner registry tests
# ---------------------------------------------------------------------------

class TestScannerRegistry:
    def test_create_registry(self):
        registry = ScannerRegistry()
        assert registry is not None

    def test_get_adapter_xml(self):
        registry = get_scanner_registry()
        adapter = registry.get_adapter("scan.xml")
        assert adapter is not None
        assert isinstance(adapter, NmapXmlAdapter)

    def test_get_adapter_json(self):
        registry = get_scanner_registry()
        # Create a temp JSON file to test detection
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"findings": []}, f)
            f.flush()
            adapter = registry.get_adapter(f.name)
            os.unlink(f.name)
        assert adapter is not None

    def test_singleton(self):
        r1 = get_scanner_registry()
        r2 = get_scanner_registry()
        assert r1 is r2


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestScannerIntegration:
    def test_parse_and_enrich(self):
        """Test parsing a scan file and enriching findings."""
        from vapt_platform.enrichment import enrich_findings

        adapter = CustomJsonAdapter()
        data = {
            "target": "10.0.0.1",
            "findings": [
                {"id": "test-1", "port": 80, "service": "http", "cve": "CVE-2021-44228"},
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            findings = adapter.parse(f.name)
            os.unlink(f.name)

        enriched = enrich_findings(findings)
        assert len(enriched) == 1
        assert enriched[0].metadata.get("epss_score", 0) > 0

    def test_parse_and_build_graph(self):
        """Test parsing a scan file and building graph."""
        from vapt_platform.graph_builder import VAPTGraph

        adapter = CustomJsonAdapter()
        data = {
            "target": "10.0.0.1",
            "findings": [
                {"id": "test-1", "port": 80, "service": "http", "cve": "CVE-2021-44228"},
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            findings = adapter.parse(f.name)
            os.unlink(f.name)

        graph = VAPTGraph.from_findings(findings)
        assert graph.node_count >= 2
