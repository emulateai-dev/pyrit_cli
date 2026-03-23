from __future__ import annotations

from typer.testing import CliRunner

from pyrit_cli.cli import app
from pyrit_cli.discover.jailbreak_templates_list import (
    list_jailbreak_templates_json,
    list_jailbreak_templates_text,
)

runner = CliRunner()


def test_list_jailbreak_templates_includes_jailbreak_1() -> None:
    text = list_jailbreak_templates_text(include_multi_parameter=False)
    assert "jailbreak_1.yaml" in text


def test_list_jailbreak_templates_json_parseable() -> None:
    raw = list_jailbreak_templates_json(include_multi_parameter=False)
    assert "jailbreak_1.yaml" in raw
    assert "relative_path" in raw


def test_jailbreak_templates_list_cli() -> None:
    r = runner.invoke(app, ["jailbreak-templates", "list"])
    assert r.exit_code == 0
    assert "jailbreak_1.yaml" in r.stdout


def test_jailbreak_templates_list_json_cli() -> None:
    r = runner.invoke(app, ["jailbreak-templates", "list", "--json"])
    assert r.exit_code == 0
    assert "jailbreak_1.yaml" in r.stdout
