"""High-confidence, read-only interaction classification.

This policy deliberately uses structural browser evidence before text.  It
only bypasses model effect discovery when the target is clearly a UI
transition (menu item, tab, option, popup controller, or an explicit editor
entry on a non-editor page).  Ambiguous buttons and mutation labels keep the
existing model/approval path.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation
from app.enterprise_capabilities.browser.engine.interaction_semantics import is_mutation_label

from .contracts import EffectContract


_NON_COMMIT_ROLES = frozenset({"tab", "option", "treeitem"})
_MENU_ROLES = frozenset({"menuitem", "menuitemcheckbox", "menuitemradio"})
_EXPLICIT_TRANSITION_LABEL = re.compile(
    r"^(?:新的创作|新建文章|新建图文|撰写文章|写文章|文章编辑|"
    r"进入.{0,24}(?:编辑|详情)|查看详情|打开(?:详情|菜单)?|返回|取消|"
    r"new\s+(?:article|post|draft)|create\s+new\s+(?:article|post|draft)|"
    r"open(?:\s+(?:details|menu|editor))?|view\s+details|back|cancel)$",
    re.I,
)


def local_read_only_interaction_contract(
    target: Mapping[str, Any],
    before: Observation,
) -> EffectContract | None:
    """Return a local non-commit contract only for unambiguous UI movement."""
    label = _target_label(target)
    role = str(target.get("role") or "").strip().casefold()
    description = str(target.get("description") or "").strip().casefold()
    mutation_label = is_mutation_label(label)

    # A destructive or externally-visible label always keeps the guarded
    # effect path, even when a component exposes imperfect menu semantics.
    if mutation_label:
        return None

    if _is_popup_controller(target):
        return _transition_contract(label or "open popup", family="open_popup")

    if role in _NON_COMMIT_ROLES:
        return _transition_contract(label or role, family="select_view")

    if role in _MENU_ROLES or "interaction_surface=popup_menu_item" in description:
        return _transition_contract(label or "select menu item", family="select_menu_item")

    # Text-only transition recognition is intentionally narrower and only
    # applies before an editor/form is present.  A button with the same copy
    # inside a form can submit custom state and must not bypass verification.
    if not _has_editable_context(before) and _EXPLICIT_TRANSITION_LABEL.fullmatch(label):
        return _transition_contract(label, family="transition")

    return None


def _is_popup_controller(target: Mapping[str, Any]) -> bool:
    has_popup = str(target.get("hasPopup") or target.get("has_popup") or "").strip().casefold()
    controls = str(target.get("controlsId") or target.get("controls_id") or "").strip()
    expanded = target.get("expanded")
    return bool(has_popup or controls or isinstance(expanded, bool))


def _has_editable_context(observation: Observation) -> bool:
    return any(
        isinstance(item, Mapping)
        and (
            bool(item.get("editable"))
            or str(item.get("role") or "").casefold() in {"textbox", "searchbox", "combobox"}
        )
        for item in list(observation.elements or [])
    )


def _target_label(target: Mapping[str, Any]) -> str:
    for key in ("name", "text", "value", "aria_label"):
        value = re.sub(r"\s+", " ", str(target.get(key) or "")).strip()
        if value:
            return value[:160]
    return ""


def _transition_contract(label: str, *, family: str) -> EffectContract:
    return EffectContract(
        action_name=label or "navigate interface",
        operation_family=family,
        side_effect="none",
        is_commit=False,
        completes_goal=False,
        source="local_rule",
    )


__all__ = ["local_read_only_interaction_contract"]
