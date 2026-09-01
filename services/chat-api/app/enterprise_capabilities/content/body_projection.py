from __future__ import annotations

import re
from typing import Any, Dict, List


_PRODUCTION_MARKERS = (
    "配图",
    "图片",
    "图示",
    "图注",
    "图位",
    "插图",
    "头图",
    "封面图",
    "图文穿插",
    "图文结构",
    "visual",
    "image",
    "infographic",
    "illustration",
    "gallery",
    "cover",
)

_VISUAL_REQUIREMENT_PATTERNS = (
    r"图\s*\d+(?:\s*[-~到至]\s*\d+)?(?:\s*[：:]\s*[^，。；;]+)?",
    r"(?:独立|分组)?(?:图示|图注|插图)(?:区块|分组)?",
    r"(?:总览|结构|架构|流程|步骤|对比|场景|模块|关系|信息|路线)(?:图|图示|示意图)",
    r"(?:图片|图示|插图|头图|封面图)(?:资源|素材|位|位点|数量|规划|计划|分布)",
)

_PRODUCTION_CLAUSE_PATTERNS = (
    r"[，、；;]?\s*建议多配图",
    r"[，、；;]?\s*要多配图",
    r"[，、；;]?\s*多配图",
    r"[，、；;]?\s*含配图建议",
    r"[，、；;]?\s*配图建议",
    r"[，、；;]?\s*配图位(?:与配图文案建议)?",
    r"[，、；;]?\s*包含多处配图位(?:与配图文案建议)?",
    r"[，、；;]?\s*包含配图位(?:与标签)?",
    r"[，、；;]?\s*插入多处配图位(?:与配图文案建议)?",
)

_INLINE_VISUAL_SUGGESTION_PATTERNS = (
    r"[【\[]\s*(?:配图|图片|插图|图示|封面图|正文配图)\s*[:：][^\]】\n]{0,800}[】\]]",
    r"(?m)^\s*(?:[-*]\s*)?[【\[]\s*(?:配图|图片|插图|图示|封面图|正文配图)\s*[:：][^\]】\n]{0,800}[】\]]\s*$",
    r"[（(]\s*(?:配图|图片|插图|图示|封面图|正文配图)\s*(?:建议|说明|提示|prompt)?\s*[:：][^（）()\n]{0,800}\s*[）)]",
    r"[（(]\s*(?:image|visual|illustration|cover)\s*(?:suggestion|note|prompt|brief)\s*:\s*[^（）()\n]{0,800}\s*[）)]",
    r"(?m)^\s*(?:[-*]\s*)?(?:配图|图片|插图|图示|封面图|正文配图)\s*(?:建议|说明|提示|prompt)?\s*[:：].*$",
    r"(?im)^\s*(?:[-*]\s*)?(?:image|visual|illustration|cover)\s*(?:suggestion|note|prompt|brief)\s*:.*$",
)

_VISUAL_PLACEHOLDER_DIRECTIVE_PATTERNS = (
    r"[，,、；;]?\s*(?:并)?(?:包含|含|带有|加入|输出|生成|插入|保留)?\s*(?:少量|若干|多处|几个|几张|适量)?\s*(?:配图|图片|插图|图示|视觉|image|visual|illustration)\s*(?:标记|占位符?|占位|placeholder|labels?|notes?|suggestions?)",
    r"[，,、；;]?\s*(?:配图|图片|插图|图示|视觉|image|visual|illustration)\s*(?:标记|占位符?|占位|placeholder|labels?|notes?|suggestions?)",
    r"[，,、；;]?\s*(?:image|visual|illustration)\s*(?:placeholder|label|note|suggestion)s?",
)

_VISUAL_FORMATTING_KEYS = (
    "image_placeholder_format",
    "visual_placeholder_format",
    "illustration_placeholder_format",
    "image_slot_format",
    "visual_slot_format",
    "illustration_slot_format",
    "caption_placeholder_format",
)

