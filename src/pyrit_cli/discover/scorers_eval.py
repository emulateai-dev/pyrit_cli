"""Run PyRIT objective scorers on arbitrary text (debugging / lab use)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from pyrit.models import Score
from pyrit.setup import IN_MEMORY, initialize_pyrit_async

from pyrit_cli.redteam.targets import openai_chat_from_spec
from pyrit_cli.registries.scorers import build_objective_scorer


def _default_openai_scorer_spec_from_env() -> str | None:
    model = (
        os.environ.get("OPENAI_CHAT_MODEL", "")
        or os.environ.get("PLATFORM_OPENAI_CHAT_GPT4O_MODEL", "")
    ).strip()
    if not model or model.startswith("${"):
        return None
    return f"openai:{model}"


def resolve_scorer_chat_target_spec(explicit: str | None) -> str:
    """Return a ``<provider>:<model>`` spec for the self-ask scorer LLM."""
    if explicit and explicit.strip():
        return explicit.strip()
    fallback = _default_openai_scorer_spec_from_env()
    if fallback:
        return fallback
    raise ValueError(
        "scorers eval needs a JSON-capable chat model: pass --scorer-chat-target "
        "(e.g. openai:gpt-4o-mini or groq:llama-3.3-70b-versatile) or set OPENAI_CHAT_MODEL."
    )


def resolve_eval_text(*, text: str | None, text_file: Path | None) -> str:
    if text_file is not None and text is not None:
        raise ValueError("Use either --text or --text-file, not both.")
    if text_file is not None:
        p = text_file.expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"Text file not found: {p}")
        return p.read_text(encoding="utf-8")
    if text is None:
        raise ValueError("Provide --text or --text-file.")
    stripped = text
    if stripped == "-":
        return sys.stdin.read()
    return stripped


def format_scores_text(scores: list[Score]) -> str:
    lines: list[str] = []
    for i, s in enumerate(scores, 1):
        lines.append(f"Score {i}/{len(scores)}")
        lines.append("-" * 48)
        lines.append(f"  value:        {s.score_value}")
        lines.append(f"  type:         {s.score_type}")
        lines.append(f"  description:  {s.score_value_description}")
        cat = ", ".join(s.score_category) if s.score_category else "(none)"
        lines.append(f"  category:     {cat}")
        lines.append(f"  rationale:    {s.score_rationale}")
        if s.score_metadata:
            lines.append(f"  metadata:     {s.score_metadata}")
        if getattr(s, "objective", None):
            lines.append(f"  objective:    {s.objective}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_scores_json(scores: list[Score]) -> str:
    payload: list[dict[str, Any]] = [s.to_dict() for s in scores]
    return json.dumps(payload, indent=2) + "\n"


async def run_scorer_eval_async(
    *,
    preset: str,
    text: str | None,
    text_file: Path | None,
    objective: str | None,
    scorer_chat_target: str | None,
    true_description: str | None,
    refusal_mode: str,
    json_out: bool,
) -> str:
    body = resolve_eval_text(text=text, text_file=text_file)
    if not body.strip():
        raise ValueError("Eval text is empty after reading input.")

    await initialize_pyrit_async(memory_db_type=IN_MEMORY)  # type: ignore[arg-type]

    spec = resolve_scorer_chat_target_spec(scorer_chat_target)
    scorer_chat = openai_chat_from_spec(spec)

    scorer = build_objective_scorer(
        preset,
        scorer_chat=scorer_chat,
        true_description=true_description,
        refusal_mode=refusal_mode,
    )
    scores = await scorer.score_text_async(body, objective=objective)
    if not scores:
        raise RuntimeError("Scorer returned no scores.")

    if json_out:
        return format_scores_json(scores)
    return format_scores_text(scores)


def run_scorer_eval(
    *,
    preset: str,
    text: str | None,
    text_file: Path | None,
    objective: str | None,
    scorer_chat_target: str | None,
    true_description: str | None,
    refusal_mode: str,
    json_out: bool,
) -> None:
    out = asyncio.run(
        run_scorer_eval_async(
            preset=preset,
            text=text,
            text_file=text_file,
            objective=objective,
            scorer_chat_target=scorer_chat_target,
            true_description=true_description,
            refusal_mode=refusal_mode,
            json_out=json_out,
        )
    )
    sys.stdout.write(out)
