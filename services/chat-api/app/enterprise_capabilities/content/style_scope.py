"""Authorize a workflow-bound writing standard against the immutable profile."""

from __future__ import annotations

from app.dsh_runtime.profile.models import RuntimeProfileSnapshot


def apply_writing_style_ref(
    arguments: dict,
    turn_context: dict,
    profile: RuntimeProfileSnapshot,
) -> tuple[dict, dict]:
    clean_arguments = dict(arguments)
    style_ref = str(clean_arguments.pop("writing_style_ref", "") or "").strip()
    clean_context = dict(turn_context)
    if not style_ref or clean_context.get("selected_writing_skill_id"):
        return clean_arguments, clean_context
    style = next((item for item in profile.writing_styles if item.ref == style_ref), None)
    if style is None:
        raise PermissionError("writing_style_ref is not authorized by this Runtime Profile")
    clean_context["selected_writing_skill_id"] = style.source_id
    return clean_arguments, clean_context
