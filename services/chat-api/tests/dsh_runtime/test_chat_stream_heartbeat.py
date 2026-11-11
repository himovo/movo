from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.dsh_runtime import chat_service
from app.dsh_runtime.events.live_stream import LiveTurnStream


def test_idle_stream_sends_heartbeat_without_finishing_turn(monkeypatch) -> None:
    class Authorizer:
        def __init__(self, _db):
            pass

        async def authorize_read(self, *_args, **_kwargs):
            return object()

    monkeypatch.setattr(chat_service, "SessionReadAuthorizer", Authorizer)
    monkeypatch.setattr(chat_service, "get_db", lambda: None)
    monkeypatch.setattr(chat_service, "_STREAM_AUTH_RECHECK_SECONDS", 0.005)
    monkeypatch.setattr(chat_service, "STREAM_HEARTBEAT_SECONDS", 0.01)

    async def run() -> None:
        service = chat_service.DshChatService.__new__(chat_service.DshChatService)
        service._live_streams = {"message-a": LiveTurnStream()}
        turn = SimpleNamespace(message_id="message-a", conversation_id="conversation-a")
        stream = service.stream(turn, tenant_id="tenant-a", user_id="user-a")
        assert await asyncio.wait_for(stream.__anext__(), timeout=1) == "\n"
        assert "message-a" in service._live_streams
        await stream.aclose()

    asyncio.run(run())
