from __future__ import annotations

from typing import Dict, List


_ARTICLE_FORMS = {"article", "post", "public_post", "newsletter"}
_REPORT_FORMS = {"report", "research_report", "analysis_report", "whitepaper", "handbook"}
_BRIEF_FORMS = {"brief", "memo", "document", "document_scale"}
_PLAN_FORMS = {"plan", "action_plan", "postmortem"}
_KNOWN_SECTION_ROLES = {
    "title",
    "opening_context",
    "background",
    "objective",
    "scope",
    "architecture",
    "module_overview",
    "core_function_detail",
    "interaction_flow",
    "data_metrics",
    "governance_constraints",
    "technical_notes",
    "risk_or_boundary",
    "analysis",
    "core_body",
    "closing",
}

_ROLE_LABELS_ZH: Dict[str, Dict[str, str]] = {
    "article": {
        "title": "标题",
        "opening_context": "导语",
        "background": "背景",
        "objective": "目标",
        "scope": "范围说明",
        "analysis": "分析",
        "core_body": "正文",
        "closing": "结尾",
    },
    "report": {
        "title": "标题",
        "opening_context": "背景",
        "background": "背景",
        "objective": "目标与范围",
        "scope": "范围与边界",
        "analysis": "核心分析",
        "governance_constraints": "规则与约束说明",
        "core_body": "核心内容",
        "closing": "结论与后续动作",
    },
    "brief": {
        "title": "标题",
        "opening_context": "背景",
        "background": "背景",
        "objective": "目标",
        "scope": "范围与边界",
        "analysis": "核心分析",
        "governance_constraints": "规则与约束说明",
        "core_body": "核心内容",
        "closing": "后续动作",
    },
    "plan": {
        "title": "标题",
        "opening_context": "背景",
        "background": "背景",
        "objective": "目标",
        "scope": "范围与前提",
        "analysis": "问题分析",
        "governance_constraints": "规则与约束说明",
        "core_body": "执行方案",
        "closing": "后续动作",
    },
}

_ROLE_LABELS_EN: Dict[str, Dict[str, str]] = {
    "article": {
        "title": "Title",
        "opening_context": "Lead",
        "background": "Background",
        "objective": "Objective",
        "scope": "Scope",
        "analysis": "Analysis",
        "core_body": "Body",
        "closing": "Conclusion",
    },
    "report": {
        "title": "Title",
        "opening_context": "Background",
        "background": "Background",
        "objective": "Objectives and Scope",
        "scope": "Scope and Constraints",
        "analysis": "Core Analysis",
        "governance_constraints": "Rules and Constraints",
        "core_body": "Core Content",
        "closing": "Conclusion and Next Steps",
    },
    "brief": {
        "title": "Title",
        "opening_context": "Background",
        "background": "Background",
        "objective": "Objective",
        "scope": "Scope and Constraints",
        "analysis": "Core Analysis",
        "governance_constraints": "Rules and Constraints",
        "core_body": "Core Content",
        "closing": "Next Steps",
    },
    "plan": {
        "title": "Title",
        "opening_context": "Background",
        "background": "Background",
        "objective": "Objective",
        "scope": "Scope and Assumptions",
        "analysis": "Problem Analysis",
        "governance_constraints": "Rules and Constraints",
        "core_body": "Execution Plan",
        "closing": "Next Steps",
    },
}


def contains_cjk(text: str) -> bool:
    for ch in str(text or ""):
        if "\u4e00" <= ch <= "\u9fff":
            return True
    return False


def resolve_language(*, text: str = "", language: str = "") -> str:
    raw = str(language or "").strip().lower()
    if raw in {"zh", "zh-cn", "zh-hans", "zh-hant"}:
        return "zh"
    if raw in {"en", "en-us", "en-gb"}:
        return "en"
    return "zh" if contains_cjk(text) else "en"


def localize_heading_label(label: str, *, language: str = "zh") -> str:
    text = str(label or "").strip()
    if not text:
        return text
    if resolve_language(text=text, language=language) != "zh":
        return text
    role = normalize_section_role(text)
    if role:
        return project_role_to_section_label(
            role,
            content_form="brief",
            publish_channel="generic",
            language="zh",
        )
    return text


def normalize_content_shape(*, content_form: str, publish_channel: str = "") -> str:
    form = str(content_form or "").strip().lower()
    if form in _ARTICLE_FORMS:
        return "article"
    if form in _REPORT_FORMS:
        return "report"
    if form in _PLAN_FORMS:
        return "plan"
    if form in _BRIEF_FORMS:
        return "brief"
    return "brief"


def default_section_roles(*, content_form: str, publish_channel: str = "") -> List[str]:
    return ["core_body"]


def infer_section_role(value: str) -> str:
    return normalize_section_role(value)


def normalize_section_role(value: str) -> str:
    token = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return token if token in _KNOWN_SECTION_ROLES else ""


def infer_section_roles(values: List[str]) -> List[str]:
    roles: List[str] = []
    for item in list(values or []):
        role = normalize_section_role(str(item or ""))
        if role and role not in roles:
            roles.append(role)
    return roles


def normalize_section_roles(values: List[str]) -> List[str]:
    roles: List[str] = []
    for item in list(values or []):
        role = normalize_section_role(str(item or "")) or infer_section_role(str(item or ""))
        if role and role not in roles:
            roles.append(role)
    return roles


def project_role_to_section_label(
    role: str,
    *,
    content_form: str,
    publish_channel: str = "",
    language: str = "zh",
) -> str:
    shape = normalize_content_shape(content_form=content_form, publish_channel=publish_channel)
    mapping = _ROLE_LABELS_ZH if resolve_language(language=language) == "zh" else _ROLE_LABELS_EN
    shape_mapping = mapping.get(shape) or mapping["brief"]
    return str(shape_mapping.get(role) or shape_mapping.get("core_body") or "").strip()


def project_section_roles(
    roles: List[str],
    *,
    content_form: str,
    publish_channel: str = "",
    language: str = "zh",
) -> List[str]:
    sections: List[str] = []
    for role in normalize_section_roles(roles):
        label = project_role_to_section_label(
            role,
            content_form=content_form,
            publish_channel=publish_channel,
            language=language,
        )
        if label and label not in sections:
            sections.append(label)
    return sections


def normalize_section_structure(
    *,
    sections: List[str],
    section_roles: List[str] | None = None,
    text: str = "",
    language: str = "",
    content_form: str = "",
    publish_channel: str = "",
) -> Dict[str, List[str]]:
    cleaned_sections: List[str] = []
    for item in list(sections or []):
        token = str(item or "").strip()
        if token and token not in cleaned_sections:
            cleaned_sections.append(token)

    normalized_language = resolve_language(text=text, language=language)
    explicit_roles = normalize_section_roles(section_roles or [])
    merged_roles = list(explicit_roles)
    projected_sections = list(cleaned_sections)

    if not projected_sections:
        projected_sections = project_section_roles(
            merged_roles,
            content_form=content_form,
            publish_channel=publish_channel,
            language=normalized_language,
        )

    return {
        "section_roles": merged_roles[:24],
        "required_sections": projected_sections[:24],
    }


def default_required_sections(*, content_form: str, publish_channel: str = "", language: str = "zh") -> List[str]:
    roles = default_section_roles(content_form=content_form, publish_channel=publish_channel)
    return project_section_roles(
        roles,
        content_form=content_form,
        publish_channel=publish_channel,
        language=language,
    )
