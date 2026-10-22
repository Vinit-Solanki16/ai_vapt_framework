"""Tests for the lightweight vapt_platform.env_loader module."""
import os
from pathlib import Path
import pytest

from vapt_platform.env_loader import load_env


def test_load_env_populates_missing_variables(tmp_path, monkeypatch):
    """load_env reads key=value from .env and sets os.environ using setdefault."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Comment line\n"
        "TEST_AUTO_PORT=9999\n"
        "TEST_AUTO_SCOPE='test-scope.org:8443'\n"
        "  TEST_AUTO_UNQUOTED = hello_world  \n"
        "\n"
        "# Another comment\n"
    )

    monkeypatch.delenv("TEST_AUTO_PORT", raising=False)
    monkeypatch.delenv("TEST_AUTO_SCOPE", raising=False)
    monkeypatch.delenv("TEST_AUTO_UNQUOTED", raising=False)

    load_env(str(env_file))

    assert os.environ.get("TEST_AUTO_PORT") == "9999"
    assert os.environ.get("TEST_AUTO_SCOPE") == "test-scope.org:8443"
    assert os.environ.get("TEST_AUTO_UNQUOTED") == "hello_world"


def test_load_env_preserves_existing_environment_variables(tmp_path, monkeypatch):
    """load_env never overwrites variables already set in os.environ."""
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING_KEY=new_val_from_file\n")

    monkeypatch.setenv("EXISTING_KEY", "original_pre_set_value")

    load_env(str(env_file))

    assert os.environ.get("EXISTING_KEY") == "original_pre_set_value"


def test_load_env_handles_missing_file_cleanly():
    """load_env does not raise an exception when file does not exist."""
    load_env("/non/existent/path/.env.missing")
