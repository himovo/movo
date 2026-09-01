from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Dict, List, Tuple

from .contracts import FieldBinding, FieldDescriptor
from .input_context import BrowserInputContext, InputCandidate


_SEMANTIC_GROUPS = {
    "title": {"title", "subject", "headline", "标题", "主题", "名称"},
    "body": {
        "body", "content", "markdown", "article", "report", "description", "detail", "message",
        "正文", "内容", "文章", "报告", "描述", "详情", "说明", "备注", "消息",
    },
    "recipient": {"recipient", "receiver", "email", "address", "to", "收件人", "接收人", "邮箱", "邮件地址"},
    "attachment": {
        "attachment", "file", "document", "upload", "image", "images", "media",
        "visual", "visuals", "附件", "文件", "文档", "上传", "图片", "配图", "媒体",
    },
}


def resolve_deterministic(
    fields: List[FieldDescriptor], context: BrowserInputContext,
) -> Tuple[Dict[str, FieldBinding], List[FieldDescriptor]]:
    resolved = _unique_structural_bindings(fields, context)
    ambiguous_candidate_ids = _candidate_ids_with_competing_fields(
        fields,
        context,
        already_resolved=resolved,
    )
    unresolved: List[FieldDescriptor] = []
    for field in fields:
        if field.current_value.strip():
            continue
        if field.field_key in resolved:
            continue
        if field.sensitive:
            unresolved.append(field)
            continue
        ranked = sorted(
            ((_candidate_score(field, candidate), candidate) for candidate in context.candidates),
            key=lambda item: item[0],
            reverse=True,
        )
        if not ranked or ranked[0][0] < 0.88:
            unresolved.append(field)
            continue
        if ranked[0][1].candidate_id in ambiguous_candidate_ids:
            unresolved.append(field)
            continue
        if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.08:
            unresolved.append(field)
            continue
        score, candidate = ranked[0]
        binding = _binding(field, candidate, score)
        if binding is None:
            unresolved.append(field)
            continue
        resolved[field.field_key] = binding
    return resolved, unresolved


def _candidate_ids_with_competing_fields(
    fields: List[FieldDescriptor],
    context: BrowserInputContext,
    *,
    already_resolved: Dict[str, FieldBinding],
) -> set[str]:
    """Do not deterministically reuse one value across multiple empty fields."""
    matches: Dict[str, set[str]] = {}
    for field in fields:
        if (
            field.field_key in already_resolved
            or field.current_value.strip()
            or field.sensitive
        ):
            continue
        for candidate in context.candidates:
            if _candidate_score(field, candidate) >= 0.88:
                matches.setdefault(candidate.candidate_id, set()).add(field.field_key)
    return {
        candidate_id
        for candidate_id, field_keys in matches.items()
        if len(field_keys) > 1
    }


def _unique_structural_bindings(
    fields: List[FieldDescriptor],
    context: BrowserInputContext,
) -> Dict[str, FieldBinding]:
    """Bind unlabelled editor/file controls only when both sides are unique."""
    resolved: Dict[str, FieldBinding] = {}
    rich_body_fields = [
        field for field in fields
        if field.control_kind == "rich_text"
        and not field.current_value.strip()
        and not field.sensitive
    ]
    multiline_body_fields = [
        field for field in fields
        if field.control_kind == "multiline"
        and not field.current_value.strip()
        and not field.sensitive
    ]
    # A browser editor commonly uses a textarea for its title and one
    # contenteditable surface for the body. Prefer the unique rich editor;
    # only fall back to a multiline control when no rich editor exists.
    body_fields = (
        rich_body_fields
        if len(rich_body_fields) == 1
        else multiline_body_fields if not rich_body_fields else []
    )
    body_candidates = [
        candidate for candidate in context.candidates
        if candidate.value_kind != "file"
        and "body" in _groups(_terms(candidate.semantic_name))
    ]
    if len(body_fields) == 1 and len(body_candidates) == 1:
        binding = _binding(body_fields[0], body_candidates[0], 0.94)
        if binding is not None:
            binding.rationale = "唯一正文编辑器与唯一上游正文产物结构匹配"
            resolved[body_fields[0].field_key] = binding

    file_fields = [
        field for field in fields
        if field.control_kind == "file"
        and not field.current_value.strip()
        and not field.sensitive
    ]
    file_candidates = [
        candidate for candidate in context.candidates
        if candidate.value_kind == "file"
    ]
    if len(file_fields) == 1 and len(file_candidates) == 1:
        binding = _binding(file_fields[0], file_candidates[0], 0.94)
        if binding is not None:
            binding.rationale = "唯一文件上传控件与唯一上游媒体产物结构匹配"
            resolved[file_fields[0].field_key] = binding
    return resolved


