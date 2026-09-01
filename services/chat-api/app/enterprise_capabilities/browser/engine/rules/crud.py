"""CRUD entry-discovery rules.

Three tiers per operation, higher tier = lower priority fallback:
  Tier 1   Named match — name or description contains verb token
  Tier 2   Unlabeled icon whose description carries a verb token
           (observer often stamps iconfont class / aria-label into
           description)
  Tier 3   Structural fallback — small-page blanket listing

No per-site class names anywhere — only verb tokens from ``tokens/``
plus ARIA roles.
"""
from __future__ import annotations

from typing import Any, Dict, List

from . import matchers as M
from .candidate_set import CandidateSet
from .tokens import ADD, EDIT, DELETE, VIEW, CONFIRM


def _search_named_then_icon(
    elements: List[Dict[str, Any]], tokens, op: str,
) -> CandidateSet:
    """Shared tier-1 + tier-2 sweep for entry-style buttons."""
    named: List[Dict[str, Any]] = []
    icon: List[Dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict) or not M.is_interactive(el):
            continue
        if not M.has_any_token(el, tokens):
            continue
        (named if M.name_text(el) else icon).append(M.entry(el))
    if named:
        return CandidateSet(op=op, tier=1, items=named[:8], reason=f"{op}:named")
    if icon:
        return CandidateSet(op=op, tier=2, items=icon[:8], reason=f"{op}:icon_token")
    return CandidateSet(op=op, tier=3, items=[], reason=f"{op}:no_token_match")


def find_create(elements: List[Dict[str, Any]]) -> CandidateSet:
    return _search_named_then_icon(elements, ADD, op="create")


def find_read(
    elements: List[Dict[str, Any]], target: str, page_kind: str,
) -> CandidateSet:
    if page_kind == "detail_of_target":
        return CandidateSet(op="read", tier=0, items=[], reason="read:already_on_detail")
    view = _search_named_then_icon(elements, VIEW, op="read")
    if view.items:
        return view
    # Fallback: elements whose name matches target (row or link)
    hits: List[Dict[str, Any]] = []
    if target:
        try:
            from app.enterprise_capabilities.browser.engine.agent_loop.planner import _find_target_matches
            hits = list(_find_target_matches(elements, target))
        except Exception:
            hits = []
    if hits:
        hits.sort(key=lambda m: 0 if str(m.get("role") or "") in ("row", "link") else 1)
        return CandidateSet(op="read", tier=2, items=hits[:8], reason="read:target_row")
    return CandidateSet(op="read", tier=3, items=[], reason="read:no_match")


def find_update(
    elements: List[Dict[str, Any]], target: str, page_kind: str,
) -> CandidateSet:
    base = _search_named_then_icon(elements, EDIT, op="update")
    if base.items:
        return base
    # Tier 3: on a small detail_of_target page, surface all unlabeled
    # affordances that look like the local "edit this entity" control.
    # We rank detail-page candidates instead of blindly returning every
    # icon, so rules stay useful on toolbars with many icon buttons.
    if page_kind == "detail_of_target":
        scored: List[tuple[int, Dict[str, Any]]] = []
        for e in elements:
            if not isinstance(e, dict) or not M.is_interactive(e):
                continue
            desc = M.description_text(e)
            if not desc:
                continue
            role = str(e.get("role") or "").lower()
            hay = f"{M.name_text(e)} {desc}".lower()
            if _is_global_nav_like(e):
                continue
            if role not in ("button", "link"):
                continue
            if not (M.is_unlabeled_icon(e) or M.has_any_token(e, EDIT) or (target and target.lower() in hay)):
                continue
            score = 0
            if role == "button":
                score += 5
            elif role in ("link", "menuitem"):
                score += 2
            if M.is_unlabeled_icon(e):
                score += 2
            if target and target.lower() in hay:
                score += 3
            if M.has_any_token(e, EDIT):
                score += 8
            if "区域:" in desc or "region:" in desc.lower():
                score += 1
            if "semantic=" in desc.lower():
                score += 2
            if M.has_any_token(e, DELETE) or M.has_any_token(e, ADD) or M.has_any_token(e, CONFIRM):
                score -= 6
            if M.has_any_token(e, VIEW):
                score -= 2
            if score > 0:
                scored.append((score, M.entry(e)))
        if scored:
            scored.sort(key=lambda item: (-item[0], len(str(item[1].get("description") or ""))))
            top = [entry for _, entry in scored[:8]]
            return CandidateSet(op="update", tier=3, items=top,
                                reason="update:ranked_detail_affordances")
    return CandidateSet(op="update", tier=3, items=[], reason="update:no_match")


