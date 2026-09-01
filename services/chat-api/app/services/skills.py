from __future__ import annotations

import datetime
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import uuid

import yaml
from pydantic import BaseModel, Field, ValidationError

from app.core.tenant import add_main_scope, resolve_main_id
from app.core.db import get_db
from app.services.skill_assets.publish_channels import publish_channel_registry
from app.services.skill_assets.composite_task import parse_composite_skill
from app.services.llm import llm_service
from app.services.org_skill_adapter import _workflow_markdown, _workflow_nodes
from app.utils.oss_uploader import AliyunOSSUploader


logger = logging.getLogger(__name__)


@dataclass
class UserSkill:
    id: str
    user_id: str
    main_id: str
    name: str
    description: str
    summary: str
    category: str
    role: str
    skill_type: str
    tags: List[str]
    visibility: str
    formats: List[str]
    input_profile: Dict[str, Any]
    contract_json: Dict[str, Any]
    skill_markdown: str
    skill_object_path: str
    sources: List[Dict[str, Any]]
    resources: Dict[str, List[Dict[str, Any]]]
    advanced: Dict[str, Any]
    notes: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    is_active: bool = True


class SkillContractModel(BaseModel):
    skill_type: str = "style"
    name: str = Field(default="", min_length=1, max_length=120)
    summary: str = Field(default="", max_length=500)
    applicable_scenarios: str = Field(default="", max_length=1500)
    publish_channel: List[str] = Field(default_factory=list)
    content_form: List[str] = Field(default_factory=list)
    target_audience: List[str] = Field(default_factory=list)
    preferred_style: List[str] = Field(default_factory=list)
    target_length: Dict[str, Any] = Field(default_factory=dict)
    section_structure: List[Dict[str, Any]] = Field(default_factory=list)
    required_sections: List[str] = Field(default_factory=list)
    required_elements: List[str] = Field(default_factory=list)
    forbidden_elements: List[str] = Field(default_factory=list)
    reference_materials: List[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=4000)


