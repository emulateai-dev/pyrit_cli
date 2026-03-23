"""Run stateless prompt converters on arbitrary text (same keys as red-team stacking)."""

from __future__ import annotations

import asyncio

from pyrit.setup import IN_MEMORY, initialize_pyrit_async

from pyrit_cli.registries.converters import make_converters


async def run_converter_pipeline(text: str, keys: list[str]) -> str:
    await initialize_pyrit_async(memory_db_type=IN_MEMORY, silent=True)  # type: ignore[arg-type]
    converters = make_converters(keys)
    current = text
    for conv in converters:
        result = await conv.convert_async(prompt=current)
        current = result.output_text
    return current


def run_converter_pipeline_sync(text: str, keys: list[str]) -> str:
    return asyncio.run(run_converter_pipeline(text, keys))
