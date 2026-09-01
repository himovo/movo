from __future__ import annotations

import datetime
import json
import logging
import re
from typing import Any, Dict, List

import yaml

from app.services.workflow_browser_node import browser_node_capability

from app.core.db import get_db
from app.core.tenant import add_main_scope, resolve_main_id

logger = logging.getLogger(__name__)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_text(value: Any, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def _safe_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return default


def _safe_string_list(value: Any, *, limit: int = 24, item_limit: int = 200) -> List[str]:
    values = value if isinstance(value, list) else [value] if value not in (None, "") else []
    out: List[str] = []
    seen: set[str] = set()
    for item in values:
        text = _safe_text(item, item_limit)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _safe_section_structure(value: Any, *, level: int = 1, max_depth: int = 2) -> List[Dict[str, Any]]:
    values = value if isinstance(value, list) else [value] if value not in (None, "") else []
    out: List[Dict[str, Any]] = []
    for raw in values:
        if isinstance(raw, str):
            title = _safe_text(raw, 200)
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
            title = _safe_text(raw.get("title") or raw.get("name") or raw.get("heading"), 200)
            if not title:
                continue
            item = {
                "title": title,
                "level": _safe_int(raw.get("level")) or level,
                "must_include": _safe_string_list(
                    raw.get("must_include")
                    or raw.get("mustInclude")
                    or raw.get("required_elements")
                    or raw.get("requiredElements"),
                    limit=24,
                    item_limit=200,
                ),
                "avoid": _safe_string_list(
                    raw.get("avoid")
                    or raw.get("must_avoid")
                    or raw.get("mustAvoid")
                    or raw.get("forbidden_elements")
                    or raw.get("forbiddenElements"),
                    limit=24,
                    item_limit=200,
                ),
                "notes": _safe_text(raw.get("notes") or raw.get("description"), 1000),
                "children": [],
            }
            if level < max_depth:
                item["children"] = _safe_section_structure(raw.get("children"), level=level + 1, max_depth=max_depth)
        else:
            continue
        out.append(item)
        if len(out) >= 32:
            break
    return out


def _flatten_section_structure_titles(value: Any) -> List[str]:
    raw_text = json.dumps(value, ensure_ascii=False)
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

    def walk(nodes: Any, level: int = 1, parent_path: List[int] | None = None) -> None:
        if not isinstance(nodes, list):
            return
        path = list(parent_path or [])
        numbered_index = 0
        for node in nodes:
            if not isinstance(node, dict):
                continue
            title = _safe_text(node.get("title"), 200)
            if title:
                if not is_unnumbered(title):
                    numbered_index += 1
                display_index = numbered_index if numbered_index > 0 else 1
                out.append(render_title(title, level, display_index, path))
            walk(node.get("children"), level + 1, [*path, display_index if title else numbered_index])

    walk(value)
    return _safe_string_list(out, limit=32, item_limit=200)


def _split_notes_to_instructions(value: Any, *, limit: int = 8) -> List[str]:
    raw = _safe_text(value, 3000)
    if not raw:
        return []
    parts: List[str] = []
    for chunk in raw.replace("\r", "\n").split("\n"):
        text = chunk.strip(" -\t")
        if not text:
            continue
        parts.append(text)
        if len(parts) >= limit:
            break
    return parts


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(float(str(value or "").strip())))
    except Exception:
        return 0


