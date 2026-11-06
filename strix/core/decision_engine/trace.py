"""Chronological decision trace logger for GAP-2 auditing."""

from __future__ import annotations

from datetime import datetime


class DecisionTraceLogger:
    """Records human-readable and structured decision trace events."""

    def __init__(self) -> None:
        self.trace_lines: list[str] = []

    def log(self, prefix: str, message: str) -> None:
        now = datetime.now().astimezone().strftime("%H:%M:%S")
        entry = f"[{now}] [{prefix}] {message}"
        self.trace_lines.append(entry)

    def get_lines(self) -> list[str]:
        return list(self.trace_lines)
