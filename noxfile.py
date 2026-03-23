"""Nox automation: editable install of pyrit-cli + pytest (unit vs integration)."""

from __future__ import annotations

import nox

nox.options.default_venv_backend = "virtualenv"
nox.options.sessions = ["tests"]


@nox.session(python=["3.10", "3.12"])
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
    """Integration tests: Hugging Face dataset inspect, Ollama (if model present), etc."""
    session.install("-e", ".[dev,hf]")
    session.run(
        "pytest",
        "tests",
        "-m",
        "integration",
        "--tb=short",
        *session.posargs,
    )


@nox.session(python="3.12")
def lint(session: nox.Session) -> None:
    session.install("-e", ".[dev]")
    session.run("ruff", "check", "src/pyrit_cli", "tests", *session.posargs)