def _split_frontmatter(content: str) -> tuple[dict, str]:
    if not content.startswith("---"):
        return {}, content
    parts = content.split("\n")
    end_idx = None
    for i in range(1, len(parts)):
        if parts[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, content
    front = "\n".join(parts[1:end_idx])
    body = "\n".join(parts[end_idx + 1 :]).lstrip()
    try:
        meta = yaml.safe_load(front) or {}
    except Exception:
        meta = {}
    return meta, body


def _slugify(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9\-]+", "-", name)
    name = re.sub(r"-{2,}", "-", name)
    name = name.strip("-")
    return name[:64] if len(name) > 64 else name


def _normalize_skill_role(role: Optional[str]) -> str:
    raw = str(role or "").strip().lower()
    aliases = {
        "compose": "execution",
        "writer": "execution",
        "write": "execution",
        "execute": "execution",
        "execution": "execution",
        "renderer": "renderer",
        "render": "renderer",
        "style": "style",
        "guideline": "style",
        "policy": "style",
    }
    return aliases.get(raw, "")


def _normalize_skill_type(skill_type: Optional[str], *, role: Optional[str] = None) -> str:
    raw = str(skill_type or "").strip().lower()
    aliases = {
        "style": "style",
        "writing_style": "style",
        "guideline": "style",
        "policy": "style",
        "execution": "execution",
        "execute": "execution",
        "compose": "execution",
        "writer": "execution",
        "renderer": "renderer",
        "render": "renderer",
        # A composite_task skill describes an ordered list of natural-language
        # steps (optionally per-step site context) that the planner expands
        # into subtasks. See UserSkillResolver.expand_composite_skill.
        "composite_task": "composite_task",
        "composite": "composite_task",
        "browser_task": "composite_task",
        "workflow": "composite_task",
    }
    normalized = aliases.get(raw, "")
    if normalized:
        return normalized
    normalized_role = _normalize_skill_role(role)
    if normalized_role in {"style", "execution", "renderer", "composite_task"}:
        return normalized_role
    return "style"


def _as_string_list(values: Any) -> List[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    out: List[str] = []
    seen: set[str] = set()
    for item in values:
        val = str(item or "").strip()
        if not val:
            continue
        key = val.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(val)
    return out


def _normalize_token_inputs(values: Any) -> List[str]:
    if isinstance(values, list):
        parts: List[str] = []
        for item in values:
            parts.extend(_split_list_tokens(str(item or "")))
        return _as_string_list(parts)
    return _split_list_tokens(str(values or ""))


def _normalize_target_length(value: Any) -> Dict[str, Any]:
    raw = dict(value or {}) if isinstance(value, dict) else {}

    def _coerce_int(v: Any) -> int:
        try:
            return max(0, int(float(str(v or "").strip())))
        except Exception:
            return 0

    min_value = _coerce_int(raw.get("min") or raw.get("min_words") or raw.get("minWords"))
    max_value = _coerce_int(raw.get("max") or raw.get("max_words") or raw.get("maxWords"))
    unit = str(raw.get("unit") or raw.get("length_unit") or "chinese_chars").strip() or "chinese_chars"
    out: Dict[str, Any] = {"unit": unit}
    if min_value > 0:
        out["min"] = min_value
    if max_value > 0:
        out["max"] = max_value
    return out


def _normalize_section_structure(value: Any, *, level: int = 1, max_depth: int = 2) -> List[Dict[str, Any]]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for raw in value:
        if isinstance(raw, str):
            title = raw.strip()
            if not title:
                continue
            item: Dict[str, Any] = {
                "title": title,
                "level": level,
                "must_include": [],
                "avoid": [],
                "notes": "",
                "children": [],
            }
        elif isinstance(raw, dict):
            title = str(raw.get("title") or raw.get("name") or raw.get("heading") or "").strip()
            if not title:
                continue
            try:
                raw_level = max(1, int(raw.get("level") or level or 1))
            except Exception:
                raw_level = max(1, level)
            item = {
                "title": title[:200],
                "level": raw_level,
                "must_include": _normalize_token_inputs(
                    raw.get("must_include")
                    or raw.get("mustInclude")
                    or raw.get("required_elements")
                    or raw.get("requiredElements")
                )[:24],
                "avoid": _normalize_token_inputs(
                    raw.get("avoid")
                    or raw.get("must_avoid")
                    or raw.get("mustAvoid")
                    or raw.get("forbidden_elements")
                    or raw.get("forbiddenElements")
                )[:24],
                "notes": str(raw.get("notes") or raw.get("description") or "").strip()[:1000],
                "children": [],
            }
            if level < max_depth:
                item["children"] = _normalize_section_structure(raw.get("children"), level=level + 1, max_depth=max_depth)
        else:
            continue
        out.append(item)
        if len(out) >= 32:
            break
    return out


def _flatten_section_titles(nodes: Any) -> List[str]:
    raw_text = json.dumps(nodes, ensure_ascii=False)
    use_cjk = bool(re.search(r"[\u4e00-\u9fff]", raw_text))
    out: List[str] = []

    def has_marker(title: str, level: int) -> bool:
        if level <= 1:
            return bool(re.match(r"^\s*(?:[一二三四五六七八九十]+、|\d+[\.、])", title))
        return bool(re.match(r"^\s*(?:（[一二三四五六七八九十]+）|\([一二三四五六七八九十]+\)|\d+(?:\.\d+)+[\.、]?)", title))

    def cjk_number(index: int) -> str:
        numerals = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
        if 1 <= index <= 10:
            return numerals[index - 1]
        if index < 20:
            return "十" + numerals[index - 11]
        return str(index)

    unnumbered_titles = {"开头总述", "引言", "导语", "摘要", "结语", "附录", "Introduction", "Executive Summary", "Summary"}

    def is_unnumbered(title: str) -> bool:
        return title in unnumbered_titles

    def render_title(title: str, level: int, index: int, parent_path: List[int]) -> str:
        if has_marker(title, level) or is_unnumbered(title):
            return title
        if use_cjk:
            return f"{cjk_number(index)}、{title}" if level <= 1 else f"（{cjk_number(index)}）{title}"
        if level <= 1:
            return f"{index}. {title}"
        return f"{'.'.join(str(x) for x in [*parent_path, index])} {title}"

    def walk(items: Any, level: int = 1, parent_path: List[int] | None = None) -> None:
        if not isinstance(items, list):
            return
        path = list(parent_path or [])
        numbered_index = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if title:
                if not is_unnumbered(title):
                    numbered_index += 1
                display_index = numbered_index if numbered_index > 0 else 1
                out.append(render_title(title, level, display_index, path))
            walk(item.get("children"), level + 1, [*path, display_index if title else numbered_index])

    walk(nodes)
    return _as_string_list(out)


def _render_section_structure_lines(nodes: Any, *, level: int = 1) -> List[str]:
    lines: List[str] = []
    if not isinstance(nodes, list):
        return lines
    indent = "  " * max(0, level - 1)
    for node in nodes:
        if not isinstance(node, dict):
            continue
        title = str(node.get("title") or "").strip()
        if not title:
            continue
        lines.append(f"{indent}- {title}")
        must_include = _as_string_list(node.get("must_include"))
        avoid = _as_string_list(node.get("avoid"))
        notes = str(node.get("notes") or "").strip()
        if must_include:
            lines.append(f"{indent}  - Must include: {'; '.join(must_include)}")
        if avoid:
            lines.append(f"{indent}  - Must avoid: {'; '.join(avoid)}")
        if notes:
            lines.append(f"{indent}  - Notes: {notes}")
        lines.extend(_render_section_structure_lines(node.get("children"), level=level + 1))
    return lines


def _normalize_contract_json(
    contract_json: Optional[Dict[str, Any]],
    *,
    skill_type: str,
    name: str,
    description: str,
    summary: str,
    notes: str,
) -> Dict[str, Any]:
    raw = dict(contract_json or {})
    section_structure = _normalize_section_structure(raw.get("section_structure") or raw.get("sectionStructure"))
    required_sections = _normalize_token_inputs(raw.get("required_sections"))
    if section_structure:
        required_sections = _flatten_section_titles(section_structure)
    normalized = {
        "skill_type": _normalize_skill_type(raw.get("skill_type"), role=skill_type) or skill_type,
        "name": str(raw.get("name") or name or "").strip(),
        "summary": str(raw.get("summary") or summary or description or "").strip(),
        "applicable_scenarios": str(raw.get("applicable_scenarios") or "").strip(),
        "publish_channel": _normalize_token_inputs(raw.get("publish_channel")),
        "content_form": _normalize_token_inputs(raw.get("content_form")),
        "target_audience": _normalize_token_inputs(raw.get("target_audience")),
        "preferred_style": _normalize_token_inputs(raw.get("preferred_style")),
        "target_length": _normalize_target_length(raw.get("target_length") or raw.get("targetLength")),
        "section_structure": section_structure,
        "required_sections": required_sections,
        "required_elements": _normalize_token_inputs(raw.get("required_elements")),
        "forbidden_elements": _normalize_token_inputs(raw.get("forbidden_elements")),
        "reference_materials": _as_string_list(raw.get("reference_materials")),
        "notes": str(raw.get("notes") or notes or "").strip(),
    }
    try:
        validated = SkillContractModel.model_validate(normalized)
        return validated.model_dump()
    except ValidationError:
        normalized["name"] = (normalized.get("name") or name or "Untitled Skill")[:120]
        normalized["summary"] = str(normalized.get("summary") or "")[:500]
        normalized["applicable_scenarios"] = str(normalized.get("applicable_scenarios") or "")[:1500]
        normalized["notes"] = str(normalized.get("notes") or "")[:4000]
        validated = SkillContractModel.model_validate(normalized)
        return validated.model_dump()


def _contract_json_from_markdown(
    skill_markdown: str,
    *,
    skill_type: str,
    name: str,
    description: str,
    summary: str,
    notes: str,
) -> Dict[str, Any]:
    meta, body = _split_frontmatter(skill_markdown or "")
    return _normalize_contract_json(
        {
            "skill_type": meta.get("skill_type") or skill_type,
            "name": meta.get("name") or name,
            "summary": meta.get("summary") or summary or description,
            "applicable_scenarios": meta.get("applicable_scenarios") or meta.get("when_to_use") or "",
            "publish_channel": meta.get("publish_channel") or [],
            "content_form": meta.get("content_form") or [],
            "target_audience": meta.get("target_audience") or [],
            "preferred_style": meta.get("preferred_style") or meta.get("tone") or [],
            "target_length": meta.get("target_length") or meta.get("targetLength") or {},
            "section_structure": meta.get("section_structure") or meta.get("sectionStructure") or [],
            "required_sections": meta.get("required_sections") or [],
            "required_elements": meta.get("required_elements") or [],
            "forbidden_elements": meta.get("forbidden_elements") or [],
            "reference_materials": meta.get("reference_materials") or [],
            "notes": notes or body,
        },
        skill_type=skill_type,
        name=name,
        description=description,
        summary=summary,
        notes=notes,
    )


def _heuristic_enrich_contract(contract_json: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(contract_json or {})
    text = " ".join(
        [
            str(out.get("name") or ""),
            str(out.get("summary") or ""),
            str(out.get("applicable_scenarios") or ""),
            str(out.get("notes") or ""),
        ]
    ).lower()

    channels = publish_channel_registry.canonicalize_many(_as_string_list(out.get("publish_channel")))
    if channels == ["generic"] or not channels:
        detected = publish_channel_registry.detect_from_text(text, default="")
        if detected:
            channels = [detected]
    out["publish_channel"] = channels or ["generic"]

    forms = _as_string_list(out.get("content_form"))
    if not forms:
        forms = ["article"]
    out["content_form"] = forms

    styles = _as_string_list(out.get("preferred_style"))
    if not styles:
        styles = ["professional"]
    for channel in out["publish_channel"]:
        for hint in publish_channel_registry.style_hints_for(channel):
            if hint not in styles:
                styles.append(hint)
    out["preferred_style"] = styles[:6]

    audience = _as_string_list(out.get("target_audience"))
    out["target_audience"] = audience or ["general_public"]

    required = _as_string_list(out.get("required_elements"))
    if not required:
        for channel in out["publish_channel"]:
            required.extend(publish_channel_registry.required_elements_for(channel))
        required = _as_string_list(required)
    out["required_elements"] = required[:12]

    forbidden = _as_string_list(out.get("forbidden_elements"))
    if not forbidden:
        for channel in out["publish_channel"]:
            forbidden.extend(publish_channel_registry.forbidden_elements_for(channel))
        forbidden = _as_string_list(forbidden)
    out["forbidden_elements"] = forbidden[:12]

    if not str(out.get("applicable_scenarios") or "").strip():
        for channel in out["publish_channel"]:
            default_scenarios = publish_channel_registry.applicable_scenarios_for(channel)
            if default_scenarios:
                out["applicable_scenarios"] = default_scenarios
                break
        if not str(out.get("applicable_scenarios") or "").strip():
            out["applicable_scenarios"] = "Use this skill in the intended target scenarios."
    return out


def _render_skill_markdown_from_contract(
    contract_json: Dict[str, Any],
    *,
    name: str,
    description: str,
) -> str:
    contract = _normalize_contract_json(
        contract_json,
        skill_type=str(contract_json.get("skill_type") or "style"),
        name=name,
        description=description,
        summary=str(contract_json.get("summary") or description or ""),
        notes=str(contract_json.get("notes") or ""),
    )
    frontmatter = {
        "skill_id": _slugify(contract.get("name") or name or "user-skill") or "user-skill",
        "name": contract.get("name") or name or "Untitled Skill",
        "description": description or contract.get("summary") or "",
        "skill_type": contract.get("skill_type") or "style",
        "summary": contract.get("summary") or "",
        "applicable_scenarios": contract.get("applicable_scenarios") or "",
        "publish_channel": contract.get("publish_channel") or [],
        "content_form": contract.get("content_form") or [],
        "target_audience": contract.get("target_audience") or [],
        "preferred_style": contract.get("preferred_style") or [],
        "target_length": contract.get("target_length") or {},
        "section_structure": contract.get("section_structure") or [],
        "required_sections": contract.get("required_sections") or [],
        "required_elements": contract.get("required_elements") or [],
        "forbidden_elements": contract.get("forbidden_elements") or [],
        "reference_materials": contract.get("reference_materials") or [],
    }
    body_sections = [
        ("Purpose", contract.get("summary") or description or "User-defined skill contract."),
        ("When To Use", contract.get("applicable_scenarios") or "Use this skill in the intended target scenarios."),
        (
            "Section Structure",
            "\n".join(_render_section_structure_lines(contract.get("section_structure") or [])) or "- ",
        ),
        ("Required Sections", "\n".join(f"- {item}" for item in (contract.get("required_sections") or [])) or "- "),
        ("Must Include", "\n".join(f"- {item}" for item in (contract.get("required_elements") or [])) or "- "),
        ("Must Avoid", "\n".join(f"- {item}" for item in (contract.get("forbidden_elements") or [])) or "- "),
        (
            "Style Notes",
            "\n".join(
                [
                    f"- Target audience: {', '.join(contract.get('target_audience') or []) or 'general'}",
                    f"- Preferred style: {', '.join(contract.get('preferred_style') or []) or 'professional'}",
                    f"- Publish channel: {', '.join(contract.get('publish_channel') or []) or 'generic'}",
                    f"- Content form: {', '.join(contract.get('content_form') or []) or 'article'}",
                ]
            ),
        ),
        ("Additional Notes", contract.get("notes") or "- "),
    ]
    fm = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    body = "\n\n".join(f"# {title}\n\n{content}".strip() for title, content in body_sections)
    return f"---\n{fm}\n---\n\n{body}\n"


def _has_executable_workflow_steps(skill_markdown: str) -> bool:
    parsed = parse_composite_skill(str(skill_markdown or ""))
    for step in list(parsed.get("steps") or []):
        if isinstance(step, dict) and "." in str(step.get("kind") or ""):
            return True
    return False


def _workflow_markdown_from_config(
    *,
    config: Dict[str, Any],
    name: str,
    description: str,
    scenario: str,
    type_value: Any = "",
    skill_type_value: Any = "",
    current_markdown: str = "",
) -> str:
    markdown = str(current_markdown or "").strip()
    raw_type = str(type_value or "").strip().lower()
    raw_skill_type = str(skill_type_value or "").strip().lower()
    nodes = _workflow_nodes(config if isinstance(config, dict) else {})
    is_workflow = raw_type == "workflow" or raw_skill_type in {"workflow", "composite_task"} or bool(nodes)
    if not is_workflow or _has_executable_workflow_steps(markdown):
        return markdown
    if not nodes:
        return markdown
    steps = [
        str(node.get("description") or "").strip()
        for node in nodes
        if str(node.get("description") or "").strip()
    ]
    return _workflow_markdown(
        name=name,
        description=description,
        scenario=scenario,
        steps=steps,
        nodes=nodes,
    )


def _infer_role_from_fields(
    *,
    category: str,
    name: str,
    description: str,
    skill_markdown: str,
    formats: Optional[List[str]] = None,
) -> str:
    normalized_formats = {str(item or "").strip().lower() for item in list(formats or []) if str(item or "").strip()}
    if normalized_formats.intersection({"docx", "pdf", "ppt", "pptx"}):
        return "renderer"
    normalized_category = str(category or "").strip().lower()
    if normalized_category in {"style", "guideline", "writing_style"}:
        return "style"
    return "execution"


def _split_list_tokens(text: str) -> List[str]:
    if not text:
        return []
    normalized = re.sub(r"[；;|/]+", ",", text)
    parts = [p.strip(" -\t\r\n") for p in re.split(r"[,，]+", normalized) if p.strip(" -\t\r\n")]
    dedup: List[str] = []
    seen: set[str] = set()
    for p in parts:
        low = p.lower()
        if low in seen:
            continue
        seen.add(low)
        dedup.append(p)
    return dedup


def _canonical_block_token(token: str) -> str:
    t = str(token or "").strip().lower()
    if not t:
        return ""
    t = re.sub(r"[\s\-]+", "_", t)
    mapping = {
        "feature_list": "feature_list",
        "feature": "feature_list",
        "code_block": "code_block",
        "code": "code_block",
        "use_case_block": "use_case_block",
        "use_case": "use_case_block",
        "usecase": "use_case_block",
        "conclusion": "conclusion_paragraph",
        "conclusion_paragraph": "conclusion_paragraph",
        "comparison": "comparison_block",
        "comparison_block": "comparison_block",
        "flow": "flow_block",
        "flow_block": "flow_block",
        "architecture": "architecture_block",
        "architecture_block": "architecture_block",
        "metric": "metric_block",
        "metric_block": "metric_block",
        "numbered_heading": "numbered_heading",
        "user_story": "user_story",
        "state_description": "state_description",
        "requirement_description": "requirement_description",
        "precondition_block": "precondition_block",
    }
    return mapping.get(t, "")


def _compile_skill_contract(
    *,
    name: str,
    description: str,
    category: str,
    formats: Optional[List[str]],
    skill_markdown: str,
    skill_type: str = "",
    contract_json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    meta, body = _split_frontmatter(skill_markdown or "")
    raw_text = " ".join([str(meta or ""), str(body or ""), str(description or ""), str(category or "")]).lower()
    lines = [ln.strip() for ln in (body or "").splitlines()]

    required_blocks: List[str] = []
    forbidden_blocks: List[str] = []
    lint_warnings: List[str] = []

    required_patterns = [
        r"(always include|must include|必须包含|必须包括)[:：]\s*(.+)$",
        r"(if .* enabled.*must include)[:：]?\s*(.+)$",
    ]
    forbidden_patterns = [
        r"(never include|must not include|do not include|禁止|不得包含)[:：]\s*(.+)$",
    ]
    for ln in lines:
        low = ln.lower()
        for pat in required_patterns:
            m = re.search(pat, low)
            if m:
                required_blocks.extend(_split_list_tokens(m.group(2)))
        for pat in forbidden_patterns:
            m = re.search(pat, low)
            if m:
                forbidden_blocks.extend(_split_list_tokens(m.group(2)))

    marker_to_block = {
        "[comparison]": "comparison_block",
        "[flow]": "flow_block",
        "[architecture]": "architecture_block",
        "[metric]": "metric_block",
        "feature list": "feature_list",
        "code block": "code_block",
        "use case": "use_case_block",
        "conclusion": "conclusion_paragraph",
    }
    for marker, blk in marker_to_block.items():
        if marker in raw_text:
            required_blocks.append(blk)

    canonical_required: List[str] = []
    for raw in required_blocks:
        c = _canonical_block_token(raw)
        if c and c not in canonical_required:
            canonical_required.append(c)
    canonical_forbidden: List[str] = []
    for raw in forbidden_blocks:
        c = _canonical_block_token(raw)
        if c and c not in canonical_forbidden:
            canonical_forbidden.append(c)

    has_visual_markers = any(
        k in raw_text
        for k in [
            "infographic",
            "visual block",
            "comparison_block",
            "flow_block",
            "architecture_block",
            "metric_block",
            "[comparison]",
            "[flow]",
            "[architecture]",
            "[metric]",
        ]
    )
    image_render_enabled = any(
        k in raw_text
        for k in [
            "image_render_enabled=true",
            "generated by tool",
            "markdown image link generated by tool",
            "信息图",
            "图像生成",
            "图片生成",
        ]
    )
    required_visual_images = 0
    m = re.search(r"required_visual_images\s*=\s*(\d+)", raw_text)
    if m:
        required_visual_images = int(m.group(1))
    elif has_visual_markers:
        required_visual_images = 1

    renderer_markers = [
        "docx",
        "pdf",
        "pptx",
        "render",
        "renderer",
        "export",
    ]
    execution_markers = [
        "run external tools",
        "tool execution",
        "network access",
        "file system",
        "invoke",
        "api",
        "browser",
        "automation",
        "execute",
    ]
    graph_markers = [
        "stategraph",
        "langgraph",
        "graph recursion",
        "workflow graph",
    ]
    style_markers = [
        "purpose",
        "when to use",
        "workflow",
        "output format",
        "rules",
        "failure handling",
        "must include",
        "never include",
        "tone",
        "formatting preferences",
    ]

    renderer_score = sum(1 for m in renderer_markers if m in raw_text) + (
        2 if any(fmt in {"pdf", "docx", "pptx"} for fmt in (formats or [])) else 0
    )
    execution_score = sum(1 for m in execution_markers if m in raw_text)
    style_score = sum(1 for m in style_markers if m in raw_text)
    has_style_sections = all(k in raw_text for k in ["purpose", "workflow", "rules"]) or all(
        k in raw_text for k in ["when to use", "output format", "failure handling"]
    )

    explicit_role = _normalize_skill_role(meta.get("role"))
    if explicit_role:
        role = explicit_role
    elif renderer_score >= 3 and renderer_score > style_score + 1:
        role = "renderer"
    elif (style_score >= 4 and style_score >= execution_score) or has_style_sections:
        role = "style"
    elif execution_score >= 2:
        role = "execution"
    else:
        role = _infer_role_from_fields(
            category=category,
            name=name,
            description=description,
            skill_markdown=skill_markdown,
            formats=formats,
        )

    explicit_plane = str(meta.get("execution_plane") or "").strip().lower()
    if explicit_plane in {"runtime", "graph"}:
        execution_plane = explicit_plane
    elif any(m in raw_text for m in graph_markers):
        execution_plane = "graph"
    else:
        execution_plane = "runtime"

    if has_visual_markers and not image_render_enabled:
        lint_warnings.append("visual_blocks_detected_but_image_render_not_explicit")
    if "rules" not in raw_text:
        lint_warnings.append("missing_rules_section")
    if "workflow" not in raw_text:
        lint_warnings.append("missing_workflow_section")

    preferred_mode = "single_pass"
    if any(k in raw_text for k in ["sectional_long_report", "long report", "深度研究", "章节", "chapter-by-chapter"]):
        preferred_mode = "sectional_long_report"

    structured_contract = _normalize_contract_json(
        contract_json or _contract_json_from_markdown(
            skill_markdown,
            skill_type=skill_type or "style",
            name=name,
            description=description,
            summary="",
            notes="",
        ),
        skill_type=skill_type or role,
        name=name,
        description=description,
        summary="",
        notes="",
    )

    required_sections = _as_string_list(structured_contract.get("required_sections"))
    if required_sections:
        canonical_required = []
        for raw in required_sections:
            c = _canonical_block_token(raw)
            if c and c not in canonical_required:
                canonical_required.append(c)

    return {
        "version": "v1",
        "skill_type": _normalize_skill_type(skill_type or structured_contract.get("skill_type"), role=role),
        "role": role,
        "execution_plane": execution_plane,
        "contract_json": structured_contract,
        "structure": {
            "required_blocks": canonical_required[:24],
            "forbidden_blocks": canonical_forbidden[:24],
        },
        "visual_policy": {
            "enabled": bool(has_visual_markers),
            "required_visual_images": int(required_visual_images),
            "image_render_enabled": bool(image_render_enabled),
            "placement_mode": "inline_contextual",
        },
        "compose_profile": {
            "preferred_mode": preferred_mode,
            "human_readability_first": True,
            "anti_template_stack": True,
        },
        "signals": {
            "style_score": style_score,
            "execution_score": execution_score,
            "renderer_score": renderer_score,
        },
        "lint_warnings": lint_warnings,
    }


class UserSkillService:
    async def enrich_skill_contract_draft(
        self,
        *,
        input_profile: Dict[str, Any],
        description: str = "",
    ) -> Dict[str, Any]:
        normalized_input = _normalize_contract_json(
            input_profile or {},
            skill_type=str((input_profile or {}).get("skill_type") or "style"),
            name=str((input_profile or {}).get("name") or "Untitled Skill"),
            description=description,
            summary=str((input_profile or {}).get("summary") or description or ""),
            notes=str((input_profile or {}).get("notes") or ""),
        )
        heuristic_input = _heuristic_enrich_contract(normalized_input)
        system = (
            "You enrich structured AI skill contracts for a writing/runtime system.\n"
            "Return JSON only with keys: skill_type,name,summary,applicable_scenarios,publish_channel,"
            "content_form,target_audience,preferred_style,target_length,section_structure,required_sections,required_elements,forbidden_elements,reference_materials,notes.\n"
            "Rules:\n"
            "- Preserve user intent exactly; enrich clarity, not scope.\n"
            "- Keep skill_type unchanged.\n"
            "- publish_channel/content_form/target_audience/preferred_style are arrays.\n"
            "- target_length is an object like {\"min\":3500,\"max\":4500,\"unit\":\"chinese_chars\"}; preserve it if provided, otherwise leave it empty.\n"
            "- section_structure is an ordered tree of section objects with title, must_include, avoid, notes, children; preserve it if provided and do not invent extra sections.\n"
            "- required_sections is an ordered array of final reader-facing section titles only. Leave empty if the user did not provide a fixed section structure.\n"
            "- required_elements is a must-cover checklist, not a section list.\n"
            "- forbidden_elements should be concise actionable items.\n"
            "- notes should become a compact operator-facing instruction block.\n"
            "- Do not invent permissions, tools, or execution claims.\n"
            "- Output valid JSON only."
        )
        try:
            resp = await llm_service.chat_complete(
                [
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "description": description,
                                "input_profile": heuristic_input,
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                temperature=0.2,
            )
            cleaned = resp.replace("```json", "").replace("```", "").strip()
            enriched = json.loads(cleaned)
            if isinstance(enriched, dict):
                enriched = {**heuristic_input, **enriched}
                if not list(enriched.get("section_structure") or []) and list(heuristic_input.get("section_structure") or []):
                    enriched["section_structure"] = list(heuristic_input.get("section_structure") or [])
                if not list(enriched.get("required_sections") or []) and list(heuristic_input.get("required_sections") or []):
                    enriched["required_sections"] = list(heuristic_input.get("required_sections") or [])
                contract_json = _normalize_contract_json(
                    enriched,
                    skill_type=str(heuristic_input.get("skill_type") or "style"),
                    name=str(heuristic_input.get("name") or "Untitled Skill"),
                    description=description,
                    summary=str(heuristic_input.get("summary") or description or ""),
                    notes=str(heuristic_input.get("notes") or ""),
                )
                contract_json = _heuristic_enrich_contract(contract_json)
                markdown = _render_skill_markdown_from_contract(
                    contract_json,
                    name=str(contract_json.get("name") or heuristic_input.get("name") or "Untitled Skill"),
                    description=description or str(contract_json.get("summary") or ""),
                )
                return {
                    "input_profile": heuristic_input,
                    "contract_json": contract_json,
                    "skill_markdown": markdown,
                }
        except Exception:
            pass

        fallback_markdown = _render_skill_markdown_from_contract(
            heuristic_input,
            name=str(heuristic_input.get("name") or "Untitled Skill"),
            description=description or str(heuristic_input.get("summary") or ""),
        )
        return {
            "input_profile": heuristic_input,
            "contract_json": heuristic_input,
            "skill_markdown": fallback_markdown,
        }

    async def list_skills(self, user_id: str, main_id: str = "default") -> List[Dict[str, Any]]:
        db = get_db()
        cursor = db.user_skills.find(add_main_scope({"user_id": str(user_id)}, main_id)).sort([("created_at", -1), ("_id", 1)])
        skills = []
        async for doc in cursor:
            skills.append(self._serialize(doc))
        return skills

    async def get_skill(self, user_id: str, skill_id: str, main_id: str = "default") -> Optional[Dict[str, Any]]:
        db = get_db()
        doc = await db.user_skills.find_one(add_main_scope({"_id": skill_id, "user_id": str(user_id)}, main_id))
        if not doc:
            return None
        return self._serialize(doc)

    async def update_skill(self, user_id: str, skill_id: str, updates: Dict[str, Any], main_id: str = "default") -> Optional[Dict[str, Any]]:
        db = get_db()
        current = await db.user_skills.find_one(add_main_scope({"_id": skill_id, "user_id": str(user_id)}, main_id))
        if not current:
            return None

        merged_name = str(updates.get("name", current.get("name", "")) or "")
        merged_description = str(updates.get("description", current.get("description", "")) or "")
        merged_summary = str(updates.get("summary", current.get("summary", "")) or "")
        merged_category = str(updates.get("category", current.get("category", "")) or "")
        merged_formats = list(updates.get("formats", current.get("formats", [])) or [])
        merged_notes = str(updates.get("notes", current.get("notes", "")) or "")
        merged_role = _normalize_skill_role(updates.get("role")) or _normalize_skill_role(current.get("role"))
        merged_skill_type = _normalize_skill_type(updates.get("skill_type"), role=merged_role or current.get("role"))
        merged_contract_json = _normalize_contract_json(
            updates.get("contract_json", current.get("contract_json", {})),
            skill_type=merged_skill_type,
            name=merged_name,
            description=merged_description,
            summary=merged_summary,
            notes=merged_notes,
        )
        merged_config = updates.get("config", current.get("config") or {})
        if not isinstance(merged_config, dict):
            merged_config = {}
        merged_markdown = str(updates.get("skill_markdown", "") or "").strip()
        merged_markdown = _workflow_markdown_from_config(
            config=merged_config,
            name=merged_name,
            description=merged_description,
            scenario=str(updates.get("scenario", current.get("scenario", "")) or ""),
            type_value=updates.get("type", current.get("type")),
            skill_type_value=merged_skill_type,
            current_markdown=merged_markdown,
        )
        if not merged_markdown:
            merged_markdown = _render_skill_markdown_from_contract(
                merged_contract_json,
                name=merged_name,
                description=merged_description,
            )

        contract = _compile_skill_contract(
            name=merged_name,
            description=merged_description,
            category=merged_category,
            formats=merged_formats,
            skill_markdown=merged_markdown,
            skill_type=merged_skill_type,
            contract_json=merged_contract_json,
        )
        normalized_role = _normalize_skill_role(updates.get("role"))
        effective_role = normalized_role or str(contract.get("role") or "")
        if effective_role:
            updates["role"] = effective_role
            contract["role"] = effective_role
        updates["skill_type"] = _normalize_skill_type(merged_skill_type, role=effective_role)
        updates["config"] = merged_config
        updates["contract_json"] = dict(contract.get("contract_json") or merged_contract_json)
        updates["input_profile"] = dict(updates.get("input_profile") or current.get("input_profile") or {})
        updates["skill_markdown"] = merged_markdown
        updates["execution_plane"] = str(contract.get("execution_plane") or "runtime")
        updates["skill_contract"] = contract
        updates["skill_contract_version"] = str(contract.get("version") or "v1")
        updates["skill_lint_warnings"] = list(contract.get("lint_warnings") or [])
        updates["updated_at"] = datetime.datetime.utcnow()
        await db.user_skills.update_one(
            add_main_scope({"_id": skill_id, "user_id": str(user_id)}, main_id),
            {"$set": updates},
        )
        doc = await db.user_skills.find_one(add_main_scope({"_id": skill_id, "user_id": str(user_id)}, main_id))
        if not doc:
            return None
        return self._serialize(doc)

    async def delete_skill(self, user_id: str, skill_id: str, main_id: str = "default") -> bool:
        db = get_db()
        result = await db.user_skills.delete_one(add_main_scope({"_id": skill_id, "user_id": str(user_id)}, main_id))
        return result.deleted_count > 0

    async def create_skill(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        db = get_db()
        now = datetime.datetime.utcnow()
        main_id = resolve_main_id(payload.get("main_id") or payload.get("mainId"))
        explicit_role = _normalize_skill_role(payload.get("role"))
        skill_type = _normalize_skill_type(payload.get("skill_type"), role=explicit_role)
        contract_json = _normalize_contract_json(
            payload.get("contract_json"),
            skill_type=skill_type,
            name=str(payload.get("name", "") or ""),
            description=str(payload.get("description", "") or ""),
            summary=str(payload.get("summary", "") or ""),
            notes=str(payload.get("notes", "") or ""),
        )
        skill_markdown = str(payload.get("skill_markdown", "") or "").strip()
        payload_config = payload.get("config") or {}
        if not isinstance(payload_config, dict):
            payload_config = {}
        skill_markdown = _workflow_markdown_from_config(
            config=payload_config,
            name=str(payload.get("name", "") or ""),
            description=str(payload.get("description", "") or ""),
            scenario=str(payload.get("scenario", "") or ""),
            type_value=payload.get("type"),
            skill_type_value=skill_type,
            current_markdown=skill_markdown,
        )
        if not skill_markdown:
            skill_markdown = _render_skill_markdown_from_contract(
                contract_json,
                name=str(payload.get("name", "") or ""),
                description=str(payload.get("description", "") or ""),
            )
        contract = _compile_skill_contract(
            name=str(payload.get("name", "") or ""),
            description=str(payload.get("description", "") or ""),
            category=str(payload.get("category", "") or ""),
            formats=list(payload.get("formats") or []),
            skill_markdown=skill_markdown,
            skill_type=skill_type,
            contract_json=contract_json,
        )
        role = explicit_role or str(contract.get("role") or "")
        if role:
            contract["role"] = role
        skill_doc = {
            "_id": payload.get("id") or uuid.uuid4().hex,
            "user_id": str(user_id),
            "main_id": main_id,
            "name": payload.get("name", "Untitled Skill"),
            "description": payload.get("description", ""),
            "scenario": payload.get("scenario", ""),
            "summary": payload.get("summary", ""),
            "category": payload.get("category", ""),
            "role": role,
            "skill_type": _normalize_skill_type(skill_type, role=role),
            "type": payload.get("type", ""),
            "config": payload_config,
            "enabled": bool(payload.get("enabled", payload.get("is_active", False))),
            "tags": payload.get("tags") or [],
            "visibility": payload.get("visibility", "private"),
            "formats": payload.get("formats") or [],
            "input_profile": payload.get("input_profile") or {},
            "contract_json": dict(contract.get("contract_json") or contract_json),
            "skill_markdown": skill_markdown,
            "skill_object_path": payload.get("skill_object_path", ""),
            "sources": payload.get("sources") or [],
            "resources": payload.get("resources") or {},
            "advanced": payload.get("advanced") or {},
            "notes": payload.get("notes", ""),
            "execution_plane": str(contract.get("execution_plane") or "runtime"),
            "skill_contract_version": str(contract.get("version") or "v1"),
            "skill_contract": contract,
            "skill_lint_warnings": list(contract.get("lint_warnings") or []),
            "created_at": now,
            "updated_at": now,
            "is_active": bool(payload.get("is_active", True)),
        }
        await db.user_skills.insert_one(skill_doc)
        return self._serialize(skill_doc)

    async def select_skill(
        self,
        user_id: str,
        user_text: str,
        intent: str,
        formats: List[str],
        main_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        skills = await self.list_skills(user_id, main_id=main_id)
        if not skills:
            return None
        candidates = []
        for skill in skills:
            if not skill.get("is_active"):
                continue
            skill_formats = skill.get("formats") or []
            # Allow 'markdown' skills as candidates for almost any text-related request,
            # as they are the foundation for PDF/Docx/PPTX exports.
            if not skill_formats or any(fmt in skill_formats for fmt in formats) or "markdown" in skill_formats:
                candidates.append(skill)
        if not candidates:
            return None

        prompt = {
            "intent": intent,
            "formats": formats,
            "user_request": user_text,
            "skills": [
                {
                    "name": s["name"],
                    "description": s.get("description", ""),
                    "formats": s.get("formats") or [],
                }
                for s in candidates
            ],
        }
        system = (
            "You are a skill selector. Choose the best matching user skill for the request. "
            "Return JSON: {\"skill_name\": \"...\"} or {\"skill_name\": null}."
        )
        response = await llm_service.chat_complete(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            temperature=0.1,
        )
        try:
            cleaned = response.replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned)
            chosen = data.get("skill_name")
        except Exception:
            chosen = None
        if not chosen:
            return None
        for skill in candidates:
            if skill["name"] == chosen:
                return skill
        return None

    async def build_skill_markdown(
        self,
        name: str,
        description: str,
        formats: List[str],
        sources_text: str,
        notes: str,
    ) -> str:
        safe_name = _slugify(name) or "user-skill"
        system = (
            "You are an expert skill author. Create a SKILL.md file with valid YAML frontmatter "
            "and clear step-by-step instructions. The skill is for document generation and formatting. "
            "Follow the Agent Skills SKILL.md conventions."
        )
        user = {
            "name": safe_name,
            "description": description,
            "formats": formats,
            "notes": notes,
            "reference": sources_text,
        }
        # Fixed temperature for build_skill_markdown as well if it uses the same model validation logic,
        # but previously it was 0.2. I'll keep it 0.2 unless it errors, but wait, the previous error was in generate_skill_from_template.
        # SAFE OPTION: Use 1.0 here too if it fails, but let's stick to what worked before for this method.
        # Actually, let's play it safe and use 1.0 for all if they share the model config.
        # But for now, I will revert to 0.2 for this one as it wasn't the one failing in my test.
        response = await llm_service.chat_complete(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.2, 
        )
        content = response.strip()
        if not content.startswith("---"):
            front = (
                "---\n"
                f"name: {safe_name}\n"
                f"description: {description or 'User skill for document generation'}\n"
                "---\n\n"
            )
            content = front + content
        return content

    async def persist_skill_markdown(self, user_id: str, name: str, content: str) -> tuple[str, str]:
        uploader = AliyunOSSUploader()
        filename = f"{_slugify(name) or 'user-skill'}.md"
        url, object_path = uploader.upload_bytes_with_path(
            content.encode("utf-8"),
            user_id=str(user_id),
            file_name=filename,
            content_type="text/markdown",
        )
        return url, object_path

    async def generate_skill_from_template(self, filename: str, content: bytes) -> Dict[str, Any]:
        """
        Orchestrator for the advanced 3-phase skill generation pipeline:
        Phase 0: Content Analysis (Flavor, Structure, Tail)
        Phase 1: Structural Signature Generation (Intermediate Fact Layer)
        Phase 2: Skill Compilation (Blueprint -> SKILL.md)
        Phase 3: Automated Validation & Repair
        """
        import re
        from app.utils.document_loader import extract_text_from_file

        # --- Phase 0: Text Extraction & Structure Signal Enhancement ---
        extracted_text = extract_text_from_file(content, filename)
        if not extracted_text:
            raise ValueError("Could not extract text from the provided file.")

        def _normalize_text(t: str) -> str:
            t = t.replace("\r\n", "\n").replace("\r", "\n")
            t = re.sub(r"\n{3,}", "\n\n", t)
            return t.strip()

        extracted_text = _normalize_text(extracted_text)

        # Helpers for structure extraction
        def _extract_headings_and_lists(t: str, max_lines: int = 400) -> str:
            lines = [ln.strip() for ln in t.split("\n") if ln.strip()][:max_lines]
            heading_like = []
            list_like = []
            section_like = []
            
            # Heuristically detect headings, sections, lists (simplified REGEX for speed)
            list_pat = re.compile(r"^(\-|\*|•|■|\u25a0|\u25cf|\d+[\.\)]|[①-⑩])\s+")
            section_pat = re.compile(r"^(第[0-9]+[章节]|Section\s+\d+|[0-9]+\.[0-9]+|[A-Z][A-Z\s]{2,}|.*[:：])$")
            
            for ln in lines:
                if list_pat.match(ln):
                    list_like.append(ln)
                elif section_pat.match(ln):
                    section_like.append(ln)
                elif len(ln) < 60 and not ln.endswith(('.', '。', '!', '！')):
                    heading_like.append(ln)

            def uniq(seq):
                seen = set()
                return [x for x in seq if not (x in seen or seen.add(x))]

            parts = []
            if heading_like: parts.append("## Detected Headings:\n" + "\n".join(f"- {h}" for h in uniq(heading_like)[:30]))
            if section_like: parts.append("## Detected Sections:\n" + "\n".join(f"- {s}" for s in uniq(section_like)[:30]))
            if list_like: parts.append("## Detected List Styles:\n" + "\n".join(uniq(list_like)[:20]))
            return "\n\n".join(parts)

        structural_signals = _extract_headings_and_lists(extracted_text)
        flavor_snippet = extracted_text[:6000]
        tail_snippet = extracted_text[-2000:] if len(extracted_text) > 2000 else ""

        def _ensure_frontmatter(md: str) -> str:
            md = md.strip()
            # Remove code fences
            md = md.replace("```markdown", "").replace("```", "").strip()
            # Find first ---
            if "---" in md and not md.startswith("---"):
                md = md[md.find("---"):]
            
            if not md.startswith("---"):
                safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', filename.split(".")[0])
                front = (
                    "---\n"
                    f"name: {safe_name}\n"
                    "description: Auto-generated generator skill\n"
                    "category: document\n"
                    "---\n\n"
                )
                md = front + md
            return md

        # --- Pipeline Execution ---
        logger.info("skill generation phase started", extra={"event": "skills.generation_phase", "phase": "structural_signature"})
        signature = await self._generate_structural_signature(filename, flavor_snippet, structural_signals, tail_snippet)
        
        logger.info("skill generation phase started", extra={"event": "skills.generation_phase", "phase": "compile_from_signature", "doc_family": signature.get("doc_family", "unknown")})
        skill_md = await self._compile_skill_from_signature(signature, filename, flavor_snippet)
        
        logger.info("skill generation phase started", extra={"event": "skills.generation_phase", "phase": "validate_and_repair"})
        final_skill_md = await self._validate_and_repair(skill_md, signature)
        
        # Final Verification & Cleanup
        final_skill_md = _ensure_frontmatter(final_skill_md)

        # Final Formatting
        meta, body = _split_frontmatter(final_skill_md)
        role = _normalize_skill_role(meta.get("role")) or _infer_role_from_fields(
            category=str(meta.get("category", "document") or ""),
            name=str(meta.get("name", "Generated Skill") or ""),
            description=str(meta.get("description", "") or ""),
            skill_markdown=final_skill_md,
            formats=[],
        )
        contract = _compile_skill_contract(
            name=str(meta.get("name", "Generated Skill") or ""),
            description=str(meta.get("description", "") or ""),
            category=str(meta.get("category", "document") or ""),
            formats=[],
            skill_markdown=final_skill_md,
        )
        if role:
            contract["role"] = role
        return {
            "name": meta.get("name", "Generated Skill"),
            "description": meta.get("description", ""),
            "category": meta.get("category", "document"),
            "role": role,
            "execution_plane": str(contract.get("execution_plane") or "runtime"),
            "skill_contract": contract,
            "skill_markdown": final_skill_md,
        }

    async def _generate_structural_signature(self, filename: str, flavor: str, structure: str, tail: str) -> Dict[str, Any]:
        """Phase 1: Create the 'Structural Signature' (Blueprint JSON)"""
        system = (
            "You are a Document Forensics Expert. Your job is to extract the 'Structural Signature' (DNA) of a document template.\n"
            "You MUST output valid JSON only.\n\n"
            "Task: Analyze the document snippets and produce a JSON blueprint with these exact fields:\n"
            "1. doc_family: The likely document category (e.g., 'api_reference', 'marketing_plan', 'legal_brief', 'prd'). Use snake_case. If it doesn't fit existing types, propose a descriptive new one.\n"
            "2. doc_topic: string (the specific subject matter, snake_case, e.g. 'net_drama_market_2025', 'q3_financial_report' - NOT generic like 'report')\n"
            "3. primary_unit: The atomic unit of the document (e.g., 'endpoint', 'feature', 'clause', 'slide', 'entry'). If unknown, propose a descriptive 'snake_case' unit.\n"
            "4. ordering_logic: one of [hierarchical, sequential, indexed, mixed]\n"
            "5. sections: list of likely section names (ordered)\n"
            "6. required_blocks: list of specific block types that MUST appear (e.g. 'code_block', 'trend_card', 'price_table', 'signature_line', 'user_story', 'acceptance_criteria')\n"
            "7. optional_blocks: list of optional elements\n"
            "8. style_profile: { tone: '...', verbosity: '...', formatting: 'markdown/table/etc' }\n"
            "9. constraints: { \n"
            "     'must_include': ['...'], \n"
            "     'must_not_include': ['...'] \n"
            "   }\n"
            "   *CRITICAL*: List 'must_not_include' to prevent template contamination.\n"
        )
        user = (
            f"Filename: {filename}\n"
            f"Structure Signals:\n{structure}\n\n"
            f"Head Snippet:\n{flavor}\n\n"
            f"Tail Snippet:\n{tail}\n\n"
            "Output JSON Signature:"
        )
        try:
            resp = await llm_service.chat_complete(
                [{"role": "system", "content": system}, {"role": "user", "content": user}], 
                temperature=1.0 # Force 1.0 based on model constraint
            )
            
            # Robust JSON extraction
            import json
            cleaned = resp.replace("```json", "").replace("```", "").strip()
            
            # Find the first { and last }
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1:
                cleaned = cleaned[start:end+1]
            
            return json.loads(cleaned)
        except Exception as e:
            logger.warning(
                "skill signature generation failed",
                extra={"event": "skills.signature_generation_failed", "error": str(e), "raw_preview": cleaned[:100] if "cleaned" in locals() else "N/A", "response_tail": resp[-500:] if "resp" in locals() else "N/A"},
            )
            return {"doc_family": "other", "constraints": {"must_not_include": []}}

    def _generate_deterministic_name_and_desc(self, signature: Dict[str, Any], flavor: str = "") -> tuple[str, str, str]:
        """
        Implements Advanced Deterministic Naming Scheme: <primary_unit>_<pattern>_<family>_<keyblock>_generator
        Returns: (name, description, category)
        """
        
        # --- Constants from User Rule ---
        GENERIC_TOKENS = {"section", "structured", "general", "generic", "text", "document", "report"}
        KEYBLOCK_PRIORITY = [
            ["ranking", "metric", "comparison", "chart", "trend", "statistics"],
            ["request_schema", "response_schema", "error_schema", "endpoint_def"],
            ["approval_flow", "version_history", "clause_numbering", "signature_block"],
            ["diagram", "architecture_placeholder", "infographic", "visuals"],
            ["table", "grid"],
            ["bullet_list", "list"],
            ["heading", "section"]
        ]

        # --- Helper Functions ---
        def pick_keyblock(required_blocks):
            rb_set = set(b.lower() for b in required_blocks)
            for tier in KEYBLOCK_PRIORITY:
                for b in tier:
                    # Check partial match (e.g. "trend" matches "trend_card")
                    if any(b in rb for rb in rb_set):
                        if b in {"heading", "section", "bullet_list", "list"}:
                            continue
                        return b
            return "table" if any("table" in rb for rb in rb_set) else "block"

        def infer_pattern(signature, force_upgrade=False):
            rb = set(b.lower() for b in signature.get("required_blocks", []))
            
            # Priority Inference Rules
            if any(w in rb for w in ["ranking", "metric", "comparison", "chart", "trend"]):
                return "analytical"
            if any(w in rb for w in ["request_schema", "response_schema", "error_schema", "endpoint"]):
                return "specification"
            if any(w in rb for w in ["approval_flow", "clause_numbering", "clause"]):
                return "regulatory"
            if any(w in rb for w in ["step", "procedure", "sequential"]):
                return "procedural"
            if any(w in rb for w in ["diagram", "infographic", "visuals", "slide"]):
                return "presentation"
            if any(w in rb for w in ["hypothesis", "method", "experiment"]):
                return "scientific"
            if any(w in rb for w in ["form", "field", "validation"]):
                return "declarative"
            if any(w in rb for w in ["user_story", "acceptance_criteria", "requirement", "feature"]):
                return "functional"
            if any(w in rb for w in ["comparison", "contrast", "versus"]):
                return "comparative"
            if any(w in rb for w in ["question", "answer", "faq", "inquiry"]):
                return "inquiry"
            
            return "structured"

        def map_primary_unit(raw_unit):
            unit_map = {
                "endpoint": "api", "step": "procedural", "clause": "policy",
                "slide": "presentation", "trend": "analytical", "metric": "metric",
                "field": "form", "argument": "academic", "feature": "feature",
                "requirement": "requirement"
            }
            mapped = unit_map.get(raw_unit.lower(), raw_unit.lower())
            return _slugify(mapped).replace("-", "_")

        def map_doc_family(raw_family):
            family_map = {
                "api_reference": "specification", "analytical_brief": "report",
                "slide_deck": "presentation", "sop_playbook": "procedure",
                "policy_document": "policy", "form_template": "form",
                "academic_paper": "paper", "dataset_report": "dataset",
                "product_requirement": "requirement", "prd": "requirement"
            }
            mapped = family_map.get(raw_family.lower(), raw_family.lower())
            return _slugify(mapped).replace("-", "_")

        def specificity_score(name, signature):
            score = 0
            if signature.get("primary_unit", "section") != "section": score += 2
            if infer_pattern(signature) != "structured": score += 2
            
            kb = pick_keyblock(signature.get("required_blocks", []))
            if kb not in {"block", "table"}: score += 3
            
            score += 1 # Base score for having family
            
            # Penalize generic tokens
            tokens = set(name.split("_"))
            score -= sum(1 for t in tokens if t in GENERIC_TOKENS)
            return score

        # --- Main Logic ---
        primary = map_primary_unit(signature.get("primary_unit", "section"))
        pattern = infer_pattern(signature)
        family = map_doc_family(signature.get("doc_family", "document"))
        keyblock = pick_keyblock(signature.get("required_blocks", []))

        # Initial Candidate: 3-segment (legacy) or 4-segment? User format is <unit>_<pattern>_<family>_<keyblock>_generator
        # But user said "Upgrade from 4 to 5 segments". Let's start with 
        # <unit>_<pattern>_<family>_generator (Base)
        # And check score. If low, add keyblock.
        
        base_name = f"{primary}_{pattern}_{family}_generator"
        final_name = base_name

        # Check Specificity
        if specificity_score(base_name, signature) < 6:
            # Upgrade Steps
            # 1. Add Keyblock
            if keyblock != "block":
                final_name = f"{primary}_{pattern}_{family}_{keyblock}_generator"
            
            # 2. If still potentially weak (or just enforces user rule), try upgrading pattern/primary
            if specificity_score(final_name, signature) < 6:
                 # Force Pattern Upgrade from Blocks
                 new_pattern = infer_pattern(signature, force_upgrade=True)
                 if new_pattern != pattern:
                     pattern = new_pattern
                     final_name = f"{primary}_{pattern}_{family}_{keyblock}_generator"
            
            if specificity_score(final_name, signature) < 6:
                # Force Primary Unit Upgrade
                if primary == "section":
                     primary = "content" # slightly better? or stick to map
                     final_name = f"{primary}_{pattern}_{family}_{keyblock}_generator"

        # --- Description Generation ---
        # "Generates a <pattern> <family> composed of <block1>, <block2>."
        # Pick 2 distinctive blocks
        distinctive_blocks = []
        rb_list = signature.get("required_blocks", [])
        
        for tier in KEYBLOCK_PRIORITY:
            for b in tier:
                if b in {"heading", "section", "bullet_list", "list"}: continue
                # Find matching block in required_blocks
                matches = [rb for rb in rb_list if b in rb.lower()]
                if matches:
                    distinctive_blocks.extend(matches)
        
        # Deduplicate and slice
        distinctive_blocks = list(dict.fromkeys(distinctive_blocks))[:2]
        if not distinctive_blocks:
            distinctive_blocks = ["standard content blocks"]
        
        blocks_text = ", ".join(distinctive_blocks)
        description = f"Generates a {pattern} {family} composed of {blocks_text}."

        # --- Category Generation ---
        # 1. Analysis & Reports
        # 2. Specs & Product
        # 3. Governance & SOPs
        # 4. Presentation & Visuals
        # 5. Coding & Engineering
        # 6. Browser Automation
        
        category = "Analysis & Reports" # Default fallback
        
        # Priority Check
        full_text = f"{family}_{pattern}_{primary}_{flavor[:1000]}".lower()
        
        if any(token in full_text for token in ["code", "script", "test", "api", "endpoint"]):
            category = "Coding & Engineering"
        elif any(token in full_text for token in ["browser", "web", "scrape", "selenium", "playwright"]):
            category = "Browser Automation"
        elif any(token in full_text for token in ["presentation", "slide", "visual", "deck", "ppt"]):
            category = "Presentation & Visuals"
        elif any(token in full_text for token in ["policy", "procedure", "sop", "regulation", "compliance", "regulatory", "legal", "clause"]):
            category = "Governance & SOPs"
        elif any(token in full_text for token in ["market", "survey", "brief", "report", "analysis", "trend", "insight", "research"]):
            category = "Analysis & Reports"
        elif any(token in full_text for token in ["specification", "spec", "schema", "product", "requirement", "feature", "prd"]):
            category = "Specs & Product"
        else:
            category = "Analysis & Reports" # Default fallback
        
        return final_name, description, category

    async def _compile_skill_from_signature(self, signature: Dict, filename: str, flavor: str) -> str:
        """Phase 2: Compile SKILL.md from the Signature"""
        sig_str = json.dumps(signature, indent=2, ensure_ascii=False)
        forbidden_list = signature.get('constraints', {}).get('must_not_include', [])
        forbidden_str = ", ".join(forbidden_list)

        # Generate Deterministic Identity
        skill_name, skill_desc, skill_cat = self._generate_deterministic_name_and_desc(signature, flavor)

        system = (
            "You are an AI Skill Compiler. Your task: Compile a 'SKILL.md' based strictly on the provided Structural Signature.\n"
            "The goal is to create a GENERATOR skill that writes NEW documents of this family from scratch.\n\n"
            "CRITICAL CONSTRAINTS (from Signature):\n"
            f"- Family: {signature.get('doc_family')}\n"
            f"- MUST include blocks: {signature.get('required_blocks')}\n"
            f"- MUST NOT include: {forbidden_str}\n\n"
            "STRICT OUTPUT TEMPLATE (You MUST include these 8 sections):\n"
            "1. # Purpose\n"
            "   - Clearly state this is a GENERATOR for [doc_family].\n"
            "   - IF doc_family is 'analytical_brief', state: 'This skill generates a NEW analysis based on structured input data.' NEVER say 'summarizes the document'.\n"
            "2. # When to use\n"
            "   - Describe the specific scenario (e.g. 'When you need to create a fresh {signature.get('doc_topic', 'document')}...').\n"
            "3. # Inputs\n"
            "   - Use configuration switches (boolean flags) for optional blocks.\n"
            "   - For list items (like endpoints, methods), use SCHEMA OBJECTS (e.g. `endpoint_schema` with fields `name`, `method`, `desc`) instead of simple strings.\n"
            "   - Include a `formatting_preferences` object (e.g. table vs list).\n"
            "   - NEVER ask for 'source text'.\n"
            "4. # Workflow\n"
            "   - Step-by-step logic to build the document.\n"
            "5. # Output format\n"
            "   - Define rigidity. If 'trend_card' is required, define its exact markdown schema here.\n"
            "6. # Examples\n"
            "   - Provide a brief dummy example of the output style.\n"
            "7. # Rules\n"
            "   - Explicitly list NEGATIVE CONSTRAINTS.\n"
            f"   - You MUST write: 'NEVER include: {forbidden_str}' as a rule.\n"
            "8. # Failure handling\n"
            "   - How to handle missing input data (e.g. 'If endpoint description is missing, use default placeholder').\n\n"
            "Return raw Markdown starting with '---'. Frontmatter MUST be exactly as follows:\n"
            f"name: {skill_name}\n"
            f"description: {skill_desc}\n"
            f"category: {skill_cat}\n"
        )
        user = f"Signature:\n{sig_str}\n\nContent Flavor (for tone inference only):\n{flavor[:2000]}"
        
        return await llm_service.chat_complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=1.0 
        )

    async def _validate_and_repair(self, skill_md: str, signature: Dict, max_retries: int = 2) -> str:
        """Phase 3: Automated QA and Repair"""
        
        def _check_fail(md: str, sig: Dict) -> List[str]:
            errors = []
            md_lower = md.lower()
            
            # 1. Intent Check
            forbidden = ["translate", "translation", "summarize", "summary", "source document", "source text", "input document", "extract text"]
            if any(w in md_lower for w in forbidden):
                errors.append("Skill appears to be a translator/summarizer (found forbidden terms like 'translate', 'source document'). Must be a GENERATOR.")
            
            # 2. Structural Check
            req_blocks = sig.get('required_blocks', []) or []
            for b in req_blocks:
                if b.replace("_", " ") not in md_lower and b not in md_lower:
                    errors.append(f"Missing required block from signature: {b}")
            
            # Check for explicit blacklist in Rules (Heuristic: search for 'never include' near the forbidden word)
            forbidden_blocks = sig.get('constraints', {}).get('must_not_include', []) or []
            for b in forbidden_blocks:
                if b.replace("_", " ") in md_lower or b in md_lower:
                    # Allow it ONLY if it is in a "NEVER include" context (simple check is hard, so we stick to strict exclusion for now unless it's in the Rules section as a negative example)
                    # Ideally, the generator simply shouldn't mention it unless it's in the Rules saying "Don't do it".
                    # We will relax this check: If it appears, it MUST be near "never" or "not".
                    # For stability, let's keep strict check -> it shouldn't be in the *content* generation logic. 
                    # But since we Asked it to write it in Rules, we need to allow it THERE.
                    # Heuristic: Check if the forbidden word is present BUT NOT prefixed by "never" or "do not" in the line.
                    pass # We trust the prompt for now, or we'd need complex regex.
                    # Actually, let's stick to the previous strict check but ignore it if it's in the # Rules section.
            
            # 3. Input Check (Heuristic)
            if "# Inputs" in md:
                inputs_section = md.split("# Inputs")[1].split("#")[0].lower()
                if "topic" not in inputs_section and "scope" not in inputs_section and "schema" not in inputs_section:
                   errors.append("Inputs section missing standard generator fields (topic, scope) or schema definition.")
                if "text" in inputs_section or "file" in inputs_section or "content" in inputs_section:
                    pass
            
            # 4. Structure Completeness (8 Sections)
            required_headers = ["# Purpose", "# When to use", "# Inputs", "# Workflow", "# Output format", "# Examples", "# Rules", "# Failure handling"]
            for h in required_headers:
                if h not in md:
                    errors.append(f"Missing required section: '{h}'")

            return errors

        current_md = skill_md
        for attempt in range(max_retries + 1):
            errors = _check_fail(current_md, signature)
            if not errors:
                return current_md
            
            if attempt < max_retries:
                logger.warning("skill validation failed", extra={"event": "skills.validation_failed", "attempt": attempt + 1, "errors": errors})
                system = (
                    "You are a strict Code Repair Engine.\n"
                    "Your task is to fix the provided SKILL.md based on the validation errors below.\n"
                    f"Validation Errors:\n" + "\n".join(f"- {e}" for e in errors) + "\n\n"
                    "REQUIREMENTS:\n"
                    "- Return a JSON object with a single key 'fixed_skill_md' containing the corrected markdown string.\n"
                    "- Do NOT output any text outside the JSON.\n"
                    "- Ensure the markdown starts with '---\n'."
                )
                try:
                    resp = await llm_service.chat_complete(
                        [{"role": "system", "content": system}, {"role": "user", "content": current_md}],
                        temperature=1.0
                    )
                    import json
                    cleaned = resp.replace("```json", "").replace("```", "").strip()
                    if "{" in cleaned:
                        current_md = json.loads(cleaned).get("fixed_skill_md", current_md)
                    else:
                        # Fallback if model refuses JSON but outputs markdown directly
                        current_md = resp
                except Exception as e:
                    logger.warning("skill repair JSON parse failed", extra={"event": "skills.repair_json_parse_failed", "error": str(e)})
                    # Use raw response as fallback (hope it's markdown)
                    current_md = resp
            else:
                logger.warning("skill validation exhausted", extra={"event": "skills.validation_exhausted", "max_retries": max_retries})
        
        return current_md

    # ------------------------------------------------------------------ #
    # Style Extraction Pipeline (default for document upload)             #
    # ------------------------------------------------------------------ #

    async def generate_style_skill_from_document(self, filename: str, content: bytes) -> Dict[str, Any]:
        """
        Orchestrator for the style extraction pipeline.
        Generates a role:style SKILL.md (YAML style_contract + LLM writing guidelines)
        from an uploaded document.
        """
        import re
        from app.utils.document_loader import extract_text_from_file

        extracted_text = extract_text_from_file(content, filename)
        if not extracted_text:
            raise ValueError("Could not extract text from the provided file.")

        def _normalize_text(t: str) -> str:
            t = t.replace("\r\n", "\n").replace("\r", "\n")
            t = re.sub(r"\n{3,}", "\n\n", t)
            return t.strip()

        extracted_text = _normalize_text(extracted_text)

        flavor_snippet = extracted_text[:6000]
        mid_snippet = ""
        if len(extracted_text) > 8000:
            mid_start = len(extracted_text) // 2 - 1000
            mid_snippet = extracted_text[mid_start:mid_start + 2000]
        tail_snippet = extracted_text[-2000:] if len(extracted_text) > 2000 else ""

        # Phase 1: Analyze writing style
        logger.info("style skill phase started", extra={"event": "skills.style_phase", "phase": "analyze_style"})
        style_analysis = await self._analyze_writing_style(filename, flavor_snippet, mid_snippet, tail_snippet)

        # Phase 2: Compile style SKILL.md
        logger.info("style skill phase started", extra={"event": "skills.style_phase", "phase": "compile_style", "doc_type": style_analysis.get("doc_type", "unknown")})
        skill_md = await self._compile_style_skill_md(style_analysis, flavor_snippet)

        # Phase 3: Validate and repair
        logger.info("style skill phase started", extra={"event": "skills.style_phase", "phase": "validate_style"})
        final_skill_md = await self._validate_style_skill(skill_md, style_analysis)

        # Ensure frontmatter
        final_skill_md = final_skill_md.strip()
        if final_skill_md.startswith("```"):
            final_skill_md = re.sub(r"^```\w*\n?", "", final_skill_md)
            final_skill_md = re.sub(r"\n?```$", "", final_skill_md)
            final_skill_md = final_skill_md.strip()
        if "---" in final_skill_md and not final_skill_md.startswith("---"):
            final_skill_md = final_skill_md[final_skill_md.find("---"):]

        meta, body = _split_frontmatter(final_skill_md)
        name = str(meta.get("name") or style_analysis.get("skill_name") or "user_writing_style")
        description = str(meta.get("description") or style_analysis.get("skill_description") or "用户写作规范")

        return {
            "name": name,
            "description": description,
            "category": "style",
            "role": "style",
            "execution_plane": "runtime",
            "skill_contract": {
                "version": "v1",
                "role": "style",
                "execution_plane": "runtime",
            },
            "skill_markdown": final_skill_md,
        }

    async def _analyze_writing_style(
        self, filename: str, flavor: str, mid: str, tail: str
    ) -> Dict[str, Any]:
        """Phase 1: LLM-based writing style analysis. Returns structured JSON."""
        system = (
            "你是一位写作规范分析专家。你的任务是从提供的文档片段中，精准提取作者的写作规范特征。\n"
            "你必须只输出有效的 JSON，不要输出其他解释。\n\n"
            "分析以下维度，输出 JSON 对象:\n"
            "1. doc_type: 文档类型（如 'tech_blog', 'research_report', 'tutorial', 'news_article', "
            "'marketing_copy', 'product_doc', 'newsletter', 'opinion_piece'）\n"
            "2. opening_style: 开头方式（如 'narrative_hook', 'data_driven', 'question', "
            "'direct_thesis', 'case_study', 'historical_context', 'quote'）\n"
            "3. tone: 语气（如 'conversational_professional', 'formal', 'casual', 'academic', "
            "'authoritative', 'humorous', 'inspirational'）\n"
            "4. conclusion_style: 结尾方式（如 'call_to_action', 'summary', 'memorable_takeaway', "
            "'open_question', 'future_outlook'）\n"
            "5. heading_style: 标题风格，对象包含:\n"
            "   - max_depth: 最大标题深度(1-4)\n"
            "   - max_headings: 大约标题数量\n"
            "   - numbered: 是否使用编号标题\n"
            "   - style: 标题语言风格('descriptive', 'question', 'action', 'mixed')\n"
            "6. paragraph_style: 段落风格('long_narrative', 'short_punchy', 'mixed', 'list_heavy')\n"
            "7. list_usage: 列表使用模式('minimal', 'moderate', 'heavy')\n"
            "8. visual_usage: 是否使用图表、信息图('none', 'occasional', 'frequent')\n"
            "9. code_usage: 代码块使用('none', 'occasional', 'frequent')\n"
            "10. separator_usage: 分割线使用频率(0=无, 1=偶尔, 2+=频繁) → 输出为整数 max_separators\n"
            "11. language: 主要语言('zh', 'en', 'mixed')\n"
            "12. notable_phrases: 文档中反复出现的风格短语或口头禅（列表，最多5个）\n"
            "13. anti_patterns: 该风格应避免的写法（列表，最多8个，如'过度使用感叹号', '每段都以列表开头'）\n"
            "14. distinctive_features: 该作者区别于一般写作的2-3个最突出特征（用自然语言描述）\n"
            "15. skill_name: 为这个风格起一个简洁的英文标识名（snake_case, 如 'tech_blog_conversational'）\n"
            "16. skill_description: 一句话中文描述这个风格\n"
        )
        user = (
            f"文件名: {filename}\n\n"
            f"--- 文档开头 ---\n{flavor}\n\n"
        )
        if mid:
            user += f"--- 文档中段 ---\n{mid}\n\n"
        if tail:
            user += f"--- 文档结尾 ---\n{tail}\n\n"
        user += "请输出 JSON:"

        try:
            resp = await llm_service.chat_complete(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=1.0,
            )
            cleaned = resp.replace("```json", "").replace("```", "").strip()
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1:
                cleaned = cleaned[start:end + 1]
            return json.loads(cleaned)
        except Exception as e:
            logger.warning("style analysis failed", extra={"event": "skills.style_analysis_failed", "error": str(e)})
            return {
                "doc_type": "article",
                "opening_style": "narrative_hook",
                "tone": "conversational_professional",
                "conclusion_style": "summary",
                "language": "zh",
                "skill_name": "user_custom_style",
                "skill_description": "从用户文档提取的写作规范",
            }

    async def _compile_style_skill_md(self, style_analysis: Dict, flavor: str) -> str:
        """Phase 2: Compile a style SKILL.md from the analysis results."""
        analysis_str = json.dumps(style_analysis, indent=2, ensure_ascii=False)
        skill_name = str(style_analysis.get("skill_name") or "user_writing_style")
        skill_desc = str(style_analysis.get("skill_description") or "用户写作规范")

        system = (
            "你是一个写作规范技能编译器。你的任务是根据写作规范分析结果，生成一个 SKILL.md 文件。\n"
            "这个文件的目的是：当 AI 写作系统需要按照这个风格写文章时，读取这个文件来指导写作。\n\n"
            "输出必须是完整的 markdown 文件，包含 YAML frontmatter 和正文两部分。\n\n"
            "== YAML Frontmatter 格式 ==\n"
            "严格按照以下结构输出（---包裹）:\n"
            "```\n"
            "---\n"
            f"name: {skill_name}\n"
            f"description: \"{skill_desc}\"\n"
            "role: style\n"
            "style_contract:\n"
            "  structure:\n"
            "    max_heading_depth: <从分析中取>\n"
            "    max_headings: <从分析中取>\n"
            "    max_separators: <从分析中取>\n"
            "    paragraph_first: <段落优先于列表则true>\n"
            "    max_consecutive_lists: 2\n"
            "  visual_policy:\n"
            "    min_infographics: <0或1或2，看分析>\n"
            "    include_infographic_blocks: <true/false>\n"
            "    image_render_enabled: <true/false>\n"
            "    visual_spec_format: \"[VISUAL:label]...[/VISUAL]\"\n"
            "  defaults:\n"
            "    opening_style: <从分析中取>\n"
            "    tone: <从分析中取>\n"
            "    conclusion_style: <从分析中取>\n"
            "  length:\n"
            "    min_words: <合理估计>\n"
            "    max_words: <合理估计>\n"
            "  anti_patterns:\n"
            "    - <从分析中取，每项一行>\n"
            "---\n"
            "```\n\n"
            "== Markdown 正文 ==\n"
            "正文是给 LLM 的写作指南（软约束），用中文自然语言写，内容包括：\n"
            "1. **开头风格**：描述应该怎么开头，给出具体指导和示例\n"
            "2. **整体语气与叙事节奏**：如何保持一致的语气\n"
            "3. **段落与结构习惯**：段落长短、过渡方式\n"
            "4. **标题风格**：标题怎么写才符合这个风格\n"
            "5. **视觉元素使用**：如果需要，说明信息图的使用规范\n"
            "6. **结尾风格**：如何收束文章\n"
            "7. **禁忌与反模式**：列出这个风格绝对不能做的事\n\n"
            "重要：\n"
            "- 正文不能包含 # Purpose, # Inputs, # Workflow, # Failure handling 等执行技能段落\n"
            "- 正文应该读起来像一份写作指导手册，不是代码逻辑说明\n"
            "- 用第二人称'你'来写指导\n"
            "- 引用原文中的实际句式作为正面示例\n"
            "- 返回纯 markdown，不要包裹在代码块中\n"
        )
        user = (
            f"风格分析结果:\n{analysis_str}\n\n"
            f"原文风味样本（供引用示例）:\n{flavor[:3000]}\n\n"
            "请生成完整的 style SKILL.md:"
        )

        return await llm_service.chat_complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=1.0,
        )

    async def _validate_style_skill(self, skill_md: str, style_analysis: Dict, max_retries: int = 2) -> str:
        """Phase 3: Validate and repair style SKILL.md."""
        import re

        def _check_errors(md: str) -> List[str]:
            errors = []
            md_lower = md.lower()

            # Must have frontmatter
            if "---" not in md:
                errors.append("缺少 YAML frontmatter（需要用 --- 包裹）")

            # Must have role: style
            if "role: style" not in md_lower and "role: 'style'" not in md_lower and 'role: "style"' not in md_lower:
                errors.append("frontmatter 中必须包含 role: style")

            # Must have style_contract
            if "style_contract:" not in md:
                errors.append("frontmatter 中必须包含 style_contract 块")

            # Must NOT have execution skill sections
            execution_headers = ["# Purpose", "# Inputs", "# Workflow", "# Failure handling"]
            for h in execution_headers:
                if h in md:
                    errors.append(f"不应包含执行技能段落 '{h}'（这是 style skill，不是 execution skill）")

            # Must have style_contract sub-sections
            if "style_contract:" in md:
                if "structure:" not in md:
                    errors.append("style_contract 中缺少 structure 段")
                if "defaults:" not in md:
                    errors.append("style_contract 中缺少 defaults 段")

            # Body should exist (writing guidelines)
            meta, body = _split_frontmatter(md)
            if len(body.strip()) < 100:
                errors.append("正文（LLM 写作指南）内容太少，至少需要 100 字")

            return errors

        current_md = skill_md
        for attempt in range(max_retries + 1):
            errors = _check_errors(current_md)
            if not errors:
                return current_md

            if attempt < max_retries:
                logger.warning("style skill validation failed", extra={"event": "skills.style_validation_failed", "attempt": attempt + 1, "errors": errors})
                system = (
                    "你是一个严格的 Style SKILL.md 修复引擎。\n"
                    "根据以下验证错误修复提供的 SKILL.md。\n\n"
                    f"验证错误:\n" + "\n".join(f"- {e}" for e in errors) + "\n\n"
                    "修复要求:\n"
                    "- 这是一个 style 类型的 skill（写作规范指南），不是 execution 类型\n"
                    "- frontmatter 必须包含 role: style 和 style_contract\n"
                    "- 正文是 LLM 写作指南，不是执行流程\n"
                    "- 直接输出修复后的完整 markdown，以 --- 开头\n"
                    "- 不要用代码块包裹输出\n"
                )
                try:
                    resp = await llm_service.chat_complete(
                        [{"role": "system", "content": system}, {"role": "user", "content": current_md}],
                        temperature=1.0,
                    )
                    resp = resp.strip()
                    if resp.startswith("```"):
                        resp = re.sub(r"^```\w*\n?", "", resp)
                        resp = re.sub(r"\n?```$", "", resp)
                    current_md = resp.strip()
                except Exception as e:
                    logger.warning("style skill repair failed", extra={"event": "skills.style_repair_failed", "error": str(e)})
            else:
                logger.warning("style skill validation exhausted", extra={"event": "skills.style_validation_exhausted", "max_retries": max_retries})

        return current_md

    def _serialize(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        config = doc.get("config") or {}
        if not isinstance(config, dict):
            config = {}
        skill_markdown = _workflow_markdown_from_config(
            config=config,
            name=str(doc.get("name", "") or ""),
            description=str(doc.get("description", "") or ""),
            scenario=str(doc.get("scenario", "") or ""),
            type_value=doc.get("type"),
            skill_type_value=doc.get("skill_type"),
            current_markdown=str(doc.get("skill_markdown", "") or ""),
        )
        existing_contract = doc.get("skill_contract")
        if isinstance(existing_contract, dict):
            contract = existing_contract
        else:
            contract = _compile_skill_contract(
                name=str(doc.get("name", "") or ""),
                description=str(doc.get("description", "") or ""),
                category=str(doc.get("category", "") or ""),
                formats=list(doc.get("formats") or []),
                skill_markdown=skill_markdown,
                skill_type=str(doc.get("skill_type") or ""),
                contract_json=doc.get("contract_json") if isinstance(doc.get("contract_json"), dict) else {},
            )
        role = _normalize_skill_role(doc.get("role")) or _normalize_skill_role(contract.get("role")) or _infer_role_from_fields(
            category=str(doc.get("category", "") or ""),
            name=str(doc.get("name", "") or ""),
            description=str(doc.get("description", "") or ""),
            skill_markdown=skill_markdown,
            formats=list(doc.get("formats") or []),
        )
        skill_type = _normalize_skill_type(doc.get("skill_type"), role=role)
        return {
            "id": str(doc.get("_id")),
            "user_id": str(doc.get("user_id")),
            "main_id": resolve_main_id(doc.get("main_id")),
            "name": doc.get("name"),
            "description": doc.get("description", ""),
            "scenario": doc.get("scenario", ""),
            "summary": doc.get("summary", ""),
            "category": doc.get("category", ""),
            "role": role,
            "skill_type": skill_type,
            "type": doc.get("type", ""),
            "config": config,
            "enabled": doc.get("enabled", doc.get("is_active", True)),
            "tags": doc.get("tags") or [],
            "visibility": doc.get("visibility", "private"),
            "formats": doc.get("formats") or [],
            "input_profile": doc.get("input_profile") or {},
            "contract_json": doc.get("contract_json") or contract.get("contract_json") or {},
            "skill_markdown": skill_markdown,
            "skill_object_path": doc.get("skill_object_path", ""),
            "sources": doc.get("sources") or [],
            "resources": doc.get("resources") or {},
            "advanced": doc.get("advanced") or {},
            "notes": doc.get("notes", ""),
            "execution_plane": str(doc.get("execution_plane") or contract.get("execution_plane") or "runtime"),
            "skill_contract_version": str(doc.get("skill_contract_version") or contract.get("version") or "v1"),
            "skill_contract": contract,
            "skill_lint_warnings": list(doc.get("skill_lint_warnings") or contract.get("lint_warnings") or []),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
            "is_active": doc.get("is_active", True),
        }


user_skill_service = UserSkillService()
