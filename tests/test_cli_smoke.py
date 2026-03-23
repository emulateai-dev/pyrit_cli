from __future__ import annotations

from typer.testing import CliRunner

from pyrit_cli.cli import app

runner = CliRunner()


def test_version() -> None:
    r = runner.invoke(app, ["--version"])
    assert r.exit_code == 0
    assert "pyrit-cli" in r.stdout


def test_converters_list_keys() -> None:
    r = runner.invoke(app, ["converters", "list-keys"])
    assert r.exit_code == 0
    assert "base64" in r.stdout


def test_converters_run_help() -> None:
    r = runner.invoke(
        app,
        ["converters", "run", "--help"],
        env={"COLUMNS": "200", "LINES": "60"},
    )
    assert r.exit_code == 0
    assert "--converter" in r.stdout or "-c" in r.stdout


def test_jailbreak_templates_list_help() -> None:
    r = runner.invoke(
        app,
        ["jailbreak-templates", "list", "--help"],
        env={"COLUMNS": "200", "LINES": "60"},
    )
    assert r.exit_code == 0
    assert "json" in r.stdout.lower()


def test_targets_list() -> None:
    r = runner.invoke(app, ["targets", "list"])
    assert r.exit_code == 0
    assert "openai:" in r.stdout
    assert "groq:" in r.stdout
    assert "ollama:" in r.stdout


def test_datasets_list() -> None:
    r = runner.invoke(app, ["datasets", "list", "--glob", "*airt*"])
    assert r.exit_code == 0


def test_scorers_list() -> None:
    r = runner.invoke(app, ["scorers", "list"])
    assert r.exit_code == 0
    assert "self-ask-tf" in r.stdout


def test_setup_status(pyrit_env_dir) -> None:
    r = runner.invoke(app, ["setup", "status"])
    assert r.exit_code == 0
    assert "PyRIT config directory" in r.stdout


def test_red_teaming_help() -> None:
    r = runner.invoke(
        app,
        ["redteam", "red-teaming-attack", "--help"],
        env={"COLUMNS": "200", "LINES": "60"},
    )
    assert r.exit_code == 0
    assert "objective-target" in r.stdout


def test_prompt_sending_attack_help() -> None:
    r = runner.invoke(
        app,
        ["redteam", "prompt-sending-attack", "--help"],
        env={"COLUMNS": "200", "LINES": "60"},
    )
    assert r.exit_code == 0
    assert "--target" in r.stdout
    assert "--scoring-mode" in r.stdout
    assert "--jailbreak-template" in r.stdout


def test_ask_ai_help() -> None:
    r = runner.invoke(
        app,
        ["ask-ai", "--help"],
        env={"COLUMNS": "200", "LINES": "60"},
    )
    assert r.exit_code == 0
    assert "query" in r.stdout.lower() or "describe" in r.stdout.lower()
    assert "http-request-file" in r.stdout
    assert "http-response-sample" in r.stdout


def test_setup_configure_help() -> None:
    r = runner.invoke(
        app,
        ["setup", "configure", "--help"],
        env={"COLUMNS": "200", "LINES": "60"},
    )
    assert r.exit_code == 0
    assert "configure" in r.stdout.lower() or "wizard" in r.stdout.lower()


def test_tap_attack_help() -> None:
    # Rich-wrapped help truncates when COLUMNS is tiny (default in tests).
    r = runner.invoke(
        app,
        ["redteam", "tap-attack", "--help"],
        env={"COLUMNS": "200", "LINES": "60"},
    )
    assert r.exit_code == 0
    assert "objective-target" in r.stdout
    assert "tree-width" in r.stdout


def test_prompt_sending_http_requires_parser(tmp_path) -> None:
    req = tmp_path / "a.req"
    req.write_text(
        'POST / HTTP/1.1\nHost: x.example\n\n{"p":"{PROMPT}"}',
        encoding="utf-8",
    )
    r = runner.invoke(
        app,
        ["redteam", "prompt-sending-attack", "--target", "http", "--http-request", str(req), "--objective", "hi"],
        env={"COLUMNS": "120"},
    )
    assert r.exit_code != 0


def test_tap_attack_rejects_http_victim() -> None:
    r = runner.invoke(
        app,
        [
            "redteam",
            "tap-attack",
            "--objective-target",
            "http",
            "--objective",
            "x",
        ],
        env={"COLUMNS": "200"},
    )
    assert r.exit_code != 0
    assert "http" in r.stdout.lower() or "http" in r.stderr.lower()


def test_tap_attack_rejects_https_url_victim() -> None:
    r = runner.invoke(
        app,
        [
            "redteam",
            "tap-attack",
            "--objective-target",
            "https://api.example.com/v1/chat",
            "--objective",
            "x",
        ],
        env={"COLUMNS": "200"},
    )
    assert r.exit_code != 0


def test_prompt_sending_https_url_requires_parser(tmp_path) -> None:
    req = tmp_path / "b.req"
    req.write_text(
        'POST / HTTP/1.1\nHost: x.example\n\n{"p":"{PROMPT}"}',
        encoding="utf-8",
    )
    r = runner.invoke(
        app,
        [
            "redteam",
            "prompt-sending-attack",
            "--target",
            "https://api.example.com/v1/chat",
            "--http-request",
            str(req),
            "--objective",
            "hi",
        ],
        env={"COLUMNS": "120"},
    )
    assert r.exit_code != 0


def test_converters_list(pyrit_env_dir) -> None:
    r = runner.invoke(app, ["converters", "list"])
    assert r.exit_code == 0
    assert "Base64Converter" in r.stdout or "base64" in r.stdout.lower()
