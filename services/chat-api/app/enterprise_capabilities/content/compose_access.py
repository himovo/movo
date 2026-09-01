from __future__ import annotations

from typing import Any, Dict


def _non_empty_required_sections(output_spec: Dict[str, Any]) -> list[str]:
    content_plan = output_spec.get("content_plan") if isinstance(output_spec.get("content_plan"), dict) else {}
    plan_sections = [
        str(item.get("title") or "").strip()
        for item in list(content_plan.get("sections") or [])
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    ]
    if plan_sections:
        return plan_sections[:12]
    profile_preset = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else {}
    structure = profile_preset.get("structure_contract") if isinstance(profile_preset.get("structure_contract"), dict) else {}
    required_blocks = [str(x).strip() for x in list(structure.get("required_blocks") or []) if str(x).strip()]
    if required_blocks:
        return required_blocks[:12]
    required = [str(x).strip() for x in list(output_spec.get("required_blocks") or []) if str(x).strip()]
    return required[:12]


def resolve_compose_policy(output_spec: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(output_spec or {})
    merged: Dict[str, Any] = {}
    for candidate in [
        out.get("profile_preset", {}).get("compose_policy") if isinstance(out.get("profile_preset"), dict) else {},
        out.get("compose_policy") if isinstance(out.get("compose_policy"), dict) else {},
        out.get("effective_policy", {}).get("compose_policy") if isinstance(out.get("effective_policy"), dict) else {},
        out.get("generation_policy") if isinstance(out.get("generation_policy"), dict) else {},
    ]:
        if not isinstance(candidate, dict):
            continue
        for key, value in candidate.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if isinstance(value, list) and not value:
                continue
            if isinstance(value, dict) and not value:
                continue
            merged[key] = value
    if not list(merged.get("required_sections") or []):
        fallback_sections = _non_empty_required_sections(out)
        if fallback_sections:
            merged["required_sections"] = fallback_sections
    return merged


def sync_generation_policy_from_effective_policy(output_spec: Dict[str, Any]) -> Dict[str, Any]:
    spec = dict(output_spec or {})
    effective = spec.get("effective_policy") if isinstance(spec.get("effective_policy"), dict) else {}
    compose = effective.get("compose_policy") if isinstance(effective.get("compose_policy"), dict) else {}
    if not compose:
        return spec
    gp = dict(spec.get("generation_policy") or {})
    existing_compose = spec.get("compose_policy") if isinstance(spec.get("compose_policy"), dict) else {}
    explicit_user_length = (
        str(gp.get("length_source") or "").strip() == "user_request"
        or str(existing_compose.get("length_source") or "").strip() == "user_request"
    )
    if explicit_user_length:
        if existing_compose.get("min_words") not in (None, "", 0):
            gp["min_words"] = existing_compose.get("min_words")
        else:
            gp["min_words"] = 0
        if existing_compose.get("max_words") not in (None, "", 0):
            gp["max_words"] = existing_compose.get("max_words")
        else:
            gp["max_words"] = 0
        gp["length_source"] = "user_request"
        gp["length_unit"] = existing_compose.get("length_unit") or gp.get("length_unit") or "chinese_chars"
    mapped = {
        "tone": compose.get("tone"),
        "voice": compose.get("voice"),
        "audience": compose.get("audience"),
        "publish_channel": compose.get("publish_channel"),
        "content_form": compose.get("content_form"),
        "presentation_skill_name": compose.get("presentation_skill_name"),
        "presentation_skill_source": compose.get("presentation_skill_source"),
        "presentation_policy": compose.get("presentation_policy"),
        "min_words": None if explicit_user_length else compose.get("min_words"),
        "max_words": None if explicit_user_length else compose.get("max_words"),
        "length_unit": None if explicit_user_length else compose.get("length_unit"),
        "length_source": None if explicit_user_length else compose.get("length_source"),
        "citation_required": compose.get("citation_required"),
        "style_description": compose.get("style_description") or "",
        "visual_requirements": compose.get("visual_requirements") or "",
        "visual_preferences": compose.get("visual_preferences") if isinstance(compose.get("visual_preferences"), dict) else {},
        "writing_instructions": list(compose.get("writing_instructions") or []),
    }
    gp.update({k: v for k, v in mapped.items() if v not in (None, "", [], {})})
    spec["generation_policy"] = gp
    spec["compose_policy"] = resolve_compose_policy(spec)
    return spec
