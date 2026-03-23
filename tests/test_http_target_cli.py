from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pyrit_cli.redteam.http_target_cli import (
    build_http_objective_target,
    is_http_objective_url,
    is_http_victim_spec,
    merge_http_request_with_objective_url,
    parse_http_response_parser,
    parse_objective_http_url,
)
from pyrit_cli.redteam.red_teaming import build_redteam_converter_config


def test_parse_json_parser() -> None:
    fn = parse_http_response_parser("json:choices[0].message.content", regex_base_url=None)
    mock = MagicMock()
    mock.content = b'{"choices":[{"message":{"content":"hi"}}]}'
    assert fn(response=mock) == "hi"


def test_parse_regex_parser() -> None:
    fn = parse_http_response_parser(r"regex:hello\s+\w+", regex_base_url=None)
    mock = MagicMock()
    mock.content = "prefix hello world suffix"
    out = fn(response=mock)
    assert "hello world" in out


def test_parse_regex_parser_decodes_utf8_bytes() -> None:
    class _Resp:
        content = b'{"choices":[{"message":{"role":"assistant","content":"hi"}}]}'

    fn = parse_http_response_parser(r'regex:(?<="content":")([^"]*)', regex_base_url=None)
    assert fn(response=_Resp()) == "hi"


def test_parse_regex_parser_base_url_prefix() -> None:
    class _Resp:
        content = b"path/to/x"

    fn = parse_http_response_parser(r"regex:path/to/x", regex_base_url="https://ex.com/")
    assert fn(response=_Resp()) == "https://ex.com/path/to/x"


def test_jq_parser_requires_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pyrit_cli.redteam.http_target_cli.shutil.which", lambda _: None)
    with pytest.raises(ValueError, match="jq"):
        parse_http_response_parser("jq:.a", regex_base_url=None)


def test_merge_http_request_with_objective_url_updates_line_and_host() -> None:
    raw = (
        "POST /v1/chat HTTP/1.1\n"
        "Host: old.example\n"
        "Content-Type: application/json\n\n"
        '{"x":"{PROMPT}"}'
    )
    out = merge_http_request_with_objective_url(
        raw, "https://api.new.example/v1/chat/completions"
    )
    assert "POST https://api.new.example/v1/chat/completions HTTP/1.1" in out
    assert "Host: api.new.example" in out
    assert '{"x":"{PROMPT}"}' in out


def test_parse_objective_http_url() -> None:
    assert parse_objective_http_url("https://a/b") == "https://a/b"
    assert parse_objective_http_url("  http://h  ") == "http://h"
    assert parse_objective_http_url("openai:gpt-4o") is None
    with pytest.raises(ValueError, match="host"):
        parse_objective_http_url("https://")


def test_is_http_victim_spec() -> None:
    assert is_http_victim_spec("http")
    assert is_http_victim_spec("HTTP")
    assert is_http_victim_spec("https://x/y")
    assert not is_http_victim_spec("openai:gpt-4o")
    assert is_http_objective_url("https://z")


def test_build_http_target_from_file(tmp_path: Path) -> None:
    req = tmp_path / "x.req"
    req.write_text(
        "POST /v1/chat HTTP/1.1\nHost: example.com\nContent-Type: application/json\n\n"
        '{"x":"{PROMPT}"}',
        encoding="utf-8",
    )
    t = build_http_objective_target(
        request_path=req,
        response_parser_spec="json:answer",
        prompt_placeholder="{PROMPT}",
        regex_base_url=None,
        use_tls=True,
        timeout=5.0,
        model_name="t",
    )
    assert "example.com" in t.http_request
    assert t.callback_function is not None


def test_build_http_target_merges_objective_url(tmp_path: Path) -> None:
    req = tmp_path / "y.req"
    req.write_text(
        "POST /p HTTP/1.1\nHost: ignored.example\n\n{}",
        encoding="utf-8",
    )
    t = build_http_objective_target(
        request_path=req,
        response_parser_spec="json:a",
        prompt_placeholder="{PROMPT}",
        regex_base_url=None,
        use_tls=True,
        timeout=None,
        model_name="m",
        objective_url="https://real.service/p",
    )
    assert "POST https://real.service/p HTTP/1.1" in t.http_request
    assert "Host: real.service" in t.http_request


def test_build_redteam_converter_json_escape_conflicts_request() -> None:
    with pytest.raises(ValueError, match="Cannot combine"):
        build_redteam_converter_config(
            http_json_body_converter=True,
            request_converter_keys=["base64"],
            response_converter_keys=[],
        )


def test_build_redteam_converter_json_escape_plus_response() -> None:
    cfg = build_redteam_converter_config(
        http_json_body_converter=True,
        request_converter_keys=[],
        response_converter_keys=["rot13"],
    )
    assert cfg is not None
    assert cfg.request_converters
    assert cfg.response_converters
