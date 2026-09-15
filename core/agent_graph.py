"""LangGraph state machine + dynamic pivot (Phase 2, Tasks 2.1-2.3).

Solves the Type-B planning/state-management failure identified by Deng et al.
(2025): the agent tracks per-vulnerability attempt counters and *pivots* to the
next target after N failed attempts instead of looping forever — the exact
weakness in the original prototype (which only ever returned False).

The graph:  assess -> execute -> (conditional) -> execute | pivot -> assess ...
with the path ordered by priority_score (EPSS x usability), so high-viability
routes are tried first and dead-ends are abandoned deterministically.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional, TypedDict

sys.path.append(str(Path(__file__).resolve().parent.parent))

from langgraph.graph import END, StateGraph

from core.exploit_assessor import assess_exploit_quality
from core.executor import Executor
from core.schemas import (
    AgentStatus,
    ExecutionOutcome,
    Finding,
    UsabilityRank,
    finding_from_dict,
    findings_from_state,
)


class AgentState(TypedDict):
    target: str
    findings: List[Finding]
    current_index: int
    current_cve: str
    exploit_rank: str
    attempt_count: int
    max_attempts: int
    status: str
    provider: str
    mode: str                       # "simulation" | "real"
    logs: List[str]
    results: List[dict]             # per-finding execution outcomes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_findings(raw: List[dict]) -> List[Finding]:
    return [finding_from_dict(d) for d in raw]


def rank_findings(findings: List[Finding]) -> List[Finding]:
    """Order by priority (EPSS x usability). Assessment happens first, so
    usability_rank is filled in during the run; we sort on each entry point."""
    return sorted(findings, key=lambda f: f.priority_score(), reverse=True)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
def assess_node(state: AgentState) -> AgentState:
    f = state["findings"][state["current_index"]]
    cve = f.cve
    state["current_cve"] = cve
    state["logs"].append(f"[Assessor] Grading PoC usability for {cve} via {state['provider'].upper()}...")
    try:
        a = assess_exploit_quality(cve, provider=state["provider"])
        f.usability_rank = UsabilityRank(a.usability_rank.value)
        f.assessed = True
        state["exploit_rank"] = a.usability_rank.value
        state["logs"].append(
            f"[Assessor] {cve} -> {a.usability_rank.value} "
            f"(complexity={a.complexity_score}, prereq_met={a.prerequisites_met})"
        )
    except Exception as e:
        f.usability_rank = UsabilityRank.MEDIUM
        state["exploit_rank"] = "MEDIUM"
        state["logs"].append(f"[Assessor] Fallback MEDIUM for {cve} ({e})")
    state["status"] = AgentStatus.TESTING.value
    return state


def execute_node(state: AgentState) -> AgentState:
    f = state["findings"][state["current_index"]]
    executor = Executor(mode=state.get("mode", "simulation"))
    result = executor.execute(f, state["target"])
    state["attempt_count"] += 1

    f.executed = True
    f.execution_outcome = result.outcome

    if result.outcome == ExecutionOutcome.SUCCESS:
        state["status"] = AgentStatus.SUCCESS.value
        state["logs"].append(
            f"[Executor] Attempt {state['attempt_count']} -> SUCCESS on {f.cve}"
        )
        state["results"].append(result.model_dump(mode="json"))
        return state

    state["logs"].append(
        f"[Executor] Attempt {state['attempt_count']}/{state['max_attempts']} "
        f"on {f.cve} -> {result.outcome.value}"
    )
    state["results"].append(result.model_dump(mode="json"))
    return state


def pivot_node(state: AgentState) -> AgentState:
    last = state["results"][-1] if state["results"] else {}
    last_outcome = last.get("outcome")
    if last_outcome == ExecutionOutcome.SUCCESS.value:
        state["logs"].append(
            f"[Advance] {state['current_cve']} validated. Moving to next target."
        )
    else:
        state["logs"].append(
            f"[Pivot] Threshold reached for {state['current_cve']}. Abandoning route."
        )
    state["current_index"] += 1
    if state["current_index"] < len(state["findings"]):
        # Clean context between pivots (per spec 2.2) — reset attempt counter.
        next_cve = state["findings"][state["current_index"]].cve
        state["attempt_count"] = 0
        state["status"] = AgentStatus.ASSESSING.value
        state["logs"].append(f"[Pivot] Re-directed to {next_cve}")
    else:
        state["status"] = AgentStatus.COMPLETED.value
        state["logs"].append("[Pivot] All targets processed. Workflow complete.")
    return state


def evaluate_decision(state: AgentState) -> str:
    if state["status"] == AgentStatus.COMPLETED.value:
        return END
    # A validated vulnerability -> advance and assess the next one (full coverage)
    if state["status"] == AgentStatus.SUCCESS.value:
        return "pivot"
    if state["attempt_count"] >= state["max_attempts"]:
        return "pivot"
    return "execute"


def build_vapt_graph(entry: str = "assess"):
    """Compile the graph. `entry` selects the start node so a resumed run can
    re-enter mid-workflow (checkpoint resume) instead of always at 'assess'."""
    valid_entries = ("assess", "execute", "pivot")
    if entry not in valid_entries:
        raise ValueError(f"Invalid entry node {entry!r}; expected one of {valid_entries}")
    g = StateGraph(AgentState)
    g.add_node("assess", assess_node)
    g.add_node("execute", execute_node)
    g.add_node("pivot", pivot_node)
    g.set_entry_point(entry)
    g.add_edge("assess", "execute")
    g.add_conditional_edges(
        "execute", evaluate_decision,
        {"execute": "execute", "pivot": "pivot", END: END},
    )
    g.add_conditional_edges(
        "pivot",
        lambda s: END if s["status"] == AgentStatus.COMPLETED.value else "assess",
        {"assess": "assess", END: END},
    )
    return g.compile()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def initial_agent_state(target: str, findings: List[dict], provider: str = "ollama",
                        max_attempts: int = 2, mode: str = "simulation") -> AgentState:
    """Build the starting AgentState (findings ranked by priority_score)."""
    fs = rank_findings(_to_findings(findings))
    return {
        "target": target,
        "findings": fs,
        "current_index": 0,
        "current_cve": fs[0].cve if fs else "NONE",
        "exploit_rank": "PENDING",
        "attempt_count": 0,
        "max_attempts": max_attempts,
        "status": AgentStatus.ASSESSING.value,
        "provider": provider,
        "mode": mode,
        "logs": [f"Agent initialized: {len(fs)} findings, pivot_threshold={max_attempts}, mode={mode}"],
        "results": [],
    }


def run_agent(target: str, findings: List[dict], provider: str = "ollama",
              max_attempts: int = 2, mode: str = "simulation") -> AgentState:
    state = initial_agent_state(target, findings, provider=provider,
                                max_attempts=max_attempts, mode=mode)
    app = build_vapt_graph()
    return app.invoke(state)


# ---------------------------------------------------------------------------
# Checkpointing (T-CHECKPOINT): serialize / deserialize / resume
# ---------------------------------------------------------------------------
# The graph is deterministic given (state, labels), so persisting the full
# AgentState is enough to continue an interrupted run exactly where it stopped.
CHECKPOINT_VERSION = 1

# Which node a resumed run must enter on, derived from the saved status.
# TESTING means the current CVE was already assessed but not yet exhausted
# (or was mid-execution), so we go straight back to execute; SUCCESS means the
# CVE validated and only the advance step remains.
_RESUME_ENTRY = {
    AgentStatus.ASSESSING.value: "assess",
    AgentStatus.TESTING.value: "execute",
    AgentStatus.SUCCESS.value: "pivot",
}


def _state_to_jsonable(state: AgentState) -> dict:
    """Deep-copy an AgentState into plain JSON-safe structures.

    Only Finding objects need conversion (pydantic models holding enums);
    everything else in the state is already JSON-native.
    """
    data = dict(state)
    data["findings"] = [
        f.model_dump(mode="json") if isinstance(f, Finding) else f
        for f in state.get("findings", [])
    ]
    return data


def save_checkpoint(state: AgentState, path: str) -> str:
    """Serialize AgentState to JSON. Call on completion OR at any interrupt.

    Returns the path written (so callers can log/hand it to resume_agent).
    """
    payload = {
        "version": CHECKPOINT_VERSION,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "state": _state_to_jsonable(state),
    }
    path = str(path)
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path


def load_checkpoint(path: str) -> AgentState:
    """Load a checkpoint file back into a runnable AgentState.

    Finding dicts are rebuilt into Finding models (enums restored by pydantic).
    """
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    version = payload.get("version")
    if version != CHECKPOINT_VERSION:
        raise ValueError(
            f"Checkpoint {path!r} has unsupported version {version!r} "
            f"(expected {CHECKPOINT_VERSION})."
        )
    raw = payload["state"]
    raw["findings"] = findings_from_state(raw.get("findings", []))
    return raw


def resume_entry_point(state: AgentState) -> Optional[str]:
    """Node the graph must re-enter on for this saved state, or None when the
    run is already complete (index past the last finding / COMPLETED)."""
    idx = state.get("current_index", 0)
    if idx >= len(state.get("findings", []) or []) or \
            state.get("status") == AgentStatus.COMPLETED.value:
        return None
    return _RESUME_ENTRY.get(state.get("status"), "assess")


def resume_agent(checkpoint_path: str) -> AgentState:
    """Load a saved state and re-invoke the graph from current_index.

    Entry node is chosen from the persisted status so no step is repeated
    (no double-execution of a validated CVE, no wasted re-assessment of one
    that is mid-attempt). A COMPLETED checkpoint returns unchanged.
    """
    state = load_checkpoint(checkpoint_path)
    entry = resume_entry_point(state)
    logs = state.setdefault("logs", [])
    if entry is None:
        logs.append("[Checkpoint] Run already complete; nothing to resume.")
        return state
    logs.append(
        f"[Checkpoint] Resuming from '{entry}' at index {state['current_index']} "
        f"({state['current_cve']})"
    )
    app = build_vapt_graph(entry=entry)
    return app.invoke(state)


if __name__ == "__main__":
    from core.schemas import finding_from_dict
    from vapt_platform.scanners import get_scanner_registry

    def _to_core_finding(cf):
        meta = cf.metadata or {}
        return finding_from_dict({
            "cve": meta.get("cve") or "UNKNOWN-CVE",
            "port": cf.port or None,
            "service": meta.get("service"),
            "description": cf.description,
            "epss_score": meta.get("epss_score", 0.0),
        })

    findings = [f.model_dump() for f in map(
        _to_core_finding, get_scanner_registry().parse("data/sample_scan.json")
    )]
    final = run_agent("127.0.0.1", findings)
    print("\n--- Execution Log ---")
    for log in final["logs"]:
        print(log)
    print("\n--- Results ---")
    for r in final["results"]:
        print(r["cve"], r["outcome"], "reqs=", r["request_count"])
