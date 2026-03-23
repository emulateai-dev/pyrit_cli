"""List YAML jailbreak templates shipped with PyRIT (TextJailBreak template_file_name)."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from pyrit.common.path import JAILBREAK_TEMPLATES_PATH


def _iter_yaml_files(root: Path, *, include_multi_parameter: bool) -> list[Path]:
    files: list[Path] = []
    for p in root.rglob("*.yaml"):
        if not include_multi_parameter and "multi_parameter" in p.parts:
            continue
        files.append(p)
    return files


def jailbreak_template_warnings(*, include_multi_parameter: bool) -> list[str]:
    root = JAILBREAK_TEMPLATES_PATH
    files = _iter_yaml_files(root, include_multi_parameter=include_multi_parameter)
    by_name: dict[str, list[Path]] = defaultdict(list)
    for p in files:
        by_name[p.name].append(p)
    out: list[str] = []
    for name in sorted(by_name.keys()):
        paths = by_name[name]
        if len(paths) > 1:
            out.append(
                f"Duplicate basename {name!r} ({len(paths)} paths): TextJailBreak(template_file_name=...) "
                "will fail — use template_path with a full path, or rename locally."
            )
    return out


def list_jailbreak_templates_text(*, include_multi_parameter: bool) -> str:
    root = JAILBREAK_TEMPLATES_PATH
    files = sorted(_iter_yaml_files(root, include_multi_parameter=include_multi_parameter))
    by_name: dict[str, list[Path]] = defaultdict(list)
    for p in files:
        by_name[p.name].append(p)

    lines: list[str] = []
    for name in sorted(by_name.keys()):
        rels = sorted(by_name[name], key=lambda x: str(x))
        if len(rels) > 1:
            for p in rels:
                rel = p.relative_to(root).as_posix()
                lines.append(f"{name}\t{rel}")
        else:
            lines.append(name)
    return "\n".join(lines)


def list_jailbreak_templates_json(*, include_multi_parameter: bool) -> str:
    root = JAILBREAK_TEMPLATES_PATH
    files = sorted(_iter_yaml_files(root, include_multi_parameter=include_multi_parameter), key=lambda p: (p.name, str(p)))
    payload = [{"name": p.name, "relative_path": p.relative_to(root).as_posix()} for p in files]
    return json.dumps(payload, indent=2)
