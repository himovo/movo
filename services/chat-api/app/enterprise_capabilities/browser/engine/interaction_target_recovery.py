"""Classify live-DOM target failures that require a fresh observation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.enterprise_capabilities.browser.engine.effect_verification.decision_target import resolve_coordinate_target
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

_STALE_TARGET_MARKERS = (
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

    def blocker(self, decision: Decision, observation: Observation) -> str | None:
        self._reconcile_page(observation)
        if decision.tool != "browser_click":
            return None
        target = _target_by_ref(observation, str((decision.args or {}).get("ref") or ""))
        identity = _target_identity(target)
        if not identity or self._failures.get(identity, 0) < self.max_failures:
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
        identity = _target_identity(target)
        if identity:
            self._failures[identity] = self._failures.get(identity, 0) + 1

    def record_success(self, decision: Decision, observation: Observation) -> None:
        self._reconcile_page(observation)
        if decision.tool != "browser_click":
            return
        target = _target_by_ref(observation, str((decision.args or {}).get("ref") or ""))
        identity = _target_identity(target)
        if identity:
            self._failures.pop(identity, None)

    def _reconcile_page(self, observation: Observation) -> None:
        key = f"{observation.url}\x00{observation.title}"
        if self._page_key and key != self._page_key:
            self._failures.clear()
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


def _target_identity(target: Optional[dict[str, Any]]) -> str:
    if not target:
        return ""
    frame = str(target.get("frameDepth") or 0)
    for key in ("backendNodeId", "selector", "href"):
        value = str(target.get(key) or "").strip()
        if value:
            return f"{frame}:{key}:{value}"
    scope = str(target.get("scopeId") or "").strip()
    semantic = "|".join(
        str(target.get(key) or "").strip().casefold()
        for key in ("role", "name", "text")
    )
    return f"{frame}:scope:{scope}:{semantic}" if scope or semantic else ""


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
