"""Build PyRIT HTTPTarget from CLI flags (see PyRIT HTTP Target docs)."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pyrit.executor.attack import AttackConverterConfig
from pyrit.models import PromptDataType
from pyrit.prompt_converter.prompt_converter import ConverterResult, PromptConverter
from pyrit.prompt_normalizer import PromptConverterConfiguration
from pyrit.prompt_target import HTTPTarget
from pyrit.prompt_target.http_target.http_target_callback_functions import (
    get_http_target_json_response_callback_function,
)

logger = logging.getLogger(__name__)

HTTP_VICTIM_TARGET = "http"


class _JsonBodyEscapeConverter(PromptConverter):
    """JSON-escape text for embedding in HTTP JSON bodies (same idea as PyRIT JsonStringConverter)."""

    SUPPORTED_INPUT_TYPES = ("text",)
    SUPPORTED_OUTPUT_TYPES = ("text",)

    async def convert_async(
        self, *, prompt: str, input_type: PromptDataType = "text"
    ) -> ConverterResult:
        if not self.input_supported(input_type):
            raise ValueError("Input type not supported")
        dumped = json.dumps(prompt)
        escaped = dumped[1:-1]
        return ConverterResult(output_text=escaped, output_type="text")


def is_http_victim_token(spec: str) -> bool:
    return spec.strip().lower() == HTTP_VICTIM_TARGET


def is_http_objective_url(spec: str) -> bool:
    """True if spec looks like an absolute http(s) URL (HTTPTarget endpoint from --objective-target / --target)."""
    s = spec.strip().lower()
    return s.startswith("http://") or s.startswith("https://")


def is_http_victim_spec(spec: str) -> bool:
    """Literal ``http`` or an ``http(s)://...`` URL selects HTTPTarget (with ``--http-*`` flags)."""
    return is_http_victim_token(spec) or is_http_objective_url(spec)


def parse_objective_http_url(spec: str) -> str | None:
    """Return normalized URL string if ``spec`` is an http(s) objective URL; else None. Raises if malformed."""
    if not is_http_objective_url(spec):
        return None
    raw = spec.strip()
    u = urlparse(raw)
    if u.scheme.lower() not in ("http", "https"):
        return None
    if not u.netloc:
        raise ValueError(
            f"HTTP(S) objective URL must include a host (e.g. https://api.example.com/v1/chat): {spec!r}"
        )
    return raw


def merge_http_request_with_objective_url(raw: str, objective_url: str) -> str:
    """Replace the request-target on the first line with ``objective_url``; align Host header with URL netloc."""
    u = urlparse(objective_url.strip())
    if u.scheme.lower() not in ("http", "https") or not u.netloc:
        raise ValueError(
            f"Invalid HTTP(S) objective URL {objective_url!r}; need scheme and host "
            "(e.g. https://api.example.com/v1/chat/completions)."
        )
    text = raw.strip()
    if not text:
        raise ValueError("HTTP request template is empty")
    parts = text.split("\n\n", 1)
    head = parts[0]
    body = parts[1] if len(parts) > 1 else ""
    hlines = head.split("\n")
    first = hlines[0].strip()
    tokens = first.split()
    if len(tokens) < 3:
        raise ValueError(
            f"HTTP request first line must look like 'METHOD /path HTTP/1.1'; got: {first!r}"
        )
    method = tokens[0]
    version = tokens[-1]
    if not version.upper().startswith("HTTP/"):
        raise ValueError(f"Invalid HTTP version in first line: {first!r}")
    new_first = f"{method} {objective_url.strip()} {version}"
    host_val = u.netloc.split("@")[-1]
    new_hlines = [new_first]
    for hl in hlines[1:]:
        if hl.strip().lower().startswith("host:"):
            new_hlines.append(f"Host: {host_val}")
        else:
            new_hlines.append(hl)
    new_head = "\n".join(new_hlines)
    if body:
        return f"{new_head}\n\n{body}"
    return new_head


