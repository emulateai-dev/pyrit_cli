"""Minimal PyRIT env for tests that touch OpenAIChatTarget or initialize_pyrit_async."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def pyrit_env_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "pyrit_test"
    d.mkdir()
    (d / ".env").write_text(
        "OPENAI_CHAT_ENDPOINT=https://api.openai.com/v1\n"
        "OPENAI_CHAT_KEY=test-key-not-used-if-no-network\n"
        "OPENAI_CHAT_MODEL=gpt-4o-mini\n",
        encoding="utf-8",
    )
    (d / ".env.local").touch()
    monkeypatch.setenv("PYRIT_ENV_DIR", str(d))
    return d
