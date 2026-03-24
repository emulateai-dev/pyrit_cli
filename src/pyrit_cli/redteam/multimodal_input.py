"""Helpers for optional multimodal (text + image path) attack inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pyrit.models import SeedGroup, SeedPrompt


def validate_image_paths(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if not p.is_file():
            raise ValueError(f"--input-image path not found: {p}")
        out.append(p)
    return out


def build_seed_group(*, input_text: str | None, input_images: list[Path]) -> SeedGroup:
    seeds: list[SeedPrompt] = []
    if input_text and input_text.strip():
        seeds.append(SeedPrompt(value=input_text.strip(), data_type="text"))
    for image in input_images:
        seeds.append(SeedPrompt(value=str(image), data_type="image_path"))
    if not seeds:
        raise ValueError("At least one multimodal input piece is required.")
    return SeedGroup(seeds=seeds)


def target_supports_image_input(target: Any) -> bool:
    """Best-effort capability check; if unknown, allow execution."""
    caps = getattr(target, "custom_capabilities", None) or getattr(target, "target_capabilities", None)
    if caps is None:
        return True
    modalities = getattr(caps, "input_modalities", None)
    if modalities is None:
        return True
    text_or_image = {"text", "image_path"}
    image_only = {"image_path"}
    for item in modalities:
        try:
            mod_set = set(item)
        except TypeError:
            continue
        if mod_set == image_only or mod_set == text_or_image:
            return True
    return False
