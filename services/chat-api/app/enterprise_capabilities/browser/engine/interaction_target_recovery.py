"""Classify live-DOM target failures that require a fresh observation."""
from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Any, Optional

from app.enterprise_capabilities.browser.engine.effect_verification.decision_target import resolve_coordinate_target
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation
from .obstruction_evidence import obstruction_evidence, OBSTRUCTION_GUIDANCE

_STALE_TARGET_MARKERS = (
    "stale_target_rebind_",
    "unknown or stale element ref",
    "click target is stale or no longer resolvable",
    "click target moved or is covered",
    "click target kept moving during pointer correction",
    "click target has no usable point",
    "click target resolves to a page container",
    "click target business identity changed",
    "element has no live click target",
)


def is_stale_interaction_target_error(error: object) -> bool:
    message = str(error or "").casefold()
    return any(marker in message for marker in _STALE_TARGET_MARKERS)


@dataclass(frozen=True)
class CoordinateBinding:
    decision: Decision
    target: Optional[dict[str, Any]] = None
    reason: str = ""
    blocked: bool = False


class InteractionTargetRecovery:
    """Bound retries to a stable live-DOM identity on one page state."""

    def __init__(self, *, max_failures: int = 2) -> None:
        self.max_failures = max(1, max_failures)
        self._page_key = ""
        self._failures: dict[str, int] = {}
        self._occluded: dict[str, dict[str, Any]] = {}

    def blocker(self, decision: Decision, observation: Observation) -> str | None:
        self._reconcile_page(observation)
        if decision.tool != "browser_click":
            return None
        target = _target_by_ref(observation, str((decision.args or {}).get("ref") or ""))
        if target and (target.get("hitTestable") is False or any(key in self._occluded for key in _target_aliases(target))):
            return OBSTRUCTION_GUIDANCE
        if not target or not self._is_quarantined(target):
            return None
        if target and target.get("editable"):
            return (
                "这个可编辑目标已连续无法获得有效点击点。不要继续点击或改用旧坐标；"
                "请直接对当前可编辑 ref 使用 browser_fill。"
            )
        return (
            "这个目标在当前页面状态下已连续无法命中。不要重复使用同一 ref 或旧坐标；"
            "请重新观察遮挡层并选择其他当前可命中的目标。"
        )

    def record_failure(
        self,
        decision: Decision,
        observation: Observation,
        error: object,
    ) -> None:
        if decision.tool != "browser_click" or not is_stale_interaction_target_error(error):
            return
        self._reconcile_page(observation)
        target = _target_by_ref(observation, str((decision.args or {}).get("ref") or ""))
        covered = obstruction_evidence(error)
        if covered:
            covered["revision"] = observation.revision
            for identity in _target_aliases(target):
                self._occluded[identity] = covered
            return
        for identity in _target_aliases(target):
            self._failures[identity] = self._failures.get(identity, 0) + 1

    def record_success(self, decision: Decision, observation: Observation) -> None:
        self._reconcile_page(observation)
        if decision.tool != "browser_click":
            return
        target = _target_by_ref(observation, str((decision.args or {}).get("ref") or ""))
        for identity in _target_aliases(target):
            self._failures.pop(identity, None)
            self._occluded.pop(identity, None)

    def planning_observation(self, observation: Observation) -> Observation:
        """Remove quarantined click targets from the next planning turn.

        Editable targets remain visible because the safe recovery for a covered
        editor is browser_fill, not selecting a different field.  Non-editable
        targets are removed so a planner cannot repeatedly choose the same
        broken card through a fresh ephemeral ref.
        """
        self._reconcile_page(observation)
        for item in observation.elements:
            if observation.fresh and item.get("hitTestable") is True:
                for identity in _target_aliases(item):
                    evidence = self._occluded.get(identity)
                    if evidence and observation.revision and observation.revision != evidence.get("revision"):
                        self._occluded.pop(identity, None)
        elements = [
            item for item in list(observation.elements or [])
            if not (
                isinstance(item, dict)
                and not item.get("editable")
                and self._is_quarantined(item)
            )
        ]
        elements = [
            {**item, "hitTestable": False} if any(
                key in self._occluded for key in _target_aliases(item)
            ) else item for item in elements
        ]
        if not self._occluded and len(elements) == len(observation.elements or []):
            return observation
        return replace(observation, elements=elements)

    def quarantined_refs(self, observation: Observation) -> tuple[str, ...]:
        return tuple(
            str(item.get("ref") or "")
            for item in list(observation.elements or [])
            if (
                isinstance(item, dict)
                and not item.get("editable")
                and self._is_quarantined(item)
                and str(item.get("ref") or "")
            )
        )

    def augment_state_ledger(self, ledger: dict[str, Any] | None) -> dict[str, Any] | None:
        quarantined = sorted(
            identity for identity, failures in self._failures.items()
            if failures >= self.max_failures
        )
        if not quarantined and not self._occluded:
            return ledger
        updated = dict(ledger or {})
        constraints = list(updated.get("action_constraints") or [])
        if self._occluded:
            constraints.append(OBSTRUCTION_GUIDANCE)
        if quarantined:
            constraints.append(
                "Targets quarantined after repeated live interaction failures are absent from the "
                "current element list; choose another visible target or change the page state."
            )
        notes = list(updated.get("notes") or [])
        if self._occluded:
            notes.append({"occluded_targets": list(self._occluded.items())[:6]})
        if quarantined:
            notes.append({"quarantined_interaction_targets": quarantined[:12]})
        updated["action_constraints"] = constraints
        updated["notes"] = notes
        return updated

    def _is_quarantined(self, target: dict[str, Any]) -> bool:
        return any(
            self._failures.get(identity, 0) >= self.max_failures
            for identity in _target_aliases(target)
        )

    def _reconcile_page(self, observation: Observation) -> None:
        key = f"{observation.url}\x00{observation.title}"
        if self._page_key and key != self._page_key:
            self._failures.clear()
            self._occluded.clear()
        self._page_key = key


