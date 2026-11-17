import asyncio
import json

import httpx

from app.services import external_tools
from app.services.mcp_streamable_http import StreamableHttpMcpClient


def test_external_tool_service_passes_auth_and_runtime_identity_to_mcp_transport(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def call(self, method, params):
            captured["method"] = method
            captured["params"] = params
            return {"content": [{"type": "text", "text": "ok"}]}

    monkeypatch.setattr(external_tools, "StreamableHttpMcpClient", FakeClient)
    tool = {
        "config": {
            "endpoint": "https://mcp.example.test/mcp",
            "headers": {"Authorization": "Bearer stale", "X-Custom": "kept"},
            "authType": "bearer",
            "authToken": "configured-token",
            "timeoutSeconds": 9,
        }
    }

    result = asyncio.run(
        external_tools.ExternalToolService()._mcp_jsonrpc(
            tool,
            "tools/call",
            {"name": "search", "arguments": {}},
            runtime_headers={"X-MOVO-User-ID": "user-7"},
        )
    )

    assert result["content"][0]["text"] == "ok"
    assert captured["endpoint"] == "https://mcp.example.test/mcp"
    assert captured["timeout"] == 9
    assert captured["headers"]["Authorization"] == "Bearer configured-token"
    assert captured["headers"]["X-Custom"] == "kept"
    assert captured["headers"]["X-MOVO-User-ID"] == "user-7"
    assert captured["method"] == "tools/call"


def test_external_tool_service_completes_real_session_handshake(monkeypatch):
    methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        methods.append(payload["method"])
        assert request.headers["authorization"] == "Bearer configured-token"
        if payload["method"] == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "service-session"},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2025-06-18", "capabilities": {}},
                },
            )
        assert request.headers["mcp-session-id"] == "service-session"
        if payload["method"] == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": {"tools": [{"name": "search"}]}},
        )

    transport = httpx.MockTransport(handler)

    def client_factory(**kwargs):
        return StreamableHttpMcpClient(**kwargs, transport=transport)

    monkeypatch.setattr(external_tools, "StreamableHttpMcpClient", client_factory)
    result = asyncio.run(
        external_tools.ExternalToolService()._mcp_jsonrpc(
            {
                "config": {
                    "endpoint": "https://mcp.example.test/mcp",
                    "authType": "bearer",
                    "authToken": "configured-token",
                }
            },
            "tools/list",
            {},
        )
    )

    assert result == {"tools": [{"name": "search"}]}
    assert methods == ["initialize", "notifications/initialized", "tools/list"]


def test_discovery_debug_and_runtime_paths_all_use_initialized_sessions(monkeypatch):
    methods = []
    sessions = set()
    update = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        method = payload["method"]
        methods.append(method)
        assert request.headers["authorization"] == "Bearer configured-token"
        if method == "initialize":
            session_id = f"session-{len(sessions) + 1}"
            sessions.add(session_id)
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": session_id},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2025-06-18", "capabilities": {}},
                },
            )
        assert request.headers.get("Mcp-Session-Id") in sessions
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "search",
                        "description": "Search records",
                        "inputSchema": {"type": "object"},
                    }
                ]
            }
        else:
            assert method == "tools/call"
            result = {"content": [{"type": "text", "text": "found"}]}
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": result},
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        external_tools,
        "StreamableHttpMcpClient",
        lambda **kwargs: StreamableHttpMcpClient(**kwargs, transport=transport),
    )

    class Collection:
        async def update_one(self, query, operation):
            update["query"] = query
            update["operation"] = operation

    class Database:
        external_tools = Collection()

    monkeypatch.setattr(external_tools, "get_db", lambda: Database())
    service = external_tools.ExternalToolService()
    tool = {
        "id": "tool-1",
        "type": "mcp",
        "status": "active",
        "config": {
            "endpoint": "https://mcp.example.test/mcp",
            "authType": "bearer",
            "authToken": "configured-token",
            "enabledToolNames": ["search"],
        },
    }

    async def fake_get(*args, **kwargs):
        return tool

    monkeypatch.setattr(service, "get", fake_get)

    from app.services import mcp_session_pool
    pool = mcp_session_pool.McpSessionPool(transport=transport)
    monkeypatch.setattr(mcp_session_pool, 'current_mcp_pool', lambda: pool)

    async def exercise_all_paths():
        discovery = await service.discover_mcp_tools("tool-1")
        connection_test = await service._test_mcp(tool, {})
        call_test = await service._test_mcp(
            tool,
            {"toolName": "search", "arguments": {"q": "test"}},
        )
        runtime = await service.execute_runtime(
            external_tool_id="tool-1",
            provider_type="mcp",
            mcp_tool_name="search",
            arguments={"q": "test"},
            actor_user_id="user-1",
        )
        await pool.close()
        return discovery, connection_test, call_test, runtime

    discovery, connection_test, call_test, runtime = asyncio.run(exercise_all_paths())

    assert discovery["tools"][0]["name"] == "search"
    assert connection_test["success"] is True
    assert call_test["raw"]["content"][0]["text"] == "found"
    assert runtime["raw"]["content"][0]["text"] == "found"
    assert len(sessions) == 4
    assert methods == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "initialize",
        "notifications/initialized",
        "tools/list",
        "initialize",
        "notifications/initialized",
        "tools/call",
        "initialize",
        "notifications/initialized",
        "tools/call",
    ]
    assert update["operation"]["$set"]["discovered_tools"][0]["name"] == "search"
