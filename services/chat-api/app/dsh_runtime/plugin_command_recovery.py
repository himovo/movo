"""Reconstruct a terminal projection from a completed native command log."""

from __future__ import annotations

from typing import Any

from app.dsh_runtime.events import KernelEventRepository
from app.dsh_runtime.gateway import DshAgentKernelGateway
from app.dsh_runtime.plugin_command_runner import _event
from app.dsh_runtime.profile.plugin_command_selection import selected_command_name


async def recover_plugin_command_terminal(
    *, gateway: DshAgentKernelGateway, events: KernelEventRepository,
    binding: dict[str, Any], message_id: str,
) -> bool:
    active = dict(binding.get("active_turn") or {})
    selected_id = str((active.get("turn_context") or {}).get("selected_command_id") or "")
    native_cursor = active.get("command_after_cursor")
    if not selected_id or not isinstance(native_cursor, int) or native_cursor < 0:
        return False
    command_name = selected_command_name(selected_id)
    native = await gateway.events_once(str(binding["kernel_session_id"]), native_cursor)
    command_ids = {
        str(event.payload.get("commandId") or "")
        for event in native
        if event.source.native_event_type == "command/run"
        and event.payload.get("name") == command_name
    }
    done = next((event for event in reversed(native)
                 if event.source.native_event_type == "command/done"
                 and str(event.payload.get("commandId") or "") in command_ids), None)
    if done is None:
        return False
    kind = str(done.payload.get("kind") or "")
    if kind not in {"success", "error"}:
        return False
    text = str(done.payload.get("text") or "")
    status = "completed" if kind == "success" else "failed"
    rows = []
    if text:
        rows.append(_event(message_id, "item.completed", {"text": text, "provisional": False}, item_kind="final_answer"))
    rows.append(_event(message_id, f"run.{status}", {"reason": "plugin_command"}))
    await events.persist_projections(
        rows,
        tenant_id=str(binding["tenant_id"]), user_id=str(binding["user_id"]),
        conversation_id=str(binding["conversation_id"]), message_id=message_id,
        kernel_session_id=str(binding["kernel_session_id"]),
    )
    return True
