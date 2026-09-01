"""Deterministic demo scenarios for the mentor-facing prototype.

Each scenario defines input candidates with ground-truth outcomes.
The prototype feeds these into the real decision_engine.run_engine() path.
No engine logic is copied here — only input data definitions.
"""

from decision_engine.core.schemas import ActionCandidate, Outcome


def make_candidates() -> list[dict]:
    """Return a reusable base candidate pool used by multiple scenarios."""
    return [
        {
            "id": "DEMO-SUCCESS-A",
            "probability": 0.95,
            "ground_truth": "SUCCESS",
        },
        {
            "id": "DEMO-SUCCESS-B",
            "probability": 0.60,
            "ground_truth": "SUCCESS",
        },
        {
            "id": "DEMO-WORKER",
            "probability": 0.85,
            "ground_truth": "SUCCESS",
        },
        {
            "id": "DEMO-DEAD-END",
            "probability": 0.70,
            "ground_truth": "FAIL_TIMEOUT",
        },
        {
            "id": "DEMO-LOW-QUALITY",
            "probability": 0.30,
            "ground_truth": "FAIL_SYNTAX",
        },
        {
            "id": "DEMO-MID",
            "probability": 0.50,
            "ground_truth": "FAIL_TIMEOUT",
        },
    ]


def success_scenario() -> list[dict]:
    """Scenario A: immediate success / advance.

    At least one successful high-priority candidate plus additional
    candidates so ranking is visible.
    """
    return [
        {"id": "DEMO-SUCCESS-A", "probability": 0.95, "ground_truth": "SUCCESS"},
        {"id": "DEMO-SUCCESS-B", "probability": 0.60, "ground_truth": "SUCCESS"},
        {"id": "DEMO-WORKER", "probability": 0.85, "ground_truth": "SUCCESS"},
    ]


def failure_pivot_scenario(max_attempts: int = 2) -> list[dict]:
    """Scenario B: bounded failure then pivot to next candidate.

    Expected trace:
      DEMO-DEAD-END -> fail attempt 1 -> fail attempt 2 -> pivot
      DEMO-WORKER -> success -> completion
    """
    return [
        {"id": "DEMO-DEAD-END", "probability": 0.70, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "DEMO-WORKER", "probability": 0.85, "ground_truth": "SUCCESS"},
    ]


def multi_candidate_scenario() -> list[dict]:
    """Scenario C: multiple candidates with mixed outcomes so ranking
    and bounded failure handling are both visible.
    """
    return [
        {"id": "DEMO-SUCCESS-A", "probability": 0.95, "ground_truth": "SUCCESS"},
        {"id": "DEMO-DEAD-END", "probability": 0.70, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "DEMO-WORKER", "probability": 0.85, "ground_truth": "SUCCESS"},
        {"id": "DEMO-LOW-QUALITY", "probability": 0.30, "ground_truth": "FAIL_SYNTAX"},
        {"id": "DEMO-MID", "probability": 0.50, "ground_truth": "FAIL_TIMEOUT"},
    ]


# Canonical registry mapping scenario names to callables + kwargs.
SCENARIOS = {
    "success": (success_scenario, {}),
    "failure_pivot": (failure_pivot_scenario, {"max_attempts": 2}),
    "multi_candidate": (multi_candidate_scenario, {}),
}


def validate_scenario(candidates) -> None:
    """Validate a scenario definition before passing it to the engine.

    Raises ValueError on malformed input.
    """
    from decision_engine.core.schemas import Outcome

    if not isinstance(candidates, list):
        raise ValueError("Scenario must be a list of candidate dicts")

    if not candidates:
        raise ValueError("Scenario must contain at least one candidate")

    for i, c in enumerate(candidates):
        if not isinstance(c, dict):
            raise ValueError(f"Candidate at index {i} must be a dict, got {type(c).__name__}")
        cid = c.get("id")
        if not cid or not isinstance(cid, str):
            raise ValueError(
                f"Candidate at index {i} must have a non-empty string 'id', got {cid!r}"
            )
        prob = c.get("probability", 0.0)
        if not isinstance(prob, (int, float)) or not (0.0 <= float(prob) <= 1.0):
            raise ValueError(
                f"Candidate {cid!r} has invalid 'probability' {prob!r}; must be float in [0, 1]"
            )
        gt = c.get("ground_truth")
        if gt is not None:
            if not isinstance(gt, str):
                raise ValueError(
                    f"Candidate {cid!r} has invalid 'ground_truth' {gt!r}; must be a string"
                )
            try:
                Outcome(gt.upper())
            except ValueError:
                raise ValueError(
                    f"Candidate {cid!r} has unknown 'ground_truth' {gt!r}; "
                    f"must be one of {[o.value for o in Outcome]}"
                )
