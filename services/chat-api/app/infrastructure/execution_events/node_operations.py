from __future__ import annotations

from typing import Any, Dict

from .operation import operation_descriptor_for_node, operation_event


class NodeOperation:
    """Own the native V3 lifecycle for one graph node across retries."""

    def __init__(self, *, enabled: bool, run_id: str, node: Any, attempt: int) -> None:
        self.enabled = bool(enabled)
        self.node = node
        # A retry updates the same user-visible operation. Attempt identity
        # remains in graph state/logs and must not create duplicate UI rows.
        self.operation_id = f"operation_node_{run_id}_{getattr(node, 'node_id', 'node')}"
        self.descriptor = operation_descriptor_for_node(node)

    def event(self, state: str, *, detail: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
        if not self.enabled:
            return None
        return operation_event(
            state,
            operation_id=self.operation_id,
            label=self.descriptor["label"],
            category=self.descriptor["category"],
            parent_id=str(getattr(self.node, "node_id", "")),
            source=self.descriptor["source"],
            detail=detail,
        )

    def started(self) -> Dict[str, Any] | None:
        return self.event("started")

    def updated(self, *, detail: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
        return self.event("updated", detail=detail)

    def completed(self) -> Dict[str, Any] | None:
        return self.event("completed")

    def failed(self, *, reason: str) -> Dict[str, Any] | None:
        return self.event("failed", detail={"reason": str(reason or "")})

    def blocked(self) -> Dict[str, Any] | None:
        return self.event("blocked")

    def attach_to_child_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Attach an unparented native operation emitted inside this node.

        A graph node is an execution scope. Child runtimes own their leaf
        operation lifecycles, while this boundary supplies the stable parent
        item id needed by V3 presentation. Explicit deeper nesting is kept.
        """

        event_type = str(event.get("type") or "").strip().lower()
        supports_parent = event_type.startswith("operation.") or event_type in {
            "tool_requested",
            "tool_completed",
            "tool_failed",
        }
        if not self.enabled or not supports_parent:
            return event
        content = event.get("content")
        if not isinstance(content, dict) or content.get("parent_id"):
            return event
        child_id = str(content.get("operation_id") or "").strip()
        if event_type.startswith("operation.") and (
            not child_id or child_id == self.operation_id
        ):
            return event
        return {
            **event,
            "content": {**content, "parent_id": self.operation_id},
        }
