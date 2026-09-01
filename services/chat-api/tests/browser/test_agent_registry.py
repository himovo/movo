import asyncio

from app.browser.registry import AgentRegistry


def test_stale_disconnect_does_not_remove_replacement_connection():
    async def scenario():
        registry = AgentRegistry()

        async def send(_frame):
            return None

        first = await registry.attach("user-1", send, [])
        second = await registry.attach("user-1", send, [])

        await registry.detach("user-1", first)
        assert registry.get("user-1") is second

        await registry.detach("user-1", second)
        assert registry.get("user-1") is None

    asyncio.run(scenario())


def test_tool_call_carries_browser_session_id():
    async def scenario():
        registry = AgentRegistry()
        sent = []

        async def send(frame):
            sent.append(frame)
            call_id = frame["payload"]["call_id"]
            await registry.on_frame("user-1", {
                "type": "tool_result",
                "payload": {"call_id": call_id, "ok": True, "result": {}},
            })

        await registry.attach("user-1", send, [])
        result = await registry.send_tool_call(
            "user-1", "browser_navigate", {"url": "https://example.com"},
            session_id="chat-session-a",
        )

        assert result["ok"] is True
        assert sent[0]["payload"]["session_id"] == "chat-session-a"
        assert sent[0]["payload"]["timeout_ms"] == 55_000

    asyncio.run(scenario())


def test_tool_timeout_cancels_the_matching_local_call():
    async def scenario():
        registry = AgentRegistry()
        sent = []

        async def send(frame):
            sent.append(frame)

        await registry.attach("user-1", send, [])
        try:
            await registry.send_tool_call(
                "user-1", "browser_fill", {"ref": "e1", "value": "hello"},
                session_id="chat-session-a", timeout=0.01,
            )
            assert False, "expected timeout"
        except asyncio.TimeoutError:
            pass

        assert [frame["type"] for frame in sent] == ["tool_call", "tool_cancel"]
        assert sent[1]["payload"]["call_id"] == sent[0]["payload"]["call_id"]
        assert sent[1]["payload"]["session_id"] == "chat-session-a"
        assert sent[1]["payload"]["reason"] == "backend_timeout"

    asyncio.run(scenario())
