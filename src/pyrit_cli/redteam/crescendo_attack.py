"""CrescendoAttack runner (multi-turn with backtracking)."""

from __future__ import annotations

import asyncio
from typing import Any

from pyrit.executor.attack import (
    AttackAdversarialConfig,
    AttackConverterConfig,
    AttackScoringConfig,
    ConsoleAttackResultPrinter,
    CrescendoAttack,
)
from pyrit.models import AttackResult
from pyrit.prompt_normalizer import PromptConverterConfiguration
from pyrit.setup import IN_MEMORY, initialize_pyrit_async

from pyrit_cli.redteam.attack_run_summary import print_attack_run_summary
from pyrit_cli.redteam.converter_fallback import (
    attack_converter_config_for_stack,
    resolve_fallback_converter_stacks,
)
from pyrit_cli.redteam.targets import openai_chat_from_spec
from pyrit_cli.registries.converters import make_converters
from pyrit_cli.registries.scorers import build_objective_scorer


def _converter_config_from_keys(
    request_keys: list[str],
    response_keys: list[str],
) -> AttackConverterConfig | None:
    if not request_keys and not response_keys:
        return None
    req_list: list = []
    resp_list: list = []
    if request_keys:
        req_list = PromptConverterConfiguration.from_converters(converters=make_converters(request_keys))
    if response_keys:
        resp_list = PromptConverterConfiguration.from_converters(converters=make_converters(response_keys))
    return AttackConverterConfig(request_converters=req_list, response_converters=resp_list)


def _crescendo_success(result: AttackResult) -> bool:
    return str(result.outcome).endswith("SUCCESS")


async def run_crescendo_attack_async(
    *,
    objective_target_spec: str,
    objective: str,
    adversarial_target_spec: str | None,
    max_turns: int,
    max_backtracks: int,
    scorer_preset: str,
    true_description: str | None,
    refusal_mode: str,
    scorer_chat_spec: str | None,
    request_converter_keys: list[str],
    response_converter_keys: list[str],
    include_adversarial_conversation: bool,
    include_pruned_conversations: bool,
    memory_labels: dict[str, str] | None,
    converter_fallback_on_failure: bool = False,
    max_converter_stacks: int = 3,
    converter_fallback_stacks: list[list[str]] | None = None,
) -> None:
    await initialize_pyrit_async(memory_db_type=IN_MEMORY)  # type: ignore[arg-type]

    objective_target = openai_chat_from_spec(objective_target_spec)
    adv_spec = adversarial_target_spec or objective_target_spec
    adversarial_chat = openai_chat_from_spec(adv_spec)

    scorer_spec = scorer_chat_spec or adv_spec
    scorer_chat = openai_chat_from_spec(scorer_spec)
    objective_scorer = build_objective_scorer(
        scorer_preset,
        scorer_chat=scorer_chat,
        true_description=true_description,
        refusal_mode=refusal_mode,
    )
    scoring_config = AttackScoringConfig(objective_scorer=objective_scorer)
    adversarial_config = AttackAdversarialConfig(target=adversarial_chat)

    conv_cfg = _converter_config_from_keys(request_converter_keys, response_converter_keys)

    kwargs: dict[str, Any] = {"objective": objective.strip()}
    if memory_labels:
        kwargs["memory_labels"] = memory_labels

    attack = CrescendoAttack(
        objective_target=objective_target,
        attack_adversarial_config=adversarial_config,
        attack_scoring_config=scoring_config,
        attack_converter_config=conv_cfg,
        max_turns=max_turns,
        max_backtracks=max_backtracks,
    )
    result = await attack.execute_async(**kwargs)  # type: ignore[misc]

    if not _crescendo_success(result) and converter_fallback_on_failure:
        stacks = resolve_fallback_converter_stacks(
            enabled=True,
            max_stacks=max_converter_stacks,
            explicit_stacks=converter_fallback_stacks,
        )
        for stack in stacks:
            fb_cfg = attack_converter_config_for_stack(stack)
            retry = CrescendoAttack(
                objective_target=objective_target,
                attack_adversarial_config=adversarial_config,
                attack_scoring_config=scoring_config,
                attack_converter_config=fb_cfg,
                max_turns=max_turns,
                max_backtracks=max_backtracks,
            )
            result = await retry.execute_async(**kwargs)  # type: ignore[misc]
            if _crescendo_success(result):
                break

    printer = ConsoleAttackResultPrinter()
    await printer.print_result_async(
        result,
        include_adversarial_conversation=include_adversarial_conversation,
        include_pruned_conversations=include_pruned_conversations,
    )

    print_attack_run_summary(
        [result],
        command="crescendo-attack",
        scorer_preset=scorer_preset,
    )


def run_crescendo_attack(**kwargs: Any) -> None:
    asyncio.run(run_crescendo_attack_async(**kwargs))
