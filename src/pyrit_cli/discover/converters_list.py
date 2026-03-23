"""List converter modalities (requires PyRIT init)."""

from __future__ import annotations

import asyncio
import json

from pyrit.prompt_converter import get_converter_modalities
from pyrit.setup import IN_MEMORY, initialize_pyrit_async


async def _list_async() -> list[tuple[str, list, list]]:
    await initialize_pyrit_async(memory_db_type=IN_MEMORY)  # type: ignore[arg-type]
    return list(get_converter_modalities())


def list_converters_text() -> str:
    rows_raw = asyncio.run(_list_async())
    rows = []
    for name, inputs, outputs in rows_raw:
        in_s = ", ".join(str(x) for x in inputs) if inputs else "any"
        out_s = ", ".join(str(x) for x in outputs) if outputs else "any"
        rows.append((name, in_s, out_s))
    lines = [f"{'Converter':<45} {'Input':<25} {'Output':<25}"]
    lines.append("-" * 95)
    for name, ins, outs in sorted(rows, key=lambda r: (r[1], r[2], r[0])):
        lines.append(f"{name:<45} {ins:<25} {outs:<25}")
    return "\n".join(lines)


def list_converters_json() -> str:
    rows_raw = asyncio.run(_list_async())
    payload = [
        {
            "converter": name,
            "input_modalities": [str(x) for x in inputs],
            "output_modalities": [str(x) for x in outputs],
        }
        for name, inputs, outputs in rows_raw
    ]
    payload.sort(key=lambda d: (d["input_modalities"], d["output_modalities"], d["converter"]))
    return json.dumps(payload, indent=2)
