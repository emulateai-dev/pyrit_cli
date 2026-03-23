from __future__ import annotations

from pyrit_cli.env_status import parse_env_file
from pyrit_cli.env_write import save_openai_compatible, save_openai_native


def test_save_openai_native(tmp_path, monkeypatch) -> None:
    root = tmp_path / "pyrit_native"
    root.mkdir()
    monkeypatch.setenv("PYRIT_ENV_DIR", str(root))

    save_openai_native("sk-test-native", model="gpt-4o-mini")

    main = parse_env_file(root / ".env")
    local = parse_env_file(root / ".env.local")
    assert main.get("OPENAI_API_KEY") == "sk-test-native"
    assert local.get("OPENAI_CHAT_ENDPOINT") == "https://api.openai.com/v1"
    assert local.get("OPENAI_CHAT_KEY") == "sk-test-native"
    assert local.get("OPENAI_CHAT_MODEL") == "gpt-4o-mini"


def test_save_openai_compatible(tmp_path, monkeypatch) -> None:
    root = tmp_path / "pyrit_compat"
    root.mkdir()
    monkeypatch.setenv("PYRIT_ENV_DIR", str(root))

    save_openai_compatible("https://api.groq.com/openai/v1", "gsk-test", "llama-test")

    main = parse_env_file(root / ".env")
    local_text = (root / ".env.local").read_text(encoding="utf-8")
    assert main.get("PLATFORM_OPENAI_CHAT_ENDPOINT") == "https://api.groq.com/openai/v1"
    assert main.get("PLATFORM_OPENAI_CHAT_API_KEY") == "gsk-test"
    assert main.get("PLATFORM_OPENAI_CHAT_GPT4O_MODEL") == "llama-test"
    assert "OPENAI_CHAT_ENDPOINT=" in local_text
    assert "llama-test" in local_text
