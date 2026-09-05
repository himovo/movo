from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.dsh_runtime.chat_service import DshChatService
from app.dsh_runtime.errors import DshRuntimeError
from app.dsh_runtime.turn_finalization import TurnStateFinalizer


def _binding() -> dict:
    return {
        "binding_id": "binding-a",
        "tenant_id": "tenant-a",
        "user_id": "user-a",
        "conversation_id": "conversation-a",
        "kernel_session_id": "session-a",
        "runtime_id": "runtime-a",
        "profile_version": "profile-a",
        "event_cursor": 0,
        "active_turn": {"message_id": "message-a", "status": "running"},
    }


class _Bindings:
    def __init__(self) -> None:
        self.binding = _binding()

    async def current(self, *_args, **_kwargs):
        return self.binding

    async def finish_turn(self, _binding_id: str, *, message_id: str, status: str) -> None:
        assert message_id == "message-a"
        self.binding["active_turn"] = {"message_id": message_id, "status": status}


class _Conversations:
    def __init__(self) -> None:
        self.cleared = False
        self.execution_events: list[dict] = []

    async def owned(self, *_args, **_kwargs):
        return {"_id": "conversation-a"}

    async def clear_active_run(self, **kwargs) -> None:
        assert kwargs["message_id"] == "message-a"
        self.cleared = True

    async def update_assistant_projection(self, **kwargs) -> None:
        self.execution_events = list(kwargs["execution_events"])


class _Coordinator:
    async def restore(self, binding):
        return binding


class _Gateway:
    def __init__(self, result: dict) -> None:
        self.result = result
        self.cancelled = False
        self.described = False

    async def cancel(self, _request):
        self.cancelled = True
        return self.result

    async def describe_session(self, _session_id: str):
        self.described = True
        return SimpleNamespace(status=SimpleNamespace(value="idle"))


class _PersistedEvents:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = list(rows or [])

    async def all_for_message(self, *_args, **_kwargs):
        return list(self.rows)


def _service(gateway: _Gateway, bindings: _Bindings, conversations: _Conversations) -> DshChatService:
    service = DshChatService(
        gateway=gateway,  # type: ignore[arg-type]
        coordinator=_Coordinator(),  # type: ignore[arg-type]
        conversations=conversations,  # type: ignore[arg-type]
        bindings=bindings,  # type: ignore[arg-type]
        events=SimpleNamespace(),
        profiles=SimpleNamespace(),
        kernel_version="0.1.0-rc.6",
    )

    async def ingest_once(**_kwargs) -> None:
        return None

    service._terminal_recovery.ingest_once = ingest_once  # type: ignore[method-assign]
    return service


def test_cancel_returns_only_after_both_persisted_states_are_terminal() -> None:
    async def run() -> None:
        bindings = _Bindings()
        conversations = _Conversations()
        gateway = _Gateway({"accepted": True, "jobsPending": False, "turnPending": False})
        service = _service(gateway, bindings, conversations)

        assert await service.cancel(
            "conversation-a", tenant_id="tenant-a", user_id="user-a"
        ) is True
        assert gateway.cancelled is True
        assert bindings.binding["active_turn"]["status"] == "cancelled"
        assert conversations.cleared is True

    asyncio.run(run())


def test_cancel_does_not_unlock_while_host_reports_pending_work() -> None:
    async def run() -> None:
        bindings = _Bindings()
        conversations = _Conversations()
        gateway = _Gateway({"accepted": True, "jobsPending": False, "turnPending": True})
        service = _service(gateway, bindings, conversations)

        with pytest.raises(DshRuntimeError, match="still stopping"):
            await service.cancel(
                "conversation-a", tenant_id="tenant-a", user_id="user-a"
            )
        assert bindings.binding["active_turn"]["status"] == "running"
        assert conversations.cleared is False

    asyncio.run(run())


def test_idle_host_does_not_unlock_a_turn_without_a_persisted_terminal() -> None:
    async def run() -> None:
        bindings = _Bindings()
        conversations = _Conversations()
        gateway = _Gateway({"accepted": True})
        service = _service(gateway, bindings, conversations)

        repaired = await service._terminal_recovery.recover(bindings.binding)

        assert repaired["active_turn"]["status"] == "running"
        assert conversations.cleared is False
        assert gateway.described is False

    asyncio.run(run())


def test_persisted_terminal_repairs_both_stale_product_states() -> None:
    async def run() -> None:
        bindings = _Bindings()
        conversations = _Conversations()
        gateway = _Gateway({"accepted": True})
        service = DshChatService(
            gateway=gateway,  # type: ignore[arg-type]
            coordinator=_Coordinator(),  # type: ignore[arg-type]
            conversations=conversations,  # type: ignore[arg-type]
            bindings=bindings,  # type: ignore[arg-type]
            events=_PersistedEvents([{
                "type": "run.cancelled",
                "item_kind": "run",
                "payload": {"reason": "user_cancelled"},
            }]),  # type: ignore[arg-type]
            profiles=SimpleNamespace(),
            kernel_version="0.1.0-rc.6",
        )

        repaired = await service._terminal_recovery.recover(bindings.binding)

        assert repaired["active_turn"]["status"] == "cancelled"
        assert conversations.cleared is True
        assert conversations.execution_events[0]["type"] == "run.cancelled"
        assert gateway.described is False

    asyncio.run(run())


def test_sidebar_state_is_not_cleared_when_admission_lock_update_fails() -> None:
    async def run() -> None:
        class _FailingBindings(_Bindings):
            async def finish_turn(self, *_args, **_kwargs):
                raise RuntimeError("database unavailable")

        conversations = _Conversations()
        finalizer = TurnStateFinalizer(_FailingBindings(), conversations)  # type: ignore[arg-type]

        with pytest.raises(RuntimeError, match="database unavailable"):
            await finalizer.finalize(
                binding=_binding(), message_id="message-a", status="cancelled"
            )
        assert conversations.cleared is False

    asyncio.run(run())
