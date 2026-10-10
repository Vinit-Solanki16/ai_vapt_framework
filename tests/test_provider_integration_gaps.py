"""Provider integration-gap coverage (independent audit follow-up).

Every test here guards a gap found by auditing the OpenRouter change against
the rest of the platform, rather than against the provider in isolation:

  A. OpenAI's LEGACY missing-key semantics must stay untouched, while
     OpenRouter's fail-fast behaviour is intentional and documented.
  B. reports must distinguish a real model assessment from a deterministic
     fallback — provenance that only names provider/model implies an answer
     the model never gave.
  C. env tuning knobs are clamped so a typo cannot create an unbounded
     retry loop or a multi-hour timeout.
  D. model names are validated syntactically (never an allowlist, so
     OPENROUTER_MODEL stays configurable) and malformed ones fail loudly.
  E. the JavaScript payload contract agrees with the Python provider registry
     (frontend/backend drift is silent otherwise).
  F. both GUI forms and the API actually thread provider/model end to end.

Everything is OFFLINE and fully mocked — no live API calls.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import core.exploit_assessor as exploit_assessor
from core.schemas import ExploitAssessment, UsabilityRank
from decision_engine.core.schemas import ActionCandidate
from vapt_platform import assessment as assessment_mod
from vapt_platform import model_config as mc
from vapt_platform import provider_errors as pe
from vapt_platform.reporting.builder import _build_web_provenance
from vapt_platform.reporting.renderers import (
    _render_web_provenance_html,
    _render_web_provenance_markdown,
    _render_web_provenance_txt,
)

FAKE_KEY = "sk-or-test-secret-key-1234567890"

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP_JS = os.path.join(_ROOT, "frontend", "web", "js", "app.js")


def _canned() -> ExploitAssessment:
    return ExploitAssessment(
        exploit_found=True,
        syntax_valid=True,
        os_dependencies="paramiko",
        privileges_required="user",
        network_noise="medium",
        complexity_score=4,
        prerequisites_met=True,
        usability_rank=UsabilityRank.HIGH,
        reasoning="stubbed assessment",
    )


def _stub(payload=None, raise_on_invoke=None):
    """A fresh ChatOpenRouter stand-in recorded at the module boundary."""
    class _Stub:
        last_kwargs = None

        def __init__(self, **kwargs):
            type(self).last_kwargs = kwargs
            self.schema = None

        def with_structured_output(self, schema):
            self.schema = schema
            return self

        def invoke(self, *_args, **_kwargs):
            if raise_on_invoke is not None:
                raise raise_on_invoke
            return payload if payload is not None else _canned()

    return _Stub


# ---------------------------------------------------------------------------
# A. OpenAI legacy semantics vs OpenRouter fail-fast (intentional difference)
# ---------------------------------------------------------------------------
def test_openai_missing_key_still_silently_falls_back(monkeypatch):
    """REGRESSION: the OpenRouter key check must not change OpenAI."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    fn = assessment_mod.create_assessor(mode="ai", provider="openai")
    result = fn(ActionCandidate(id="CVE-2021-44228", probability=0.5))

    assert result.fallback is True
    assert result.provider == "openai"
    assert result.source == "deterministic"


