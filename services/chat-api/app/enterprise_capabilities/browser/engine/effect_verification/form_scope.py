"""DOM-scoped interaction lock for an in-progress browser form."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation
from app.enterprise_capabilities.browser.engine.form_input.identity import find_field

from .contracts import EffectReceipt
from .decision_target import resolve_effect_target
from .interaction_relation import resolve_action_fields_relation
from .scope_identity import ScopeIdentity, scope_identity, scope_present, scopes_related


_SCOPED_TOOLS = {
    "browser_fill",
    "browser_type_at",
    "browser_select",
    "browser_click",
    "browser_click_at",
    "browser_press",
    "browser_upload_file",
    "browser_paste_image",
}


@dataclass(frozen=True)
class ScopeBlocker:
    active_scope: str
    target_scope: str
    reason: str


class FormScopeLock:
    """Keep one form transaction inside the DOM container that owns it.

    The lock uses scope metadata emitted by the native-CDP DOM snapshot. It
    does not interpret site names, labels, placeholders, or action keywords.
    """

    def __init__(self) -> None:
        self._active: Optional[ScopeIdentity] = None
        self._started_url = ""
        self._field_target: Dict[str, Any] = {}

    @property
    def active(self) -> Optional[ScopeIdentity]:
        return self._active

    def record_confirmed_fill(
        self,
        target: Dict[str, Any],
        observation: Observation,
    ) -> None:
        identity = scope_identity(target)
        if identity is None:
            return
        self.reconcile(observation)
        if self._active is None:
            self._active = identity
            self._started_url = str(observation.url or "")
        if self._active is not None and scopes_related(self._active, identity):
            self._field_target = dict(target)

    def bind_press_target(self, decision: Decision, observation: Observation) -> Decision:
        """Attach the active field ref to a key press when UI focus is absent."""
        if decision.tool != "browser_press" or str((decision.args or {}).get("ref") or "").strip():
            return decision
        target = self.resolve_target(decision, observation)
        if target is None or not target.get("editable"):
            return decision
        args = dict(decision.args or {})
        args["ref"] = str(target.get("ref") or "")
        return Decision(tool=decision.tool, args=args, rationale=decision.rationale)

    def resolve_target(
        self,
        decision: Decision,
        observation: Observation,
    ) -> Optional[Dict[str, Any]]:
        if decision.tool == "browser_press":
            ref = str((decision.args or {}).get("ref") or "").strip()
            if ref:
                return _element_by_ref(observation, ref)
            focused = next((
                item for item in observation.elements
                if isinstance(item, dict) and item.get("focused")
            ), None)
            if focused is not None:
                return focused
            if self._field_target:
                located = find_field(observation.elements, self._field_target)
                if located is not None:
                    return located
            return None
        return _decision_target(decision, observation)

    def blocker(
        self,
        decision: Decision,
        observation: Observation,
        *,
        related_fields: Iterable[Dict[str, Any]] = (),
    ) -> Optional[ScopeBlocker]:
        self.reconcile(observation)
        active = self._active
        if active is None or decision.tool not in _SCOPED_TOOLS:
            return None

        target = self.resolve_target(decision, observation)
        target_scope = scope_identity(target or {})
        if target_scope is not None and scopes_related(active, target_scope):
            return None
        if target is not None and self._target_related_to_fields(
            target,
            related_fields,
        ):
            return None

        return ScopeBlocker(
            active_scope=active.scope_id,
            target_scope=target_scope.scope_id if target_scope else "unresolved",
            reason=(
                "当前交互目标不属于正在编辑的表单作用域；"
                "应继续操作当前表单，或先使该表单完成、关闭或离开页面"
            ),
        )

    def planner_state(
        self,
        observation: Observation,
        *,
        related_fields: Iterable[Dict[str, Any]] = (),
    ) -> Optional[Dict[str, Any]]:
        """Return planner constraints for the active form transaction."""
        self.reconcile(observation)
        active = self._active
        if active is None:
            return None

        field_targets = self._relation_fields(related_fields)
        allowed_refs: List[str] = []
        for item in observation.elements:
            if not isinstance(item, dict):
                continue
            identity = scope_identity(item)
            ref = str(item.get("ref") or "").strip()
            structurally_related = bool(
                field_targets
                and resolve_action_fields_relation(
                    action=item,
                    fields=field_targets,
                ).related
            )
            if ref and (
                (identity is not None and scopes_related(active, identity))
                or structurally_related
            ):
                allowed_refs.append(ref)

        # Preserve DOM order while preventing a noisy page from inflating the
        # model prompt. The execution-time blocker remains authoritative even
        # when a scope contains more controls than this planner hint exposes.
        allowed_refs = list(dict.fromkeys(allowed_refs))[:40]
        return {
            "scope_id": active.scope_id,
            "allowed_refs": allowed_refs,
            "constraint": (
                "当前有未完成的表单事务。下一步只能操作该表单内的元素 "
                f"refs={allowed_refs}；不要操作页面其他输入框或按钮。"
            ),
            "note": "表单提交成功、关闭或页面切换后，系统会自动解除此限制。",
        }

    def _target_related_to_fields(
        self,
        target: Dict[str, Any],
        related_fields: Iterable[Dict[str, Any]],
    ) -> bool:
        fields = self._relation_fields(related_fields)
        return bool(
            fields
            and resolve_action_fields_relation(
                action=target,
                fields=fields,
            ).related
        )

    def _relation_fields(
        self,
        related_fields: Iterable[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        fields = [
            dict(item)
            for item in related_fields
            if isinstance(item, dict)
        ]
        if self._field_target:
            fields.append(dict(self._field_target))
        unique: Dict[str, Dict[str, Any]] = {}
        for item in fields:
            key = "|".join((
                str(item.get("frameDepth") or 0),
                str(item.get("backendNodeId") or ""),
                str(item.get("selector") or ""),
                str(item.get("ref") or ""),
            ))
            unique[key] = item
        return list(unique.values())

    def after_action(
        self,
        decision: Decision,
        *,
        before: Observation,
        after: Observation,
        ok: bool,
    ) -> None:
        if self._active is None or not ok or not after.fresh:
            return
        before_url = str(before.url or "")
        after_url = str(after.url or "")
        if before_url and after_url and before_url != after_url:
            self.release()
            return
        self.reconcile(after)

    def after_effect(self, receipt: EffectReceipt, observation: Observation) -> None:
        if receipt.status == "confirmed_success":
            self.release()
            return
        self.reconcile(observation)

    def reconcile(self, observation: Observation) -> None:
        if not observation.fresh:
            return
        active = self._active
        if active is None:
            return
        if self._started_url and observation.url and self._started_url != observation.url:
            self.release()
            return
        if not scope_present(
            active,
            (item for item in observation.elements if isinstance(item, dict)),
        ):
            self.release()

    def release(self) -> None:
        self._active = None
        self._started_url = ""
        self._field_target = {}

    def export_state(self) -> Dict[str, Any]:
        return {
            "active": (
                {
                    "scope_id": self._active.scope_id,
                    "selector": self._active.selector,
                    "frame_depth": self._active.frame_depth,
                    "ancestor_scope_ids": list(self._active.ancestor_scope_ids),
                }
                if self._active is not None else None
            ),
            "started_url": self._started_url,
            "field_target": dict(self._field_target),
        }

    def restore_state(self, payload: Dict[str, Any]) -> None:
        active = (payload or {}).get("active")
        self._active = (
            ScopeIdentity(
                scope_id=str(active.get("scope_id") or ""),
                selector=str(active.get("selector") or ""),
                frame_depth=int(active.get("frame_depth") or 0),
                ancestor_scope_ids=tuple(
                    str(item).strip()
                    for item in list(active.get("ancestor_scope_ids") or [])
                    if str(item).strip()
                ),
            )
            if isinstance(active, dict) and str(active.get("scope_id") or "")
            else None
        )
        self._started_url = str((payload or {}).get("started_url") or "")
        self._field_target = dict((payload or {}).get("field_target") or {})


def _decision_target(
    decision: Decision,
    observation: Observation,
) -> Optional[Dict[str, Any]]:
    resolved = resolve_effect_target(decision, observation)
    if resolved is not None:
        return resolved
    ref = str((decision.args or {}).get("ref") or "").strip()
    if not ref:
        return None
    return _element_by_ref(observation, ref)


def _element_by_ref(observation: Observation, ref: str) -> Optional[Dict[str, Any]]:
    return next((
        item for item in observation.elements
        if isinstance(item, dict) and str(item.get("ref") or "").strip() == ref
    ), None)


__all__ = ["FormScopeLock", "ScopeBlocker", "ScopeIdentity"]
