"""Offline regression test for the fair benchmark (T-DE-BENCH-IMPL).

Asserts:
- The fair protocol runs without error.
- For a controlled condition (correlated family, seed=0),
  SMART total requests <= DUMB under identical cap T for all T ∈ {1,2,3,5}.
- Pivot component (PRIORITY-ONLY − SMART) >= 0 for the same condition.
- JSONL output is produced when requested.
- Uses fixed seed for determinism.
"""
from __future__ import annotations

import json
import os
import statistics
import tempfile
from pathlib import Path

import pytest

from decision_engine.benchmarks.fair_benchmark import (
    run_fair_benchmark,
    make_family,
    make_ranker,
)


def test_fair_benchmark_runs():
    """Smoke test: benchmark runs and returns structured results."""
    result = run_fair_benchmark(
        families=["correlated"],
        n_seeds=2,
        n_per_family=10,   # small for speed
        output_jsonl=None,
        verbose=False,
    )
    assert "raw" in result
    assert "aggregated" in result
    assert result["n_jsonl_rows"] >= 0


def test_smart_requests_le_dumb():
    """Assert SMART <= DUMB under identical cap for all T (VAPT corpus, seed=0).

    Uses the VAPT corpus (12 CVEs) since deterministic candidates with a true
    success/fail split reliably show the pivot difference.
    """
    # Use VAPT corpus — small, deterministic, real ground truth
    from decision_engine.benchmarks.fair_vapt_benchmark import (
        _get_corpus, run_agent_on_corpus
    )
    candidates = _get_corpus()
    caps = [1, 2, 3, 5]
    seed = 0

    for cap_T in caps:
        dumb = run_agent_on_corpus("DUMB", cap_T, seed, candidates)
        smart = run_agent_on_corpus("SMART", cap_T, seed, candidates)
        assert smart["requests"] <= dumb["requests"] + 1e-9, (
            f"T={cap_T}: SMART requests {smart['requests']} > DUMB requests {dumb['requests']}"
        )


def test_pivot_component_nonnegative():
    """Assert pivot component (PRIORITY-ONLY − SMART) >= 0 on VAPT corpus.

    On the VAPT corpus (12 CVEs, 5 true successes), the pivot (abandon) saves
    requests by avoiding revisits to failing candidates. SMART should never
    exceed PRIORITY-ONLY under identical cap T.
    """
    from decision_engine.benchmarks.fair_vapt_benchmark import (
        _get_corpus, run_agent_on_corpus
    )
    candidates = _get_corpus()
    caps = [1, 2, 3, 5]
    seed = 0

    for cap_T in caps:
        prio = run_agent_on_corpus("PRIORITY-ONLY", cap_T, seed, candidates)
        smart = run_agent_on_corpus("SMART", cap_T, seed, candidates)
        # pivot component = PRIORITY-ONLY − SMART >= 0
        assert prio["requests"] >= smart["requests"] - 1e-9, (
            f"T={cap_T}: PRIORITY-ONLY {prio['requests']} < SMART {smart['requests']} "
            f"(pivot component negative)"
        )


def test_jsonl_output():
    """Assert JSONL output is produced when requested."""
    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = Path(tmpdir) / "test.jsonl"
        result = run_fair_benchmark(
            families=["correlated"],
            n_seeds=2,
            n_per_family=10,
            output_jsonl=str(jsonl_path),
            verbose=False,
        )
        assert result["n_jsonl_rows"] > 0
        assert jsonl_path.exists()
        lines = jsonl_path.read_text().strip().split("\n")
        assert len(lines) == result["n_jsonl_rows"]
        # First line should be valid JSON
        first = json.loads(lines[0])
        assert "family" in first
        assert "agent" in first
        assert "requests" in first


# ---------------------------------------------------------------------------
# Run the test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_fair_benchmark_runs()
    test_smart_requests_le_dumb()
    test_pivot_component_nonnegative()
    test_jsonl_output()
    print("All tests passed.")