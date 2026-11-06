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
STATE_FILENAME = "gap_state.json"


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


class GapRunState:
    """Run-isolated state manager for GAP-1 queue processing and GAP-2 bounded pivots."""

    def __init__(self, directory: Path | str | None = None, *, threshold_override: int | None = None) -> None:
        self.directory: Path | None = Path(directory) if directory else None
        self._threshold_override: int | None = threshold_override
        self.attempts: dict[str, int] = {}
        self.exhausted: set[str] = set()
        self.completed: set[str] = set()
        self.announced: bool = False
        self.probe_outcomes: list[dict[str, Any]] = []
        self._load()

    def state_file(self) -> Path | None:
        if self.directory is not None:
            return self.directory / STATE_FILENAME
        return None

    def _load(self) -> None:
        sf = self.state_file()
        if sf is not None and sf.is_file():
            try:
                data = json.loads(sf.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.attempts = {str(k): int(v) for k, v in data.get("attempts", {}).items()}
                    self.exhausted = {str(x) for x in data.get("exhausted", [])}
                    self.completed = {str(x) for x in data.get("completed", [])}
                    self.announced = bool(data.get("announced", False))
                    self.probe_outcomes = list(data.get("probe_outcomes", []))
            except Exception:
                pass

    def save(self) -> None:
        sf = self.state_file()
        if sf is not None:
            try:
                sf.parent.mkdir(parents=True, exist_ok=True)
                data = {
                    "attempts": self.attempts,
                    "exhausted": sorted(self.exhausted),
                    "completed": sorted(self.completed),
                    "announced": self.announced,
                    "probe_outcomes": self.probe_outcomes,
                }
                sf.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except OSError:
                pass

    def reset(self) -> None:
        self.attempts.clear()
        self.exhausted.clear()
        self.completed.clear()
        self.announced = False
        self.probe_outcomes.clear()
        sf = self.state_file()
        if sf is not None and sf.is_file():
            try:
                sf.unlink()
            except OSError:
                pass

    def mark_exhausted(self, candidate_id: str) -> None:
        if candidate_id:
            self.exhausted.add(str(candidate_id))
            self.save()

    def mark_completed(self, candidate_id: str) -> None:
        if candidate_id:
            self.completed.add(str(candidate_id))
            self.save()

    def threshold(self) -> int:
        if self._threshold_override is not None:
            return max(1, self._threshold_override)
        return threshold()


_run_states: dict[str, GapRunState] = {}
_default_state: GapRunState = GapRunState(None)


def get_run_state(directory: Path | str | None = None) -> GapRunState:
    resolved_dir = Path(directory) if directory else control_dir()
    if resolved_dir is None:
        return _default_state
    resolved_key = str(resolved_dir.resolve())
    if resolved_key not in _run_states:
        _run_states[resolved_key] = GapRunState(resolved_dir)
    return _run_states[resolved_key]


def __getattr__(name: str) -> Any:
    """Backward compatibility for module-level state attributes."""
    st = get_run_state()
    if name == "_attempts":
        return st.attempts
    if name == "_exhausted":
        return st.exhausted
    if name == "_completed":
        return st.completed
    if name == "_announced":
        return st.announced
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def _queue_path(directory: Path | None = None) -> Path | None:
    if directory is not None:
        candidate_file = Path(directory) / QUEUE_FILENAME
        if candidate_file.is_file():
            return candidate_file
    explicit = os.environ.get(QUEUE_ENV, "").strip()
    if explicit:
        return Path(explicit)
    d = directory or control_dir()
    return d / QUEUE_FILENAME if d else None


def load_queue(directory: Path | None = None) -> list[dict[str, Any]]:
    path = _queue_path(directory)
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


def queue_order(directory: Path | None = None) -> tuple[list[str], list[str]]:
    path = _queue_path(directory)
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


def note_event(event: str, *, directory: Path | None = None, **fields: Any) -> dict[str, Any]:
    payload = {"timestamp": _utc_now(), "event": event, **fields}
    target_dir = directory or control_dir()
    if target_dir is not None:
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            with (target_dir / TRACE_FILENAME).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass
    return payload


def gap1_instruction_block(directory: Path | None = None, state: GapRunState | None = None) -> str:
    if not gap1_enabled():
        return ""
    st = state or get_run_state(directory)
    candidates = load_queue(directory or st.directory)
    if not candidates:
        return ""
    if not st.announced:
        original, ranked = queue_order(directory or st.directory)
        note_event(
            "GAP1_ROOT_TASK_INJECTED",
            original_order=original,
            ranked_order=ranked,
            ranking_changed=ranked != original,
            directory=directory or st.directory,
        )
        st.announced = True
        st.save()
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
            f"{st.threshold()}), abandon it and pivot to the next ranked candidate.",
            "Do not keep retrying an exhausted route.",
            "",
            "### Investigation & Outcome Recording Instructions:",
            "1. Work through the candidates in prioritized order.",
            "2. If you confirm a vulnerability: call `create_vulnerability_report` "
            "(include the candidate endpoint and title). This records a POSITIVE outcome in GAP-2 and marks the candidate complete.",
            "3. If an attack surface is verified clean, safe, or not vulnerable: call "
            "`record_coverage(surface=endpoint, risk_area=title, outcome='no_issue_found', evidence=...)`. "
            "This records a NEGATIVE outcome in GAP-2 and marks the candidate complete.",
            "4. If an initial probe is inconclusive or requires follow-up: call "
            "`record_coverage(surface=endpoint, risk_area=title, outcome='needs_follow_up', evidence=...)`. "
            f"If a candidate reaches {st.threshold()} inconclusive attempts, GAP-2 triggers an automatic PIVOT.",
            "5. When GAP-2 signals a PIVOT, abandon the current candidate immediately and proceed to the next ranked candidate.",
            "6. The completion gate requires all GAP-1 candidates to be investigated or ruled out before `finish_scan` can succeed.",
        ]
    )
    return "\n".join(lines)


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return cleaned[:80] or "candidate"


