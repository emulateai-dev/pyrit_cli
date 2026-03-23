"""Subprocess CLI checks (real `python -m pyrit_cli` entry) and optional live services.

Default Nox session excludes ``integration`` markers (no HF download, no Ollama).
Run ``nox -s integration`` for Hugging Face + Ollama scenarios.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from pyrit_cli.env_write import save_openai_compatible


def _run_pyrit_cli(
    *args: str,
    env: dict[str, str] | None = None,
    timeout: float = 300.0,
) -> subprocess.CompletedProcess[str]:
    base = os.environ.copy()
    if env:
        base.update(env)
    return subprocess.run(
        [sys.executable, "-m", "pyrit_cli", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=base,
        check=False,
    )


def test_subprocess_cli_version() -> None:
    p = _run_pyrit_cli("--version")
    assert p.returncode == 0
    assert "pyrit-cli" in p.stdout


def test_subprocess_datasets_inspect_pyrit_seed() -> None:
    p = _run_pyrit_cli(
        "datasets",
        "inspect",
        "pyrit:seed_datasets/local/airt/illegal.prompt",
        "--limit",
        "2",
    )
    assert p.returncode == 0, p.stderr
    assert "Seeds:" in p.stdout or "[1]" in p.stdout


def test_subprocess_datasets_list_glob() -> None:
    p = _run_pyrit_cli("datasets", "list", "--glob", "*airt*")
    assert p.returncode == 0, p.stderr


def test_subprocess_jailbreak_templates_list() -> None:
    p = _run_pyrit_cli("jailbreak-templates", "list")
    assert p.returncode == 0, p.stderr


def test_subprocess_converters_run_rot13() -> None:
    p = _run_pyrit_cli("converters", "run", "-c", "rot13", "Hello")
    assert p.returncode == 0, p.stderr
    out = (p.stdout + p.stderr).lower()
    assert "uryyb" in out or "rot" in out


def test_subprocess_setup_status_custom_env_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``PYRIT_ENV_DIR`` points at an alternate config tree (same contract as ``setup configure`` output)."""
    root = tmp_path / "alt_pyrit"
    root.mkdir()
    monkeypatch.delenv("PYRIT_ENV_DIR", raising=False)
    (root / ".env").write_text('OPENAI_API_KEY="sk-dummy"\n', encoding="utf-8")
    (root / ".env.local").write_text(
        "OPENAI_CHAT_ENDPOINT=https://api.openai.com/v1\n"
        "OPENAI_CHAT_KEY=sk-dummy\n"
        "OPENAI_CHAT_MODEL=gpt-4o-mini\n",
        encoding="utf-8",
    )
    p = _run_pyrit_cli("setup", "status", env={"PYRIT_ENV_DIR": str(root)})
    assert p.returncode == 0, p.stderr
    combined = p.stdout + p.stderr
    assert str(root) in combined or "PyRIT" in combined


def test_subprocess_setup_after_save_openai_compatible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Programmatic ``save_openai_compatible`` + CLI status using ``PYRIT_ENV_DIR``."""
    root = tmp_path / "pyrit_cfg"
    root.mkdir()
    monkeypatch.setenv("PYRIT_ENV_DIR", str(root))
    save_openai_compatible("https://api.groq.com/openai/v1", "gsk-test-key", "llama-test-model")
    monkeypatch.delenv("PYRIT_ENV_DIR", raising=False)
    p = _run_pyrit_cli("setup", "status", env={"PYRIT_ENV_DIR": str(root)})
    assert p.returncode == 0, p.stderr
    assert "PLATFORM" in p.stdout.upper() or "GROQ" in p.stdout.upper() or "OPENAI" in p.stdout.upper()


@pytest.mark.integration
def test_subprocess_datasets_inspect_hf_imdb() -> None:
    """Downloads / caches HF data on first run; use ``nox -s integration``."""
    p = _run_pyrit_cli(
        "datasets",
        "inspect",
        "hf:imdb",
        "--hf-split",
        "train",
        "--hf-column",
        "text",
        "--limit",
        "1",
        timeout=120.0,
    )
    assert p.returncode == 0, p.stderr
    assert "[1]" in p.stdout or "1." in p.stdout or "text" in p.stdout.lower()


def _ollama_model_names() -> list[str]:
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/tags",
            headers={"User-Agent": "pyrit-cli-nox-tests"},
        )
        with urllib.request.urlopen(req, timeout=2) as r:
            data = json.loads(r.read().decode())
        return [m.get("name", "") for m in data.get("models", [])]
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return []


def _has_qwen3_0_6b() -> bool:
    return any(
        n == "qwen3:0.6b" or n.endswith(":qwen3:0.6b") or "qwen3:0.6b" in n
        for n in _ollama_model_names()
    )


@pytest.mark.integration
@pytest.mark.skipif(not _has_qwen3_0_6b(), reason="Ollama not reachable or qwen3:0.6b not in ollama list")
def test_subprocess_prompt_sending_ollama_qwen3_0_6b() -> None:
    p = _run_pyrit_cli(
        "redteam",
        "prompt-sending-attack",
        "--target",
        "ollama:qwen3:0.6b",
        "--objective",
        "Reply with exactly the single word: OK",
        timeout=120.0,
    )
    assert p.returncode == 0, p.stderr
    out = p.stdout + p.stderr
    assert len(out) > 0
