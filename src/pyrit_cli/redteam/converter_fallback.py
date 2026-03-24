"""Curated stateless converter stacks for opt-in fallback retries (benchmark, TAP, Crescendo)."""

from __future__ import annotations

from pyrit.executor.attack import AttackConverterConfig
from pyrit.prompt_normalizer import PromptConverterConfiguration

from pyrit_cli.registries.converters import make_converters

# Lightweight stacks only (avoid ascii-art and other token-heavy converters by default).
CURATED_FALLBACK_STACKS: list[list[str]] = [
    ["rot13"],
    ["base64"],
    ["rot13", "base64"],
]


def parse_fallback_stack_arg(spec: str) -> list[str]:
    """Parse 'rot13,base64' -> ['rot13', 'base64']."""
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    if not parts:
        raise ValueError("Empty --converter-fallback-stack; use comma-separated keys.")
    return parts


def resolve_fallback_converter_stacks(
    *,
    enabled: bool,
    max_stacks: int,
    explicit_stacks: list[list[str]] | None,
) -> list[list[str]]:
    if not enabled or max_stacks <= 0:
        return []
    if explicit_stacks:
        return [list(s) for s in explicit_stacks[:max_stacks]]
    return [list(s) for s in CURATED_FALLBACK_STACKS[:max_stacks]]


def attack_converter_config_for_stack(keys: list[str]) -> AttackConverterConfig | None:
    if not keys:
        return None
    req = PromptConverterConfiguration.from_converters(converters=make_converters(keys))
    return AttackConverterConfig(request_converters=req, response_converters=[])
