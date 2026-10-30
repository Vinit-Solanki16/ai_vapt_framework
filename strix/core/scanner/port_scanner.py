"""Fast, portable TCP port and network service scanner in pure Python.

No external nmap or binary dependencies required.
Executes non-destructive concurrent socket connection probes across standard
web, database, administrative, cloud, and telephony ports.
Supports 'quick', 'standard', and 'deep' modes.
"""
from __future__ import annotations

import concurrent.futures
import socket
import urllib.parse
from typing import Any, Dict, List, Optional


KNOWN_PORTS: Dict[int, Dict[str, str]] = {
    # File transfer & Shell
    21: {"service": "FTP", "severity": "medium", "risk": "Unencrypted File Transfer Protocol daemon exposed."},
    22: {"service": "SSH", "severity": "low", "risk": "Remote administrative Secure Shell service."},
    23: {"service": "Telnet", "severity": "high", "risk": "Cleartext unencrypted Telnet administrative daemon exposed."},
    25: {"service": "SMTP", "severity": "low", "risk": "Mail transfer agent service exposed."},
    53: {"service": "DNS", "severity": "low", "risk": "Domain Name System resolution service."},
    69: {"service": "TFTP", "severity": "high", "risk": "Trivial File Transfer Protocol daemon without authentication."},
    80: {"service": "HTTP", "severity": "low", "risk": "Standard cleartext HTTP web server port."},
    88: {"service": "Kerberos", "severity": "medium", "risk": "Kerberos domain authentication service exposed."},
    110: {"service": "POP3", "severity": "medium", "risk": "Legacy Post Office Protocol mail service."},
    111: {"service": "RPCBind", "severity": "medium", "risk": "RPC port mapper service exposed."},
    135: {"service": "MSRPC", "severity": "high", "risk": "Microsoft RPC endpoint mapper exposed."},
    137: {"service": "NetBIOS-NS", "severity": "medium", "risk": "NetBIOS Name Service exposed."},
    138: {"service": "NetBIOS-DGM", "severity": "medium", "risk": "NetBIOS Datagram Service exposed."},
    139: {"service": "NetBIOS-SSN", "severity": "medium", "risk": "NetBIOS session file sharing service exposed."},
    143: {"service": "IMAP", "severity": "medium", "risk": "Internet Message Access Protocol service."},
    389: {"service": "LDAP", "severity": "high", "risk": "Lightweight Directory Access Protocol service exposed."},
    443: {"service": "HTTPS", "severity": "low", "risk": "Secure TLS encrypted web server port."},
    445: {"service": "SMB", "severity": "high", "risk": "Server Message Block service exposed externally."},
    465: {"service": "SMTPS", "severity": "low", "risk": "Secure SMTP submission over SSL."},
    514: {"service": "Syslog", "severity": "medium", "risk": "Remote system logging daemon exposed."},
    587: {"service": "SMTP-Submission", "severity": "low", "risk": "SMTP email submission port."},
    636: {"service": "LDAPS", "severity": "medium", "risk": "Secure LDAP directory service."},
    873: {"service": "Rsync", "severity": "high", "risk": "Remote file sync daemon without encryption."},
    993: {"service": "IMAPS", "severity": "low", "risk": "Secure IMAP mail service."},
    995: {"service": "POP3S", "severity": "low", "risk": "Secure POP3 mail service."},
    1080: {"service": "SOCKS-Proxy", "severity": "high", "risk": "SOCKS proxy gateway exposed."},
    1194: {"service": "OpenVPN", "severity": "low", "risk": "OpenVPN virtual private network endpoint."},
    1433: {"service": "MSSQL", "severity": "high", "risk": "Microsoft SQL Server database listener exposed."},
    1521: {"service": "Oracle-TNS", "severity": "high", "risk": "Oracle Database listener service exposed."},
    1720: {"service": "H.323 Call Signalling", "severity": "medium", "risk": "H.323 VoIP gatekeeper/telephony signalling port exposed."},
    2049: {"service": "NFS", "severity": "high", "risk": "Network File System mount daemon exposed."},
    2082: {"service": "cPanel", "severity": "medium", "risk": "cPanel web hosting control panel port."},
    2083: {"service": "cPanel-SSL", "severity": "medium", "risk": "cPanel secure management interface."},
    2086: {"service": "WHM", "severity": "high", "risk": "Web Host Manager administrative console."},
    2087: {"service": "WHM-SSL", "severity": "high", "risk": "Web Host Manager secure administrative console."},
    2181: {"service": "ZooKeeper", "severity": "high", "risk": "Apache ZooKeeper coordination service exposed."},
    2375: {"service": "Docker-Daemon", "severity": "critical", "risk": "Unauthenticated Docker REST engine API exposed (direct RCE)."},
    2376: {"service": "Docker-TLS", "severity": "medium", "risk": "Docker TLS-protected daemon port."},
    3000: {"service": "Node/React/Grafana", "severity": "low", "risk": "Alternative web application or Grafana dashboard."},
    3128: {"service": "Squid-Proxy", "severity": "medium", "risk": "Squid forward/reverse proxy port exposed."},
    3306: {"service": "MySQL", "severity": "high", "risk": "MySQL database server exposed to external networks."},
    3389: {"service": "RDP", "severity": "medium", "risk": "Microsoft Remote Desktop Protocol administrative endpoint."},
    4000: {"service": "HTTP-Dev", "severity": "low", "risk": "Alternative development application port."},
    4200: {"service": "Angular-Dev", "severity": "low", "risk": "Angular web development server port."},
    5000: {"service": "Flask/Docker-Registry", "severity": "low", "risk": "Flask web service or internal container registry."},
    5001: {"service": "Synology-Admin", "severity": "medium", "risk": "Synology NAS administrative web interface."},
    5060: {"service": "SIP", "severity": "medium", "risk": "Session Initiation Protocol VoIP gateway."},
    5061: {"service": "SIPS", "severity": "medium", "risk": "Secure SIP VoIP gateway."},
    5432: {"service": "PostgreSQL", "severity": "high", "risk": "PostgreSQL relational database service exposed."},
    5601: {"service": "Kibana", "severity": "high", "risk": "Elasticsearch Kibana analytics dashboard exposed."},
    5672: {"service": "RabbitMQ", "severity": "high", "risk": "RabbitMQ message broker AMQP listener."},
    5900: {"service": "VNC", "severity": "high", "risk": "Virtual Network Computing remote desktop exposed."},
    5901: {"service": "VNC-Display-1", "severity": "high", "risk": "VNC remote display 1 exposed."},
    5984: {"service": "CouchDB", "severity": "high", "risk": "Apache CouchDB NoSQL database REST API."},
    5985: {"service": "WinRM-HTTP", "severity": "high", "risk": "Windows Remote Management cleartext listener."},
    5986: {"service": "WinRM-HTTPS", "severity": "medium", "risk": "Windows Remote Management TLS listener."},
    6000: {"service": "X11", "severity": "high", "risk": "X Window System display server exposed."},
    6379: {"service": "Redis", "severity": "critical", "risk": "In-memory Redis cache exposed without firewall isolation."},
    6443: {"service": "Kubernetes-API", "severity": "high", "risk": "Kubernetes cluster master control plane API."},
    7000: {"service": "Cassandra-Cluster", "severity": "high", "risk": "Apache Cassandra internal cluster communication."},
    7001: {"service": "WebLogic", "severity": "high", "risk": "Oracle WebLogic server administration console."},
    7077: {"service": "Apache-Spark", "severity": "high", "risk": "Apache Spark cluster master port."},
    8000: {"service": "HTTP-Dev", "severity": "low", "risk": "Alternative development HTTP web port."},
    8001: {"service": "K8s-Dashboard", "severity": "medium", "risk": "Kubernetes web dashboard proxy port."},
    8008: {"service": "HTTP-Alt", "severity": "low", "risk": "Alternative HTTP management interface."},
    8080: {"service": "HTTP-Proxy/Tomcat", "severity": "low", "risk": "Alternative HTTP proxy or Tomcat application server port."},
    8081: {"service": "Nexus/Blackberry", "severity": "low", "risk": "Sonatype Nexus artifact repository or alt web port."},
    8088: {"service": "YARN-ResourceManager", "severity": "high", "risk": "Hadoop YARN resource manager web UI."},
    8161: {"service": "ActiveMQ-Console", "severity": "high", "risk": "Apache ActiveMQ web administration console."},
    8443: {"service": "HTTPS-Alt", "severity": "low", "risk": "Alternative secure web application service port."},
    8500: {"service": "Consul", "severity": "high", "risk": "HashiCorp Consul service discovery HTTP API."},
    8529: {"service": "ArangoDB", "severity": "high", "risk": "ArangoDB multi-model database interface."},
    8880: {"service": "CD-Admin", "severity": "low", "risk": "Alternative HTTP management portal."},
    8888: {"service": "Jupyter/Tornado", "severity": "medium", "risk": "Jupyter notebook server or Tornado web app."},
    9000: {"service": "SonarQube/PHP-FPM", "severity": "medium", "risk": "SonarQube dashboard or PHP FastCGI manager."},
    9042: {"service": "Cassandra-Native", "severity": "high", "risk": "Apache Cassandra native CQL query client port."},
    9090: {"service": "Prometheus/Cockpit", "severity": "medium", "risk": "Prometheus metric collector or Cockpit server admin."},
    9092: {"service": "Apache-Kafka", "severity": "high", "risk": "Apache Kafka message broker listener."},
    9200: {"service": "Elasticsearch", "severity": "high", "risk": "Elasticsearch REST search API exposed externally."},
    9300: {"service": "Elastic-Cluster", "severity": "medium", "risk": "Elasticsearch internal node communication."},
    9999: {"service": "JDWP/Urchin", "severity": "critical", "risk": "Java Debug Wire Protocol or diagnostic daemon exposed."},
    10000: {"service": "Webmin", "severity": "high", "risk": "Webmin Linux system administration web interface."},
    11211: {"service": "Memcached", "severity": "high", "risk": "Memcached distributed memory caching system listener."},
    15672: {"service": "RabbitMQ-Mgmt", "severity": "medium", "risk": "RabbitMQ web management UI console."},
    27017: {"service": "MongoDB", "severity": "critical", "risk": "MongoDB document store listener exposed externally."},
    27018: {"service": "MongoDB-Shard", "severity": "high", "risk": "MongoDB sharded cluster routing daemon."},
    50000: {"service": "SAP-Gateway", "severity": "high", "risk": "SAP NetWeaver diagnostic gateway or Jenkins agent port."},
    50070: {"service": "Hadoop-HDFS", "severity": "high", "risk": "Hadoop NameNode administrative web interface."},
}

