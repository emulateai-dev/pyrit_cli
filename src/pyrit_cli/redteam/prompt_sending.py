"""PromptSendingAttack runner (see PyRIT docs)."""

from __future__ import annotations

import asyncio
import os
import warnings
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pyrit.common.path import DATASETS_PATH
from pyrit.datasets import TextJailBreak

from pyrit.executor.attack import (
    AttackConverterConfig,
    AttackExecutor,
    AttackScoringConfig,
    ConsoleAttackResultPrinter,
    PromptSendingAttack,
)
from pyrit.models import Message, SeedDataset
from pyrit.score import SelfAskRefusalScorer, SelfAskTrueFalseScorer, TrueFalseInverterScorer, TrueFalseQuestion
from pyrit.setup import IN_MEMORY, initialize_pyrit_async

from pyrit_cli.redteam.http_target_cli import (
    build_http_json_escape_converter_config,
    build_http_objective_target,
    is_http_victim_spec,
    parse_objective_http_url,
)
from pyrit_cli.redteam.targets import openai_chat_from_spec, parse_target_spec


def resolve_pyrit_dataset_path(spec: str) -> Path:
    """spec is path after 'pyrit:' prefix."""
    raw = spec[6:].strip() if spec.lower().startswith("pyrit:") else spec.strip()
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p
    return (Path(DATASETS_PATH) / raw).resolve()


def load_objectives_from_pyrit_dataset(spec: str) -> Sequence[str]:
    path = resolve_pyrit_dataset_path(spec)
    if not path.is_file():
        raise FileNotFoundError(f"PyRIT dataset file not found: {path}")
    ds = SeedDataset.from_yaml_file(path)
    return list(ds.get_values())


def load_objectives_from_hf(
    repo_id: str,
    *,
    split: str,
    column: str,
    config: str | None,
) -> list[str]:
    try:
        from datasets import load_dataset
    except ImportError as e:
        raise ImportError(
            "Hugging Face datasets dependency is missing. Reinstall/upgrade pyrit-cli in this environment."
        ) from e

    kwargs: dict = {}
    if config:
        kwargs["name"] = config
    with warnings.catch_warnings():
        # Keep CLI output focused; users can still opt in to HF auth for better rate limits.
        warnings.filterwarnings(
            "ignore",
            message="Warning: You are sending unauthenticated requests to the HF Hub.*",
        )
        ds = load_dataset(repo_id, split=split, **kwargs)
    col = ds[column]
    return [str(x) for x in col if x is not None and str(x).strip()]


def collect_objectives(
    objective: str | None,
    dataset: str | None,
    *,
    hf_split: str,
    hf_column: str,
    hf_config: str | None,
    limit: int | None,
) -> list[str]:
    if dataset and objective:
        raise ValueError("Use either --objective or --dataset, not both.")
    if not dataset and not objective:
        raise ValueError("Provide --objective or --dataset.")

    if objective:
        obs = [objective.strip()]
    elif dataset.lower().startswith("pyrit:"):
        obs = list(load_objectives_from_pyrit_dataset(dataset))
    elif dataset.lower().startswith("hf:"):
        repo_id = dataset.split(":", 1)[1].strip()
        if not repo_id:
            raise ValueError("Invalid --dataset hf:; need hf:<org/dataset>")
        obs = load_objectives_from_hf(
            repo_id, split=hf_split, column=hf_column, config=hf_config
        )
    else:
        raise ValueError(
            "Invalid --dataset; use pyrit:<path_under_pyrit_datasets> or hf:<hub_dataset_id>"
        )

    if limit is not None:
        obs = obs[:limit]
    if not obs:
        raise ValueError("No objectives after loading dataset / applying --limit.")
    return obs


