"""Tests for ask-ai HTTP file attachments (no live API)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyrit_cli.ask_ai import (
    ASK_AI_ATTACHMENT_MAX_BYTES,
    build_ask_ai_user_message,
    read_ask_ai_file,
)


def test_read_ask_ai_file_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    p.write_text("hello\n", encoding="utf-8")
    assert read_ask_ai_file(p) == "hello\n"


def test_read_ask_ai_file_not_found(tmp_path: Path) -> None:
    p = tmp_path / "missing.txt"
    with pytest.raises(FileNotFoundError, match="Attachment not found"):
        read_ask_ai_file(p)


def test_read_ask_ai_file_not_regular(tmp_path: Path) -> None:
    d = tmp_path / "dir"
    d.mkdir()
    with pytest.raises(IsADirectoryError, match="not a regular file"):
        read_ask_ai_file(d)


def test_read_ask_ai_file_too_large(tmp_path: Path) -> None:
    p = tmp_path / "big.txt"
    p.write_bytes(b"x" * (ASK_AI_ATTACHMENT_MAX_BYTES + 1))
    with pytest.raises(ValueError, match="max"):
        read_ask_ai_file(p)


def test_read_ask_ai_file_invalid_utf8(tmp_path: Path) -> None:
    p = tmp_path / "bad.bin"
    p.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(ValueError, match="not valid UTF-8"):
        read_ask_ai_file(p)


def test_build_ask_ai_user_message_includes_paths_and_content(tmp_path: Path) -> None:
    req = tmp_path / "r.req"
    req.write_text("GET / HTTP/1.1\n\n", encoding="utf-8")
    resp = tmp_path / "s.json"
    resp.write_text('{"x":1}', encoding="utf-8")
    msg = build_ask_ai_user_message(
        "Fix my HTTP target",
        http_request_file=req,
        http_response_sample=resp,
    )
    assert "Fix my HTTP target" in msg
    assert "Attached HTTP request template" in msg
    assert "Sample HTTP response body" in msg
    assert str(req.resolve()) in msg
    assert str(resp.resolve()) in msg
    assert "GET / HTTP/1.1" in msg
    assert '{"x":1}' in msg
    assert "If the question is broad" in msg


def test_build_ask_ai_user_message_goal_only() -> None:
    msg = build_ask_ai_user_message("plain question")
    assert msg.startswith("User question")
    assert "plain question" in msg
    assert "Attached HTTP" not in msg