# Pre-defined subsets for scan modes
QUICK_PORTS = [80, 443, 8080, 8443, 8000, 1720, 21, 22, 25, 3389, 3306, 5432, 6379, 27017, 8888]
STANDARD_PORTS = [
    21, 22, 23, 25, 53, 80, 110, 139, 143, 389, 443, 445, 465, 587, 636, 1433,
    1521, 1720, 2082, 2083, 2087, 3000, 3306, 3389, 4200, 5000, 5432, 5900,
    6379, 7001, 8000, 8080, 8081, 8443, 8888, 9000, 9090, 9200, 10000, 27017,
]
DEEP_PORTS = list(KNOWN_PORTS.keys())


def scan_target_ports(
    target_host_or_url: str,
    scan_mode: str = "quick",
    timeout: float = 1.5,
    max_workers: int = 20,
) -> List[Dict[str, Any]]:
    """Scan ports on target host concurrently using native non-blocking sockets.

    - quick: 15 most frequent web, admin, and database ports (~1 sec)
    - standard: 40 critical network services (~2-3 sec)
    - deep: 85+ well-known, cloud, database, messaging, and telephony ports (~4-6 sec)
    """
    host = target_host_or_url.strip()
    if host.startswith("http://") or host.startswith("https://"):
        parsed = urllib.parse.urlsplit(host)
        host = parsed.hostname or host

    if not host:
        return []

    # Resolve IP address
    try:
        ip = socket.gethostbyname(host)
    except Exception:
        return []

    mode_lower = (scan_mode or "quick").lower()
    if mode_lower == "deep":
        ports_to_scan = DEEP_PORTS
        port_timeout = min(timeout, 2.0)
        workers = max(max_workers, 25)
    elif mode_lower == "standard":
        ports_to_scan = STANDARD_PORTS
        port_timeout = min(timeout, 1.5)
        workers = max(max_workers, 18)
    else:
        ports_to_scan = QUICK_PORTS
        port_timeout = min(timeout, 1.0)
        workers = max(max_workers, 15)

    open_ports: List[Dict[str, Any]] = []

    def _check_port(port: int) -> Optional[Dict[str, Any]]:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(port_timeout)
        try:
            res = s.connect_ex((ip, port))
            if res == 0:
                meta = KNOWN_PORTS.get(port, {"service": f"TCP/{port}", "severity": "low", "risk": "Open network port."})
                return {
                    "port": port,
                    "service": meta["service"],
                    "protocol": "tcp",
                    "state": "OPEN",
                    "severity": meta["severity"],
                    "risk": meta["risk"],
                    "cwe_id": "CWE-200",
                    "ip": ip,
                }
        except Exception:
            pass
        finally:
            try:
                s.close()
            except Exception:
                pass
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_check_port, p): p for p in ports_to_scan}
        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            if res:
                open_ports.append(res)

    open_ports.sort(key=lambda x: x["port"])
    return open_ports
