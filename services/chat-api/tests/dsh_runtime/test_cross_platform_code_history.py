from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from bson import ObjectId

from app.dsh_runtime import chat_service as chat_service_module
from app.dsh_runtime.chat_service import DshChatService


class _Conversations:
    async def owned(self, conversation_id, **_scope):
        return {"_id": conversation_id}


class _Bindings:
    async def current(self, conversation_id, **_scope):
        return {
            "conversation_id": conversation_id,
            "execution_location": "desktop",
            "preset_id": "code",
        }


class _Coordinator:
    def __init__(self):
        self.restored = False

    async def restore(self, _binding):
        self.restored = True
        raise AssertionError("server must not restore a desktop Code binding")


def test_server_chat_cannot_execute_a_desktop_project_history(monkeypatch) -> None:
    coordinator = _Coordinator()
    conversation_id = str(ObjectId())

    async def _session_doc(query, *_args, **_kwargs):
        # The mandatory admission authorizer's tenant-scoped session read:
        # the caller is the seeded owner of tenant-a's session.
        if query.get("_id") != ObjectId(conversation_id) or query.get("main_id") != "tenant-a":
            return None
        return {"_id": ObjectId(conversation_id), "user_id": "user-a", "main_id": "tenant-a"}

    async def _no_participant(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        chat_service_module,
        "get_db",
        lambda: SimpleNamespace(
            chat_sessions=SimpleNamespace(find_one=_session_doc),
            session_participants=SimpleNamespace(find_one=_no_participant),
        ),
    )
    service = DshChatService(
        gateway=object(), coordinator=coordinator, conversations=_Conversations(),
        bindings=_Bindings(), events=object(), profiles=object(), kernel_version="test",
    )

    async def run() -> None:
        with pytest.raises(ValueError, match="bound desktop Runtime"):
            await service.prepare_turn(
                tenant_id="tenant-a", user_id="user-a", conversation_id=conversation_id,
                text="continue editing", model_instance_id=None, timezone_name="Asia/Shanghai",
                images=[], documents=[],
            )

    asyncio.run(run())
    assert coordinator.restored is False
