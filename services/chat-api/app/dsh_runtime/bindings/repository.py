"""Authoritative ASKAI Conversation-to-kernel binding records."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pymongo import ReturnDocument


class BindingReplacementConflict(RuntimeError):
    """Another turn or profile refresh won the current-binding claim."""


class KernelBindingRepository:
    COLLECTION = "agent_kernel_bindings"

    def __init__(self, db: Any) -> None:
        self._collection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index("binding_id", unique=True)
        await self._collection.create_index("kernel_session_id", unique=True)
        await self._collection.create_index(
            [("tenant_id", 1), ("conversation_id", 1)],
            unique=True,
            partialFilterExpression={"current": True},
            name="one_current_kernel_binding_per_conversation",
        )
        await self._collection.create_index([("tenant_id", 1), ("user_id", 1), ("conversation_id", 1)])

    async def create(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        kernel_session_id: str,
        runtime_id: str,
        profile_version: str,
        model_instance_id: str,
        kernel_version: str,
        preset_id: str = "askai-enterprise",
        execution_location: str = "server",
        dsh_workspace_id: str | None = None,
        device_id: str | None = None,
        source_workspace_id: str | None = None,
        git_branch: str | None = None,
        source_ref: str | None = None,
        base_commit: str | None = None,
        detached_head: bool = False,
        execution_mode: str | None = None,
        worktree: bool = False,
        replaces_binding_id: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.utcnow()
        if execution_location not in {"server", "desktop", "remote_sandbox"}:
            raise ValueError("unsupported execution_location")
        if execution_location == "server" and dsh_workspace_id:
            raise ValueError("server bindings cannot reference a local DSH workspace")
        if preset_id == "code" and execution_location == "server":
            raise ValueError("code preset requires desktop or remote_sandbox execution")
        replacement_claimed = False
        if replaces_binding_id:
            replaced = await self._collection.update_one(
                {
                    "binding_id": replaces_binding_id,
                    "tenant_id": tenant_id,
                    "conversation_id": conversation_id,
                    "current": True,
                    "$or": [
                        {"active_turn": None},
                        {"active_turn.status": {"$in": ["completed", "failed", "cancelled"]}},
                    ],
                },
                {"$set": {"current": False, "status": "replacing", "updated_at": now}},
            )
            if replaced.matched_count == 0:
                raise BindingReplacementConflict("Conversation binding changed or is still running")
            replacement_claimed = True
        row = {
            "binding_id": f"akb-{uuid4()}",
            "tenant_id": tenant_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "kernel_session_id": kernel_session_id,
            "runtime_id": runtime_id,
            "profile_version": profile_version,
            "model_instance_id": model_instance_id,
            "kernel": "dsh",
            "kernel_version": kernel_version,
            "preset_id": preset_id,
            "execution_location": execution_location,
            "dsh_workspace_id": dsh_workspace_id,
            "device_id": device_id,
            "source_workspace_id": source_workspace_id,
            "git_branch": git_branch,
            "source_ref": source_ref,
            "base_commit": base_commit,
            "detached_head": bool(detached_head),
            "execution_mode": execution_mode or ("worktree" if worktree else "local"),
            "worktree": bool(worktree),
            "status": "idle",
            "current": True,
            "event_cursor": 0,
            "active_turn": None,
            "replaces_binding_id": replaces_binding_id,
            "created_at": now,
            "updated_at": now,
        }
        try:
            await self._collection.insert_one(row)
        except Exception:
            if replacement_claimed:
                current = await self._collection.find_one({
                    "tenant_id": tenant_id, "conversation_id": conversation_id, "current": True,
                })
                if current is None:
                    await self._collection.update_one(
                        {"binding_id": replaces_binding_id, "status": "replacing"},
                        {"$set": {"current": True, "status": "idle", "updated_at": datetime.utcnow()}},
                    )
            raise
        if replacement_claimed:
            await self._collection.update_one(
                {"binding_id": replaces_binding_id, "status": "replacing"},
                {"$set": {"status": "superseded", "updated_at": datetime.utcnow()}},
            )
        return row

    async def current(self, conversation_id: str, *, tenant_id: str, user_id: str) -> dict[str, Any] | None:
        return await self._collection.find_one(
            {
                "conversation_id": conversation_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "current": True,
            }
        )

    async def by_message(self, message_id: str, *, tenant_id: str, user_id: str) -> dict[str, Any] | None:
        return await self._collection.find_one(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "active_turn.message_id": message_id,
            }
        )

    async def by_kernel_session(
        self, kernel_session_id: str, *, tenant_id: str, user_id: str
    ) -> dict[str, Any] | None:
        return await self._collection.find_one({
            "kernel_session_id": kernel_session_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
        })

    async def update_runtime(self, binding_id: str, *, runtime_id: str) -> None:
        await self._collection.update_one(
            {"binding_id": binding_id},
            {"$set": {"runtime_id": runtime_id, "updated_at": datetime.utcnow()}},
        )

    async def update_git_state(self, binding_id: str, *, git_branch: str, head_commit: str) -> None:
        await self._collection.update_one(
            {"binding_id": binding_id, "current": True},
            {"$set": {
                "git_branch": git_branch,
                "detached_head": False,
                "head_commit": head_commit,
                "updated_at": datetime.utcnow(),
            }},
        )

    async def advance_cursor(self, binding_id: str, cursor: int) -> None:
        await self._collection.update_one(
            {"binding_id": binding_id},
            {"$max": {"event_cursor": int(cursor)}, "$set": {"updated_at": datetime.utcnow()}},
        )

    async def claim_turn(
        self,
        binding_id: str,
        *,
        message_id: str,
        request_id: str,
        turn_context: dict[str, Any] | None = None,
        turn_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.utcnow()
        return await self._collection.find_one_and_update(
            {
                "binding_id": binding_id,
                "current": True,
                "$or": [{"active_turn": None}, {"active_turn.status": {"$in": ["completed", "failed", "cancelled"]}}],
            },
            {
                "$set": {
                    "status": "running",
                    "active_turn": {
                        "message_id": message_id,
                        "request_id": request_id,
                        "status": "running",
                        "turn_context": dict(turn_context or {}),
                        "turn_metadata": dict(turn_metadata or {}),
                        "started_at": now,
                    },
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )

    async def finish_turn(self, binding_id: str, *, message_id: str, status: str) -> bool:
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError(f"unsupported terminal turn status: {status}")
        now = datetime.utcnow()
        result = await self._collection.update_one(
            {
                "binding_id": binding_id,
                "active_turn.message_id": message_id,
                "active_turn.status": "running",
            },
            {
                "$set": {
                    "status": "idle" if status == "completed" else status,
                    "active_turn.status": status,
                    "active_turn.finished_at": now,
                    "updated_at": now,
                }
            },
        )
        return result.matched_count > 0

    async def mark_disposed(self, binding_id: str, *, pending: bool = False) -> None:
        await self._collection.update_one(
            {"binding_id": binding_id},
            {
                "$set": {
                    "current": False,
                    "status": "disposal_pending" if pending else "disposed",
                    "active_turn": None,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
