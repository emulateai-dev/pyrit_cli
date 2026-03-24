"""Automated benchmark pipeline: baseline -> templates -> TAP fallback."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import Counter, defaultdict
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
from pyrit_cli.redteam.converter_fallback import (
    attack_converter_config_for_stack,
    resolve_fallback_converter_stacks,
)
from pyrit_cli.redteam.jailbreak_prepended import build_jailbreak_prepended_conversation
from pyrit_cli.redteam.prompt_sending import collect_objectives
from pyrit_cli.redteam.targets import openai_chat_from_spec

_SNAPSHOT_MAX = 4000


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
    attack_path_log: list[dict[str, Any]] = field(default_factory=list)

    def log_attack_step(self, *, stage: str, label: str, success: bool, prompt_snapshot: str) -> None:
        snap = prompt_snapshot.strip()
        if len(snap) > _SNAPSHOT_MAX:
            snap = snap[: _SNAPSHOT_MAX - 1] + "…"
        self.attack_path_log.append(
            {
                "order": len(self.attack_path_log),
                "stage": stage,
                "label": label,
                "success": success,
                "prompt_snapshot": snap,
            }
        )


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


def _stack_label(stack: list[str]) -> str:
    return "|".join(stack) if stack else "plain"


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
    """Best-effort final prompt when the run did not succeed (or no path log)."""
    if rec.final_stage == "tap":
        return _tap_objective_note(rec.objective)
    if rec.transformed_prompt and rec.template_winner:
        return rec.transformed_prompt
    return rec.objective.strip()


def resolve_success_final_prompt_and_label(rec: PromptRunRecord) -> tuple[str, str | None]:
    """Last successful path step defines the winning prompt text and strategy label."""
    last_win: dict[str, Any] | None = None
    for step in rec.attack_path_log:
        if step.get("success"):
            last_win = step
    if last_win:
        snap = (last_win.get("prompt_snapshot") or "").strip()
        label = (str(last_win.get("label") or "").strip()) or None
        stage = last_win.get("stage")
        if snap:
            if stage in ("baseline_converter", "template_converter") and label:
                return f"{snap}\n\n(Converter on victim path: {label})", label
            return snap, label
    return resolve_final_prompt_for_record(rec), None


def build_attack_paths_tree(*, dataset: str, records: list[PromptRunRecord]) -> dict[str, Any]:
    children: list[dict[str, Any]] = []
    for r in records:
        pv = r.objective.replace("\n", " ").strip()[:80]
        if len(r.objective) > 80:
            pv += "…"
        prompt_node: dict[str, Any] = {
            "name": f"#{r.index} {pv}",
            "type": "prompt",
            "index": r.index,
            "final_success": r.success,
            "children": [],
        }
        for step in r.attack_path_log:
            prompt_node["children"].append(
                {
                    "name": step["label"],
                    "type": "step",
                    "stage": step["stage"],
                    "success": step["success"],
                }
            )
        children.append(prompt_node)
    return {"name": str(dataset), "type": "dataset", "children": children}


def _step_merge_id(stage: str, label: str, success: bool) -> str:
    raw = f"{stage}\0{label}\0{success}"
    return "st_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _diagram_compact_label(meta: dict[str, Any]) -> str:
    t = meta["type"]
    n = (meta.get("name") or "").replace("\n", " ").strip()
    if t == "dataset":
        return n if len(n) <= 24 else n[:23] + "…"
    if t == "prompt":
        m = re.match(r"^#(\d+)\b", n)
        if m:
            return f"#{m.group(1)}"
        return n if len(n) <= 12 else n[:11] + "…"
    if t == "step":
        stage = str(meta.get("stage") or "")
        if stage == "baseline":
            return "bl"
        if stage == "baseline_converter":
            return "bl+"
        if stage == "tap":
            return "TAP"
        if stage == "template_converter":
            tc = n.split("/")[-1] if "/" in n else n
            tc = tc if len(tc) <= 10 else "…" + tc[-9:]
            return "t+" + tc
        if stage == "template":
            tail = n.split("/")[-1] if "/" in n else n
            if tail.startswith("template:"):
                tail = tail[len("template:") :]
            tail = tail if len(tail) <= 12 else "…" + tail[-11:]
            return "t·" + tail
        return n if len(n) <= 14 else n[:13] + "…"
    return n if len(n) <= 16 else n[:15] + "…"


def _diagram_full_title(meta: dict[str, Any]) -> str:
    n = (meta.get("name") or "").replace("\n", " ").strip()
    if meta["type"] == "prompt" and meta.get("final_success") is not None:
        return n + " — final " + ("PASS" if meta["final_success"] else "FAIL")
    if meta["type"] == "step":
        st = str(meta.get("stage") or "")
        succ = bool(meta.get("success"))
        return n + " (" + st + ") — " + ("jailbreak signal" if succ else "defense held")
    return n


def build_path_diagram_layers(*, dataset: str, records: list[PromptRunRecord]) -> dict[str, Any]:
    """Layered DAG for the pipeline figure: identical stage+label+scorer outcome share one node."""
    ds_id = "d0"
    nodes: dict[str, dict[str, Any]] = {
        ds_id: {
            "id": ds_id,
            "type": "dataset",
            "name": str(dataset),
            "stage": None,
            "success": None,
            "final_success": None,
        }
    }
    edges: set[tuple[str, str]] = set()

    for r in records:
        pv = r.objective.replace("\n", " ").strip()[:80]
        if len(r.objective) > 80:
            pv += "…"
        pid = f"p{r.index}"
        if pid not in nodes:
            nodes[pid] = {
                "id": pid,
                "type": "prompt",
                "name": f"#{r.index} {pv}",
                "stage": None,
                "success": None,
                "final_success": r.success,
            }
        edges.add((ds_id, pid))
        prev = pid
        for step in r.attack_path_log:
            st = str(step.get("stage", ""))
            lab = str(step.get("label", ""))
            ok = bool(step.get("success"))
            sid = _step_merge_id(st, lab, ok)
            if sid not in nodes:
                nodes[sid] = {
                    "id": sid,
                    "type": "step",
                    "name": lab,
                    "stage": st,
                    "success": ok,
                    "final_success": None,
                }
            edges.add((prev, sid))
            prev = sid

    incoming: dict[str, set[str]] = defaultdict(set)
    for p, c in edges:
        incoming[c].add(p)

    level_memo: dict[str, int] = {}

    def level_of(nid: str) -> int:
        if nid in level_memo:
            return level_memo[nid]
        ps = incoming.get(nid, set())
        if not ps:
            lev = 0
        else:
            lev = max(level_of(x) for x in ps) + 1
        level_memo[nid] = lev
        return lev

    for nid in nodes:
        level_of(nid)

    max_lv = max(level_memo.values(), default=0)
    levels_out: list[list[dict[str, Any]]] = [[] for _ in range(max_lv + 1)]
    for nid, meta in nodes.items():
        lv = level_memo[nid]
        parents_sorted = sorted(incoming.get(nid, set()))
        entry: dict[str, Any] = {
            "id": nid,
            "parents": parents_sorted,
            "type": meta["type"],
            "name": meta.get("name") or "",
            "stage": meta.get("stage"),
            "success": meta.get("success"),
            "final_success": meta.get("final_success"),
            "label": _diagram_compact_label(meta),
            "fullTitle": _diagram_full_title(meta),
            "nodeType": meta["type"],
            "stepSuccess": meta.get("success"),
        }
        levels_out[lv].append(entry)

    for row in levels_out:
        row.sort(key=lambda x: x["id"])

    return {"format": "layers", "levels": levels_out}


_PATH_SIG_TOP_K = 30

_SANKEY_START = "start"
_SANKEY_END_PASS = "end_pass"
_SANKEY_END_FAIL = "end_fail"


def _sankey_step_node_id(depth: int, stage: str, success: bool) -> str:
    suf = "T" if success else "F"
    st = stage.replace("|", "/")
    st = re.sub(r"[\s]+", " ", st).strip()[:64]
    return f"L{depth}|{st}|{suf}"


def _signature_step_phrase(step: dict[str, Any]) -> str:
    stage = str(step.get("stage", ""))
    lab = str(step.get("label", "")).replace("\n", " ").strip()
    ok = bool(step.get("success"))
    outcome = "jailbreak signal" if ok else "defense held"
    if stage == "baseline":
        return f"baseline ({outcome})"
    if stage == "baseline_converter":
        tail = lab.split("/")[-1] if "/" in lab else lab
        return f"baseline+conv {tail[:40]} ({outcome})"
    if stage == "template":
        tail = lab.split("/")[-1] if "/" in lab else lab
        tail = tail.removeprefix("template:")
        return f"template {tail[:48]} ({outcome})"
    if stage == "template_converter":
        tail = lab.split("/")[-1] if "/" in lab else lab
        return f"template+conv {tail[:36]} ({outcome})"
    if stage == "tap":
        return f"TAP ({outcome})"
    return f"{stage or 'step'} ({outcome})"


def _signature_key_from_log(log: list[dict[str, Any]], final_success: bool) -> str:
    parts = [
        f"{s.get('stage','')}|{s.get('label','')}|{int(bool(s.get('success')))}" for s in log
    ]
    return "\n".join(parts) + f"\nfinal|{int(final_success)}"


def build_attack_path_overview(*, records: list[PromptRunRecord]) -> dict[str, Any]:
    """Aggregates for large runs: Sankey link counts + top path signatures."""
    if not records:
        return {
            "sankey": {"nodes": [], "links": []},
            "path_signatures": [],
            "path_signature_total_distinct": 0,
        }

    link_counts: Counter[tuple[str, str]] = Counter()
    sig_agg: dict[str, dict[str, Any]] = {}

    for r in records:
        log = list(r.attack_path_log)
        fs = bool(r.success)

        sig_key = _signature_key_from_log(log, fs)
        if sig_key not in sig_agg:
            human = (
                " → ".join(_signature_step_phrase(s) for s in log)
                or "(no logged steps)"
            )
            human += " → " + ("final PASS" if fs else "final FAIL")
            sig_agg[sig_key] = {
                "signature": human,
                "count": 0,
                "final_success": 0,
                "final_failure": 0,
            }
        sig_agg[sig_key]["count"] += 1
        if fs:
            sig_agg[sig_key]["final_success"] += 1
        else:
            sig_agg[sig_key]["final_failure"] += 1

        if not log:
            tgt = _SANKEY_END_PASS if fs else _SANKEY_END_FAIL
            link_counts[(_SANKEY_START, tgt)] += 1
            continue

        prev = _SANKEY_START
        for d, step in enumerate(log):
            st = str(step.get("stage", "unknown"))
            ok = bool(step.get("success"))
            nid = _sankey_step_node_id(d, st, ok)
            link_counts[(prev, nid)] += 1
            prev = nid
        tgt = _SANKEY_END_PASS if fs else _SANKEY_END_FAIL
        link_counts[(prev, tgt)] += 1

    needed: set[str] = set()
    for (a, b), v in link_counts.items():
        if v <= 0:
            continue
        needed.add(a)
        needed.add(b)

    node_ids: list[str] = []
    if _SANKEY_START in needed:
        node_ids.append(_SANKEY_START)
    node_ids.extend(sorted(k for k in needed if k.startswith("L")))
    if _SANKEY_END_PASS in needed:
        node_ids.append(_SANKEY_END_PASS)
    if _SANKEY_END_FAIL in needed:
        node_ids.append(_SANKEY_END_FAIL)

    node_meta: dict[str, dict[str, Any]] = {}
    for nid in node_ids:
        if nid == _SANKEY_START:
            node_meta[nid] = {
                "id": nid,
                "label": "All prompts",
                "kind": "start",
                "stepSuccess": None,
            }
        elif nid == _SANKEY_END_PASS:
            node_meta[nid] = {
                "id": nid,
                "label": "Final PASS",
                "kind": "end",
                "stepSuccess": True,
            }
        elif nid == _SANKEY_END_FAIL:
            node_meta[nid] = {
                "id": nid,
                "label": "Final FAIL",
                "kind": "end",
                "stepSuccess": False,
            }
        else:
            segs = nid.split("|")
            if len(segs) != 3 or not segs[0].startswith("L"):
                node_meta[nid] = {"id": nid, "label": nid, "kind": "step", "stepSuccess": None}
                continue
            try:
                depth_i = int(segs[0][1:])
            except ValueError:
                node_meta[nid] = {"id": nid, "label": nid, "kind": "step", "stepSuccess": None}
                continue
            stage_raw = segs[1]
            suf = segs[2]
            ok = suf == "T"
            stage_disp = stage_raw.replace("_", " ")[:48]
            node_meta[nid] = {
                "id": nid,
                "label": f"[{depth_i}] {stage_disp} ({'signal' if ok else 'held'})",
                "kind": "step",
                "stepSuccess": ok,
            }

    id_index = {nid: i for i, nid in enumerate(node_ids)}
    sankey_links: list[dict[str, Any]] = []
    for (src, tgt), v in link_counts.items():
        if v <= 0:
            continue
        sankey_links.append({"source": id_index[src], "target": id_index[tgt], "value": int(v)})

    sankey_nodes = [node_meta[nid] for nid in node_ids]

    sig_rows = sorted(sig_agg.values(), key=lambda x: (-x["count"], x["signature"]))[:_PATH_SIG_TOP_K]

    return {
        "sankey": {"nodes": sankey_nodes, "links": sankey_links},
        "path_signatures": sig_rows,
        "path_signature_total_distinct": len(sig_agg),
    }


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
        if r.success:
            final_prompt, winning_label = resolve_success_final_prompt_and_label(r)
        else:
            final_prompt, winning_label = resolve_final_prompt_for_record(r), None
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
                "final_prompt": final_prompt,
                "winning_step_label": winning_label,
                "jailbreak_attempted": jailbreak_attempted,
                "tap_applied": tap_applied,
                "outcome_reason": resolve_outcome_reason_text(r),
                "score_summary": resolve_score_summary_for_record(r),
                "attack_path_log": list(r.attack_path_log),
            }
        )

    dataset_label = str(meta.get("dataset", "dataset"))
    attack_paths = build_attack_paths_tree(dataset=dataset_label, records=records)
    attack_path_diagram = build_path_diagram_layers(dataset=dataset_label, records=records)
    attack_path_overview = build_attack_path_overview(records=records)

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
        "attack_paths": attack_paths,
        "attack_path_diagram": attack_path_diagram,
        "attack_path_overview": attack_path_overview,
    }


async def _run_prompt_attack(
    *,
    objective_target_spec: str,
    evaluator_spec: str,
    objective: str,
    prepended_conversation: list[Message] | None,
    attack_converter_config: Any | None = None,
) -> AttackResult:
    objective_target = openai_chat_from_spec(objective_target_spec)
    scorer_target = openai_chat_from_spec(evaluator_spec)
    scoring_cfg = AttackScoringConfig(
        objective_scorer=TrueFalseInverterScorer(scorer=SelfAskRefusalScorer(chat_target=scorer_target))
    )
    attack = PromptSendingAttack(
        objective_target=objective_target,
        attack_scoring_config=scoring_cfg,
        attack_converter_config=attack_converter_config,
    )
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
    attack_converter_config: Any | None = None,
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
        attack_converter_config=attack_converter_config,
        tree_width=tree_width,
        tree_depth=tree_depth,
        branching_factor=branching_factor,
    )
    return await attack.execute_async(objective=objective.strip())  # type: ignore[misc]


def _template_converter_budget(
    *,
    max_templates: int,
    num_templates: int,
    stacks: list[list[str]],
    explicit_cap: int | None,
) -> int:
    if not stacks:
        return 0
    derived = min(num_templates * len(stacks), max(1, max_templates) * len(stacks))
    if explicit_cap is not None:
        return min(explicit_cap, derived)
    return derived


async def _drive_benchmark_stages(
    *,
    records: list[PromptRunRecord],
    templates: list[Path],
    objective_target_spec: str,
    evaluator_spec: str,
    adversarial_target: str | None,
    stacks: list[list[str]],
    converter_fallback: bool,
    template_stats: dict[str, dict[str, int]],
    max_templates: int,
    tap_top_k: int,
    tap_tree_width: int,
    tap_tree_depth: int,
    tap_branching_factor: int,
    tap_score_threshold: float,
    max_template_converter_attempts: int | None,
    progress: Progress | None,
) -> None:
    def tick(task_id: int | None, desc: str) -> None:
        if progress is not None and task_id is not None:
            progress.update(task_id, description=desc)
            progress.advance(task_id)

    n_stacks = len(stacks)
    use_conv = converter_fallback and n_stacks > 0

    template_plain_cap = max(1, len(templates) * len(records))
    tc_budget = _template_converter_budget(
        max_templates=max_templates,
        num_templates=len(templates),
        stacks=stacks if use_conv else [],
        explicit_cap=max_template_converter_attempts,
    )
    if progress is not None:
        with progress:
            t_plain = progress.add_task(f"Baseline plain · {_asr_display(records)}", total=len(records))
            for rec in records:
                result = await _run_prompt_attack(
                    objective_target_spec=objective_target_spec,
                    evaluator_spec=evaluator_spec,
                    objective=rec.objective,
                    prepended_conversation=None,
                    attack_converter_config=None,
                )
                rec.baseline_outcome = _normalize_outcome(result.outcome)
                rec.final_response = _extract_response_text(result)
                rec.transformed_prompt = None
                rec.baseline_reason = _extract_outcome_reason(result)
                rec.baseline_score_summary = _extract_score_summary(result)
                ok = _is_success(result.outcome)
                rec.log_attack_step(
                    stage="baseline",
                    label="baseline (plain)",
                    success=ok,
                    prompt_snapshot=rec.objective,
                )
                if ok:
                    rec.success = True
                    rec.final_stage = "baseline"
                tick(t_plain, f"Baseline plain · {_asr_display(records)}")

            if use_conv:
                pending_after_baseline = [r for r in records if not r.success]
                if pending_after_baseline:
                    t_bconv = progress.add_task(
                        f"Baseline+converter · {_asr_display(records)}",
                        total=max(1, len(pending_after_baseline) * n_stacks),
                    )
                    for rec in records:
                        if rec.success:
                            continue
                        for stack in stacks:
                            cfg = attack_converter_config_for_stack(stack)
                            result = await _run_prompt_attack(
                                objective_target_spec=objective_target_spec,
                                evaluator_spec=evaluator_spec,
                                objective=rec.objective,
                                prepended_conversation=None,
                                attack_converter_config=cfg,
                            )
                            out = _normalize_outcome(result.outcome)
                            rec.baseline_outcome = out
                            rec.final_response = _extract_response_text(result)
                            rec.baseline_reason = _extract_outcome_reason(result)
                            rec.baseline_score_summary = _extract_score_summary(result)
                            ok = _is_success(result.outcome)
                            rec.log_attack_step(
                                stage="baseline_converter",
                                label=f"baseline+converter:{_stack_label(stack)}",
                                success=ok,
                                prompt_snapshot=rec.objective,
                            )
                            if ok:
                                rec.success = True
                                rec.final_stage = "baseline"
                                tick(t_bconv, f"Baseline+converter · {_asr_display(records)}")
                                break
                            tick(t_bconv, f"Baseline+converter · {_asr_display(records)}")

            t_tmpl = progress.add_task(f"Templates · {_asr_display(records)}", total=template_plain_cap)
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
                        attack_converter_config=None,
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
                    snap = rec.transformed_prompt or rec.objective
                    ok = _is_success(result.outcome)
                    rec.log_attack_step(
                        stage="template",
                        label=f"template:{template_name}",
                        success=ok,
                        prompt_snapshot=snap,
                    )
                    if ok:
                        rec.success = True
                        rec.template_winner = template_name
                        rec.final_stage = "template"
                        template_stats[template_name]["rescued"] += 1
                    tick(t_tmpl, f"Templates · {_asr_display(records)}")

            attempts = 0
            if use_conv and tc_budget > 0:
                t_tc = progress.add_task(f"Templates+converter · {_asr_display(records)}", total=tc_budget)
                outer_break = False
                for template in templates:
                    if outer_break:
                        break
                    template_name = template.relative_to(JAILBREAK_TEMPLATES_PATH).as_posix()
                    prepended = build_jailbreak_prepended_conversation(
                        jailbreak_template=str(template),
                        jailbreak_template_params=[],
                    )
                    for stack in stacks:
                        if outer_break:
                            break
                        cfg = attack_converter_config_for_stack(stack)
                        for rec in records:
                            if attempts >= tc_budget:
                                outer_break = True
                                break
                            if rec.success:
                                continue
                            template_stats[template_name]["attempted"] += 1
                            attempts += 1
                            result = await _run_prompt_attack(
                                objective_target_spec=objective_target_spec,
                                evaluator_spec=evaluator_spec,
                                objective=rec.objective,
                                prepended_conversation=prepended,
                                attack_converter_config=cfg,
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
                            snap = rec.transformed_prompt or rec.objective
                            ok = _is_success(result.outcome)
                            rec.log_attack_step(
                                stage="template_converter",
                                label=f"template:{template_name}+converter:{_stack_label(stack)}",
                                success=ok,
                                prompt_snapshot=snap,
                            )
                            if ok:
                                rec.success = True
                                rec.template_winner = template_name
                                rec.final_stage = "template"
                                template_stats[template_name]["rescued"] += 1
                            tick(t_tc, f"Templates+converter · {_asr_display(records)}")

            tap_cands = select_tap_candidates(records, tap_top_k)
            if tap_cands:
                tap_cap = len(tap_cands) * (n_stacks if use_conv else 1)
                t_tap = progress.add_task(f"TAP · {_asr_display(records)}", total=max(1, tap_cap))
                for rec in tap_cands:
                    # TAP is a separate jailbreak path: always the raw dataset objective, never
                    # jailbreak-template prepends. Optional converter stacks apply on the victim path only.
                    rec.transformed_prompt = _tap_objective_note(rec.objective)
                    tap_snap = rec.transformed_prompt
                    if use_conv:
                        tap_ok_any = False
                        for stack in stacks:
                            cfg = attack_converter_config_for_stack(stack)
                            result = await _run_tap_single(
                                objective_target_spec=objective_target_spec,
                                adversarial_target_spec=adversarial_target,
                                evaluator_spec=evaluator_spec,
                                objective=rec.objective,
                                tree_width=tap_tree_width,
                                tree_depth=tap_tree_depth,
                                branching_factor=tap_branching_factor,
                                score_threshold=tap_score_threshold,
                                attack_converter_config=cfg,
                            )
                            out = _normalize_outcome(result.outcome)
                            rec.tap_outcome = out
                            rec.final_response = _extract_response_text(result)
                            rec.tap_reason = _extract_outcome_reason(result)
                            rec.tap_score_summary = _extract_score_summary(result)
                            ok = _is_success(result.outcome)
                            rec.log_attack_step(
                                stage="tap",
                                label=f"tap+converter:{_stack_label(stack)}",
                                success=ok,
                                prompt_snapshot=tap_snap,
                            )
                            tick(t_tap, f"TAP · {_asr_display(records)}")
                            if ok:
                                rec.success = True
                                rec.final_stage = "tap"
                                tap_ok_any = True
                                break
                        if not tap_ok_any and rec.final_stage != "template":
                            rec.final_stage = "tap"
                    else:
                        result = await _run_tap_single(
                            objective_target_spec=objective_target_spec,
                            adversarial_target_spec=adversarial_target,
                            evaluator_spec=evaluator_spec,
                            objective=rec.objective,
                            tree_width=tap_tree_width,
                            tree_depth=tap_tree_depth,
                            branching_factor=tap_branching_factor,
                            score_threshold=tap_score_threshold,
                            attack_converter_config=None,
                        )
                        rec.tap_outcome = _normalize_outcome(result.outcome)
                        rec.final_response = _extract_response_text(result)
                        rec.tap_reason = _extract_outcome_reason(result)
                        rec.tap_score_summary = _extract_score_summary(result)
                        ok = _is_success(result.outcome)
                        rec.log_attack_step(
                            stage="tap",
                            label="tap (plain)",
                            success=ok,
                            prompt_snapshot=tap_snap,
                        )
                        if ok:
                            rec.success = True
                            rec.final_stage = "tap"
                        elif rec.final_stage != "template":
                            rec.final_stage = "tap"
                        tick(t_tap, f"TAP · {_asr_display(records)}")
        return

    # No progress bar
    for rec in records:
        result = await _run_prompt_attack(
            objective_target_spec=objective_target_spec,
            evaluator_spec=evaluator_spec,
            objective=rec.objective,
            prepended_conversation=None,
            attack_converter_config=None,
        )
        rec.baseline_outcome = _normalize_outcome(result.outcome)
        rec.final_response = _extract_response_text(result)
        rec.transformed_prompt = None
        rec.baseline_reason = _extract_outcome_reason(result)
        rec.baseline_score_summary = _extract_score_summary(result)
        ok = _is_success(result.outcome)
        rec.log_attack_step(
            stage="baseline",
            label="baseline (plain)",
            success=ok,
            prompt_snapshot=rec.objective,
        )
        if ok:
            rec.success = True
            rec.final_stage = "baseline"

    if use_conv:
        for rec in records:
            if rec.success:
                continue
            for stack in stacks:
                cfg = attack_converter_config_for_stack(stack)
                result = await _run_prompt_attack(
                    objective_target_spec=objective_target_spec,
                    evaluator_spec=evaluator_spec,
                    objective=rec.objective,
                    prepended_conversation=None,
                    attack_converter_config=cfg,
                )
                out = _normalize_outcome(result.outcome)
                rec.baseline_outcome = out
                rec.final_response = _extract_response_text(result)
                rec.baseline_reason = _extract_outcome_reason(result)
                rec.baseline_score_summary = _extract_score_summary(result)
                ok = _is_success(result.outcome)
                rec.log_attack_step(
                    stage="baseline_converter",
                    label=f"baseline+converter:{_stack_label(stack)}",
                    success=ok,
                    prompt_snapshot=rec.objective,
                )
                if ok:
                    rec.success = True
                    rec.final_stage = "baseline"
                    break

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
                attack_converter_config=None,
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
            snap = rec.transformed_prompt or rec.objective
            ok = _is_success(result.outcome)
            rec.log_attack_step(
                stage="template",
                label=f"template:{template_name}",
                success=ok,
                prompt_snapshot=snap,
            )
            if ok:
                rec.success = True
                rec.template_winner = template_name
                rec.final_stage = "template"
                template_stats[template_name]["rescued"] += 1

    attempts = 0
    tc_budget = _template_converter_budget(
        max_templates=max_templates,
        num_templates=len(templates),
        stacks=stacks if use_conv else [],
        explicit_cap=max_template_converter_attempts,
    )
    if use_conv and tc_budget > 0:
        outer_break = False
        for template in templates:
            if outer_break:
                break
            template_name = template.relative_to(JAILBREAK_TEMPLATES_PATH).as_posix()
            prepended = build_jailbreak_prepended_conversation(
                jailbreak_template=str(template),
                jailbreak_template_params=[],
            )
            for stack in stacks:
                if outer_break:
                    break
                cfg = attack_converter_config_for_stack(stack)
                for rec in records:
                    if attempts >= tc_budget:
                        outer_break = True
                        break
                    if rec.success:
                        continue
                    template_stats[template_name]["attempted"] += 1
                    attempts += 1
                    result = await _run_prompt_attack(
                        objective_target_spec=objective_target_spec,
                        evaluator_spec=evaluator_spec,
                        objective=rec.objective,
                        prepended_conversation=prepended,
                        attack_converter_config=cfg,
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
                    snap = rec.transformed_prompt or rec.objective
                    ok = _is_success(result.outcome)
                    rec.log_attack_step(
                        stage="template_converter",
                        label=f"template:{template_name}+converter:{_stack_label(stack)}",
                        success=ok,
                        prompt_snapshot=snap,
                    )
                    if ok:
                        rec.success = True
                        rec.template_winner = template_name
                        rec.final_stage = "template"
                        template_stats[template_name]["rescued"] += 1

    tap_cands = select_tap_candidates(records, tap_top_k)
    for rec in tap_cands:
        # Same as progress-bar branch: TAP objective is always the base prompt (see comment there).
        rec.transformed_prompt = _tap_objective_note(rec.objective)
        tap_snap = rec.transformed_prompt
        if use_conv:
            tap_ok_any = False
            for stack in stacks:
                cfg = attack_converter_config_for_stack(stack)
                result = await _run_tap_single(
                    objective_target_spec=objective_target_spec,
                    adversarial_target_spec=adversarial_target,
                    evaluator_spec=evaluator_spec,
                    objective=rec.objective,
                    tree_width=tap_tree_width,
                    tree_depth=tap_tree_depth,
                    branching_factor=tap_branching_factor,
                    score_threshold=tap_score_threshold,
                    attack_converter_config=cfg,
                )
                out = _normalize_outcome(result.outcome)
                rec.tap_outcome = out
                rec.final_response = _extract_response_text(result)
                rec.tap_reason = _extract_outcome_reason(result)
                rec.tap_score_summary = _extract_score_summary(result)
                ok = _is_success(result.outcome)
                rec.log_attack_step(
                    stage="tap",
                    label=f"tap+converter:{_stack_label(stack)}",
                    success=ok,
                    prompt_snapshot=tap_snap,
                )
                if ok:
                    rec.success = True
                    rec.final_stage = "tap"
                    tap_ok_any = True
                    break
            if not tap_ok_any and rec.final_stage != "template":
                rec.final_stage = "tap"
        else:
            result = await _run_tap_single(
                objective_target_spec=objective_target_spec,
                adversarial_target_spec=adversarial_target,
                evaluator_spec=evaluator_spec,
                objective=rec.objective,
                tree_width=tap_tree_width,
                tree_depth=tap_tree_depth,
                branching_factor=tap_branching_factor,
                score_threshold=tap_score_threshold,
                attack_converter_config=None,
            )
            rec.tap_outcome = _normalize_outcome(result.outcome)
            rec.final_response = _extract_response_text(result)
            rec.tap_reason = _extract_outcome_reason(result)
            rec.tap_score_summary = _extract_score_summary(result)
            ok = _is_success(result.outcome)
            rec.log_attack_step(
                stage="tap",
                label="tap (plain)",
                success=ok,
                prompt_snapshot=tap_snap,
            )
            if ok:
                rec.success = True
                rec.final_stage = "tap"
            elif rec.final_stage != "template":
                rec.final_stage = "tap"


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
    converter_fallback: bool = False,
    max_converter_stacks: int = 3,
    converter_fallback_stacks: list[list[str]] | None = None,
    max_template_converter_attempts: int | None = None,
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
    stacks = resolve_fallback_converter_stacks(
        enabled=converter_fallback,
        max_stacks=max_converter_stacks,
        explicit_stacks=converter_fallback_stacks,
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

    await _drive_benchmark_stages(
        records=records,
        templates=templates,
        objective_target_spec=objective_target_spec,
        evaluator_spec=evaluator_spec,
        adversarial_target=adversarial_target,
        stacks=stacks,
        converter_fallback=converter_fallback,
        template_stats=template_stats,
        max_templates=max_templates,
        tap_top_k=tap_top_k,
        tap_tree_width=tap_tree_width,
        tap_tree_depth=tap_tree_depth,
        tap_branching_factor=tap_branching_factor,
        tap_score_threshold=tap_score_threshold,
        max_template_converter_attempts=max_template_converter_attempts,
        progress=progress,
    )

    meta = build_meta(
        objective_target=objective_target_spec,
        dataset=dataset,
        adversarial_target=adversarial_target,
        scorer_target=evaluator_spec,
        template_count=len(templates),
        tap_top_k=tap_top_k,
        report_title=report_title,
        report_organization=report_organization,
        converter_fallback=converter_fallback,
        max_converter_stacks=max_converter_stacks,
    )
    payload = aggregate_payload(
        records=records,
        template_stats=template_stats,
        meta=meta,
    )
    return write_benchmark_artifacts(output_dir=output_dir, payload=payload)


def run_benchmark_attack(**kwargs: Any) -> tuple[Path, Path]:
    return asyncio.run(run_benchmark_attack_async(**kwargs))
