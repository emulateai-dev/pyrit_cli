"""Suggest pyrit-cli commands using HELP.md + OpenAI-compatible chat API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from pyrit_cli.env_status import pyrit_dir
from pyrit_cli.help_loader import load_help_markdown

_DEFAULT_BASE = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o-mini"

# Max bytes per file attached to ask-ai (request template or response sample).
ASK_AI_ATTACHMENT_MAX_BYTES = 64 * 1024


def load_pyrit_dotenv() -> None:
    d = pyrit_dir()
    load_dotenv(d / ".env", override=False)
    load_dotenv(d / ".env.local", override=True)


def resolve_api_key(explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    for key in ("OPENAI_API_KEY", "OPENAI_CHAT_KEY"):
        v = os.environ.get(key, "").strip()
        if v and not v.startswith("${"):
            return v
    raise ValueError(
        "No API key: pass --api-key or set OPENAI_API_KEY or OPENAI_CHAT_KEY in the environment "
        "(e.g. after `pyrit-cli setup configure` or in ~/.pyrit/.env)."
    )


def resolve_base_url(explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip().rstrip("/")
    v = os.environ.get("OPENAI_CHAT_ENDPOINT", "").strip()
    if v and not v.startswith("${"):
        return v.rstrip("/")
    return _DEFAULT_BASE


def _chat_completions_url(base: str) -> str:
    return f"{base.rstrip('/')}/chat/completions"


def read_ask_ai_file(path: Path, *, max_bytes: int = ASK_AI_ATTACHMENT_MAX_BYTES) -> str:
    """Read a UTF-8 text file for ask-ai attachments; enforce size and regular-file checks."""
    p = path.expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"Attachment not found: {p}")
    if not p.is_file():
        raise IsADirectoryError(f"Attachment path is not a regular file: {p}")
    size = p.stat().st_size
    if size > max_bytes:
        raise ValueError(
            f"Attachment {p} is {size} bytes (max {max_bytes}); truncate or use a smaller file."
        )
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"Attachment {p} is not valid UTF-8 text: {e}") from e


def build_ask_ai_user_message(
    goal: str,
    *,
    http_request_file: Path | None = None,
    http_response_sample: Path | None = None,
    max_bytes: int = ASK_AI_ATTACHMENT_MAX_BYTES,
) -> str:
    """Build the user message, optionally appending HTTP template and/or response sample bodies."""
    parts: list[str] = [
        "User question (answer in the format described in your instructions):\n\n",
        goal.strip(),
        "\n\n",
    ]
    if http_request_file is not None:
        text = read_ask_ai_file(http_request_file, max_bytes=max_bytes)
        rp = http_request_file.expanduser().resolve()
        parts.append("Attached HTTP request template (for `--http-request`) from `")
        parts.append(str(rp))
        parts.append("`:\n\n```http\n")
        parts.append(text)
        parts.append("\n```\n\n")
    if http_response_sample is not None:
        text = read_ask_ai_file(http_response_sample, max_bytes=max_bytes)
        sp = http_response_sample.expanduser().resolve()
        parts.append(
            "Sample HTTP response body (to derive `--http-response-parser`) from `"
        )
        parts.append(str(sp))
        parts.append("`:\n\n```\n")
        parts.append(text)
        parts.append("\n```\n\n")
    parts.append(
        "If the question is broad, prioritize multiple variants with prerequisites for each."
    )
    return "".join(parts)


def _ask_ai_system_prompt(help_md: str, *, http_file_context: bool = False) -> str:
    http_block = ""
    if http_file_context:
        http_block = (
            "## HTTP file attachments (user message may include these)\n"
            "When the user message includes an attached HTTP request template and/or a sample response body:\n"
            "- Propose or refine a **complete** raw HTTP request (method, URL or path, Host header if needed, "
            "headers, blank line, body) suitable for saving to a file and passing as `--http-request`. "
            "Use the default prompt placeholder **`{PROMPT}`** where the objective text must be injected "
            "(or note `--http-prompt-placeholder` if another token is used).\n"
            "- For JSON bodies embedding the user text, recommend `--http-json-body-converter` on "
            "`prompt-sending-attack` or `red-teaming-attack` when HELP says to (see HTTP victim flags).\n"
            "- Propose exactly one **`--http-response-parser`** value using only these forms from HELP: "
            "**`json:KEYPATH`**, **`regex:PATTERN`**, or **`jq:EXPR`**. Prefer **`json:`** when the sample "
            "body is JSON and a stable key path exists (e.g. OpenAI-style `choices[0].message.content`). "
            "Otherwise **`regex:`** or **`jq:`** with a one-line rationale.\n"
            "- Include a fenced **bash** example: `pyrit-cli redteam prompt-sending-attack` or "
            "`red-teaming-attack` with `--target` / `--objective-target` as literal `http` **or** a full "
            "`https://...` / `http://...` victim URL (when the template uses a path-only request line), "
            "`--http-request <path-to-file>`, `--http-response-parser '...'`, and if multi-turn with HTTP "
            "victim, `--adversarial-target` as a chat spec per HELP.\n"
            "- Remind the user to redact secrets; attached file contents were sent to this chat API.\n\n"
        )

    return (
        "You help users with pyrit-cli for **authorized** red-teaming and workshop demos only. "
        "Every fact and flag must come from the HELP reference below — do not invent subcommands or options.\n\n"
        "## Output format\n"
        "- Use Markdown. For each distinct approach, use a short heading (e.g. **Variant 1 — single-turn**).\n"
        "- Immediately under each heading, a **Prerequisites** bullet list: which environment variables must be set, "
        "with example lines like `export GROQ_API_KEY=\"...\"` or \"ensure OPENAI_CHAT_* in ~/.pyrit (pyrit-cli setup configure)\".\n"
        "  Whenever you suggest `groq:`, `ollama:`, `lmstudio:`, or `compat:` targets, you MUST list their required env vars "
        "(see HELP section \"Environment variables reference\"). `openai:` targets need OPENAI_CHAT_* or setup configure.\n"
        "- Then a fenced bash block ```bash ... ``` containing the full `pyrit-cli` command (line continuations `\\` allowed).\n"
        "- One line after the fence (plain text or `#` comment) summarizing when to use that variant.\n\n"
        "## When to give one vs many variants\n"
        "- **Specific** question (clear model, one attack type, one objective): one variant is enough (still include Prerequisites if not openai-only).\n"
        "- **Generic or exploratory** question (e.g. how to test Groq, how to start, what attacks exist, compare approaches): "
        "give **2–4** clearly different variants when the reference supports them — e.g. prompt-sending-attack vs red-teaming-attack "
        "vs tap-attack; or openai: vs groq: with explicit Groq exports; or benign multi-turn with --true-description.\n\n"
        "## Command choice hints\n"
        "- Single-shot / smoke test → `redteam prompt-sending-attack`.\n"
        "- Multi-turn with scorer → `redteam red-teaming-attack` + `--true-description` (self-ask-tf) unless refusal testing.\n"
        "- Tree / TAP / pruning → `redteam tap-attack` only if relevant.\n"
        "- Use benign placeholder objectives when the user is vague.\n\n"
        + http_block
        + "### pyrit-cli HELP reference\n\n"
        + help_md
    )


def suggest_command(
    user_goal: str,
    *,
    model: str,
    api_key: str,
    base_url: str,
    http_request_file: Path | None = None,
    http_response_sample: Path | None = None,
) -> str:
    help_md = load_help_markdown()
    http_ctx = http_request_file is not None or http_response_sample is not None
    system = _ask_ai_system_prompt(help_md, http_file_context=http_ctx)
    user = build_ask_ai_user_message(
        user_goal,
        http_request_file=http_request_file,
        http_response_sample=http_response_sample,
    )

    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.45,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        _chat_completions_url(base_url),
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Chat API HTTP {e.code}: {detail[:800]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Chat API request failed: {e}") from e

    try:
        choices = payload["choices"]
        return str(choices[0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Unexpected API response: {repr(payload)[:500]}") from e


def run_ask_ai(
    user_goal: str,
    *,
    model: str | None,
    api_key: str | None,
    base_url: str | None,
    http_request_file: Path | None = None,
    http_response_sample: Path | None = None,
) -> str:
    load_pyrit_dotenv()
    key = resolve_api_key(api_key)
    base = resolve_base_url(base_url)
    m = (model or os.environ.get("OPENAI_CHAT_MODEL") or _DEFAULT_MODEL).strip()
    return suggest_command(
        user_goal,
        model=m,
        api_key=key,
        base_url=base,
        http_request_file=http_request_file,
        http_response_sample=http_response_sample,
    )
