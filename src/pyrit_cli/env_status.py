"""Env discovery aligned with aisec_gradio.env_manager (keep in sync)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

ConnectionMode = Literal["openai_native", "openai_compatible"]

_SENSITIVE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|API_KEY)", re.I)


def pyrit_dir() -> Path:
    override = os.environ.get("PYRIT_ENV_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".pyrit"


def env_path(name: str) -> Path:
    return pyrit_dir() / name


def ensure_pyrit_dir() -> Path:
    d = pyrit_dir()
    d.mkdir(parents=True, exist_ok=True)
    for f in (".env", ".env.local"):
        p = d / f
        if not p.exists():
            p.touch()
    return d


def parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            out[k] = v
    return out


def mask_value(key: str, value: str) -> str:
    if _SENSITIVE.search(key) and value:
        if len(value) <= 8:
            return "****"
        return value[:4] + "…" + value[-2:]
    return value


def load_for_cli() -> dict:
    """Same heuristics as aisec_gradio.env_manager.load_for_ui."""
    ensure_pyrit_dir()
    main = parse_env_file(env_path(".env"))
    local = parse_env_file(env_path(".env.local"))

    if main.get("PLATFORM_OPENAI_CHAT_ENDPOINT"):
        mode: ConnectionMode = "openai_compatible"
    elif main.get("OPENAI_API_KEY"):
        mode = "openai_native"
    else:
        mode = "openai_compatible"

    display_main = {k: mask_value(k, v) for k, v in main.items()}
    display_local = {k: mask_value(k, v) for k, v in local.items()}

    native_model = local.get("OPENAI_CHAT_MODEL") or main.get("PLATFORM_OPENAI_CHAT_GPT4O_MODEL") or "gpt-4o"

    return {
        "pyrit_dir": str(pyrit_dir()),
        "mode": mode,
        "openai_api_key": main.get("OPENAI_API_KEY", ""),
        "native_model": native_model,
        "endpoint": main.get("PLATFORM_OPENAI_CHAT_ENDPOINT", "https://api.groq.com/openai/v1"),
        "platform_api_key": main.get("PLATFORM_OPENAI_CHAT_API_KEY", ""),
        "model": main.get("PLATFORM_OPENAI_CHAT_GPT4O_MODEL", "qwen/qwen3-32b"),
        "display_main": display_main,
        "display_local": display_local,
    }


def format_setup_report(data: dict) -> str:
    lines = [
        f"PyRIT config directory: {data['pyrit_dir']}",
        f"Inferred mode: {data['mode']}",
        "",
        "OpenAIChatTarget uses OPENAI_CHAT_KEY, OPENAI_CHAT_ENDPOINT, OPENAI_CHAT_MODEL",
        "(often set in .env.local; see workshop README Option A / B).",
        "",
        "~/.pyrit/.env (masked):",
    ]
    if not data["display_main"]:
        lines.append("  (empty)")
    else:
        for k, v in sorted(data["display_main"].items()):
            lines.append(f"  {k}={v}")
    lines.append("")
    lines.append("~/.pyrit/.env.local (masked):")
    if not data["display_local"]:
        lines.append("  (empty)")
    else:
        for k, v in sorted(data["display_local"].items()):
            lines.append(f"  {k}={v}")
    return "\n".join(lines)


GUIDE_TEXT = """
PyRIT + workshop setup (summary)

1) Config directory: ~/.pyrit/ unless PYRIT_ENV_DIR is set.
2) Files: .env and .env.local (both may be loaded by PyRIT).

Option A — OpenAI API
  Put OPENAI_API_KEY in .env and mirror chat overrides in .env.local, e.g.:
    OPENAI_CHAT_ENDPOINT=https://api.openai.com/v1
    OPENAI_CHAT_KEY=<same key>
    OPENAI_CHAT_MODEL=gpt-4o

Option B — OpenAI-compatible host (e.g. Groq)
  In ~/.pyrit/.env set (or use pyrit-cli setup configure):
    PLATFORM_OPENAI_CHAT_ENDPOINT=https://api.groq.com/openai/v1
    PLATFORM_OPENAI_CHAT_API_KEY=gsk_...
    PLATFORM_OPENAI_CHAT_GPT4O_MODEL=llama-3.3-70b-versatile
  In ~/.pyrit/.env.local the wizard writes OPENAI_CHAT_* pointing at those vars
  (OPENAI_CHAT_ENDPOINT=${PLATFORM_OPENAI_CHAT_ENDPOINT}, etc.).

  Run red-team with a model id your host accepts, e.g.:
    pyrit-cli redteam prompt-sending-attack --target openai:llama-3.3-70b-versatile --objective "Reply: OK"
  Or: export GROQ_API_KEY=gsk_... and --target groq:llama-3.3-70b-versatile
""".strip()
