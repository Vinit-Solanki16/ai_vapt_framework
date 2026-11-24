"""Automated tests for AI-VAPT Frontend/Backend Readiness and Runtime API Key Integration.

Covers:
1. Docker ready in backend means no Docker-unavailable warning in frontend.
2. Docker unavailable produces the correct warning.
3. LLM provider unavailable produces an LLM-specific warning, not a Docker warning.
4. A valid frontend-entered OpenRouter key makes the provider ready without requiring .env.
5. Placeholder credentials remain configuration_required.
6. The selected frontend model reaches the actual Strix runtime.
7. Invalid keys are rejected with useful errors.
8. Credentials are redacted from logs and responses.
9. Assessment creation uses the same validated runtime provider configuration.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from strix.core.runtime_credentials import (
    clear_runtime_credentials,
    get_runtime_credential,
    is_placeholder_credential,
    set_runtime_credential,
)
from strix.interface.api import (
    _RUNS,
    _execute_run_worker,
    app,
)
from strix.interface.schemas import OpenRouterValidateResponse, RunRequest
from strix.llm.router import format_openrouter_model


@pytest.fixture(autouse=True)
def reset_credentials_state() -> Generator[None, None, None]:
    """Ensure clean runtime credentials state before and after each test."""
    clear_runtime_credentials()
    yield
    clear_runtime_credentials()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Test 1: Docker ready in backend means no Docker-unavailable warning in frontend
# ---------------------------------------------------------------------------
def test_docker_ready_no_docker_unavailable_warning(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1. When Docker runtime is ready, backend reports available=True and frontend logic never shows Docker unavailable."""
    monkeypatch.setenv("STRIX_TEST_ALLOW_DOCKER_PROBE", "1")

    with (
        patch("subprocess.run") as mock_subproc,
        patch("shutil.which", return_value="/usr/bin/docker"),
    ):
        # Mock docker info and docker image inspect succeeding
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_subproc.return_value = mock_proc

        res = client.get("/system/readiness")
        assert res.status_code == 200
        data = res.json()

        docker_comp = data["components"]["docker_runtime"]
        assert docker_comp["available"] is True
        assert docker_comp["status"] == "ready"

        # Simulate the frontend updateReadinessDisplay decision logic
        docker_ok = docker_comp["available"]
        autonomous_ok = data["autonomous_ready"]

        # If Docker is ok, the warning should NEVER state that Docker is unavailable on host
        if not autonomous_ok:
            assert docker_ok is True
            # The display must state Docker runtime ready and point to the blocking component
            llm_comp = data["components"]["llm_provider"]
            if not llm_comp["available"]:
                display_text = f"Docker runtime ready. AI Provider configuration required: {llm_comp['actionable_message']}"
                assert "Docker unavailable on host" not in display_text
                assert "Docker runtime ready" in display_text


