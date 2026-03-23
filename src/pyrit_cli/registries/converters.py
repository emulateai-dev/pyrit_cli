"""Stateless prompt converters (no extra LLM target). Keys match ``--request-converter`` / ``--response-converter``."""

from __future__ import annotations

from collections.abc import Callable

from pyrit.prompt_converter import (
    AsciiArtConverter,
    AtbashConverter,
    Base64Converter,
    BinaryConverter,
    BrailleConverter,
    EcojiConverter,
    EmojiConverter,
    FirstLetterConverter,
    MorseConverter,
    ROT13Converter,
    StringJoinConverter,
    UnicodeConfusableConverter,
)
from pyrit.prompt_converter.prompt_converter import PromptConverter

ConverterFactory = Callable[[], PromptConverter]

CONVERTER_REGISTRY: dict[str, ConverterFactory] = {
    "ascii-art": lambda: AsciiArtConverter(),
    "atbash": lambda: AtbashConverter(),
    "base64": lambda: Base64Converter(),
    "binary": lambda: BinaryConverter(),
    "braille": lambda: BrailleConverter(),
    "ecoji": lambda: EcojiConverter(),
    "emoji": lambda: EmojiConverter(),
    "first-letter": lambda: FirstLetterConverter(),
    "morse": lambda: MorseConverter(),
    "rot13": lambda: ROT13Converter(),
    "string-join": lambda: StringJoinConverter(),
    "unicode-confusable": lambda: UnicodeConfusableConverter(),
}


def list_converter_keys() -> list[str]:
    return sorted(CONVERTER_REGISTRY.keys())


def make_converters(keys: list[str]) -> list[PromptConverter]:
    out: list[PromptConverter] = []
    for k in keys:
        factory = CONVERTER_REGISTRY.get(k)
        if factory is None:
            raise ValueError(
                f"Unknown converter {k!r}. Use: pyrit-cli converters list (or one of: {', '.join(list_converter_keys())})"
            )
        out.append(factory())
    return out
