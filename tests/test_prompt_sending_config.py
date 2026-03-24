from __future__ import annotations

import pytest

from pyrit_cli.redteam.jailbreak_prepended import (
    build_jailbreak_prepended_conversation,
    parse_jailbreak_template_params,
)


def test_parse_jailbreak_template_params_success() -> None:
    out = parse_jailbreak_template_params(["a=1", "b=two=parts"])
    assert out["a"] == "1"
    assert out["b"] == "two=parts"


def test_parse_jailbreak_template_params_requires_equal() -> None:
    with pytest.raises(ValueError, match="key=value"):
        parse_jailbreak_template_params(["nope"])


def test_jailbreak_params_require_template() -> None:
    with pytest.raises(ValueError, match="requires --jailbreak-template"):
        build_jailbreak_prepended_conversation(
            jailbreak_template=None, jailbreak_template_params=["a=1"]
        )