def _response_body_text(response: Any) -> str:
    """Decode httpx-like response body for regex search (UTF-8; avoids str(bytes) repr issues)."""
    text_attr = getattr(response, "text", None)
    if isinstance(text_attr, str):
        return text_attr
    raw = getattr(response, "content", b"")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def _make_regex_parser_callback(pattern: str, url: str | None) -> Callable[..., Any]:
    """Regex parser over decoded response text (matches PyRIT semantics: full match + optional URL prefix)."""

    re_pattern = re.compile(pattern)

    def parse_using_regex_decoded(response: Any) -> str:
        text = _response_body_text(response)
        match = re_pattern.search(text)
        if match:
            fragment = match.group()
            if url:
                return url + fragment
            return fragment
        return text

    parse_using_regex_decoded.__name__ = "parse_using_regex_decoded"
    return parse_using_regex_decoded


def parse_http_response_parser(
    spec: str,
    *,
    regex_base_url: str | None,
) -> Callable[..., Any]:
    """Return a callback suitable for HTTPTarget (response has .content bytes)."""
    raw = spec.strip()
    if ":" not in raw:
        raise ValueError(
            "Invalid --http-response-parser; use json:KEYPATH, regex:PATTERN, or jq:EXPR "
            "(see pyrit-cli HELP)."
        )
    kind, payload = raw.split(":", 1)
    kind_l = kind.strip().lower()
    payload = payload.strip()
    if not payload:
        raise ValueError(f"Empty payload for {kind_l!r} parser.")

    if kind_l == "json":
        return get_http_target_json_response_callback_function(key=payload)

    if kind_l == "regex":
        return _make_regex_parser_callback(
            payload,
            url=regex_base_url.strip() if regex_base_url else None,
        )

    if kind_l == "jq":
        return _make_jq_callback(payload)

    raise ValueError(
        f"Unknown parser type {kind!r}; use json:, regex:, or jq: (got prefix {kind_l!r})."
    )


def _make_jq_callback(jq_expr: str) -> Callable[..., Any]:
    if not shutil.which("jq"):
        raise ValueError(
            "jq is not on PATH; install jq (https://jqlang.org/) or use json:KEYPATH instead of jq:."
        )

    def parse_with_jq(response: Any) -> str:
        body = response.content if hasattr(response, "content") else response
        if isinstance(body, str):
            body_b = body.encode("utf-8")
        else:
            body_b = body
        try:
            proc = subprocess.run(
                ["jq", "-r", jq_expr],
                input=body_b,
                capture_output=True,
                check=False,
                timeout=60,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("jq subprocess timed out") from e
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"jq failed (exit {proc.returncode}): {err}")
        out = proc.stdout.decode("utf-8", errors="replace").strip()
        if out == "null":
            return ""
        return out

    parse_with_jq.__name__ = "parse_with_jq"
    return parse_with_jq


def load_raw_http_request(path: Path) -> str:
    p = path.expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"HTTP request file not found: {p}")
    return p.read_text(encoding="utf-8")


def build_http_objective_target(
    *,
    request_path: Path,
    response_parser_spec: str,
    prompt_placeholder: str,
    regex_base_url: str | None,
    use_tls: bool,
    timeout: float | None,
    model_name: str,
    objective_url: str | None = None,
) -> HTTPTarget:
    http_request = load_raw_http_request(request_path)
    if objective_url:
        http_request = merge_http_request_with_objective_url(http_request, objective_url)
    callback = parse_http_response_parser(response_parser_spec, regex_base_url=regex_base_url)
    if not re.search(prompt_placeholder, http_request):
        logger.warning(
            "Prompt placeholder %r not found in HTTP request; injection may not occur.",
            prompt_placeholder,
        )
    httpx_kw: dict[str, Any] = {}
    if timeout is not None:
        httpx_kw["timeout"] = float(timeout)
    return HTTPTarget(
        http_request=http_request,
        prompt_regex_string=prompt_placeholder,
        use_tls=use_tls,
        callback_function=callback,
        model_name=model_name,
        **httpx_kw,
    )


def build_http_json_escape_converter_config() -> AttackConverterConfig:
    req_list = PromptConverterConfiguration.from_converters(converters=[_JsonBodyEscapeConverter()])
    return AttackConverterConfig(request_converters=req_list, response_converters=[])
