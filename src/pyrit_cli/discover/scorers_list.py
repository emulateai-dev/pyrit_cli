"""List scorer presets and PyRIT-exported scorers (hint for RedTeamingAttack objective_scorer)."""

from __future__ import annotations

import inspect

import pyrit.score as score_package
from pyrit.score.true_false.true_false_scorer import TrueFalseScorer

from pyrit_cli.registries.scorers import SCORER_PRESETS_DOC


def list_scorers_text() -> str:
    lines: list[str] = [
        "CLI presets for `pyrit-cli redteam red-teaming-attack --scorer-preset`:",
        "-" * 60,
    ]
    for key, desc in SCORER_PRESETS_DOC:
        lines.append(f"  {key}")
        lines.append(f"      {desc}")
    lines.append("")
    lines.append("PyRIT TrueFalseScorer subclasses (usable as objective_scorer in AttackScoringConfig):")
    lines.append("-" * 60)
    tf_names: list[str] = []
    for name in sorted(score_package.__all__):
        obj = getattr(score_package, name, None)
        if not inspect.isclass(obj):
            continue
        try:
            if issubclass(obj, TrueFalseScorer) and obj is not TrueFalseScorer:
                tf_names.append(name)
        except TypeError:
            continue
    for n in tf_names:
        lines.append(f"  {n}")
    lines.append("")
    lines.append("Other exported scorers (often float_scale or auxiliary; see PyRIT scoring docs):")
    lines.append("-" * 60)
    other = [n for n in sorted(score_package.__all__) if n not in tf_names and n != "TrueFalseScorer"]
    for n in other:
        lines.append(f"  {n}")
    return "\n".join(lines)
