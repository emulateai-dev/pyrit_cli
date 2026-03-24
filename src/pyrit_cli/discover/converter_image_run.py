"""Run PyRIT image converters through a CLI-friendly wrapper."""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any

from pyrit.setup import IN_MEMORY, initialize_pyrit_async


def _resolve_ctor_kwargs(cls: type, kwargs: dict[str, Any]) -> dict[str, Any]:
    sig = inspect.signature(cls.__init__)
    return {k: v for k, v in kwargs.items() if k in sig.parameters}


async def _convert_with_instance(instance: Any, prompt: str) -> str:
    result = await instance.convert_async(prompt=prompt)
    return str(result.output_text)


async def run_image_qrcode(text: str) -> str:
    from pyrit.prompt_converter import QRCodeConverter

    await initialize_pyrit_async(memory_db_type=IN_MEMORY, silent=True)  # type: ignore[arg-type]
    return await _convert_with_instance(QRCodeConverter(), text)


async def run_image_compress(input_path: Path, *, quality: int) -> str:
    from pyrit.prompt_converter import ImageCompressionConverter

    await initialize_pyrit_async(memory_db_type=IN_MEMORY, silent=True)  # type: ignore[arg-type]
    kwargs = _resolve_ctor_kwargs(ImageCompressionConverter, {"quality": quality})
    converter = ImageCompressionConverter(**kwargs)
    return await _convert_with_instance(converter, str(input_path))


async def run_image_add_text_image(image_path: Path, *, text: str) -> str:
    from pyrit.prompt_converter import AddTextImageConverter

    await initialize_pyrit_async(memory_db_type=IN_MEMORY, silent=True)  # type: ignore[arg-type]
    kwargs = _resolve_ctor_kwargs(AddTextImageConverter, {"text_to_add": text})
    converter = AddTextImageConverter(**kwargs)
    return await _convert_with_instance(converter, str(image_path))


async def run_image_add_image_text(base_image_path: Path, *, text: str) -> str:
    from pyrit.prompt_converter import AddImageTextConverter

    await initialize_pyrit_async(memory_db_type=IN_MEMORY, silent=True)  # type: ignore[arg-type]
    kwargs = _resolve_ctor_kwargs(AddImageTextConverter, {"img_to_add": str(base_image_path)})
    converter = AddImageTextConverter(**kwargs)
    return await _convert_with_instance(converter, text)


async def run_image_transparency(
    benign_image_path: Path,
    attack_image_path: Path,
    *,
    size: int,
    steps: int,
    learning_rate: float,
) -> str:
    from pyrit.prompt_converter import TransparencyAttackConverter

    await initialize_pyrit_async(memory_db_type=IN_MEMORY, silent=True)  # type: ignore[arg-type]
    kwargs = _resolve_ctor_kwargs(
        TransparencyAttackConverter,
        {
            "benign_image_path": benign_image_path,
            "size": (size, size),
            "steps": steps,
            "learning_rate": learning_rate,
        },
    )
    converter = TransparencyAttackConverter(**kwargs)
    return await _convert_with_instance(converter, str(attack_image_path))


def run_image_qrcode_sync(text: str) -> str:
    return asyncio.run(run_image_qrcode(text))


def run_image_compress_sync(input_path: Path, *, quality: int) -> str:
    return asyncio.run(run_image_compress(input_path, quality=quality))


def run_image_add_text_image_sync(image_path: Path, *, text: str) -> str:
    return asyncio.run(run_image_add_text_image(image_path, text=text))


def run_image_add_image_text_sync(base_image_path: Path, *, text: str) -> str:
    return asyncio.run(run_image_add_image_text(base_image_path, text=text))


def run_image_transparency_sync(
    benign_image_path: Path,
    attack_image_path: Path,
    *,
    size: int,
    steps: int,
    learning_rate: float,
) -> str:
    return asyncio.run(
        run_image_transparency(
            benign_image_path,
            attack_image_path,
            size=size,
            steps=steps,
            learning_rate=learning_rate,
        )
    )
