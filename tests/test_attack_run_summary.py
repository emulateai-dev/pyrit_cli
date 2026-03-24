from __future__ import annotations

from pyrit.models import AttackOutcome, AttackResult

from pyrit_cli.redteam.attack_run_summary import format_attack_run_summary


def _ar(outcome: AttackOutcome, i: int = 0) -> AttackResult:
    return AttackResult(
        conversation_id=f"c{i}",
        objective=f"obj{i}",
        attack_identifier=None,
        outcome=outcome,
    )


def test_batch_all_success_asr_100() -> None:
    results = [_ar(AttackOutcome.SUCCESS, i) for i in range(10)]
    text = format_attack_run_summary(
        results,
        command="prompt-sending-attack",
        scoring_mode="auto",
        scorer_preset="non-refusal",
    )
    assert "Run summary (batch)" in text
    assert "Total runs:     10" in text
    assert "SUCCESS:        10" in text
    assert "ASR (SUCCESS/total): 100.0%" in text


def test_batch_mixed_asr_30() -> None:
    results = [_ar(AttackOutcome.SUCCESS, i) for i in range(3)] + [
        _ar(AttackOutcome.FAILURE, i) for i in range(3, 10)
    ]
    text = format_attack_run_summary(results, command="prompt-sending-attack", scoring_mode="auto")
    assert "ASR (SUCCESS/total): 30.0%  (3/10)" in text


def test_all_undetermined_no_asr() -> None:
    results = [_ar(AttackOutcome.UNDETERMINED, i) for i in range(5)]
    text = format_attack_run_summary(results, command="prompt-sending-attack", scoring_mode="off")
    assert "not meaningful" in text
    assert "ASR (SUCCESS/total)" not in text


def test_empty_results() -> None:
    text = format_attack_run_summary([], command="prompt-sending-attack")
    assert "No attack results" in text


def test_single_result_red_teaming_title() -> None:
    text = format_attack_run_summary(
        [_ar(AttackOutcome.FAILURE)],
        command="red-teaming-attack",
        scorer_preset="self-ask-tf",
    )
    assert "Run summary" in text
    assert "Run summary (batch)" not in text
    assert "ASR (SUCCESS/total): 0.0%  (0/1)" in text
    assert "self-ask-tf" in text


def test_tap_interpretation_includes_threshold() -> None:
    text = format_attack_run_summary(
        [_ar(AttackOutcome.SUCCESS)],
        command="tap-attack",
        tap_score_threshold=0.5,
    )
    assert "threshold=0.5" in text
