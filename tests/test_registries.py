from __future__ import annotations

import pytest

from pyrit_cli.registries.converters import make_converters


def test_make_converters_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown converter"):
        make_converters(["not-a-real-converter"])


def test_make_converters_order() -> None:
    converters = make_converters(["base64", "rot13"])
    assert len(converters) == 2