def _parse_kv_pairs(raw_pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in raw_pairs:
        if "=" not in raw:
            raise ValueError(f"Invalid --jailbreak-template-param {raw!r}; expected key=value")
        key, value = raw.split("=", 1)
        k = key.strip()
        if not k:
            raise ValueError(f"Invalid --jailbreak-template-param {raw!r}; key cannot be empty")
        out[k] = value
    return out


def _build_scoring_config(
    *,
    mode: str,
    preset: str,
    true_description: str | None,
    scorer_chat_target_spec: str | None,
    attack_target_spec: str,
):
    m = mode.strip().lower()
    if m not in {"auto", "off", "configured"}:
        raise ValueError("--scoring-mode must be one of: auto, off, configured")
    if m == "off":
        return None

    if scorer_chat_target_spec:
        scorer_spec = scorer_chat_target_spec
    else:
        if is_http_victim_spec(attack_target_spec):
            raise ValueError(
                "When scoring is enabled for HTTP victim targets, set --scorer-chat-target "
                "to a chat model spec (e.g. openai:gpt-4o-mini)."
            )
        provider, _ = parse_target_spec(attack_target_spec)
        scorer_spec = attack_target_spec
        # Match red-teaming behavior: for local/non-JSON victims, prefer OPENAI_CHAT_MODEL fallback.
        if provider in {"ollama", "lmstudio", "compat"}:
            model = (
                os.environ.get("OPENAI_CHAT_MODEL", "")
                or os.environ.get("PLATFORM_OPENAI_CHAT_GPT4O_MODEL", "")
            ).strip()
            if model and not model.startswith("${"):
                scorer_spec = f"openai:{model}"

    scorer_chat = openai_chat_from_spec(scorer_spec)

    p = preset.strip().lower().replace("_", "-")
    if m == "auto":
        p = "non-refusal"

    if p == "non-refusal":
        objective_scorer = TrueFalseInverterScorer(scorer=SelfAskRefusalScorer(chat_target=scorer_chat))
    elif p == "refusal":
        objective_scorer = SelfAskRefusalScorer(chat_target=scorer_chat)
    elif p == "self-ask-tf":
        if not (true_description and true_description.strip()):
            raise ValueError("--true-description is required when --scorer-preset is self-ask-tf")
        objective_scorer = SelfAskTrueFalseScorer(
            chat_target=scorer_chat,
            true_false_question=TrueFalseQuestion(true_description=true_description.strip()),
        )
    else:
        raise ValueError("--scorer-preset must be one of: non-refusal, refusal, self-ask-tf")

    return AttackScoringConfig(objective_scorer=objective_scorer)


def _build_prepended_conversation(
    *,
    jailbreak_template: str | None,
    jailbreak_template_params: list[str],
) -> list[Message] | None:
    if not jailbreak_template:
        if jailbreak_template_params:
            raise ValueError("--jailbreak-template-param requires --jailbreak-template")
        return None
    kwargs = _parse_kv_pairs(jailbreak_template_params)
    jailbreak = TextJailBreak(template_file_name=jailbreak_template)
    system_prompt = jailbreak.get_jailbreak_system_prompt(**kwargs)
    return [Message.from_system_prompt(system_prompt)]


async def run_prompt_sending_async(
    target: str,
    objectives: Sequence[str],
    *,
    http_request_path: str | None = None,
    http_response_parser: str | None = None,
    http_prompt_placeholder: str = "{PROMPT}",
    http_regex_base_url: str | None = None,
    http_timeout: float | None = None,
    http_use_tls: bool = True,
    http_json_body_converter: bool = False,
    http_model_name: str = "",
    scoring_mode: str = "auto",
    scorer_preset: str = "non-refusal",
    true_description: str | None = None,
    scorer_chat_target: str | None = None,
    jailbreak_template: str | None = None,
    jailbreak_template_params: list[str] | None = None,
) -> None:
    await initialize_pyrit_async(memory_db_type=IN_MEMORY)  # type: ignore[arg-type]

    conv_cfg: AttackConverterConfig | None = None
    if is_http_victim_spec(target):
        if not http_request_path or not http_response_parser:
            raise ValueError(
                "When --target is `http` or an http(s) URL, --http-request and --http-response-parser are required."
            )
        chat_target = build_http_objective_target(
            request_path=Path(http_request_path),
            response_parser_spec=http_response_parser,
            prompt_placeholder=http_prompt_placeholder,
            regex_base_url=http_regex_base_url,
            use_tls=http_use_tls,
            timeout=http_timeout,
            model_name=http_model_name,
            objective_url=parse_objective_http_url(target),
        )
        if http_json_body_converter:
            conv_cfg = build_http_json_escape_converter_config()
    else:
        chat_target = openai_chat_from_spec(target)

    scoring_cfg = _build_scoring_config(
        mode=scoring_mode,
        preset=scorer_preset,
        true_description=true_description,
        scorer_chat_target_spec=scorer_chat_target,
        attack_target_spec=target,
    )
    prepended_conversation = _build_prepended_conversation(
        jailbreak_template=jailbreak_template,
        jailbreak_template_params=list(jailbreak_template_params or []),
    )
    attack = PromptSendingAttack(
        objective_target=chat_target,
        attack_converter_config=conv_cfg,
        attack_scoring_config=scoring_cfg,
    )
    executor = AttackExecutor()
    printer = ConsoleAttackResultPrinter()

    results = await executor.execute_attack_async(
        attack=attack,
        objectives=list(objectives),
        prepended_conversation=prepended_conversation,
    )
    for result in results:
        await printer.print_result_async(result)


def run_prompt_sending(
    target: str,
    objectives: Sequence[str],
    **kwargs: Any,
) -> None:
    asyncio.run(run_prompt_sending_async(target, objectives, **kwargs))
