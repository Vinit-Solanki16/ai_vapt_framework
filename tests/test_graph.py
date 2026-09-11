"""Tests for asset/vulnerability graph integration."""
from __future__ import annotations

import pytest

from vapt_platform.graph_builder import VAPTGraph, GraphNode, GraphEdge
from vapt_platform.normalization import CanonicalFinding
from vapt_platform.application import VAPTApplication, VAPTRequest


# ---------------------------------------------------------------------------
# Graph builder tests
# ---------------------------------------------------------------------------

class TestVAPTGraph:
    def test_create_empty_graph(self):
        graph = VAPTGraph()
        assert graph.node_count == 0
        assert graph.edge_count == 0

    def test_add_node(self):
        graph = VAPTGraph()
        node = GraphNode(id="host:10.0.0.1", node_type="host", label="10.0.0.1")
        graph.add_node(node)
        assert graph.node_count == 1
        assert graph.has_node("host:10.0.0.1")

    def test_add_edge(self):
        graph = VAPTGraph()
        graph.add_node(GraphNode(id="host:10.0.0.1", node_type="host", label="10.0.0.1"))
        graph.add_node(GraphNode(id="cve:CVE-2021-44228", node_type="cve", label="CVE-2021-44228"))
        edge = GraphEdge(source="host:10.0.0.1", target="cve:CVE-2021-44228", edge_type="has_vulnerability")
        graph.add_edge(edge)
        assert graph.edge_count == 1
        assert graph.has_edge("host:10.0.0.1", "cve:CVE-2021-44228")

    def test_from_findings(self):
        findings = [
            CanonicalFinding(
                finding_id="test-1",
                host="10.0.0.1",
                port=80,
                title="HTTP Service",
                metadata={"cve_ids": ["CVE-2021-44228"]},
            ),
        ]
        graph = VAPTGraph.from_findings(findings)
        assert graph.node_count >= 2  # host + service + cve
        assert graph.has_node("host:10.0.0.1")

    def test_get_hosts(self):
        findings = [
            CanonicalFinding(host="10.0.0.1", metadata={"cve_ids": ["CVE-2021-44228"]}),
        ]
        graph = VAPTGraph.from_findings(findings)
        hosts = graph.get_hosts()
        assert len(hosts) >= 1

    def test_get_critical_vulns(self):
        findings = [
            CanonicalFinding(
                host="10.0.0.1",
                metadata={"cve_ids": ["CVE-2021-44228"], "severity": "critical"},
            ),
        ]
        graph = VAPTGraph.from_findings(findings)
        vulns = graph.get_critical_vulns("10.0.0.1")
        assert len(vulns) >= 1

    def test_summary(self):
        findings = [
            CanonicalFinding(host="10.0.0.1", metadata={"cve_ids": ["CVE-2021-44228"]}),
        ]
        graph = VAPTGraph.from_findings(findings)
        summary = graph.summary()
        assert "total_nodes" in summary
        assert "total_edges" in summary
        assert "nodes_by_type" in summary


# ---------------------------------------------------------------------------
# Application graph integration tests
# ---------------------------------------------------------------------------

class TestApplicationGraph:
    def test_build_graph_from_candidates(self):
        app = VAPTApplication()
        candidates = [
            {"id": "CVE-2021-44228", "host": "10.0.0.1", "port": 80, "probability": 0.95},
        ]
        graph = app._build_graph(candidates)
        assert isinstance(graph, VAPTGraph)
        assert graph.node_count >= 1

    def test_graph_in_result(self):
        app = VAPTApplication()
        req = VAPTRequest(
            scenario="success",
            mode="simulation",
            max_attempts=2,
            assessor_mode="deterministic",
        )
        result = app.run(req)
        # Graph summary is available in presentation result
        assert hasattr(result, 'graph_summary')

    def test_graph_with_cve_candidates(self):
        app = VAPTApplication()
        candidates = [
            {"id": "CVE-2021-44228", "host": "10.0.0.1", "port": 80, "probability": 0.95, "metadata": {"cve_ids": ["CVE-2021-44228"]}},
        ]
        graph = app._build_graph(candidates)
        assert graph.has_node("cve:CVE-2021-44228")

    def test_empty_candidates_graph(self):
        app = VAPTApplication()
        candidates = []
        graph = app._build_graph(candidates)
        assert isinstance(graph, VAPTGraph)
        assert graph.node_count == 0