def find_delete(
    elements: List[Dict[str, Any]], target: str, page_kind: str,
) -> CandidateSet:
    base = _search_named_then_icon(elements, DELETE, op="delete")
    if base.items:
        return base
    if page_kind == "detail_of_target":
        scored: List[tuple[int, Dict[str, Any]]] = []
        for e in elements:
            if not isinstance(e, dict) or not M.is_interactive(e):
                continue
            desc = M.description_text(e)
            if not desc:
                continue
            role = str(e.get("role") or "").lower()
            hay = f"{M.name_text(e)} {desc}".lower()
            if _is_global_nav_like(e):
                continue
            if role not in ("button", "link"):
                continue
            if not (M.is_unlabeled_icon(e) or M.has_any_token(e, DELETE) or (target and target.lower() in hay)):
                continue
            score = 0
            if role == "button":
                score += 5
            elif role in ("link", "menuitem"):
                score += 2
            if M.is_unlabeled_icon(e):
                score += 2
            if target and target.lower() in hay:
                score += 2
            if M.has_any_token(e, DELETE):
                score += 8
            if "semantic=" in desc.lower():
                score += 2
            if M.has_any_token(e, ADD) or M.has_any_token(e, EDIT) or M.has_any_token(e, CONFIRM):
                score -= 5
            if score > 0:
                scored.append((score, M.entry(e)))
        if scored:
            scored.sort(key=lambda item: (-item[0], len(str(item[1].get("description") or ""))))
            top = [entry for _, entry in scored[:8]]
            return CandidateSet(op="delete", tier=3, items=top,
                                reason="delete:ranked_detail_affordances")
    return CandidateSet(op="delete", tier=3, items=[], reason="delete:no_match")


def find_confirm(elements: List[Dict[str, Any]]) -> CandidateSet:
    """Post-action confirm dialog. Only fires when a dialog is present
    — otherwise CONFIRM tokens would match the main form's Save button."""
    if not M.dialog_open(elements):
        return CandidateSet(op="confirm", tier=0, items=[], reason="confirm:no_dialog")
    named: List[Dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict) or not M.is_interactive(el):
            continue
        if M.has_any_token(el, CONFIRM) and M.name_text(el):
            named.append(M.entry(el))
    if named:
        return CandidateSet(op="confirm", tier=1, items=named[:4], reason="confirm:named")
    return CandidateSet(op="confirm", tier=3, items=[], reason="confirm:no_match")


def _is_global_nav_like(el: Dict[str, Any]) -> bool:
    role = str(el.get("role") or "").lower()
    hay = f"{M.name_text(el)} {M.description_text(el)}".lower()
    if role in ("menubar", "menuitem"):
        return True
    nav_tokens = (
        "菜单", "menu", "menubar", "导航", "nav", "navbar",
        "首页", "home", "链接", "link", "用户", "账号",
        "登录", "退出", "plugin", "botmain", "database",
        "chat_", "chat/", "统计", "报表",
    )
    return any(tok in hay for tok in nav_tokens)


def resolve(
    op: str, elements: List[Dict[str, Any]],
    target: str = "", page_kind: str = "unknown",
) -> CandidateSet:
    """Single dispatch for all CRUD ops. Callers branch on ``.action``."""
    if op == "create":
        return find_create(elements)
    if op == "read":
        return find_read(elements, target, page_kind)
    if op == "update":
        return find_update(elements, target, page_kind)
    if op == "delete":
        return find_delete(elements, target, page_kind)
    if op == "confirm":
        return find_confirm(elements)
    return CandidateSet(op=op, tier=3, items=[], reason=f"unknown_op:{op}")
