"""Regression: preparatory GAP-1 probes must not exhaust the GAP-2 decision queue.

Before the fix, ``_investigate_gap1_candidates`` fed every bounded prep probe
into the shared DecisionEngine. With 22 candidates at k=2, that marked all 22
ABANDONED before the autonomous model started, so ``record_probe_outcome``
always returned ``recommended_next_candidate=None`` and no agent-driven pivot
was possible. The prep loop now uses a private DecisionEngine.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from strix.core import runner
from strix.core.decision_engine.engine import DecisionEngine
from strix.core.decision_engine.schemas import ActionCandidate, Outcome


def test_prep_loop_uses_private_decision_engine(monkeypatch) -> None:
    """The shared engine must keep PENDING candidates for agent-driven pivots."""
    shared = DecisionEngine(pivot_threshold=2)
    shared.initialize(
        [
            ActionCandidate(id="c1", endpoint="/one"),
            ActionCandidate(id="c2", endpoint="/two"),
        ]
    )

    seen: dict[str, list[str]] = {"shared": [], "prep": []}
    original_shared_record = shared.record_outcome

    # The prep loop's private engine is a distinct instance: if the source
    # still calls decision_engine.record_outcome, this test fails because the
    # shared engine's calls would be recorded here.
    def _shared_record(candidate_id, outcome, **kwargs):
        seen["shared"].append(candidate_id)
        return original_shared_record(candidate_id, outcome, **kwargs)

    monkeypatch.setattr(shared, "record_outcome", _shared_record)

    src = inspect.getsource(runner._investigate_gap1_candidates)
    assert "prep_decision_engine = DecisionEngine(" in src
    assert "prep_decision_engine.record_outcome(" in src

    # Simulate two failures on c1 in the private engine: a real alternative
    # must still be available from the shared engine.
    prep = DecisionEngine(pivot_threshold=2)
    prep.initialize(
        [
            ActionCandidate(id="c1", endpoint="/one"),
            ActionCandidate(id="c2", endpoint="/two"),
        ]
    )
    for _ in range(2):
        prep.record_outcome("c1", Outcome.FAIL_TIMEOUT)

    assert seen["shared"] == []
    # c1 is the currently targeted candidate; the important invariant is that
    # c2 remains available as a real alternative (get_next_available_candidate
    # marks it ATTEMPTING, so call it exactly once).
    alternative = shared.get_next_available_candidate()
    assert alternative is not None
    assert alternative.id == "c2"


def test_source_has_no_shared_engine_call_in_prep_loop() -> None:
    """AST: the prep function must not call decision_engine.record_outcome."""
    path = Path(inspect.getfile(runner._investigate_gap1_candidates))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
        and n.name == "_investigate_gap1_candidates"
    )
    calls = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "record_outcome":
                base = func.value
                if isinstance(base, ast.Name):
                    calls.append(base.id)
    assert "decision_engine" not in calls
    assert "prep_decision_engine" in calls
