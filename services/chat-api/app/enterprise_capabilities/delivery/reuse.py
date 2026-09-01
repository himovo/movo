"""Reuse accepted authoritative deliveries without re-running their capability."""

from __future__ import annotations

from typing import Any, Protocol


class DeliveryRepository(Protocol):
    async def find_accepted(self, **scope: Any) -> dict[str, Any] | None: ...

    async def save(self, **delivery: Any) -> None: ...


async def reuse_accepted_delivery(
    repository: DeliveryRepository,
    *,
    action_id: str,
    tenant_id: str,
    user_id: str,
    message_id: str,
    tool_name: str,
) -> dict[str, Any] | None:
    delivery = await repository.find_accepted(
        tenant_id=tenant_id,
        user_id=user_id,
        message_id=message_id,
        tool_name=tool_name,
    )
    if delivery is None:
        return None
    source_action_id = str(delivery.get("source_action_id") or "") or str(
        delivery.get("action_id") or ""
    )
    result = {
        "success": True,
        "accepted": True,
        "acceptance": dict(delivery.get("acceptance") or {}),
        "markdown": str(delivery.get("content") or ""),
        "artifacts": [],
        "production": {"reused_from_action_id": source_action_id},
        "message": "",
        "reused": True,
        "source_action_id": source_action_id,
    }
    await repository.save(
        action_id=action_id,
        tenant_id=tenant_id,
        user_id=user_id,
        message_id=message_id,
        tool_name=tool_name,
        markdown=result["markdown"],
        accepted=True,
        acceptance=result["acceptance"],
        source_action_id=source_action_id,
    )
    return result


async def record_accepted_delivery(
    repository: DeliveryRepository,
    *,
    result: dict[str, Any],
    action_id: str,
    tenant_id: str,
    user_id: str,
    message_id: str,
    tool_name: str,
) -> None:
    if not bool(result.get("accepted", result.get("success", True))):
        return
    await repository.save(
        action_id=action_id,
        tenant_id=tenant_id,
        user_id=user_id,
        message_id=message_id,
        tool_name=tool_name,
        markdown=str(result.get("markdown") or ""),
        accepted=True,
        acceptance=dict(result.get("acceptance") or {}),
    )


__all__ = ["record_accepted_delivery", "reuse_accepted_delivery"]
