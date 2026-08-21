"""VAPT report generation (Phase 3, Task 3.3).

Produces two artifacts from a final AgentState:
  - structured JSON (machine-readable, for the dashboard "download")
  - human-readable PDF (for the thesis appendix / supervisor)

Both include validated vulnerabilities, rejected/low-ranked exploits, and the
wasted-attempt/time-saving metrics the framework is built to demonstrate.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import List

from core.schemas import ExecutionOutcome, Finding, UsabilityRank

REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "reports")


def build_report(target: str, findings: List[Finding], logs: List[str],
                 results: List[dict], provider: str, mode: str,
                 threshold: int) -> dict:
    validated = [f for f in findings if f.execution_outcome == ExecutionOutcome.SUCCESS]
    rejected = [f for f in findings if f.usability_rank == UsabilityRank.LOW]
    total_requests = sum(r.get("request_count", 0) for r in results)

    # "Time saved" estimate: each avoided LOW-ranked exploit *would* have cost
    # up to `threshold` attempts. We count pivots that spared low-value routes.
    wasted_avoided = len(rejected) * threshold

    return {
        "target": target,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "provider": provider,
        "mode": mode,
        "pivot_threshold": threshold,
        "summary": {
            "total_findings": len(findings),
            "validated": len(validated),
            "low_ranked_skipped": len(rejected),
            "total_requests": total_requests,
            "wasted_attempts_avoided": wasted_avoided,
        },
        "validated_vulnerabilities": [
            {
                "cve": f.cve, "port": f.port, "service": f.service,
                "epss": f.epss_score, "usability": f.usability_rank.value if f.usability_rank else None,
                "outcome": f.execution_outcome.value if f.execution_outcome else None,
            } for f in validated
        ],
        "rejected_exploits": [
            {"cve": f.cve, "reason": "LOW usability rank"} for f in rejected
        ],
        "remediation": _remediation(validated),
        "execution_log": logs,
    }


def _remediation(validated: List[Finding]) -> List[str]:
    recs = []
    for f in validated:
        recs.append(f"Patch / mitigate {f.cve} (EPSS={f.epss_score:.4f}).")
    if not recs:
        recs.append("No validated exploitation in this run; re-scan after remediation.")
    return recs


def save_json(report: dict, path: str = None) -> str:
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = path or os.path.join(REPORT_DIR, f"vapt_report_{datetime.now():%Y%m%d_%H%M%S}.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    return path


def save_pdf(report: dict, path: str = None) -> str:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table

    os.makedirs(REPORT_DIR, exist_ok=True)
    path = path or os.path.join(REPORT_DIR, f"vapt_report_{datetime.now():%Y%m%d_%H%M%S}.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=styles["Title"], fontSize=16)
    body = styles["BodyText"]
    flow = [Paragraph("Autonomous AI VAPT Report", title), Spacer(1, 8)]
    flow.append(Paragraph(f"Target: {report['target']} | Mode: {report['mode']} | "
                          f"Provider: {report['provider']}", body))
    flow.append(Paragraph(f"Generated: {report['generated']}", body))
    flow.append(Spacer(1, 10))

    s = report["summary"]
    flow.append(Paragraph("Summary", styles["Heading2"]))
    rows = [[k, str(v)] for k, v in s.items()]
    flow.append(Table(rows, colWidths=[180, 320]))
    flow.append(Spacer(1, 10))

    flow.append(Paragraph("Validated Vulnerabilities", styles["Heading2"]))
    if report["validated_vulnerabilities"]:
        vrows = [["CVE", "Port", "EPSS", "Usability", "Outcome"]]
        for v in report["validated_vulnerabilities"]:
            vrows.append([v["cve"], str(v["port"]), f"{v['epss']:.4f}",
                          v["usability"], v["outcome"]])
        flow.append(Table(vrows, colWidths=[120, 60, 80, 90, 120]))
    else:
        flow.append(Paragraph("None validated in this run.", body))
    flow.append(Spacer(1, 10))

    flow.append(Paragraph("Remediation", styles["Heading2"]))
    for r in report["remediation"]:
        flow.append(Paragraph(f"&bull; {r}", body))

    doc.build(flow)
    return path
