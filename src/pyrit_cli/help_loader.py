"""Load bundled HELP.md for ask-ai and docs."""

from __future__ import annotations

import importlib.resources


def load_help_markdown() -> str:
    root = importlib.resources.files("pyrit_cli")
    path = root.joinpath("HELP.md")
    if not path.is_file():
        msg = "Bundled HELP.md missing from pyrit_cli package."
        raise FileNotFoundError(msg)
    return path.read_text(encoding="utf-8")
