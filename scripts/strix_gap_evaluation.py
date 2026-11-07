#!/usr/bin/env python3
"""Controlled A–E comparison of the GAP-1/GAP-2 bridge.

This harness exercises the actual Strix bridge module (queue loading, attempt
counters, pivot selection) without invoking an LLM. It is a deterministic
comparison for the decision-layer behavior; live LLM run results are reported
separately in EVALUATION_REPORT.md.

Usage:
    .venv/bin/python scripts/strix_gap_evaluation.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
STRIX_ROOT = Path(os.environ.get("STRIX_ROOT", "/home/vinit/STRIX/strix"))
BRIDGE_PATH = STRIX_ROOT / "strix" / "core" / "gap_bridge.py"
THRESHOLD = 2
BASELINE_ATTEMPTS_PER_CANDIDATE = 6

CANDIDATES = [
    {
        "id": "csrf",
        "title": "CSRF",
        "endpoint": "/csrf",
        "probability": 0.3,
        "quality_rank": "low",
        "assessed": True,
    },
    {
        "id": "xss",
        "title": "Reflected XSS",
        "endpoint": "/xss",
        "probability": 0.6,
        "quality_rank": "medium",
        "assessed": True,
    },
    {
        "id": "sqli",
        "title": "SQL injection",
        "endpoint": "/sqli",
        "probability": 0.85,
        "quality_rank": "high",
        "assessed": True,
    },
    {
        "id": "default-creds",
        "title": "Default credentials",
        "endpoint": "/login",
        "probability": 0.95,
        "quality_rank": "high",
        "assessed": True,
    },
    {
        "id": "fi",
        "title": "File inclusion",
        "endpoint": "/fi",
        "probability": 0.5,
        "quality_rank": "medium",
        "assessed": True,
    },
]
SUCCESS_CANDIDATE = "sqli"


def _load_bridge():
    if not BRIDGE_PATH.is_file():
        raise SystemExit(f"Strix bridge not found: {BRIDGE_PATH}")
    spec = importlib.util.spec_from_file_location("strix_gap_bridge_eval", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _queue_payload(bridge, ranked: dict[str, Any], *, gap1: bool) -> dict[str, Any]:
    if gap1:
        ordered = [dict(item) for item in ranked["candidates"]]
    else:
        by_id = {item["candidate_id"]: item for item in ranked["candidates"]}
        ordered = []
        for index, raw in enumerate(CANDIDATES, start=1):
            item = dict(by_id[raw["id"]])
            item["gap1_rank"] = index
            ordered.append(item)
    return {
        "original_order": [c["id"] for c in CANDIDATES],
        "ranked_order": [c["candidate_id"] for c in ordered],
        "ranking_changed": [c["candidate_id"] for c in ordered] != [c["id"] for c in CANDIDATES],
        "candidates": ordered,
    }


def _write_queue(control: Path, payload: dict[str, Any]) -> None:
    control.mkdir(parents=True, exist_ok=True)
    (control / "gap1_queue.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _simulate(bridge, config: str, *, gap1: bool, gap2: bool) -> dict[str, Any]:
    from vapt_platform.adapters.gap_hooks import assess_and_rank_candidates

    ranked = assess_and_rank_candidates(CANDIDATES)
    queue = _queue_payload(bridge, ranked, gap1=gap1)
    with tempfile.TemporaryDirectory(prefix=f"gap-eval-{config}-") as tmp:
        control = Path(tmp) / "control"
        _write_queue(control, queue)
        bridge.reset_state()
        os.environ[bridge.CONTROL_DIR_ENV] = str(control)
        os.environ[bridge.GAP1_ENABLED_ENV] = "1" if gap1 else "0"
        os.environ[bridge.GAP2_ENABLED_ENV] = "1" if gap2 else "0"
        os.environ[bridge.THRESHOLD_ENV] = str(THRESHOLD)

        attempts = 0
        pivots = 0
        order: list[str] = []
        first_verified_at = None
        for candidate in queue["candidates"]:
            candidate_id = candidate["candidate_id"]
            order.append(candidate_id)
            limit = THRESHOLD if gap2 else BASELINE_ATTEMPTS_PER_CANDIDATE
            for attempt in range(1, limit + 1):
                attempts += 1
                success = candidate_id == SUCCESS_CANDIDATE and attempt == 1
                if success:
                    first_verified_at = attempts
                    if gap2:
                        bridge.record_outcome(
                            title=candidate.get("title", ""),
                            endpoint=candidate.get("endpoint", ""),
                            success=True,
                            report_id="eval-report",
                        )
                    break
                if gap2:
                    outcome = bridge.record_outcome(
                        title=candidate.get("title", ""),
                        endpoint=candidate.get("endpoint", ""),
                        success=False,
                        detail="controlled failure",
                    )
                    if outcome.get("pivot"):
                        pivots += 1
                        break
            if first_verified_at is not None:
                break
    return {
        "config": config,
        "gap1": gap1,
        "gap2": gap2,
        "execution_order": order,
        "attempts": attempts,
        "pivots": pivots,
        "first_verified_finding": SUCCESS_CANDIDATE if first_verified_at else None,
        "attempts_before_first_finding": first_verified_at,
        "ranking_changed": queue["ranking_changed"],
    }


def main() -> int:
    bridge = _load_bridge()
    configs = [
        ("A", False, False),
        ("B", True, False),
        ("C", False, True),
        ("D", True, True),
        ("E", True, True),
    ]
    results = []
    for name, gap1, gap2 in configs:
        result = _simulate(bridge, name, gap1=gap1, gap2=gap2)
        results.append(result)
    print(json.dumps({"results": results}, indent=2))
    return 0


if __name__ == "__main__":
    env_control = os.environ.copy()
    try:
        raise SystemExit(main())
    finally:
        os.environ.clear()
        os.environ.update(env_control)
