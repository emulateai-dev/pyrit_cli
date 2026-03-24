from __future__ import annotations

import json

import pytest

from pyrit_cli.discover.jailbreak_templates_inspect import (
    parse_template_params,
    run_jailbreak_template_inspect,
)


def test_parse_template_params_ok() -> None:
    assert parse_template_params(["a=1", "b=x=y"]) == {"a": "1", "b": "x=y"}


def test_parse_template_params_requires_equal() -> None:
    with pytest.raises(ValueError, match="key=value"):
        parse_template_params(["bad"])


def test_inspect_dan_1_yaml() -> None:
    out = run_jailbreak_template_inspect("dan_1.yaml")
    assert "Template:" in out
    assert "dan_1.yaml" in out
    assert "Rendered system prompt" in out


def test_inspect_dan_1_json() -> None:
    raw = run_jailbreak_template_inspect("dan_1.yaml", json_out=True)
    data = json.loads(raw)
    assert data["name"] == "dan_1.yaml"
    assert "system_prompt_preview" in data
    assert data["system_prompt_length"] > 0


def test_inspect_unknown_template() -> None:
    with pytest.raises(FileNotFoundError):
        run_jailbreak_template_inspect("no_such_template_cli_test_zzzz.yaml")
