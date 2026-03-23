"""Write ~/.pyrit/.env and .env.local — keep in sync with aisec_gradio.env_manager."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pyrit_cli.env_status import ensure_pyrit_dir, parse_env_file


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".env_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def merge_write(path: Path, updates: dict[str, str], *, remove_keys: frozenset[str] | None = None) -> None:
    existing = parse_env_file(path)
    if remove_keys:
        for k in remove_keys:
            existing.pop(k, None)
    existing.update({k: v for k, v in updates.items() if v is not None})
    lines = [f'{k}="{v}"' if " " in v or "$" in v else f"{k}={v}" for k, v in sorted(existing.items())]
    _atomic_write(path, "\n".join(lines) + "\n")


def save_openai_native(openai_api_key: str, *, model: str = "gpt-4.1-mini") -> tuple[str, str]:
    d = ensure_pyrit_dir()
    env_main = d / ".env"
    env_local = d / ".env.local"

    platform_keys = frozenset(
        {
            "PLATFORM_OPENAI_CHAT_ENDPOINT",
            "PLATFORM_OPENAI_CHAT_API_KEY",
            "PLATFORM_OPENAI_CHAT_GPT4O_MODEL",
        }
    )

    merge_write(env_main, {"OPENAI_API_KEY": openai_api_key.strip()}, remove_keys=platform_keys)
    merge_write(
        env_local,
        {
            "OPENAI_CHAT_ENDPOINT": "https://api.openai.com/v1",
            "OPENAI_CHAT_KEY": openai_api_key.strip(),
            "OPENAI_CHAT_MODEL": model.strip(),
        },
    )
    return f"Saved {env_main}", f"Updated {env_local} (OpenAIChatTarget mapping)"


def save_openai_compatible(
    endpoint: str,
    api_key: str,
    model: str,
) -> tuple[str, str]:
    d = ensure_pyrit_dir()
    env_main = d / ".env"
    env_local = d / ".env.local"

    main_updates = {
        "PLATFORM_OPENAI_CHAT_ENDPOINT": endpoint.strip().rstrip("/"),
        "PLATFORM_OPENAI_CHAT_API_KEY": api_key.strip(),
        "PLATFORM_OPENAI_CHAT_GPT4O_MODEL": model.strip(),
    }
    merge_write(env_main, main_updates, remove_keys=frozenset({"OPENAI_API_KEY"}))

    local_content = (
        "# Overrides for default OpenAIChatTarget (PyRIT)\n"
        'OPENAI_CHAT_ENDPOINT="${PLATFORM_OPENAI_CHAT_ENDPOINT}"\n'
        'OPENAI_CHAT_KEY="${PLATFORM_OPENAI_CHAT_API_KEY}"\n'
        f'OPENAI_CHAT_MODEL="{model.strip()}"\n'
    )
    _atomic_write(env_local, local_content)
    return f"Updated {env_main}", f"Updated {env_local}"
