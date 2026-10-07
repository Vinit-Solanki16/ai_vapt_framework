"""Phase 33A — model-selection plumbing + structured-output compatibility.

Covers ONLY:
  1. the single authoritative model configuration source
     (vapt_platform/model_config.py) and its defaults;
  2. clean model_name threading GUI/API -> assessor_provider -> model_name ->
     create_assessor -> assess_exploit_quality -> get_llm -> Ollama;
  3. the existing ExploitAssessment structured-output contract being unchanged
     (so a second model can be swapped in without altering the schema).

Does NOT test model quality (that is the A/B experiment's job) and does NOT
touch the research core, GAP-1, or GAP-2.
"""
from __future__ import annotations

import inspect
from typing import Literal

import pytest

from vapt_platform import model_config as mc


# ---------------------------------------------------------------------------
# 1. Authoritative configuration source
# ---------------------------------------------------------------------------

def test_baseline_is_llama_and_unchanged():
    assert mc.DEFAULT_OLLAMA_MODEL == "llama3.2:3b"
    assert mc.DEFAULT_OPENAI_MODEL == "gpt-4o-mini"
    assert mc.is_baseline("llama3.2:3b")


def test_qwen_is_registered_as_experimental_not_default():
    assert "qwen2.5:3b" in mc.OLLAMA_MODELS
    assert mc.is_experimental("qwen2.5:3b")
    assert not mc.is_baseline("qwen2.5:3b")
    # The experimental arm is never the implicit default.
    assert mc.default_model_for("ollama") != "qwen2.5:3b"


def test_ollama_models_are_ordered_baseline_first():
    assert mc.OLLAMA_MODELS[0] == mc.DEFAULT_OLLAMA_MODEL


def test_resolve_model_explicit_wins_and_blank_falls_back():
    assert mc.resolve_model("ollama", "qwen2.5:3b") == "qwen2.5:3b"
    assert mc.resolve_model("ollama", None) == "llama3.2:3b"
    assert mc.resolve_model("ollama", "") == "llama3.2:3b"
    assert mc.resolve_model("ollama", "   ") == "llama3.2:3b"
    assert mc.resolve_model("openai", None) == "gpt-4o-mini"


def test_models_for_provider_unknown_is_empty():
    assert mc.models_for_provider("nope") == ()


# ---------------------------------------------------------------------------
# 2. Clean threading
# ---------------------------------------------------------------------------

def test_get_llm_honours_explicit_model_and_default():
    from core.exploit_assessor import get_llm

    assert get_llm("ollama").model == "llama3.2:3b"
    assert get_llm("ollama", "qwen2.5:3b").model == "qwen2.5:3b"


def test_get_llm_uses_authoritative_default_not_a_local_literal():
    """get_llm must resolve through model_config, not its own literal."""
    from core import exploit_assessor

    src = inspect.getsource(exploit_assessor.get_llm)
    assert "resolve_model" in src
    assert '"llama3.2:3b"' not in src
    assert '"gpt-4o-mini"' not in src


def test_create_assessor_accepts_model_name():
    from vapt_platform.assessment import create_assessor

    sig = inspect.signature(create_assessor)
    assert "model_name" in sig.parameters
    # Constructing both modes must not raise.
    create_assessor(mode="deterministic")
    create_assessor(mode="ai", provider="ollama", model_name="qwen2.5:3b")


def test_ai_fallback_reports_the_resolved_model(monkeypatch):
    """When the provider is unreachable the fallback must still name the model."""
    from vapt_platform import assessment as a
    from decision_engine.core.schemas import ActionCandidate

    monkeypatch.setattr(a, "_try_ollama_assess", lambda *args, **kwargs: None)
    fn = a.create_assessor(mode="ai", provider="ollama", model_name="qwen2.5:3b")
    res = fn(ActionCandidate(id="X", probability=0.5))
    assert res.fallback is True
    assert res.model == "qwen2.5:3b"


