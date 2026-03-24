"""Preview a PyRIT jailbreak YAML template (similar to datasets inspect)."""

from __future__ import annotations

import json
from pathlib import Path

from pyrit.common.path import JAILBREAK_TEMPLATES_PATH
from pyrit.datasets import TextJailBreak
from pyrit.models import SeedPrompt

from pyrit_cli.discover.jailbreak_templates_list import _iter_yaml_files


def _truncate(text: str, max_len: int = 4096) -> str:
    one_line = text.replace("\r", "").replace("\n", " ")
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 3] + "..."


def parse_template_params(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in pairs:
        if "=" not in raw:
            raise ValueError(f"Invalid --param {raw!r}; expected key=value")
        key, value = raw.split("=", 1)
        k = key.strip()
        if not k:
            raise ValueError(f"Invalid --param {raw!r}; key cannot be empty")
        out[k] = value
    return out


def resolve_jailbreak_yaml_path(
    spec: str,
    *,
    include_multi_parameter: bool,
    relative_path: str | None,
) -> Path:
    """Return absolute path to a single .yaml jailbreak template."""
    root = JAILBREAK_TEMPLATES_PATH
    if relative_path:
        p = (root / relative_path.strip()).resolve()
        try:
            p.relative_to(root.resolve())
        except ValueError as e:
            raise ValueError(f"--relative-path must be under jailbreak templates root: {root}") from e
        if not p.is_file():
            raise FileNotFoundError(f"Template file not found: {p}")
        if p.suffix.lower() not in {".yaml", ".yml"}:
            raise ValueError(f"Not a YAML template: {p}")
        return p

    raw = spec.strip()
    p_abs = Path(raw).expanduser()
    if p_abs.is_file():
        return p_abs.resolve()

    under_root = (root / raw).resolve()
    if under_root.is_file():
        try:
            under_root.relative_to(root.resolve())
        except ValueError:
            pass
        else:
            return under_root

    name = raw if raw.lower().endswith((".yaml", ".yml")) else f"{raw}.yaml"
    files = _iter_yaml_files(root, include_multi_parameter=include_multi_parameter)
    matches = sorted([f for f in files if f.name == name], key=lambda x: str(x))
    if not matches:
        raise FileNotFoundError(
            f"No jailbreak template {name!r} under {root}. "
            f"Try: pyrit-cli jailbreak-templates list"
        )
    if len(matches) > 1:
        lines = "\n".join(f"  {m.name}\t{m.relative_to(root).as_posix()}" for m in matches)
        raise ValueError(
            f"Multiple templates named {name!r}. Disambiguate with --relative-path:\n{lines}"
        )
    return matches[0].resolve()


def run_jailbreak_template_inspect(
    spec: str,
    *,
    include_multi_parameter: bool = False,
    relative_path: str | None = None,
    param_pairs: list[str] | None = None,
    preview_chars: int = 4096,
    json_out: bool = False,
) -> str:
    path = resolve_jailbreak_yaml_path(
        spec,
        include_multi_parameter=include_multi_parameter,
        relative_path=relative_path,
    )
    root = JAILBREAK_TEMPLATES_PATH.resolve()
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = str(path)

    seed = SeedPrompt.from_yaml_file(str(path))
    params = list(seed.parameters) if seed.parameters else []
    required_excluding_prompt = [p for p in params if p != "prompt"]

    kwargs = parse_template_params(list(param_pairs or []))
    in_multi = "multi_parameter" in path.parts

    try:
        jb = TextJailBreak(template_path=str(path), **kwargs)
        system_prompt = jb.get_jailbreak_system_prompt()
    except ValueError as e:
        raise ValueError(
            f"Could not render template (missing --param for required placeholders?): {e}"
        ) from e

    preview = _truncate(system_prompt, max_len=max(80, min(preview_chars, 8000)))

    if json_out:
        payload = {
            "name": path.name,
            "relative_path": rel,
            "absolute_path": str(path),
            "parameters": params,
            "required_excluding_prompt": required_excluding_prompt,
            "under_multi_parameter": in_multi,
            "system_prompt_preview": preview,
            "system_prompt_length": len(system_prompt),
        }
        return json.dumps(payload, indent=2)

    truncated = len(system_prompt) > preview_chars or "\n" in system_prompt
    lines = [
        f"Template: {path.name}",
        f"Relative to JAILBREAK_TEMPLATES_PATH: {rel}",
        f"Parameters: {params if params else '(none)'}",
        f"Required (excluding prompt): {required_excluding_prompt if required_excluding_prompt else '(none)'}",
        f"multi_parameter subtree: {in_multi}",
        "-" * 60,
        "Rendered system prompt (truncated):" if truncated else "Rendered system prompt:",
        preview,
    ]
    if truncated:
        lines.append(f"(full length: {len(system_prompt)} chars)")
    return "\n".join(lines)
