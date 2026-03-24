"""End-of-run aggregate stats (counts, ASR) for red-team CLI commands."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from pyrit.models import AttackOutcome, AttackResult


def format_attack_run_summary(
    results: Sequence[AttackResult],
    *,
    command: str,
    scoring_mode: str | None = None,
    scorer_preset: str | None = None,
    tap_score_threshold: float | None = None,
) -> str:
    """Return a plain-text footer: outcome counts and ASR where meaningful."""
    lines: list[str] = []
    n = len(results)
    sep = "=" * 80

    if n == 0:
        lines.append(sep)
        lines.append("Run summary")
        lines.append(sep)
        lines.append("  No attack results to summarize.")
        lines.append("")
        return "\n".join(lines)

    counts = Counter(r.outcome for r in results)
    success = counts.get(AttackOutcome.SUCCESS, 0)
    failure = counts.get(AttackOutcome.FAILURE, 0)
    undetermined = counts.get(AttackOutcome.UNDETERMINED, 0)

    batch = n > 1 and command == "prompt-sending-attack"
    title = "Run summary (batch)" if batch else "Run summary"

    lines.append(sep)
    lines.append(title)
    lines.append(sep)
    lines.append(f"  Total runs:     {n}")
    lines.append(f"  SUCCESS:        {success}")
    lines.append(f"  FAILURE:        {failure}")
    lines.append(f"  UNDETERMINED:   {undetermined}")

    if undetermined == n:
        lines.append("  ASR:            not meaningful (all UNDETERMINED; e.g. scoring off or scorer inconclusive).")
    else:
        asr_pct = 100.0 * success / n
        lines.append(f"  ASR (SUCCESS/total): {asr_pct:.1f}%  ({success}/{n})")

    lines.append("  ---")
    lines.append(f"  Note: { _interpretation_line(command, scoring_mode=scoring_mode, scorer_preset=scorer_preset, tap_score_threshold=tap_score_threshold) }")
    lines.append("")
    return "\n".join(lines)


def _interpretation_line(
    command: str,
    *,
    scoring_mode: str | None,
    scorer_preset: str | None,
    tap_score_threshold: float | None,
) -> str:
    if command == "prompt-sending-attack":
        mode = (scoring_mode or "auto").strip().lower()
        preset = (scorer_preset or "non-refusal").strip().lower().replace("_", "-")
        if mode == "off":
            return "Scoring was disabled; outcomes are often UNDETERMINED. Enable scoring for meaningful ASR."
        if mode == "auto":
            return (
                "With --scoring-mode auto, SUCCESS means the objective scorer marked non-refusal "
                "(inverted refusal), common for jailbreak-style success in safety benchmarks."
            )
        # configured
        if preset == "non-refusal":
            return (
                "With configured non-refusal preset, SUCCESS follows the same non-refusal / inverted-refusal idea as auto."
            )
        if preset == "refusal":
            return "With configured refusal preset, SUCCESS means the scorer classified the response as a refusal."
        if preset == "self-ask-tf":
            return "With self-ask-tf, SUCCESS means the model agreed the --true-description criterion was met."
        return "SUCCESS follows the configured objective scorer."

    if command == "red-teaming-attack":
        preset = (scorer_preset or "self-ask-tf").strip().lower().replace("_", "-")
        if preset == "self-ask-refusal":
            return "SUCCESS means the red-team objective was met per self-ask-refusal (refusal detection semantics)."
        return "SUCCESS means the red-team objective was met per self-ask-tf (--true-description criterion)."

    if command == "tap-attack":
        th = tap_score_threshold if tap_score_threshold is not None else 0.7
        return (
            f"SUCCESS means TAP's threshold objective scorer judged success "
            f"(default threshold 0.7 unless overridden; this run threshold={th})."
        )

    if command == "crescendo-attack":
        preset = (scorer_preset or "self-ask-tf").strip().lower().replace("_", "-")
        if preset == "self-ask-refusal":
            return "SUCCESS means the Crescendo objective was met per self-ask-refusal (refusal detection semantics)."
        return "SUCCESS means the Crescendo objective was met per self-ask-tf (--true-description criterion)."

    return "SUCCESS means objective achieved per PyRIT AttackOutcome for this command."


def print_attack_run_summary(
    results: Sequence[AttackResult],
    *,
    command: str,
    scoring_mode: str | None = None,
    scorer_preset: str | None = None,
    tap_score_threshold: float | None = None,
) -> None:
    text = format_attack_run_summary(
        results,
        command=command,
        scoring_mode=scoring_mode,
        scorer_preset=scorer_preset,
        tap_score_threshold=tap_score_threshold,
    )
    print(text, flush=True)
