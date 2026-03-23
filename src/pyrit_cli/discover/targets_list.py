"""CLI-supported targets vs PyRIT library targets."""

from __future__ import annotations

_SUPPORTED = [
    (
        "openai:<model>",
        "OpenAIChatTarget using OPENAI_CHAT_ENDPOINT / OPENAI_CHAT_KEY / OPENAI_CHAT_MODEL from ~/.pyrit.",
    ),
    (
        "groq:<model>",
        "Groq OpenAI-compatible API. Env: GROQ_API_KEY; optional GROQ_OPENAI_BASE_URL (default https://api.groq.com/openai/v1).",
    ),
    (
        "ollama:<model>",
        "Local Ollama (/v1 chat). Env: OLLAMA_HOST (default 127.0.0.1:11434 or full URL); optional OLLAMA_API_KEY.",
    ),
    (
        "lmstudio:<model>",
        "LM Studio local server. Env: LMSTUDIO_OPENAI_BASE_URL (default http://127.0.0.1:1234/v1); optional LMSTUDIO_API_KEY.",
    ),
    (
        "compat:<model>",
        "Custom OpenAI-compatible base URL. Env: PYRIT_CLI_COMPAT_ENDPOINT (required), PYRIT_CLI_COMPAT_API_KEY (optional).",
    ),
    (
        "http | https://host/path…",
        "Victim-only HTTPTarget (raw HTTP). Use literal `http` or pass the full endpoint URL as "
        "`--target` / `--objective-target` when the `.req` file uses a path-only request line — the CLI merges the URL into the first line. "
        "Requires --http-request FILE and --http-response-parser (json:|regex:|jq:). "
        "See HELP; example: examples/http_target/sample_openai_chat.req. red-teaming needs --adversarial-target <chat>. "
        "Not supported for tap-attack.",
    ),
]

_NOT_EXPOSED = [
    "OpenAIResponseTarget (Responses API — see PyRIT docs)",
    "AzureMLChatTarget",
    "HuggingFaceChatTarget",
    "HuggingFaceEndpointTarget",
    "OpenAIImageTarget",
    "OpenAICompletionTarget",
    "TextTarget",
    "HTTPXAPITarget",
    "PlaywrightTarget",
    "GandalfTarget",
    "CrucibleTarget",
    "... see pyrit.prompt_target",
]


def list_targets_text() -> str:
    lines = [
        "Supported by pyrit-cli (use with --target / --objective-target / --adversarial-target / --scorer-chat-target):",
        "-" * 60,
    ]
    for pat, note in _SUPPORTED:
        lines.append(f"  {pat}")
        lines.append(f"      {note}")
    lines.append("")
    lines.append("PyRIT: chat vs Responses — https://azure.github.io/PyRIT/code/targets/openai-responses-target/")
    lines.append("PyRIT: HTTP target — https://azure.github.io/PyRIT/code/targets/http-target/")
    lines.append("")
    lines.append("Not yet exposed via CLI (available in PyRIT library):")
    lines.append("-" * 60)
    for n in _NOT_EXPOSED:
        lines.append(f"  {n}")
    return "\n".join(lines)
