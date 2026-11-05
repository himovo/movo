from __future__ import annotations

import asyncio

from app.dsh_runtime.events.repository import KernelEventRepository


class Inbox:
    def __init__(self, row):
        self.row = row
        self.query = None

    async def find_one(self, query, projection, *, sort):
        self.query = query
        assert projection == {"cursor": 1}
        assert sort == [("cursor", -1)]
        return self.row


def test_restore_cursor_excludes_synthetic_failure():
    inbox = Inbox({"cursor": 1217})
    repository = KernelEventRepository({
        "kernel_event_inbox": inbox,
        "kernel_event_projections": object(),
        "chat_messages": object(),
    })
    assert asyncio.run(repository.latest_native_cursor("session-a")) == 1217
    assert inbox.query == {
        "kernel_session_id": "session-a",
        "kernel_event.type": {"$ne": "runtime.failed"},
    }
