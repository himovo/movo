from __future__ import annotations

import asyncio

from app.services.session_runtime_context import attach_session_runtime_contexts


class _Cursor:
    def __init__(self, rows):
        self._rows = iter(rows)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._rows)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _Bindings:
    def __init__(self, rows):
        self.rows = rows
        self.query = None
        self.projection = None

    def find(self, query, projection):
        self.query = query
        self.projection = projection
        return _Cursor(self.rows)


class _Db:
    def __init__(self, rows):
        self.agent_kernel_bindings = _Bindings(rows)


def test_cross_platform_runtime_context_is_safe_and_identifies_desktop_history() -> None:
    db = _Db([{
        "conversation_id": "conversation-a", "execution_location": "desktop",
        "preset_id": "code", "source_workspace_id": "workspace-a",
        "git_branch": "codex/task-a", "worktree": True,
        "device_id": "must-not-leak", "dsh_workspace_id": "/must/not/leak",
    }])
    sessions = [{"_id": "conversation-a"}, {"_id": "conversation-b"}]
    asyncio.run(attach_session_runtime_contexts(
        db, sessions, tenant_id="tenant-a", user_id="user-a",
    ))
    assert sessions[0]["execution_location"] == "desktop"
    assert sessions[0]["runtime_preset_id"] == "code"
    assert sessions[0]["code_project"] == {
        "workspace_id": "workspace-a", "git_branch": "codex/task-a", "worktree": True,
    }
    assert "device_id" not in sessions[0]
    assert "dsh_workspace_id" not in sessions[0]
    assert "execution_location" not in sessions[1]
