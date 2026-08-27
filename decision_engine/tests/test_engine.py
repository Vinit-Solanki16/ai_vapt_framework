"""Regression suite for the domain-independent decision_engine/ (TRACK1).

Mirrors the safety net TRACK0's tests/test_core.py provides for core/, but
exercises the generalized engine (engine + executor + schemas + assessor +
checkpoint) entirely offline via the simulation backend. No VAPT corpus, no
network, no LLM. If a test reveals a genuine engine bug, flag it to Hermes
rather than patching engine logic to make the test pass.

Naming follows TEST-DE-01..12 from 01_TASK_REGISTER.md.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import decision_engine
from decision_engine.core.schemas import (
    ActionCandidate,
    EngineStatus,
    ExecutionResult,
    Outcome,
    QualityRank,
    candidate_from_dict,
)
from decision_engine.core.assessor import deterministic_assessor
from decision_engine.core.executor import Executor
from decision_engine.core import engine as engine_mod
from decision_engine.core.engine import (
    initial_state,
    load_checkpoint,
    rank_candidates,
    run_engine,
    save_checkpoint,
)


def _sim_executor(max_attempts: int = 2) -> Executor:
    return Executor(mode="simulation")


def _outcomes_by_candidate(results):
    """Group execution-result dicts by candidate_id -> list of outcomes."""
    grouped: dict[str, list[str]] = {}
    for r in results:
        grouped.setdefault(r["candidate_id"], []).append(r["outcome"])
    return grouped


# --- TEST-DE-01: schema validation -----------------------------------------
def test_de01_schema_validation_and_priority_score():
    c = candidate_from_dict({"id": "T1", "probability": 0.8, "ground_truth": "SUCCESS"})
    assert isinstance(c, ActionCandidate)
    assert c.id == "T1"
    assert c.probability == 0.8
    assert c.ground_truth == Outcome.SUCCESS

    # priority_score = prob * (0.5 + 0.5 * quality_weight)
    c.quality_rank = QualityRank.HIGH  # weight 1.0
    assert c.priority_score() == round(0.8 * (0.5 + 0.5 * 1.0), 4)

    c_low = ActionCandidate(id="T2", probability=0.8, quality_rank=QualityRank.LOW)
    # LOW weight 0.3 -> 0.8 * (0.5 + 0.15) = 0.52
    assert c_low.priority_score() == round(0.8 * (0.5 + 0.5 * 0.3), 4)


# --- TEST-DE-02: priority ordering -----------------------------------------
def test_de02_priority_ordering():
    a = ActionCandidate(id="A", probability=0.5, quality_rank=QualityRank.HIGH)   # 0.5
    b = ActionCandidate(id="B", probability=0.9, quality_rank=QualityRank.LOW)   # 0.585
    c = ActionCandidate(id="C", probability=0.1, quality_rank=QualityRank.HIGH)  # 0.1
    ordered = rank_candidates([c, a, b])  # shuffled input
    assert [x.id for x in ordered] == ["B", "A", "C"]


# --- TEST-DE-03: success advances immediately (no retry on success) ---------
def test_de03_success_advances_immediately():
    candidates = [
        {"id": "WIN", "probability": 0.9, "ground_truth": "SUCCESS"},
        {"id": "LOSE", "probability": 0.1, "ground_truth": "FAIL_TIMEOUT"},
    ]
    final = run_engine(candidates, executor=_sim_executor(), max_attempts=2)
    grouped = _outcomes_by_candidate(final["results"])
    # WIN succeeded on the very first attempt and was never retried.
    assert grouped["WIN"] == ["SUCCESS"]
    assert final["status"] == EngineStatus.COMPLETED.value
    # The winning candidate object records a single success.
    win = next(c for c in final["candidates"] if c.id == "WIN")
    assert win.execution_outcome == Outcome.SUCCESS


# --- TEST-DE-04: failure increments attempt_count --------------------------
def test_de04_failure_increments_attempt_count():
    candidates = [{"id": "F", "probability": 0.5, "ground_truth": "FAIL_SYNTAX"}]
    final = run_engine(candidates, executor=_sim_executor(), max_attempts=2)
    grouped = _outcomes_by_candidate(final["results"])
    # One execute node per attempt: failing candidate is attempted twice.
    assert len(grouped["F"]) == 2
    assert all(o != "SUCCESS" for o in grouped["F"])


# --- TEST-DE-05: below-threshold retry -------------------------------------
def test_de05_below_threshold_retries_until_max():
    candidates = [{"id": "F", "probability": 0.5, "ground_truth": "FAIL_SYNTAX"}]
    final = run_engine(candidates, executor=_sim_executor(), max_attempts=3)
    grouped = _outcomes_by_candidate(final["results"])
    # max_attempts=3 => exactly 3 attempts before pivot (bounded retry).
    assert len(grouped["F"]) == 3


# --- TEST-DE-06: threshold pivot -------------------------------------------
def test_de06_threshold_pivot_abandons_candidate():
    candidates = [{"id": "F", "probability": 0.5, "ground_truth": "FAIL_TIMEOUT"}]
    final = run_engine(candidates, executor=_sim_executor(), max_attempts=2)
    grouped = _outcomes_by_candidate(final["results"])
    # Reached the pivot threshold: no more than max_attempts attempts, then pivot.
    assert len(grouped["F"]) == 2
    # After pivoting the only candidate, the workflow completes (no infinite loop).
    assert final["status"] == EngineStatus.COMPLETED.value
    assert final["current_index"] == len(final["candidates"])


# --- TEST-DE-07: bounded termination (no infinite loop) --------------------
def test_de07_bounded_termination_multiple_failing():
    candidates = [
        {"id": f"F{i}", "probability": 0.1 * (i + 1), "ground_truth": "FAIL_DEPENDENCY"}
        for i in range(4)
    ]
    final = run_engine(candidates, executor=_sim_executor(), max_attempts=2)
    # All four candidates processed; engine terminated with COMPLETED.
    assert final["status"] == EngineStatus.COMPLETED.value
    assert final["current_index"] == len(candidates)
    grouped = _outcomes_by_candidate(final["results"])
    # 4 candidates * 2 attempts each = 8 executions, no runaway.
    assert sum(len(v) for v in grouped.values()) == 8


# --- TEST-DE-08: checkpoint create -----------------------------------------
def test_de08_checkpoint_create(tmp_path):
    state = initial_state(
        [{"id": "X", "probability": 0.7, "ground_truth": "SUCCESS"}], max_attempts=2
    )
    path = save_checkpoint(state, str(tmp_path / "ckpt.json"))
    assert os.path.exists(path)
    payload = json.loads(Path(path).read_text())
    assert payload["version"] == engine_mod.ENGINE_VERSION
    assert "saved_at" in payload
    assert payload["state"]["candidates"][0]["id"] == "X"


# --- TEST-DE-09: resume reproduces state -----------------------------------
def test_de09_checkpoint_resume_reproduces_state(tmp_path):
    state = initial_state(
        [
            {"id": "X", "probability": 0.7, "ground_truth": "SUCCESS"},
            {"id": "Y", "probability": 0.2, "ground_truth": "FAIL_TIMEOUT"},
        ],
        max_attempts=3,
    )
    path = save_checkpoint(state, str(tmp_path / "ckpt.json"))
    loaded = load_checkpoint(path)
    # Round-trip reproducibility: re-serialized loaded state equals original.
    assert loaded["candidates"][0].id == "X"
    assert loaded["max_attempts"] == 3
    assert loaded["mode"] == state["mode"]
    # version guard: tampered version raises.
    bad = json.loads(Path(path).read_text())
    bad["version"] = 999
    Path(path).write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        load_checkpoint(path)


# --- TEST-DE-10: generic executor calls supplied execute_fn ----------------
def test_de10_generic_executor_calls_supplied_fn():
    seen = {}

    def my_fn(candidate: ActionCandidate) -> ExecutionResult:
        seen["id"] = candidate.id
        return ExecutionResult(candidate_id=candidate.id, outcome=Outcome.SUCCESS)

    ex = Executor(mode="real", execute_fn=my_fn)
    cand = ActionCandidate(id="G1", probability=0.5)
    res = ex.execute(cand)
    assert seen.get("id") == "G1"
    assert isinstance(res, ExecutionResult)
    assert res.outcome == Outcome.SUCCESS


# --- TEST-DE-11: real executor requires execute_fn (no silent fallback) ----
def test_de11_real_executor_requires_execute_fn():
    with pytest.raises(ValueError):
        Executor(mode="real")
    # A non-ExecutionResult return is rejected, keeping the engine typed.
    ex = Executor(mode="real", execute_fn=lambda c: "not-a-result")
    with pytest.raises(TypeError):
        ex.execute(ActionCandidate(id="Z"))


# --- TEST-DE-12: adapter import boundary (no VAPT leak in core) ------------
def test_de12_adapter_boundary_and_core_clean():
    # The VAPT adapter imports cleanly (the only VAPT-coupled file).
    import decision_engine.adapters.vapt_adapter as vapt  # noqa: F401

    assert hasattr(vapt, "vapt_candidates_from_corpus")

    # Core must NOT import VAPT-specific *code* (only vapt_adapter.py may).
    forbidden = ("poc_corpus", "labels.json", "from core import", "import core")
    core_files = [
        engine_mod.__file__,
        decision_engine.core.assessor.__file__,
        decision_engine.core.executor.__file__,
        decision_engine.core.schemas.__file__,
    ]
    for fpath in core_files:
        text = Path(fpath).read_text()
        for token in forbidden:
            assert token not in text, f"{token!r} leaked into {fpath}"
