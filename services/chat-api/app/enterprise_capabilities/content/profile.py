from __future__ import annotations

from typing import Any

from app.enterprise_capabilities.content.profile_presets.resolver import ProfilePresetResolver


async def apply_content_profile(
    *,
    messages: list[dict[str, Any]],
    output_spec: dict[str, Any],
    task_ir: dict[str, Any],
    resolver: ProfilePresetResolver | None = None,
) -> dict[str, Any]:
    resolution = await (resolver or ProfilePresetResolver()).resolve(
        messages=messages, output_spec=output_spec, task_ir=task_ir,
    )
    preset = resolution.selected_preset.model_dump(mode="json") if resolution.selected_preset else {}
    trace = dict(resolution.trace or {})
    structure = dict(preset.get("structure_contract") or {})
    explicit = [str(x).strip() for x in list(output_spec.get("required_blocks") or []) if str(x).strip()]
    if explicit:
        structure["required_blocks"] = explicit
        structure["section_count"] = max(len(explicit), int(structure.get("section_count") or 0))
        preset["structure_contract"] = structure
    output_spec["compose_profile"] = dict(trace.get("compose_profile") or {})
    output_spec["profile_preset"] = preset
    output_spec["profile_preset_trace"] = trace
    output_spec["profile_preset_used_dynamic"] = bool(resolution.used_dynamic)
    output_spec["generation_policy"] = {
        **dict(output_spec.get("generation_policy") or {}),
        **dict(preset.get("compose_policy") or {}),
        **{key: value for key, value in dict(preset.get("quality_gates") or {}).items() if key in {"min_words", "max_words"}},
    }
    if structure.get("required_blocks"):
        output_spec["required_blocks"] = list(structure["required_blocks"])
    output_spec["write_skill_name"] = "tool_writer_engine_compose"
    output_spec["dynamic_skill_selected"] = "tool_writer_engine_compose"
    output_spec["executor_locked"] = True
    return {
        "preset_id": str(preset.get("preset_id") or ""),
        "preset_source": str(preset.get("source") or ""),
        "used_dynamic": bool(resolution.used_dynamic),
    }


__all__ = ["apply_content_profile"]
