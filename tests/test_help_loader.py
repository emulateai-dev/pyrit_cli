from __future__ import annotations

from pyrit_cli.help_loader import load_help_markdown


def test_load_help_markdown_contains_cli_reference() -> None:
    text = load_help_markdown()
    assert "pyrit-cli" in text
    assert "prompt-sending-attack" in text