def _target_length(value: Any, config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    raw = _safe_dict(value)
    cfg = _safe_dict(config)
    min_value = _safe_int(
        raw.get("min")
        or raw.get("min_words")
        or raw.get("minWords")
        or cfg.get("minWords")
        or cfg.get("min_words")
    )
    max_value = _safe_int(
        raw.get("max")
        or raw.get("max_words")
        or raw.get("maxWords")
        or cfg.get("maxWords")
        or cfg.get("max_words")
    )
    unit = _safe_text(raw.get("unit") or raw.get("length_unit") or cfg.get("lengthUnit") or cfg.get("length_unit") or "chinese_chars", 40)
    out: Dict[str, Any] = {"unit": unit or "chinese_chars"}
    if min_value > 0:
        out["min"] = min_value
    if max_value > 0:
        out["max"] = max_value
    return out


def _target_length_from_config(config: Dict[str, Any]) -> Dict[str, Any]:
    raw = config.get("targetLength") or config.get("target_length")
    if not isinstance(raw, dict):
        raw = {}
    if not raw and isinstance(config.get("contractJson") or config.get("contract_json"), dict):
        contract = _safe_dict(config.get("contractJson") or config.get("contract_json"))
        raw = contract.get("target_length") or contract.get("targetLength") or {}
    return _target_length(raw, config)


def _workflow_steps(config: Dict[str, Any]) -> List[str]:
    raw_steps = config.get("workflowSteps")
    if not isinstance(raw_steps, list):
        return []
    steps: List[str] = []
    for item in raw_steps:
        if isinstance(item, dict):
            text = _safe_text(item.get("text"), 1200)
        else:
            text = _safe_text(item, 1200)
        if text:
            steps.append(text)
    return steps


def _workflow_node_instruction(item: Dict[str, Any], *, title: str, business_config: Dict[str, Any], output_alias: str) -> str:
    explicit = _safe_text(
        item.get("description")
        or item.get("text")
        or item.get("instruction")
        or item.get("goal")
        or item.get("objective"),
        1200,
    )
    if explicit:
        return explicit
    parts: List[str] = []
    if title:
        parts.append(title)
    if output_alias:
        parts.append(f"输出：{output_alias}")
    config_parts: List[str] = []
    for key, value in business_config.items():
        if str(key).strip() in {"pluginCode", "scriptCode", "code", "python"}:
            continue
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (str, int, float, bool)):
            rendered = str(value)
        elif isinstance(value, list):
            rendered = "、".join(str(v) for v in value if str(v).strip())
        else:
            rendered = json.dumps(value, ensure_ascii=False)
        rendered = _safe_text(rendered, 240)
        if rendered:
            config_parts.append(f"{key}={rendered}")
        if len(config_parts) >= 8:
            break
    if config_parts:
        parts.append("配置：" + "；".join(config_parts))
    return _safe_text("；".join(part for part in parts if part), 1200)


