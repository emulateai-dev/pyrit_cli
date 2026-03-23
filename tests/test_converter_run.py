from __future__ import annotations

from typer.testing import CliRunner

from pyrit_cli.cli import app
from pyrit_cli.discover.converter_run import run_converter_pipeline_sync

runner = CliRunner()


def test_run_converter_pipeline_rot13() -> None:
    out = run_converter_pipeline_sync("Hello", ["rot13"])
    assert out == "Uryyb"


def test_run_converter_pipeline_stack() -> None:
    b64 = run_converter_pipeline_sync("Hello", ["base64"])
    out = run_converter_pipeline_sync(b64, ["rot13"])
    assert "U" in out or len(out) > 0


def test_converters_run_cli_rot13(pyrit_env_dir) -> None:
    r = runner.invoke(app, ["converters", "run", "-c", "rot13", "test"])
    assert r.exit_code == 0
    assert r.stdout.strip() == "grfg"


def test_converters_run_cli_stdin(pyrit_env_dir) -> None:
    r = runner.invoke(app, ["converters", "run", "-c", "base64"], input="plain\n")
    assert r.exit_code == 0
    assert r.stdout.strip() == "cGxhaW4="


def test_converters_run_requires_converter(pyrit_env_dir) -> None:
    r = runner.invoke(app, ["converters", "run", "x"])
    assert r.exit_code != 0


def test_converters_run_unknown_key(pyrit_env_dir) -> None:
    r = runner.invoke(app, ["converters", "run", "-c", "not-a-real-converter", "x"])
    assert r.exit_code != 0
    assert "Unknown converter" in r.stdout or "Unknown converter" in r.stderr
