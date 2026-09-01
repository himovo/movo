"""Causal bindings between a form transaction and its commit controls."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from app.enterprise_capabilities.browser.engine.effect_verification.interaction_relation import (
    resolve_action_fields_relation,
)
from app.enterprise_capabilities.browser.engine.effect_verification.scope_identity import selector_contains
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from .contracts import FieldDescriptor


@dataclass(frozen=True)
class CommitControlState:
    disabled: bool
    visible: bool
    hit_testable: bool


@dataclass(frozen=True)
class RejectedCommitControl:
    key: str
    label: str
    reason: str
    stage_key: str
    hits: int = 1


class CommitBindingLedger:
    """Remember commit controls that react to fields changed by this transaction."""

    def __init__(self) -> None:
        self._known_states: Dict[str, CommitControlState] = {}
        self._field_snapshots: Dict[str, Dict[str, Any]] = {}
        self._bound_action_keys: set[str] = set()
        self._rejected_actions: Dict[str, RejectedCommitControl] = {}
        self._stage_key = ""
        self._baseline_observed = False

    @property
    def bound_action_keys(self) -> set[str]:
        return set(self._bound_action_keys)

    def observe(
        self,
        *,
        candidates: Iterable[Dict[str, Any]],
        fields: Iterable[FieldDescriptor],
        mutated_field_keys: Iterable[str],
        page_url: str = "",
    ) -> None:
        field_list = list(fields)
        self._reconcile_stage(page_url=page_url, fields=field_list)
        for field in field_list:
            self._field_snapshots[field.field_key] = dict(field.raw)

        mutated = {
            str(item or "").strip()
            for item in mutated_field_keys
            if str(item or "").strip()
        }
        active_fields = [
            self._field_snapshots[key]
            for key in mutated
            if key in self._field_snapshots
        ]
        current: Dict[str, tuple[Dict[str, Any], CommitControlState]] = {}
        for candidate in candidates:
            key = commit_control_key(candidate)
            if not key:
                continue
            current[key] = (candidate, _control_state(candidate))

        if not mutated:
            self._baseline_observed = True
        elif self._baseline_observed and active_fields:
            for key, (candidate, state) in current.items():
                relation = resolve_action_fields_relation(
                    action=candidate,
                    fields=active_fields,
                )
                if relation.status == "unrelated":
                    continue
                previous = self._known_states.get(key)
                locally_related = relation.related or _inside_field_component(
                    candidate,
                    active_fields,
                )
                if (
                    previous is not None
                    and previous.disabled
                    and not state.disabled
                ):
                    self._bound_action_keys.add(key)
                    self._rejected_actions.pop(key, None)
                elif (
                    locally_related
                    and (
                        previous is None
                        or _became_visible_or_hit_testable(previous, state)
                    )
                ):
                    self._bound_action_keys.add(key)
                    self._rejected_actions.pop(key, None)

        self._known_states.update(
            {key: state for key, (_, state) in current.items()}
        )

    def reject(
        self,
        *,
        target: Dict[str, Any],
        fields: Iterable[FieldDescriptor],
        reason: str,
        page_url: str = "",
    ) -> None:
        field_list = list(fields)
        self._reconcile_stage(page_url=page_url, fields=field_list)
        key = commit_control_key(target)
        if not key or key in self._bound_action_keys:
            return
        previous = self._rejected_actions.get(key)
        self._rejected_actions[key] = RejectedCommitControl(
            key=key,
            label=_control_label(target),
            reason=str(reason or "control is not bound to the active form"),
            stage_key=self._stage_key,
            hits=(previous.hits + 1 if previous else 1),
        )

    def is_rejected_decision(
        self,
        decision: Decision,
        observation: Observation,
        *,
        fields: Iterable[FieldDescriptor],
    ) -> bool:
        field_list = list(fields)
        self._reconcile_stage(page_url=observation.url, fields=field_list)
        if decision.tool != "browser_click":
            return False
        target = _target_by_ref(
            observation,
            str((decision.args or {}).get("ref") or "").strip(),
        )
        return bool(
            target
            and commit_control_key(target) in self._rejected_actions
        )

    def augment_planner_state(
        self,
        *,
        observation: Observation,
        fields: Iterable[FieldDescriptor],
        state_ledger: Optional[Dict[str, Any]],
        repeated_selection: bool = False,
    ) -> Optional[Dict[str, Any]]:
        field_list = list(fields)
        self._reconcile_stage(page_url=observation.url, fields=field_list)
        if not self._rejected_actions:
            return state_ledger

        live_rejected = [
            item for item in observation.elements
            if isinstance(item, dict)
            and commit_control_key(item) in self._rejected_actions
        ]
        rejected_refs = [
            str(item.get("ref") or "").strip()
            for item in live_rejected
            if str(item.get("ref") or "").strip()
        ]
        alternatives = _local_action_candidates(
            observation,
            fields=field_list,
            rejected_keys=set(self._rejected_actions),
        )
        alternative_refs = [
            str(item.get("ref") or "").strip()
            for item in alternatives
            if str(item.get("ref") or "").strip()
        ]

        ledger = dict(state_ledger or {})
        forbidden = list(ledger.get("forbidden_actions") or [])
        forbidden.append(
            "当前表单阶段禁止再次选择这些已确认不属于编辑器的控件："
            f"refs={rejected_refs or ['当前已消失']}。"
        )
        constraints = list(ledger.get("action_constraints") or [])
        constraints.append(
            "刚才选择的提交/发布控件不属于当前正在编辑的表单。"
            "不要重复选择它，也不要只重复观察；请从当前编辑器内其他实时控件中选择下一步。"
            + (
                f" 当前编辑器候选 refs={alternative_refs}。"
                if alternative_refs else
                " 当前没有可靠候选时，应明确说明缺少可继续的表单内控件。"
            )
        )
        if repeated_selection:
            constraints.append(
                "模型刚刚再次选择了已被拒绝的控件。本轮必须改选其他候选，"
                "不得返回同一 ref。"
            )
        notes = list(ledger.get("notes") or [])
        notes.append(
            "被拒绝控件："
            + "；".join(
                f"{item.label or item.key}（{item.reason}，已拒绝 {item.hits} 次）"
                for item in self._rejected_actions.values()
            )
        )
        if alternatives:
            notes.append(
                "当前编辑器内可重新评估的控件："
                + "；".join(
                    f"{item.get('ref')}={_control_label(item) or item.get('role') or 'action'}"
                    for item in alternatives[:12]
                )
            )
        pinned = list(ledger.get("pinned_refs") or [])
        pinned.extend(alternative_refs)
        ledger.update({
            "forbidden_actions": list(dict.fromkeys(str(item) for item in forbidden)),
            "action_constraints": list(dict.fromkeys(str(item) for item in constraints)),
            "notes": list(dict.fromkeys(str(item) for item in notes)),
            "pinned_refs": list(dict.fromkeys(
                str(item) for item in pinned
                if str(item) and str(item) not in set(rejected_refs)
            )),
        })
        return ledger

    def reset(self) -> None:
        self._known_states.clear()
        self._field_snapshots.clear()
        self._bound_action_keys.clear()
        self._rejected_actions.clear()
        self._stage_key = ""
        self._baseline_observed = False

    def _reconcile_stage(
        self,
        *,
        page_url: str,
        fields: Iterable[FieldDescriptor],
    ) -> None:
        stage_key = _form_stage_key(page_url, fields)
        if self._stage_key and stage_key and stage_key != self._stage_key:
            self._rejected_actions.clear()
        if stage_key:
            self._stage_key = stage_key


def commit_control_key(element: Dict[str, Any]) -> str:
    """Return an observation-stable identity without relying on ephemeral refs."""
    frame = int(element.get("frameDepth") or 0)
    selector = str(element.get("selector") or "").strip()
    if selector:
        return f"{frame}:selector:{selector}"

    form_owner = str(element.get("formOwnerSelector") or "").strip()
    associated = "|".join(sorted(
        str(item or "").strip()
        for item in list(element.get("associatedFieldSelectors") or [])
        if str(item or "").strip()
    ))
    scope = str(
        element.get("scopeId")
        or element.get("scopeSelector")
        or ""
    ).strip()
    role = str(element.get("role") or element.get("type") or "").strip().casefold()
    label = " ".join(
        str(element.get(key) or "").strip()
        for key in ("name", "text", "value")
    ).strip().casefold()
    if not any((form_owner, associated, scope, role, label)):
        return ""
    return f"{frame}:semantic:{form_owner}:{associated}:{scope}:{role}:{label}"


def _control_state(element: Dict[str, Any]) -> CommitControlState:
    return CommitControlState(
        disabled=bool(element.get("disabled")),
        visible=element.get("visible") is not False,
        hit_testable=element.get("hitTestable") is not False,
    )


def _became_visible_or_hit_testable(
    before: CommitControlState,
    after: CommitControlState,
) -> bool:
    if not before.visible and after.visible:
        return True
    return not before.hit_testable and after.hit_testable


def _inside_field_component(
    action: Dict[str, Any],
    fields: Iterable[Dict[str, Any]],
) -> bool:
    action_selector = str(action.get("selector") or "").strip()
    if not action_selector:
        return False
    for field in fields:
        scope_selector = str(
            field.get("scopeSelector")
            or field.get("scope_selector")
            or ""
        ).strip()
        if scope_selector and selector_contains(scope_selector, action_selector):
            return True
    return False


def _form_stage_key(page_url: str, fields: Iterable[FieldDescriptor]) -> str:
    stable_fields = sorted(
        (
            int(field.raw.get("frameDepth") or 0),
            str(field.scope_id or field.raw.get("scopeId") or "").strip(),
            str(field.field_key or "").strip(),
        )
        for field in fields
        if field.control_kind != "file"
    )
    if not stable_fields:
        return ""
    return f"{str(page_url or '').strip()}\0{stable_fields!r}"


def _target_by_ref(
    observation: Observation,
    ref: str,
) -> Optional[Dict[str, Any]]:
    if not ref:
        return None
    return next((
        item for item in observation.elements
        if isinstance(item, dict)
        and str(item.get("ref") or "").strip() == ref
    ), None)


def _local_action_candidates(
    observation: Observation,
    *,
    fields: Iterable[FieldDescriptor],
    rejected_keys: set[str],
) -> list[Dict[str, Any]]:
    field_list = list(fields)
    scope_ids = {
        str(field.scope_id or field.raw.get("scopeId") or "").strip()
        for field in field_list
        if str(field.scope_id or field.raw.get("scopeId") or "").strip()
    }
    scope_selectors = {
        str(field.raw.get("scopeSelector") or "").strip()
        for field in field_list
        if str(field.raw.get("scopeSelector") or "").strip()
    }
    candidates: list[Dict[str, Any]] = []
    for item in observation.elements:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or "").strip()
        role = str(item.get("role") or "").strip().casefold()
        if (
            not ref
            or item.get("disabled")
            or item.get("visible") is False
            or item.get("hitTestable") is False
            or item.get("editable")
            or role not in {"button", "link", "menuitem", "tab"}
            or commit_control_key(item) in rejected_keys
        ):
            continue
        item_scope = str(item.get("scopeId") or "").strip()
        item_scope_selector = str(item.get("scopeSelector") or "").strip()
        item_selector = str(item.get("selector") or "").strip()
        same_local_scope = bool(item_scope and item_scope in scope_ids)
        inside_local_scope = any(
            selector and (
                selector_contains(selector, item_scope_selector)
                or selector_contains(selector, item_selector)
            )
            for selector in scope_selectors
            if item_scope_selector or item_selector
        )
        if same_local_scope or inside_local_scope:
            candidates.append(item)
        if len(candidates) >= 24:
            break
    return candidates


def _control_label(element: Dict[str, Any]) -> str:
    return " ".join(
        str(element.get(key) or "").strip()
        for key in ("name", "text", "description")
        if str(element.get(key) or "").strip()
    )[:180]


__all__ = [
    "CommitBindingLedger",
    "CommitControlState",
    "RejectedCommitControl",
    "commit_control_key",
]