def bind_coordinate_action(
    decision: Decision,
    observation: Observation,
) -> CoordinateBinding:
    """Bind coordinate input to a current semantic ref when one exists."""
    if decision.tool not in {"browser_type_at", "browser_click_at"}:
        return CoordinateBinding(decision=decision)
    args = dict(decision.args or {})
    try:
        point = (float(args.get("x")), float(args.get("y")))
    except (TypeError, ValueError):
        return CoordinateBinding(decision=decision, reason="coordinate action has invalid coordinates")
    target = resolve_coordinate_target(
        observation.elements,
        point,
        editable_only=decision.tool == "browser_type_at",
        tolerance=52.0 if decision.tool == "browser_type_at" else 36.0,
    )
    ref = str((target or {}).get("ref") or "").strip()
    if not ref:
        if decision.tool == "browser_type_at" and _has_visible_editable(observation):
            return CoordinateBinding(
                decision=decision,
                target=target,
                reason=(
                    "坐标没有命中当前 DOM 中的可编辑字段。请重新观察并使用最新字段 ref，"
                    "不要把文本输入到未经确认的坐标。"
                ),
                blocked=True,
            )
        return CoordinateBinding(decision=decision, target=target)
    if decision.tool == "browser_type_at":
        value = str(args.get("value") or "")
        return CoordinateBinding(
            decision=Decision(
                tool="browser_fill",
                args={"ref": ref, "value": value, **_domain_arg(args)},
                rationale="coordinate text input rebound to the latest editable DOM target",
            ),
            target=target,
            reason="coordinate input rebound to browser_fill",
        )
    if _is_interactive(target or {}):
        return CoordinateBinding(
            decision=Decision(
                tool="browser_click",
                args={"ref": ref, **_domain_arg(args)},
                rationale="coordinate click rebound to the latest interactive DOM target",
            ),
            target=target,
            reason="coordinate click rebound to browser_click",
        )
    return CoordinateBinding(decision=decision, target=target)


def _target_by_ref(observation: Observation, ref: str) -> Optional[dict[str, Any]]:
    return next((
        item for item in observation.elements
        if isinstance(item, dict) and str(item.get("ref") or "") == ref
    ), None)


def _target_aliases(target: Optional[dict[str, Any]]) -> set[str]:
    """Stable aliases survive AX ref/backend-node replacement on one page."""
    if not target:
        return set()
    frame = str(target.get("frameDepth") or 0)
    aliases: set[str] = set()
    for key in ("contentContextId", "href"):
        value = str(target.get(key) or "").strip()
        if value:
            aliases.add(f"{frame}:{key}:{value.casefold()}")
    selector = str(target.get("selector") or "").strip()
    if re.fullmatch(r"#[A-Za-z][\w:-]*", selector):
        aliases.add(f"{frame}:selector:{selector.casefold()}")
    scope = str(target.get("scopeId") or target.get("scopeSelector") or "").strip().casefold()
    role = str(target.get("role") or "").strip().casefold()
    label = " ".join(str(target.get(key) or "").strip() for key in ("name", "text"))
    label = " ".join(label.casefold().split())[:240]
    if label:
        aliases.add(f"{frame}:semantic:{scope}:{role}:{label}")
    backend_node_id = str(target.get("backendNodeId") or "").strip()
    if backend_node_id:
        aliases.add(f"{frame}:backendNodeId:{backend_node_id}")
    return aliases


def _is_interactive(target: dict[str, Any]) -> bool:
    return bool(
        target.get("editable")
        or target.get("href")
        or str(target.get("role") or "").casefold()
        in {"button", "link", "menuitem", "checkbox", "radio", "textbox", "searchbox"}
    )


def _has_visible_editable(observation: Observation) -> bool:
    return any(
        isinstance(item, dict)
        and item.get("editable") is True
        and item.get("visible") is not False
        and item.get("disabled") is not True
        for item in observation.elements or []
    )


def _domain_arg(args: dict[str, Any]) -> dict[str, str]:
    domain = str(args.get("domain") or "").strip()
    return {"domain": domain} if domain else {}


__all__ = [
    "CoordinateBinding",
    "InteractionTargetRecovery",
    "bind_coordinate_action",
    "is_stale_interaction_target_error",
]
