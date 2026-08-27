"""Top-level decision_engine package.

Stage 1 deliverable: a domain-independent autonomous decision & pivot engine.
Attach any domain (VAPT, scheduling, robotics, ...) via decision_engine/adapters/.
"""
from decision_engine.core import (
    ActionCandidate,
    EngineStatus,
    ExecutionResult,
    Outcome,
    QualityRank,
    assess_candidates,
    deterministic_assessor,
    Executor,
    build_graph,
    initial_state,
    rank_candidates,
    run_engine,
    save_checkpoint,
    load_checkpoint,
)

__version__ = "0.1.0"
