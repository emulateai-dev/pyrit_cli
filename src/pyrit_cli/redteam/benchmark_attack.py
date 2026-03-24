"""Automated benchmark pipeline: baseline -> templates -> TAP fallback."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyrit.common.path import JAILBREAK_TEMPLATES_PATH
from pyrit.executor.attack import AttackAdversarialConfig, AttackScoringConfig, PromptSendingAttack, TAPAttack
from pyrit.executor.attack.multi_turn.tree_of_attacks import TAPAttackScoringConfig
from pyrit.models import AttackOutcome, AttackResult, Message
from pyrit.score import FloatScaleThresholdScorer, SelfAskRefusalScorer, SelfAskScaleScorer, TrueFalseInverterScorer
from pyrit.setup import IN_MEMORY, initialize_pyrit_async
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from pyrit_cli.redteam.benchmark_report import build_meta, write_benchmark_artifacts
from pyrit_cli.redteam.jailbreak_prepended import build_jailbreak_prepended_conversation
from pyrit_cli.redteam.prompt_sending import collect_objectives
from pyrit_cli.redteam.targets import openai_chat_from_spec


@dataclass
class PromptRunRecord:
    index: int
    objective: str
    baseline_outcome: str = "UNDETERMINED"
    success: bool = False
    final_stage: str = "baseline"
    template_winner: str | None = None
    template_outcomes: dict[str, str] = field(default_factory=dict)
    tap_outcome: str | None = None
    final_response: str | None = None
    transformed_prompt: str | None = None
    baseline_reason: str | None = None
    baseline_score_summary: str | None = None
    last_template_reason: str | None = None
    last_template_score_summary: str | None = None
    tap_reason: str | None = None
    tap_score_summary: str | None = None


def _is_success(outcome: AttackOutcome | str) -> bool:
    raw = str(outcome)
    return raw.endswith("SUCCESS")


def _normalize_outcome(outcome: AttackOutcome | str) -> str:
    raw = str(outcome)
    if "." in raw:
        raw = raw.split(".")[-1]
    return raw


def _extract_response_text(result: AttackResult) -> str | None:
    piece = result.last_response
    if piece is None:
        return None
    converted = getattr(piece, "converted_value", None)
    original = getattr(piece, "original_value", None)
    if converted and str(converted).strip():
        return str(converted)
    if original and str(original).strip():
        return str(original)
    return None


def _extract_outcome_reason(result: AttackResult) -> str | None:
    raw = getattr(result, "outcome_reason", None)
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def _extract_score_summary(result: AttackResult) -> str | None:
    score = result.last_score
    if score is None:
        return None
    try:
        d = score.to_dict()
        text = json.dumps(d, default=str)
    except Exception:
        text = str(score)
    text = text.strip()
    if len(text) > 800:
        return text[:797] + "..."
    return text or None


def _tap_objective_note(objective: str) -> str:
    o = objective.strip()
    return (
        f"{o}\n\n"
        "(TAP uses multi-turn adversarial search; the line above is the benchmark objective. "
        "The target may have received additional turns not reproduced in this field.)"
    )


def _build_transformed_prompt(*, prepended_conversation: list[Message] | None, objective: str) -> str | None:
    if not prepended_conversation:
        return None
    chunks: list[str] = []
    for msg in prepended_conversation:
        try:
            values = msg.get_all_values()
        except Exception:
            values = []
        for val in values:
            text = str(val).strip()
            if text:
                chunks.append(text)
    if not chunks:
        return None
    chunks.append(objective.strip())
    return "\n\n".join(chunks)


def _iter_templates(*, include_glob: str | None, exclude_glob: str | None, max_templates: int) -> list[Path]:
    paths = sorted(JAILBREAK_TEMPLATES_PATH.rglob("*.yaml"))
    filtered: list[Path] = []
    for p in paths:
        rel = p.relative_to(JAILBREAK_TEMPLATES_PATH).as_posix()
        if "multi_parameter" in p.parts:
            continue
        if include_glob and not Path(rel).match(include_glob):
            continue
        if exclude_glob and Path(rel).match(exclude_glob):
            continue
        filtered.append(p)
        if len(filtered) >= max_templates:
            break
    return filtered


def select_tap_candidates(records: list[PromptRunRecord], top_k: int) -> list[PromptRunRecord]:
    unresolved = [r for r in records if not r.success]
    return unresolved[:top_k]


def resolve_benchmark_evaluator_spec(
    *,
    objective_target_spec: str,
    scorer_chat_target: str | None,
    adversarial_target: str | None,
) -> str:
    """Scorer/evaluator chat target: explicit scorer, else adversarial (if set), else victim."""
    if scorer_chat_target and scorer_chat_target.strip():
        return scorer_chat_target.strip()
    if adversarial_target and adversarial_target.strip():
        return adversarial_target.strip()
    return objective_target_spec


def _asr_display(records: list[PromptRunRecord]) -> str:
    n = len(records)
    if n == 0:
        return "ASR — (0/0)"
    s = sum(1 for r in records if r.success)
    pct = 100.0 * s / n
    return f"ASR {pct:.1f}% ({s}/{n})"


def resolve_outcome_reason_text(rec: PromptRunRecord) -> str:
    if rec.success:
        if rec.final_stage == "baseline":
            return (rec.baseline_reason or "").strip() or (
                "Objective scorer marked success at baseline (inverted refusal / non-refusal signal)."
            )
        if rec.final_stage == "template":
            return (rec.last_template_reason or "").strip() or (
                "Objective scorer marked success after a jailbreak-template retry."
            )
        return (rec.tap_reason or "").strip() or "TAP threshold scorer marked success."
    if rec.tap_outcome is not None:
        return (rec.tap_reason or "").strip() or (
            f"TAP completed with outcome {rec.tap_outcome}; objective not satisfied."
        )
    if rec.template_outcomes:
        last_out = list(rec.template_outcomes.values())[-1]
        return (rec.last_template_reason or "").strip() or (
            f"Template retries did not satisfy the objective; last attempt outcome: {last_out}."
        )
    return (rec.baseline_reason or "").strip() or (
        f"Baseline outcome {rec.baseline_outcome}; objective not satisfied."
    )


def resolve_score_summary_for_record(rec: PromptRunRecord) -> str | None:
    if rec.success:
        if rec.final_stage == "baseline":
            return rec.baseline_score_summary
        if rec.final_stage == "template":
            return rec.last_template_score_summary
        return rec.tap_score_summary
    if rec.tap_outcome is not None:
        return rec.tap_score_summary
    if rec.template_outcomes:
        return rec.last_template_score_summary
    return rec.baseline_score_summary


def resolve_final_prompt_for_record(rec: PromptRunRecord) -> str:
    if rec.final_stage == "tap":
        return _tap_objective_note(rec.objective)
    if rec.transformed_prompt and rec.template_winner:
        return rec.transformed_prompt
    return rec.objective.strip()


def aggregate_payload(
    *,
    records: list[PromptRunRecord],
    template_stats: dict[str, dict[str, int]],
    meta: dict[str, Any],
) -> dict[str, Any]:
    total = len(records)
    baseline_success = sum(1 for r in records if _is_success(r.baseline_outcome))
    template_success = sum(1 for r in records if r.success and r.final_stage in {"baseline", "template"})
    tap_success = sum(1 for r in records if r.success)
    final_failure = total - tap_success

    template_rows = []
    for template, counts in sorted(template_stats.items(), key=lambda kv: (-kv[1].get("rescued", 0), kv[0])):
        template_rows.append(
            {
                "template": template,
                "attempted": counts.get("attempted", 0),
                "rescued": counts.get("rescued", 0),
            }
        )

    prompts = []
    for r in records:
        jailbreak_attempted = bool(r.template_outcomes)
        tap_applied = r.tap_outcome is not None
        prompts.append(
            {
                "index": r.index,
                "objective": r.objective,
                "baseline_outcome": r.baseline_outcome,
                "template_winner": r.template_winner,
                "tap_outcome": r.tap_outcome,
                "final_stage": r.final_stage,
                "success": r.success,
                "final_response": r.final_response,
                "transformed_prompt": r.transformed_prompt,
                "final_prompt": resolve_final_prompt_for_record(r),
                "jailbreak_attempted": jailbreak_attempted,
                "tap_applied": tap_applied,
                "outcome_reason": resolve_outcome_reason_text(r),
                "score_summary": resolve_score_summary_for_record(r),
            }
        )

    return {
        "meta": meta,
        "metrics": {
            "total_prompts": total,
            "final_success": tap_success,
            "final_failure": final_failure,
            "stage": {
                "baseline_success": baseline_success,
                "template_success": template_success,
                "tap_success": tap_success,
            },
        },
        "templates": template_rows,
        "prompts": prompts,
    }


async def _run_prompt_attack(
    *,
    objective_target_spec: str,
    evaluator_spec: str,
    objective: str,
    prepended_conversation: list[Message] | None,
) -> AttackResult:
    objective_target = openai_chat_from_spec(objective_target_spec)
    scorer_target = openai_chat_from_spec(evaluator_spec)
    scoring_cfg = AttackScoringConfig(
        objective_scorer=TrueFalseInverterScorer(scorer=SelfAskRefusalScorer(chat_target=scorer_target))
    )
    attack = PromptSendingAttack(objective_target=objective_target, attack_scoring_config=scoring_cfg)
    return await attack.execute_async(objective=objective, prepended_conversation=prepended_conversation)  # type: ignore[misc]


async def _run_tap_single(
    *,
    objective_target_spec: str,
    adversarial_target_spec: str | None,
    evaluator_spec: str,
    objective: str,
    tree_width: int,
    tree_depth: int,
    branching_factor: int,
    score_threshold: float,
) -> AttackResult:
    objective_target = openai_chat_from_spec(objective_target_spec)
    adv_spec = adversarial_target_spec or objective_target_spec
    adversarial_chat = openai_chat_from_spec(adv_spec)
    scorer_target = openai_chat_from_spec(evaluator_spec)
    scoring = TAPAttackScoringConfig(
        objective_scorer=FloatScaleThresholdScorer(
            scorer=SelfAskScaleScorer(chat_target=scorer_target),
            threshold=score_threshold,
        )
    )
    attack = TAPAttack(
        objective_target=objective_target,
        attack_adversarial_config=AttackAdversarialConfig(target=adversarial_chat),
        attack_scoring_config=scoring,
        tree_width=tree_width,
        tree_depth=tree_depth,
        branching_factor=branching_factor,
    )
    return await attack.execute_async(objective=objective.strip())  # type: ignore[misc]


async def run_benchmark_attack_async(
    *,
    objective_target_spec: str,
    dataset: str,
    hf_split: str,
    hf_column: str,
    hf_config: str | None,
    limit: int | None,
    scorer_chat_target: str | None,
    adversarial_target: str | None,
    template_include_glob: str | None,
    template_exclude_glob: str | None,
    max_templates: int,
    tap_top_k: int,
    tap_tree_width: int,
    tap_tree_depth: int,
    tap_branching_factor: int,
    tap_score_threshold: float,
    output_dir: Path,
    show_progress: bool = False,
    report_title: str | None = None,
    report_organization: str | None = None,
) -> tuple[Path, Path]:
    await initialize_pyrit_async(memory_db_type=IN_MEMORY)  # type: ignore[arg-type]
    objectives = collect_objectives(
        objective=None,
        dataset=dataset,
        hf_split=hf_split,
        hf_column=hf_column,
        hf_config=hf_config,
        limit=limit,
    )
    templates = _iter_templates(
        include_glob=template_include_glob,
        exclude_glob=template_exclude_glob,
        max_templates=max_templates,
    )

    records = [PromptRunRecord(index=i + 1, objective=obj) for i, obj in enumerate(objectives)]
    template_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"attempted": 0, "rescued": 0})
    evaluator_spec = resolve_benchmark_evaluator_spec(
        objective_target_spec=objective_target_spec,
        scorer_chat_target=scorer_chat_target,
        adversarial_target=adversarial_target,
    )

    progress: Progress | None = None
    if show_progress:
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
        )

    if progress is None:
        # Stage 1: baseline
        for rec in records:
            result = await _run_prompt_attack(
                objective_target_spec=objective_target_spec,
                evaluator_spec=evaluator_spec,
                objective=rec.objective,
                prepended_conversation=None,
            )
            rec.baseline_outcome = _normalize_outcome(result.outcome)
            rec.final_response = _extract_response_text(result)
            rec.transformed_prompt = None
            rec.baseline_reason = _extract_outcome_reason(result)
            rec.baseline_score_summary = _extract_score_summary(result)
            if _is_success(result.outcome):
                rec.success = True
                rec.final_stage = "baseline"

        # Stage 2: template retries
        for template in templates:
            template_name = template.relative_to(JAILBREAK_TEMPLATES_PATH).as_posix()
            prepended = build_jailbreak_prepended_conversation(
                jailbreak_template=str(template),
                jailbreak_template_params=[],
            )
            for rec in records:
                if rec.success:
                    continue
                template_stats[template_name]["attempted"] += 1
                result = await _run_prompt_attack(
                    objective_target_spec=objective_target_spec,
                    evaluator_spec=evaluator_spec,
                    objective=rec.objective,
                    prepended_conversation=prepended,
                )
                out = _normalize_outcome(result.outcome)
                rec.template_outcomes[template_name] = out
                rec.final_response = _extract_response_text(result)
                rec.transformed_prompt = _build_transformed_prompt(
                    prepended_conversation=prepended,
                    objective=rec.objective,
                )
                rec.last_template_reason = _extract_outcome_reason(result)
                rec.last_template_score_summary = _extract_score_summary(result)
                if _is_success(result.outcome):
                    rec.success = True
                    rec.template_winner = template_name
                    rec.final_stage = "template"
                    template_stats[template_name]["rescued"] += 1

        # Stage 3: TAP fallback on top-k unresolved
        tap_candidates = select_tap_candidates(records, tap_top_k)
        for rec in tap_candidates:
            rec.transformed_prompt = _tap_objective_note(rec.objective)
            result = await _run_tap_single(
                objective_target_spec=objective_target_spec,
                adversarial_target_spec=adversarial_target,
                evaluator_spec=evaluator_spec,
                objective=rec.objective,
                tree_width=tap_tree_width,
                tree_depth=tap_tree_depth,
                branching_factor=tap_branching_factor,
                score_threshold=tap_score_threshold,
            )
            rec.tap_outcome = _normalize_outcome(result.outcome)
            rec.final_response = _extract_response_text(result)
            rec.tap_reason = _extract_outcome_reason(result)
            rec.tap_score_summary = _extract_score_summary(result)
            if _is_success(result.outcome):
                rec.success = True
                rec.final_stage = "tap"
            elif rec.final_stage != "template":
                rec.final_stage = "tap"
    else:
        with progress:
            baseline_task = progress.add_task(
                f"Baseline prompts · {_asr_display(records)}",
                total=len(records),
            )
            for rec in records:
                result = await _run_prompt_attack(
                    objective_target_spec=objective_target_spec,
                    evaluator_spec=evaluator_spec,
                    objective=rec.objective,
                    prepended_conversation=None,
                )
                rec.baseline_outcome = _normalize_outcome(result.outcome)
                rec.final_response = _extract_response_text(result)
                rec.transformed_prompt = None
                rec.baseline_reason = _extract_outcome_reason(result)
                rec.baseline_score_summary = _extract_score_summary(result)
                if _is_success(result.outcome):
                    rec.success = True
                    rec.final_stage = "baseline"
                progress.update(baseline_task, description=f"Baseline prompts · {_asr_display(records)}")
                progress.advance(baseline_task)

            max_template_attempts = len(templates) * len(records)
            template_task = progress.add_task(
                f"Template retries · {_asr_display(records)}",
                total=max_template_attempts,
            )
            actual_template_attempts = 0
            for template in templates:
                template_name = template.relative_to(JAILBREAK_TEMPLATES_PATH).as_posix()
                prepended = build_jailbreak_prepended_conversation(
                    jailbreak_template=str(template),
                    jailbreak_template_params=[],
                )
                for rec in records:
                    if rec.success:
                        continue
                    template_stats[template_name]["attempted"] += 1
                    actual_template_attempts += 1
                    result = await _run_prompt_attack(
                        objective_target_spec=objective_target_spec,
                        evaluator_spec=evaluator_spec,
                        objective=rec.objective,
                        prepended_conversation=prepended,
                    )
                    out = _normalize_outcome(result.outcome)
                    rec.template_outcomes[template_name] = out
                    rec.final_response = _extract_response_text(result)
                    rec.transformed_prompt = _build_transformed_prompt(
                        prepended_conversation=prepended,
                        objective=rec.objective,
                    )
                    rec.last_template_reason = _extract_outcome_reason(result)
                    rec.last_template_score_summary = _extract_score_summary(result)
                    if _is_success(result.outcome):
                        rec.success = True
                        rec.template_winner = template_name
                        rec.final_stage = "template"
                        template_stats[template_name]["rescued"] += 1
                    progress.update(template_task, description=f"Template retries · {_asr_display(records)}")
                    progress.advance(template_task)
            progress.update(template_task, total=actual_template_attempts, completed=actual_template_attempts)

            tap_candidates = select_tap_candidates(records, tap_top_k)
            tap_task = progress.add_task(
                f"TAP fallback · {_asr_display(records)}",
                total=len(tap_candidates),
            )
            for rec in tap_candidates:
                rec.transformed_prompt = _tap_objective_note(rec.objective)
                result = await _run_tap_single(
                    objective_target_spec=objective_target_spec,
                    adversarial_target_spec=adversarial_target,
                    evaluator_spec=evaluator_spec,
                    objective=rec.objective,
                    tree_width=tap_tree_width,
                    tree_depth=tap_tree_depth,
                    branching_factor=tap_branching_factor,
                    score_threshold=tap_score_threshold,
                )
                rec.tap_outcome = _normalize_outcome(result.outcome)
                rec.final_response = _extract_response_text(result)
                rec.tap_reason = _extract_outcome_reason(result)
                rec.tap_score_summary = _extract_score_summary(result)
                if _is_success(result.outcome):
                    rec.success = True
                    rec.final_stage = "tap"
                elif rec.final_stage != "template":
                    rec.final_stage = "tap"
                progress.update(tap_task, description=f"TAP fallback · {_asr_display(records)}")
                progress.advance(tap_task)

    payload = aggregate_payload(
        records=records,
        template_stats=template_stats,
        meta=build_meta(
            objective_target=objective_target_spec,
            dataset=dataset,
            adversarial_target=adversarial_target,
            scorer_target=evaluator_spec,
            template_count=len(templates),
            tap_top_k=tap_top_k,
            report_title=report_title,
            report_organization=report_organization,
        ),
    )
    return write_benchmark_artifacts(output_dir=output_dir, payload=payload)


def run_benchmark_attack(**kwargs: Any) -> tuple[Path, Path]:
    return asyncio.run(run_benchmark_attack_async(**kwargs))
