"""VAPT DOMAIN ADAPTER for the general decision engine.

This is the ONLY file that knows about CVEs, PoCs, and exploit scoring. It maps
the existing VAPT corpus (data/poc_corpus) into the domain-independent
ActionCandidate type, and provides:

  - vapt_candidates_from_corpus() : builds candidates (with ground_truth labels
    for simulation + live EPSS probabilities) from the existing corpus.
  - assess_exploit_quality_adapter(candidate): a real Gap-1 scorer that delegates
    to the original VAPT assessor (core/exploit_assessor.py) when an LLM is
    available; otherwise falls back to the deterministic scorer.
  - vapt_executor(execute_fn): wraps a domain action runner (e.g. the original
    core/executor.Executor) as the engine's real-mode execute_fn.

No changes are made to core/ — this adapter imports it read-only. Stage 1 engine
stays domain-free; VAPT is just one domain plugged into it.
"""
from __future__ import annotations

import json
import os
from typing import Callable, List, Optional

from decision_engine.core.schemas import (
    ActionCandidate,
    Outcome,
    QualityRank,
)
from decision_engine.core.assessor import deterministic_assessor

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "poc_corpus")
LABELS = os.path.join(CORPUS_DIR, "labels.json")
EPSS_ENRICH = os.path.join(os.path.dirname(__file__), "..", "..", "datasets", "epss_corpus_enrichment.json")

# Map VAPT label outcome strings -> engine Outcome
_OUTCOME_MAP = {
    "success": Outcome.SUCCESS,
    "fail_timeout": Outcome.FAIL_TIMEOUT,
    "fail_syntax": Outcome.FAIL_SYNTAX,
    "fail_dependency": Outcome.FAIL_DEPENDENCY,
    "fail_no_target": Outcome.FAIL_NO_TARGET,
    "skipped": Outcome.SKIPPED,
}


def _load():
    labels = json.load(open(LABELS)) if os.path.exists(LABELS) else {}
    epss = json.load(open(EPSS_ENRICH)) if os.path.exists(EPSS_ENRICH) else {}
    return labels, epss


def vapt_candidates_from_corpus() -> List[ActionCandidate]:
    """Build ActionCandidates from the existing VAPT corpus.

    - probability = live EPSS score (from datasets/epss_corpus_enrichment.json)
    - ground_truth = curated corpus label outcome (simulation backend)
    """
    labels, epss = _load()
    cands = []
    for cve, meta in labels.items():
        o = _OUTCOME_MAP.get(str(meta.get("outcome", "")).lower(), Outcome.FAIL_TIMEOUT)
        cands.append(ActionCandidate(
            id=cve,
            probability=float(epss.get(cve, 0.0)),
            ground_truth=o,
        ))
    return cands


def vapt_assess_fn(use_llm: bool = False, provider: str = "ollama"):
    """Return a Gap-1 scorer for the engine.

    use_llm=False (default) -> deterministic offline scorer (research/repro).
    use_llm=True  -> delegates to core/exploit_assessor.assess_exploit_quality
                    (requires a reachable Ollama/OpenAI). Kept isolated so the
                    engine core never depends on the VAPT LLM path.
    """
    if not use_llm:
        return deterministic_assessor

    def _llm_score(candidate: ActionCandidate) -> QualityRank:
        from core.exploit_assessor import assess_exploit_quality
        a = assess_exploit_quality(candidate.id, provider=provider)
        return QualityRank(a.usability_rank.value)

    return _llm_score


def vapt_real_executor(execute_fn: Callable[[ActionCandidate], "object"]):
    """Wrap a domain action runner (returns a VAPT ExecutionResult-like object)."""
    from core.schemas import ExecutionResult as VaptResult
    from decision_engine.core.schemas import ExecutionResult

    def _wrap(candidate: ActionCandidate) -> ExecutionResult:
        r = execute_fn(candidate)
        return ExecutionResult(
            candidate_id=candidate.id,
            outcome=Outcome(r.outcome.value),
            request_count=getattr(r, "request_count", 1),
            detail=getattr(r, "detail", ""),
        )

    return _wrap
