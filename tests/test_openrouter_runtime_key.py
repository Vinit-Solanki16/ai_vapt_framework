"""In-GUI OpenRouter runtime credential setup coverage.

Scope — every test is OFFLINE and fully mocked (no live API calls, no key is
ever pasted into a test, a terminal or an agent):

  1. KEY LIFECYCLE   — in-memory only; never persisted, never logged,
                       never written to os.environ; gone on reload.
  2. TRANSPORT       — the credential rides the ``X-OpenRouter-API-Key``
                       header, never the JSON body, never the URL.
  3. VALIDATION      — authenticated *catalogue* request only (never a
                       completion); every documented status reachable.
  4. FREE MODELS     — free determined from documented pricing only;
                       a paid model is never selected implicitly.
  5. UI GATING       — a run cannot start on an unvalidated credential, and
                       the setup panel is revealed instead.
  6. RUN THREADING   — the header key reaches this run's in-memory
                       VAPTRequest and nothing else.
  7. ISOLATION       — one browser session's key never reaches another.
  8. UNCHANGED ARMS  — Ollama default, baseline model and deterministic
                       fallback semantics are untouched.

Research integrity: OpenRouter remains a separate, opt-in run arm. No
historical baseline result is affected by anything in this module.
"""
from __future__ import annotations

import inspect
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from vapt_platform import model_config as mc
from vapt_platform import openrouter_setup as ors

FAKE_KEY = "sk-or-v1-0123456789abcdef0123456789abcdef0123456789abcdef"
FREE_MODEL = "meta-llama/llama-3.3-70b-instruct"
FREE_ROUTER = "openrouter/free"
PAID_MODEL = "openai/gpt-4o"
#: A model id that the live catalogue no longer returns (verified: removed
#: from OpenRouter). Used to prove stale ids are reported, not assumed.
STALE_MODEL = "anthropic/claude-3.5-haiku"


# ---------------------------------------------------------------------------
# Helpers: a recorded, fully offline transport
# ---------------------------------------------------------------------------

class RecordingTransport:
    """Offline Transport seam. Never touches the network."""

    def __init__(self, responses):
        """``responses`` maps a URL path suffix -> (status, payload)."""
        self.responses = responses
        self.calls: list[tuple] = []

    def __call__(self, method, url, headers, timeout):
        self.calls.append((method, url, dict(headers), timeout))
        for suffix, response in self.responses.items():
            if url.endswith(suffix):
                return response
        raise AssertionError(f"unexpected URL requested: {url}")

    @property
    def urls(self) -> list[str]:
        return [c[1] for c in self.calls]


def _catalogue(*models) -> dict:
    """Build a ModelsListResponse envelope from (id, prompt, completion)."""
    data = []
    for model_id, prompt, completion in models:
        data.append({
            "id": model_id,
            "name": model_id,
            "pricing": {"prompt": prompt, "completion": completion},
            "context_length": 8192,
        })
    return {"data": data}


LIVE_CATALOGUE = _catalogue(
    (FREE_ROUTER, "0", "0"),
    (FREE_MODEL, "0", "0"),
    ("z-ai/z-ai-glm", "0", "0"),
    (PAID_MODEL, "0.000003", "0.000015"),
    ("openai/gpt-4o-mini", "0.00015", "0.0006"),
)


def ok_transport():
    return RecordingTransport({
        "/models/user": (200, LIVE_CATALOGUE),
        "/auth/key": (200, {"data": {"label": "test"}}),
        "/models": (200, LIVE_CATALOGUE),
    })


