"""Engine integration layer.

High-level wrapper around the real decision_engine.run_engine() path.

This module:
  - converts scenario dicts using the existing candidate_from_dict schema
  - constructs the real Executor
  - uses the real deterministic_assessor
  - calls the real run_engine()
  - returns the actual final engine state
  - computes ONLY presentation-level metadata outside the engine

No engine logic is reimplemented here.
"""

from __future__ import annotations

from typing import Any, List, Optional

from decision_engine.core.assessor import deterministic_assessor
from decision_engine.core.engine import run_engine
from decision_engine.core.executor import Executor
from decision_engine.core.schemas import (
    ActionCandidate,
    EngineStatus,
    Outcome,
    candidate_from_dict,
)


def validate_scenario(candidates: List[dict]) -> None:
    """Validate a scenario definition before passing it to the engine.

    Raises ValueError on malformed input.
    """
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


def build_executor(mode: str = "simulation") -> Executor:
    """Construct the real Executor.

    Args:
        mode: "simulation" (default) or "real"

    Returns:
        Configured Executor instance
    """
    if mode not in ("simulation", "real"):
        raise ValueError(f"Unsupported mode: {mode!r}; expected 'simulation' or 'real'")
    return Executor(mode=mode)


def run_decision_scenario(
    scenario: List[dict],
    max_attempts: int = 2,
    mode: str = "simulation",
    executor: Executor | None = None,
    assessor: str = "deterministic",
    assessment_mode: str = "deterministic",
    assessment_provider: str = "ollama",
    assessment_api_key: Optional[str] = None,
) -> dict:
    """Run a scenario through the real decision engine.

    Steps:
      1. Validate scenario input
      2. Convert scenario dicts via candidate_from_dict (existing schema)
      3. Construct the real Executor (or use a pre-built one)
      4. Use the real assessor (deterministic or LLM)
      5. Call the real run_engine()
      6. Return the actual final engine state
      7. Compute presentation-level metadata outside the engine

    Args:
        scenario: List of candidate dicts
        max_attempts: Pivot threshold (max attempts per candidate)
        mode: "simulation" (default), "real", or "lab"
        executor: pre-built Executor (optional; overrides mode-based construction)
        assessor: "deterministic" (default) or "llm" (requires Ollama)

    Returns:
        Final engine state dict with presentation metadata appended
    """
    # 1. Validate
    validate_scenario(scenario)

    # 2. Normalize ground_truth to uppercase (engine's Outcome enum is uppercase)
    #    and pass raw scenario dicts to run_engine() — it internally calls
    #    candidate_from_dict() on each dict.
    candidates = []
    for d in scenario:
        normalized = dict(d)
        if normalized.get("ground_truth") is not None:
            normalized["ground_truth"] = str(normalized["ground_truth"]).upper()
        candidates.append(normalized)

    # 3. Construct the real Executor (or use pre-built)
    if executor is None:
        executor = build_executor(mode=mode)

    # 4. Use the pluggable assessor
    from vapt_platform.assessment import create_assessor, AssessmentResult
    from decision_engine.core.schemas import QualityRank

    assessor_fn = create_assessor(
        mode=assessment_mode,
        provider=assessment_provider,
        api_key=assessment_api_key,
    )

    # Wrap the pluggable assessor to work with the engine's assess_fn interface
    def _assess_fn(candidate: ActionCandidate) -> QualityRank:
        result: AssessmentResult = assessor_fn(candidate)
        return result.quality_rank

    # 5. Call the real run_engine()
    final_state = run_engine(
        candidates,
        assess_fn=_assess_fn,
        executor=executor,
        max_attempts=max_attempts,
        mode=mode,
    )

    # Store assessment provenance in state.
    # Metadata semantics (reporting only — does NOT alter GAP-1 logic):
    #   deterministic mode -> provider "deterministic" (no LLM involved)
    #   ai mode            -> provider as configured (e.g. "ollama")
    effective_provider = assessment_provider if assessment_mode == "ai" else "deterministic"
    final_state["_assessment"] = {
        "mode": assessment_mode,
        "provider": effective_provider,
    }

    # 6-7. Presentation-level metadata (computed OUTSIDE the engine)
    final_state["_presentation"] = _compute_presentation(final_state, scenario, max_attempts, mode)

    return final_state


def _compute_presentation(
    final_state: dict,
    scenario: List[dict],
    max_attempts: int,
    mode: str,
) -> dict:
    """Compute presentation-level metadata from the engine's actual output.

    This does NOT alter engine behavior — it only reads the final state
    and derives display-friendly fields.
    """
    results = final_state.get("results", [])
    candidates = final_state.get("candidates", [])

    total_attempts = sum(
        1 for r in results
    )
    # Count pivots: each pivot event in logs that contains "Abandoning" or "Redirected"
    pivot_count = sum(
        1 for log in final_state.get("logs", [])
        if "[Pivot]" in log and ("Abandoning" in log or "Redirected" in log)
    )

    processed_ids = []
    seen = set()
    for c in candidates:
        cid = getattr(c, "id", None)
        if cid and cid not in seen:
            seen.add(cid)
            processed_ids.append(cid)

    return {
        "scenario_candidates": len(scenario),
        "total_attempts": total_attempts,
        "pivot_count": pivot_count,
        "candidates_processed": processed_ids,
        "max_attempts": max_attempts,
        "mode": mode,
    }


def load_vapt_corpus_scenario() -> List[dict]:
    """Load VAPT corpus candidates for use as a demo scenario.

    Reuses the existing vapt_candidates_from_corpus() adapter.
    Returns a list of candidate dicts suitable for run_decision_scenario().
    """
    try:
        from decision_engine.adapters.vapt_adapter import vapt_candidates_from_corpus
    except Exception as e:
        raise RuntimeError(
            "Cannot load VAPT corpus scenario: vapt_candidates_from_corpus() is unavailable"
        ) from e

    candidates = vapt_candidates_from_corpus()
    if not candidates:
        raise RuntimeError("VAPT corpus scenario is empty")

    # Convert ActionCandidate objects to plain dicts for the scenario API
    return [
        {
            "id": c.id,
            "probability": c.probability,
            "ground_truth": c.ground_truth.value if c.ground_truth else None,
        }
        for c in candidates
    ]


def run_corpus_scenario(max_attempts: int = 2, mode: str = "simulation") -> dict:
    """Run the VAPT corpus as a scenario through the real engine.

    Convenience wrapper around run_decision_scenario() + load_vapt_corpus_scenario().
    """
    candidates = load_vapt_corpus_scenario()
    return run_decision_scenario(candidates, max_attempts=max_attempts, mode=mode)


def run_scan_file(scan_path: str, max_attempts: int = 2, mode: str = "simulation") -> dict:
    """Run a scan file through the real decision engine.

    Steps:
      1. Call scan_adapter.candidates_from_scan() to parse + enrich the scan
      2. Convert candidates to scenario dicts
      3. Call run_decision_scenario() with the real engine

    Args:
        scan_path: Path to scan file (Nmap XML/JSON or custom JSON)
        max_attempts: Pivot threshold (max attempts per candidate)
        mode: "simulation" (default) or "lab"

    Returns:
        Final engine state dict with presentation metadata appended
    """
    from decision_engine.adapters.scan_adapter import candidates_from_scan, candidates_to_scenario

    candidates = candidates_to_scenario(candidates_from_scan(scan_path))
    return run_decision_scenario(
        candidates,
        max_attempts=max_attempts,
        mode=mode,
    )