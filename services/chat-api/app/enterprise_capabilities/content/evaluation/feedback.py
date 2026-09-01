"""Project evaluation issues back into the existing writer pipeline."""

from __future__ import annotations

from collections.abc import Sequence

from .contracts import Issue


def issues_summary(issues: Sequence[Issue]) -> str:
    if not issues:
        return "no issues"
    counts = {"critical": 0, "major": 0, "minor": 0}
    for issue in issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
    parts = [f"{severity}={count}" for severity, count in counts.items() if count > 0]
    return ", ".join(parts) if parts else "no issues"


def issues_as_writer_feedback(issues: Sequence[Issue]) -> str:
    if not issues:
        return ""
    lines = ["上一版产物存在以下问题，本次重写时请避免："]
    for index, issue in enumerate(issues, start=1):
        lines.append(f"{index}. [{issue.severity}] {issue.location} — {issue.finding}")
        if issue.fix_suggestion:
            lines.append(f"   建议: {issue.fix_suggestion}")
    return "\n".join(lines)
