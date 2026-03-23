"""Objective scorer presets for RedTeamingAttack (must be TrueFalseScorer subclasses)."""

from __future__ import annotations

import inspect

from pyrit.prompt_target import OpenAIChatTarget
from pyrit.score import SelfAskTrueFalseScorer, TrueFalseQuestion
from pyrit.score.true_false.self_ask_refusal_scorer import SelfAskRefusalScorer
from pyrit.score.true_false.true_false_scorer import TrueFalseScorer

SCORER_PRESETS_DOC = [
    ("self-ask-tf", "SelfAskTrueFalseScorer — pass --true-description (criterion for True)."),
    (
        "self-ask-refusal",
        "SelfAskRefusalScorer — True if model refused. On PyRIT 0.11.x, --refusal-mode is ignored; "
        "0.12+ supports default|strict prompts.",
    ),
]


def _self_ask_refusal_scorer(chat_target: OpenAIChatTarget, refusal_mode: str) -> SelfAskRefusalScorer:
    sig = inspect.signature(SelfAskRefusalScorer.__init__)
    if "refusal_system_prompt_path" not in sig.parameters:
        return SelfAskRefusalScorer(chat_target=chat_target)
    from pyrit.score.true_false.self_ask_refusal_scorer import RefusalScorerPaths

    path = RefusalScorerPaths.STRICT if refusal_mode.lower() == "strict" else RefusalScorerPaths.DEFAULT
    return SelfAskRefusalScorer(chat_target=chat_target, refusal_system_prompt_path=path)


def build_objective_scorer(
    preset: str,
    *,
    scorer_chat: OpenAIChatTarget,
    true_description: str | None,
    refusal_mode: str,
) -> TrueFalseScorer:
    p = preset.lower().replace("_", "-")
    if p == "self-ask-tf":
        if not (true_description and true_description.strip()):
            raise ValueError("--true-description is required for scorer-preset self-ask-tf")
        return SelfAskTrueFalseScorer(
            chat_target=scorer_chat,
            true_false_question=TrueFalseQuestion(true_description=true_description.strip()),
        )
    if p == "self-ask-refusal":
        return _self_ask_refusal_scorer(scorer_chat, refusal_mode)
    raise ValueError(
        f"Unknown scorer-preset {preset!r}. Use: pyrit-cli scorers list (presets: self-ask-tf, self-ask-refusal)"
    )
