from __future__ import annotations

import json

from pyrit_cli.redteam.benchmark_attack import (
    PromptRunRecord,
    aggregate_payload,
    resolve_benchmark_evaluator_spec,
    select_tap_candidates,
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
    assert all("outcome_reason" in p for p in payload["prompts"])
    assert all("final_prompt" in p for p in payload["prompts"])


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
                "jailbreak_attempted": True,
                "tap_applied": True,
                "outcome_reason": "TAP did not meet threshold.",
                "score_summary": '{"score_value": 0.2}',
            },
        ],
    }
    html = build_benchmark_html(payload)
    assert "LLM security benchmark report" in html
    assert "PyRIT" not in html
    assert "Executive summary" in html
    assert "Final results" in html
    assert "Outcome reason" in html
    assert "details" in html
    html_path, json_path = write_benchmark_artifacts(output_dir=tmp_path, payload=payload)
    assert html_path.exists()
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["metrics"]["final_success"] == 1
