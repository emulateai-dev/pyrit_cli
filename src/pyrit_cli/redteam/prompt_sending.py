"""PromptSendingAttack runner (see PyRIT docs)."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pyrit.common.path import DATASETS_PATH

from pyrit.executor.attack import AttackConverterConfig, ConsoleAttackResultPrinter, PromptSendingAttack
from pyrit.models import SeedDataset
from pyrit.setup import IN_MEMORY, initialize_pyrit_async

from pyrit_cli.redteam.http_target_cli import (
    build_http_json_escape_converter_config,
    build_http_objective_target,
    is_http_victim_spec,
    parse_objective_http_url,
)
from pyrit_cli.redteam.targets import openai_chat_from_spec


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

    attack = PromptSendingAttack(objective_target=chat_target, attack_converter_config=conv_cfg)
    printer = ConsoleAttackResultPrinter()

    for obj in objectives:
        result = await attack.execute_async(objective=obj)  # type: ignore[misc]
        await printer.print_result_async(result)


def run_prompt_sending(
    target: str,
    objectives: Sequence[str],
    **kwargs: Any,
) -> None:
    asyncio.run(run_prompt_sending_async(target, objectives, **kwargs))
