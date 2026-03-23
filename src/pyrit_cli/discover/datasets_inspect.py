"""Preview dataset contents for pyrit: file/registered specs and hf: hubs."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pyrit.common.path import DATASETS_PATH
from pyrit.datasets import SeedDatasetProvider
from pyrit.models import SeedDataset
from pyrit.setup import IN_MEMORY, initialize_pyrit_async

# Ensure provider registry is populated (local + remote dataset classes).
from pyrit.datasets.seed_datasets import local, remote  # noqa: F401

from pyrit_cli.redteam.prompt_sending import resolve_pyrit_dataset_path


def _truncate(text: str, max_len: int = 240) -> str:
    one_line = text.replace("\r", "").replace("\n", " ")
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 3] + "..."


def _format_seed_dataset_preview(ds: SeedDataset, *, limit: int) -> str:
    lines: list[str] = []
    name = ds.dataset_name or ds.name or "(unnamed)"
    lines.append(f"Dataset: {name}")
    if ds.description:
        lines.append(f"Description: {_truncate(str(ds.description), 300)}")
    if ds.harm_categories:
        lines.append(f"Harm categories: {', '.join(ds.harm_categories)}")
    n = len(ds.seeds)
    lines.append(f"Seeds: {n} (preview up to {limit})")
    lines.append("-" * 60)
    for i, seed in enumerate(ds.seeds[:limit], start=1):
        val = getattr(seed, "value", str(seed))
        lines.append(f"[{i}] {_truncate(str(val))}")
    if n > limit:
        lines.append(f"... ({n - limit} more)")
    return "\n".join(lines)


async def _inspect_pyrit_registered_async(dataset_name: str, *, limit: int) -> str:
    await initialize_pyrit_async(memory_db_type=IN_MEMORY)  # type: ignore[arg-type]
    available = SeedDatasetProvider.get_all_dataset_names()
    if dataset_name not in available:
        raise ValueError(
            f"Unknown registered dataset {dataset_name!r}. "
            f"Try: pyrit-cli datasets inspect pyrit:<path> or pick from SeedDatasetProvider "
            f"(see https://azure.github.io/PyRIT/code/datasets/loading-datasets/). "
            f"Sample names: {', '.join(available[:8])}..."
        )
    fetched = await SeedDatasetProvider.fetch_datasets_async(
        dataset_names=[dataset_name],
        cache=True,
        max_concurrency=1,
    )
    if not fetched:
        raise RuntimeError(f"Provider returned no data for {dataset_name!r}")
    return _format_seed_dataset_preview(fetched[0], limit=limit)


def inspect_pyrit_file(spec: str, *, limit: int) -> str:
    path = resolve_pyrit_dataset_path(spec)
    if not path.is_file():
        raise FileNotFoundError(f"PyRIT dataset file not found: {path}")
    ds = SeedDataset.from_yaml_file(path)
    header = [
        f"Source: file {path}",
        f"Resolved under DATASETS_PATH: {DATASETS_PATH}",
    ]
    return "\n".join(header) + "\n" + _format_seed_dataset_preview(ds, limit=limit)


def inspect_hf(
    repo_id: str,
    *,
    limit: int,
    split: str,
    column: str,
    config: str | None,
) -> str:
    try:
        from datasets import load_dataset
    except ImportError as e:
        raise ImportError(
            "Hugging Face preview requires: pip install 'pyrit-cli[hf]' or pip install datasets"
        ) from e

    kwargs: dict[str, Any] = {}
    if config:
        kwargs["name"] = config
    stream = load_dataset(repo_id, split=split, streaming=True, **kwargs)
    rows: list[str] = []
    for row in stream:
        if column not in row:
            raise ValueError(f"Column {column!r} not in row keys: {list(row.keys())}")
        val = row[column]
        if val is None or not str(val).strip():
            continue
        rows.append(str(val))
        if len(rows) >= limit:
            break

    lines = [
        f"Hugging Face: {repo_id}",
        f"split={split!r} column={column!r}"
        + (f" config={config!r}" if config else ""),
        f"Preview: first {len(rows)} non-empty row(s) (streaming; total size not computed)",
        "-" * 60,
    ]
    for i, r in enumerate(rows, start=1):
        lines.append(f"[{i}] {_truncate(r)}")
    if not rows:
        lines.append("(no rows in preview window; check split/column)")
    return "\n".join(lines)


def parse_inspect_spec(raw: str) -> tuple[str, dict[str, Any]]:
    """
    Returns (kind, payload).

    kind: 'hf' | 'pyrit_file' | 'pyrit_registered'
    payload: str (repo id, file spec, or registered name)
    """
    s = raw.strip()
    sl = s.lower()
    if sl.startswith("hf:"):
        repo = s.split(":", 1)[1].strip()
        if not repo:
            raise ValueError("Invalid hf: spec; use hf:<org/dataset>")
        return "hf", {"repo_id": repo}
    if sl.startswith("pyrit:"):
        rest = s[6:].strip()
        if not rest:
            raise ValueError("Invalid pyrit: spec; use pyrit:<path> or pyrit:<registered_name>")
        path_candidate = (Path(DATASETS_PATH) / rest).resolve()
        names = SeedDatasetProvider.get_all_dataset_names()
        if path_candidate.is_file():
            return "pyrit_file", {"spec": s}
        if rest in names:
            return "pyrit_registered", {"name": rest}
        if "/" in rest or rest.endswith((".yaml", ".yml", ".prompt")):
            return "pyrit_file", {"spec": s}
        raise ValueError(
            f"Not a dataset file under DATASETS_PATH and not a registered name: {rest!r}. "
            f"Files: pyrit:seed_datasets/... Registered examples: airt_illegal, harmbench, ..."
        )
    raise ValueError(
        "Spec must start with pyrit: or hf: (e.g. pyrit:seed_datasets/local/airt/illegal.prompt "
        "or pyrit:airt_illegal or hf:imdb)."
    )


async def inspect_dataset_async(
    spec: str,
    *,
    limit: int,
    hf_split: str,
    hf_column: str,
    hf_config: str | None,
) -> str:
    kind, payload = parse_inspect_spec(spec)
    if kind == "hf":
        return inspect_hf(
            payload["repo_id"],
            limit=limit,
            split=hf_split,
            column=hf_column,
            config=hf_config,
        )
    if kind == "pyrit_file":
        return inspect_pyrit_file(payload["spec"], limit=limit)
    return await _inspect_pyrit_registered_async(payload["name"], limit=limit)


def run_dataset_inspect(
    spec: str,
    *,
    limit: int,
    hf_split: str,
    hf_column: str,
    hf_config: str | None,
) -> str:
    """Run inspect (async for PyRIT registered built-ins that use SeedDatasetProvider)."""
    return asyncio.run(
        inspect_dataset_async(
            spec,
            limit=limit,
            hf_split=hf_split,
            hf_column=hf_column,
            hf_config=hf_config,
        )
    )
