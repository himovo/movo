"""Immutable browser action context spanning pre- and post-dispatch DOM."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


@dataclass(frozen=True)
class ActionTargetSnapshot:
    ref: str = ""
    role: str = ""
    name: str = ""
    text: str = ""
    href: str = ""
    editable: bool = False
    semantic_purpose: str = ""
    search_context: bool = False
    scope_id: str = ""
    scope_name: str = ""

    @property
    def is_search(self) -> bool:
        return (
            self.semantic_purpose.casefold() == "search"
            or self.role.casefold() == "searchbox"
            or self.search_context
        )


@dataclass(frozen=True)
class BrowserActionTransition:
    decision: Decision
    before: Observation
    after: Observation
    target: ActionTargetSnapshot

    @classmethod
    def capture(
        cls,
        decision: Decision,
        *,
        before: Observation,
        after: Observation,
    ) -> "BrowserActionTransition":
        return cls(
            decision=decision,
            before=before,
            after=after,
            target=capture_action_target(decision, before),
        )


def capture_action_target(
    decision: Decision,
    observation: Observation,
) -> ActionTargetSnapshot:
    """Resolve a planner ref while it still belongs to the current DOM."""
    ref = str((decision.args or {}).get("ref") or "").strip()
    target: Dict[str, Any] = next(
        (
            item
            for item in observation.elements
            if isinstance(item, dict) and str(item.get("ref") or "").strip() == ref
        ),
        {},
    )
    return ActionTargetSnapshot(
        ref=ref,
        role=str(target.get("role") or ""),
        name=str(target.get("name") or ""),
        text=str(target.get("text") or ""),
        href=str(target.get("href") or ""),
        editable=bool(target.get("editable")),
        semantic_purpose=str(target.get("semanticPurpose") or ""),
        search_context=bool(target.get("searchContext")),
        scope_id=str(target.get("scopeId") or ""),
        scope_name=str(target.get("scopeName") or ""),
    )


__all__ = [
    "ActionTargetSnapshot",
    "BrowserActionTransition",
    "capture_action_target",
]
