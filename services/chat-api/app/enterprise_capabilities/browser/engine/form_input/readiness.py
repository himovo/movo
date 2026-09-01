"""Page-level guard for consuming business form input artifacts."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.enterprise_capabilities.browser.engine.rules import matchers
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation

from .contracts import FieldDescriptor
from .commit_resolver import is_semantic_commit_control
from .inventory import is_business_form
from .scopes import elements_in_scope, group_fields_by_scope, has_explicit_scope


_SEARCH_TOKENS = ("search", "query", "find", "搜索", "查询", "查找", "筛选")
_COMMIT_TOKENS = (
    "submit", "publish", "send", "save", "confirm", "post", "reply",
    "提交", "发布", "发送", "保存", "确认", "回复", "评论", "创建", "新建",
)


def is_ready_business_form(
    observation: Observation,
    fields: List[FieldDescriptor],
) -> bool:
    """Require coherent form evidence, not just an incidental editable node."""
    return bool(ready_business_form_scopes(observation, fields))


def ready_business_form_scopes(
    observation: Observation,
    fields: List[FieldDescriptor],
) -> Dict[str, List[FieldDescriptor]]:
    ready: Dict[str, List[FieldDescriptor]] = {}
    for scope_id, scoped_fields in group_fields_by_scope(fields).items():
        if _scope_is_ready(observation, scope_id, scoped_fields):
            ready[scope_id] = scoped_fields
    return ready


def _scope_is_ready(
    observation: Observation,
    scope_id: str,
    fields: List[FieldDescriptor],
) -> bool:
    if not is_business_form(fields):
        return False

    visible = [field for field in fields if field.raw.get("visible") is not False]
    usable = [field for field in visible if not field.sensitive and not _is_search_field(field)]
    if not usable:
        return False
    scoped_elements = elements_in_scope(observation.elements or [], scope_id)
    has_commit = _has_commit_action(scoped_elements) or _has_structural_commit_evidence(usable)
    semantic_scope = has_explicit_scope(scope_id) and any(
        field.scope_role in {"form", "dialog", "alertdialog"} for field in usable
    )
    if any(field.required for field in usable):
        # A required field is strong form evidence even when a framework has
        # not rendered the next/submit control yet. Collection surfaces are
        # still protected by FormInteractionStage before this scope can run.
        return True
    if len(usable) >= 2:
        return has_commit or semantic_scope or _is_structured_content_editor(usable)

    # Single rich-text editors are common for comments and replies. They are
    # considered ready only when the same page also exposes a commit action.
    only = usable[0]
    if only.control_kind not in {"multiline", "rich_text", "file"}:
        return False
    return has_commit or _has_latent_commit_action(scoped_elements, only)


def _is_structured_content_editor(fields: Iterable[FieldDescriptor]) -> bool:
    """Recognize title/body authoring surfaces before a remote submit appears."""

    candidates = list(fields)
    has_rich_body = any(
        field.control_kind == "rich_text"
        or bool(field.raw.get("contentEditable"))
        or bool(field.raw.get("content_editable"))
        for field in candidates
    )
    has_companion_field = any(
        field.control_kind in {"text", "multiline"}
        and not _is_search_field(field)
        for field in candidates
    )
    return has_rich_body and has_companion_field


def _is_search_field(field: FieldDescriptor) -> bool:
    if field.role == "searchbox":
        return True
    if field.raw.get("searchContext") or field.raw.get("search_context"):
        return True
    text = " ".join((field.name, field.placeholder, field.description)).casefold()
    return any(token in text for token in _SEARCH_TOKENS)


def _has_commit_action(elements: Iterable[Any]) -> bool:
    for element in elements:
        if not isinstance(element, dict) or not matchers.is_interactive(element):
            continue
        if element.get("disabled") or element.get("visible") is False:
            continue
        text = matchers.haystack(element)
        if any(token in text for token in _COMMIT_TOKENS):
            return True
    return False


def _has_structural_commit_evidence(fields: Iterable[FieldDescriptor]) -> bool:
    """Recognize a focused editor whose disabled commit control is snapshot-only text.

    Some rich editors render their commit control as a disabled, non-semantic
    element until content is entered.  Native CDP therefore sees the editor's
    compact interaction scope and its text, but no independently clickable
    commit element.  Treat that as form-readiness evidence only for a focused
    editor in a lockable local scope; broad page text must never activate a
    form.
    """
    for field in fields:
        if field.control_kind not in {"multiline", "rich_text"}:
            continue
        raw = field.raw
        if not raw.get("focused") or raw.get("scopeLockable") is not True:
            continue
        scope_text = str(raw.get("scopeText") or raw.get("scope_text") or "").casefold()
        if any(token in scope_text for token in _COMMIT_TOKENS):
            return True
    return False


def _has_latent_commit_action(
    elements: Iterable[Any],
    field: FieldDescriptor,
) -> bool:
    """Recognize a local submit control that becomes enabled after input.

    Comment, reply and message editors commonly render their submit button
    disabled until the first character is entered. The disabled control is
    valid form-structure evidence, but never an executable action: the commit
    resolver still refreshes the DOM and requires an enabled control before
    clicking it.
    """
    if field.raw.get("scopeLockable") is not True:
        return False
    for element in elements:
        if not isinstance(element, dict) or not element.get("disabled"):
            continue
        if is_semantic_commit_control(element, require_hit_testable=False):
            return True
    return False


__all__ = ["is_ready_business_form", "ready_business_form_scopes"]
