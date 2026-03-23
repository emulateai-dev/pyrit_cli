"""Tests for datasets inspect (pyrit file spec; parse only for hf)."""

from __future__ import annotations

import pytest

from pyrit_cli.discover.datasets_inspect import (
    inspect_pyrit_file,
    parse_inspect_spec,
    run_dataset_inspect,
)


def test_parse_inspect_spec_hf() -> None:
    k, p = parse_inspect_spec("hf:imdb")
    assert k == "hf"
    assert p["repo_id"] == "imdb"


def test_parse_inspect_spec_pyrit_file() -> None:
    k, p = parse_inspect_spec("pyrit:seed_datasets/local/airt/illegal.prompt")
    assert k == "pyrit_file"
    assert "pyrit:" in p["spec"]


def test_parse_inspect_spec_invalid() -> None:
    with pytest.raises(ValueError, match="pyrit:|hf:"):
        parse_inspect_spec("openai:gpt-4o")


def test_inspect_pyrit_file_smoke() -> None:
    out = inspect_pyrit_file("pyrit:seed_datasets/local/airt/illegal.prompt", limit=2)
    assert "Seeds:" in out
    assert "[1]" in out


def test_run_dataset_inspect_file_matches_inspect_pyrit_file() -> None:
    spec = "pyrit:seed_datasets/local/airt/illegal.prompt"
    assert run_dataset_inspect(
        spec, limit=1, hf_split="train", hf_column="text", hf_config=None
    ) == inspect_pyrit_file(spec, limit=1)


def test_datasets_inspect_help() -> None:
    from typer.testing import CliRunner

    from pyrit_cli.cli import app

    r = CliRunner().invoke(
        app,
        ["datasets", "inspect", "--help"],
        env={"COLUMNS": "200", "LINES": "60"},
    )
    assert r.exit_code == 0
    assert "pyrit:" in r.stdout or "SPEC" in r.stdout
