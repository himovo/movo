from __future__ import annotations

import json
from typing import Any, Dict, List


MAX_PROMPT_BLOCK_CHARS = 16000
CONTRACT_HEADER = "# Writing Style Skill Contract"


def is_writer_style_contract_block(value: Any) -> bool:
    text = str(value or "").lstrip()
    return text.startswith(CONTRACT_HEADER) or CONTRACT_HEADER in text[:2000] or "writer_style_contract.v" in text[:2000]


def extract_writer_style_contract_block(*sources: Dict[str, Any] | None) -> str:
    for source in sources:
        if not isinstance(source, dict):
            continue
        direct = str(source.get("writer_style_contract_block") or "").strip()
        if direct:
            return direct
        contract = source.get("writer_style_contract")
        if isinstance(contract, dict):
            block = str(contract.get("prompt_block") or "").strip()
            if block:
                return block
    return ""


def resolve_writer_style_prompt(
    *,
    output_spec: Dict[str, Any] | None = None,
    payload: Dict[str, Any] | None = None,
    selected_style_markdowns: List[Any] | None = None,
) -> Dict[str, Any]:
    """Resolve writer style prompt with contract as the single primary source.

    When a normalized writer_style_contract exists, older style payloads are
    deliberately ignored. They are only fallback inputs for legacy skill data
    that has not produced a writer_style_contract.
    """

    output = output_spec if isinstance(output_spec, dict) else {}
    runtime_payload = payload if isinstance(payload, dict) else {}
    contract_block = extract_writer_style_contract_block(output, runtime_payload)
    if contract_block:
        return {"mode": "contract", "parts": [contract_block], "contract_block": contract_block}

    parts: List[str] = []
    for item in list(selected_style_markdowns or runtime_payload.get("selected_style_markdowns") or []):
        text = str(item or "").strip()
        if text:
            parts.append(text)

    prompt_contract = output.get("prompt_contract") if isinstance(output.get("prompt_contract"), dict) else {}
    compiled_style = str(
        prompt_contract.get("style_markdown_compact")
        or prompt_contract.get("style_markdown")
        or ""
    ).strip()
    if compiled_style:
        parts.insert(0, compiled_style)

    return {"mode": "legacy", "parts": parts, "contract_block": ""}


def build_writer_style_contract(
    style_skills: List[Dict[str, Any]] | None,
    *,
    user_request: str = "",
) -> Dict[str, Any]:
    skills = [dict(item) for item in list(style_skills or []) if isinstance(item, dict)]
    if not skills:
        return {}

    rendered_skills: List[Dict[str, Any]] = []
    blocks: List[str] = [
        "# Writing Style Skill Contract",
        "Priority: system/developer safety rules come first. If the current user request explicitly conflicts with this contract, the current user request wins; otherwise this contract is mandatory for generation.",
    ]
    request = str(user_request or "").strip()
    if request:
        blocks.append("Current user request:\n" + request)

    for skill in skills:
        contract = _normalize_style_skill(skill)
        if not contract:
            continue
        rendered_skills.append(contract)
        blocks.append(_render_single_contract(contract))

    if not rendered_skills:
        return {}

    prompt_block = "\n\n".join(part for part in blocks if str(part or "").strip()).strip()
    truncated = False
    if len(prompt_block) > MAX_PROMPT_BLOCK_CHARS:
        prompt_block = prompt_block[:MAX_PROMPT_BLOCK_CHARS].rstrip() + "\n\n[Contract truncated by backend safety limit]"
        truncated = True

    return {
        "version": "writer_style_contract.v1",
        "skills": rendered_skills,
        "prompt_block": prompt_block,
        "truncated": truncated,
    }


