"""Build prepended conversation messages from PyRIT TextJailBreak templates."""

from __future__ import annotations

from pathlib import Path

from pyrit.datasets import TextJailBreak
from pyrit.models import Message


def parse_jailbreak_template_params(raw_pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in raw_pairs:
        if "=" not in raw:
            raise ValueError(f"Invalid jailbreak template param {raw!r}; expected key=value")
        key, value = raw.split("=", 1)
        k = key.strip()
        if not k:
            raise ValueError(f"Invalid jailbreak template param {raw!r}; key cannot be empty")
        out[k] = value
    return out


def build_jailbreak_prepended_conversation(
    *,
    jailbreak_template: str | None,
    jailbreak_template_params: list[str],
) -> list[Message] | None:
    """Return a single system message list, or None if no template.

    Template kwargs (besides ``prompt``) are passed to ``TextJailBreak(...)`` per PyRIT API.
    """
    if not jailbreak_template:
        if jailbreak_template_params:
            raise ValueError("--jailbreak-template-param requires --jailbreak-template")
        return None
    kwargs = parse_jailbreak_template_params(jailbreak_template_params)
    path = Path(jailbreak_template).expanduser()
    if path.is_file():
        jailbreak = TextJailBreak(template_path=str(path.resolve()), **kwargs)
    else:
        jailbreak = TextJailBreak(template_file_name=jailbreak_template, **kwargs)
    system_prompt = jailbreak.get_jailbreak_system_prompt()
    return [Message.from_system_prompt(system_prompt)]
