from __future__ import annotations

import pytest

from pyrit_cli.redteam.targets import openai_chat_from_spec, parse_target_spec


def test_parse_target_spec_providers() -> None:
    assert parse_target_spec("openai:gpt-4o") == ("openai", "gpt-4o")
    assert parse_target_spec("groq:llama-3.3-70b-versatile") == ("groq", "llama-3.3-70b-versatile")
    assert parse_target_spec("groq:openai/gpt-oss-120b") == ("groq", "openai/gpt-oss-120b")
    assert parse_target_spec("ollama:llama3.2") == ("ollama", "llama3.2")
    assert parse_target_spec("lmstudio:my-model") == ("lmstudio", "my-model")
    assert parse_target_spec("lm-studio:x") == ("lmstudio", "x")
    assert parse_target_spec("compat:qwen") == ("compat", "qwen")


def test_parse_target_spec_invalid() -> None:
    with pytest.raises(ValueError):
        parse_target_spec("nocolon")
    with pytest.raises(ValueError):
        parse_target_spec("openai:")
    with pytest.raises(ValueError, match="Unknown provider"):
        parse_target_spec("azure:gpt-4")


def test_groq_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        openai_chat_from_spec("groq:foo")


def test_groq_builds_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("GROQ_OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
    t = openai_chat_from_spec("groq:llama-x")
    assert t._endpoint.rstrip("/") == "https://api.groq.com/openai/v1"


def test_ollama_builds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:11434")
    t = openai_chat_from_spec("ollama:qwen2.5")
    assert t._endpoint == "http://127.0.0.1:11434/v1"


def test_compat_requires_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYRIT_CLI_COMPAT_ENDPOINT", raising=False)
    with pytest.raises(ValueError, match="PYRIT_CLI_COMPAT_ENDPOINT"):
        openai_chat_from_spec("compat:m")


def test_compat_builds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYRIT_CLI_COMPAT_ENDPOINT", "http://localhost:8080/v1")
    t = openai_chat_from_spec("compat:my-model")
    assert t._endpoint == "http://localhost:8080/v1"
