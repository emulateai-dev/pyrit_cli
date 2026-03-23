from __future__ import annotations

import pytest

from pyrit_cli.redteam.prompt_sending import _build_prepended_conversation, _parse_kv_pairs


def test_parse_kv_pairs_success() -> None:
    out = _parse_kv_pairs(["a=1", "b=two=parts"])
    assert out["a"] == "1"
    assert out["b"] == "two=parts"


def test_parse_kv_pairs_requires_equal() -> None:
    with pytest.raises(ValueError, match="key=value"):
        _parse_kv_pairs(["nope"])


def test_jailbreak_params_require_template() -> None:
    with pytest.raises(ValueError, match="requires --jailbreak-template"):
        _build_prepended_conversation(jailbreak_template=None, jailbreak_template_params=["a=1"])
