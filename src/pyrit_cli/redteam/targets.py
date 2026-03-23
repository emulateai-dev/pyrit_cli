"""Parse CLI target specs into PyRIT OpenAIChatTarget (OpenAI-compatible chat APIs)."""

from __future__ import annotations

import os
from typing import Any

from pyrit.prompt_target import OpenAIChatTarget

# Typer option help (keep in sync with HELP.md and targets list).
TARGET_SPEC_HELP = (
    "<provider>:<model> (openai, groq, ollama, lmstudio, compat), literal `http`, or an "
    "`https://...` / `http://...` URL for HTTPTarget — see targets list / HELP for --http-* flags"
)

# Aliases map to the same routing key used in parse_target_spec.
_PROVIDER_ALIASES: dict[str, str] = {
    "groq": "groq",
    "ollama": "ollama",
    "lmstudio": "lmstudio",
    "lm-studio": "lmstudio",
    "compat": "compat",
    "openai": "openai",
}

_DEFAULT_GROQ_BASE = "https://api.groq.com/openai/v1"
_DEFAULT_LMSTUDIO_BASE = "http://127.0.0.1:1234/v1"
_DUMMY_LOCAL_KEY = "not-needed"


def parse_target_spec(spec: str) -> tuple[str, str]:
    """Split ``provider:model`` (first colon only). Provider is normalized internal name."""
    t = spec.strip()
    if ":" not in t:
        raise ValueError(
            f"Invalid target {spec!r}; expected <provider>:<model>, e.g. openai:gpt-4o-mini, groq:llama-3.3-70b-versatile, ollama:llama3.2"
        )
    raw_provider, model = t.split(":", 1)
    model = model.strip()
    if not model:
        raise ValueError(f"Invalid target {spec!r}; model name is empty")
    key = raw_provider.strip().lower()
    provider = _PROVIDER_ALIASES.get(key)
    if provider is None:
        raise ValueError(
            f"Unknown provider {raw_provider!r}; supported: openai, groq, ollama, lmstudio, compat"
        )
    return provider, model


def parse_openai_target(spec: str) -> str:
    """Parse ``openai:<model_name>`` only (backward compatible)."""
    provider, model = parse_target_spec(spec)
    if provider != "openai":
        raise ValueError(f"Invalid target {spec!r}; expected openai:<model_name>")
    return model


def _groq_base_url() -> str:
    return os.environ.get("GROQ_OPENAI_BASE_URL", _DEFAULT_GROQ_BASE).strip().rstrip("/")


def _ollama_chat_base_url() -> str:
    h = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434").strip()
    if h.startswith("http://") or h.startswith("https://"):
        base = h.rstrip("/")
    else:
        base = f"http://{h}".rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def _lmstudio_base_url() -> str:
    return os.environ.get("LMSTUDIO_OPENAI_BASE_URL", _DEFAULT_LMSTUDIO_BASE).strip().rstrip("/")


def openai_chat_from_spec(spec: str, **kwargs: Any) -> OpenAIChatTarget:
    """Build ``OpenAIChatTarget`` for OpenAI or OpenAI-compatible hosts.

    Specs (first colon separates provider from model; model may contain further colons, e.g.
    ``groq:openai/gpt-oss-120b``):

    - ``openai:<model>`` — uses ``OPENAI_CHAT_*`` / global PyRIT env (default workshop path).
    - ``groq:<model>`` — ``GROQ_API_KEY``; base URL ``GROQ_OPENAI_BASE_URL`` or Groq default.
    - ``ollama:<model>`` — local Ollama OpenAI API; ``OLLAMA_HOST`` (host:port or URL); optional ``OLLAMA_API_KEY``.
    - ``lmstudio:<model>`` — LM Studio local server; ``LMSTUDIO_OPENAI_BASE_URL`` default ``http://127.0.0.1:1234/v1``.
    - ``compat:<model>`` — any OpenAI-compatible server: ``PYRIT_CLI_COMPAT_ENDPOINT`` and optional
      ``PYRIT_CLI_COMPAT_API_KEY`` (omit or empty for no-auth locals).

    For local backends, ``is_json_supported`` defaults to ``False`` unless already set in ``kwargs``.
    """
    provider, model = parse_target_spec(spec)

    if provider == "openai":
        return OpenAIChatTarget(model_name=model, **kwargs)

    if provider == "groq":
        key = os.environ.get("GROQ_API_KEY", "").strip()
        if not key:
            raise ValueError("groq:<model> requires GROQ_API_KEY in the environment.")
        kwargs.setdefault("is_json_supported", True)
        return OpenAIChatTarget(
            model_name=model,
            endpoint=_groq_base_url(),
            api_key=key,
            **kwargs,
        )

    if provider == "ollama":
        key = (os.environ.get("OLLAMA_API_KEY") or _DUMMY_LOCAL_KEY).strip()
        kwargs.setdefault("is_json_supported", False)
        return OpenAIChatTarget(
            model_name=model,
            endpoint=_ollama_chat_base_url(),
            api_key=key,
            **kwargs,
        )

    if provider == "lmstudio":
        key = (os.environ.get("LMSTUDIO_API_KEY") or _DUMMY_LOCAL_KEY).strip()
        kwargs.setdefault("is_json_supported", False)
        return OpenAIChatTarget(
            model_name=model,
            endpoint=_lmstudio_base_url(),
            api_key=key,
            **kwargs,
        )

    if provider == "compat":
        endpoint = os.environ.get("PYRIT_CLI_COMPAT_ENDPOINT", "").strip().rstrip("/")
        if not endpoint:
            raise ValueError(
                "compat:<model> requires PYRIT_CLI_COMPAT_ENDPOINT (OpenAI-compatible base URL, e.g. https://host/v1)."
            )
        key = os.environ.get("PYRIT_CLI_COMPAT_API_KEY", "").strip()
        compat_key = key if key else _DUMMY_LOCAL_KEY
        kwargs.setdefault("is_json_supported", False)
        return OpenAIChatTarget(
            model_name=model,
            endpoint=endpoint,
            api_key=compat_key,
            **kwargs,
        )

    raise ValueError(f"Unsupported provider {provider!r}")