# ===========================================================================
# 1. KEY LIFECYCLE — in-memory only, never persisted
# ===========================================================================
class TestKeyLifecycle:
    def test_runtime_header_constant(self):
        assert ors.RUNTIME_KEY_HEADER == "X-OpenRouter-API-Key"

    def test_no_key_reports_not_configured(self):
        result = ors.validate_runtime_key(None)
        assert result["status"] == ors.STATUS_NOT_CONFIGURED
        assert result["models"] == []

    def test_blank_key_makes_no_network_call(self):
        transport = RecordingTransport({})
        result = ors.validate_runtime_key("   ", transport=transport)
        assert result["status"] == ors.STATUS_NOT_CONFIGURED
        assert transport.calls == []

    def test_setup_module_never_writes_to_os_environ(self):
        source = inspect.getsource(ors)
        assert "os.environ[" not in source
        assert "os.putenv" not in source
        # The module may READ the base URL from the environment, but must
        # never assign into it.
        for line in source.splitlines():
            if "environ" in line:
                assert "=" not in line.split("environ", 1)[1], line

    def test_api_module_never_writes_the_runtime_key_to_os_environ(self):
        import services.api

        source = inspect.getsource(services.api)
        assert "os.environ[" not in source
        assert "os.putenv" not in source

    def test_validation_leaves_the_environment_untouched(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        before = dict(os.environ)
        ors.validate_runtime_key(FAKE_KEY, transport=ok_transport())
        assert dict(os.environ) == before
        assert os.getenv("OPENROUTER_API_KEY") is None

    @pytest.mark.parametrize(
        "status,code",
        [
            (ors.STATUS_CONFIGURED, 200),
            (ors.STATUS_INVALID_CREDENTIALS, 401),
            (ors.STATUS_RATE_LIMITED, 429),
            (ors.STATUS_UNREACHABLE, 500),
        ],
    )
    def test_no_result_ever_contains_the_key(self, status, code):
        transports = {
            200: {"/models/user": (200, LIVE_CATALOGUE)},
            401: {"/models/user": (401, {"error": FAKE_KEY})},
            429: {"/models/user": (429, {"error": "rate limited"})},
            500: {"/models/user": (500, {"error": "boom"})},
        }
        result = ors.validate_runtime_key(FAKE_KEY, FREE_MODEL,
                                          transport=RecordingTransport(transports[code]))
        assert result["status"] == status
        blob = json.dumps(result)
        assert FAKE_KEY not in blob
        assert "Bearer " not in blob
        # And every string anywhere in the result is free of key material.
        def walk(node):
            if isinstance(node, dict):
                for v in node.values():
                    yield from walk(v)
            elif isinstance(node, list):
                for v in node:
                    yield from walk(v)
            elif isinstance(node, str):
                yield node
        for text in walk(result):
            assert FAKE_KEY not in text
            assert "sk-or-" not in text

    def test_result_shape_matches_the_documented_contract(self):
        result = ors.validate_runtime_key(FAKE_KEY, FREE_MODEL,
                                          transport=ok_transport())
        for field in ("status", "message", "models", "model",
                      "model_available", "catalogue_count"):
            assert field in result

    def test_key_is_not_a_response_field_of_the_schema(self):
        from services.schemas import OpenRouterValidateResponse, OpenRouterValidateRequest

        for model in (OpenRouterValidateRequest, OpenRouterValidateResponse):
            assert "key" not in model.model_fields
            assert "api_key" not in model.model_fields
            assert "secret" not in model.model_fields
            assert "token" not in model.model_fields
        assert list(OpenRouterValidateRequest.model_fields) == ["model"]

    def test_session_isolation_two_sessions_do_not_share_a_key(self):
        # Browser sessions are separate objects; the module is stateless, so
        # validating for session A must not influence session B's result.
        a = ors.validate_runtime_key(FAKE_KEY, transport=ok_transport())
        b = ors.validate_runtime_key(None)
        assert a["status"] == ors.STATUS_CONFIGURED
        assert b["status"] == ors.STATUS_NOT_CONFIGURED
        # ...and validating A must not have stored A's key anywhere global.
        assert not hasattr(ors, "VALIDATED_KEY")
        assert FAKE_KEY not in json.dumps(b)


# ===========================================================================
# 2. TRANSPORT — header only, never body/URL
# ===========================================================================
class TestTransport:
    def test_key_travels_in_an_authorization_header(self):
        transport = ok_transport()
        ors.validate_runtime_key(FAKE_KEY, transport=transport)
        method, url, headers, _ = transport.calls[0]
        assert method == "GET"
        assert headers["Authorization"] == f"Bearer {FAKE_KEY}"

    def test_key_never_appears_in_the_requested_url(self):
        transport = ok_transport()
        ors.validate_runtime_key(FAKE_KEY, FREE_MODEL, transport=transport)
        for url in transport.urls:
            assert FAKE_KEY not in url
            assert "key=" not in url

    def test_validation_never_issues_a_completion(self):
        transport = ok_transport()
        ors.validate_runtime_key(FAKE_KEY, transport=transport)
        for url in transport.urls:
            lowered = url.lower()
            for forbidden in ("/chat/completions", "/messages", "/completions",
                              "/generate"):
                assert forbidden not in lowered, url
        # Only catalogue/auth endpoints are ever hit.
        allowed = ("/api/v1/models/user", "/api/v1/auth/key", "/api/v1/models")
        for url in transport.urls:
            assert any(url.endswith(p) for p in allowed), url

    def test_api_validate_endpoint_reads_the_header_not_the_body(self):
        """A key smuggled in the JSON body must be ignored entirely."""
        from fastapi.testclient import TestClient
        import services.api

        seen = {}

        def fake_validate(api_key, requested_model=None, *, timeout=None,
                          transport=None):
            seen["key"] = api_key
            seen["model"] = requested_model
            return {"status": "not_configured", "models": [],
                    "model": None, "model_available": None,
                    "catalogue_count": 0}

        original = None
        import vapt_platform.openrouter_setup as setup_mod
        original = setup_mod.validate_runtime_key
        setup_mod.validate_runtime_key = fake_validate
        try:
            client = TestClient(services.api.app)
            resp = client.post(
                "/providers/openrouter/validate",
                json={"model": FREE_MODEL, "assessor_api_key": FAKE_KEY,
                      "key": FAKE_KEY, "api_key": FAKE_KEY},
                headers={ors.RUNTIME_KEY_HEADER: ""},
            )
            assert resp.status_code == 200
            # The body field is not even part of the schema; the header (empty
            # here) is what reaches the validator.
            assert seen["key"] in (None, "")
            assert seen["model"] == FREE_MODEL
        finally:
            setup_mod.validate_runtime_key = original

    def test_api_validate_endpoint_passes_the_header_key_through(self):
        from fastapi.testclient import TestClient
        import services.api
        import vapt_platform.openrouter_setup as setup_mod

        seen = {}

        def fake_validate(api_key, requested_model=None, *, timeout=None,
                          transport=None):
            seen["key"] = api_key
            return {"status": "configured", "models": [], "model": None,
                    "model_available": None, "catalogue_count": 0}

        original = setup_mod.validate_runtime_key
        setup_mod.validate_runtime_key = fake_validate
        try:
            resp = TestClient(services.api.app).post(
                "/providers/openrouter/validate",
                json={},
                headers={ors.RUNTIME_KEY_HEADER: FAKE_KEY},
            )
            assert resp.status_code == 200
            assert seen["key"] == FAKE_KEY
        finally:
            setup_mod.validate_runtime_key = original


# ===========================================================================
# 3. VALIDATION STATES — every documented status, all offline
# ===========================================================================
class TestValidationStates:
    def test_valid_key_with_requested_model_is_configured(self):
        result = ors.validate_runtime_key(
            FAKE_KEY, FREE_MODEL, transport=ok_transport())
        assert result["status"] == ors.STATUS_CONFIGURED
        assert result["model"] == FREE_MODEL
        assert result["model_available"] is True
        assert result["catalogue_count"] == len(LIVE_CATALOGUE["data"])

    def test_valid_key_without_a_model_is_configured(self):
        result = ors.validate_runtime_key(FAKE_KEY, transport=ok_transport())
        assert result["status"] == ors.STATUS_CONFIGURED
        assert result["model_available"] is None

    def test_401_is_invalid_credentials(self):
        transport = RecordingTransport({"/models/user": (401, {"error": "bad key"})})
        result = ors.validate_runtime_key(FAKE_KEY, transport=transport)
        assert result["status"] == ors.STATUS_INVALID_CREDENTIALS
        assert result["models"] == []

    def test_429_is_rate_limited(self):
        transport = RecordingTransport({"/models/user": (429, {"error": "slow down"})})
        result = ors.validate_runtime_key(FAKE_KEY, transport=transport)
        assert result["status"] == ors.STATUS_RATE_LIMITED

    def test_network_failure_is_unreachable_not_invalid(self):
        def boom(method, url, headers, timeout):
            raise OSError("connection refused")

        result = ors.validate_runtime_key(FAKE_KEY, transport=boom)
        assert result["status"] == ors.STATUS_UNREACHABLE
        # Crucially NOT an auth failure: a network blip must not tell the
        # user their key is bad.
        assert result["status"] != ors.STATUS_INVALID_CREDENTIALS

    def test_403_falls_back_to_auth_key_plus_public_catalogue(self):
        # An ordinary (non-management) key gets 403 from /models/user.
        transport = RecordingTransport({
            "/models/user": (403, {"error": "management only"}),
            "/auth/key": (200, {"data": {"label": "t"}}),
            "/models": (200, LIVE_CATALOGUE),
        })
        result = ors.validate_runtime_key(FAKE_KEY, FREE_MODEL,
                                          transport=transport)
        assert result["status"] == ors.STATUS_CONFIGURED
        assert transport.urls[0].endswith("/models/user")
        assert transport.urls[1].endswith("/auth/key")
        assert transport.urls[2].endswith("/models")

    def test_403_with_a_bad_key_is_still_invalid_credentials(self):
        transport = RecordingTransport({
            "/models/user": (403, {"error": "nope"}),
            "/auth/key": (401, {"error": "bad key"}),
        })
        result = ors.validate_runtime_key(FAKE_KEY, transport=transport)
        assert result["status"] == ors.STATUS_INVALID_CREDENTIALS

    @pytest.mark.parametrize("body", [
        {}, {"data": "not-a-list"}, {"data": [1, 2, 3]}, {"data": []},
        None, [],
    ])
    def test_unusable_catalogue_body_is_unreachable_not_configured(self, body):
        transport = RecordingTransport({"/models/user": (200, body)})
        result = ors.validate_runtime_key(FAKE_KEY, transport=transport)
        assert result["status"] == ors.STATUS_UNREACHABLE

    def test_malformed_key_is_rejected_before_any_network_call(self):
        transport = RecordingTransport({})
        result = ors.validate_runtime_key(
            "sk-or-v1-abc\nSECRET", transport=transport)
        assert result["status"] == ors.STATUS_INVALID_CREDENTIALS
        assert transport.calls == []
        assert "whitespace" in result["message"].lower() or \
               "space" in result["message"].lower()

    @pytest.mark.parametrize("bad", ["", "x" * 600, "a b", "a\tb", "a\x00b"])
    def test_overlong_or_control_keyed_values_are_rejected(self, bad):
        transport = RecordingTransport({})
        result = ors.validate_runtime_key(bad, transport=transport)
        assert transport.calls == []
        assert result["status"] in (
            ors.STATUS_NOT_CONFIGURED, ors.STATUS_INVALID_CREDENTIALS)

    def test_stale_model_id_is_reported_as_unavailable(self):
        result = ors.validate_runtime_key(FAKE_KEY, STALE_MODEL,
                                          transport=ok_transport())
        assert result["status"] == ors.STATUS_MODEL_UNAVAILABLE
        assert result["model_available"] is False
        assert result["model"] == STALE_MODEL
        # The catalogue is still returned so the UI can offer alternatives.
        assert result["models"], "unavailable model must still return the list"

    def test_malformed_model_id_is_not_silently_accepted(self):
        result = ors.validate_runtime_key(FAKE_KEY, "not a valid model id",
                                          transport=ok_transport())
        assert result["status"] == ors.STATUS_MODEL_UNAVAILABLE

    def test_every_status_has_actionable_help_text(self):
        for status in ors.SETUP_STATUSES:
            assert ors.HELP_TEXT.get(status), status

    @pytest.mark.parametrize("status", ors.SETUP_STATUSES)
    def test_help_text_never_contains_a_key_shape(self, status):
        assert "sk-or-" not in ors.HELP_TEXT[status]


# ===========================================================================
# 4. FREE MODELS — pricing is the only source of truth
# ===========================================================================
class TestFreeModelHandling:
    def test_free_requires_zero_prompt_and_zero_completion(self):
        assert ors.is_free_pricing({"prompt": "0", "completion": "0"})
        assert ors.is_free_pricing({"prompt": "0.0", "completion": "0.0"})
        assert not ors.is_free_pricing({"prompt": "0", "completion": "1e-6"})
        assert not ors.is_free_pricing({"prompt": "1e-6", "completion": "0"})

    def test_free_is_not_inferred_from_the_name(self):
        # A ":free" NAME with paid pricing is not free.
        assert not ors.is_free_pricing(
            {"prompt": "0.000003", "completion": "0.000015"})

    @pytest.mark.parametrize("pricing", [None, "free", 0, {}, {"prompt": "0"}])
    def test_missing_pricing_is_never_treated_as_free(self, pricing):
        assert not ors.is_free_pricing(pricing)

    def test_parse_catalogue_marks_free_and_paid(self):
        models = {m["id"]: m for m in ors.parse_catalogue(LIVE_CATALOGUE)}
        assert models[FREE_ROUTER]["free"] is True
        assert models[FREE_ROUTER]["paid"] is False
        assert models[PAID_MODEL]["free"] is False
        assert models[PAID_MODEL]["paid"] is True

    def test_parse_catalogue_tolerates_garbage_without_raising(self):
        assert ors.parse_catalogue(None) == []
        assert ors.parse_catalogue({"data": None}) == []
        assert ors.parse_catalogue({"data": [None, 3, {}, {"id": ""}]}) == []
        assert ors.parse_catalogue("nonsense") == []

    def test_sort_models_puts_free_first(self):
        models = ors.sort_models(ors.parse_catalogue(LIVE_CATALOGUE))
        free_ids = [m["id"] for m in models if m["free"]]
        paid_ids = [m["id"] for m in models if m["paid"]]
        # Every free entry precedes every paid entry.
        first_paid = next(i for i, m in enumerate(models) if m["paid"])
        last_free = len(free_ids) - 1
        assert first_paid > last_free
        # ...and each group is alphabetical.
        assert free_ids == sorted(free_ids)
        assert paid_ids == sorted(paid_ids)

    def test_catalogue_returned_by_validation_is_free_first(self):
        result = ors.validate_runtime_key(FAKE_KEY, transport=ok_transport())
        models = result["models"]
        first_paid = next((i for i, m in enumerate(models) if m["paid"]),
                          len(models))
        assert all(not m["paid"] for m in models[:first_paid])
        assert all(m["paid"] for m in models[first_paid:])
        # Within each group the ids are alphabetical; the FREE-ROUTER
        # preference is applied separately by pick_default_model.
        assert ors.pick_default_model(models) == FREE_ROUTER

    def test_the_stale_id_used_by_the_suite_is_genuinely_absent(self):
        # Guards the unavailable-model test against a fixture that quietly
        # starts advertising a model the real catalogue has dropped.
        ids = {m["id"] for m in ors.parse_catalogue(LIVE_CATALOGUE)}
        assert STALE_MODEL not in ids
        assert STALE_MODEL in mc.OPENROUTER_MODELS

    def test_default_model_prefers_the_free_router(self):
        models = ors.sort_models(ors.parse_catalogue(LIVE_CATALOGUE))
        assert ors.pick_default_model(models) == FREE_ROUTER

    def test_default_model_falls_back_to_the_first_free_entry(self):
        models = ors.sort_models(ors.parse_catalogue(
            _catalogue(("a/free-ish", "0", "0"), (PAID_MODEL, "1", "2"))))
        assert ors.pick_default_model(models) == "a/free-ish"

    def test_default_model_is_none_when_nothing_is_free(self):
        models = ors.parse_catalogue(
            _catalogue((PAID_MODEL, "1", "2"), ("openai/gpt-4o", "1", "2")))
        # NEVER selects a paid model implicitly.
        assert ors.pick_default_model(models) is None

    def test_default_model_of_an_empty_catalogue_is_none(self):
        assert ors.pick_default_model([]) is None

    def test_validation_does_not_choose_a_paid_model_for_the_user(self):
        result = ors.validate_runtime_key(
            FAKE_KEY, transport=RecordingTransport({
                "/models/user": (200, _catalogue(
                    (PAID_MODEL, "0.000003", "0.000015")))}) )
        # With no requested model and nothing free available, no model is
        # chosen on the user's behalf.
        assert result["model"] is None
        assert ors.pick_default_model(result["models"]) is None

    def test_catalogue_is_capped(self):
        big = _catalogue(*[(f"vendor-{i:04d}/model", "0", "0")
                           for i in range(ors.MAX_MODELS_RETURNED + 500)])
        transport = RecordingTransport({"/models/user": (200, big)})
        result = ors.validate_runtime_key(FAKE_KEY, transport=transport)
        assert len(result["models"]) == ors.MAX_MODELS_RETURNED

    def test_pricing_display_is_derived_not_invented(self):
        models = {m["id"]: m for m in ors.parse_catalogue(LIVE_CATALOGUE)}
        paid = models[PAID_MODEL]["pricing"]
        assert paid["prompt_per_million"] == "3"
        assert paid["completion_per_million"] == "15"
        assert models[FREE_ROUTER]["pricing"]["prompt_per_million"] == "0"


# ===========================================================================
# 5. UI GATING — no run on an unvalidated credential
# ===========================================================================
class TestUiGating:
    @staticmethod
    def _js():
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "frontend", "web", "js", "app.js")
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_setup_panel_markup_exists(self):
        js = self._js()
        for element_id in ("openrouter-setup", "or-key", "or-model",
                           "or-validate", "or-use", "or-clear", "or-help",
                           "or-status-badge"):
            assert f'id="{element_id}"' in js, element_id

    def test_both_start_functions_are_gated(self):
        js = self._js()
        assert js.count("openRouterGateError") >= 3  # def + 2 call sites
        assert "async function startAssessment()" in js
        assert "async function startWebAssessment()" in js

    def test_gate_reveals_the_panel_instead_of_dispatching(self):
        js = self._js()
        # Inside each gate the code must return BEFORE any startRun call.
        for fn in ("startAssessment", "startWebAssessment"):
            start = js.index(f"async function {fn}()")
            body = js[start:start + 4000]
            gate_at = body.index("openRouterGateError()")
            # The gate block must contain an early `return`.
            gate_block = body[gate_at:gate_at + 900]
            assert "return;" in gate_block, fn
            # ...and must reveal the setup panel.
            assert "openrouter-setup" in gate_block, fn

    def test_key_is_only_sent_as_a_header(self):
        js = self._js()
        assert "openrouterKeyHeaders()" in js
        assert "X-OpenRouter-API-Key" in js
        # The credential is never placed into the JSON body object.
        assert '"assessor_api_key"' not in js
        assert "assessor_api_key:" not in js

    def test_header_only_attached_for_the_openrouter_provider(self):
        js = self._js()
        assert "provider === 'openrouter'" in js or \
               "webProvider === 'openrouter'" in js
        assert "api.startRun(data, headers)" in js or \
               "api.startRun(data, webHeaders)" in js

    def test_browser_storage_is_never_used(self):
        import re

        js = self._js()
        # Strip comments first: the source is allowed to SAY we do not use
        # these APIs (the banner does, deliberately); it is the CALLS —
        # member access / assignment — that must not exist.
        code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
        code = re.sub(r"//[^\n]*", "", code)
        patterns = {
            "localStorage": r"\blocalStorage\s*[.[]",
            "sessionStorage": r"\bsessionStorage\s*[.[]",
            "indexedDB": r"\bindexedDB\s*[.[]",
            "window.localStorage": r"window\s*\.\s*localStorage",
            "window.sessionStorage": r"window\s*\.\s*sessionStorage",
            "document.cookie": r"document\s*[.\[]\s*['\"]?cookie",
            "window.name": r"window\s*\.\s*name\s*=",
        }
        for label, pattern in patterns.items():
            assert not re.search(pattern, code), f"{label} is used"

    def test_no_element_assigns_the_key_to_the_dom(self):
        js = self._js()
        # The key input must be type=password and never echoed anywhere.
        assert 'type="password"' in js
        assert "textContent = or.key" not in js
        assert "innerHTML = or.key" not in js
        assert "innerHTML += or.key" not in js

    def test_forget_clears_the_key_and_everything_derived(self):
        js = self._js()
        start = js.index("function clearOpenRouterKey()")
        block = js[start:start + 300]
        # A full session reset — nothing derived from the key survives.
        assert "createOpenRouterSession()" in block
        body = js[js.index("function createOpenRouterSession()"):
                  js.index("function createOpenRouterSession()") + 900]
        assert "key: null" in body
        assert "selectedModel: null" in body
        assert "userSelectedModel: null" in body
        assert "validatedModel: null" in body
        assert "status: 'not_configured'" in body
        assert "key: null" in body

    def test_a_paid_model_is_not_chosen_silently_after_validation(self):
        js = self._js()
        assert "or.userSelectedModel" in js
        # The post-validation default path must go through the free-first
        # picker rather than keeping a paid selection.
        start = js.index("async function validateOpenRouterSetup(")
        block = js[start:start + 3000]
        assert "pickDefaultOpenRouterModel()" in block
        assert "if (!or.userSelectedModel)" in block

    def test_paid_model_selection_is_warned_about(self):
        js = self._js()
        assert "or-pricing-warning" in js
        assert "PAID" in js

    def test_status_labels_cover_every_setup_status(self):
        js = self._js()
        for status in ors.SETUP_STATUSES:
            if status == ors.STATUS_VALIDATING:
                continue  # client-side transient, rendered by the button
            assert status in js, status

    def test_validation_is_not_the_same_as_dispatching_a_run(self):
        js = self._js()
        # Validate must call the validate endpoint only.
        start = js.index("async function validateOpenRouterSetup(")
        block = js[start:start + 3000]
        assert "validateOpenRouter" in block
        assert "startRun" not in block