def candidate_for(title: str, endpoint: str, target: str, directory: Path | None = None) -> dict[str, Any] | None:
    candidates = load_queue(directory)
    if not candidates:
        return None
    endpoint_key = (endpoint or "").strip().lower()
    target_key = (target or "").strip().lower()
    title_key = (title or "").strip().lower()

    # 1. Exact or bracketed candidate_id matching
    for entry in candidates:
        cid = str(entry.get("candidate_id") or "").strip().lower()
        if not cid:
            continue
        if (
            cid == endpoint_key
            or cid == title_key
            or cid == target_key
            or f"[{cid}]" in title_key
            or f"[{cid}]" in endpoint_key
            or cid in title_key.split()
            or cid in endpoint_key.split()
        ):
            return entry

    # Helper: tokenize text into clean alpha-numeric words
    def _tokens(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", (text or "").lower()))

    # 2. Title token matching (Title is uniquely descriptive for each candidate)
    title_tokens = _tokens(title_key)
    if title_tokens:
        best_candidate = None
        best_score = 0
        for entry in candidates:
            entry_title = str(entry.get("title") or "").strip().lower()
            e_tokens = _tokens(entry_title)
            common = len(title_tokens & e_tokens)
            if common > best_score and common >= 2:
                best_score = common
                best_candidate = entry
            elif common == best_score and common >= 2 and best_candidate:
                e_ep = str(entry.get("endpoint") or "").strip().lower()
                b_ep = str(best_candidate.get("endpoint") or "").strip().lower()
                if endpoint_key and e_ep == endpoint_key and b_ep != endpoint_key:
                    best_candidate = entry
        if best_candidate:
            return best_candidate

    # 3. Non-root endpoint matching
    # NEVER match root slash "/" or empty string as a substring of other endpoints!
    if endpoint_key and endpoint_key != "/":
        for entry in candidates:
            entry_endpoint = str(entry.get("endpoint") or "").strip().lower()
            if entry_endpoint and entry_endpoint != "/":
                if endpoint_key == entry_endpoint or endpoint_key in entry_endpoint or entry_endpoint in endpoint_key:
                    return entry

    # 4. Exact endpoint match (when non-ambiguous)
    if endpoint_key:
        for entry in candidates:
            entry_endpoint = str(entry.get("endpoint") or "").strip().lower()
            if entry_endpoint == endpoint_key:
                return entry

    return None


def candidate_id_for(title: str, endpoint: str, target: str, directory: Path | None = None) -> str:
    entry = candidate_for(title, endpoint, target, directory=directory)
    if entry is not None and entry.get("candidate_id"):
        return str(entry["candidate_id"])
    raw = endpoint or title or target or "unknown"
    return f"strix-{_slug(raw)}"


def next_candidate(directory: Path | None = None, state: GapRunState | None = None) -> dict[str, Any] | None:
    st = state or get_run_state(directory)
    for entry in load_queue(directory or st.directory):
        candidate_id = str(entry.get("candidate_id") or "")
        if candidate_id and candidate_id not in st.exhausted and candidate_id not in st.completed:
            return entry
    return None


def record_outcome(
    *,
    title: str = "",
    candidate_id: str | None = None,
    endpoint: str = "",
    target: str = "",
    success: bool = False,
    detail: str = "",
    report_id: str = "",
    directory: Path | None = None,
    state: GapRunState | None = None,
    is_tool_error: bool = False,
    probe_status: str | None = None,
    source: str = "",
) -> dict[str, Any]:
    """Record one candidate outcome and return GAP-2 guidance.

    Success or confirmed negative probe completes the candidate. Failures
    increment its attempt count; when the threshold is reached the candidate is
    abandoned and the next ranked candidate is returned so the caller can steer
    the agent. Tool errors are recorded without being treated as safety proof.
    """
    st = state or get_run_state(directory)
    cid = candidate_id or candidate_id_for(title, endpoint, target, directory=directory or st.directory)
    candidate_id = cid

    # Determine semantic status
    if probe_status is not None:
        status_norm = probe_status.lower().strip()
    elif is_tool_error:
        status_norm = "error"
    elif success:
        status_norm = "positive"
    else:
        status_norm = "inconclusive"

    # Avoid duplicate completed recording
    if candidate_id in st.completed and status_norm in ("positive", "negative"):
        return {
            "candidate_id": candidate_id,
            "attempts": max(1, st.attempts.get(candidate_id, 1)),
            "threshold": st.threshold(),
            "pivot": False,
            "next_candidate": next_candidate(directory=st.directory, state=st),
            "status": status_norm,
            "duplicate": True,
        }

    # 1. Confirmed Positive Finding (Vulnerability confirmed)
    if status_norm == "positive":
        attempts = max(1, st.attempts.get(candidate_id, 0))
        st.attempts[candidate_id] = attempts
        st.completed.add(candidate_id)
        note_event(
            "GAP2_SUCCESS",
            candidate_id=candidate_id,
            outcome="SUCCESS",
            report_id=report_id,
            detail=detail,
            directory=st.directory,
        )
        st.probe_outcomes.append({
            "candidate_id": candidate_id,
            "status": "positive",
            "detail": detail,
            "report_id": report_id,
            "timestamp": _utc_now(),
        })
        nxt = next_candidate(directory=st.directory, state=st)
        st.save()
        return {
            "candidate_id": candidate_id,
            "attempts": attempts,
            "threshold": st.threshold(),
            "pivot": False,
            "next_candidate": nxt,
            "status": "positive",
        }

    # 2. Confirmed Negative Result (Clean / Ruled out / No issue found)
    if status_norm == "negative":
        attempts = max(1, st.attempts.get(candidate_id, 0))
        st.attempts[candidate_id] = attempts
        st.completed.add(candidate_id)
        note_event(
            "GAP2_NEGATIVE_CONFIRMED",
            candidate_id=candidate_id,
            outcome="NEGATIVE",
            detail=detail,
            directory=st.directory,
        )
        st.probe_outcomes.append({
            "candidate_id": candidate_id,
            "status": "negative",
            "detail": detail,
            "timestamp": _utc_now(),
        })
        nxt = next_candidate(directory=st.directory, state=st)
        st.save()
        return {
            "candidate_id": candidate_id,
            "attempts": attempts,
            "threshold": st.threshold(),
            "pivot": False,
            "next_candidate": nxt,
            "status": "negative",
        }

    # 3. Tool Execution Error (Exception, syntax, parameter error)
    # Does NOT mark candidate safe and does NOT increment towards failure exhaustion
    if status_norm == "error":
        note_event(
            "GAP2_TOOL_ERROR",
            candidate_id=candidate_id,
            outcome="ERROR",
            detail=detail,
            directory=st.directory,
        )
        st.probe_outcomes.append({
            "candidate_id": candidate_id,
            "status": "error",
            "detail": detail,
            "timestamp": _utc_now(),
        })
        st.save()
        return {
            "candidate_id": candidate_id,
            "attempts": st.attempts.get(candidate_id, 0),
            "threshold": st.threshold(),
            "pivot": False,
            "next_candidate": next_candidate(directory=st.directory, state=st),
            "status": "error",
        }

    # 4. Inconclusive Probe / Failed Verification Attempt
    # Check for rapid duplicate inconclusive calls
    if st.probe_outcomes:
        last = st.probe_outcomes[-1]
        if last.get("candidate_id") == candidate_id and last.get("status") == "inconclusive" and last.get("detail") == detail:
            attempts = st.attempts.get(candidate_id, 1)
            pivot = attempts >= st.threshold() and candidate_id not in st.exhausted
            return {
                "candidate_id": candidate_id,
                "attempts": attempts,
                "threshold": st.threshold(),
                "pivot": pivot,
                "next_candidate": next_candidate(directory=st.directory, state=st),
                "status": "inconclusive",
                "duplicate": True,
            }

    attempts = st.attempts.get(candidate_id, 0) + 1
    st.attempts[candidate_id] = attempts
    note_event(
        "GAP2_ATTEMPT",
        candidate_id=candidate_id,
        outcome="FAILURE",
        attempt=attempts,
        threshold=st.threshold(),
        detail=detail,
        directory=st.directory,
    )
    pivot = attempts >= st.threshold() and candidate_id not in st.exhausted
    next_entry = None
    if pivot:
        st.exhausted.add(candidate_id)
        next_entry = next_candidate(directory=st.directory, state=st)
        note_event(
            "GAP2_PIVOT",
            candidate_id=candidate_id,
            outcome="ABANDON",
            attempts=attempts,
            threshold=st.threshold(),
            next_candidate=(next_entry or {}).get("candidate_id"),
            message=(
                f"GAP-2 threshold reached for {candidate_id} after {attempts} "
                "failed attempts; abandon it and pivot"
            ),
            directory=st.directory,
        )
    st.probe_outcomes.append({
        "candidate_id": candidate_id,
        "status": "inconclusive",
        "attempt": attempts,
        "pivot": pivot,
        "detail": detail,
        "timestamp": _utc_now(),
    })
    st.save()
    return {
        "candidate_id": candidate_id,
        "attempts": attempts,
        "threshold": st.threshold(),
        "pivot": pivot,
        "next_candidate": next_entry or next_candidate(directory=st.directory, state=st),
        "status": "inconclusive",
    }


def record_probe_result(
    *,
    title: str,
    endpoint: str = "",
    target: str = "",
    outcome: str,
    detail: str = "",
    report_id: str = "",
    directory: Path | None = None,
    state: GapRunState | None = None,
) -> dict[str, Any]:
    """Helper to record arbitrary probe results into GAP-2."""
    norm = outcome.lower().strip()
    is_err = norm == "error"
    succ = norm in ("positive", "success")
    return record_outcome(
        title=title,
        endpoint=endpoint,
        target=target,
        success=succ,
        detail=detail,
        report_id=report_id,
        directory=directory,
        state=state,
        is_tool_error=is_err,
        probe_status=norm,
    )


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


def reset_state(directory: Path | str | None = None) -> None:
    if directory is not None:
        resolved_key = str(Path(directory).resolve())
        if resolved_key in _run_states:
            _run_states[resolved_key].reset()
            del _run_states[resolved_key]
    else:
        _default_state.reset()
        for state in list(_run_states.values()):
            state.reset()
        _run_states.clear()


__all__ = [
    "CONTROL_DIR_ENV",
    "DEFAULT_THRESHOLD",
    "GAP1_ENABLED_ENV",
    "GAP2_ENABLED_ENV",
    "GapRunState",
    "QUEUE_ENV",
    "QUEUE_FILENAME",
    "STATE_FILENAME",
    "THRESHOLD_ENV",
    "TRACE_FILENAME",
    "candidate_for",
    "candidate_id_for",
    "control_dir",
    "gap1_instruction_block",
    "gap1_enabled",
    "gap2_enabled",
    "get_run_state",
    "guidance_text",
    "load_queue",
    "next_candidate",
    "note_event",
    "queue_order",
    "record_outcome",
    "record_probe_result",
    "reset_state",
    "threshold",
]
