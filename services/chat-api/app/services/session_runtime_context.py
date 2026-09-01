"""Read-only runtime metadata projection for cross-platform conversation history."""

from __future__ import annotations

from typing import Any


async def attach_session_runtime_contexts(
    db: Any,
    sessions: list[dict[str, Any]],
    *,
    tenant_id: str,
    user_id: str,
) -> None:
    """Attach safe binding metadata without exposing device ids or filesystem paths."""
    by_id = {str(row.get("_id")): row for row in sessions if row.get("_id") is not None}
    if not by_id:
        return
    cursor = db.agent_kernel_bindings.find({
        "tenant_id": str(tenant_id),
        "user_id": str(user_id),
        "conversation_id": {"$in": list(by_id)},
        "current": True,
    }, {
        "conversation_id": 1,
        "execution_location": 1,
        "preset_id": 1,
        "source_workspace_id": 1,
        "git_branch": 1,
        "worktree": 1,
    })
    async for binding in cursor:
        target = by_id.get(str(binding.get("conversation_id") or ""))
        if target is None:
            continue
        target["execution_location"] = str(binding.get("execution_location") or "server")
        target["runtime_preset_id"] = str(binding.get("preset_id") or "askai-enterprise")
        if target["execution_location"] in {"desktop", "remote_sandbox"}:
            target["code_project"] = {
                "workspace_id": str(binding.get("source_workspace_id") or ""),
                "git_branch": str(binding.get("git_branch") or ""),
                "worktree": bool(binding.get("worktree")),
            }