_VISUAL_FORMATTING_KEY_MARKERS = (
    "image",
    "visual",
    "illustration",
    "picture",
    "photo",
    "cover",
    "thumbnail",
    "配图",
    "图片",
    "插图",
    "图示",
    "封面",
)

_PLACEHOLDER_FORMATTING_KEY_MARKERS = (
    "placeholder",
    "slot",
    "label",
    "note",
    "suggestion",
    "format",
    "占位",
    "标记",
    "标签",
    "建议",
    "格式",
)

_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")


def _strip_visual_suggestion_blocks(text: str) -> str:
    lines = str(text or "").splitlines()
    if not lines:
        return str(text or "")

    def _heading_label(line: str) -> str:
        stripped = str(line or "").strip()
        stripped = re.sub(r"^\s{0,3}#{1,6}\s+", "", stripped)
        stripped = re.sub(r"^\s*(?:[-*]|\d+[.、])\s+", "", stripped)
        return stripped.strip(" ：:。")

    def _is_visual_heading(line: str) -> bool:
        label = _heading_label(line)
        return bool(
            re.match(
                r"^(?:配图|图片|插图|图示|封面图|正文配图)\s*(?:建议|说明|提示|prompt)?$",
                label,
                flags=re.IGNORECASE,
            )
            or re.match(
                r"^(?:image|visual|illustration|cover)\s*(?:suggestions?|notes?|prompts?|briefs?)$",
                label,
                flags=re.IGNORECASE,
            )
        )

    def _is_visual_body(line: str) -> bool:
        stripped = str(line or "").strip()
        if not stripped:
            return True
        if re.match(r"^\s{0,3}#{1,6}\s+", stripped):
            return False
        return bool(
            re.search(
                r"(?:第[一二三四五六七八九十\d]+张\s*)?(?:配图|图片|插图|图示|封面图|正文配图|照片|舞台照|生活照|画面|高清动态定格)",
                stripped,
                flags=re.IGNORECASE,
            )
            or re.search(
                r"(?:image|visual|illustration|cover|photo|picture|shot)\s*(?:\d+|one|two|three|suggestion|prompt|brief)?",
                stripped,
                flags=re.IGNORECASE,
            )
        )

    out: List[str] = []
    skipping = False
    for raw in lines:
        line = str(raw or "")
        if _is_visual_heading(line):
            skipping = True
            continue
        if skipping:
            if _is_visual_body(line):
                continue
            skipping = False
        out.append(line)
    return "\n".join(out)


def is_visual_or_production_requirement(value: str) -> bool:
    raw = str(value or "").strip()
    token = raw.lower()
    if not token:
        return False
    if any(re.search(pattern, raw, flags=re.IGNORECASE) for pattern in _VISUAL_REQUIREMENT_PATTERNS):
        return True
    return any(marker in token for marker in _PRODUCTION_MARKERS)


