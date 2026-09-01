from __future__ import annotations

import asyncio

import pytest

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


def test_server_chat_cannot_execute_a_desktop_project_history() -> None:
    coordinator = _Coordinator()
    service = DshChatService(
        gateway=object(), coordinator=coordinator, conversations=_Conversations(),
        bindings=_Bindings(), events=object(), profiles=object(), kernel_version="test",
    )

    async def run() -> None:
        with pytest.raises(ValueError, match="bound desktop Runtime"):
            await service.prepare_turn(
                tenant_id="tenant-a", user_id="user-a", conversation_id="conversation-a",
                text="continue editing", model_instance_id=None, timezone_name="Asia/Shanghai",
                images=[], documents=[],
            )

    asyncio.run(run())
    assert coordinator.restored is False
