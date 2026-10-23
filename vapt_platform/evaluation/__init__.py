"""Ground-truth evaluation package for finding reliability and model comparison."""
from typing import Any


def __getattr__(name: str) -> Any:
    if name in (
        "ReliabilityEvaluator",
        "FindingReliabilityEvaluator",
        "FullEvaluationReport",
        "LayerMetrics",
        "TestCaseResult",
        "build_evaluation_test_suite",
    ):
        import vapt_platform.evaluation.reliability_evaluator as re_mod
        return getattr(re_mod, name)
    if name in ("run_eval_server", "eval_fixture_client"):
        import vapt_platform.evaluation.fixtures as fix_mod
        return getattr(fix_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "run_eval_server",
    "eval_fixture_client",
    "ReliabilityEvaluator",
    "FindingReliabilityEvaluator",
    "FullEvaluationReport",
    "LayerMetrics",
    "TestCaseResult",
    "build_evaluation_test_suite",
]
