from __future__ import annotations

import pytest

from pyrit_cli.discover.scorers_eval import resolve_eval_text, resolve_scorer_chat_target_spec


def test_resolve_eval_text_mutually_exclusive(tmp_path) -> None:
    p = tmp_path / "t.txt"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="not both"):
        resolve_eval_text(text="a", text_file=p)


def test_resolve_eval_text_requires_input() -> None:
    with pytest.raises(ValueError, match="Provide"):
        resolve_eval_text(text=None, text_file=None)


def test_resolve_eval_text_from_file(tmp_path) -> None:
    p = tmp_path / "t.txt"
    p.write_text("hello\n", encoding="utf-8")
    assert resolve_eval_text(text=None, text_file=p) == "hello\n"


def test_resolve_scorer_chat_target_explicit() -> None:
    assert resolve_scorer_chat_target_spec("  groq:llama  ") == "groq:llama"


def test_resolve_scorer_chat_target_env(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_CHAT_MODEL", raising=False)
    monkeypatch.delenv("PLATFORM_OPENAI_CHAT_GPT4O_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    assert resolve_scorer_chat_target_spec(None) == "openai:gpt-4o-mini"


def test_resolve_scorer_chat_target_missing(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_CHAT_MODEL", raising=False)
    monkeypatch.delenv("PLATFORM_OPENAI_CHAT_GPT4O_MODEL", raising=False)
    with pytest.raises(ValueError, match="scorer-chat-target"):
        resolve_scorer_chat_target_spec(None)
