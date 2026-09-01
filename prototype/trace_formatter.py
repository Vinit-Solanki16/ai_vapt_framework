"""Convert the engine's actual state into a human-readable decision trace.

Each displayed event is derived from the real engine state["logs"] and
state["results"]. No invented events.

Display format:
  [ASSESS]   Candidate: <id>
  [EXECUTE]  Attempt: <n>/<max>  Outcome: <outcome>
  [PIVOT]    Threshold reached / Redirected to <id>
  [COMPLETED]
"""

from typing import List, Tuple, Optional

from decision_engine.core.schemas import EngineStatus, Outcome


def parse_engine_log(log: str) -> Tuple[str, dict]:
    """Parse a single engine log entry into (phase, fields).

    Returns a phase label and a dict of derived fields.
    Unknown log formats return ('UNKNOWN', {}).
    """
    log = log.strip()

    if log.startswith("[Assessor]"):
        # e.g. "[Assessor] error ValueError"
        return ("ASSESS", {"detail": log[len("[Assessor]"):].strip()})

    if log.startswith("[Executor]"):
        rest = log[len("[Executor]"):].strip()
        if "-> SUCCESS" in rest:
            # e.g. "[Executor] Attempt 1 -> SUCCESS on DEMO-DEAD-END"
            return _parse_executor_success(rest)
        else:
            # e.g. "[Executor] Attempt 1/2 on DEMO-DEAD-END -> FAIL_TIMEOUT"
            return _parse_executor_attempt(rest)

    if log.startswith("[Pivot]"):
        rest = log[len("[Pivot]"):].strip()
        if "Abandoning" in rest:
            return ("PIVOT_ABANDON", {"reason": rest})
        if "Redirected" in rest:
            parts = rest.split("to", 1)
            return ("PIVOT_REDIRECT", {"next_id": parts[1].strip() if len(parts) > 1 else ""})
        if "All candidates" in rest:
            return ("PIVOT_COMPLETE", {"reason": rest})
        return ("PIVOT", {"reason": rest})

    if log.startswith("[Advance]"):
        # e.g. "[Advance] DEMO-SUCCESS-A validated. Next candidate."
        rest = log[len("[Advance]"):].strip()
        return ("ADVANCE", {"detail": rest})

    if log.startswith("Engine initialized"):
        return ("INIT", {"detail": log})

    return ("UNKNOWN", {})


def _parse_executor_success(rest: str) -> Tuple[str, dict]:
    """Parse a SUCCESS executor log."""
    # "Attempt 1 -> SUCCESS on DEMO-SUCCESS-A"
    parts = rest.split("->")
    attempt_part = parts[0].replace("Attempt", "").strip()
    id_part = parts[1].replace("SUCCESS", "").replace("on", "").strip()
    return ("EXECUTE_SUCCESS", {"attempt": attempt_part, "candidate": id_part})


def _parse_executor_attempt(rest: str) -> Tuple[str, dict]:
    """Parse a FAIL executor log."""
    # "Attempt 1/2 on DEMO-DEAD-END -> FAIL_TIMEOUT"
    parts = rest.split("->")
    attempt_part = parts[0].replace("Attempt", "").strip()  # "1/2 on DEMO-DEAD-END"
    outcome_part = parts[1].strip()

    # Extract candidate id from after "on"
    if " on " in attempt_part:
        before_on, after_on = attempt_part.split(" on ", 1)
        id_part = after_on.strip()
        attempt_num_raw = before_on.strip()
    elif "on" in attempt_part:
        before_on, after_on = attempt_part.split("on", 1)
        id_part = after_on.strip()
        attempt_num_raw = before_on.strip()
    else:
        id_part = ""
        attempt_num_raw = attempt_part

    # Extract attempt number from "1/2" -> ["1","2"]
    if "/" in attempt_num_raw:
        attempt_num, max_part = attempt_num_raw.split("/", 1)
        attempt_num = attempt_num.strip()
        max_part = max_part.strip()
    else:
        attempt_num = attempt_num_raw.strip()
        max_part = ""

    return (
        "EXECUTE_FAIL",
        {
            "attempt": attempt_num,
            "max_attempts": max_part,
            "candidate": id_part,
            "outcome": outcome_part,
        },
    )


