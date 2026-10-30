"""Optional AI_VAPT GAP-1/GAP-2 bridge.

Activated only when the control plane sets ``STRIX_GAP_CONTROL_DIR``. The
bridge reads the AI_VAPT-ranked candidate queue, injects that order into the
root task, records attempt outcomes, and returns pivot guidance after the
configured failure threshold. It never changes scan scope: authorization is
enforced by the AI_VAPT adapter before Strix is launched.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONTROL_DIR_ENV = "STRIX_GAP_CONTROL_DIR"
QUEUE_ENV = "STRIX_GAP1_QUEUE"
THRESHOLD_ENV = "STRIX_GAP2_THRESHOLD"
GAP1_ENABLED_ENV = "STRIX_GAP1_ENABLED"
GAP2_ENABLED_ENV = "STRIX_GAP2_ENABLED"
DEFAULT_THRESHOLD = 2
QUEUE_FILENAME = "gap1_queue.json"
TRACE_FILENAME = "decision_trace.jsonl"

_attempts: dict[str, int] = {}
_exhausted: set[str] = set()
_completed: set[str] = set()
_announced = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def control_dir() -> Path | None:
    raw = os.environ.get(CONTROL_DIR_ENV, "").strip()
    return Path(raw) if raw else None


def _enabled(name: str) -> bool:
    return os.environ.get(name, "1").strip().lower() not in {"0", "false", "no", "off"}


def gap1_enabled() -> bool:
    return _enabled(GAP1_ENABLED_ENV)


def gap2_enabled() -> bool:
    return _enabled(GAP2_ENABLED_ENV)


def threshold() -> int:
    try:
        value = int(os.environ.get(THRESHOLD_ENV, DEFAULT_THRESHOLD))
    except (TypeError, ValueError):
        value = DEFAULT_THRESHOLD
    return max(1, value)


def _queue_path() -> Path | None:
    explicit = os.environ.get(QUEUE_ENV, "").strip()
    if explicit:
        return Path(explicit)
    directory = control_dir()
    return directory / QUEUE_FILENAME if directory else None


def load_queue() -> list[dict[str, Any]]:
    path = _queue_path()
    if path is None or not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return []
    return [dict(item) for item in candidates if isinstance(item, dict)]


def queue_order() -> tuple[list[str], list[str]]:
    path = _queue_path()
    if path is None or not path.is_file():
        return [], []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    if not isinstance(payload, dict):
        return [], []
    original = payload.get("original_order") if isinstance(payload.get("original_order"), list) else []
    ranked = payload.get("ranked_order") if isinstance(payload.get("ranked_order"), list) else []
    return [str(item) for item in original], [str(item) for item in ranked]


def note_event(event: str, **fields: Any) -> dict[str, Any]:
    payload = {"timestamp": _utc_now(), "event": event, **fields}
    directory = control_dir()
    if directory is not None:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / TRACE_FILENAME).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass
    return payload


def gap1_instruction_block() -> str:
    global _announced
    if not gap1_enabled():
        return ""
    candidates = load_queue()
    if not candidates:
        return ""
    if not _announced:
        original, ranked = queue_order()
        note_event(
            "GAP1_ROOT_TASK_INJECTED",
            original_order=original,
            ranked_order=ranked,
            ranking_changed=ranked != original,
        )
        _announced = True
    lines = [
        "## AI_VAPT GAP-1 prioritized candidate queue",
        "",
        "AI_VAPT assessed and ranked these authorized candidates before this run.",
        "Work through them in this exact order unless a candidate is proven",
        "ineligible. Candidate ids are stable identifiers used by GAP-2 attempt",
        "tracking. After each candidate, record the result and move on.",
        "",
    ]
    for entry in candidates:
        label = entry.get("title") or entry.get("endpoint") or entry.get("candidate_id")
        lines.append(
            f"{entry.get('gap1_rank', '?')}. [{entry.get('candidate_id')}] {label}"
            f" | endpoint={entry.get('endpoint') or entry.get('target') or 'n/a'}"
            f" | method={entry.get('method') or 'n/a'}"
            f" | quality={entry.get('quality_rank') or 'unassessed'}"
            f" | priority={entry.get('priority_score')}"
            f" | reasoning={(entry.get('assessment_reasoning') or 'recorded')}"
        )
    lines.extend(
        [
            "",
            f"If one candidate fails verification repeatedly (threshold "
            f"{threshold()}), abandon it and pivot to the next ranked candidate.",
            "Do not keep retrying an exhausted route.",
        ]
    )
    return "\n".join(lines)


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return cleaned[:80] or "candidate"


def candidate_for(title: str, endpoint: str, target: str) -> dict[str, Any] | None:
    candidates = load_queue()
    if not candidates:
        return None
    endpoint_key = (endpoint or "").strip().lower()
    target_key = (target or "").strip().lower()
    title_key = (title or "").strip().lower()
    for entry in candidates:
        entry_endpoint = str(entry.get("endpoint") or entry.get("target") or "").strip().lower()
        if endpoint_key and entry_endpoint and (
            endpoint_key == entry_endpoint
            or endpoint_key in entry_endpoint
            or entry_endpoint in endpoint_key
        ):
            return entry
    for entry in candidates:
        entry_title = str(entry.get("title") or "").strip().lower()
        if title_key and entry_title and (
            title_key == entry_title or title_key in entry_title or entry_title in title_key
        ):
            return entry
    if target_key:
        for entry in candidates:
            entry_target = str(entry.get("target") or "").strip().lower()
            if entry_target and (
                target_key == entry_target or target_key in entry_target or entry_target in target_key
            ):
                return entry
    return None


def candidate_id_for(title: str, endpoint: str, target: str) -> str:
    entry = candidate_for(title, endpoint, target)
    if entry is not None and entry.get("candidate_id"):
        return str(entry["candidate_id"])
    raw = endpoint or title or target or "unknown"
    return f"strix-{_slug(raw)}"


def next_candidate() -> dict[str, Any] | None:
    for entry in load_queue():
        candidate_id = str(entry.get("candidate_id") or "")
        if candidate_id and candidate_id not in _exhausted and candidate_id not in _completed:
            return entry
    return None


def record_outcome(
    *,
    title: str,
    endpoint: str = "",
    target: str = "",
    success: bool,
    detail: str = "",
    report_id: str = "",
) -> dict[str, Any]:
    """Record one candidate outcome and return GAP-2 guidance.

    Success completes the candidate. Failures increment its attempt count; when
    the threshold is reached the candidate is abandoned and the next ranked
    candidate is returned so the caller can steer the agent.
    """
    candidate_id = candidate_id_for(title, endpoint, target)
    if success:
        _attempts[candidate_id] = 0
        _completed.add(candidate_id)
        note_event(
            "GAP2_SUCCESS",
            candidate_id=candidate_id,
            outcome="SUCCESS",
            report_id=report_id,
            detail=detail,
        )
        nxt = next_candidate()
        return {
            "candidate_id": candidate_id,
            "attempts": 0,
            "threshold": threshold(),
            "pivot": False,
            "next_candidate": nxt,
        }

    attempts = _attempts.get(candidate_id, 0) + 1
    _attempts[candidate_id] = attempts
    note_event(
        "GAP2_ATTEMPT",
        candidate_id=candidate_id,
        outcome="FAILURE",
        attempt=attempts,
        threshold=threshold(),
        detail=detail,
    )
    pivot = attempts >= threshold() and candidate_id not in _exhausted
    next_entry = None
    if pivot:
        _exhausted.add(candidate_id)
        next_entry = next_candidate()
        note_event(
            "GAP2_PIVOT",
            candidate_id=candidate_id,
            outcome="ABANDON",
            attempts=attempts,
            threshold=threshold(),
            next_candidate=(next_entry or {}).get("candidate_id"),
            message=(
                f"GAP-2 threshold reached for {candidate_id} after {attempts} "
                "failed attempts; abandon it and pivot"
            ),
        )
    return {
        "candidate_id": candidate_id,
        "attempts": attempts,
        "threshold": threshold(),
        "pivot": pivot,
        "next_candidate": next_entry or next_candidate(),
    }


def guidance_text(outcome: dict[str, Any]) -> str:
    if not outcome.get("pivot"):
        return ""
    nxt = outcome.get("next_candidate") or {}
    label = nxt.get("title") or nxt.get("endpoint") or nxt.get("candidate_id") or "the next ranked candidate"
    return (
        f"GAP-2 PIVOT: candidate {outcome.get('candidate_id')} reached the failure "
        f"threshold ({outcome.get('attempts')}/{outcome.get('threshold')}). "
        f"Abandon this route now and pivot to {label}."
    )


def reset_state() -> None:
    global _announced
    _attempts.clear()
    _exhausted.clear()
    _completed.clear()
    _announced = False


__all__ = [
    "CONTROL_DIR_ENV",
    "DEFAULT_THRESHOLD",
    "GAP1_ENABLED_ENV",
    "GAP2_ENABLED_ENV",
    "QUEUE_ENV",
    "THRESHOLD_ENV",
    "candidate_for",
    "candidate_id_for",
    "control_dir",
    "gap1_instruction_block",
    "gap1_enabled",
    "gap2_enabled",
    "guidance_text",
    "load_queue",
    "next_candidate",
    "note_event",
    "queue_order",
    "record_outcome",
    "reset_state",
    "threshold",
]