def _workflow_nodes(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_nodes = config.get("workflowNodes") or config.get("workflow_nodes")
    if not isinstance(raw_nodes, list):
        return []
    nodes: List[Dict[str, Any]] = []
    allowed = {
        "read_material",
        "extract_resources",
        "understand_image",
        "extract_info",
        "compute_metric",
        "data_collect",
        "browser_automation",
        "internal_search",
        "external_search",
        "call_tool",
        "script_plugin",
        "generate_content",
        "translate_rewrite",
        "fill_table",
        "review_check",
        "export_delivery",
    }
    for idx, item in enumerate(raw_nodes):
        if not isinstance(item, dict):
            continue
        node_type = _safe_text(item.get("type") or item.get("node_type"), 80)
        # Preserve an unknown type so the DSH Skill compiler can fail closed.
        # Silently rewriting it to generate_content would execute a materially
        # different workflow and hide a missing Step 6 capability migration.
        if node_type not in allowed:
            logger.warning("org_skill_adapter_unknown_workflow_node type=%s index=%s", node_type, idx)
        business_config = item.get("businessConfig") or item.get("business_config") or {}
        if not isinstance(business_config, dict):
            business_config = {}
        title = _safe_text(item.get("title") or f"业务节点 {idx + 1}", 160)
        output_alias = _safe_text(item.get("outputAlias") or item.get("output_alias") or business_config.get("outputAlias") or business_config.get("output_alias"), 120)
        description = _workflow_node_instruction(item, title=title, business_config=business_config, output_alias=output_alias)
        if not description:
            logger.warning(
                "org_skill_adapter_workflow_node_skipped index=%s reason=empty_instruction raw_keys=%s",
                idx,
                sorted(str(key) for key in item.keys()),
            )
            continue
        nodes.append(
            {
                "id": _safe_text(item.get("id"), 80) or f"node_{idx + 1}",
                "type": node_type,
                "title": title,
                "description": description,
                "businessConfig": business_config,
                "boundWritingSkillId": _safe_text(item.get("boundWritingSkillId") or item.get("bound_writing_skill_id"), 120),
                "outputAlias": output_alias,
            }
        )
    return nodes


def _frontmatter_markdown(frontmatter: Dict[str, Any], sections: List[tuple[str, str]]) -> str:
    fm = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    body = "\n\n".join(f"# {title}\n\n{content}".strip() for title, content in sections if content.strip())
    return f"---\n{fm}\n---\n\n{body}\n"


def _workflow_kind_from_node_type(node_type: str) -> str:
    mapping = {
        "read_material": "file.parse_documents",
        "extract_resources": "file.extract_resources",
        "understand_image": "vision.extract_image_facts",
        "extract_info": "analysis.dataset_diagnosis",
        "compute_metric": "analysis.compute_metrics",
        "data_collect": "web.collect_url",
        "browser_automation": "browser.navigate_and_extract",
        "internal_search": "kb.search",
        "external_search": "research.collect_external_evidence",
        "call_tool": "external.invoke_tool",
        "script_plugin": "file.run_script_plugin",
        "generate_content": "generation.compose_dynamic",
        "translate_rewrite": "file.transform_content",
        "fill_table": "file.generate_table",
        "review_check": "generation",
        "export_delivery": "file.export_document",
    }
    return mapping.get(str(node_type or "").strip(), "generation")


def _workflow_node_kind(node: Dict[str, Any]) -> str:
    node_type = str(node.get("type") or "").strip()
    if node_type == "browser_automation":
        return browser_node_capability(
            str(node.get("description") or ""),
            node.get("businessConfig") if isinstance(node.get("businessConfig"), dict) else {},
        )
    return _workflow_kind_from_node_type(node_type)


def _workflow_markdown(*, name: str, description: str, scenario: str, steps: List[str], nodes: List[Dict[str, Any]] | None = None) -> str:
    semantic_nodes = list(nodes or [])
    if semantic_nodes:
        step_items = [
            {
                "id": _safe_text(node.get("id"), 80) or f"node_{idx + 1}",
                "title": _safe_text(node.get("title"), 160) or f"业务节点 {idx + 1}",
                "instruction": _safe_text(node.get("description"), 1200),
                "kind": _workflow_node_kind(node),
                "node_type": str(node.get("type") or ""),
                "semantic_config": dict(node.get("businessConfig") or {}) if isinstance(node.get("businessConfig"), dict) else {},
                "bound_writing_skill_id": _safe_text(node.get("boundWritingSkillId"), 120),
                "output_alias": _safe_text(node.get("outputAlias"), 120),
            }
            for idx, node in enumerate(semantic_nodes)
            if _safe_text(node.get("description"), 1200)
        ]
    else:
        step_items = [
            {
                "title": f"业务步骤 {idx + 1}",
                "instruction": step,
            }
            for idx, step in enumerate(steps)
        ]
    frontmatter = {
        "skill_id": "",
        "name": name,
        "description": description,
        "skill_type": "composite_task",
        "role": "execution",
        "triggers": [item for item in [name, scenario, description] if item],
        "steps": step_items,
    }
    return _frontmatter_markdown(
        frontmatter,
        [
            ("Purpose", description or name),
            ("When To Use", scenario or "当用户请求与该组织级工作流 Skill 的业务目标一致时使用。"),
            ("Business Logic", "\n".join(f"{idx + 1}. {step}" for idx, step in enumerate(steps))),
        ],
    )


def _style_contract(*, name: str, description: str, scenario: str, config: Dict[str, Any]) -> Dict[str, Any]:
    style_notes = _safe_text(
        config.get("styleNotes")
        or config.get("style_notes")
        or config.get("instructions")
        or config.get("notes")
        or description
        or scenario,
        2000,
    )
    target_length = _target_length_from_config(config)
    contract_json = _safe_dict(config.get("contractJson") or config.get("contract_json"))
    section_structure = _safe_section_structure(
        config.get("sectionStructure")
        or config.get("section_structure")
        or contract_json.get("section_structure")
        or contract_json.get("sectionStructure")
    )
    required_blocks = [
        str(item).strip()
        for item in list(
            config.get("requiredSections")
            or config.get("required_sections")
            or config.get("requiredBlocks")
            or config.get("required_blocks")
            or contract_json.get("required_sections")
            or []
        )
        if str(item).strip()
    ]
    if section_structure:
        required_blocks = _flatten_section_structure_titles(section_structure)
    return {
        "defaults": {
            "tone": _safe_text(config.get("tone") or "professional", 120),
            "voice": _safe_text(config.get("voice") or "clear", 120),
            "style_description": style_notes,
        },
        "structure": {
            "section_structure": section_structure,
            "required_blocks": required_blocks,
            "forbidden_blocks": [str(item).strip() for item in list(config.get("forbiddenBlocks") or config.get("forbidden_blocks") or []) if str(item).strip()],
            "paragraph_first": bool(config.get("paragraphFirst") or config.get("paragraph_first") or False),
        },
        "length": {
            "min_words": int(target_length.get("min") or 0),
            "max_words": int(target_length.get("max") or 0),
            "unit": _safe_text(target_length.get("unit") or "chinese_chars", 40),
        },
        "visual_policy": _safe_dict(config.get("visualPolicy") or config.get("visual_policy")),
        "anti_patterns": [str(item).strip() for item in list(config.get("antiPatterns") or config.get("anti_patterns") or []) if str(item).strip()],
    }


def _style_markdown(*, name: str, description: str, scenario: str, config: Dict[str, Any]) -> str:
    contract = _style_contract(name=name, description=description, scenario=scenario, config=config)
    frontmatter = {
        "skill_id": "",
        "name": name,
        "description": description,
        "role": "style",
        "category": "style",
        "tags": ["organization", "writing_style"],
        "style_contract": contract,
    }
    guidance = _safe_text(
        config.get("styleNotes")
        or config.get("style_notes")
        or config.get("instructions")
        or config.get("notes")
        or description,
        3000,
    )
    return _frontmatter_markdown(
        frontmatter,
        [
            ("Purpose", description or name),
            ("When To Use", scenario or "当用户请求与该组织级写作规范 Skill 的适用场景一致时使用。"),
            ("Style Guidance", guidance or "按照该 Skill 的名称、描述和适用场景控制表达风格。"),
        ],
    )


def _style_contract_json_from_config(*, name: str, description: str, scenario: str, config: Dict[str, Any]) -> Dict[str, Any]:
    contract = _safe_dict(config.get("contractJson") or config.get("contract_json"))
    if contract:
        target_length = _target_length(contract.get("target_length") or contract.get("targetLength"), config)
        section_structure = _safe_section_structure(contract.get("section_structure") or contract.get("sectionStructure"))
        required_sections = _safe_string_list(contract.get("required_sections"), limit=32, item_limit=200)
        if not required_sections and section_structure:
            required_sections = _flatten_section_structure_titles(section_structure)
        return {
            "skill_type": "style",
            "name": _safe_text(contract.get("name") or name, 120) or name,
            "summary": _safe_text(contract.get("summary") or description or scenario, 500),
            "applicable_scenarios": _safe_text(contract.get("applicable_scenarios") or scenario, 1500),
            "publish_channel": _safe_string_list(contract.get("publish_channel"), limit=12, item_limit=80),
            "content_form": _safe_string_list(contract.get("content_form"), limit=12, item_limit=80),
            "target_audience": _safe_string_list(contract.get("target_audience"), limit=12, item_limit=120),
            "preferred_style": _safe_string_list(contract.get("preferred_style"), limit=12, item_limit=120),
            "target_length": target_length,
            "section_structure": section_structure,
            "required_sections": required_sections,
            "required_elements": _safe_string_list(contract.get("required_elements"), limit=24, item_limit=200),
            "forbidden_elements": _safe_string_list(contract.get("forbidden_elements"), limit=24, item_limit=200),
            "reference_materials": _safe_string_list(contract.get("reference_materials"), limit=16, item_limit=200),
            "notes": _safe_text(contract.get("notes"), 4000),
        }
    target_length = _target_length(config.get("targetLength") or config.get("target_length"), config)
    section_structure = _safe_section_structure(config.get("sectionStructure") or config.get("section_structure"))
    required_sections = _safe_string_list(
        config.get("requiredSections") or config.get("required_sections") or config.get("requiredBlocks") or config.get("required_blocks"),
        limit=32,
        item_limit=200,
    )
    if not required_sections and section_structure:
        required_sections = _flatten_section_structure_titles(section_structure)
    return {
        "skill_type": "style",
        "name": name,
        "summary": _safe_text(description or scenario, 500),
        "applicable_scenarios": scenario,
        "publish_channel": [],
        "content_form": [],
        "target_audience": [],
        "preferred_style": [],
        "target_length": target_length,
        "section_structure": section_structure,
        "required_sections": required_sections,
        "required_elements": _safe_string_list(config.get("requiredElements") or config.get("required_elements"), limit=24, item_limit=200),
        "forbidden_elements": _safe_string_list(config.get("forbiddenBlocks") or config.get("forbidden_blocks"), limit=24, item_limit=200),
        "reference_materials": [],
        "notes": _safe_text(
            config.get("notes")
            or config.get("styleNotes")
            or config.get("style_notes")
            or config.get("instructions"),
            4000,
        ),
    }


def _style_markdown_from_contract(*, name: str, description: str, scenario: str, contract_json: Dict[str, Any]) -> str:
    frontmatter = {
        "skill_id": "",
        "name": name,
        "description": description,
        "skill_type": "style",
        "role": "style",
        "summary": _safe_text(contract_json.get("summary") or description or scenario, 500),
        "applicable_scenarios": _safe_text(contract_json.get("applicable_scenarios") or scenario, 1500),
        "publish_channel": _safe_string_list(contract_json.get("publish_channel"), limit=12, item_limit=80),
        "content_form": _safe_string_list(contract_json.get("content_form"), limit=12, item_limit=80),
        "target_audience": _safe_string_list(contract_json.get("target_audience"), limit=12, item_limit=120),
        "preferred_style": _safe_string_list(contract_json.get("preferred_style"), limit=12, item_limit=120),
        "target_length": _target_length(contract_json.get("target_length") or contract_json.get("targetLength")),
        "section_structure": _safe_section_structure(contract_json.get("section_structure") or contract_json.get("sectionStructure")),
        "required_sections": _safe_string_list(contract_json.get("required_sections"), limit=32, item_limit=200),
        "required_elements": _safe_string_list(contract_json.get("required_elements"), limit=24, item_limit=200),
        "forbidden_elements": _safe_string_list(contract_json.get("forbidden_elements"), limit=24, item_limit=200),
        "reference_materials": _safe_string_list(contract_json.get("reference_materials"), limit=16, item_limit=200),
    }
    guidance_sections = [
        ("Purpose", description or name),
        ("When To Use", scenario or "当用户请求与该组织级写作规范 Skill 的适用场景一致时使用。"),
        ("Style Guidance", _safe_text(contract_json.get("notes"), 3000) or "按照该 Skill 的配置控制结构、表达风格与内容边界。"),
    ]
    return _frontmatter_markdown(frontmatter, guidance_sections)


def _base_payload(
    doc: Dict[str, Any],
    *,
    skill_type: str,
    role: str,
    skill_markdown: str,
    skill_contract: Dict[str, Any],
    contract_json: Dict[str, Any] | None = None,
    input_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    org_id = _safe_text(doc.get("_id"), 80)
    now = doc.get("updated_at") or doc.get("created_at") or datetime.datetime.utcnow()
    name = _safe_text(doc.get("name"), 120) or "组织级 Skill"
    description = _safe_text(doc.get("description"), 1200)
    scenario = _safe_text(doc.get("scenario"), 1500)
    resolved_contract_json = _safe_dict(contract_json) or {
        "skill_type": skill_type,
        "name": name,
        "summary": description or scenario,
        "applicable_scenarios": scenario,
        "notes": description,
    }
    return {
        "id": f"org_skill:{org_id}",
        "user_id": "organization",
        "main_id": resolve_main_id(doc.get("main_id")),
        "name": name,
        "description": description,
        "summary": description or scenario,
        "category": "organization",
        "role": role,
        "skill_type": skill_type,
        "tags": ["organization", str(doc.get("type") or "")],
        "visibility": "organization",
        "formats": [],
        "input_profile": _safe_dict(input_profile),
        "contract_json": resolved_contract_json,
        "skill_markdown": skill_markdown,
        "skill_object_path": "",
        "sources": [],
        "resources": {},
        "advanced": {},
        "notes": scenario,
        "execution_plane": str(skill_contract.get("execution_plane") or "runtime"),
        "skill_contract_version": str(skill_contract.get("version") or "org_v1"),
        "skill_contract": skill_contract,
        "skill_lint_warnings": list(skill_contract.get("lint_warnings") or []),
        "created_at": doc.get("created_at") or now,
        "updated_at": now,
        "is_active": True,
        "source": "org_db",
    }


def _adapt_workflow(doc: Dict[str, Any]) -> Dict[str, Any] | None:
    config = _safe_dict(doc.get("config"))
    nodes = _workflow_nodes(config)
    steps = [
        _safe_text(node.get("description"), 1200)
        for node in nodes
        if _safe_text(node.get("description"), 1200)
    ] or _workflow_steps(config)
    if not steps:
        return None
    name = _safe_text(doc.get("name"), 120) or "组织级工作流"
    description = _safe_text(doc.get("description"), 1200)
    scenario = _safe_text(doc.get("scenario"), 1500)
    markdown = _workflow_markdown(name=name, description=description, scenario=scenario, steps=steps, nodes=nodes)
    logger.info(
        "org_skill_adapter_workflow_adapted skill=%s raw_nodes=%s executable_nodes=%s mapped_capabilities=%s fallback_steps=%s",
        name,
        len(config.get("workflowNodes") or config.get("workflow_nodes") or []),
        len(nodes),
        [
            {
                "type": str(node.get("type") or ""),
                "title": str(node.get("title") or ""),
                "kind": _workflow_node_kind(node),
            }
            for node in nodes
        ],
        len(_workflow_steps(config)) if not nodes else 0,
    )
    contract = {
        "version": "org_v1",
        "skill_type": "composite_task",
        "role": "execution",
        "execution_plane": "runtime",
        "contract_json": {
            "skill_type": "composite_task",
            "name": name,
            "summary": description or scenario,
            "applicable_scenarios": scenario,
            "notes": description,
        },
        "structure": {"workflow_nodes": nodes},
        "visual_policy": {},
        "compose_profile": {},
        "signals": {},
        "lint_warnings": [],
    }
    return _base_payload(
        doc,
        skill_type="composite_task",
        role="execution",
        skill_markdown=markdown,
        skill_contract=contract,
    )


def _adapt_writing_style(doc: Dict[str, Any]) -> Dict[str, Any] | None:
    config = _safe_dict(doc.get("config"))
    name = _safe_text(doc.get("name"), 120) or "组织级写作规范"
    description = _safe_text(doc.get("description"), 1200)
    scenario = _safe_text(doc.get("scenario"), 1500)
    contract_json = _style_contract_json_from_config(name=name, description=description, scenario=scenario, config=config)
    style_contract = _style_contract(name=name, description=description, scenario=scenario, config=config)
    existing_skill_contract = _safe_dict(config.get("skillContract") or config.get("skill_contract"))
    visual_policy = _safe_dict(existing_skill_contract.get("visual_policy")) or _safe_dict(style_contract.get("visual_policy"))
    notes_instructions = _split_notes_to_instructions(contract_json.get("notes"))
    style_description = _safe_text(
        contract_json.get("notes")
        or (style_contract.get("defaults") or {}).get("style_description")
        or description
        or scenario,
        4000,
    )
    required_blocks = _safe_string_list(
        contract_json.get("required_sections")
        or (style_contract.get("structure") or {}).get("required_blocks"),
        limit=16,
        item_limit=160,
    )
    forbidden_blocks = _safe_string_list(
        contract_json.get("forbidden_elements")
        or (style_contract.get("structure") or {}).get("forbidden_blocks"),
        limit=16,
        item_limit=160,
    )
    content_forms = _safe_string_list(contract_json.get("content_form"), limit=12, item_limit=80)
    markdown = _safe_text(config.get("skillMarkdown") or config.get("skill_markdown"), 20000)
    if not markdown:
        markdown = _style_markdown_from_contract(
            name=name,
            description=description,
            scenario=scenario,
            contract_json=contract_json,
        )
    contract = {
        "version": "org_v1",
        "skill_type": "style",
        "role": "style",
        "execution_plane": "runtime",
        "contract_json": contract_json,
        "structure": {
            "required_blocks": required_blocks,
            "forbidden_blocks": forbidden_blocks,
        },
        "visual_policy": visual_policy,
        "compose_profile": {
            "preferred_mode": "auto",
            "human_readability_first": True,
            "content_form": content_forms[0] if content_forms else "",
            "style_description": style_description,
            "writing_instructions": notes_instructions,
        },
        "signals": {
            "style_score": 1,
            "contract_json_fields": len([k for k, v in contract_json.items() if v not in ("", [], {})]),
        },
        "lint_warnings": list(existing_skill_contract.get("lint_warnings") or []),
    }
    return _base_payload(
        doc,
        skill_type="style",
        role="style",
        skill_markdown=markdown,
        skill_contract=contract,
        contract_json=contract_json,
        input_profile=_safe_dict(config.get("inputProfile") or config.get("input_profile")),
    )


class OrganizationSkillAdapter:
    async def list_runtime_skills(self, *, main_id: str) -> List[Dict[str, Any]]:
        db = get_db()
        query = add_main_scope({}, main_id)
        cursor = db.skills.find(query).sort("updated_at", -1)
        out: List[Dict[str, Any]] = []
        async for doc in cursor:
            if not isinstance(doc, dict):
                continue
            if not _safe_bool(doc.get("enabled"), True):
                continue
            raw_type = _safe_text(doc.get("type"), 80).lower()
            if raw_type == "workflow":
                adapted = _adapt_workflow(doc)
            elif raw_type == "writing_style":
                adapted = _adapt_writing_style(doc)
            else:
                adapted = None
            if adapted:
                out.append(adapted)
        return out


organization_skill_adapter = OrganizationSkillAdapter()
