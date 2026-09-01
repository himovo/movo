"""ASKAI final-delivery guard for tools that own their rendered answer."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Protocol

from app.dsh_runtime.contracts import KernelEventEnvelope


class DeliveryStore(Protocol):
    async def get(
        self,
        action_id: str,
        *,
        tenant_id: str,
        user_id: str,
        message_id: str,
    ) -> dict[str, Any] | None: ...


class AuthoritativeDeliveryGuard:
    """Replace only the final model answer after an authoritative tool succeeds."""

    def __init__(
        self,
        *,
        store: DeliveryStore | None,
        tool_presentations: Mapping[str, Mapping[str, Any]],
        tenant_id: str,
        user_id: str,
        message_id: str,
    ) -> None:
        self._store = store
        self._tools = tool_presentations
        self._tenant_id = tenant_id
        self._user_id = user_id
        self._message_id = message_id
        self._markdown = ""
        self._tool_name = ""
        self._action_id = ""

    async def apply(
        self,
        event: KernelEventEnvelope,
        projected: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if projected is None:
            return None
        if event.type == "tool.call.completed":
            await self._capture(projected)
            return projected
        if not self._markdown or projected.get("item_kind") != "final_answer":
            return projected
        if projected.get("type") == "item.delta":
            return None
        if projected.get("type") != "item.completed":
            return projected
        result = deepcopy(projected)
        payload = dict(result.get("payload") or {})
        payload.update({
            "text": self._markdown,
            "provisional": False,
            "source": "askai_authoritative_tool",
            "source_tool": self._tool_name,
            "source_action_id": self._action_id,
        })
        result["payload"] = payload
        return result

    async def _capture(self, projected: dict[str, Any]) -> None:
        payload = projected.get("payload")
        if not isinstance(payload, dict) or not bool(payload.get("ok")):
            return
        tool_name = str(payload.get("name") or "")
        policy = str((self._tools.get(tool_name) or {}).get("delivery_mode") or "model_synthesized")
        if policy != "authoritative_markdown" or self._store is None:
            return
        action_id = str(payload.get("callId") or "")
        delivery = await self._store.get(
            action_id,
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            message_id=self._message_id,
        )
        markdown = str((delivery or {}).get("content") or "").strip()
        if not markdown:
            return
        self._markdown = markdown
        self._tool_name = tool_name
        self._action_id = action_id


__all__ = ["AuthoritativeDeliveryGuard", "DeliveryStore"]