def format_phase(phase: str, fields: dict) -> str:
    """Format a single parsed phase into a human-readable line."""
    if phase == "INIT":
        return f"  [INIT]   {fields.get('detail', '')}"

    if phase == "ASSESS":
        cid = fields.get("candidate", fields.get("detail", ""))
        return f"  [ASSESS] Candidate: {cid}"

    if phase == "EXECUTE_SUCCESS":
        return (
            f"  [EXECUTE] Attempt: {fields.get('attempt', '?')}/{fields.get('max_attempts', '?')}"
            f"  Outcome: SUCCESS  Candidate: {fields.get('candidate', '?')}"
        )

    if phase == "EXECUTE_FAIL":
        max_a = fields.get("max_attempts", "?")
        return (
            f"  [EXECUTE] Attempt: {fields.get('attempt', '?')}/{max_a}"
            f"  Outcome: {fields.get('outcome', 'UNKNOWN')}"
            f"  Candidate: {fields.get('candidate', '?')}"
        )

    if phase == "PIVOT_ABANDON":
        return f"  [PIVOT]   {fields.get('reason', 'Threshold reached. Candidate abandoned.')}"

    if phase == "PIVOT_REDIRECT":
        return f"  [PIVOT]   Redirected to: {fields.get('next_id', '?')}"

    if phase == "PIVOT_COMPLETE":
        return f"  [PIVOT]   {fields.get('reason', 'All candidates processed.')}"

    if phase == "ADVANCE":
        return f"  [ADVANCE] {fields.get('detail', '')}"

    if phase == "UNKNOWN":
        return f"  [LOG]     {fields.get('detail', '')}"

    return f"  [{phase}]   {fields}"


def format_engine_trace(state: dict) -> str:
    """Format an engine state into a mentor-readable decision trace.

    Each line is derived from the engine's actual logs and results.
    """
    lines = []
    logs = state.get("logs", [])
    state_max_attempts = state.get("max_attempts", "?")

    # Track current phase context for better formatting
    current_candidate: Optional[str] = None
    in_assess = False

    for log in logs:
        phase, fields = parse_engine_log(log)

        # For SUCCESS attempts, the log doesn't contain max_attempts;
        # fill in from the engine state.
        if phase == "EXECUTE_SUCCESS" and not fields.get("max_attempts"):
            fields["max_attempts"] = str(state_max_attempts)

        # Keep candidate context
        if phase == "ASSESS":
            in_assess = True
            current_candidate = fields.get("candidate", fields.get("detail", ""))
            lines.append(format_phase(phase, fields))
        elif phase in ("EXECUTE_SUCCESS", "EXECUTE_FAIL"):
            in_assess = False
            current_candidate = fields.get("candidate", current_candidate)
            lines.append(format_phase(phase, fields))
        elif phase in ("PIVOT", "PIVOT_ABANDON", "PIVOT_REDIRECT", "PIVOT_COMPLETE", "ADVANCE"):
            lines.append(format_phase(phase, fields))
        elif phase == "INIT":
            lines.append(format_phase(phase, fields))
        else:
            lines.append(format_phase("UNKNOWN", {"detail": log}))

    # Append terminal status
    status = state.get("status", "UNKNOWN")
    if status == EngineStatus.COMPLETED.value:
        lines.append("")
        lines.append("  [COMPLETED]  All candidates processed. Workflow complete.")
    elif status == EngineStatus.SUCCESS.value:
        lines.append("")
        lines.append("  [COMPLETED]  SUCCESS — candidate validated.")

    return "\n".join(lines)


def format_candidate_ranking(state: dict) -> str:
    """Format the ranked candidate list from engine state."""
    lines = []
    candidates = state.get("candidates", [])
    if not candidates:
        return "  (no candidates)"

    for i, c in enumerate(candidates):
        cid = getattr(c, "id", "?")
        prob = getattr(c, "probability", 0.0)
        qr = getattr(c, "quality_rank", None)
        qr_str = qr.value if qr else "PENDING"
        score = getattr(c, "priority_score", lambda: 0.0)()
        if callable(score):
            score = score()
        score_str = f"{score:.4f}" if isinstance(score, float) else str(score)

        lines.append(
            f"  {i + 1}. {cid:<25}  prob={prob:.4f}  quality={qr_str:<8}  score={score_str}"
        )

    return "\n".join(lines)


def format_execution_results(state: dict) -> str:
    """Format the execution results from engine state."""
    results = state.get("results", [])
    if not results:
        return "  (no execution results)"

    lines = []
    for r in results:
        cid = r.get("candidate_id", "?")
        outcome = r.get("outcome", "?")
        detail = r.get("detail", "")
        lines.append(f"  {cid:<25}  Outcome: {outcome}  ({detail})")

    return "\n".join(lines)