# ===========================================================================
# 6. RUN THREADING — header key reaches this run's VAPTRequest only
# ===========================================================================
class TestRunThreading:
    @staticmethod
    def _fake_application(captured):
        from types import SimpleNamespace

        domain = SimpleNamespace(
            run_id="run-test-1",
            scenario="failure_pivot",
            mode="simulation",
            final_status="completed",
            candidates=[],
            service_discovery=[],
            execution_results=[],
            decision_trace=[],
            total_attempts=0,
            pivot_count=0,
            candidates_processed=0,
            evidence_tier="none",
            assessment=None,
            safety_notice="",
        )
        application = SimpleNamespace()

        def run(request):
            captured.append(request)
            return SimpleNamespace(domain=domain, report={})

        application.run = run
        return application

    def test_header_key_reaches_the_in_memory_request(self, monkeypatch):
        from fastapi.testclient import TestClient
        import services.api

        captured: list = []
        monkeypatch.setattr(services.api, "get_application",
                            lambda: self._fake_application(captured))
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        resp = TestClient(services.api.app).post(
            "/runs",
            json={"scenario": "failure_pivot", "mode": "simulation",
                  "assessor": "deterministic",
                  "assessor_provider": "openrouter"},
            headers={ors.RUNTIME_KEY_HEADER: FAKE_KEY},
        )
        assert resp.status_code == 200
        assert len(captured) == 1
        assert captured[0].assessor_api_key == FAKE_KEY
        assert captured[0].assessor_provider == "openrouter"

    def test_header_key_is_not_written_to_the_environment(self, monkeypatch):
        from fastapi.testclient import TestClient
        import services.api

        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        captured: list = []
        monkeypatch.setattr(services.api, "get_application",
                            lambda: self._fake_application(captured))
        TestClient(services.api.app).post(
            "/runs",
            json={"scenario": "failure_pivot", "mode": "simulation"},
            headers={ors.RUNTIME_KEY_HEADER: FAKE_KEY},
        )
        assert os.getenv("OPENROUTER_API_KEY") is None
        assert "OPENROUTER_API_KEY" not in os.environ

    def test_header_key_is_not_echoed_back_in_the_run_response(self, monkeypatch):
        from fastapi.testclient import TestClient
        import services.api

        captured: list = []
        monkeypatch.setattr(services.api, "get_application",
                            lambda: self._fake_application(captured))
        resp = TestClient(services.api.app).post(
            "/runs",
            json={"scenario": "failure_pivot", "mode": "simulation"},
            headers={ors.RUNTIME_KEY_HEADER: FAKE_KEY},
        )
        assert resp.status_code == 200
        assert FAKE_KEY not in resp.text

    def test_run_state_kept_by_the_job_manager_has_no_key(self, monkeypatch):
        from fastapi.testclient import TestClient
        import services.api
        from services.jobs import job_manager

        captured: list = []
        monkeypatch.setattr(services.api, "get_application",
                            lambda: self._fake_application(captured))
        TestClient(services.api.app).post(
            "/runs",
            json={"scenario": "failure_pivot", "mode": "simulation"},
            headers={ors.RUNTIME_KEY_HEADER: FAKE_KEY},
        )
        state = job_manager.get("run-test-1")
        assert FAKE_KEY not in json.dumps(state, default=str)

    def test_body_key_still_works_for_cli_callers_but_is_never_persisted(
            self, monkeypatch):
        from fastapi.testclient import TestClient
        import services.api

        captured: list = []
        monkeypatch.setattr(services.api, "get_application",
                            lambda: self._fake_application(captured))
        resp = TestClient(services.api.app).post(
            "/runs",
            json={"scenario": "failure_pivot", "mode": "simulation",
                  "assessor_api_key": FAKE_KEY},
        )
        assert resp.status_code == 200
        assert captured[0].assessor_api_key == FAKE_KEY
        assert FAKE_KEY not in resp.text

    def test_failed_run_error_detail_redacts_the_runtime_key(self, monkeypatch):
        from fastapi.testclient import TestClient
        import services.api

        def explode(request):
            raise RuntimeError(
                f"provider said 401 unauthorized for Bearer {FAKE_KEY}")

        captured: list = []
        fake = self._fake_application(captured)
        fake.run = explode
        monkeypatch.setattr(services.api, "get_application", lambda: fake)

        resp = TestClient(services.api.app).post(
            "/runs",
            json={"scenario": "failure_pivot", "mode": "simulation"},
            headers={ors.RUNTIME_KEY_HEADER: FAKE_KEY},
        )
        assert resp.status_code == 500
        assert FAKE_KEY not in resp.text

    def test_assessor_api_key_is_not_a_persisted_or_reported_field(self):
        import vapt_platform.persistence.models as persistence_models
        import vapt_platform.reporting.builder as builder

        for module in (persistence_models, builder):
            source = inspect.getsource(module)
            assert "assessor_api_key" not in source, module.__name__

    def test_vapt_request_carries_the_key_as_a_plain_in_memory_field(self):
        from vapt_platform.application import VAPTRequest

        request = VAPTRequest(assessor_api_key=FAKE_KEY)
        assert request.assessor_api_key == FAKE_KEY
        # Not a FileField / path / anything that could be written out.
        assert not isinstance(request.assessor_api_key, (bytes, bytearray))


