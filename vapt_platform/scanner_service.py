"""Controlled scanner execution service for authorized web targets (Phase 32).

Builds on the existing offline scanner adapters (vapt_platform/scanners.py)
by adding guarded live execution for explicitly authorized LOCAL targets only.

Safety rules:
    - Every entry point re-validates the target via web_target.parse_web_target
      (fail closed). No validation → no subprocess, ever.
    - No shell strings: subprocess argv lists only.
    - No user-controlled template/command input; fixed safe scan profiles.
    - Nuclei absence is handled gracefully (status NOT AVAILABLE).

Provenance recorded for every scan: scanner, target, command metadata,
start/end time, output path, exit code, finding count.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Optional


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _clean_version(raw: str) -> str:
    """Strip ANSI color codes and extract a compact version line."""
    text = _ANSI_RE.sub("", raw or "").strip()
    if not text:
        return "unknown"
    # Prefer the line naming the engine version (nuclei prints INF log lines).
    for line in text.splitlines():
        if "Engine Version" in line:
            return line.split("Engine Version:")[-1].strip()[:40]
        if line.lower().startswith("nmap version"):
            return line.strip()[:80]
    return text.splitlines()[0].strip()[:80]


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def _which_or_version(binary: str, version_args: list[str]) -> dict[str, Any]:
    path = shutil.which(binary)
    if not path:
        return {"available": False, "path": None, "version": None}
    try:
        proc = subprocess.run(
            [path, *version_args],
            capture_output=True, text=True, timeout=15,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        version = _clean_version(out)
    except Exception:
        version = "unknown"
    return {"available": True, "path": path, "version": version[:120]}


def nmap_status() -> dict[str, Any]:
    """Check Nmap executable availability."""
    return {"scanner": "nmap", **_which_or_version("nmap", ["--version"])}


def nuclei_status() -> dict[str, Any]:
    """Check Nuclei executable availability."""
    return {"scanner": "nuclei", **_which_or_version("nuclei", ["-version"])}


def scanner_status() -> dict[str, Any]:
    """Combined scanner availability report."""
    return {"nmap": nmap_status(), "nuclei": nuclei_status()}


# ---------------------------------------------------------------------------
# Scan results
# ---------------------------------------------------------------------------

@dataclass
class ScanResult:
    """Provenance + findings for one controlled scanner execution."""
    scanner: str = ""
    target: str = ""
    command: list[str] = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""
    duration_s: float = 0.0
    output_path: str = ""
    exit_code: int = -1
    finding_count: int = 0
    status: str = "UNKNOWN"  # COMPLETED | FAILED | NOT AVAILABLE | SKIPPED
    detail: str = ""
    findings: list[Any] = field(default_factory=list)

    def to_dict(self, include_findings: bool = False) -> dict[str, Any]:
        d = {
            "scanner": self.scanner,
            "target": self.target,
            "command": list(self.command),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_s": round(self.duration_s, 3),
            "output_path": self.output_path,
            "exit_code": self.exit_code,
            "finding_count": self.finding_count,
            "status": self.status,
            "detail": self.detail,
        }
        if include_findings:
            d["findings"] = [f for f in self.findings]
        return d


def _utc_now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _ensure_output_dir(output_dir: Optional[str]) -> str:
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        return output_dir
    return tempfile.mkdtemp(prefix="ai_vapt_scan_")


# ---------------------------------------------------------------------------
# Nmap web-target discovery
# ---------------------------------------------------------------------------

def run_nmap_discovery(
    raw_url: str,
    output_dir: Optional[str] = None,
    timeout: int = 180,
) -> ScanResult:
    """Run controlled Nmap service discovery against an authorized web target.

    Fixed safe profile: nmap -Pn -sV -p <port> -oX <output> <host>.
    Target is re-validated here — never execute on authorization failure.
    """
    from vapt_platform.web_target import parse_web_target

    # Fail closed BEFORE any subprocess or output-dir side effects.
    target = parse_web_target(raw_url)

    status = nmap_status()
    if not status["available"]:
        return ScanResult(
            scanner="nmap", target=target.normalized_url, status="NOT AVAILABLE",
            detail="Nmap executable not found on PATH.",
        )

    out_dir = _ensure_output_dir(output_dir)
    out_path = os.path.join(out_dir, f"nmap_{target.host}_{target.port}.xml")
    # Use the deterministically resolved loopback IP (127.0.0.1 for localhost)
    # to avoid DNS in scans. resolved_host is guaranteed loopback by
    # parse_web_target, so this never widens the target scope.
    argv = [
        status["path"], "-Pn", "-sV",
        "-p", str(target.port),
        "-oX", out_path,
        target.resolved_host,
    ]

    start = time.time()
    start_iso = _utc_now()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        return ScanResult(
            scanner="nmap", target=target.normalized_url, command=argv,
            start_time=start_iso, end_time=_utc_now(),
            duration_s=time.time() - start, output_path=out_path,
            exit_code=-1, status="FAILED",
            detail=f"Nmap timed out after {timeout}s.",
        )
    except Exception as e:
        return ScanResult(
            scanner="nmap", target=target.normalized_url, command=argv,
            start_time=start_iso, end_time=_utc_now(),
            duration_s=time.time() - start, output_path=out_path,
            exit_code=-1, status="FAILED", detail=f"Nmap execution failed: {e}",
        )

    end_iso = _utc_now()
    duration = time.time() - start

    # Parse via the EXISTING offline adapter (no new finding representation).
    from vapt_platform.scanners import NmapXmlAdapter
    try:
        findings = NmapXmlAdapter().parse(out_path)
    except Exception as e:
        return ScanResult(
            scanner="nmap", target=target.normalized_url, command=argv,
            start_time=start_iso, end_time=end_iso, duration_s=duration,
            output_path=out_path, exit_code=exit_code, status="FAILED",
            detail=f"Nmap ran (exit {exit_code}) but XML parsing failed: {e}",
        )

    ok = exit_code == 0
    return ScanResult(
        scanner="nmap", target=target.normalized_url, command=argv,
        start_time=start_iso, end_time=end_iso, duration_s=duration,
        output_path=out_path, exit_code=exit_code,
        finding_count=len(findings),
        status="COMPLETED" if ok else "FAILED",
        detail=f"Nmap discovery exit={exit_code}, findings={len(findings)}.",
        findings=findings,
    )


# ---------------------------------------------------------------------------
# Nuclei web vulnerability scan (controlled local-target profile)
# ---------------------------------------------------------------------------

#: Fixed safe Nuclei profile for the local training application.
#: No user-supplied templates or flags are accepted.
#: Scope: technology fingerprinting + misconfiguration + exposure templates
#: (bounded subset appropriate for a training app — NOT the full corpus).
#: Throughput (-rate-limit/-c) is set for loopback-only targets, which is
#: safe because parse_web_target() guarantees locality before execution.
NUCLEI_TEMPLATE_SUBDIRS = (
    "http/technologies",
    "http/misconfiguration",
    "http/exposures",
    "http/exposed-panels",
)
NUCLEI_FIXED_FLAGS = ["-silent", "-timeout", "5", "-rate-limit", "150",
                      "-c", "50", "-retries", "1"]


def nuclei_template_dirs() -> list[str]:
    """Resolve the bounded template directories for the fixed profile.

    Returns absolute paths under ~/nuclei-templates (nuclei's default
    location, populated via `nuclei -update-templates`). Empty list when
    templates are not installed — the caller reports FAILED explicitly
    instead of silently scanning with a different scope.
    """
    root = os.path.join(os.path.expanduser("~"), "nuclei-templates")
    dirs = [os.path.join(root, sub) for sub in NUCLEI_TEMPLATE_SUBDIRS]
    return [d for d in dirs if os.path.isdir(d)]


def run_nuclei_scan(
    raw_url: str,
    output_dir: Optional[str] = None,
    timeout: int = 300,
) -> ScanResult:
    """Run a controlled Nuclei scan against an authorized web target.

    Returns status NOT AVAILABLE (with zero findings) when Nuclei is not
    installed. Target is re-validated here — never execute on failure.
    """
    from vapt_platform.web_target import parse_web_target

    # Fail closed BEFORE any subprocess or output-dir side effects.
    target = parse_web_target(raw_url)

    status = nuclei_status()
    if not status["available"]:
        return ScanResult(
            scanner="nuclei", target=target.normalized_url, status="NOT AVAILABLE",
            detail="Nuclei executable not found on PATH. Vulnerability-scan "
                   "findings are unavailable; Nmap discovery still applies.",
        )

    out_dir = _ensure_output_dir(output_dir)
    out_path = os.path.join(out_dir, f"nuclei_{target.host}_{target.port}.jsonl")

    template_dirs = nuclei_template_dirs()
    if not template_dirs:
        return ScanResult(
            scanner="nuclei", target=target.normalized_url, status="FAILED",
            detail="Nuclei template set not found (~/nuclei-templates). "
                   "Run `nuclei -update-templates` first; refusing to scan "
                   "with an unintended template scope.",
        )

    argv = [
        status["path"], "-target", target.normalized_url,
        "-t", ",".join(template_dirs),
        "-jsonl", "-o", out_path, *NUCLEI_FIXED_FLAGS,
    ]

    start = time.time()
    start_iso = _utc_now()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        return ScanResult(
            scanner="nuclei", target=target.normalized_url, command=argv,
            start_time=start_iso, end_time=_utc_now(),
            duration_s=time.time() - start, output_path=out_path,
            exit_code=-1, status="FAILED",
            detail=f"Nuclei timed out after {timeout}s.",
        )
    except Exception as e:
        return ScanResult(
            scanner="nuclei", target=target.normalized_url, command=argv,
            start_time=start_iso, end_time=_utc_now(),
            duration_s=time.time() - start, output_path=out_path,
            exit_code=-1, status="FAILED", detail=f"Nuclei execution failed: {e}",
        )

    end_iso = _utc_now()
    duration = time.time() - start

    # Parse via the EXISTING offline Nuclei adapter.
    from vapt_platform.scanners import NucleiAdapter
    try:
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            findings = NucleiAdapter().parse(out_path)
        else:
            findings = []
    except Exception as e:
        return ScanResult(
            scanner="nuclei", target=target.normalized_url, command=argv,
            start_time=start_iso, end_time=end_iso, duration_s=duration,
            output_path=out_path, exit_code=exit_code, status="FAILED",
            detail=f"Nuclei ran (exit {exit_code}) but output parsing failed: {e}",
        )

    ok = exit_code == 0
    return ScanResult(
        scanner="nuclei", target=target.normalized_url, command=argv,
        start_time=start_iso, end_time=end_iso, duration_s=duration,
        output_path=out_path, exit_code=exit_code,
        finding_count=len(findings),
        status="COMPLETED" if ok else "FAILED",
        detail=f"Nuclei scan exit={exit_code}, findings={len(findings)}.",
        findings=findings,
    )
