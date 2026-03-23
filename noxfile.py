"""Nox automation: editable install of pyrit-cli + pytest (unit vs integration)."""

from __future__ import annotations

import nox

nox.options.default_venv_backend = "virtualenv"
nox.options.sessions = ["tests"]
nox.options.error_on_missing_interpreters = False


@nox.session(python=["3.10", "3.12"], reuse_venv=True)
def tests(session: nox.Session) -> None:
    """Install pyrit-cli with dev+hf extras; run fast tests (excludes integration)."""
    session.install("-e", ".[dev,hf]")
    session.run(
        "pytest",
        "tests",
        "-m",
        "not integration",
        "--tb=short",
        *session.posargs,
    )


@nox.session(python="3.12")
def integration(session: nox.Session) -> None:
    """Ollama (if ``qwen3:0.6b``). Optional HF: ``nox -s integration -- --with-hf``."""
    session.install("-e", ".[dev,hf]")
    want_hf = "--with-hf" in session.posargs
    args = [a for a in session.posargs if a != "--with-hf"]
    run_env = {"RUN_HF_INTEGRATION": "1"} if want_hf else {}
    session.run(
        "pytest",
        "tests",
        "-m",
        "integration",
        "--tb=short",
        *args,
        env=run_env,
    )


@nox.session(python="3.12")
def lint(session: nox.Session) -> None:
    session.install("-e", ".[dev]")
    session.run("ruff", "check", "src/pyrit_cli", "tests", *session.posargs)