def _binding(field: FieldDescriptor, candidate: InputCandidate, score: float) -> FieldBinding | None:
    if field.control_kind == "file":
        if candidate.value_kind != "file":
            return None
        return FieldBinding(
            field_key=field.field_key,
            action="upload",
            source_kind="attachment",
            value=list(candidate.value or []),
            candidate_id=candidate.candidate_id,
            source_path=candidate.source_path,
            confidence=score,
            rationale="附件字段与上游文件产物高置信匹配",
        )
    if candidate.value_kind == "file":
        return None
    value = str(candidate.value or "")
    if field.control_kind == "select":
        option = _matching_option(value, field.options)
        if not option:
            return None
        return FieldBinding(
            field_key=field.field_key,
            action="select",
            source_kind="selection",
            value=option,
            candidate_id=candidate.candidate_id,
            source_path=candidate.source_path,
            confidence=score,
            rationale="上游值与页面选项精确匹配",
        )
    return FieldBinding(
        field_key=field.field_key,
        action="fill",
        source_kind="user_input" if candidate.source_kind == "user_input" else "upstream",
        value=value,
        candidate_id=candidate.candidate_id,
        source_path=candidate.source_path,
        plain_text=candidate.plain_text,
        rich_html=candidate.rich_html,
        confidence=score,
        rationale="字段语义与已有输入产物高置信匹配",
    )


def _candidate_score(field: FieldDescriptor, candidate: InputCandidate) -> float:
    if field.control_kind == "file" and candidate.value_kind != "file":
        return 0.0
    if field.control_kind != "file" and candidate.value_kind == "file":
        return 0.0
    # Placeholder text is frequently dynamic (for example rotating search
    # suggestions).  It may be shown to a model as a hint, but cannot support a
    # deterministic high-confidence binding.
    field_terms = _terms(" ".join((
        field.name,
        field.description,
        field.semantic_label if field.semantic_label != field.label else "",
    )))
    candidate_terms = _terms(candidate.semantic_name)
    if not field_terms or not candidate_terms:
        return 0.0
    field_groups = _groups(field_terms)
    candidate_groups = _groups(candidate_terms)
    if field_groups & candidate_groups:
        return 0.96
    field_text = "".join(sorted(field_terms))
    candidate_text = "".join(sorted(candidate_terms))
    if field_text == candidate_text:
        return 1.0
    if field_terms & candidate_terms:
        return 0.9
    ratio = SequenceMatcher(None, field_text, candidate_text).ratio()
    return ratio * 0.82


def _groups(terms: set[str]) -> set[str]:
    result = set()
    for group, aliases in _SEMANTIC_GROUPS.items():
        if any(_semantic_term_matches(term, alias) for term in terms for alias in aliases):
            result.add(group)
    return result


def _semantic_term_matches(term: str, alias: str) -> bool:
    if term == alias:
        return True
    # English identifiers are already split on snake/camel/punctuation;
    # substring matching would make short aliases such as "to" match
    # unrelated words such as "content". Chinese labels are not naturally
    # tokenized, so retain conservative multi-character containment there.
    if re.search(r"[\u4e00-\u9fff]", term + alias):
        return len(term) >= 2 and len(alias) >= 2 and (term in alias or alias in term)
    return False


def _terms(value: str) -> set[str]:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value or ""))
    return {
        token.casefold()
        for token in re.split(r"[^A-Za-z0-9\u4e00-\u9fff]+", expanded)
        if token.strip()
    }


def _matching_option(value: str, options: List[str]) -> str:
    normalized = _normalize(value)
    for option in options:
        if _normalize(option) == normalized:
            return option
    return ""


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()