# ===========================================================================
# 7. STATUS ENDPOINT — state only, never a secret
# ===========================================================================
class TestStatusEndpoint:
    def test_status_reports_configuration_not_secrets(self, monkeypatch):
        from fastapi.testclient import TestClient
        import services.api

        monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
        resp = TestClient(services.api.app).get("/providers/openrouter/status")
        assert resp.status_code == 200
        payload = resp.json()
        assert FAKE_KEY not in resp.text
        assert payload["provider"] == "openrouter"
        assert payload["runtime_key_header"] == ors.RUNTIME_KEY_HEADER
        assert payload["runtime_key_supported"] is True
        assert "key_value" not in payload
        assert "runtime_key" not in payload

    def test_status_reports_env_presence_without_the_value(self, monkeypatch):
        from fastapi.testclient import TestClient
        import services.api

        monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
        payload = TestClient(services.api.app).get(
            "/providers/openrouter/status").json()
        assert payload["env_key_configured"] is True
        assert payload["env_key_env"] == "OPENROUTER_API_KEY"

    def test_status_without_env_key(self, monkeypatch):
        from fastapi.testclient import TestClient
        import services.api

        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        payload = TestClient(services.api.app).get(
            "/providers/openrouter/status").json()
        assert payload["env_key_configured"] is False

    def test_validate_endpoint_returns_not_configured_without_a_header(self):
        from fastapi.testclient import TestClient
        import services.api

        resp = TestClient(services.api.app).post(
            "/providers/openrouter/validate", json={})
        assert resp.status_code == 200
        assert resp.json()["status"] == ors.STATUS_NOT_CONFIGURED