def test_assess_candidates_with_provenance_threads_model_name():
    from vapt_platform.assessment import assess_candidates_with_provenance

    sig = inspect.signature(assess_candidates_with_provenance)
    assert "model_name" in sig.parameters


def test_request_models_expose_assessor_model():
    from vapt_platform.application import VAPTRequest
    from services.schemas import RunRequest

    assert "assessor_model" in VAPTRequest.__dataclass_fields__
    assert VAPTRequest().assessor_model is None
    assert "assessor_model" in RunRequest.model_fields
    assert RunRequest().assessor_model is None


def test_engine_integration_threads_assessment_model():
    from prototype.engine_integration import run_decision_scenario

    sig = inspect.signature(run_decision_scenario)
    assert "assessment_model" in sig.parameters


def test_no_duplicated_model_literals_in_threaded_layers():
    """The model name must live in ONE place (model_config), not be copied."""
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    threaded = [
        "vapt_platform/assessment.py",
        "vapt_platform/application.py",
        "prototype/engine_integration.py",
        "services/api.py",
        "core/exploit_assessor.py",
    ]

    def _code_strings(text: str) -> list[str]:
        """String constants that are actual code, excluding docstrings."""
        tree = ast.parse(text)
        doc_nodes = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)):
                body = getattr(node, "body", None) or []
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    doc_nodes.add(id(body[0].value))
        return [
            n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in doc_nodes
        ]

    offenders = []
    for rel in threaded:
        strings = _code_strings((root / rel).read_text(encoding="utf-8"))
        for literal in ('"llama3.2:3b"', '"gpt-4o-mini"'):
            if literal.strip('"') in strings:
                offenders.append(f"{rel}: {literal}")
    assert not offenders, f"hardcoded model literals outside model_config: {offenders}"


# ---------------------------------------------------------------------------
# 3. Structured-output contract unchanged (schema compatibility)
# ---------------------------------------------------------------------------

def test_exploit_assessment_schema_unchanged():
    """A second model must satisfy THIS contract, so it must not drift."""
    from core.schemas import ExploitAssessment, UsabilityRank

    fields = ExploitAssessment.model_fields
    # Exact field set — adding/removing a field changes the contract.
    assert set(fields) == {
        "exploit_found", "syntax_valid", "os_dependencies",
        "privileges_required", "network_noise", "complexity_score",
        "prerequisites_met", "usability_rank", "reasoning",
    }
    # Exact constrained types — the enum/Literal constraints are the fix for
    # the original loose-`str` garbage-output bug, so they must not relax.
    assert fields["exploit_found"].annotation is bool
    assert fields["syntax_valid"].annotation is bool
    assert fields["os_dependencies"].annotation is str
    assert fields["privileges_required"].annotation == Literal["none", "user", "root"]
    assert fields["network_noise"].annotation == Literal["low", "medium", "high"]
    assert fields["complexity_score"].annotation is int
    assert fields["prerequisites_met"].annotation is bool
    assert fields["usability_rank"].annotation is UsabilityRank
    assert fields["reasoning"].annotation is str
    # Complexity bounds preserved.
    assert fields["complexity_score"].metadata  # ge/le constraints present


def test_assess_exploit_quality_accepts_model_name():
    from core.exploit_assessor import assess_exploit_quality

    sig = inspect.signature(assess_exploit_quality)
    assert "model_name" in sig.parameters
    assert sig.parameters["model_name"].default is None


def test_temperature_is_unchanged_for_both_models():
    """The A/B comparison requires an identical sampling temperature."""
    from core.exploit_assessor import get_llm

    assert get_llm("ollama").temperature == 0.1
    assert get_llm("ollama", "qwen2.5:3b").temperature == 0.1


def test_prompt_is_shared_and_not_model_specific():
    from core.exploit_assessor import SYSTEM_PROMPT

    assert isinstance(SYSTEM_PROMPT, str) and SYSTEM_PROMPT
    lowered = SYSTEM_PROMPT.lower()
    assert "llama" not in lowered and "qwen" not in lowered
