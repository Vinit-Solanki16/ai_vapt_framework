"""T-OPENAI coverage: OpenAI provider branch of core/exploit_assessor.py.

Scope:
  1. get_llm(provider="openai") builds a REAL ChatOpenAI wired into the SAME
     structured-output contract (llm.with_structured_output(ExploitAssessment))
     that the Ollama path uses — verified via a stubbed ChatOpenAI class.
  2. assess_exploit_quality(provider="openai") returns an enum-constrained
     ExploitAssessment with NO network and NO real API key (ChatOpenAI is
     stubbed at the module boundary).
  3. Fail safe: with OPENAI_API_KEY unset (and no api_key= passed) the path
     raises an immediate, clear error instead of hanging on a dummy-key
     request.

All tests are offline & fast: conftest.py blocks requests/socket; ChatOpenAI
is stubbed here. NOTE: the LIVE OpenAI path remains UNVERIFIED without a real
key (documented in docs/project_management/07_TEST_STATUS.md).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from langchain_core.runnables import Runnable
from pydantic import SecretStr

import core.exploit_assessor as exploit_assessor
from core.schemas import ExploitAssessment, UsabilityRank


def _canned_assessment() -> ExploitAssessment:
    """Fully valid, enum-constrained ExploitAssessment (as the LLM must emit)."""
    return ExploitAssessment(
        exploit_found=True,
        syntax_valid=True,
        os_dependencies="paramiko",
        privileges_required="user",
        network_noise="medium",
        complexity_score=4,
        prerequisites_met=True,
        usability_rank=UsabilityRank.HIGH,
        reasoning="stubbed openai structured output",
    )


class _RecordingStubChatOpenAI:
    """Stand-in for langchain_openai.ChatOpenAI at the module boundary.

    Records constructor kwargs and exposes with_structured_output() exactly
    like the real client, returning a deterministic canned assessment.
    """

    last_kwargs = None
    last_instance = None

    def __init__(self, **kwargs):
        type(self).last_kwargs = kwargs
        type(self).last_instance = self

    def with_structured_output(self, schema):
        # Record which contract was applied (must be the shared schema).
        self.schema = schema

        class _Structured(Runnable):
            def __init__(self, payload):
                super().__init__()
                self._payload = payload

            def invoke(self, *_a, **_k):
                return self._payload

        return _Structured(_canned_assessment())


# ---------------------------------------------------------------------------
# 1+2: provider="openai" -> real-path chain, stubbed LLM, constrained result
# ---------------------------------------------------------------------------
def test_assess_exploit_quality_openai_stubbed_no_key_or_network(
    monkeypatch, offline_guard
):
    monkeypatch.setattr(
        exploit_assessor, "ChatOpenAI", _RecordingStubChatOpenAI
    )
    # Fake key satisfies the fail-safe check; NO real key / network needed.
    monkeypatch.setenv("OPENAI_API_KEY", "test-fake-key-offline")
    monkeypatch.setattr(exploit_assessor, "fetch_github_poc", lambda cve: None)

    result = exploit_assessor.assess_exploit_quality(
        "CVE-2021-44228", provider="openai"
    )

    # Valid, enum-constrained structured output (same contract as Ollama).
    assert isinstance(result, ExploitAssessment)
    assert isinstance(result.usability_rank, UsabilityRank)
    assert result.usability_rank.value in ("HIGH", "MEDIUM", "LOW")
    assert result.privileges_required in ("none", "user", "root")
    assert result.network_noise in ("low", "medium", "high")
    assert isinstance(result.complexity_score, int)
    assert 1 <= result.complexity_score <= 10
    assert isinstance(result.reasoning, str) and result.reasoning

    # A real ChatOpenAI-shaped client was constructed correctly.
    kwargs = _RecordingStubChatOpenAI.last_kwargs
    assert kwargs["model"] == "gpt-4o-mini"
    assert isinstance(kwargs["api_key"], SecretStr)
    assert kwargs["api_key"].get_secret_value() == "test-fake-key-offline"
    assert kwargs["temperature"] == 0.1

    # The SAME structured-output contract used by Ollama was applied.
    assert _RecordingStubChatOpenAI.last_instance.schema is ExploitAssessment

    # Corpus-label cross-check proves the full assess path ran.
    assert "[corpus-label=" in result.reasoning
    assert offline_guard.call_count == 0  # zero subprocesses, fully offline


# ---------------------------------------------------------------------------
# 3: missing OPENAI_API_KEY -> immediate, clear failure (never hangs)
# ---------------------------------------------------------------------------
def test_openai_without_api_key_fails_safe_and_fast(monkeypatch, offline_guard):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        exploit_assessor.get_llm(provider="openai")

    # And the same clear error propagates through the assessor entrypoint.
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        exploit_assessor.assess_exploit_quality(
            "CVE-2021-44228", provider="openai"
        )

    assert offline_guard.call_count == 0  # nothing shelled out while failing


def test_unsupported_provider_still_rejected():
    with pytest.raises(ValueError, match="Unsupported provider"):
        exploit_assessor.get_llm(provider="azure-fake")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