# ===========================================================================
# 8. STREAMLIT FRONTEND — session state only, gated run
# ===========================================================================
class TestStreamlitFrontend:
    @staticmethod
    def _source():
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "frontend", "app.py")
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_setup_panel_function_exists(self):
        assert "def _openrouter_setup_panel(" in self._source()
        assert "def forget_openrouter_key(" in self._source()

    def test_key_field_is_masked(self):
        source = self._source()
        assert 'type="password"' in source
        assert 'autocomplete="off"' in source

    def test_key_lives_in_session_state_only(self):
        source = self._source()
        assert "st.session_state" in source
        assert 'st.session_state.openrouter_setup = {' in source
        # Nothing about the key may touch disk or the process environment.
        assert 'os.environ["OPENROUTER_API_KEY"]' not in source
        assert "os.environ['OPENROUTER_API_KEY']" not in source
        assert "os.putenv" not in source
        # The key is only ever handed to the in-memory VAPTRequest.
        assert "assessor_api_key=runtime_key" in source
        for line in source.splitlines():
            if "runtime_key" in line and "os.environ" in line:
                raise AssertionError(line)

    def test_forget_key_deletes_it_from_the_session(self):
        source = self._source()
        start = source.index("def forget_openrouter_key()")
        block = source[start:start + 400]
        assert 'st.session_state.pop("openrouter_setup", None)' in block
        assert 'st.session_state.pop("openrouter_key_input", None)' in block

    def test_panel_exposes_validate_continue_and_forget(self):
        source = self._source()
        for label in ("Validate Connection", "Use OpenRouter", "Forget Key"):
            assert label in source, label

    def test_every_setup_status_has_a_visible_label(self):
        source = self._source()
        for status in ors.SETUP_STATUSES:
            assert status in source, status

    def test_run_is_gated_on_a_validated_credential(self):
        source = self._source()
        assert '_or.get("status") == "configured"' in source
        assert "st.stop()" in source

    def test_gate_message_is_actionable_and_does_not_downgrade(self):
        source = self._source()
        marker = "**OpenRouter** is selected but no credential is available."
        assert marker in source
        start = source.index(marker)
        block = source[start - 400:start + 1400]
        assert "will not silently switch providers" in block
        assert "OpenRouter Setup" in block
        assert "Validate Connection" in block
        assert "Ollama" in block
        # The gate stops the run rather than continuing.
        assert "st.stop()" in block
        # ...and it fires before the request is built.
        build = source.index("request = VAPTRequest(")
        assert start < build

    def test_runtime_key_is_passed_into_the_request_not_the_env(self):
        source = self._source()
        assert "assessor_api_key=runtime_key" in source
        assert "runtime_key: Optional[str] = None" in source

    def test_panel_is_rendered_only_for_the_openrouter_provider(self):
        source = self._source()
        assert 'if assessor_provider == "openrouter":' in source
        assert "_openrouter_setup_panel(assessor_model)" in source

    def test_no_line_assigns_any_variable_named_key_into_os_environ(self):
        for line in self._source().splitlines():
            stripped = line.strip()
            if stripped.startswith("os.environ["):
                assert "key" not in stripped.lower(), line


