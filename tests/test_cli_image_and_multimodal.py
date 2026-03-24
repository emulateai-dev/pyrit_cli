from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import pyrit_cli.cli as cli_mod
from pyrit_cli.cli import app

runner = CliRunner()


def test_converters_image_list_keys() -> None:
    r = runner.invoke(app, ["converters", "image", "list-keys"])
    assert r.exit_code == 0
    assert "qrcode" in r.stdout
    assert "transparency" in r.stdout


def test_converters_image_qrcode_calls_runner(monkeypatch) -> None:
    monkeypatch.setattr(cli_mod, "run_image_qrcode_sync", lambda text: f"/tmp/{text}.png")
    r = runner.invoke(app, ["converters", "image", "qrcode", "hello"])
    assert r.exit_code == 0
    assert "/tmp/hello.png" in r.stdout


def test_prompt_sending_multimodal_flags_forwarded(monkeypatch, tmp_path: Path) -> None:
    img = tmp_path / "i.png"
    img.write_text("x", encoding="utf-8")
    captured: dict = {}

    monkeypatch.setattr(cli_mod, "collect_objectives", lambda *args, **kwargs: ["obj"])

    def _fake_run_prompt_sending(target, objectives, **kwargs):
        captured["target"] = target
        captured["objectives"] = objectives
        captured["kwargs"] = kwargs

    monkeypatch.setattr(cli_mod, "run_prompt_sending", _fake_run_prompt_sending)
    r = runner.invoke(
        app,
        [
            "redteam",
            "prompt-sending-attack",
            "--target",
            "openai:gpt-4o-mini",
            "--objective",
            "x",
            "--input-image",
            str(img),
            "--input-text",
            "look at image",
        ],
    )
    assert r.exit_code == 0
    assert captured["kwargs"]["input_images"] == [str(img)]
    assert captured["kwargs"]["input_text"] == "look at image"


def test_red_teaming_multimodal_flags_forwarded(monkeypatch, tmp_path: Path) -> None:
    img = tmp_path / "i2.png"
    img.write_text("x", encoding="utf-8")
    captured: dict = {}

    monkeypatch.setattr(cli_mod, "parse_memory_labels_json", lambda *_: None)

    def _fake_run_red_teaming(**kwargs):
        captured["kwargs"] = kwargs

    monkeypatch.setattr(cli_mod, "run_red_teaming", _fake_run_red_teaming)
    r = runner.invoke(
        app,
        [
            "redteam",
            "red-teaming-attack",
            "--objective-target",
            "openai:gpt-4o-mini",
            "--objective",
            "x",
            "--input-image",
            str(img),
            "--input-text",
            "look at image",
        ],
    )
    assert r.exit_code == 0
    assert captured["kwargs"]["input_images"] == [str(img)]
    assert captured["kwargs"]["input_text"] == "look at image"
