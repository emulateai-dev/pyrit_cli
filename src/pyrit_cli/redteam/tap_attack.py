"""Tree of Attacks with Pruning (TAP) — see PyRIT TAPAttack / TreeOfAttacksWithPruningAttack."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pyrit.executor.attack import AttackAdversarialConfig, ConsoleAttackResultPrinter, TAPAttack
from pyrit.executor.attack.multi_turn.tree_of_attacks import TAPAttackScoringConfig
from pyrit.score import FloatScaleThresholdScorer, SelfAskScaleScorer
from pyrit.setup import IN_MEMORY, initialize_pyrit_async

from pyrit_cli.redteam.attack_run_summary import print_attack_run_summary
from pyrit_cli.redteam.targets import openai_chat_from_spec


def _tap_scoring_config(
    *,
    scorer_chat_spec: str | None,
    adversarial_spec: str,
    score_threshold: float | None,
    score_criteria_file: Path | None,
) -> TAPAttackScoringConfig | None:
    """Return None to use PyRIT default (SelfAskScaleScorer + threshold 0.7 on adversarial chat)."""
    if scorer_chat_spec is None and score_threshold is None and score_criteria_file is None:
        return None
    adv_or_scorer_spec = scorer_chat_spec or adversarial_spec
    scorer_chat = openai_chat_from_spec(adv_or_scorer_spec)
    if score_threshold is not None and not (0 <= score_threshold <= 1):
        raise ValueError("--score-threshold must be between 0 and 1.")
    threshold = 0.7 if score_threshold is None else score_threshold
    scale_arguments_path: str | Path | None = score_criteria_file
    wrapped = FloatScaleThresholdScorer(
        scorer=SelfAskScaleScorer(
            chat_target=scorer_chat,
            scale_arguments_path=scale_arguments_path,
        ),
        threshold=threshold,
    )
    return TAPAttackScoringConfig(objective_scorer=wrapped)


async def run_tap_attack_async(
    *,
    objective_target_spec: str,
    objective: str,
    adversarial_target_spec: str | None,
    adversarial_temperature: float | None,
    tree_width: int,
    tree_depth: int,
    branching_factor: int,
    on_topic_checking_enabled: bool,
    desired_response_prefix: str,
    batch_size: int,
    memory_labels: dict[str, str] | None,
    scorer_chat_spec: str | None,
    score_threshold: float | None,
    score_criteria_file: Path | None,
    include_adversarial_conversation: bool,
    include_pruned_conversations: bool,
) -> None:
    await initialize_pyrit_async(memory_db_type=IN_MEMORY)  # type: ignore[arg-type]

    objective_target = openai_chat_from_spec(objective_target_spec)
    adv_spec = adversarial_target_spec or objective_target_spec
    if adversarial_temperature is not None:
        adversarial_chat = openai_chat_from_spec(adv_spec, temperature=adversarial_temperature)
    else:
        adversarial_chat = openai_chat_from_spec(adv_spec)

    scoring = _tap_scoring_config(
        scorer_chat_spec=scorer_chat_spec,
        adversarial_spec=adv_spec,
        score_threshold=score_threshold,
        score_criteria_file=score_criteria_file,
    )

    adversarial_config = AttackAdversarialConfig(target=adversarial_chat)

    attack = TAPAttack(
        objective_target=objective_target,
        attack_adversarial_config=adversarial_config,
        attack_scoring_config=scoring,
        tree_width=tree_width,
        tree_depth=tree_depth,
        branching_factor=branching_factor,
        on_topic_checking_enabled=on_topic_checking_enabled,
        desired_response_prefix=desired_response_prefix,
        batch_size=batch_size,
    )

    kwargs: dict[str, Any] = {"objective": objective.strip()}
    if memory_labels:
        kwargs["memory_labels"] = memory_labels

    result = await attack.execute_async(**kwargs)  # type: ignore[misc]
    printer = ConsoleAttackResultPrinter()
    await printer.print_result_async(
        result,
        include_adversarial_conversation=include_adversarial_conversation,
        include_pruned_conversations=include_pruned_conversations,
    )

    print_attack_run_summary(
        [result],
        command="tap-attack",
        tap_score_threshold=0.7 if score_threshold is None else score_threshold,
    )


def run_tap_attack(**kwargs: Any) -> None:
    asyncio.run(run_tap_attack_async(**kwargs))
