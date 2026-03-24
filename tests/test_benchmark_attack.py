from __future__ import annotations

import json

from pyrit_cli.redteam.benchmark_attack import (
    PromptRunRecord,
    aggregate_payload,
    build_attack_paths_tree,
    resolve_benchmark_evaluator_spec,
    resolve_success_final_prompt_and_label,
    select_tap_candidates,
)
from pyrit_cli.redteam.converter_fallback import (
    attack_converter_config_for_stack,
    parse_fallback_stack_arg,
    resolve_fallback_converter_stacks,
)
from pyrit_cli.redteam.benchmark_report import build_benchmark_html, write_benchmark_artifacts


def test_resolve_benchmark_evaluator_spec() -> None:
    assert (
        resolve_benchmark_evaluator_spec(
            objective_target_spec="openai:victim",
            scorer_chat_target=None,
            adversarial_target="groq:red",
        )
        == "groq:red"
    )
    assert (
        resolve_benchmark_evaluator_spec(
            objective_target_spec="openai:victim",
            scorer_chat_target="openai:judge",
            adversarial_target="groq:red",
        )
        == "openai:judge"
    )
    assert (
        resolve_benchmark_evaluator_spec(
            objective_target_spec="openai:victim",
            scorer_chat_target=None,
            adversarial_target=None,
        )
        == "openai:victim"
    )


def test_select_tap_candidates_top_k() -> None:
    records = [
        PromptRunRecord(index=1, objective="a", success=True),
        PromptRunRecord(index=2, objective="b", success=False),
        PromptRunRecord(index=3, objective="c", success=False),
    ]
    selected = select_tap_candidates(records, top_k=1)
    assert len(selected) == 1
    assert selected[0].index == 2


def test_parse_and_resolve_fallback_stacks() -> None:
    assert parse_fallback_stack_arg("rot13, base64") == ["rot13", "base64"]
    assert resolve_fallback_converter_stacks(enabled=False, max_stacks=3, explicit_stacks=None) == []
    r = resolve_fallback_converter_stacks(enabled=True, max_stacks=2, explicit_stacks=None)
    assert len(r) == 2
    r2 = resolve_fallback_converter_stacks(
        enabled=True,
        max_stacks=5,
        explicit_stacks=[["emoji"], ["rot13", "atbash"]],
    )
    assert r2 == [["emoji"], ["rot13", "atbash"]]
    cfg = attack_converter_config_for_stack(["rot13"])
    assert cfg is not None


def test_resolve_success_final_prompt_uses_winning_step() -> None:
    rec = PromptRunRecord(index=1, objective="base", success=True, final_stage="template")
    rec.log_attack_step(stage="baseline", label="baseline (plain)", success=False, prompt_snapshot="base")
    rec.log_attack_step(
        stage="template",
        label="template:w.yaml",
        success=True,
        prompt_snapshot="wrapped base objective",
    )
    text, lbl = resolve_success_final_prompt_and_label(rec)
    assert text == "wrapped base objective"
    assert lbl == "template:w.yaml"


def test_build_attack_paths_tree() -> None:
    rec = PromptRunRecord(index=1, objective="hello")
    rec.log_attack_step(stage="baseline", label="baseline (plain)", success=False, prompt_snapshot="hello")
    tree = build_attack_paths_tree(dataset="pyrit:x", records=[rec])
    assert tree["type"] == "dataset"
    assert len(tree["children"]) == 1
    assert tree["children"][0]["children"][0]["name"] == "baseline (plain)"


def test_aggregate_payload_stage_counts() -> None:
    records = [
        PromptRunRecord(index=1, objective="a", baseline_outcome="SUCCESS", success=True, final_stage="baseline"),
        PromptRunRecord(index=2, objective="b", baseline_outcome="FAILURE", success=True, final_stage="template"),
        PromptRunRecord(index=3, objective="c", baseline_outcome="FAILURE", success=False, final_stage="tap"),
    ]
    payload = aggregate_payload(
        records=records,
        template_stats={"t1.yaml": {"attempted": 2, "rescued": 1}},
        meta={"dataset": "pyrit:x", "report_title": "Test report"},
    )
    assert payload["metrics"]["total_prompts"] == 3
    assert payload["metrics"]["stage"]["baseline_success"] == 1
    assert payload["metrics"]["stage"]["template_success"] == 2
    assert payload["metrics"]["stage"]["tap_success"] == 2
    assert payload["metrics"]["final_failure"] == 1
    assert "examples" not in payload
    assert "attack_paths" in payload
    assert "failed_prompt_examples" not in payload
    assert payload["attack_paths"]["type"] == "dataset"
    assert all("outcome_reason" in p for p in payload["prompts"])
    assert all("final_prompt" in p for p in payload["prompts"])
    assert all("attack_path_log" in p for p in payload["prompts"])
    assert all("winning_step_label" in p for p in payload["prompts"])


def test_report_artifacts_written(tmp_path) -> None:
    payload = {
        "meta": {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "objective_target": "openai:gpt-4o-mini",
            "dataset": "hf:demo/test",
            "report_title": "LLM security benchmark report",
            "report_organization": "Security engineering",
            "template_count": 8,
            "tap_top_k": 3,
        },
        "metrics": {
            "total_prompts": 2,
            "final_success": 1,
            "final_failure": 1,
            "stage": {"baseline_success": 0, "template_success": 1, "tap_success": 1},
        },
        "templates": [{"template": "a.yaml", "attempted": 2, "rescued": 1}],
        "prompts": [
            {
                "index": 1,
                "final_stage": "template",
                "success": True,
                "baseline_outcome": "FAILURE",
                "objective": "p1",
                "final_response": "r1",
                "final_prompt": "wrapped p1",
                "winning_step_label": "template:x.yaml",
                "jailbreak_attempted": True,
                "tap_applied": False,
                "outcome_reason": "Scorer success.",
                "score_summary": None,
            },
            {
                "index": 2,
                "final_stage": "tap",
                "success": False,
                "baseline_outcome": "FAILURE",
                "objective": "p2",
                "final_response": "r2",
                "final_prompt": "p2\n\n(TAP:",
                "winning_step_label": None,
                "jailbreak_attempted": True,
                "tap_applied": True,
                "outcome_reason": "TAP did not meet threshold.",
                "score_summary": '{"score_value": 0.2}',
            },
        ],
    }
    payload["attack_paths"] = {"name": "hf:demo/test", "type": "dataset", "children": []}
    html = build_benchmark_html(payload)
    assert "LLM security benchmark report" in html
    assert "PyRIT" not in html
    assert "Executive summary" in html
    assert "Attack paths (tangled tree)" in html
    assert "paths-tree-svg" in html
    assert "bench-attack-paths-json" in html
    assert "Failed-stage prompt examples" not in html
    assert "Winning strategy" in html
    assert "Final prompt (winning attempt)" in html
    assert "d3.min.js" in html
    assert "Final results" in html
    assert "Outcome reason" in html
    assert "details" in html
    html_path, json_path = write_benchmark_artifacts(output_dir=tmp_path, payload=payload)
    assert html_path.exists()
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["metrics"]["final_success"] == 1
