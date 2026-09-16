"""Domain-independent decision & pivot engine (LangGraph).

This is a faithful COPY + REFACTOR of core/agent_graph.py, stripped of every
VAPT/CVE-specific detail. The engine knows only about:
  - ActionCandidate (a task to attempt, with a probability + pre-execution quality)
  - an assessor (Gap-1, fills quality_rank)
  - an executor (resolves an Outcome)
It tracks per-candidate attempt counts, pivots away from a failing candidate
after ``max_attempts`` (Gap-2), advances on success, and terminates boundedly.

The VAPT domain is attached via adapters/vapt_adapter.py, so this file is the
reusable "Stage 1" core you described: a general autonomous decision engine.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from decision_engine.core.assessor import assess_candidates, deterministic_assessor
from decision_engine.core.executor import Executor
from decision_engine.core.schemas import (
    ActionCandidate,
    EngineStatus,
    Outcome,
    candidate_from_dict,
    candidates_from_state,
)

ENGINE_VERSION = 1


class EngineState(TypedDict):
    candidates: List[ActionCandidate]
    current_index: int
    current_id: str
    quality_rank: str
    attempt_count: int
    max_attempts: int
    status: str
    mode: str
    logs: List[str]
    results: List[dict]


def rank_candidates(candidates: List[ActionCandidate]) -> List[ActionCandidate]:
    """Order by priority_score (probability x quality). Gap-1 fills quality first."""
    return sorted(candidates, key=lambda c: c.priority_score(), reverse=True)


def _assess_node(state: EngineState, assess_fn) -> EngineState:
    c = state["candidates"][state["current_index"]]
    state["current_id"] = c.id
    try:
        assess_candidates([c], assess_fn=assess_fn)
        state["quality_rank"] = c.quality_rank.value if c.quality_rank else "NONE"
    except Exception as e:  # pragma: no cover - defensive
        c.quality_rank = None
        state["quality_rank"] = "NONE"
        state["logs"].append(f"[Assessor] error {e}")
    state["status"] = EngineStatus.TESTING.value
    return state


def _execute_node(state: EngineState, executor) -> EngineState:
    c = state["candidates"][state["current_index"]]
    result = executor.execute(c)
    state["attempt_count"] += 1
    c.attempted = True
    c.execution_outcome = result.outcome
    if result.outcome == Outcome.SUCCESS:
        state["status"] = EngineStatus.SUCCESS.value
        state["logs"].append(
            f"[Executor] Attempt {state['attempt_count']} -> SUCCESS on {c.id}"
        )
        state["results"].append(result.model_dump(mode="json"))
        return state
    state["logs"].append(
        f"[Executor] Attempt {state['attempt_count']}/{state['max_attempts']} "
        f"on {c.id} -> {result.outcome.value}"
    )
    state["results"].append(result.model_dump(mode="json"))
    return state


def _pivot_node(state: EngineState) -> EngineState:
    last = state["results"][-1] if state["results"] else {}
    if last.get("outcome") == Outcome.SUCCESS.value:
        state["logs"].append(f"[Advance] {state['current_id']} validated. Next candidate.")
    else:
        state["logs"].append(f"[Pivot] Threshold reached for {state['current_id']}. Abandoning route.")
    state["current_index"] += 1
    if state["current_index"] < len(state["candidates"]):
        state["attempt_count"] = 0  # reset per-candidate counter (Gap-2)
        state["status"] = EngineStatus.ASSESSING.value
        state["logs"].append(f"[Pivot] Redirected to {state['candidates'][state['current_index']].id}")
    else:
        state["status"] = EngineStatus.COMPLETED.value
        state["logs"].append("[Pivot] All candidates processed. Workflow complete.")
    return state


def _evaluate(state: EngineState) -> str:
    if state["status"] == EngineStatus.COMPLETED.value:
        return END
    if state["status"] == EngineStatus.SUCCESS.value:
        return "pivot"
    if state["attempt_count"] >= state["max_attempts"]:
        return "pivot"
    return "execute"


def build_graph(entry: str = "assess", assess_fn=None, executor=None):
    valid = ("assess", "execute", "pivot")
    if entry not in valid:
        raise ValueError(f"Invalid entry node {entry!r}; expected one of {valid}")
    g = StateGraph(EngineState)
    g.add_node("assess", lambda s: _assess_node(s, assess_fn))
    g.add_node("execute", lambda s: _execute_node(s, executor))
    g.add_node("pivot", _pivot_node)
    g.set_entry_point(entry)
    g.add_edge("assess", "execute")
    g.add_conditional_edges("execute", _evaluate, {"execute": "execute", "pivot": "pivot", END: END})
    g.add_conditional_edges("pivot", lambda s: END if s["status"] == EngineStatus.COMPLETED.value else "assess",
                            {"assess": "assess", END: END})
    return g.compile()


def initial_state(candidates: List[dict], max_attempts: int = 2, mode: str = "simulation", assess_fn=None) -> dict:
    # FIX: Assess ALL candidates BEFORE ranking so quality_rank affects ordering
    # (GAP-1 research contribution requires assessment to influence candidate priority)
    raw_candidates = [candidate_from_dict(d) for d in candidates]
    if assess_fn:
        assess_candidates(raw_candidates, assess_fn=assess_fn)
    cs = rank_candidates(raw_candidates)
    return {
        "candidates": cs,
        "current_index": 0,
        "current_id": cs[0].id if cs else "NONE",
        "quality_rank": "PENDING",
        "attempt_count": 0,
        "max_attempts": max_attempts,
        "status": EngineStatus.ASSESSING.value,
        "mode": mode,
        "logs": [f"Engine initialized: {len(cs)} candidates, pivot_threshold={max_attempts}, mode={mode}"],
        "results": [],
    }


def run_engine(candidates: List[dict], assess_fn=None, executor=None,
               max_attempts: int = 2, mode: str = "simulation") -> dict:
    state = initial_state(candidates, max_attempts=max_attempts, mode=mode, assess_fn=assess_fn)
    # Guard: empty candidates -> return COMPLETED immediately
    if not state["candidates"]:
        state["status"] = EngineStatus.COMPLETED.value
        state["logs"].append("[Engine] No candidates provided. Workflow complete.")
        return state
    app = build_graph(assess_fn=assess_fn, executor=executor)
    final = app.invoke(state)
    # promote validated status for the router
    if final["results"] and final["results"][-1].get("outcome") == Outcome.SUCCESS.value:
        final["status"] = EngineStatus.SUCCESS.value
    return final


# ---------------------------------------------------------------------------
# Checkpointing (copy of T-CHECKPOINT behaviour, domain-independent)
# ---------------------------------------------------------------------------
def _state_to_jsonable(state: dict) -> dict:
    data = dict(state)
    data["candidates"] = [
        c.model_dump(mode="json") if isinstance(c, ActionCandidate) else c
        for c in state.get("candidates", [])
    ]
    return data


def save_checkpoint(state: dict, path: str) -> str:
    payload = {"version": ENGINE_VERSION, "saved_at": datetime.now(timezone.utc).isoformat(),
               "state": _state_to_jsonable(state)}
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path


def load_checkpoint(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    if payload.get("version") != ENGINE_VERSION:
        raise ValueError(f"Unsupported checkpoint version {payload.get('version')}")
    raw = payload["state"]
    raw["candidates"] = candidates_from_state(raw.get("candidates", []))
    return raw
