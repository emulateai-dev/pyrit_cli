"""Phoenix tracing bootstrap aligned with dtx_kali_mcp.

Fail-open behavior:
- If disabled by env, do nothing.
- If dependencies are missing, do nothing.
- If initialization fails, do nothing.
"""

from __future__ import annotations

import os
import threading
from importlib.util import find_spec
from collections.abc import Callable

_TRACE_LOCK = threading.Lock()
_TRACE_STATE = {"initialized": False, "enabled": False}


def _env_enabled(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def setup_phoenix_tracing(
    service_name: str = "pyrit-cli",
    log: Callable[[str], None] | None = None,
) -> bool:
    with _TRACE_LOCK:
        if _TRACE_STATE["initialized"]:
            return bool(_TRACE_STATE["enabled"])

        _TRACE_STATE["initialized"] = True

        enabled_by_env = os.getenv("PHOENIX_TRACING_ENABLED")
        if not _env_enabled("PHOENIX_TRACING_ENABLED", default=False):
            _TRACE_STATE["enabled"] = False
            # Stay quiet by default; only log when user explicitly set the env var.
            if log and enabled_by_env is not None:
                log("Phoenix tracing disabled via PHOENIX_TRACING_ENABLED.")
            return False

        endpoint = str(
            os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:16007/v1/traces")
        ).strip()
        project_name = str(os.getenv("PHOENIX_PROJECT_NAME", "pyrit-cli")).strip() or "pyrit-cli"

        os.environ.setdefault("OTEL_SERVICE_NAME", service_name)
        os.environ.setdefault("PHOENIX_COLLECTOR_ENDPOINT", endpoint)
        os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", endpoint)
        os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", endpoint)

        try:
            from phoenix.otel import register
        except Exception as exc:
            _TRACE_STATE["enabled"] = False
            if log:
                log(f"Phoenix tracing disabled: tracing dependencies unavailable ({exc}).")
            return False

        try:
            auto_instrument = _env_enabled("PHOENIX_AUTO_INSTRUMENT", default=False)
            tracer_provider = register(
                project_name=project_name,
                endpoint=endpoint,
                protocol="http/protobuf",
                auto_instrument=auto_instrument,
            )
            try:
                from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

                HTTPXClientInstrumentor().instrument(tracer_provider=tracer_provider)
            except Exception:
                pass
            if find_spec("langchain_core") is not None:
                try:
                    from openinference.instrumentation.langchain import LangChainInstrumentor

                    LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
                except Exception:
                    pass
            try:
                from openinference.instrumentation.openai import OpenAIInstrumentor

                OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
            except Exception:
                pass
            _TRACE_STATE["enabled"] = True
        except Exception as exc:
            _TRACE_STATE["enabled"] = False
            if log:
                log(f"Phoenix tracing disabled: failed to initialize tracing ({exc}).")
            return False

        if log:
            log(
                f"Phoenix tracing enabled: endpoint={endpoint}, project={project_name}, "
                f"service={service_name}, auto_instrument={auto_instrument}"
            )
        return True