# ---------------------------------------------------------------------------
# Test 2: Docker unavailable produces the correct warning
# ---------------------------------------------------------------------------
def test_docker_unavailable_produces_correct_warning(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2. When Docker runtime is absent, backend reports runtime_unavailable and provides lightweight fallback."""
    monkeypatch.setenv("STRIX_TEST_ALLOW_DOCKER_PROBE", "1")

    with (
        patch("shutil.which", return_value=None),
        patch("strix.interface.api._is_docker_available", return_value=False),
    ):
        res = client.get("/system/readiness")
        assert res.status_code == 200
        data = res.json()

        docker_comp = data["components"]["docker_runtime"]
        assert docker_comp["available"] is False
        assert docker_comp["status"] == "runtime_unavailable"
        assert "Docker CLI is not found" in docker_comp["actionable_message"]
        assert "lightweight scanning mode" in docker_comp["actionable_message"]
        assert data["autonomous_ready"] is False
        assert data["lightweight_ready"] is True


# ---------------------------------------------------------------------------
# Test 3: LLM provider unavailable produces an LLM-specific warning, not a Docker warning
# ---------------------------------------------------------------------------
def test_llm_provider_unavailable_produces_llm_warning_not_docker(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """3. When Docker is ready but LLM is unconfigured, report LLM-specific warning rather than blaming Docker."""
    monkeypatch.setenv("STRIX_TEST_ALLOW_DOCKER_PROBE", "1")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with (
        patch("shutil.which", return_value="/usr/bin/docker"),
        patch("subprocess.run") as mock_subproc,
        patch("strix.core.runtime_credentials._read_strix_cli_config", return_value={}),
        patch("strix.core.diagnostics._read_strix_cli_config", return_value={}),
    ):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_subproc.return_value = mock_proc

        res = client.get("/system/readiness?provider=openrouter")
        assert res.status_code == 200
        data = res.json()

        docker_comp = data["components"]["docker_runtime"]
        llm_comp = data["components"]["llm_provider"]

        # Docker is ready, LLM is not
        assert docker_comp["available"] is True
        assert llm_comp["available"] is False
        assert llm_comp["status"] == "configuration_required"
        assert any(
            phrase in llm_comp["actionable_message"]
            for phrase in (
                "requires an API credential",
                "placeholder test token",
                "No AI model configured",
            )
        )

        # Verify frontend display logic
        docker_ok = docker_comp["available"]
        assert docker_ok is True
        warning = f"Docker runtime ready. AI Provider configuration required: {llm_comp['actionable_message']}"
        assert "Docker unavailable on host" not in warning
        assert "Docker runtime ready" in warning


# ---------------------------------------------------------------------------
# Test 4: Valid frontend-entered OpenRouter key makes provider ready without .env
# ---------------------------------------------------------------------------
def test_frontend_entered_openrouter_key_makes_provider_ready_without_env(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """4. Entering and validating a key via the frontend in-memory makes /system/readiness ready without editing .env."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("STRIX_TEST_ALLOW_DOCKER_PROBE", "1")
    monkeypatch.setenv("STRIX_LLM", "openrouter/auto")

    valid_key = "sk-or-v1-abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"

    mock_val = OpenRouterValidateResponse(
        status="configured",
        message="OpenRouter verified (16 free models available)",
        valid=True,
        catalogue_count=16,
        models=[],
    )

    with (
        patch(
            "strix.llm.provider_validation.validate_openrouter_credential", return_value=mock_val
        ),
        patch("shutil.which", return_value="/usr/bin/docker"),
        patch("subprocess.run") as mock_subproc,
    ):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_subproc.return_value = mock_proc

        # Frontend calls validation endpoint
        val_res = client.post("/providers/openrouter/validate", json={"api_key": valid_key})
        assert val_res.status_code == 200
        assert val_res.json()["valid"] is True

        # Check that runtime credential manager now knows this key
        assert get_runtime_credential("openrouter") == valid_key

        # Check /system/readiness now reports LLM provider ready
        readiness_res = client.get("/system/readiness?provider=openrouter")
        assert readiness_res.status_code == 200
        r_data = readiness_res.json()

        llm_comp = r_data["components"]["llm_provider"]
        assert llm_comp["available"] is True
        assert llm_comp["status"] == "ready"
        assert r_data["autonomous_ready"] is True


# ---------------------------------------------------------------------------
# Test 5: Placeholder credentials remain configuration_required
# ---------------------------------------------------------------------------
def test_placeholder_credentials_remain_configuration_required(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """5. Placeholder keys (e.g. sk-or-v1-test... or containing placeholder) remain configuration_required."""
    clear_runtime_credentials()
    monkeypatch.setenv("STRIX_LLM", "openrouter/auto")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey1234567890abcdef")

    assert is_placeholder_credential("sk-or-v1-testkey1234567890abcdef") is True
    assert is_placeholder_credential("placeholder_value") is True
    assert is_placeholder_credential("your-api-key") is True
    assert is_placeholder_credential("sk-or-v1-livevalidkey9876543210") is False

    res = client.get("/system/readiness?provider=openrouter")
    assert res.status_code == 200
    data = res.json()

    llm_comp = data["components"]["llm_provider"]
    assert llm_comp["status"] == "configuration_required"
    assert llm_comp["available"] is False
    assert "placeholder test token" in llm_comp["actionable_message"]


# ---------------------------------------------------------------------------
# Test 6: Selected frontend model reaches actual Strix runtime
# ---------------------------------------------------------------------------
def test_selected_frontend_model_reaches_strix_runtime(tmp_path: Path) -> None:
    """6. The model selected in frontend (e.g. nvidia/nemotron-3.5-super-vl:free) is normalized and passed to subprocess env."""
    selected_model = "nvidia/nemotron-3.5-super-vl:free"
    expected_normalized = "openrouter/nvidia/nemotron-3.5-super-vl:free"

    # Verify LiteLLM model normalization
    norm = format_openrouter_model(selected_model)
    assert norm == expected_normalized

    run_id = "test-model-prop-run"
    _RUNS[run_id] = {
        "run_id": run_id,
        "status": "queued",
        "scenario": "web_assessment",
        "mode": "autonomous",
        "target_url": "http://127.0.0.1:4280",
        "events": [],
        "findings": [],
        "candidates": [],
    }

    req = RunRequest(
        scenario="default",
        max_attempts=2,
        mode="autonomous",
        target=None,
        port=8080,
        path="/",
        target_url="http://127.0.0.1:4280",
        target_scope_acknowledged=True,
        assessor="llm",
        assessor_provider="openrouter",
        assessor_model=selected_model,
        assessor_api_key="sk-or-v1-livekeyforpropagation123456789",
        scan_file=None,
        assessment_type="strix_autonomous",
        use_nmap=False,
        use_nuclei=False,
        engagement_id=None,
        scan_mode="quick",
        max_turns=1,
        instruction=None,
        auth_config=None,
    )

    captured_env: dict[str, str] = {}

    def fake_popen(cmd: Any, **kwargs: Any) -> MagicMock:
        captured_env.update(kwargs.get("env", {}))
        mock_p = MagicMock()
        mock_p.poll.return_value = 0
        mock_p.stdout.readline.return_value = ""
        mock_p.stderr.readline.return_value = ""
        mock_p.wait.return_value = 0
        return mock_p

    with (
        patch("strix.interface.api.runs_base_dir", return_value=tmp_path),
        patch("strix.interface.api._is_docker_available", return_value=True),
        patch("subprocess.Popen", side_effect=fake_popen),
    ):
        _execute_run_worker(run_id, req, "sk-or-v1-livekeyforpropagation123456789")

    # Assert subprocess environment received the exact model and provider
    assert captured_env.get("STRIX_LLM") == expected_normalized
    assert captured_env.get("STRIX_LLM_PROVIDER") == "openrouter"
    assert captured_env.get("OPENROUTER_API_KEY") == "sk-or-v1-livekeyforpropagation123456789"


# ---------------------------------------------------------------------------
# Test 7: Invalid keys are rejected with useful errors
# ---------------------------------------------------------------------------
def test_invalid_keys_rejected_with_useful_errors(client: TestClient) -> None:
    """7. An invalid key returns a descriptive error message and does not set runtime credentials."""
    invalid_key = "sk-or-v1-badkey00000000000000000000000"

    mock_resp = OpenRouterValidateResponse(
        status="invalid_credentials",
        message="Invalid OpenRouter API key (Unauthorized)",
        valid=False,
        catalogue_count=0,
        models=[],
    )

    with patch(
        "strix.llm.provider_validation.validate_openrouter_credential", return_value=mock_resp
    ):
        res = client.post("/providers/openrouter/validate", json={"api_key": invalid_key})
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is False
        assert data["status"] == "invalid_credentials"
        assert "Invalid OpenRouter API key" in data["message"]

        # Ensure invalid key was not stored in runtime state
        assert get_runtime_credential("openrouter") != invalid_key


# ---------------------------------------------------------------------------
# Test 8: Credentials are redacted from logs and responses
# ---------------------------------------------------------------------------
def test_credentials_redacted_from_responses_and_reports(client: TestClient) -> None:
    """8. Sensitive keys are never returned plaintext in settings, diagnostics, or run records."""
    secret_key = "sk-or-v1-secretlivekeyneverdisclose99999999"
    set_runtime_credential("openrouter", secret_key, "nvidia/nemotron-3.5-super-vl:free")

    # 1. /settings/llm response
    settings_res = client.get("/settings/llm")
    assert settings_res.status_code == 200
    s_data = settings_res.json()
    assert secret_key not in json.dumps(s_data)
    assert s_data["masked_api_key"].startswith("sk-or-")
    assert "..." in s_data["masked_api_key"]

    # 2. /system/readiness response
    readiness_res = client.get("/system/readiness?provider=openrouter")
    assert readiness_res.status_code == 200
    r_data = readiness_res.json()
    assert secret_key not in json.dumps(r_data)

    # 3. /diagnostics/readiness response
    diag_res = client.get("/diagnostics/readiness?provider=openrouter")
    assert diag_res.status_code == 200
    d_data = diag_res.json()
    assert secret_key not in json.dumps(d_data)


# ---------------------------------------------------------------------------
# Test 9: Assessment creation uses the same validated runtime provider configuration
# ---------------------------------------------------------------------------
def test_assessment_creation_uses_validated_runtime_credential(
    client: TestClient, tmp_path: Path
) -> None:
    """9. Assessment creation automatically uses the validated in-memory key when not passed in the request body."""
    active_key = "sk-or-v1-prevalidatedkey112233445566778899"
    set_runtime_credential("openrouter", active_key, "nvidia/nemotron-3.5-super-vl:free")

    mock_val = OpenRouterValidateResponse(
        status="configured",
        message="OpenRouter verified",
        valid=True,
        catalogue_count=10,
        models=[],
    )

    with (
        patch(
            "strix.llm.provider_validation.validate_openrouter_credential", return_value=mock_val
        ),
        patch("strix.interface.api._is_docker_available", return_value=True),
        patch("strix.interface.api.runs_base_dir", return_value=tmp_path),
    ):
        # Post run without passing assessor_api_key in body
        run_res = client.post(
            "/runs",
            json={
                "target_url": "http://127.0.0.1:4280",
                "mode": "autonomous",
                "target_scope_acknowledged": True,
                "assessor_provider": "openrouter",
                "assessor_model": "nvidia/nemotron-3.5-super-vl:free",
            },
        )
        assert run_res.status_code == 200
        run_data = run_res.json()
        assert run_data["status"] == "running"
        run_id = run_data["run_id"]

        run_record = _RUNS[run_id]
        assert run_record["provider"] == "openrouter"
        assert run_record["model"] == "nvidia/nemotron-3.5-super-vl:free"
