"""OpenRouter optional-provider coverage (hosted API arm).

Scope — every test is OFFLINE and fully mocked (no live API calls):
  1. provider/model selection threads through get_llm / resolve_model.
  2. a missing API key is a CLEAR, immediate error — never a silent switch.
  3. a valid structured assessment satisfies the shared ExploitAssessment
     contract (the SAME schema Ollama uses).
  4. malformed / unsupported structured output is surfaced, not swallowed.
  5. timeout, rate-limit and generic API errors are classified and made
     visible in AssessmentResult.error.
  6. a hosted failure NEVER dispatches to another provider (no accidental
     switch to Ollama/OpenAI).
  7. the Ollama default and baseline model configuration are UNCHANGED.

Research integrity: OpenRouter is a separate, clearly-labelled run arm. It is
never selected implicitly and its results are never merged into the historical
Ollama/llama3.2:3b baseline experiments.
"""
from __future__ import annotations

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from langchain_core.runnables import Runnable
from pydantic import SecretStr, ValidationError

import core.exploit_assessor as exploit_assessor
from core.schemas import ExploitAssessment, UsabilityRank
from vapt_platform import assessment as assessment_mod
from vapt_platform import model_config as mc
from vapt_platform import provider_errors as pe
from decision_engine.core.schemas import ActionCandidate

FAKE_KEY = "sk-or-test-secret-key-1234567890"


def _canned_assessment(reasoning: str = "stubbed openrouter structured output") -> ExploitAssessment:
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
        reasoning=reasoning,
    )


def _malformed_validation_error() -> ValidationError:
    """A real pydantic ValidationError, as with_structured_output raises when
    the model's payload violates the contract."""
    from pydantic import BaseModel

    class _Strict(BaseModel):
        complexity_score: int

    try:
        _Strict.model_validate({"complexity_score": "not-an-int"})
    except ValidationError as e:
        return e
    raise AssertionError("expected a ValidationError")  # pragma: no cover


def make_stub_chat_openrouter(payload=None, raise_on_invoke=None):
    """Build a fresh ChatOpenRouter stand-in recorded at the module boundary.

    A NEW class per test avoids cross-test leakage of recorded kwargs.
    """
    class _StubChatOpenRouter:
        last_kwargs = None
        last_instance = None

        def __init__(self, **kwargs):
            type(self).last_kwargs = kwargs
            type(self).last_instance = self
            self.schema = None

        def with_structured_output(self, schema):
            self.schema = schema

            class _Structured(Runnable):
                def invoke(self, *_a, **_k):
                    if raise_on_invoke is not None:
                        raise raise_on_invoke
                    return payload if payload is not None else _canned_assessment()

            return _Structured()

    return _StubChatOpenRouter


@pytest.fixture
def openrouter_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    return FAKE_KEY


@pytest.fixture
def client():
    """In-memory FastAPI client (the health endpoint persists nothing)."""
    from fastapi.testclient import TestClient
    from services.api import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Provider / model selection
# ---------------------------------------------------------------------------

def test_openrouter_is_a_registered_provider_but_not_the_default():
    assert "openrouter" in mc.KNOWN_PROVIDERS
    assert mc.DEFAULT_PROVIDER == "ollama"
    # Never selected implicitly.
    assert mc.default_model_for(None) == mc.DEFAULT_OLLAMA_MODEL
    assert mc.resolve_model(None, None) == mc.DEFAULT_OLLAMA_MODEL


def test_openrouter_default_model_is_the_hosted_default():
    assert mc.default_model_for("openrouter") == mc.DEFAULT_OPENROUTER_MODEL
    assert mc.default_model_for("openrouter") in mc.OPENROUTER_MODELS
    assert mc.OPENROUTER_MODELS[0] == mc.DEFAULT_OPENROUTER_MODEL


