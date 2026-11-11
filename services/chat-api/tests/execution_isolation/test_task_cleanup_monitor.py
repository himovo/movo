from __future__ import annotations

import asyncio

from app.execution_isolation import task_cleanup_monitor


def test_pending_cleanup_scan_retries_archived_tasks(monkeypatch) -> None:
    attempts = []

    class Cursor:
        def limit(self, count):
            assert count == 20
            return self

        def __aiter__(self):
            self.rows = iter([{"_id": "tenant:message", "message_id": "message"}])
            return self

        async def __anext__(self):
            try:
                return next(self.rows)
            except StopIteration:
                raise StopAsyncIteration

    class Collection:
        def find(self, query, projection):
            assert query == {"cleanup_pending": True}
            return Cursor()

    class Database:
        sandbox_task_audits = Collection()

    async def cleanup(*, message_id, audit_id):
        attempts.append((message_id, audit_id))

    monkeypatch.setattr(task_cleanup_monitor, "get_db", Database)
    monkeypatch.setattr(task_cleanup_monitor, "cleanup_task_audit", cleanup)
    asyncio.run(task_cleanup_monitor.retry_pending_task_cleanups())
    assert attempts == [("message", "tenant:message")]
