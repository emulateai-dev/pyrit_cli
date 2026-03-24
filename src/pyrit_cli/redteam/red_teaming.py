"""RedTeamingAttack runner (multi-turn)."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from pyrit.executor.attack import (
    AttackAdversarialConfig,
    AttackConverterConfig,
    AttackScoringConfig,
    ConsoleAttackResultPrinter,
    RedTeamingAttack,
    RTASystemPromptPaths,
)
from pyrit.prompt_normalizer import PromptConverterConfiguration
from pyrit.setup import IN_MEMORY, initialize_pyrit_async

from pyrit_cli.redteam.attack_run_summary import print_attack_run_summary
from pyrit_cli.redteam.jailbreak_prepended import build_jailbreak_prepended_conversation
from pyrit_cli.redteam.multimodal_input import build_seed_group, target_supports_image_input, validate_image_paths
from pyrit_cli.redteam.http_target_cli import (
    build_http_json_escape_converter_config,
    build_http_objective_target,
    is_http_victim_spec,
    parse_objective_http_url,
)
from pyrit_cli.redteam.targets import openai_chat_from_spec, parse_target_spec
from pyrit_cli.registries.converters import make_converters
from pyrit_cli.registries.scorers import build_objective_scorer

_RTA_CHOICES: dict[str, Any] = {
    "text_generation": RTASystemPromptPaths.TEXT_GENERATION.value,
    "image_generation": RTASystemPromptPaths.IMAGE_GENERATION.value,
    "naive_crescendo": RTASystemPromptPaths.NAIVE_CRESCENDO.value,
    "violent_durian": RTASystemPromptPaths.VIOLENT_DURIAN.value,
    "crucible": RTASystemPromptPaths.CRUCIBLE.value,
}


def _default_openai_chain_spec_from_env() -> str | None:
    model = (
        os.environ.get("OPENAI_CHAT_MODEL", "")
        or os.environ.get("PLATFORM_OPENAI_CHAT_GPT4O_MODEL", "")
    ).strip()
    if not model or model.startswith("${"):
        return None
    return f"openai:{model}"


def _resolve_default_chat_chain_spec(
    *,
    objective_target_spec: str,
    explicit_chain_spec: str | None,
) -> str:
    if explicit_chain_spec:
        return explicit_chain_spec

    provider, _ = parse_target_spec(objective_target_spec)

    # Local/non-JSON victims often fail with self-ask scorers when scorer defaults to victim.
    # Prefer the configured OpenAI-compatible default chain when available.
    if provider in {"ollama", "lmstudio", "compat"}:
        fallback = _default_openai_chain_spec_from_env()
        if fallback:
            return fallback
    return objective_target_spec


def resolve_rta_prompt(name: str) -> Any:
    key = name.strip().lower().replace("-", "_")
    if key not in _RTA_CHOICES:
        raise ValueError(
            f"Invalid --rta-prompt {name!r}; use one of: {', '.join(sorted(_RTA_CHOICES))}"
        )
    return _RTA_CHOICES[key]


def attack_converter_config_from_keys(
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


def build_redteam_converter_config(
    *,
    http_json_body_converter: bool,
    request_converter_keys: list[str],
    response_converter_keys: list[str],
) -> AttackConverterConfig | None:
    if http_json_body_converter and request_converter_keys:
        raise ValueError(
            "Cannot combine --http-json-body-converter with --request-converter; use one or the other."
        )
    if http_json_body_converter:
        base = build_http_json_escape_converter_config()
        if not response_converter_keys:
            return base
        resp_list = PromptConverterConfiguration.from_converters(
            converters=make_converters(response_converter_keys)
        )
        return AttackConverterConfig(
            request_converters=base.request_converters,
            response_converters=resp_list,
        )
    return attack_converter_config_from_keys(request_converter_keys, response_converter_keys)


async def run_red_teaming_async(
    *,
    objective_target_spec: str,
    adversarial_target_spec: str | None,
    objective: str,
    max_turns: int,
    rta_prompt: str,
    memory_labels: dict[str, str] | None,
    scorer_preset: str,
    true_description: str | None,
    refusal_mode: str,
    scorer_chat_spec: str | None,
    request_converter_keys: list[str],
    response_converter_keys: list[str],
    include_adversarial_conversation: bool,
    http_request_path: str | None = None,
    http_response_parser: str | None = None,
    http_prompt_placeholder: str = "{PROMPT}",
    http_regex_base_url: str | None = None,
    http_timeout: float | None = None,
    http_use_tls: bool = True,
    http_json_body_converter: bool = False,
    http_model_name: str = "",
    jailbreak_template: str | None = None,
    jailbreak_template_params: list[str] | None = None,
    input_images: list[str] | None = None,
    input_text: str | None = None,
) -> None:
    await initialize_pyrit_async(memory_db_type=IN_MEMORY)  # type: ignore[arg-type]

    if is_http_victim_spec(objective_target_spec):
        if not http_request_path or not http_response_parser:
            raise ValueError(
                "When --objective-target is `http` or an http(s) URL, --http-request and "
                "--http-response-parser are required."
            )
        if not adversarial_target_spec or is_http_victim_spec(adversarial_target_spec):
            raise ValueError(
                "When the victim is HTTP (`http` or an http(s) URL), set --adversarial-target to a chat target "
                "(e.g. openai:gpt-4o-mini); HTTP is only supported for the victim."
            )
        objective_target = build_http_objective_target(
            request_path=Path(http_request_path),
            response_parser_spec=http_response_parser,
            prompt_placeholder=http_prompt_placeholder,
            regex_base_url=http_regex_base_url,
            use_tls=http_use_tls,
            timeout=http_timeout,
            model_name=http_model_name,
            objective_url=parse_objective_http_url(objective_target_spec),
        )
        adversarial_chat = openai_chat_from_spec(adversarial_target_spec)
        adv_spec = adversarial_target_spec
    else:
        objective_target = openai_chat_from_spec(objective_target_spec)
        adv_spec = _resolve_default_chat_chain_spec(
            objective_target_spec=objective_target_spec,
            explicit_chain_spec=adversarial_target_spec,
        )
        adversarial_chat = openai_chat_from_spec(adv_spec)

    scorer_spec = scorer_chat_spec or adv_spec
    scorer_chat = openai_chat_from_spec(scorer_spec)

    objective_scorer = build_objective_scorer(
        scorer_preset,
        scorer_chat=scorer_chat,
        true_description=true_description,
        refusal_mode=refusal_mode,
    )

    adversarial_config = AttackAdversarialConfig(
        target=adversarial_chat,
        system_prompt_path=resolve_rta_prompt(rta_prompt),
    )
    scoring_config = AttackScoringConfig(objective_scorer=objective_scorer)
    conv_cfg = build_redteam_converter_config(
        http_json_body_converter=http_json_body_converter and is_http_victim_spec(objective_target_spec),
        request_converter_keys=request_converter_keys,
        response_converter_keys=response_converter_keys,
    )

    attack = RedTeamingAttack(
        objective_target=objective_target,
        attack_adversarial_config=adversarial_config,
        attack_scoring_config=scoring_config,
        attack_converter_config=conv_cfg,
        max_turns=max_turns,
    )

    prepended = build_jailbreak_prepended_conversation(
        jailbreak_template=jailbreak_template,
        jailbreak_template_params=list(jailbreak_template_params or []),
    )

    kwargs: dict[str, Any] = {"objective": objective.strip()}
    if memory_labels:
        kwargs["memory_labels"] = memory_labels
    if prepended:
        kwargs["prepended_conversation"] = prepended
    images = validate_image_paths(list(input_images or []))
    has_multimodal = bool(images) or bool((input_text or "").strip())
    if has_multimodal:
        if not target_supports_image_input(objective_target):
            raise ValueError(
                "Objective target does not appear to support image input. Use a vision-capable target or remove --input-image."
            )
        seed_group = build_seed_group(input_text=input_text, input_images=images)
        kwargs["next_message"] = seed_group.next_message

    result = await attack.execute_async(**kwargs)  # type: ignore[misc]
    printer = ConsoleAttackResultPrinter()
    await printer.print_result_async(
        result,
        include_adversarial_conversation=include_adversarial_conversation,
    )

    print_attack_run_summary(
        [result],
        command="red-teaming-attack",
        scorer_preset=scorer_preset,
    )


def parse_memory_labels_json(raw: str | None) -> dict[str, str] | None:
    if not raw or not raw.strip():
        return None
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("--memory-labels-json must be a JSON object")
    out: dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(k, str):
            raise ValueError("memory_labels keys must be strings")
        out[k] = v if isinstance(v, str) else json.dumps(v)
    return out


def run_red_teaming(**kwargs: Any) -> None:
    asyncio.run(run_red_teaming_async(**kwargs))
