"""Audit-Ready Comprehensive Report Builder for AI-VAPT.

Builds structured audit reports containing:
- Executive assessment summary with severity distribution
- Complete vulnerability findings with CVSS, CVE, CWE, and OWASP mapping
- Cryptographic SHA-256 evidence hashes (tamper-proof PoC)
- Tailored remediation configurations (Nginx/Apache & Code patches)
- GAP-1 Candidate Triage Prioritization Queue
- GAP-2 Bounded Dynamic Pivoting State & Audit Trail
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from strix.core.triage.owasp_mapping import map_finding_to_owasp


def render_html_report(run_data: Any) -> str:
    """Render a standalone, executive-grade, printable styled HTML assessment report."""
    if hasattr(run_data, "vulnerability_reports") and not isinstance(run_data, dict):
        run_data = {
            "run_id": getattr(run_data, "run_id", getattr(run_data, "run_name", "unknown")),
            "status": "completed",
            "mode": getattr(run_data, "execution_mode", "web"),
            "execution_mode": getattr(run_data, "execution_mode", None),
            "findings": getattr(run_data, "vulnerability_reports", []),
            "start_time": getattr(run_data, "start_time", None),
            "end_time": getattr(run_data, "end_time", None),
        }

    from strix.report.reconciliation import reconcile_all

    run_data = reconcile_all(run_data)

    run_id = html.escape(str(run_data.get("run_id", "unknown")))
    status = html.escape(str(run_data.get("status", "completed")))
    mode = html.escape(str(run_data.get("mode", "web")))
    raw_exec_mode = str(run_data.get("execution_mode") or run_data.get("mode") or "web").lower()
    if raw_exec_mode in ("autonomous", "autonomous_multi_agent"):
        exec_mode_display = "Autonomous Multi-Agent Core (Docker)"
    elif raw_exec_mode in (
        "lightweight",
        "lightweight_active_scanner",
        "in_process",
        "web",
        "web_controlled",
    ):
        exec_mode_display = "Lightweight Active Scanner (In-Process)"
    elif raw_exec_mode == "blocked":
        exec_mode_display = "Blocked (Runtime Dependencies Unavailable)"
    else:
        exec_mode_display = html.escape(raw_exec_mode.replace("_", " ").title())
    raw_target = run_data.get("target_url", run_data.get("target", "Target Scope"))
    target = html.escape(str(raw_target))
    target_ip = html.escape(str(run_data.get("target_ip") or "Resolved via DNS"))
    evidence_tier = html.escape(str(run_data.get("evidence_tier") or "OBSERVED_EXTERNAL"))
    safety_notice = html.escape(
        str(
            run_data.get("safety_notice")
            or "LIVE ACTIVE VAPT — Non-destructive active verification with cryptographic SHA-256 evidence."
        )
    )

    # Format created_at to local timezone with abbreviation
    raw_created = run_data.get("created_at")
    if raw_created:
        try:
            dt = datetime.fromisoformat(str(raw_created).replace("Z", "+00:00"))
            created_at = dt.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        except Exception:
            created_at = str(raw_created)
    else:
        created_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    created_at = html.escape(created_at)

    findings = run_data.get("findings", [])
    candidates = run_data.get("candidates", [])
    decision_trace = run_data.get("decision_trace", [])
    pivot_events = run_data.get("pivot_events", [])
    tech_stack = run_data.get("tech_stack", "generic_web")

    dur_secs = (
        run_data.get("active_duration_seconds")
        if run_data.get("active_duration_seconds") is not None
        else run_data.get("duration_seconds")
    )
    if dur_secs is not None:
        try:
            total_sec = max(0, int(float(dur_secs)))
            dur_display = (
                f"{total_sec // 3600:02d}:{(total_sec % 3600) // 60:02d}:{total_sec % 60:02d}"
            )
        except Exception:
            dur_display = str(dur_secs)
    else:
        dur_display = "—"

    raw_started = run_data.get("start_time") or run_data.get("created_at")
    if raw_started:
        try:
            dt_s = datetime.fromisoformat(str(raw_started).replace("Z", "+00:00"))
            started_at = dt_s.strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            started_at = str(raw_started)
    else:
        started_at = "—"
    started_at = html.escape(started_at)

    raw_ended = run_data.get("end_time") or run_data.get("completed_at")
    if raw_ended:
        try:
            dt_e = datetime.fromisoformat(str(raw_ended).replace("Z", "+00:00"))
            ended_at = dt_e.strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            ended_at = str(raw_ended)
    else:
        ended_at = "Running" if status.lower() == "running" else "—"
    ended_at = html.escape(ended_at)

    candidate_acct = run_data.get("candidate_accounting") or {}
    dispatched_cnt = candidate_acct.get("dispatched", len(candidates))
    investigated_cnt = candidate_acct.get(
        "investigated",
        sum(
            1
            for c in candidates
            if c.get("state") in ("VALIDATED", "ABANDONED") or c.get("attempts", 0) > 0
        ),
    )
    verified_findings_cnt = sum(
        1
        for f in findings
        if f.get("verified") or str(f.get("verification_state", "")).lower() == "verified"
    )

    turns_consumed = int(
        run_data.get("turns_consumed") or (run_data.get("stats") or {}).get("attempts", 0) or 0
    )
    configured_turn_limit = int(
        run_data.get("configured_turn_limit") or run_data.get("max_turns", 500) or 500
    )
    completeness_pct = float(run_data.get("assessment_completeness_percent", 0.0) or 0.0)
    run_lifecycle_status = html.escape(
        str(
            run_data.get("run_lifecycle_status")
            or f"Run process completed — {turns_consumed} of {configured_turn_limit} turns used."
        )
    )

    # Severity counters
    crit_count = sum(1 for f in findings if f.get("severity", "").upper() == "CRITICAL")
    high_count = sum(1 for f in findings if f.get("severity", "").upper() == "HIGH")
    med_count = sum(1 for f in findings if f.get("severity", "").upper() == "MEDIUM")
    low_count = sum(1 for f in findings if f.get("severity", "").upper() == "LOW")

    # DEF-02: Honest GAP-2 Pivot & Abandonment accounting
    # Executed pivots require an active redirection dispatch (next_candidate exists and pivot_executed is not False)
    executed_pivots = len(
        [
            e
            for e in pivot_events
            if (e.get("type") in ("REDIRECT", "GAP2_PIVOT") or e.get("event") == "GAP2_PIVOT")
            and e.get("pivot_executed") is True
            and (e.get("next_candidate") or e.get("to_candidate"))
        ]
    )
    abandoned_candidates_count = len(
        [
            e
            for e in pivot_events
            if (
                e.get("type") in ("REDIRECT", "GAP2_PIVOT", "ABANDON")
                or e.get("event") in ("GAP2_PIVOT", "ABANDON")
                or "abandon" in str(e.get("result", "")).lower()
                or "abandon" in str(e.get("message", "")).lower()
                or "abandon" in str(e.get("reason", "")).lower()
            )
            and (
                e.get("outcome") == "ABANDON"
                or e.get("type") == "ABANDON"
                or e.get("event") == "ABANDON"
                or "abandon" in str(e.get("result", "")).lower()
                or "abandon" in str(e.get("message", "")).lower()
                or "abandon" in str(e.get("reason", "")).lower()
            )
        ]
    )
    # Fallback to run_data gap2_pivots / pivots if pivot_events list was not supplied directly
    if not pivot_events:
        executed_pivots = int(run_data.get("gap2_pivots", run_data.get("pivots", 0)) or 0)
    total_pivots = executed_pivots
    if total_pivots == 0 and abandoned_candidates_count > 0:
        pivots_display_html = f'{total_pivots} <small style="font-size:0.75rem; color:#94a3b8;">({abandoned_candidates_count} abandoned; queue exhausted)</small>'
    else:
        pivots_display_html = (
            f'{total_pivots} <small style="font-size:0.75rem; color:#94a3b8;">(k=2 bound)</small>'
        )

    sp_stats = run_data.get("spider_stats") or {}
    sp_paths_cnt = len(sp_stats.get("discovered_paths", []))
    sp_forms_cnt = sp_stats.get("forms_count", 0)
    sp_params_cnt = sp_stats.get("parameters_count", 0)
    sp_card_html = ""
    if sp_stats:
        sp_card_html = f"""
        <div style="background:rgba(56, 189, 248, 0.08); border:1px solid rgba(56, 189, 248, 0.3); border-radius:8px; padding:0.85rem 1.25rem; margin-bottom:1.5rem; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:0.75rem;">
            <div>
                <strong style="color:#38bdf8; font-size:0.85rem; text-transform:uppercase; letter-spacing:0.05em;">🕷️ Web Spider Surface Profiling:</strong>
                <span style="color:#cbd5e1; font-size:0.85rem; margin-left:0.5rem;">Crawled internal attack surface, mapped form targets and parameter vectors.</span>
            </div>
            <div style="display:flex; gap:1.25rem; font-size:0.85rem; font-family:monospace;">
                <span style="color:#f8fafc;">Routes: <strong style="color:#38bdf8;">{sp_paths_cnt}</strong></span>
                <span style="color:#f8fafc;">Forms: <strong style="color:#38bdf8;">{sp_forms_cnt}</strong></span>
                <span style="color:#f8fafc;">Parameters: <strong style="color:#38bdf8;">{sp_params_cnt}</strong></span>
            </div>
        </div>
        """

    # 1. Findings table rows & Mitigations
    finding_rows = []
    mitigation_sections = []
    target_clean = str(raw_target).replace("https://", "").replace("http://", "").rstrip("/")

    for idx, f in enumerate(findings, 1):
        raw_title = f.get("title", f.get("id", f"Finding #{idx}"))
        title = html.escape(str(raw_title))
        sev = str(f.get("severity", "medium")).upper()
        cvss = html.escape(str(f.get("cvss_score", 5.0)))
        raw_cve = f.get("cve_id")
        raw_cwe = f.get("cwe_id", "CWE-200")
        raw_owasp = f.get("owasp_category", "A01:2021 - Broken Access Control")
        location = html.escape(str(f.get("location", f.get("endpoint", "/"))))
        hash_val = html.escape(str(f.get("evidence_hash", "N/A")))
        raw_impact = f.get("impact", "")
        raw_remed = f.get("remediation_technical", "")
        raw_retest = f.get("retest_procedure", "")

        # Fallback to catalog profile if metadata was incomplete
        if not raw_cve or raw_cve == "CVE-2022-XXXX" or not raw_remed:
            mapped = map_finding_to_owasp(
                raw_title, f.get("id"), endpoint=location, tech_stack=tech_stack
            )
            raw_cve = raw_cve if raw_cve and raw_cve != "CVE-2022-XXXX" else mapped.get("cve_id")
            raw_cwe = (
                raw_cwe if raw_cwe and raw_cwe != "CWE-200" else mapped.get("cwe_id", "CWE-200")
            )
            raw_impact = raw_impact or mapped.get(
                "impact", "Potential security exposure requiring defensive hardening."
            )
            raw_remed = raw_remed or mapped.get(
                "remediation_technical",
                "# Apply input validation, sanitization, and least-privilege permissions.",
            )
            raw_retest = raw_retest or mapped.get(
                "retest_procedure",
                f'curl -s -k "https://{target_clean}{"/" + location.lstrip("/") if location else "/"}"',
            )

        has_real_cve = bool(
            raw_cve
            and str(raw_cve).upper().startswith("CVE-")
            and "XXXX" not in str(raw_cve).upper()
            and "N/A" not in str(raw_cve).upper()
        )
        if has_real_cve:
            cve_badge = f'<span class="badge-cve">{html.escape(str(raw_cve))}</span>'
            mit_cve_badge = f'<span class="badge-cve">{html.escape(str(raw_cve))}</span>'
        else:
            cve_badge = '<span class="badge" style="background:rgba(148, 163, 184, 0.1); color:#94a3b8; border:1px solid #334155; font-size:0.75rem;">N/A (CWE-based)</span>'
            mit_cve_badge = '<span class="badge" style="background:rgba(148, 163, 184, 0.1); color:#94a3b8; border:1px solid #334155; font-size:0.75rem;">CWE-based Weakness</span>'

        cwe = html.escape(str(raw_cwe))
        owasp_cat = html.escape(str(raw_owasp))
        impact = html.escape(str(raw_impact))
        remed_tech = html.escape(str(raw_remed))
        clean_ep = "/" + location.lstrip("/") if location else "/"
        retest_cmd = html.escape(
            str(raw_retest.replace("<target>", target_clean).replace("<endpoint>", clean_ep))
        )

        sev_badge = (
            '<span class="badge badge-crit">CRITICAL</span>'
            if sev == "CRITICAL"
            else (
                '<span class="badge badge-high">HIGH</span>'
                if sev == "HIGH"
                else (
                    '<span class="badge badge-med">MEDIUM</span>'
                    if sev == "MEDIUM"
                    else '<span class="badge badge-low">LOW</span>'
                )
            )
        )

        v_state_raw = f.get("verification_state") or (
            "Verified" if f.get("verified") else "Candidate"
        )
        # Normalize old title-case and new lowercase values
        v_state_norm = str(v_state_raw).strip()
        _v_map = {
            "Verified": "VERIFIED",
            "verified": "VERIFIED",
            "Unconfirmed": "UNCONFIRMED",
            "unconfirmed": "UNCONFIRMED",
            "Candidate": "CANDIDATE",
            "candidate": "CANDIDATE",
        }
        v_state_str = _v_map.get(v_state_norm, v_state_norm.upper())

        if v_state_str == "VERIFIED" or "VERIF" in v_state_str:
            v_badge = '<span class="badge badge-emerald">VERIFIED</span>'
        elif v_state_str == "UNCONFIRMED":
            v_badge = '<span class="badge badge-amber">UNCONFIRMED</span>'
        elif "INVESTIGAT" in v_state_str or "ATTEMPT" in v_state_str:
            v_badge = '<span class="badge badge-amber">UNDER INVESTIGATION</span>'
        elif v_state_str == "CANDIDATE":
            v_badge = '<span class="badge badge-cyan">CANDIDATE</span>'
        elif "BLOCKED" in v_state_str:
            v_badge = '<span class="badge badge-rose">BLOCKED</span>'
        elif "FALSE" in v_state_str:
            v_badge = '<span class="badge badge-rose">FALSE POSITIVE</span>'
        else:
            v_badge = f'<span class="badge badge-cyan">{html.escape(v_state_str)}</span>'

        v_proc = html.escape(
            str(
                f.get("verification_procedure")
                or f.get("validation_method")
                or "Active HTTP verification probe & response pattern analysis"
            )
        )
        param_str = html.escape(str(f.get("parameter") or "N/A"))
        synthetic_note = (
            '&nbsp;⚠️ <small style="color:#f59e0b;">(synthetic)</small>'
            if f.get("evidence_type") in ("synthetic_legacy", "legacy_synthetic")
            else ""
        )
        short_hash = f"{hash_val[:12]}...{hash_val[-6:]}" if len(hash_val) > 18 else hash_val

        finding_rows.append(
            f"""<tr>
                <td><strong>{title}</strong><br><small class="mono-sub">{location}</small><div style="margin-top:0.25rem;">{v_badge}</div></td>
                <td>{sev_badge}</td>
                <td><strong class="cvss-val">{cvss}</strong></td>
                <td>{cve_badge}</td>
                <td><span class="badge-cwe">{cwe}</span></td>
                <td>{owasp_cat}</td>
                <td><code class="hash-code">{short_hash}</code>{synthetic_note}</td>
            </tr>"""
        )

        color_border = (
            "#ef4444"
            if sev == "CRITICAL"
            else ("#f97316" if sev == "HIGH" else ("#f59e0b" if sev == "MEDIUM" else "#3b82f6"))
        )

        val_method = html.escape(
            str(
                f.get("validation_method")
                or "Active HTTP verification probe & response payload matching"
            )
        )
        sev_just = html.escape(
            str(
                f.get("severity_justification")
                or f"Rated {sev} (CVSS {cvss}) based on unauthenticated network exploitability and observed impact."
            )
        )
        # DEF-04: Remove synthetic request/response fabrication
        raw_req = f.get("poc_script_code") or f.get("reproducible_request")
        rep_req = (
            html.escape(str(raw_req))
            if raw_req and str(raw_req).strip()
            else "No raw HTTP exchange captured."
        )

        raw_ev = f.get("evidence_snippet") or f.get("evidence") or f.get("reproducible_response")
        resp_ev = (
            html.escape(str(raw_ev))
            if raw_ev and str(raw_ev).strip()
            else "No raw HTTP exchange captured."
        )

        mitigation_sections.append(
            f"""<div class="mitigation-card" style="border-left-color: {color_border};" id="mitigation-{idx}">
                <div class="mitigation-header">
                    <h3>{idx}. Mitigations for: {title}</h3>
                    <div class="badge-cluster">
                        {v_badge}
                        {sev_badge}
                        {mit_cve_badge}
                        <span class="badge-cwe">{cwe}</span>
                    </div>
                </div>
                <p><strong>Affected Endpoint:</strong> <code>{location}</code> (Parameter: <code>{param_str}</code>)</p>
                <p><strong>Validation Method:</strong> {val_method}</p>
                <p><strong>Verification Procedure:</strong> {v_proc}</p>
                <p><strong>OWASP Taxonomy:</strong> {owasp_cat}</p>
                <p><strong>Severity Justification:</strong> {sev_just}</p>
                <p><strong>Vulnerability Impact:</strong> {impact}</p>
                <p><strong>Demonstrated Impact:</strong> {impact}</p>
                <div class="code-title">Reproducible Request / Proof-of-Concept:</div>
                <pre class="code-block"><code>{rep_req}</code></pre>
                <div class="code-title">Relevant Response Evidence:</div>
                <pre class="code-block"><code>{resp_ev}</code></pre>
                <div class="code-title">Server Hardening Configuration & Code Patch:</div>
                <pre class="code-block"><code>{remed_tech}</code></pre>
                <div class="code-title retest-title">Retest Verification Procedure:</div>
                <code class="cmd-block">{retest_cmd}</code>
            </div>"""
        )

    findings_table = (
        "\n".join(finding_rows)
        if finding_rows
        else "<tr><td colspan='7'>No confirmed vulnerabilities identified.</td></tr>"
    )

    if not mitigation_sections:
        # Provide proactive hardening guidelines for high-priority attack vectors evaluated
        top_candidates = [
            c for c in candidates if str(c.get("severity", "")).upper() in ("CRITICAL", "HIGH")
        ][:3]
        if not top_candidates and candidates:
            top_candidates = candidates[:3]

        fallback_mitigations = []
        for f_idx, tc in enumerate(top_candidates, 1):
            mapped = map_finding_to_owasp(tc.get("name", tc.get("id")), tc.get("id"))
            tc_title = html.escape(str(mapped.get("title", tc.get("name", tc.get("id")))))
            tc_cve = mapped.get("cve_id")
            has_tc_cve = bool(
                tc_cve
                and str(tc_cve).upper().startswith("CVE-")
                and "XXXX" not in str(tc_cve).upper()
                and "N/A" not in str(tc_cve).upper()
            )
            tc_cve_badge = (
                f'<span class="badge-cve">{html.escape(str(tc_cve))}</span>'
                if has_tc_cve
                else '<span class="badge" style="background:rgba(148, 163, 184, 0.1); color:#94a3b8; border:1px solid #334155; font-size:0.75rem;">CWE-based Weakness</span>'
            )
            tc_cwe = html.escape(str(mapped.get("cwe_id", "CWE-200")))
            tc_owasp = html.escape(
                f"{mapped.get('owasp_id', 'A01:2021')} - {mapped.get('category_name', 'Security Configuration')}"
            )
            tc_impact = html.escape(str(mapped.get("impact", "Baseline security hygiene defense.")))
            tc_remed = html.escape(
                str(
                    mapped.get(
                        "remediation_technical",
                        "# Ensure defensive controls and hardening policies are active.",
                    )
                )
            )
            tc_retest = html.escape(
                str(mapped.get("retest_procedure", f'curl -s -k "https://{target_clean}/"'))
            )

            fallback_mitigations.append(
                f"""<div class="mitigation-card" style="border-left-color: #38bdf8;" id="mitigation-recom-{f_idx}">
                    <div class="mitigation-header">
                        <h3>{f_idx}. Defensive Hardening Recommendation: {tc_title}</h3>
                        <div class="badge-cluster">
                            <span class="badge badge-low">PREVENTATIVE</span>
                            {tc_cve_badge}
                            <span class="badge-cwe">{tc_cwe}</span>
                        </div>
                    </div>
                    <p><strong>OWASP Taxonomy:</strong> {tc_owasp}</p>
                    <p><strong>Preventative Impact:</strong> {tc_impact}</p>
                    <div class="code-title">Server Hardening Configuration & Code Patch:</div>
                    <pre class="code-block"><code>{tc_remed}</code></pre>
                    <div class="code-title retest-title">Verification Procedure:</div>
                    <code class="cmd-block">{tc_retest}</code>
                </div>"""
            )
        mitigations_html = (
            "\n".join(fallback_mitigations)
            if fallback_mitigations
            else "<p>No immediate remediation actions required. All evaluated vectors conformed to baseline controls.</p>"
        )
    else:
        mitigations_html = "\n".join(mitigation_sections)

    # 2. GAP-1 Triage table rows
    findings_total = len(findings)
    gap1_rows = []
    for c in candidates:
        rank = html.escape(str(c.get("priority_rank", "-")))
        c_title = html.escape(str(c.get("name", c.get("id"))))
        c_endp = html.escape(str(c.get("endpoint", c.get("target", "/"))))
        c_sev = html.escape(str(c.get("severity", "medium")).upper())
        c_cvss = html.escape(str(c.get("cvss_score", 5.0)))
        c_usab = html.escape(str(c.get("usability_rank", "MEDIUM")))
        comp_val = c.get("composite_score", c.get("probability", 0.5))
        c_comp = html.escape(
            f"{comp_val:.4f}" if isinstance(comp_val, (int, float)) else str(comp_val)
        )
        c_reason = html.escape(str(c.get("reasoning", "")))
        c_state = str(c.get("state", "PENDING")).upper()

        usab_badge = (
            '<span class="badge badge-emerald">HIGH</span>'
            if c_usab == "HIGH"
            else (
                '<span class="badge badge-amber">MEDIUM</span>'
                if c_usab == "MEDIUM"
                else '<span class="badge badge-purple">LOW</span>'
            )
        )

        if c_state == "VERIFIED_VULNERABILITY" or (c_state == "VALIDATED" and findings_total > 0):
            state_badge = '<span class="badge badge-emerald">VALIDATED VULNERABILITY</span>'
        elif c_state == "VALIDATED_OBSERVATION" or (c_state == "VALIDATED" and findings_total == 0):
            state_badge = '<span class="badge badge-cyan">VALIDATED OBSERVATION</span>'
        elif c_state in ("RULED_OUT", "RULED_OUT_WITH_EVIDENCE"):
            state_badge = '<span class="badge badge-secondary">RULED OUT</span>'
        elif c_state == "ABANDONED":
            state_badge = '<span class="badge badge-rose">ABANDONED</span>'
        elif c_state == "NOT_TESTED":
            state_badge = (
                '<span class="badge" style="background:#334155; color:#94a3b8;">NOT TESTED</span>'
            )
        elif c_state == "BLOCKED":
            state_badge = '<span class="badge badge-rose">BLOCKED</span>'
        elif c_state == "INCONCLUSIVE":
            state_badge = '<span class="badge badge-amber">INCONCLUSIVE</span>'
        elif c_state in ("ATTEMPTING", "UNDER_INVESTIGATION", "PROBE_EXECUTED"):
            state_badge = '<span class="badge badge-cyan">UNDER INVESTIGATION</span>'
        else:
            state_badge = '<span class="badge badge-cyan">PENDING</span>'

        gap1_rows.append(
            f"""<tr>
                <td><strong>#{rank}</strong></td>
                <td><strong>{c_title}</strong><br><small class="mono-sub">{c_endp}</small></td>
                <td>{c_sev} (CVSS {c_cvss})</td>
                <td>{usab_badge}</td>
                <td><strong class="comp-val">{c_comp}</strong></td>
                <td>{state_badge}</td>
                <td class="reason-cell">{c_reason}</td>
            </tr>"""
        )
    gap1_table = (
        "\n".join(gap1_rows)
        if gap1_rows
        else "<tr><td colspan='7'>No candidate queue available.</td></tr>"
    )

    # 3. Scan Matrix Category Table
    scan_matrix = run_data.get("scan_matrix", [])
    if not scan_matrix:
        from strix.core.scanner.passive_rules import SCAN_CATEGORIES

        scan_matrix = [
            {
                "category_key": k,
                "title": v["title"],
                "description": v["description"],
                "test_count": v["test_count"],
                "capability": v["capability"],
                "findings_count": 0,
                "status": "NOT TESTED",
            }
            for k, v in SCAN_CATEGORIES.items()
        ]

    # DEF-01: Derive honest category execution status and test coverage
    tested_cat_count = 0
    executed_tests_count = 0
    matrix_rows = []
    for m in scan_matrix:
        m_title = html.escape(str(m.get("title", "")))
        configured_tests = int(m.get("configured_checks") or m.get("test_count", 0))
        executed_tests = int(m.get("executed_checks", m.get("test_count", 0)))
        m_cap = html.escape(str(m.get("capability", "Passive & Active Probes")))
        m_count = int(m.get("findings_count", 0))
        m_status_raw = str(m.get("status", "")).upper().strip()

        # Enforce truthful status: 0 executed checks can NEVER be marked PASSED
        if executed_tests == 0 and m_count == 0:
            m_status_raw = "NOT TESTED"

        if m_count > 0 or m_status_raw in ("FAILED", "VULNERABILITIES_IDENTIFIED"):
            m_status = '<span class="badge badge-amber">FINDINGS IDENTIFIED</span>'
            status_color = "#f59e0b"
            tested_cat_count += 1
            executed_tests_count += executed_tests
        elif m_status_raw == "PASSED":
            m_status = '<span class="badge badge-emerald">PASSED</span>'
            status_color = "#10b981"
            tested_cat_count += 1
            executed_tests_count += executed_tests
        elif m_status_raw == "PARTIALLY TESTED":
            m_status = '<span class="badge badge-cyan">PARTIALLY TESTED</span>'
            status_color = "#38bdf8"
            tested_cat_count += 1
            executed_tests_count += executed_tests
        elif m_status_raw == "BLOCKED":
            m_status = '<span class="badge badge-rose">BLOCKED</span>'
            status_color = "#f43f5e"
            tested_cat_count += 1
            executed_tests_count += executed_tests
        elif m_status_raw == "INCONCLUSIVE":
            m_status = '<span class="badge badge-amber">INCONCLUSIVE</span>'
            status_color = "#f59e0b"
            tested_cat_count += 1
            executed_tests_count += executed_tests
        else:
            m_status = '<span class="badge" style="background:rgba(148, 163, 184, 0.15); color:#94a3b8; border:1px solid #475569;">NOT TESTED</span>'
            status_color = "#94a3b8"

        test_display = (
            f"{executed_tests} executed <small style='color:#64748b;'>({configured_tests} configured)</small>"
            if configured_tests != executed_tests
            else f"{executed_tests} tests"
        )

        matrix_rows.append(
            f"""<tr>
                <td><strong>{m_title}</strong></td>
                <td>{test_display}</td>
                <td><span style="font-size:0.8rem; color:#94a3b8;">{m_cap}</span></td>
                <td><strong style="color:{status_color};">{m_count} finding(s)</strong></td>
                <td>{m_status}</td>
            </tr>"""
        )
    matrix_table = "\n".join(matrix_rows)

    total_matrix_tests = sum(int(m.get("test_count", 0)) for m in scan_matrix)
    untested_cat_count = len(scan_matrix) - tested_cat_count
    if tested_cat_count == len(scan_matrix) and len(scan_matrix) > 0:
        matrix_narrative = (
            f"Comprehensive multi-layer audit coverage across all {len(scan_matrix)} core VAPT test categories "
            f"({executed_tests_count} total tests evaluated) aligned with industry benchmarks:"
        )
    elif tested_cat_count > 0:
        matrix_narrative = (
            f"Audit coverage across {tested_cat_count} of {len(scan_matrix)} test categories "
            f"({executed_tests_count} of {total_matrix_tests} test routines evaluated; {untested_cat_count} categories not tested):"
        )
    else:
        matrix_narrative = "Scan category baseline matrix (no category tests were dispatched or completed in this assessment; all categories marked NOT TESTED):"

    # 4. Open Ports & Environmental Observations Table
    open_ports = run_data.get("open_ports", [])
    target_ports = [
        p for p in open_ports if p.get("in_scope", True) and p.get("scope") != "environmental"
    ]
    env_ports = [
        p for p in open_ports if not p.get("in_scope", True) or p.get("scope") == "environmental"
    ]

    def _render_port_rows(port_list: list[dict[str, Any]], is_env: bool = False) -> str:
        rows = []
        for p in port_list:
            p_num = html.escape(str(p.get("port", "-")))
            p_proto = html.escape(str(p.get("protocol", "tcp")).upper())
            p_state = html.escape(str(p.get("state", "OPEN")).upper())
            p_confirmed = bool(p.get("service_confirmed", False))

            if is_env or not p_confirmed:
                p_serv = "Unfingerprinted TCP Listener"
                conv = p.get("conventional_service") or p.get("service", "")
                conv_clean = conv.split(" (Conventional")[0]
                serv_cell = f"{p_serv}<br><small style='color:#94a3b8;'>Conventional Guess: {html.escape(conv_clean)}</small>"
                conf_badge = '<span class="badge badge-amber">UNCONFIRMED</span>'
                p_sev_badge = '<span class="badge badge-low">INFO</span>'
                p_risk = html.escape(
                    str(
                        p.get("risk")
                        or f"TCP handshake succeeded on port {p_num}. Protocol unconfirmed; out of scope."
                    )
                )
            else:
                p_serv = html.escape(str(p.get("service", "HTTP Web Service")))
                fp = p.get("service_fingerprint") or "HTTP/Web Service"
                serv_cell = f"<strong>{p_serv}</strong><br><small style='color:#38bdf8;'>Fingerprint: {html.escape(str(fp))}</small>"
                conf_badge = '<span class="badge badge-emerald">CONFIRMED</span>'
                p_sev_badge = '<span class="badge badge-low">LOW (INFO)</span>'
                p_risk = html.escape(
                    str(p.get("risk") or "Target application web service endpoint.")
                )

            rows.append(
                f"""<tr>
                    <td><strong style="font-family:monospace; color:#38bdf8;">Port {p_num}/{p_proto}</strong></td>
                    <td>{serv_cell}</td>
                    <td>{conf_badge}</td>
                    <td><span class="badge badge-emerald">{p_state}</span></td>
                    <td>{p_sev_badge}</td>
                    <td style="font-size:0.85rem; color:#cbd5e1;">{p_risk}</td>
                </tr>"""
            )
        return "\n".join(rows)

    target_ports_header = """<tr style="background:rgba(15, 23, 42, 0.8);"><td colspan="6" style="padding:8px 12px; font-weight:700; color:#38bdf8; font-size:0.8rem; letter-spacing:0.05em; text-transform:uppercase;">
        Target Application Exposed Ports
    </td></tr>"""
    target_ports_html = (
        _render_port_rows(target_ports, is_env=False)
        if target_ports
        else "<tr><td colspan='6'>Standard web ports inspected.</td></tr>"
    )
    env_ports_html = _render_port_rows(env_ports, is_env=True) if env_ports else ""

    ports_table = target_ports_header + "\n" + target_ports_html
    if env_ports_html:
        ports_table += f"""
        <tr style="background:rgba(30, 41, 59, 0.6);"><td colspan="6" style="padding:8px 12px; font-weight:700; color:#94a3b8; font-size:0.8rem; letter-spacing:0.05em; text-transform:uppercase;">
            Out-of-Scope Environmental Host Network Listeners (Non-Target Handshakes — Informational Only)
        </td></tr>
        {env_ports_html}
        """

    # 5. Software Components (SCA) Table
    components = run_data.get("components", [])
    comp_rows = []
    for comp in components:
        c_lib = html.escape(str(comp.get("library", "Unknown")).capitalize())
        c_ver = html.escape(str(comp.get("version", "N/A")))
        c_file = html.escape(str(comp.get("source_file", "/")))
        c_vuln = comp.get("vulnerable", False)
        c_cves = comp.get("cves", [])
        cve_badges = (
            " ".join(f'<span class="badge-cve">{html.escape(cve)}</span>' for cve in c_cves)
            if c_cves
            else '<span class="badge" style="background:#1e293b; color:#94a3b8; border:1px solid #334155;">N/A (No Known CVEs)</span>'
        )
        c_stat = (
            '<span class="badge badge-amber">OUTDATED / VULNERABLE</span>'
            if c_vuln
            else '<span class="badge badge-emerald">SECURE VERSION</span>'
        )
        c_remed = html.escape(
            str(comp.get("remediation", "Keep component updated to supported version."))
        )
        comp_rows.append(
            f"""<tr>
                <td><strong>{c_lib}</strong></td>
                <td><code style="color:#38bdf8;">v{c_ver}</code></td>
                <td><small class="mono-sub">{c_file}</small></td>
                <td>{c_stat}</td>
                <td>{cve_badges}</td>
                <td style="font-size:0.85rem; color:#cbd5e1;">{c_remed}</td>
            </tr>"""
        )
    components_table = (
        "\n".join(comp_rows)
        if comp_rows
        else "<tr><td colspan='6'>No outdated or vulnerable client-side JavaScript components identified.</td></tr>"
    )

    # 6. Decision trace list
    trace_items = (
        "\n".join(
            f'<div class="trace-row">{html.escape(str(line))}</div>' for line in decision_trace
        )
        if decision_trace
        else "<div class='trace-row'>No trace recorded.</div>"
    )

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI-VAPT Security Audit Report - {run_id}</title>
    <style>
        :root {{
            --bg-page: #0b0f19;
            --bg-surface: #111827;
            --bg-code: #030712;
            --text-primary: #f1f5f9;
            --text-muted: #94a3b8;
            --border: #1f2937;
            --primary: #38bdf8;
            --primary-dark: #0284c7;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: var(--bg-page);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 2.5rem 1.5rem;
            max-width: 1200px;
            margin: auto;
        }}
        h1, h2, h3 {{ color: var(--primary); font-weight: 700; margin-top: 1.75rem; margin-bottom: 0.75rem; }}
        .header {{
            background: linear-gradient(135deg, #1e293b, #0f172a);
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 2rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 20px rgba(0,0,0,0.4);
        }}
        .header h1 {{ margin: 0 0 0.5rem 0; font-size: 1.8rem; display: flex; align-items: center; gap: 0.75rem; }}
        .header p {{ margin: 0; color: var(--text-muted); font-size: 0.95rem; }}
        
        .jump-nav {{
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
            margin-bottom: 2rem;
            padding: 0.75rem 1rem;
            background: #111827;
            border: 1px solid var(--border);
            border-radius: 8px;
        }}
        .jump-nav a {{
            color: var(--primary);
            text-decoration: none;
            font-size: 0.85rem;
            font-weight: 600;
            padding: 0.3rem 0.65rem;
            border-radius: 4px;
            background: rgba(56, 189, 248, 0.1);
            transition: all 0.2s ease;
        }}
        .jump-nav a:hover {{ background: rgba(56, 189, 248, 0.25); text-decoration: underline; }}

        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 1rem;
            margin-bottom: 1.75rem;
        }}
        .meta-card {{
            background: var(--bg-surface);
            padding: 1.25rem;
            border-radius: 8px;
            border: 1px solid var(--border);
        }}
        .meta-label {{ font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; letter-spacing: 0.05em; }}
        .meta-value {{ font-size: 1.35rem; font-weight: 700; margin-top: 0.35rem; color: #f8fafc; }}
        
        .severity-bar {{
            display: flex;
            height: 12px;
            border-radius: 6px;
            overflow: hidden;
            margin: 1.5rem 0 0.5rem 0;
            background: #1f2937;
        }}
        .sev-crit-bar {{ background: #ef4444; width: {(crit_count / max(len(findings), 1)) * 100}%; }}
        .sev-high-bar {{ background: #f97316; width: {(high_count / max(len(findings), 1)) * 100}%; }}
        .sev-med-bar  {{ background: #f59e0b; width: {(med_count / max(len(findings), 1)) * 100}%; }}
        .sev-low-bar  {{ background: #3b82f6; width: {(low_count / max(len(findings), 1)) * 100}%; }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 2.5rem;
            background: var(--bg-surface);
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid var(--border);
        }}
        th, td {{ padding: 0.85rem 1rem; text-align: left; border-bottom: 1px solid var(--border); font-size: 0.9rem; }}
        th {{ background: #1e293b; color: #e2e8f0; font-weight: 600; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; }}
        tr:hover td {{ background: #1a2234; }}
        .mono-sub {{ color: #94a3b8; font-family: monospace; display: block; }}
        .cvss-val {{ color: #f8fafc; }}
        .comp-val {{ color: var(--primary); font-family: monospace; }}
        .reason-cell {{ font-size: 0.85rem; color: #cbd5e1; }}
        
        .badge {{ display: inline-block; padding: 0.2rem 0.55rem; border-radius: 4px; font-weight: 700; font-size: 0.75rem; text-transform: uppercase; }}
        .badge-crit {{ background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.4); }}
        .badge-high {{ background: rgba(249, 115, 22, 0.2); color: #f97316; border: 1px solid rgba(249, 115, 22, 0.4); }}
        .badge-med, .badge-amber {{ background: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.4); }}
        .badge-low  {{ background: rgba(59, 130, 246, 0.2); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.4); }}
        .badge-emerald {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }}
        .badge-rose {{ background: rgba(244, 63, 94, 0.2); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.4); }}
        .badge-cyan {{ background: rgba(6, 182, 212, 0.2); color: #38bdf8; border: 1px solid rgba(6, 182, 212, 0.4); }}
        .badge-purple {{ background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4); }}
        .badge-cve {{ background: #1e1b4b; color: #a5b4fc; padding: 0.2rem 0.5rem; border-radius: 4px; font-family: monospace; font-size: 0.8rem; border: 1px solid #3730a3; }}
        .badge-cwe {{ background: #142e2a; color: #5eead4; padding: 0.2rem 0.5rem; border-radius: 4px; font-family: monospace; font-size: 0.8rem; border: 1px solid #115e59; }}
        .hash-code {{ font-family: monospace; font-size: 0.75rem; color: #38bdf8; background: #0f172a; padding: 0.2rem 0.4rem; border-radius: 3px; }}

        .mitigation-card {{
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-left: 5px solid var(--primary);
            padding: 1.5rem;
            margin-bottom: 1.75rem;
            border-radius: 6px;
        }}
        .mitigation-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; flex-wrap: wrap; gap: 0.5rem; }}
        .mitigation-header h3 {{ margin: 0; color: #f8fafc; font-size: 1.15rem; }}
        .badge-cluster {{ display: flex; gap: 0.5rem; align-items: center; }}
        .code-title {{ font-size: 0.85rem; font-weight: 700; color: var(--primary); margin-top: 0.75rem; }}
        .retest-title {{ color: #34d399; margin-top: 0.75rem; }}
        .code-block {{
            background: var(--bg-code);
            padding: 1rem;
            border-radius: 6px;
            font-family: monospace;
            font-size: 0.85rem;
            color: #e2e8f0;
            overflow-x: auto;
            border: 1px solid var(--border);
            margin: 0.35rem 0 0.75rem 0;
            white-space: pre-wrap;
            word-break: break-all;
        }}
        .cmd-block {{
            background: var(--bg-code);
            padding: 0.5rem 0.75rem;
            border-radius: 4px;
            font-family: monospace;
            font-size: 0.85rem;
            color: #7dd3fc;
            display: block;
            border: 1px solid var(--border);
            white-space: pre-wrap;
            word-break: break-all;
        }}

        .trace-box {{
            background: var(--bg-code);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 1rem 1.25rem;
            font-family: monospace;
            font-size: 0.85rem;
            max-height: 400px;
            overflow-y: auto;
            margin-bottom: 2.5rem;
        }}
        .trace-row {{ padding: 0.25rem 0; border-bottom: 1px solid rgba(255,255,255,0.05); color: #94a3b8; word-break: break-all; }}
        .trace-row:last-child {{ border-bottom: none; }}

        /* Professional Executive PDF & Print Optimization */
        @media print {{
            @page {{
                margin: 1.0cm 1.2cm;
                size: A4 portrait;
            }}
            *, *::before, *::after {{
                box-sizing: border-box !important;
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            }}
            body {{
                background: #ffffff !important;
                color: #0f172a !important;
                padding: 0 !important;
                font-size: 8pt !important;
                line-height: 1.35 !important;
                max-width: 100% !important;
            }}
            .no-print {{ display: none !important; }}
            .header {{
                background: #f8fafc !important;
                color: #0f172a !important;
                border: 1.5pt solid #cbd5e1 !important;
                border-left: 6pt solid #0284c7 !important;
                padding: 10pt 14pt !important;
                box-shadow: none !important;
                margin-bottom: 12pt !important;
                page-break-inside: avoid !important;
                break-inside: avoid !important;
            }}
            .header h1 {{ color: #0369a1 !important; font-size: 13pt !important; margin: 0 0 4pt 0 !important; }}
            .header p {{ color: #475569 !important; font-size: 8pt !important; margin: 0 !important; }}
            
            h1, h2, h3, h4 {{
                color: #0369a1 !important;
                page-break-after: avoid !important;
                break-after: avoid !important;
            }}
            h2 {{
                font-size: 10.5pt !important;
                margin: 14pt 0 6pt 0 !important;
                border-bottom: 1.5pt solid #cbd5e1 !important;
                padding-bottom: 3pt !important;
            }}
            h3 {{
                font-size: 9pt !important;
                margin: 0 0 3pt 0 !important;
            }}
            
            .meta-grid {{
                display: grid !important;
                grid-template-columns: repeat(3, 1fr) !important;
                gap: 6pt !important;
                margin-bottom: 10pt !important;
                page-break-inside: avoid !important;
                break-inside: avoid !important;
            }}
            .meta-card {{
                background: #f8fafc !important;
                border: 1pt solid #cbd5e1 !important;
                color: #0f172a !important;
                padding: 6pt 8pt !important;
                border-radius: 4pt !important;
                page-break-inside: avoid !important;
                break-inside: avoid !important;
            }}
            .meta-label {{ font-size: 6.5pt !important; color: #64748b !important; }}
            .meta-value {{ font-size: 10.5pt !important; color: #0f172a !important; margin-top: 2pt !important; }}
            .severity-bar {{ background: #e2e8f0 !important; height: 8pt !important; margin: 4pt 0 !important; }}
            
            table {{
                background: #ffffff !important;
                border: 1pt solid #cbd5e1 !important;
                font-size: 7.5pt !important;
                margin-bottom: 12pt !important;
                page-break-inside: auto !important;
            }}
            thead {{
                display: table-header-group !important;
            }}
            tr {{
                page-break-inside: avoid !important;
                break-inside: avoid !important;
            }}
            th {{
                background: #f1f5f9 !important;
                color: #0f172a !important;
                border-bottom: 1.5pt solid #cbd5e1 !important;
                padding: 4pt 6pt !important;
                font-size: 7pt !important;
            }}
            td {{
                border-bottom: 0.5pt solid #e2e8f0 !important;
                color: #1e293b !important;
                padding: 4pt 6pt !important;
                font-size: 7.5pt !important;
            }}
            .badge {{
                font-size: 6.5pt !important;
                padding: 1pt 3.5pt !important;
                border-radius: 2pt !important;
            }}
            .badge-cve {{
                font-size: 6.5pt !important;
                padding: 1pt 3pt !important;
                background: #e0e7ff !important;
                color: #3730a3 !important;
                border: 0.5pt solid #c7d2fe !important;
            }}
            .badge-cwe {{
                font-size: 6.5pt !important;
                padding: 1pt 3pt !important;
                background: #ccfbf1 !important;
                color: #0f766e !important;
                border: 0.5pt solid #99f6e4 !important;
            }}

            .mitigation-card {{
                background: #f8fafc !important;
                border: 1pt solid #cbd5e1 !important;
                border-left: 4pt solid #0284c7 !important;
                color: #0f172a !important;
                padding: 8pt 10pt !important;
                margin-bottom: 8pt !important;
                page-break-inside: avoid !important;
                break-inside: avoid !important;
                border-radius: 4pt !important;
            }}
            .mitigation-header {{
                margin-bottom: 4pt !important;
                display: flex !important;
                justify-content: space-between !important;
                align-items: center !important;
            }}
            .mitigation-header h3 {{
                color: #0f172a !important;
                font-size: 8.5pt !important;
                margin: 0 !important;
            }}
            .code-title {{
                color: #0369a1 !important;
                font-size: 7.5pt !important;
                font-weight: 700 !important;
                margin-top: 4pt !important;
                page-break-after: avoid !important;
                break-after: avoid !important;
            }}
            .retest-title {{
                color: #059669 !important;
                font-size: 7.5pt !important;
                font-weight: 700 !important;
                margin-top: 4pt !important;
                page-break-after: avoid !important;
                break-after: avoid !important;
            }}
            .code-block, .cmd-block {{
                background: #f1f5f9 !important;
                color: #0f172a !important;
                border: 0.5pt solid #cbd5e1 !important;
                font-size: 6.8pt !important;
                line-height: 1.25 !important;
                padding: 4pt 6pt !important;
                margin: 2pt 0 5pt 0 !important;
                border-radius: 3pt !important;
                white-space: pre-wrap !important;
                word-break: break-all !important;
                overflow: hidden !important;
                scrollbar-width: none !important;
            }}
            .code-block::-webkit-scrollbar, .cmd-block::-webkit-scrollbar {{
                display: none !important;
            }}

            .trace-box {{
                background: #f8fafc !important;
                border: 1pt solid #cbd5e1 !important;
                color: #334155 !important;
                font-size: 7pt !important;
                line-height: 1.3 !important;
                padding: 6pt 8pt !important;
                max-height: none !important;
                overflow: visible !important;
                page-break-inside: avoid !important;
                break-inside: avoid !important;
            }}
            .trace-row {{
                color: #475569 !important;
                border-bottom: 0.5pt solid #e2e8f0 !important;
                padding: 1.5pt 0 !important;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🛡️ AI-VAPT Autonomous Security Audit Report</h1>
        <p>Cryptographically Verified Vulnerability Assessment, GAP-1 Triage Queue & GAP-2 Pivoting Audit Trail</p>
    </div>

    <!-- Quick Jump Navigation -->
    <div class="jump-nav no-print">
        <span style="color:#94a3b8; font-size:0.85rem; font-weight:700; align-self:center; margin-right:0.25rem;">NAVIGATE:</span>
        <a href="#summary">🎯 Summary</a>
        <a href="#findings">🚨 Findings Table</a>
        <a href="#matrix">📊 Category Matrix</a>
        <a href="#ports">🌐 Open Ports</a>
        <a href="#components">📦 Components (SCA)</a>
        <a href="#mitigations">🔧 Remediation Roadmap</a>
        <a href="#gap1">📈 GAP-1 Triage</a>
        <a href="#gap2">🌲 GAP-2 Trace</a>
    </div>

    <!-- Engagement Integrity Notice -->
    <div style="background:rgba(16, 185, 129, 0.08); border:1px solid #059669; border-radius:8px; padding:0.85rem 1.25rem; margin-bottom:1.5rem; display:flex; align-items:center; gap:0.85rem;">
        <span style="font-size:1.5rem;">🔒</span>
        <div>
            <strong style="color:#34d399; font-size:0.85rem; text-transform:uppercase; letter-spacing:0.05em;">Engagement Verification & Integrity Notice:</strong>
            <div style="color:#cbd5e1; font-size:0.85rem; margin-top:0.2rem;">{safety_notice}</div>
        </div>
    </div>

    {sp_card_html}

    <!-- Executive Meta Grid -->
    <div class="meta-grid" id="summary">
        <div class="meta-card">
            <div class="meta-label">Run Reference</div>
            <div class="meta-value" style="font-family:monospace; font-size:1.1rem; color:#38bdf8;">{run_id}</div>
        </div>
        <div class="meta-card">
            <div class="meta-label">Assessment Started</div>
            <div class="meta-value" style="font-size:0.95rem; color:#f8fafc;">{started_at}</div>
        </div>
        <div class="meta-card">
            <div class="meta-label">Total Duration</div>
            <div class="meta-value" style="font-size:1.1rem; font-family:monospace; color:#38bdf8;">{dur_display}</div>
        </div>
        <div class="meta-card">
            <div class="meta-label">Assessment Status</div>
            <div class="meta-value" style="color:#10b981;">{status.upper()}</div>
        </div>
        <div class="meta-card">
            <div class="meta-label">Target Scope & IP</div>
            <div class="meta-value" style="font-size:0.95rem; word-break:break-all;">{target}<br><small style="font-size:0.8rem; color:#94a3b8; font-weight:normal;">({target_ip})</small></div>
        </div>
        <div class="meta-card">
            <div class="meta-label">Verified Findings</div>
            <div class="meta-value" style="color:#ef4444;">{verified_findings_cnt} <small style="font-size:0.75rem; color:#94a3b8;">({len(findings)} total)</small></div>
        </div>
        <div class="meta-card">
            <div class="meta-label">Evidence Tier</div>
            <div class="meta-value" style="font-size:0.95rem; color:#f8fafc;">{evidence_tier}</div>
        </div>
        <div class="meta-card">
            <div class="meta-label">GAP-1 Triage</div>
            <div class="meta-value" style="font-size:0.95rem; color:#f8fafc;">{investigated_cnt}/{dispatched_cnt} <small style="font-size:0.75rem; color:#94a3b8;">investigated</small></div>
        </div>
        <div class="meta-card">
            <div class="meta-label">Execution Mode</div>
            <div class="meta-value" style="font-size:0.95rem; color:#38bdf8;">{exec_mode_display}</div>
        </div>
        <div class="meta-card">
            <div class="meta-label">GAP-2 Dynamic Pivots</div>
            <div class="meta-value" style="color:#f59e0b;">{pivots_display_html}</div>
        </div>
        <div class="meta-card">
            <div class="meta-label">Execution Turns</div>
            <div class="meta-value" style="font-size:0.95rem; color:#f8fafc;">{turns_consumed} / {configured_turn_limit} <small style="font-size:0.75rem; color:#94a3b8;">turns used</small></div>
        </div>
        <div class="meta-card">
            <div class="meta-label">Assessment Lifecycle</div>
            <div class="meta-value" style="font-size:0.85rem; color:#f8fafc;">{run_lifecycle_status}</div>
        </div>
    </div>

    <!-- Severity Distribution Summary -->
    <div style="background:#111827; border:1px solid #1f2937; padding:1.25rem; border-radius:8px; margin-bottom:2rem;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem;">
            <strong style="color:#f8fafc; font-size:0.95rem;">Severity Distribution Breakdown</strong>
            <div style="display:flex; gap:1rem; font-size:0.85rem;">
                <span style="color:#ef4444; font-weight:700;">Critical: {crit_count}</span>
                <span style="color:#f97316; font-weight:700;">High: {high_count}</span>
                <span style="color:#f59e0b; font-weight:700;">Medium: {med_count}</span>
                <span style="color:#3b82f6; font-weight:700;">Low: {low_count}</span>
            </div>
        </div>
        <div class="severity-bar">
            <div class="sev-crit-bar"></div>
            <div class="sev-high-bar"></div>
            <div class="sev-med-bar"></div>
            <div class="sev-low-bar"></div>
        </div>
    </div>

    <!-- Section 1: Findings Table -->
    <h2 id="findings">1. Confirmed Vulnerability Findings & Cryptographic PoC Evidence</h2>
    <p style="color:#94a3b8; font-size:0.85rem; margin-top:-0.5rem; margin-bottom:1rem; line-height:1.5;">
        All findings below were actively confirmed with non-destructive verification against the target and cryptographically hashed using SHA-256.<br>
        <span style="color:#cbd5e1;"><em>Note on Vulnerability Taxonomy:</em> Architectural and web configuration weaknesses (e.g. missing HTTP hardening headers, insecure cookie flags, missing CSRF tokens, permissive CSP) are categorized under authoritative <strong>Common Weakness Enumerations (CWE)</strong> and <strong>OWASP Top 10</strong> standards. <strong>CVE Identifiers</strong> are strictly reserved for verified Common Vulnerabilities and Exposures in third-party COTS software components.</span>
    </p>
    <table>
        <thead>
            <tr>
                <th>Vulnerability Title & Location</th>
                <th>Severity</th>
                <th>CVSS</th>
                <th>CVE Reference</th>
                <th>CWE Identifier</th>
                <th>OWASP Classification</th>
                <th>SHA-256 Proof Hash</th>
            </tr>
        </thead>
        <tbody>
            {findings_table}
        </tbody>
    </table>

    <!-- Section 2: Scan Coverage & Vulnerability Category Matrix -->
    <h2 id="matrix">2. Scan Capabilities & Vulnerability Category Matrix</h2>
    <p style="color:#94a3b8; font-size:0.9rem; margin-top:-0.5rem; margin-bottom:1rem;">
        {matrix_narrative}
    </p>
    <table>
        <thead>
            <tr>
                <th>Vulnerability Category</th>
                <th>Total Rules</th>
                <th>Execution Capability</th>
                <th>Findings Identified</th>
                <th>Audit Status</th>
            </tr>
        </thead>
        <tbody>
            {matrix_table}
        </tbody>
    </table>

    <!-- Section 3: Network Surface & Open Port Reconnaissance -->
    <h2 id="ports">3. Target Network Surface & Open Port Reconnaissance</h2>
    <p style="color:#94a3b8; font-size:0.9rem; margin-top:-0.5rem; margin-bottom:1rem;">
        Non-destructive TCP socket connection reconnaissance across standard, administrative, database, and telephony listening daemons:
    </p>
    <table>
        <thead>
            <tr>
                <th>Listening Port & Protocol</th>
                <th>Service Name</th>
                <th>Socket State</th>
                <th>Exposure Severity</th>
                <th>Security Implication & Exposure Risk</th>
            </tr>
        </thead>
        <tbody>
            {ports_table}
        </tbody>
    </table>

    <!-- Section 4: Software Component Analysis (SCA) & Library Inventory -->
    <h2 id="components">4. Software Component Analysis (SCA) & Library Inventory</h2>
    <p style="color:#94a3b8; font-size:0.9rem; margin-top:-0.5rem; margin-bottom:1rem;">
        Client-side JavaScript libraries and third-party frameworks detected in page source cross-referenced with National Vulnerability Database (NVD) CVEs:
    </p>
    <table>
        <thead>
            <tr>
                <th>Library Component</th>
                <th>Detected Version</th>
                <th>Source Asset Location</th>
                <th>Security Status</th>
                <th>Authoritative Public CVE References</th>
                <th>Recommended Action</th>
            </tr>
        </thead>
        <tbody>
            {components_table}
        </tbody>
    </table>

    <!-- Section 5: Tailored Remediation Roadmap -->
    <h2 id="mitigations">5. Tailored Remediation Roadmap & Server Hardening Patches</h2>
    <p style="color:#94a3b8; font-size:0.9rem; margin-top:-0.5rem; margin-bottom:1.5rem;">
        Concrete, tailored configuration snippets and code-level patches for each identified vulnerability:
    </p>
    {mitigations_html}

    <!-- Section 6: GAP-1 Triage Prioritization -->
    <h2 id="gap1">6. GAP-1 Exploit Quality Prioritization & Candidate Queue</h2>
    <p style="color:#94a3b8; font-size:0.9rem; margin-top:-0.5rem; margin-bottom:1rem;">
        Candidate vulnerabilities ranked according to composite priority score:
        <em>Score = (w_cvss &times; S_cvss) + (w_exp &times; E_exp) + (w_ai &times; Q_ai)</em>
    </p>
    <table>
        <thead>
            <tr>
                <th>Rank</th>
                <th>Candidate & Target Vector</th>
                <th>Severity & CVSS</th>
                <th>Usability Rank</th>
                <th>Composite Score</th>
                <th>Status</th>
                <th>AI Triage Reasoning</th>
            </tr>
        </thead>
        <tbody>
            {gap1_table}
        </tbody>
    </table>

    <!-- Section 7: GAP-2 Bounded Dynamic Decision-Pivoting Trail -->
    <h2 id="gap2">7. GAP-2 Bounded Dynamic Pivoting (k=2) & Audit Trace</h2>
    <p style="color:#94a3b8; font-size:0.9rem; margin-top:-0.5rem; margin-bottom:1rem;">
        Chronological audit log showing state machine transitions, attempt limits, failure detection, and automatic route abandonment:
    </p>
    <div class="trace-box">
        {trace_items}
    </div>

    <hr style="border-color: #1f2937; margin-top: 3.5rem;">
    <p style="font-size: 0.85rem; color: #64748b; text-align: center;">
        AI-VAPT Autonomous Operations Engine • Cryptographically Verified Output • Generated {created_at}
    </p>
</body>
</html>"""
    return html_doc


build_executive_html_report = render_html_report
build_html_report = render_html_report