def test_openrouter_model_is_env_configurable(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    assert mc.resolve_model("openrouter", None) == "openai/gpt-4o-mini"
    # An explicit request still wins over the env default.
    assert mc.resolve_model("openrouter", "anthropic/claude-3.5-haiku") == \
        "anthropic/claude-3.5-haiku"


def test_openrouter_env_default_ignores_blank(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "   ")
    assert mc.default_model_for("openrouter") == mc.DEFAULT_OPENROUTER_MODEL


def test_ollama_baseline_is_not_env_overridable(monkeypatch):
    """The thesis baseline must stay fixed regardless of hosted config."""
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    assert mc.default_model_for("ollama") == "llama3.2:3b"
    assert mc.resolve_model("ollama", None) == "llama3.2:3b"


def test_get_llm_openrouter_builds_client_with_selection(monkeypatch, openrouter_key):
    stub = make_stub_chat_openrouter()
    monkeypatch.setattr(exploit_assessor, "ChatOpenRouter", stub)

    llm = exploit_assessor.get_llm("openrouter")

    kwargs = stub.last_kwargs
    assert kwargs["model"] == mc.DEFAULT_OPENROUTER_MODEL
    assert isinstance(kwargs["api_key"], SecretStr)
    assert kwargs["api_key"].get_secret_value() == FAKE_KEY
    assert kwargs["temperature"] == 0.1
    assert kwargs["request_timeout"] == 60_000   # default 60s -> milliseconds
    assert kwargs["max_retries"] == 2
    assert llm.schema is None  # schema is applied later via with_structured_output


def test_get_llm_openrouter_honours_explicit_model(monkeypatch, openrouter_key):
    stub = make_stub_chat_openrouter()
    monkeypatch.setattr(exploit_assessor, "ChatOpenRouter", stub)
    exploit_assessor.get_llm("openrouter", "openai/gpt-4o-mini")
    assert stub.last_kwargs["model"] == "openai/gpt-4o-mini"


def test_openrouter_timeout_and_retries_are_configurable(monkeypatch, openrouter_key):
    monkeypatch.setenv("OPENROUTER_TIMEOUT_S", "12.5")
    monkeypatch.setenv("OPENROUTER_MAX_RETRIES", "0")
    stub = make_stub_chat_openrouter()
    monkeypatch.setattr(exploit_assessor, "ChatOpenRouter", stub)
    exploit_assessor.get_llm("openrouter")
    assert stub.last_kwargs["request_timeout"] == 12_500
    assert stub.last_kwargs["max_retries"] == 0


def test_openrouter_timeout_env_garbage_falls_back_to_default(monkeypatch, openrouter_key):
    monkeypatch.setenv("OPENROUTER_TIMEOUT_S", "not-a-number")
    stub = make_stub_chat_openrouter()
    monkeypatch.setattr(exploit_assessor, "ChatOpenRouter", stub)
    exploit_assessor.get_llm("openrouter")
    assert stub.last_kwargs["request_timeout"] == 60_000


def test_api_key_env_for_providers():
    assert mc.api_key_env_for("openrouter") == "OPENROUTER_API_KEY"
    assert mc.api_key_env_for("openai") == "OPENAI_API_KEY"
    # Local providers need no key by design.
    assert mc.api_key_env_for("ollama") is None
    assert mc.api_key_env_for("nope") is None


# ---------------------------------------------------------------------------
# 2. Missing API key -> clear error, no silent switch
# ---------------------------------------------------------------------------

def test_openrouter_without_key_fails_safe_and_fast(monkeypatch, offline_guard):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        exploit_assessor.get_llm(provider="openrouter")

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        exploit_assessor.assess_exploit_quality("CVE-2021-44228", provider="openrouter")

    assert offline_guard.call_count == 0


def test_create_assessor_openrouter_without_key_raises(monkeypatch):
    """Explicit selection + missing key is a config error, not a fallback."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        assessment_mod.create_assessor(mode="ai", provider="openrouter")


def test_create_assessor_openrouter_error_names_no_provider_switch(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc:
        assessment_mod.create_assessor(mode="ai", provider="openrouter")
    assert "No fallback to another provider" in str(exc.value)


def test_create_assessor_openrouter_accepts_explicit_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    fn = assessment_mod.create_assessor(
        mode="ai", provider="openrouter", api_key=FAKE_KEY,
    )
    assert callable(fn)


def test_openrouter_optional_package_missing_is_clear(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    monkeypatch.setattr(exploit_assessor, "ChatOpenRouter", None)
    with pytest.raises(RuntimeError, match="langchain-openrouter"):
        exploit_assessor.get_llm("openrouter")


# ---------------------------------------------------------------------------
# 3. Valid structured assessment
# ---------------------------------------------------------------------------

def test_valid_structured_assessment_end_to_end(monkeypatch, openrouter_key, offline_guard):
    stub = make_stub_chat_openrouter()
    monkeypatch.setattr(exploit_assessor, "ChatOpenRouter", stub)
    monkeypatch.setattr(exploit_assessor, "fetch_github_poc", lambda cve: None)

    result = exploit_assessor.assess_exploit_quality(
        "CVE-2021-44228", provider="openrouter"
    )

    assert isinstance(result, ExploitAssessment)
    assert isinstance(result.usability_rank, UsabilityRank)
    assert result.usability_rank.value in ("HIGH", "MEDIUM", "LOW")
    assert result.privileges_required in ("none", "user", "root")
    assert result.network_noise in ("low", "medium", "high")
    assert 1 <= result.complexity_score <= 10
    # The SAME structured-output contract Ollama uses was applied.
    assert stub.last_instance.schema is ExploitAssessment
    # Corpus-label cross-check proves the full assess path ran.
    assert "[corpus-label=" in result.reasoning
    assert offline_guard.call_count == 0


def test_openrouter_uses_shared_schema_not_a_private_one(monkeypatch, openrouter_key):
    """The hosted arm must not invent a different output contract."""
    from core.schemas import ExploitAssessment as Shared

    stub = make_stub_chat_openrouter()
    monkeypatch.setattr(exploit_assessor, "ChatOpenRouter", stub)
    monkeypatch.setattr(exploit_assessor, "fetch_github_poc", lambda cve: None)
    exploit_assessor.assess_exploit_quality("CVE-2021-44228", provider="openrouter")
    assert stub.last_instance.schema is Shared


# ---------------------------------------------------------------------------
# 4. Malformed / unsupported structured output
# ---------------------------------------------------------------------------

def test_malformed_structured_output_is_classified(monkeypatch):
    assert pe.classify_error(_malformed_validation_error()) == "malformed_output"


def test_malformed_structured_output_surfaces_via_assessor(monkeypatch, openrouter_key):
    stub = make_stub_chat_openrouter(raise_on_invoke=_malformed_validation_error())
    monkeypatch.setattr(exploit_assessor, "ChatOpenRouter", stub)
    monkeypatch.setattr(exploit_assessor, "fetch_github_poc", lambda cve: None)

    # assess_exploit_quality itself surfaces the validation failure...
    with pytest.raises(ValidationError):
        exploit_assessor.assess_exploit_quality(
            "CVE-2021-44228", provider="openrouter"
        )

    # ...and the pluggable assessor converts it into a VISIBLE, tagged
    # deterministic fallback rather than hiding it.
    fn = assessment_mod.create_assessor(
        mode="ai", provider="openrouter", api_key=FAKE_KEY,
    )
    res = fn(ActionCandidate(id="CVE-2021-44228", probability=0.5))
    assert res.fallback is True
    assert res.source == "deterministic"
    assert res.provider == "openrouter"          # still names the SELECTED provider
    assert "malformed_output" in (res.error or "")


def test_unsupported_provider_still_rejected():
    with pytest.raises(ValueError, match="Unsupported provider"):
        exploit_assessor.get_llm(provider="azure-fake")


# ---------------------------------------------------------------------------
# 5. Timeout / rate-limit / API errors are visible
# ---------------------------------------------------------------------------

class _FakeHTTPStatusError(Exception):
    """SDK-shaped error carrying an HTTP status code."""

    def __init__(self, status_code: int):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def test_error_classification_matrix():
    assert pe.classify_error(TimeoutError("deadline exceeded")) == "timeout"
    assert pe.classify_error(_FakeHTTPStatusError(429)) == "rate_limit"
    assert pe.classify_error(_FakeHTTPStatusError(401)) == "auth"
    assert pe.classify_error(_FakeHTTPStatusError(402)) == "quota"
    assert pe.classify_error(_FakeHTTPStatusError(503)) == "unavailable"
    assert pe.classify_error(_FakeHTTPStatusError(404)) == "not_found"
    assert pe.classify_error(ConnectionError("refused")) == "connection"
    # Class-name based fallback for exceptions with no status code.
    class RateLimitError(Exception):
        pass

    class APITimeoutError(Exception):
        pass

    assert pe.classify_error(RateLimitError("slow down")) == "rate_limit"
    assert pe.classify_error(APITimeoutError("too slow")) == "timeout"
    assert pe.classify_error(RuntimeError("??")) == "unknown"


@pytest.mark.parametrize("exc,expected", [
    (TimeoutError("read timed out"), "timeout"),
    (_FakeHTTPStatusError(429), "rate_limit"),
    (_FakeHTTPStatusError(500), "unavailable"),
    (RuntimeError("boom"), "unknown"),
])
def test_provider_failure_keeps_selected_provider_and_reports_category(
    monkeypatch, openrouter_key, exc, expected
):
    stub = make_stub_chat_openrouter(raise_on_invoke=exc)
    monkeypatch.setattr(exploit_assessor, "ChatOpenRouter", stub)

    fn = assessment_mod.create_assessor(mode="ai", provider="openrouter")
    res = fn(ActionCandidate(id="CVE-2021-44228", probability=0.5))

    # Visible, classified, never concealed.
    assert res.fallback is True
    assert res.provider == "openrouter"
    assert expected in (res.error or "")
    assert "deterministic fallback used" in (res.error or "")


def test_retryable_categories():
    assert pe.is_retryable(TimeoutError())
    assert pe.is_retryable(_FakeHTTPStatusError(429))
    assert not pe.is_retryable(_FakeHTTPStatusError(401))
    assert not pe.is_retryable(RuntimeError())


# ---------------------------------------------------------------------------
# 6. No accidental switch to another provider
# ---------------------------------------------------------------------------

def test_openrouter_failure_never_dispatches_to_ollama(monkeypatch, openrouter_key):
    stub = make_stub_chat_openrouter(raise_on_invoke=TimeoutError("deadline"))
    monkeypatch.setattr(exploit_assessor, "ChatOpenRouter", stub)

    def _must_not_be_called(*_a, **_k):
        raise AssertionError("provider switched to ollama")

    monkeypatch.setattr(assessment_mod, "_try_ollama_assess", _must_not_be_called)
    monkeypatch.setattr(assessment_mod, "_try_openai_assess", _must_not_be_called)

    fn = assessment_mod.create_assessor(mode="ai", provider="openrouter")
    res = fn(ActionCandidate(id="CVE-2021-44228", probability=0.5))

    assert res.provider == "openrouter"   # provenance names the SELECTED provider
    assert res.source == "deterministic"
    assert res.fallback is True


def test_openrouter_get_llm_is_never_called_for_ollama(monkeypatch, openrouter_key):
    """get_llm must only ever be asked for the selected provider."""
    stub = make_stub_chat_openrouter(raise_on_invoke=RuntimeError("api down"))
    monkeypatch.setattr(exploit_assessor, "ChatOpenRouter", stub)

    seen: list[str] = []
    real_get_llm = exploit_assessor.get_llm

    def _spy(provider="ollama", model_name=None, api_key=None):
        seen.append(provider)
        return real_get_llm(provider, model_name=model_name, api_key=api_key)

    monkeypatch.setattr(exploit_assessor, "get_llm", _spy)

    fn = assessment_mod.create_assessor(mode="ai", provider="openrouter")
    fn(ActionCandidate(id="CVE-2021-44228", probability=0.5))

    # get_llm is invoked twice by design (reachability probe + the assess
    # call, mirroring the Ollama/OpenAI helpers). The invariant is that it is
    # ONLY ever asked for the selected provider — never "ollama"/"openai".
    assert seen, "get_llm was never called"
    assert set(seen) == {"openrouter"}


def test_successful_openrouter_result_is_labelled_openrouter(monkeypatch, openrouter_key):
    stub = make_stub_chat_openrouter()
    monkeypatch.setattr(exploit_assessor, "ChatOpenRouter", stub)
    monkeypatch.setattr(exploit_assessor, "fetch_github_poc", lambda cve: None)

    fn = assessment_mod.create_assessor(mode="ai", provider="openrouter")
    res = fn(ActionCandidate(id="CVE-2021-44228", probability=0.5))

    assert res.source == "llm"
    assert res.provider == "openrouter"
    assert res.model == mc.DEFAULT_OPENROUTER_MODEL
    assert res.fallback is False
    assert res.error is None


# ---------------------------------------------------------------------------
# 7. Ollama default and model configuration UNCHANGED
# ---------------------------------------------------------------------------

def test_ollama_default_and_baseline_unchanged():
    assert mc.DEFAULT_PROVIDER == "ollama"
    assert mc.DEFAULT_OLLAMA_MODEL == "llama3.2:3b"
    assert mc.is_baseline("llama3.2:3b")
    assert mc.OLLAMA_MODELS[0] == "llama3.2:3b"
    assert mc.default_model_for("ollama") == "llama3.2:3b"
    assert mc.resolve_model("ollama", None) == "llama3.2:3b"


def test_ollama_client_construction_unchanged():
    llm = exploit_assessor.get_llm("ollama")
    assert llm.model == "llama3.2:3b"
    assert llm.temperature == 0.1


def test_ollama_path_untouched_by_openrouter_configuration(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    # Hosted config must not leak into the local baseline.
    assert exploit_assessor.get_llm("ollama").model == "llama3.2:3b"
    fn = assessment_mod.create_assessor(mode="ai", provider="ollama")
    assert callable(fn)


def test_openai_provider_unaffected():
    assert mc.default_model_for("openai") == "gpt-4o-mini"
    monkeypatch_env = os.environ.get("OPENAI_API_KEY")
    try:
        os.environ.pop("OPENAI_API_KEY", None)
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            exploit_assessor.get_llm("openai")
    finally:
        if monkeypatch_env is not None:
            os.environ["OPENAI_API_KEY"] = monkeypatch_env


def test_deterministic_mode_never_touches_any_provider(monkeypatch, offline_guard):
    def _boom(*_a, **_k):
        raise AssertionError("provider touched in deterministic mode")

    monkeypatch.setattr(assessment_mod, "_try_ollama_assess", _boom)
    monkeypatch.setattr(assessment_mod, "_try_openrouter_assess", _boom)
    monkeypatch.setattr(assessment_mod, "_try_openai_assess", _boom)

    fn = assessment_mod.create_assessor(mode="deterministic")
    res = fn(ActionCandidate(id="X", probability=0.5))
    assert res.source == "deterministic"
    assert res.fallback is False
    assert res.provider is None
    assert offline_guard.call_count == 0


# ---------------------------------------------------------------------------
# 8. Credentials are redacted everywhere they could surface
# ---------------------------------------------------------------------------

def test_redact_strips_literal_secret():
    msg = f"auth failed for key {FAKE_KEY} on model x"
    out = pe.redact(msg, [FAKE_KEY])
    assert FAKE_KEY not in out
    assert pe.REDACTED in out


def test_redact_strips_secretstr():
    out = pe.redact(f"bad key {FAKE_KEY}", [SecretStr(FAKE_KEY)])
    assert FAKE_KEY not in out


def test_redact_strips_key_shapes_we_never_held():
    # A key echoed inside a provider error body we never saw.
    body = "Invalid key: sk-or-abcdefghijklmnop and bearer abcdef1234567890"
    out = pe.redact(body)
    assert "sk-or-abcdefghijklmnop" not in out
    assert "abcdef1234567890" not in out


def test_redact_handles_env_assignment_shape():
    out = pe.redact("OPENROUTER_API_KEY=" + FAKE_KEY)
    assert FAKE_KEY not in out
    out2 = pe.redact('api_key="super-secret-value-999"')
    assert "super-secret-value-999" not in out2


def test_describe_error_never_leaks_the_key(monkeypatch):
    exc = RuntimeError(f"request failed, key={FAKE_KEY}")
    described = pe.describe_error(exc, secrets=[FAKE_KEY], provider="openrouter")
    assert FAKE_KEY not in described
    assert "openrouter" in described
    assert pe.classify_error(exc) == "unknown"


def test_fallback_error_is_redacted(monkeypatch, openrouter_key):
    exc = RuntimeError(f"upstream rejected key {FAKE_KEY}")
    stub = make_stub_chat_openrouter(raise_on_invoke=exc)
    monkeypatch.setattr(exploit_assessor, "ChatOpenRouter", stub)

    fn = assessment_mod.create_assessor(mode="ai", provider="openrouter")
    res = fn(ActionCandidate(id="CVE-2021-44228", probability=0.5))
    assert FAKE_KEY not in (res.error or "")


def test_redact_tolerates_empty_and_none():
    assert pe.redact(None) == ""
    assert pe.redact("") == ""
    assert pe.redact("no secrets here", [None, ""]) == "no secrets here"


# ---------------------------------------------------------------------------
# 9. API surface: schema accepts the provider, key never echoed
# ---------------------------------------------------------------------------

def test_run_request_accepts_openrouter_provider():
    from services.schemas import RunRequest

    req = RunRequest(assessor="llm", assessor_provider="openrouter")
    assert req.assessor_provider == "openrouter"
    # Default remains ollama for an unspecified request.
    assert RunRequest().assessor_provider == "ollama"


def test_run_request_rejects_unknown_provider():
    from services.schemas import RunRequest
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError):
        RunRequest(assessor_provider="azure-fake")


def test_health_reports_openrouter_configuration_without_the_key(
    monkeypatch, client
):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    resp = client.get("/system/health")
    assert resp.status_code == 200
    payload = resp.text
    # Configuration state is visible...
    assert "openrouter" in payload
    # ...but the secret never is.
    assert FAKE_KEY not in payload


def test_assessment_result_to_dict_exposes_provider_and_model(monkeypatch, openrouter_key):
    """Run metadata must show provider + model, never the key."""
    stub = make_stub_chat_openrouter()
    monkeypatch.setattr(exploit_assessor, "ChatOpenRouter", stub)
    monkeypatch.setattr(exploit_assessor, "fetch_github_poc", lambda cve: None)

    fn = assessment_mod.create_assessor(mode="ai", provider="openrouter")
    d = fn(ActionCandidate(id="CVE-2021-44228", probability=0.5)).to_dict()
    assert d["provider"] == "openrouter"
    assert d["model"] == mc.DEFAULT_OPENROUTER_MODEL
    assert FAKE_KEY not in str(d)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