# ===========================================================================
# 9. UNCHANGED ARMS — defaults, baseline and research integrity
# ===========================================================================
class TestUnchangedBehavior:
    def test_default_provider_and_baseline_are_unchanged(self):
        assert mc.DEFAULT_PROVIDER == "ollama"
        assert mc.DEFAULT_OLLAMA_MODEL == "llama3.2:3b"
        assert mc.DEFAULT_OPENROUTER_MODEL == "meta-llama/llama-3.3-70b-instruct"
        assert mc.default_model_for(None) == mc.DEFAULT_OLLAMA_MODEL
        assert mc.default_model_for("unknown") == mc.DEFAULT_OLLAMA_MODEL

    def test_openrouter_is_never_selected_implicitly(self):
        from services.schemas import RunRequest

        assert RunRequest().assessor_provider == "ollama"
        assert RunRequest().assessor == "deterministic"
        assert RunRequest().assessor_api_key is None

    def test_openrouter_setup_does_not_change_provider_selection(self):
        from vapt_platform.model_config import resolve_model

        assert resolve_model("ollama", None) == "llama3.2:3b"
        assert resolve_model(None, None) == "llama3.2:3b"

    def test_cors_configuration_is_unchanged(self):
        import services.api

        # The runtime key must not be a reason to widen CORS.
        source = inspect.getsource(services.api)
        assert 'allow_origins=["*"]' in source

    def test_provider_errors_redaction_still_applies(self):
        from vapt_platform.provider_errors import REDACTED, redact

        assert FAKE_KEY not in redact(f"failed: {FAKE_KEY}")
        assert REDACTED in redact(f"failed: {FAKE_KEY}")

    def test_setup_module_is_importable_standalone(self):
        import importlib

        module = importlib.reload(ors)
        assert module.RUNTIME_KEY_HEADER
        assert callable(module.validate_runtime_key)
        # Reloaded module must still be free of environment writes.
        assert "os.environ[" not in inspect.getsource(module)
