"""Shared helpers for tests that mock a *genuinely executed* Strix subprocess.

Older worker tests stub the CLI subprocess with only a "Starting turn" line.
Since the worker refuses to report success without model reasoning and real
security-tool execution, those fixtures now use this helper to emit the log
lines a real run produces. Tests that verify failure on missing evidence must
NOT use it.
"""

from __future__ import annotations

from typing import Any

# One model call plus one real security tool call and a bookkeeping call.
REAL_EXECUTION_LOG_LINES = [
    "Calling LLM model=test-model provider=cloud_hosted",
    "Invoking tool http_request",
    "Invoking tool record_coverage",
    "Starting turn 1, current_agent=Root Agent",
]


def with_real_execution(prefix: list[str] | None = None) -> list[str]:
    """Return mock stdout lines representing a genuinely executed scan."""
    return list(prefix or []) + REAL_EXECUTION_LOG_LINES


def attach_real_execution(mock_proc: Any, prefix: list[str] | None = None) -> Any:
    """Mutate a MagicMock subprocess to emit genuine execution log lines."""
    mock_proc.stdout.readline.side_effect = with_real_execution(prefix)
    return mock_proc
