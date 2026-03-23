from __future__ import annotations

import pytest

from pyrit_cli.redteam.red_teaming import resolve_rta_prompt
from pyrit_cli.registries.scorers import build_objective_scorer
from pyrit_cli.redteam.targets import openai_chat_from_spec, parse_openai_target, parse_target_spec


def test_parse_openai_target() -> None:
    assert parse_openai_target("openai:gpt-4o") == "gpt-4o"
    with pytest.raises(ValueError):
        parse_openai_target("groq:foo")


def test_parse_target_spec_groq_model_with_slashes() -> None:
    p, m = parse_target_spec("groq:openai/gpt-oss-120b")
    assert p == "groq"
    assert m == "openai/gpt-oss-120b"


def test_resolve_rta_prompt() -> None:
    p = resolve_rta_prompt("text_generation")
    assert p.name == "text_generation.yaml"


def test_resolve_rta_prompt_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid"):
        resolve_rta_prompt("nope")


def test_build_scorer_self_ask_tf_requires_description(pyrit_env_dir) -> None:
    ct = openai_chat_from_spec("openai:gpt-4o-mini")
    with pytest.raises(ValueError, match="true-description"):
        build_objective_scorer("self-ask-tf", scorer_chat=ct, true_description=None, refusal_mode="default")


def test_build_scorer_self_ask_refusal(pyrit_env_dir) -> None:
    ct = openai_chat_from_spec("openai:gpt-4o-mini")
    s = build_objective_scorer(
        "self-ask-refusal",
        scorer_chat=ct,
        true_description=None,
        refusal_mode="strict",
    )
    assert s.__class__.__name__ == "SelfAskRefusalScorer"
