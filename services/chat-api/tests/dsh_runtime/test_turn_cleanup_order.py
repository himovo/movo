from __future__ import annotations

import asyncio

from app.dsh_runtime import turn_finalization


def test_cleanup_runs_after_conversation_unlock(monkeypatch) -> None:
    order = []

    class Bindings:
        async def finish_turn(self, binding_id, *, message_id, status):
            order.append("binding_finished")
            return True

    class Conversations:
        async def clear_active_run(self, **kwargs):
            order.append("conversation_unlocked")

    async def archive(**kwargs):
        order.append("audit_archived")
        return True

    async def cleanup(**kwargs):
        order.append("sandbox_cleaned")
        return True

    monkeypatch.setattr(turn_finalization, "finalize_task_audit", archive)
    monkeypatch.setattr(turn_finalization, "cleanup_task_audit", cleanup)

    async def run() -> None:
        finalizer = turn_finalization.TurnStateFinalizer(Bindings(), Conversations())
        await finalizer.finalize(
            binding={"tenant_id": "tenant", "user_id": "user", "conversation_id": "session", "binding_id": "binding"},
            message_id="message", status="completed",
        )
        assert order == ["audit_archived", "binding_finished", "conversation_unlocked"]
        await asyncio.sleep(0)
        assert order == ["audit_archived", "binding_finished", "conversation_unlocked", "sandbox_cleaned"]

    asyncio.run(run())
