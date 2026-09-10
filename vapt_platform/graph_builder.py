"""Asset/Vulnerability Graph Builder (M5).

This module builds a graph representation of assets (hosts, services,
applications) and their vulnerabilities (CVEs, misconfigurations) from
enriched CanonicalFinding objects.

The graph supports:
- Node types: host, service, application, vulnerability, cve
- Edge types: has_vulnerability, depends_on, communicates_with
- Query methods: get_critical_vulns(host), get_attack_paths(source, target)
- Visualization: DOT export, optional graphviz rendering

Architecture:
    Enriched CanonicalFinding ──> VAPTGraph.from_findings() ──> VAPTGraph
                                                                      │
                                                                      ▼
                                                              DOT / Graphviz
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Optional

from vapt_platform.normalization import CanonicalFinding, severity_rank


# ---------------------------------------------------------------------------
# Graph primitives
# ---------------------------------------------------------------------------

NODE_TYPES = frozenset({"host", "service", "application", "vulnerability", "cve"})
EDGE_TYPES = frozenset({"has_vulnerability", "depends_on", "communicates_with", "has_service"})


@dataclass
class GraphNode:
    """A single node in the asset/vulnerability graph.

    Attributes:
        id: Stable unique identifier for the node.
        node_type: One of NODE_TYPES.
        label: Human-readable label.
        properties: Arbitrary metadata (severity, port, etc.).
    """

    id: str
    node_type: str
    label: str
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.node_type not in NODE_TYPES:
            raise ValueError(
                f"Invalid node_type '{self.node_type}'. Must be one of: {sorted(NODE_TYPES)}"
            )


@dataclass
class GraphEdge:
    """A directed edge between two graph nodes.

    Attributes:
        source: Source node id.
        target: Target node id.
        edge_type: One of EDGE_TYPES.
        label: Optional human-readable label.
        properties: Arbitrary metadata.
    """

    source: str
    target: str
    edge_type: str
    label: str = ""
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.edge_type not in EDGE_TYPES:
            raise ValueError(
                f"Invalid edge_type '{self.edge_type}'. Must be one of: {sorted(EDGE_TYPES)}"
            )


# ---------------------------------------------------------------------------
# VAPT Graph
# ---------------------------------------------------------------------------

class VAPTGraph:
    """Asset/Vulnerability graph for VAPT assessment data.

    Built from enriched CanonicalFinding objects. Supports querying
    for critical vulnerabilities, attack path analysis, and visualization.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        # Adjacency: source_id -> list of (target_id, edge)
        self._adjacency: dict[str, list[tuple[str, GraphEdge]]] = defaultdict(list)
        # Reverse adjacency: target_id -> list of (source_id, edge)
        self._reverse_adjacency: dict[str, list[tuple[str, GraphEdge]]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_node(self, node: GraphNode) -> GraphNode:
        """Add a node to the graph. Replaces existing node with same id."""
        self.nodes[node.id] = node
        return node

    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        """Add a directed edge. Creates adjacency entries."""
        # Ensure both endpoints exist
        if edge.source not in self.nodes:
            raise KeyError(f"Source node '{edge.source}' not in graph")
        if edge.target not in self.nodes:
            raise KeyError(f"Target node '{edge.target}' not in graph")

        self.edges.append(edge)
        self._adjacency[edge.source].append((edge.target, edge))
        self._reverse_adjacency[edge.target].append((edge.source, edge))
        return edge

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Retrieve a node by id."""
        return self.nodes.get(node_id)

    def has_node(self, node_id: str) -> bool:
        """Check if a node exists."""
        return node_id in self.nodes

    def has_edge(self, source: str, target: str, edge_type: Optional[str] = None) -> bool:
        """Check if an edge exists between source and target."""
        for tid, edge in self._adjacency.get(source, []):
            if tid == target:
                if edge_type is None or edge.edge_type == edge_type:
                    return True
        return False

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_neighbors(
        self,
        node_id: str,
        direction: str = "out",
        edge_type: Optional[str] = None,
    ) -> list[GraphNode]:
        """Get neighboring nodes.

        Args:
            node_id: The node to get neighbors for.
            direction: 'out' for outgoing edges, 'in' for incoming.
            edge_type: Optional filter by edge type.

        Returns:
            List of neighboring GraphNode objects.
        """
        if direction == "out":
            pairs = self._adjacency.get(node_id, [])
        elif direction == "in":
            pairs = self._reverse_adjacency.get(node_id, [])
        else:
            raise ValueError(f"Invalid direction '{direction}'. Use 'in' or 'out'.")

        result = []
        for neighbor_id, edge in pairs:
            if edge_type is None or edge.edge_type == edge_type:
                node = self.nodes.get(neighbor_id)
                if node is not None:
                    result.append(node)
        return result

    def get_nodes_by_type(self, node_type: str) -> list[GraphNode]:
        """Get all nodes of a given type."""
        return [n for n in self.nodes.values() if n.node_type == node_type]

    def get_hosts(self) -> list[GraphNode]:
        """Get all host nodes."""
        return self.get_nodes_by_type("host")

    def get_vulnerabilities(self) -> list[GraphNode]:
        """Get all vulnerability and CVE nodes."""
        return [n for n in self.nodes.values() if n.node_type in ("vulnerability", "cve")]

    def get_services(self) -> list[GraphNode]:
        """Get all service nodes."""
        return self.get_nodes_by_type("service")

    def get_critical_vulns(self, host: str, min_severity: str = "high") -> list[GraphNode]:
        """Get vulnerabilities at or above a severity threshold for a host.

        Traverses the graph from the host node through has_vulnerability
        edges to find connected vulnerability nodes.

        Args:
            host: Host node id or hostname to search from.
            min_severity: Minimum severity level (default: 'high').

        Returns:
            List of vulnerability GraphNode objects meeting the threshold.
        """
        min_rank = severity_rank(min_severity)
        host_ids: list[str] = []

        # Resolve host: could be a node id or a hostname
        if host in self.nodes:
            host_ids.append(host)
        else:
            # Search by hostname property
            for node in self.get_hosts():
                if node.properties.get("hostname") == host or node.label == host:
                    host_ids.append(node.id)

        if not host_ids:
            return []

        # BFS to find all reachable vulnerability nodes
        visited: set[str] = set()
        vuln_ids: list[str] = []
        queue: deque[str] = deque(host_ids)

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            node = self.nodes.get(current)
            if node is None:
                continue

            # If this is a vulnerability node, check severity
            if node.node_type in ("vulnerability", "cve"):
                vuln_severity = node.properties.get("severity", "unknown")
                if severity_rank(vuln_severity) >= min_rank:
                    vuln_ids.append(current)

            # Continue traversal through relevant edges
            for neighbor_id, edge in self._adjacency.get(current, []):
                if edge.edge_type in ("has_vulnerability", "has_service", "depends_on"):
                    if neighbor_id not in visited:
                        queue.append(neighbor_id)

        # Also check reverse direction (vulnerabilities pointing to hosts)
        for host_id in host_ids:
            for source_id, edge in self._reverse_adjacency.get(host_id, []):
                if edge.edge_type == "has_vulnerability" and source_id not in visited:
                    node = self.nodes.get(source_id)
                    if node and node.node_type in ("vulnerability", "cve"):
                        vuln_severity = node.properties.get("severity", "unknown")
                        if severity_rank(vuln_severity) >= min_rank:
                            vuln_ids.append(source_id)

        # Deduplicate and return
        seen: set[str] = set()
        result: list[GraphNode] = []
        for vid in vuln_ids:
            if vid not in seen:
                seen.add(vid)
                node = self.nodes.get(vid)
                if node:
                    result.append(node)
        return result

    def get_attack_paths(
        self,
        source: str,
        target: str,
        max_depth: int = 10,
    ) -> list[list[str]]:
        """Find all attack paths from source to target node.

        Uses BFS to find all simple paths up to max_depth hops.

        Args:
            source: Source node id.
            target: Target node id.
            max_depth: Maximum path length (default: 10).

        Returns:
            List of paths, where each path is a list of node ids.
        """
        if source not in self.nodes or target not in self.nodes:
            return []

        paths: list[list[str]] = []
        # BFS with path tracking
        queue: deque[tuple[str, list[str]]] = deque([(source, [source])])

        while queue:
            current, path = queue.popleft()

            if len(path) > max_depth:
                continue

            for neighbor_id, edge in self._adjacency.get(current, []):
                if neighbor_id == target:
                    paths.append(path + [neighbor_id])
                elif neighbor_id not in path:  # Avoid cycles
                    queue.append((neighbor_id, path + [neighbor_id]))

        return paths

    def get_attack_paths_by_hostname(
        self,
        source_host: str,
        target_host: str,
        max_depth: int = 10,
    ) -> list[list[str]]:
        """Find attack paths between two hosts by hostname.

        Resolves hostnames to node ids and delegates to get_attack_paths.
        """
        source_id = self._resolve_host_id(source_host)
        target_id = self._resolve_host_id(target_host)

        if source_id is None or target_id is None:
            return []

        return self.get_attack_paths(source_id, target_id, max_depth)

    def _resolve_host_id(self, hostname: str) -> Optional[str]:
        """Resolve a hostname to a host node id."""
        for node in self.get_hosts():
            if (
                node.id == hostname
                or node.properties.get("hostname") == hostname
                or node.label == hostname
            ):
                return node.id
        return None

    # ------------------------------------------------------------------
    # Visualization
    # ------------------------------------------------------------------

    def to_dot(self, title: str = "VAPT Asset/Vulnerability Graph") -> str:
        """Export the graph to DOT format.

        Args:
            title: Graph title.

        Returns:
            DOT format string.
        """
        lines: list[str] = []
        lines.append("digraph {")
        lines.append(f'    label="{title}";')
        lines.append("    labelloc=t;")
        lines.append("    rankdir=LR;")
        lines.append('    node [shape=box, style=filled];')
        lines.append("")

        # Node type styling
        type_styles: dict[str, dict[str, str]] = {
            "host": {"shape": "ellipse", "fillcolor": "#4A90D9", "fontcolor": "white"},
            "service": {"shape": "box", "fillcolor": "#7B68EE", "fontcolor": "white"},
            "application": {"shape": "component", "fillcolor": "#5DADE2", "fontcolor": "white"},
            "vulnerability": {"shape": "diamond", "fillcolor": "#E74C3C", "fontcolor": "white"},
            "cve": {"shape": "diamond", "fillcolor": "#C0392B", "fontcolor": "white"},
        }

        # Write nodes
        for node_id, node in sorted(self.nodes.items()):
            style = type_styles.get(node.node_type, {})
            style_parts = ", ".join(f'{k}="{v}"' for k, v in style.items())
            label = node.label.replace('"', '\\"')
            lines.append(f'    "{node_id}" [label="{label}", {style_parts}];')

        lines.append("")

        # Edge type styling
        edge_styles: dict[str, dict[str, str]] = {
            "has_vulnerability": {"color": "#E74C3C", "style": "solid"},
            "depends_on": {"color": "#F39C12", "style": "dashed"},
            "communicates_with": {"color": "#27AE60", "style": "dotted"},
            "has_service": {"color": "#7B68EE", "style": "solid"},
        }

        # Write edges
        for edge in self.edges:
            style = edge_styles.get(edge.edge_type, {})
            style_parts = ", ".join(f'{k}="{v}"' for k, v in style.items())
            label = edge.label.replace('"', '\\"')
            if label:
                style_parts += f', label="{label}"'
            lines.append(f'    "{edge.source}" -> "{edge.target}" [{style_parts}];')

        lines.append("}")
        return "\n".join(lines)

    def render(
        self,
        output_path: str,
        format: str = "png",
        title: str = "VAPT Asset/Vulnerability Graph",
    ) -> Optional[str]:
        """Render the graph to a file using graphviz.

        Args:
            output_path: Output file path (without extension).
            format: Output format (png, svg, pdf, etc.).
            title: Graph title.

        Returns:
            The output file path if successful, None if graphviz is unavailable.
        """
        try:
            import graphviz  # noqa: PLC0415
        except ImportError:
            return None

        dot_source = self.to_dot(title=title)
        graph = graphviz.Source(dot_source)
        graph.format = format
        return graph.render(output_path, cleanup=True)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def summary(self) -> dict[str, Any]:
        """Return a summary of node and edge counts by type."""
        node_counts: dict[str, int] = defaultdict(int)
        edge_counts: dict[str, int] = defaultdict(int)

        for node in self.nodes.values():
            node_counts[node.node_type] += 1
        for edge in self.edges:
            edge_counts[edge.edge_type] += 1

        return {
            "total_nodes": self.node_count,
            "total_edges": self.edge_count,
            "nodes_by_type": dict(node_counts),
            "edges_by_type": dict(edge_counts),
        }

    # ------------------------------------------------------------------
    # Build from findings
    # ------------------------------------------------------------------

    @classmethod
    def from_findings(cls, findings: list[CanonicalFinding]) -> "VAPTGraph":
        """Build a VAPTGraph from a list of enriched CanonicalFinding objects.

        Creates:
        - Host nodes for each unique host
        - Service nodes for each unique (host, port, service) combination
        - Vulnerability/CVE nodes for each finding
        - Edges connecting hosts to services and services to vulnerabilities

        Args:
            findings: List of enriched CanonicalFinding objects.

        Returns:
            A populated VAPTGraph.
        """
        graph = cls()

        for finding in findings:
            # Create host node
            host_id = _make_host_id(finding.host)
            if not graph.has_node(host_id):
                graph.add_node(
                    GraphNode(
                        id=host_id,
                        node_type="host",
                        label=finding.host,
                        properties={"hostname": finding.host},
                    )
                )

            # Create service node if port is specified
            service_id: Optional[str] = None
            if finding.port and finding.port > 0:
                service_id = _make_service_id(finding.host, finding.port, finding.title)
                if not graph.has_node(service_id):
                    graph.add_node(
                        GraphNode(
                            id=service_id,
                            node_type="service",
                            label=f"{finding.title}:{finding.port}",
                            properties={
                                "host": finding.host,
                                "port": finding.port,
                                "protocol": finding.protocol,
                                "service_name": finding.title,
                            },
                        )
                    )
                # Edge: host -> has_service -> service
                if not graph.has_edge(host_id, service_id, "has_service"):
                    graph.add_edge(
                        GraphEdge(
                            source=host_id,
                            target=service_id,
                            edge_type="has_service",
                            label="has_service",
                        )
                    )

            # Determine if this is a CVE or generic vulnerability
            cve_ids = _extract_cve_ids_from_finding(finding)
            severity = finding.metadata.get("severity", finding.severity)

            if cve_ids:
                for cve in cve_ids:
                    vuln_id = _make_cve_id(cve)
                    if not graph.has_node(vuln_id):
                        graph.add_node(
                            GraphNode(
                                id=vuln_id,
                                node_type="cve",
                                label=cve,
                                properties={
                                    "cve_id": cve,
                                    "severity": severity,
                                    "cvss_score": finding.metadata.get("cvss_score"),
                                    "epss_score": finding.metadata.get("epss_score"),
                                    "cisa_kev": finding.metadata.get("cisa_kev", False),
                                },
                            )
                        )
                    # Edge: service/host -> has_vulnerability -> cve
                    source_id = service_id if service_id else host_id
                    if not graph.has_edge(source_id, vuln_id, "has_vulnerability"):
                        graph.add_edge(
                            GraphEdge(
                                source=source_id,
                                target=vuln_id,
                                edge_type="has_vulnerability",
                                label="has_vulnerability",
                            )
                        )
            else:
                # Generic vulnerability node
                vuln_id = _make_vuln_id(finding)
                if not graph.has_node(vuln_id):
                    graph.add_node(
                        GraphNode(
                            id=vuln_id,
                            node_type="vulnerability",
                            label=finding.title or finding.rule_id,
                            properties={
                                "severity": severity,
                                "rule_id": finding.rule_id,
                                "description": finding.description,
                                "source": finding.source,
                                "cvss_score": finding.metadata.get("cvss_score"),
                                "epss_score": finding.metadata.get("epss_score"),
                            },
                        )
                    )
                # Edge: service/host -> has_vulnerability -> vulnerability
                source_id = service_id if service_id else host_id
                if not graph.has_edge(source_id, vuln_id, "has_vulnerability"):
                    graph.add_edge(
                        GraphEdge(
                            source=source_id,
                            target=vuln_id,
                            edge_type="has_vulnerability",
                            label="has_vulnerability",
                        )
                    )

        return graph


# ---------------------------------------------------------------------------
# ID generation helpers
# ---------------------------------------------------------------------------

def _make_host_id(host: str) -> str:
    """Generate a stable host node id."""
    return f"host:{host}"


def _make_service_id(host: str, port: int, service_name: str) -> str:
    """Generate a stable service node id."""
    return f"svc:{host}:{port}:{service_name}"


def _make_cve_id(cve: str) -> str:
    """Generate a stable CVE node id."""
    return f"cve:{cve.upper()}"


def _make_vuln_id(finding: CanonicalFinding) -> str:
    """Generate a stable vulnerability node id for non-CVE findings."""
    key = f"{finding.source}:{finding.host}:{finding.port}:{finding.rule_id}"
    h = hashlib.sha256(key.encode()).hexdigest()[:12]
    return f"vuln:{h}"


def _extract_cve_ids_from_finding(finding: CanonicalFinding) -> list[str]:
    """Extract CVE IDs from a finding's metadata and evidence."""
    cves: set[str] = set()
    cve_pattern = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)

    # From metadata.cve_ids
    cve_ids = finding.metadata.get("cve_ids")
    if cve_ids:
        if isinstance(cve_ids, list):
            for c in cve_ids:
                if isinstance(c, str):
                    cves.add(c.strip().upper())
        elif isinstance(cve_ids, str):
            cves.add(cve_ids.strip().upper())

    # From metadata.cve
    cve = finding.metadata.get("cve")
    if cve and isinstance(cve, str):
        cves.add(cve.strip().upper())

    # From rule_id
    if finding.rule_id and finding.rule_id.upper().startswith("CVE-"):
        cves.add(finding.rule_id.strip().upper())

    # From evidence
    for ev in finding.evidence:
        if isinstance(ev, str):
            matches = cve_pattern.findall(ev)
            for m in matches:
                cves.add(m.upper())

    return sorted(cves)