"""Generic activation gate for forms embedded in search/list surfaces."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set
from urllib.parse import parse_qs, urlsplit

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord

from .contracts import FieldDescriptor
from .scopes import element_scope_id


_SEARCH_WORDS = re.compile(r"(?:search|results?|query|find|搜索|查询|筛选)", re.I)
_COLLECTION_PATH = re.compile(r"(?:^|/)(?:search|results?|list|feed|items?)(?:/|$)", re.I)
_EXPLICIT_OPENED_SCOPE_ROLES = {"dialog", "alertdialog", "form"}
_INTERACTION_TOOLS = {"browser_click", "browser_click_at"}


class FormInteractionStage:
    """Only activates an embedded form after an observable user/agent entry action."""

    def __init__(self) -> None:
        self._activated_scope_ids: Set[str] = set()

    def select_scope(
        self,
        observation: Observation,
        ready_scopes: Dict[str, List[FieldDescriptor]],
        history: Iterable[StepRecord] = (),
    ) -> str:
        self._reconcile_history(history)
        if not ready_scopes:
            return ""
        candidates = list(ready_scopes)
        if is_collection_surface(observation):
            candidates = [
                scope_id for scope_id in candidates
                if scope_id in self._activated_scope_ids
                or any(bool(field.raw.get("focused")) for field in ready_scopes[scope_id])
            ]
        if not candidates:
            return ""
        focused = next((
            scope_id for scope_id in candidates
            if any(bool(field.raw.get("focused")) for field in ready_scopes[scope_id])
        ), "")
        if focused:
            return focused
        activated = next((scope_id for scope_id in candidates if scope_id in self._activated_scope_ids), "")
        if activated:
            return activated
        required = next((
            scope_id for scope_id in candidates
            if any(field.required for field in ready_scopes[scope_id])
        ), "")
        return required or candidates[0]

    def record_transition(
        self,
        *,
        decision: Decision,
        ok: bool,
        before: Observation | None,
        after: Observation,
    ) -> None:
        if not ok or before is None or decision.tool not in _INTERACTION_TOOLS:
            return
        target = _target_for_decision(before, decision)
        target_scope = element_scope_id(target) if target else ""
        before_counts = _editable_counts(before.elements)
        after_counts = _editable_counts(after.elements)

        if target and target.get("editable") and target_scope:
            self._activated_scope_ids.add(target_scope)
        if target_scope and after_counts.get(target_scope, 0) > before_counts.get(target_scope, 0):
            self._activated_scope_ids.add(target_scope)

        for scope_id, count in after_counts.items():
            if count <= before_counts.get(scope_id, 0):
                continue
            role = _scope_role(after.elements, scope_id)
            if role in _EXPLICIT_OPENED_SCOPE_ROLES or not scope_id.startswith("__page__:"):
                self._activated_scope_ids.add(scope_id)

    def export_state(self) -> Dict[str, Any]:
        return {"activated_scope_ids": sorted(self._activated_scope_ids)}

    def restore_state(self, state: Any) -> None:
        if not isinstance(state, dict):
            return
        values = state.get("activated_scope_ids")
        if isinstance(values, list):
            self._activated_scope_ids = {str(item) for item in values if str(item).strip()}

    def _reconcile_history(self, history: Iterable[StepRecord]) -> None:
        records = list(history)[-24:]
        for index in range(1, len(records)):
            record = records[index]
            self.record_transition(
                decision=record.decision,
                ok=record.ok,
                before=records[index - 1].observation,
                after=record.observation,
            )


def is_collection_surface(observation: Observation) -> bool:
    elements = [item for item in observation.elements if isinstance(item, dict)]
    list_items = sum(
        1 for item in elements
        if str(item.get("role") or "").strip().lower() in {"listitem", "row", "article"}
    )
    search_fields = sum(1 for item in elements if _is_search_field(item))
    if search_fields and list_items >= 3:
        return True

    parsed = urlsplit(str(observation.url or ""))
    query_keys = {key.casefold() for key in parse_qs(parsed.query).keys()}
    url_signals_search = bool(_COLLECTION_PATH.search(parsed.path)) or bool(
        query_keys & {"q", "query", "search", "keyword", "keywords", "filter"}
    )
    return url_signals_search and list_items >= 2


def _is_search_field(item: Dict[str, Any]) -> bool:
    if item.get("searchContext") or item.get("search_context"):
        return True
    if str(item.get("role") or "").strip().lower() == "searchbox":
        return True
    text = " ".join(str(item.get(key) or "") for key in ("name", "placeholder", "description"))
    return bool(_SEARCH_WORDS.search(text)) and bool(item.get("editable"))


def _editable_counts(elements: Iterable[Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in elements:
        if not isinstance(item, dict) or item.get("disabled") or item.get("visible") is False:
            continue
        if not item.get("editable") and not item.get("contentEditable") and not item.get("content_editable"):
            continue
        scope_id = element_scope_id(item)
        counts[scope_id] = counts.get(scope_id, 0) + 1
    return counts


def _target_for_decision(observation: Observation, decision: Decision) -> Dict[str, Any]:
    ref = str((decision.args or {}).get("ref") or "").strip()
    if not ref:
        return {}
    return next((
        item for item in observation.elements
        if isinstance(item, dict) and str(item.get("ref") or "").strip() == ref
    ), {})


def _scope_role(elements: Iterable[Any], scope_id: str) -> str:
    for item in elements:
        if not isinstance(item, dict) or element_scope_id(item) != scope_id:
            continue
        return str(item.get("scopeRole") or item.get("scope_role") or "").strip().lower()
    return ""


__all__ = ["FormInteractionStage", "is_collection_surface"]