def strip_inline_visual_suggestions(value: str) -> str:
    text = str(value or "")
    if not text:
        return text
    cleaned = _strip_visual_suggestion_blocks(text)
    for pattern in _INLINE_VISUAL_SUGGESTION_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[（(]\s*[)）]", "", cleaned)
    cleaned = re.sub(r"[ \t]+([，。！？；：,.!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() if text.strip() == text else cleaned


def strip_visual_placeholder_directives(value: str) -> str:
    """Remove visual placeholder instructions from reader-facing body contracts.

    This intentionally does not remove ordinary visual intent. A phrase like
    "少量配图" may still drive the production-side visual pipeline; phrases like
    "含少量配图标记" or "image placeholders" must not reach body generation.
    """
    text = str(value or "")
    if not text:
        return text
    cleaned = strip_inline_visual_suggestions(text)
    for pattern in _VISUAL_PLACEHOLDER_DIRECTIVE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[（(]\s*[，,、；;]?\s*[)）]", "", cleaned)
    cleaned = re.sub(r"[（(]\s*[,，、]\s*", "（", cleaned)
    cleaned = re.sub(r"\s+([）)])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([，。！？；：,.!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"([（(])\s+", r"\1", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() if text.strip() == text else cleaned


def body_only_formatting_rules(formatting_rules: Dict[str, Any]) -> Dict[str, Any]:
    """Project preset formatting rules to reader-facing body constraints.

    Visual placeholders are production instructions. They can make the writer
    emit literal "[配图：...]" text, so they must stay out of body prompts.
    """
    out: Dict[str, Any] = {}
    for raw_key, raw_value in dict(formatting_rules or {}).items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        key_token = key.lower()
        is_visual_key = any(marker in key_token for marker in _VISUAL_FORMATTING_KEY_MARKERS)
        is_placeholder_key = key_token in _VISUAL_FORMATTING_KEYS or (
            is_visual_key and any(marker in key_token for marker in _PLACEHOLDER_FORMATTING_KEY_MARKERS)
        )
        if is_placeholder_key:
            continue

        if isinstance(raw_value, str):
            cleaned = strip_visual_placeholder_directives(raw_value)
            if is_visual_key and cleaned != raw_value:
                continue
            out[key] = cleaned
            continue

        out[key] = raw_value
    return out


def _is_renderable_markdown_image_url(url: str) -> bool:
    value = str(url or "").strip()
    if not value:
        return False
    return value.startswith(("http://", "https://", "data:", "/askai-api/api/files/", "/askai-api/files/", "/api/files/"))


def strip_unrenderable_markdown_images(value: str) -> str:
    text = str(value or "")
    if not text:
        return text

    lines = text.splitlines()
    out: List[str] = []
    pending_removed_full_line_image = False
    for raw in lines:
        line = str(raw or "")
        stripped = line.strip()
        if pending_removed_full_line_image:
            if not stripped:
                continue
            if re.match(r"^\*?\s*(?:图注|caption|说明)[:：].*\*?\s*$", stripped, flags=re.IGNORECASE):
                pending_removed_full_line_image = False
                continue
            pending_removed_full_line_image = False
        full_image = re.match(r"^!\[[^\]]*\]\(([^)]*)\)\s*$", stripped)
        if full_image:
            url = str(full_image.group(1) or "").strip()
            if not _is_renderable_markdown_image_url(url):
                pending_removed_full_line_image = True
                continue

        def _replace_image(match: re.Match[str]) -> str:
            url = str(match.group(2) or "").strip()
            if _is_renderable_markdown_image_url(url):
                return match.group(0)
            return ""

        cleaned_line = _MARKDOWN_IMAGE_RE.sub(_replace_image, line)
        out.append(cleaned_line.rstrip())

    cleaned = "\n".join(out)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() if text.strip() == text else cleaned


def strip_visual_or_production_clauses(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    cleaned = strip_inline_visual_suggestions(text)
    for pattern in _PRODUCTION_CLAUSE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"(?:包含|提供|插入|附|含)?[^，。；:：()（）]{0,24}?(?:配图|图片|图示|图位|visual|image)[^，。；:：()（）]{0,24}",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[（(]\s*[)）]", "", cleaned)
    cleaned = re.sub(r"[，、；;]{2,}", "，", cleaned).strip("，。；;、 ")
    return cleaned or text


def canonicalize_required_blocks(blocks: List[str], *, preserve_order: bool = False) -> List[str]:
    def _looks_like_explicit_heading(value: str) -> bool:
        token = str(value or "").strip()
        if not token:
            return False
        return bool(
            re.match(r"^(?:#{1,6}\s*)?(?:\d+(?:\.\d+)*[\.、]?\s*|[一二三四五六七八九十]+[、.]\s*)", token)
        )

    def _should_preserve_order(values: List[str]) -> bool:
        if not values:
            return False
        explicit = sum(1 for item in values if _looks_like_explicit_heading(item))
        return explicit >= 2

    def _weight(value: str) -> tuple[int, str]:
        token = str(value or "").strip().lower()
        if not token:
            return (99, "")
        if any(marker in token for marker in ("标题", "title")):
            return (0, token)
        if any(marker in token for marker in ("钩子", "hook", "开头3行", "opening")):
            return (1, token)
        if any(marker in token for marker in ("导语", "lead", "背景", "前言", "intro")):
            return (2, token)
        if any(marker in token for marker in ("核心概念", "核心", "正文", "body", "分析", "概览")):
            return (3, token)
        if any(marker in token for marker in ("使用场景", "场景", "案例", "example")):
            return (4, token)
        if any(marker in token for marker in ("步骤", "上手", "落地", "howto", "实践")):
            return (5, token)
        if any(marker in token for marker in ("结尾", "总结", "结论", "cta", "互动")):
            return (6, token)
        if any(marker in token for marker in ("标签", "tag", "话题")):
            return (7, token)
        return (5, token)

    deduped: List[str] = []
    for item in list(blocks or []):
        token = str(item or "").strip()
        if token and token not in deduped:
            deduped.append(token)
    # preserve_order: caller (e.g. dynamic-compose path for resume / cover
    # letter) already produced the reader-facing order, and the article
    # weight map below would clobber it (resume tokens like "experience" /
    # "education" don't match any weight bucket and get sorted alphabetically).
    if preserve_order or _should_preserve_order(deduped):
        return deduped
    weighted = [(_weight(item), item) for item in deduped]
    weighted.sort(key=lambda item: item[0])
    return [item for _, item in weighted]


def body_only_structure_contract(structure_contract: Dict[str, Any]) -> Dict[str, Any]:
    structure = dict(structure_contract or {})
    blocks = []
    visual_sidecar: List[Dict[str, str]] = []
    for item in list(structure.get("blocks") or []):
        if not isinstance(item, dict):
            continue
        block = dict(item)
        title = str(block.get("title") or block.get("name") or block.get("block_name") or "").strip()
        visual_hint = str(block.get("visual_hint") or "").strip().lower()
        if title and visual_hint and visual_hint != "none":
            visual_sidecar.append({"title": title, "visual_hint": visual_hint})
        block.pop("visual_hint", None)
        blocks.append(block)
    if blocks:
        structure["blocks"] = blocks
    if visual_sidecar:
        metadata = dict(structure.get("metadata") or {})
        metadata["visual_sidecar"] = visual_sidecar
        structure["metadata"] = metadata
    return structure


def _strip_visual_sidecar_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(payload or {})
    metadata = dict(out.get("metadata") or {})
    for key in ("visual_sidecar", "visual_slots_sidecar"):
        metadata.pop(key, None)
    if metadata:
        out["metadata"] = metadata
    else:
        out.pop("metadata", None)
    return out


def body_only_content_plan(content_plan: Dict[str, Any]) -> Dict[str, Any]:
    plan = dict(content_plan or {})
    visual_slots = list(plan.get("visual_slots") or [])
    if "visual_slots" in plan:
        plan.pop("visual_slots", None)
    sections = []
    visual_sidecar: List[Dict[str, str]] = []
    for item in list(plan.get("sections") or []):
        if not isinstance(item, dict):
            continue
        section = dict(item)
        section_id = str(section.get("section_id") or "").strip()
        title = str(section.get("title") or "").strip()
        visual_hint = str(section.get("visual_hint") or "").strip().lower()
        if (section_id or title) and visual_hint and visual_hint != "none":
            visual_sidecar.append({"section_id": section_id, "title": title, "visual_hint": visual_hint})
        section.pop("visual_hint", None)
        sections.append(section)
    if sections:
        plan["sections"] = sections
    if visual_slots:
        metadata = dict(plan.get("metadata") or {})
        metadata["visual_slots_sidecar"] = visual_slots
        plan["metadata"] = metadata
    if visual_sidecar:
        metadata = dict(plan.get("metadata") or {})
        metadata["visual_sidecar"] = visual_sidecar
        plan["metadata"] = metadata
    return plan


def _section_count(payload: Dict[str, Any]) -> int:
    return len([item for item in list((payload or {}).get("sections") or []) if isinstance(item, dict)])


def body_only_content_schema(content_schema: Dict[str, Any]) -> Dict[str, Any]:
    schema = dict(content_schema or {})
    blocks = []
    visual_sidecar: List[Dict[str, str]] = []
    for item in list(schema.get("blocks") or []):
        if not isinstance(item, dict):
            continue
        block = dict(item)
        title = str(block.get("title") or "").strip()
        visual_hint = str(block.get("visual_hint") or "").strip().lower()
        if title and visual_hint and visual_hint != "none":
            visual_sidecar.append({"title": title, "visual_hint": visual_hint})
        block.pop("visual_hint", None)
        blocks.append(block)
    if blocks:
        schema["blocks"] = blocks
    if visual_sidecar:
        metadata = dict(schema.get("metadata") or {})
        metadata["visual_sidecar"] = visual_sidecar
        schema["metadata"] = metadata
    return schema


def body_only_content_task_spec(content_task_spec: Dict[str, Any]) -> Dict[str, Any]:
    spec = dict(content_task_spec or {})
    spec.pop("visual_plan", None)

    goal = dict(spec.get("goal") or {})
    if goal:
        for key in ("outcome", "primary_action"):
            if key in goal:
                goal[key] = strip_visual_or_production_clauses(str(goal.get(key) or ""))
        secondary = [
            strip_visual_or_production_clauses(str(item))
            for item in list(goal.get("secondary_actions") or [])
            if strip_visual_or_production_clauses(str(item))
            and not is_visual_or_production_requirement(str(item))
        ]
        if secondary:
            goal["secondary_actions"] = secondary
        else:
            goal.pop("secondary_actions", None)
        spec["goal"] = goal

    medium = dict(spec.get("medium") or {})
    if medium:
        if "delivery_expectation" in medium:
            medium["delivery_expectation"] = strip_visual_or_production_clauses(str(medium.get("delivery_expectation") or ""))
        spec["medium"] = medium

    # Writer should not consume coarse required_elements / handoff / production constraints.
    spec.pop("constraints", None)
    spec.pop("artifact_contract", None)

    return spec


def body_only_contract_context(contract_context: Dict[str, Any] | None) -> Dict[str, Any]:
    ctx = dict(contract_context or {})
    ctx.pop("visual_contract", None)
    ctx.pop("visual_semantics", None)
    ctx.pop("production_contract", None)

    compose_policy = dict(ctx.get("compose_policy") or {})
    compose_policy.pop("visual_requirements", None)
    compose_policy.pop("writing_instructions", None)
    assembly_profile = dict(compose_policy.get("assembly_profile") or {})
    if assembly_profile:
        assembly_profile.pop("visual_density", None)
        compose_policy["assembly_profile"] = assembly_profile
    ctx["compose_policy"] = compose_policy

    prompt_contract = dict(ctx.get("prompt_contract") or {})
    prompt_contract.pop("visual_axes", None)
    prompt_contract.pop("must_include", None)
    ctx["prompt_contract"] = prompt_contract

    if isinstance(ctx.get("structure_contract"), dict):
        ctx["structure_contract"] = _strip_visual_sidecar_metadata(
            body_only_structure_contract(dict(ctx.get("structure_contract") or {}))
        )

    body_plan = ctx.get("body_plan") if isinstance(ctx.get("body_plan"), dict) else {}
    content_plan = ctx.get("content_plan") if isinstance(ctx.get("content_plan"), dict) else {}
    chosen_plan = body_plan if _section_count(body_plan) >= _section_count(content_plan) else content_plan
    if isinstance(chosen_plan, dict) and chosen_plan:
        ctx["content_plan"] = _strip_visual_sidecar_metadata(body_only_content_plan(dict(chosen_plan or {})))
    ctx.pop("body_plan", None)
    if isinstance(ctx.get("content_task_spec"), dict):
        ctx["content_task_spec"] = body_only_content_task_spec(dict(ctx.get("content_task_spec") or {}))
    return ctx


def body_only_strategy(strategy: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(strategy or {})
    out.pop("visual_policy", None)
    out.pop("visual_contract", None)
    out.pop("visual_semantics", None)
    out.pop("production_contract", None)
    return body_only_contract_context(out)
