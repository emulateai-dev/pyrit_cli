"""List seed dataset paths under PyRIT DATASETS_PATH."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from pyrit.common.path import DATASETS_PATH


def list_datasets_text(*, glob_pattern: str | None = None) -> str:
    root = Path(DATASETS_PATH) / "seed_datasets"
    if not root.is_dir():
        return f"No seed_datasets directory at {root}"

    paths: list[Path] = []
    for pat in ("**/*.prompt", "**/*.yaml", "**/*.yml"):
        paths.extend(root.glob(pat))
    rels: list[str] = []
    for p in sorted(set(paths), key=lambda x: str(x).lower()):
        try:
            rel = p.relative_to(Path(DATASETS_PATH))
        except ValueError:
            rel = p
        s = rel.as_posix()
        if glob_pattern and not fnmatch.fnmatch(s, glob_pattern):
            continue
        rels.append(s)

    if not rels:
        return "No matching dataset files."

    lines = [
        "Use with: pyrit-cli redteam prompt-sending-attack --dataset pyrit:<path_below>",
        f"(resolved under PyRIT DATASETS_PATH: {DATASETS_PATH})",
        "-" * 60,
    ]
    lines.extend(rels)
    return "\n".join(lines)
