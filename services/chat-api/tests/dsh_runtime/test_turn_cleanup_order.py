from __future__ import annotations

import asyncio
import pytest

from app.dsh_runtime import turn_finalization


def test_presented_output_upload_failure_keeps_turn_retryable(monkeypatch) -> None:
    class Bindings:
        async def finish_turn(self, *_args, **_kwargs):
            raise AssertionError("turn must not finish")

    class Conversations:
        async def update_assistant_projection(self, **_kwargs):
            raise AssertionError("failed delivery must not be committed")

    async def fail_delivery(*_args, **_kwargs):
        raise RuntimeError("upload failed")

    monkeypatch.setattr(turn_finalization, "deliver_personal_outputs", fail_delivery)
    finalizer = turn_finalization.TurnStateFinalizer(Bindings(), Conversations())
    with pytest.raises(turn_finalization.TurnFinalizationRetryableError, match="publish workspace outputs"):
        asyncio.run(finalizer.finalize(
            binding={"tenant_id": "tenant", "user_id": "user", "conversation_id": "session", "binding_id": "binding"},
            message_id="message", status="completed",
            assistant=turn_finalization.TurnAssistantProjection(content="done", execution_events=[]),
        ))


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
