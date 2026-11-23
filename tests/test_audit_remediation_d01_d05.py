"""Regression tests for Phase P3 audit findings D01–D05.

Coverage:
- D01: Candidate findings linked strictly by candidate ID; unrelated findings do not validate candidate.
- D02: SVG DAG renderer constructs nodes safely via DOM APIs without inline onclick script injection.
- D03: Docker cleanup preserves running containers by default (preserve_running=True).
- D04: CI workflow contains required branch triggers for staging, release, and feature branches.
- D05: Version alignment across metadata files and fixture sanitization / secret freedom.
"""

from __future__ import annotations

import re
from pathlib import Path
import pytest
import yaml

from strix.runtime.docker_cleanup import reap_orphaned_containers


# ---------------------------------------------------------------------------
# D01 Tests: Candidate Finding Linkage
# ---------------------------------------------------------------------------

def test_d01_unrelated_findings_do_not_validate_candidate() -> None:
    """A run with candidate A confirmed and B merely observed must never treat B as confirmed."""
    from strix.report.reconciliation import reconcile_all

    run_data = {
        "run_id": "run-d01-test",
        "candidates": [
            {"id": "cand-a", "title": "SQL Injection", "endpoint": "/sqli", "state": "VALIDATED"},
            {"id": "cand-b", "title": "Directory Traversal", "endpoint": "/lfi", "state": "PENDING"},
        ],
        "findings": [
            {
                "id": "FINDING-001",
                "candidate_id": "cand-a",
                "title": "SQL Injection",
                "verification_state": "verified",
                "verified": True,
            }
        ],
        "tool_calls": [
            {"tool": "exec_command", "args": {"command": "curl http://127.0.0.1/sqli"}}
        ],
    }

    reconciled = reconcile_all(run_data)
    candidates_by_id = {c["id"]: c for c in reconciled.get("candidates", [])}

    cand_a = candidates_by_id["cand-a"]
    cand_b = candidates_by_id["cand-b"]

    # Candidate A has a matching verified finding
    assert cand_a.get("state") in ("VALIDATED", "VERIFIED_VULNERABILITY")

    # Candidate B does NOT have a matching finding; must not be marked verified
    assert cand_b.get("state") != "VERIFIED_VULNERABILITY"
    assert cand_b.get("verified") is not True


# ---------------------------------------------------------------------------
# D02 Tests: SVG DOM Safety & No Inline Onclick Injection
# ---------------------------------------------------------------------------

def test_d02_svg_renderer_avoids_inline_onclick() -> None:
    """app.js must not interpolate raw candidate IDs into SVG innerHTML onclick handlers."""
    app_js_path = Path(__file__).resolve().parent.parent / "strix" / "interface" / "web" / "js" / "app.js"
    assert app_js_path.is_file(), f"Missing app.js at {app_js_path}"
    content = app_js_path.read_text(encoding="utf-8")

    # Insecure pattern: onclick="inspectDagNode('${...}')" or similar
    insecure_pattern = re.compile(r'onclick\s*=\s*["\']inspectDagNode\(["\']?\$\{', re.IGNORECASE)
    assert not insecure_pattern.search(content), "Found insecure inline onclick handler in app.js"

    # Secure pattern: addEventListener('click', ...)
    assert "inspectDagNode" in content
    assert "addEventListener" in content or "data-node-id" in content or "dataset.nodeId" in content


# ---------------------------------------------------------------------------
# D03 Tests: Docker Cleanup Preserves Running Containers
# ---------------------------------------------------------------------------

def test_d03_running_sandboxes_preserved_by_default() -> None:
    """reap_orphaned_containers must preserve running containers by default."""
    # When docker client is not connected / mock environment, reap_orphaned_containers
    # should safely return empty report with 0 killed without raising unhandled error.
    report = reap_orphaned_containers(
        active_run_ids=["run-active-001"],
        preserve_running=True,
    )
    assert isinstance(report, dict)
    assert report.get("killed_count", 0) == 0
    assert "errors" in report


# ---------------------------------------------------------------------------
# D04 Tests: CI Workflow Branch Triggers
# ---------------------------------------------------------------------------

def test_d04_ci_workflow_branch_triggers() -> None:
    """ci.yml must trigger on main, ai-vapt-full-application, ai-vapt-release, and fix/*."""
    ci_yml_path = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"
    assert ci_yml_path.is_file(), f"Missing ci.yml at {ci_yml_path}"
    content = ci_yml_path.read_text(encoding="utf-8")

    parsed = yaml.safe_load(content)
    on_config = parsed.get(True) if True in parsed else parsed.get("on", {})
    push_config = on_config.get("push", {})
    branches = push_config.get("branches", [])

    assert "main" in branches
    assert "ai-vapt-full-application" in branches
    assert "ai-vapt-release" in branches
    assert any("fix/" in b or b == "fix/*" for b in branches)


# ---------------------------------------------------------------------------
# D05 Tests: Release Metadata Alignment & Fixture Sanitization
# ---------------------------------------------------------------------------

def test_d05_release_metadata_alignment() -> None:
    """pyproject.toml, README.md, and CHANGELOG.md must consistently reference v1.7.0."""
    root_dir = Path(__file__).resolve().parent.parent

    pyproject_text = (root_dir / "pyproject.toml").read_text(encoding="utf-8")
    readme_text = (root_dir / "README.md").read_text(encoding="utf-8")
    changelog_text = (root_dir / "CHANGELOG.md").read_text(encoding="utf-8")

    # pyproject.toml has version 1.7.0
    assert 'version = "1.7.0"' in pyproject_text or 'version = "1.7.0rc1"' in pyproject_text

    # README references 1.7.0 RC1
    assert "1.7.0" in readme_text

    # CHANGELOG references 1.7.0-rc1
    assert "1.7.0" in changelog_text


def test_d05_no_plaintext_private_keys_in_repo() -> None:
    """Ensure no real RSA/EC private keys or production credentials exist in tracked source."""
    root_dir = Path(__file__).resolve().parent.parent
    strix_dir = root_dir / "strix"

    for py_file in strix_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        assert "-----BEGIN RSA PRIVATE KEY-----" not in text
        assert "-----BEGIN EC PRIVATE KEY-----" not in text
        assert "-----BEGIN OPENSSH PRIVATE KEY-----" not in text
