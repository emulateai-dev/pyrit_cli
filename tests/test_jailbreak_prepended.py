from __future__ import annotations

from pyrit_cli.redteam.jailbreak_prepended import build_jailbreak_prepended_conversation


def test_build_jailbreak_prepended_dan_1() -> None:
    msgs = build_jailbreak_prepended_conversation(
        jailbreak_template="dan_1.yaml",
        jailbreak_template_params=[],
    )
    assert msgs is not None
    assert len(msgs) == 1
    assert str(msgs[0].api_role).lower().endswith("system")
    assert msgs[0].message_pieces
    assert len(str(msgs[0].message_pieces[0].original_value)) > 50


def test_build_jailbreak_prepended_custom_yaml_path(tmp_path) -> None:
    p = tmp_path / "custom_jb.yaml"
    p.write_text(
        """---
name: CLI test template
description: tmp
parameters:
  - prompt
data_type: text
value: 'Prefix: {{ prompt }}'
""",
        encoding="utf-8",
    )
    msgs = build_jailbreak_prepended_conversation(
        jailbreak_template=str(p),
        jailbreak_template_params=[],
    )
    assert msgs is not None
    assert len(msgs) == 1
    body = str(msgs[0].message_pieces[0].original_value)
    assert body.strip().startswith("Prefix:")