def _normalize_style_skill(skill: Dict[str, Any]) -> Dict[str, Any]:
    cfg = _dict(skill.get("config"))
    skill_contract = _dict(skill.get("skill_contract"))
    contract_json = _merge_dicts(
        _dict(cfg.get("contractJson") or cfg.get("contract_json")),
        _dict(cfg.get("inputProfile") or cfg.get("input_profile")),
        _dict(skill.get("contract_json")),
        _dict(skill.get("input_profile")),
        _dict(skill_contract.get("contract_json")),
    )
    structure = _dict(skill_contract.get("structure"))
    compose_profile = _dict(skill_contract.get("compose_profile"))

    section_structure = _list(
        contract_json.get("section_structure")
        or contract_json.get("sectionStructure")
        or structure.get("section_structure")
        or structure.get("sectionStructure")
    )
    required_sections = _strings(
        contract_json.get("required_sections")
        or contract_json.get("requiredSections")
        or structure.get("required_blocks")
        or structure.get("requiredBlocks")
    )
    if not required_sections and section_structure:
        required_sections = _section_titles(section_structure)

    target_length = _dict(
        contract_json.get("target_length")
        or contract_json.get("targetLength")
        or compose_profile.get("target_length")
        or compose_profile.get("targetLength")
        or skill_contract.get("length")
    )

    return {
        "id": str(skill.get("id") or skill.get("_id") or "").strip(),
        "name": str(skill.get("name") or contract_json.get("name") or "").strip(),
        "description": str(skill.get("description") or skill.get("summary") or contract_json.get("summary") or "").strip(),
        "applicable_scenarios": str(
            contract_json.get("applicable_scenarios")
            or skill.get("scenario")
            or skill.get("notes")
            or ""
        ).strip(),
        "publish_channel": _strings(contract_json.get("publish_channel")),
        "content_form": _strings(contract_json.get("content_form")),
        "target_audience": _strings(contract_json.get("target_audience")),
        "preferred_style": _strings(contract_json.get("preferred_style")),
        "target_length": target_length,
        "required_sections": required_sections,
        "section_structure": section_structure,
        "required_elements": _strings(contract_json.get("required_elements") or contract_json.get("requiredElements")),
        "forbidden_elements": _strings(contract_json.get("forbidden_elements") or contract_json.get("forbiddenElements")),
        "reference_materials": _strings(contract_json.get("reference_materials") or contract_json.get("referenceMaterials")),
        "notes": str(contract_json.get("notes") or compose_profile.get("style_description") or "").strip(),
    }


def _render_single_contract(contract: Dict[str, Any]) -> str:
    lines: List[str] = [f"## Skill: {contract.get('name') or contract.get('id') or 'writing_style'}"]
    _append_scalar(lines, "Description", contract.get("description"))
    _append_scalar(lines, "Applicable scenarios", contract.get("applicable_scenarios"))
    _append_list(lines, "Publish channel", contract.get("publish_channel"))
    _append_list(lines, "Content form", contract.get("content_form"))
    _append_list(lines, "Target audience", contract.get("target_audience"))
    _append_list(lines, "Tone/style", contract.get("preferred_style"))
    if contract.get("target_length"):
        lines.append("Target length: " + json.dumps(contract.get("target_length"), ensure_ascii=False, default=str))
    _append_list(lines, "Required sections", contract.get("required_sections"))
    if contract.get("section_structure"):
        lines.append("Section structure:")
        lines.extend(_render_sections(contract.get("section_structure") or []))
    _append_list(lines, "Must include", contract.get("required_elements"))
    _append_list(lines, "Must avoid", contract.get("forbidden_elements"))
    _append_list(lines, "Reference materials", contract.get("reference_materials"))
    _append_scalar(lines, "Notes", contract.get("notes"))
    return "\n".join(lines).strip()


def _render_sections(sections: List[Any], *, depth: int = 0) -> List[str]:
    out: List[str] = []
    indent = "  " * depth
    for raw in sections:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or raw.get("name") or "").strip()
        if title:
            out.append(f"{indent}- {title}")
        must = _strings(raw.get("must_include") or raw.get("mustInclude") or raw.get("required_elements"))
        avoid = _strings(raw.get("avoid") or raw.get("must_avoid") or raw.get("forbidden_elements"))
        notes = str(raw.get("notes") or "").strip()
        if must:
            out.append(f"{indent}  Must include: {'; '.join(must)}")
        if avoid:
            out.append(f"{indent}  Must avoid: {'; '.join(avoid)}")
        if notes:
            out.append(f"{indent}  Notes: {notes}")
        out.extend(_render_sections(_list(raw.get("children")), depth=depth + 1))
    return out


def _append_scalar(lines: List[str], label: str, value: Any) -> None:
    text = str(value or "").strip()
    if text:
        lines.append(f"{label}: {text}")


def _append_list(lines: List[str], label: str, values: Any) -> None:
    items = _strings(values)
    if items:
        lines.append(label + ":\n" + "\n".join(f"- {item}" for item in items))


def _merge_dicts(*items: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if key not in out or out.get(key) in (None, "", [], {}):
                out[key] = value
    return out


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    return []


def _strings(value: Any) -> List[str]:
    raw = value if isinstance(value, list) else [value] if value not in (None, "") else []
    out: List[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _section_titles(sections: List[Any]) -> List[str]:
    out: List[str] = []
    for raw in sections:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or raw.get("name") or "").strip()
        if title and title not in out:
            out.append(title)
        for child in _section_titles(_list(raw.get("children"))):
            if child not in out:
                out.append(child)
    return out