def test_openrouter_missing_key_raises_with_actionable_message(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY") as exc:
        assessment_mod.create_assessor(mode="ai", provider="openrouter")

    message = str(exc.value)
    assert "ollama" in message  # offers the offline path
    assert "No fallback" in message


def test_missing_key_error_classifies_as_auth(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc:
        assessment_mod.create_assessor(mode="ai", provider="openrouter")

    assert pe.classify_error(exc.value) == "auth"
    assert pe.classify_error(exc.value) in pe.ERROR_CATEGORIES


def test_openrouter_missing_key_produces_no_network_call(monkeypatch, offline_guard):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        assessment_mod.create_assessor(mode="ai", provider="openrouter")
    assert offline_guard.call_count == 0


def test_openrouter_success_still_needs_a_key(monkeypatch):
    """With a key present the construction path succeeds."""
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    monkeypatch.setattr(exploit_assessor, "ChatOpenRouter", _stub())
    fn = assessment_mod.create_assessor(mode="ai", provider="openrouter")
    assert callable(fn)


# ---------------------------------------------------------------------------
# B. Reports distinguish model assessment from fallback
# ---------------------------------------------------------------------------
_WEB = {"web": {"target_url": "http://lab.local", "nmap": {"status": "OK",
        "finding_count": 2, "duration_s": 1.5}}}
_AI = {"mode": "ai", "provider": "openrouter", "model": "m"}


def _prov(details):
    return _build_web_provenance(dict(_WEB), {**_AI, "details": details}, [])


def test_report_outcome_model_assessed_when_no_fallback():
    prov = _prov([{"id": "A", "fallback": False, "error": None}])
    assert prov["ai"]["outcome"] == "MODEL ASSESSED"
    assert prov["ai"]["fallback"] is False


def test_report_outcome_flags_deterministic_fallback():
    prov = _prov([{"id": "A", "fallback": True, "error": "openrouter auth: 401"}])
    assert prov["ai"]["outcome"] == "DETERMINISTIC FALLBACK"
    assert prov["ai"]["fallback"] is True
    assert prov["ai"]["fallback_count"] == 1
    assert "401" in prov["ai"]["fallback_detail"]


def test_report_outcome_partial_when_some_candidates_fell_back():
    prov = _prov([
        {"id": "A", "fallback": False, "error": None},
        {"id": "B", "fallback": True, "error": "rate_limit"},
    ])
    assert prov["ai"]["outcome"] == "PARTIAL (1 of 2 fell back)"
    assert prov["ai"]["fallback"] is True
    assert prov["ai"]["detail_count"] == 2


def test_report_outcome_not_recorded_without_details():
    prov = _prov([])
    assert prov["ai"]["outcome"] == "NOT RECORDED"
    assert prov["ai"]["fallback"] is False


def test_every_renderer_shows_the_ai_outcome():
    prov = _prov([{"id": "A", "fallback": True, "error": "openrouter auth: 401"}])
    md = "\n".join(_render_web_provenance_markdown(prov))
    txt = "\n".join(_render_web_provenance_txt(prov))
    html = _render_web_provenance_html(prov)

    for rendered in (md, txt, html):
        assert "DETERMINISTIC FALLBACK" in rendered
        assert "openrouter / m" in rendered


def test_non_web_run_has_no_web_provenance_section():
    assert _build_web_provenance({}, {"mode": "ai"}, []) == {}


def test_report_provenance_never_contains_the_api_key(monkeypatch):
    prov = _prov([{"id": "A", "fallback": True, "error": f"bad key {FAKE_KEY}"}])
    assert FAKE_KEY not in json.dumps(prov)


# ---------------------------------------------------------------------------
# C. env knobs are clamped
# ---------------------------------------------------------------------------
def test_max_retries_is_clamped_to_a_bounded_range(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MAX_RETRIES", "999999")
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    monkeypatch.setattr(exploit_assessor, "ChatOpenRouter", _stub())
    exploit_assessor.get_llm(provider="openrouter")
    assert exploit_assessor._env_int("OPENROUTER_MAX_RETRIES", 2, 0, 5) == 5

    monkeypatch.setenv("OPENROUTER_MAX_RETRIES", "-7")
    assert exploit_assessor._env_int("OPENROUTER_MAX_RETRIES", 2, 0, 5) == 2

    monkeypatch.setenv("OPENROUTER_MAX_RETRIES", "junk")
    assert exploit_assessor._env_int("OPENROUTER_MAX_RETRIES", 2, 0, 5) == 2


def test_timeout_is_clamped(monkeypatch):
    monkeypatch.setenv("OPENROUTER_TIMEOUT_S", "1000000")
    assert exploit_assessor._env_float("OPENROUTER_TIMEOUT_S", 60.0, 1.0, 600.0) == 600.0

    monkeypatch.setenv("OPENROUTER_TIMEOUT_S", "0.01")
    assert exploit_assessor._env_float("OPENROUTER_TIMEOUT_S", 60.0, 1.0, 600.0) == 1.0

    monkeypatch.setenv("OPENROUTER_TIMEOUT_S", "not-a-number")
    assert exploit_assessor._env_float("OPENROUTER_TIMEOUT_S", 60.0, 1.0, 600.0) == 60.0


def test_clamped_values_reach_the_openrouter_client(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    monkeypatch.setenv("OPENROUTER_MAX_RETRIES", "999999")
    monkeypatch.setenv("OPENROUTER_TIMEOUT_S", "999999")
    stub = _stub()
    monkeypatch.setattr(exploit_assessor, "ChatOpenRouter", stub)

    exploit_assessor.get_llm(provider="openrouter")

    assert stub.last_kwargs["max_retries"] == 5
    assert stub.last_kwargs["request_timeout"] == 600_000  # ms


# ---------------------------------------------------------------------------
# D. model names are validated (syntactic, never an allowlist)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["meta llama", "m\ncrafted", "m\rc", "x" * 250,
                                 "ta\tb", "a b/c"])
def test_malformed_model_names_are_rejected(bad):
    with pytest.raises(ValueError, match="Malformed model name"):
        mc.resolve_model("openrouter", bad)


def test_non_string_model_name_is_rejected():
    with pytest.raises(ValueError, match="must be a string"):
        mc.resolve_model("ollama", 123)


def test_unknown_but_wellformed_slug_is_accepted():
    """OPENROUTER_MODEL must stay configurable — no allowlist."""
    assert mc.resolve_model("openrouter", "totally/bogus-model") == "totally/bogus-model"
    assert mc.is_valid_model_name("totally/bogus-model") is True


def test_blank_or_none_falls_back_to_provider_default():
    assert mc.resolve_model("ollama", None) == mc.DEFAULT_OLLAMA_MODEL
    assert mc.resolve_model("ollama", "   ") == mc.DEFAULT_OLLAMA_MODEL
    assert mc.resolve_model("openai", None) == mc.DEFAULT_OPENAI_MODEL


def test_baseline_default_is_never_env_overridable(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "vendor/custom-model")
    assert mc.resolve_model("ollama", None) == mc.DEFAULT_OLLAMA_MODEL
    assert mc.resolve_model("openrouter", None) == "vendor/custom-model"


def test_health_endpoint_default_does_not_raise_on_bad_override(monkeypatch):
    """default_model_for is called by /system/health and must never raise."""
    monkeypatch.setenv("OPENROUTER_MODEL", "bad model")
    assert mc.default_model_for("openrouter") == "bad model"
    with pytest.raises(ValueError, match="Malformed default model"):
        mc.resolve_model("openrouter", None)


def test_all_registered_models_are_valid():
    for provider in mc.KNOWN_PROVIDERS:
        for name in mc.models_for_provider(provider):
            assert mc.is_valid_model_name(name), (provider, name)


# ---------------------------------------------------------------------------
# E. JavaScript <-> Python provider registry agreement
# ---------------------------------------------------------------------------
def _js_provider_models() -> dict[str, list[str]]:
    """Parse PROVIDER_MODELS out of app.js (no JS engine needed).

    Returns ``{provider: [model, ...]}`` in declaration order.
    """
    with open(_APP_JS, encoding="utf-8") as handle:
        source = handle.read()
    block = re.search(
        r"const\s+PROVIDER_MODELS\s*=\s*\{(.*?)\n\};", source, re.S
    )
    assert block, "PROVIDER_MODELS declaration not found in app.js"
    models: dict[str, list[str]] = {}
    for match in re.finditer(r"(\w+)\s*:\s*\[(.*?)\]", block.group(1), re.S):
        provider, body = match.group(1), match.group(2)
        models[provider] = re.findall(r"value:\s*'([^']+)'", body)
    return models


def test_js_exposes_exactly_the_python_provider_set():
    js = _js_provider_models()
    assert set(js) == set(mc.KNOWN_PROVIDERS)


def test_js_default_model_matches_python_default_for_each_provider():
    js = _js_provider_models()
    for provider, values in js.items():
        assert values, provider
        assert values[0] == mc.default_model_for(provider), provider


def test_js_model_lists_agree_with_python_model_lists():
    js = _js_provider_models()
    for provider in mc.KNOWN_PROVIDERS:
        assert js[provider] == list(mc.models_for_provider(provider)), provider


# ---------------------------------------------------------------------------
# F. both GUI forms and the API thread provider/model end to end
# ---------------------------------------------------------------------------
def test_web_app_js_sends_provider_and_model_from_both_forms():
    with open(_APP_JS, encoding="utf-8") as handle:
        source = handle.read()

    assert source.count("assessor_provider:") >= 2   # standard + web run form
    assert source.count("assessor_model:") >= 2
    assert "PROVIDER_MODELS" in source


def test_streamlit_form_exposes_provider_and_model_selects():
    import inspect
    from frontend import app

    source = inspect.getsource(app)
    assert 'st.selectbox' in source
    assert 'assessor_provider' in source
    assert 'assessor_model' in source
    assert 'models_for_provider' in source
    assert 'api_key_env_for' in source  # hosted providers require a key


def test_api_run_request_and_engine_retain_assessor_model():
    from services.schemas import RunRequest

    req = RunRequest(assessor="llm", assessor_provider="openrouter",
                     assessor_model="openai/gpt-4o-mini")
    assert req.assessor_provider == "openrouter"
    assert req.assessor_model == "openai/gpt-4o-mini"
    assert RunRequest().assessor_model is None
    assert RunRequest().assessor_provider == mc.DEFAULT_PROVIDER


def test_api_start_run_passes_assessor_model_to_the_request():
    import inspect

    import services.api

    source = inspect.getsource(services.api)
    # Both request->VAPTRequest adapters must thread the model through.
    assert source.count("assessor_model=req.assessor_model") >= 2


# ---------------------------------------------------------------------------
# Health endpoint: configuration visible, secret never leaked
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("env", ["OPENROUTER_API_KEY", "OPENAI_API_KEY"])
def test_health_never_leaks_a_configured_key(monkeypatch, env):
    from fastapi.testclient import TestClient
    from services.api import app

    monkeypatch.setenv(env, FAKE_KEY)
    resp = TestClient(app).get("/system/health")
    assert resp.status_code == 200
    assert FAKE_KEY not in resp.text


def test_health_stays_200_when_model_override_is_malformed(monkeypatch):
    from fastapi.testclient import TestClient
    from services.api import app

    monkeypatch.setenv("OPENROUTER_MODEL", "bad model")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    resp = TestClient(app).get("/system/health")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload.get("openrouter_model") is None
    assert "openrouter_model_error" in payload


# ---------------------------------------------------------------------------
# Guardrails: defaults and non-goals
# ---------------------------------------------------------------------------
def test_default_provider_and_baseline_are_unchanged():
    assert mc.DEFAULT_PROVIDER == "ollama"
    assert mc.DEFAULT_OLLAMA_MODEL == "llama3.2:3b"
    assert mc.DEFAULT_OPENROUTER_MODEL == "meta-llama/llama-3.3-70b-instruct"


def test_openrouter_is_never_selected_implicitly():
    # The default resolution path for an unspecified provider is Ollama.
    assert mc.default_model_for(None) == mc.DEFAULT_OLLAMA_MODEL
    assert mc.default_model_for("unknown") == mc.DEFAULT_OLLAMA_MODEL
    assert mc.is_known_provider("ollama")
    assert not mc.is_known_provider("azure-fake")


def test_describe_error_redacts_the_secret(monkeypatch):
    detail = pe.describe_error(
        RuntimeError(f"401 with key {FAKE_KEY}"), provider="openrouter"
    )
    assert FAKE_KEY not in detail
    assert pe.REDACTED in detail


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
