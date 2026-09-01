from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from app.dsh_runtime import DshAgentKernelGateway, DshHostConfig, DshRuntimeHostManager, HttpKernelHostTransport
from app.dsh_runtime.contracts import ContentBlock, CreateRuntimeRequest, CreateSessionRequest, SendRequest, SessionSpec
from app.dsh_runtime.model_gateway.token import ModelGatewayTokenService
from app.dsh_runtime.profile import InMemoryRuntimeProfileStore, RuntimeProfileResolver, RuntimeProfileSnapshot
from app.dsh_runtime.profile.tools import ToolProfileDefinition
from app.dsh_runtime.tool_gateway import ToolGatewayTokenService
from app.enterprise_capabilities.data import MetricsEngine


CHAT_API_ROOT = Path(__file__).parents[2]
HOST_ENTRY = CHAT_API_ROOT / "dsh" / "runtime-host" / "src" / "host.mjs"
CODEX_NODE = Path("/Users/jack/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node")


def _node_22_or_newer() -> Path | None:
    for value in (shutil.which("node"), str(CODEX_NODE)):
        candidate = Path(value) if value else None
        if not candidate or not candidate.is_file():
            continue
        result = subprocess.run([str(candidate), "--version"], capture_output=True, text=True, check=False)
        if int(result.stdout.strip().removeprefix("v").split(".", 1)[0]) >= 22:
            return candidate
    return None


class _BridgeHandler(BaseHTTPRequestHandler):
    model_tokens: ModelGatewayTokenService
    tool_tokens: ToolGatewayTokenService
    model_calls: list[dict] = []
    tool_calls: list[dict] = []
    approvals: list[dict] = []
    session_prompts: dict[str, str] = {}

    def do_POST(self):  # noqa: N802
        payload = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)))
        bearer = str(self.headers.get("authorization") or "").removeprefix("Bearer ")
        if self.path == "/model":
            self.model_tokens.verify(bearer)
            self.model_calls.append(payload)
            return self._model(payload)
        self.tool_tokens.verify(bearer)
        if self.path == "/tools/approval/request":
            self.approvals.append(payload)
            prompt = self.session_prompts.get(str(payload.get("sessionId")), "")
            return self._json({"outcome": "rejected" if "reject" in prompt else "allowed-once"})
        if self.path == "/tools/execute":
            self.tool_calls.append(payload)
            if payload["toolName"] == "compute_metrics":
                return self._json({"ok": True, "result": MetricsEngine.compute(payload["arguments"])})
            if payload["toolName"] == "external_search":
                return self._json({"ok": True, "result": {
                    "success": True,
                    "results": [{"title": "Current fact", "url": "https://example.test/fact", "snippet": "verified"}],
                    "total": 1,
                }})
            return self._json({"ok": True, "result": {
                "code": 0,
                "data": {"source": payload["toolName"], "arguments": payload["arguments"]},
            }})
        return self._json({"error": "not found"}, status=404)

    def _model(self, payload: dict):
        session_id = str(payload.get("sessionId") or "")
        messages = list(payload.get("messages") or [])
        has_result = any(
            isinstance(block, dict) and block.get("type") == "tool-result"
            for message in messages for block in list(message.get("content") or [])
        )
        if has_result:
            return self._ndjson([
                {"type": "text-delta", "text": "tool round complete"},
                {"type": "finish", "reason": {"kind": "stop"}},
            ])
        prompt = " ".join(
            str(block.get("text") or "")
            for message in messages
            if message.get("role") == "user"
            and (message.get("source") or {}).get("kind") == "user"
            for block in list(message.get("content") or []) if block.get("type") == "text"
        )
        self.session_prompts[session_id] = prompt
        tools = {item["name"]: item for item in payload.get("tools") or []}
        marker = (
            "web_search" if "use native web" in prompt
            else "progressive_research" if "use progressive" in prompt
            else "compute" if "compute" in prompt
            else "mcp" if "mcp" in prompt
            else "write" if "write" in prompt or "reject" in prompt
            else "http"
        )
        name = marker if marker in tools else next(name for name in tools if marker in name)
        arguments = (
            json.dumps({
                "records": [{"amount": 10}, {"amount": 20}],
                "calculations": [{"name": "total", "op": "sum", "field": "amount"}],
                "per_item_calculations": [],
            })
            if marker == "compute"
            else json.dumps({"queries": ["current fact"]})
            if marker == "web_search"
            else json.dumps({"query": "current fact"})
            if marker == "progressive_research"
            else "{\"value\":\"x\"}"
        )
        return self._ndjson([
            {"type": "tool-call", "id": f"call-{len(self.model_calls)}", "name": name, "arguments": arguments},
            {"type": "finish", "reason": {"kind": "tool-calls"}},
        ])

    def _json(self, payload: dict, status: int = 200):
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _ndjson(self, events: list[dict]):
        encoded = "".join(json.dumps(event) + "\n" for event in events).encode()
        self.send_response(200)
        self.send_header("content-type", "application/x-ndjson")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format: str, *_args):
        return


def _tool(name: str, *, source: str, approval: bool) -> ToolProfileDefinition:
    output_schema = (
        {"type": "string"}
        if source == "http"
        else {
            "type": "object",
            "properties": {"code": {"type": "integer"}, "data": {"type": "object"}},
            "required": ["code", "data"],
        }
    )
    return ToolProfileDefinition(
        name=name, version=f"v-{name}", source_type=source, external_tool_id=f"id-{name}",
        mcp_tool_name="native" if source == "mcp" else "", description=f"Call {name}",
        input_schema={"type": "object", "properties": {"value": {"type": "string"}}},
        output_schema=output_schema, output_validation="strict" if source == "mcp" else "none",
        risk_level="write" if approval else "read", approval_required=approval,
        required_scopes=(("tools:write" if approval else "tools:read"),), timeout_ms=2000,
    )


async def _collect(gateway: DshAgentKernelGateway, session_id: str):
    events = []
    async for event in gateway.subscribe(session_id):
        events.append(event)
        if event.type == "turn.completed":
            return events
    raise AssertionError("turn did not complete")


def test_real_dsh_tool_loop_http_mcp_approval_rejection_and_events(tmp_path: Path) -> None:
    asyncio.run(_run_e2e(tmp_path))


def test_real_dsh_host_calls_extracted_metrics_core_without_skill_or_graph(tmp_path: Path) -> None:
    asyncio.run(_run_internal_metrics_e2e(tmp_path))


def test_real_dsh_exposes_native_and_progressive_search_without_duplicate_primitive(tmp_path: Path) -> None:
    asyncio.run(_run_search_depth_e2e(tmp_path))


async def _run_search_depth_e2e(tmp_path: Path) -> None:
    node = _node_22_or_newer()
    if node is None:
        pytest.skip("Node.js 22+ is required")
    model_tokens = ModelGatewayTokenService("search-model-secret")
    tool_tokens = ToolGatewayTokenService("search-tool-secret")
    _BridgeHandler.model_tokens = model_tokens
    _BridgeHandler.tool_tokens = tool_tokens
    _BridgeHandler.model_calls = []
    _BridgeHandler.tool_calls = []
    _BridgeHandler.approvals = []
    _BridgeHandler.session_prompts = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _BridgeHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    search_primitive = ToolProfileDefinition(
        name="external_search", version="search-provider-v1", source_type="internal",
        external_tool_id="research.search_web@v1", capability_ref="research.search_web@v1",
        description="Internal provider primitive",
        input_schema={"type": "object", "properties": {
            "queries": {"type": "array", "items": {"type": "string"}},
            "max_results_per_query": {"type": "integer"},
        }, "required": ["queries"], "additionalProperties": False},
        output_schema={}, output_validation="none", risk_level="read", approval_required=False,
        required_scopes=("capabilities:read",), timeout_ms=120000,
    )
    progressive = ToolProfileDefinition(
        name="progressive_research", version="progressive-v1", source_type="internal",
        external_tool_id="research.progressive@v1", capability_ref="research.progressive@v1",
        description="Multi-round evidence research",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}},
                      "required": ["query"], "additionalProperties": False},
        output_schema={}, output_validation="none", risk_level="read", approval_required=False,
        required_scopes=("capabilities:read",), timeout_ms=300000,
    )
    profile = RuntimeProfileSnapshot(
        profile_version="profile-search-depth", content_hash="e" * 64, tenant_id="tenant-a", subject_user_id="user-a",
        model_source_tenant_id="tenant-a", model_instance_id="model-a", provider_id="provider-a",
        provider_type="openai_compatible", provider_name="provider", model_name="model", display_name="model",
        capabilities=("chat", "tools"), tool_versions=(search_primitive.version, progressive.version),
        tools=(search_primitive, progressive),
    )
    store = InMemoryRuntimeProfileStore()
    await store.publish(profile, actor_id="admin", activate=False)
    resolver = RuntimeProfileResolver(
        store, model_tokens, gateway_url=f"http://127.0.0.1:{server.server_port}/model",
        tool_token_service=tool_tokens, tool_gateway_url=f"http://127.0.0.1:{server.server_port}/tools",
    )
    host = DshRuntimeHostManager(DshHostConfig(
        node_executable=node, host_entry=HOST_ENTRY, storage_root=tmp_path / "sessions", log_path=tmp_path / "host.log",
    ))
    transport = None
    try:
        transport = HttpKernelHostTransport(await host.start(), timeout_seconds=5)
        gateway = DshAgentKernelGateway(transport, profile_resolver=resolver)
        runtime = await gateway.create_runtime(CreateRuntimeRequest(
            tenant_id="tenant-a", profile_version=profile.profile_version, isolation_key="tenant-a:search-depth",
        ))
        for index, prompt in enumerate(("use native web", "use progressive")):
            session = await gateway.create_session(CreateSessionRequest(
                runtime_id=runtime.runtime_id,
                session_spec=SessionSpec(conversation_id=f"search-{index}", tenant_id="tenant-a", user_id="user-a", profile_version=profile.profile_version),
            ))
            await gateway.send(SendRequest(
                session_id=session.session_id, request_id=f"search-request-{index}",
                content=[ContentBlock(type="text", data={"text": prompt})],
            ))
            await asyncio.wait_for(_collect(gateway, session.session_id), timeout=8)
        first_turn_tools = {item["name"] for item in _BridgeHandler.model_calls[0].get("tools") or []}
        assert {"web_search", "progressive_research"} <= first_turn_tools
        assert "external_search" not in first_turn_tools
        assert [call["toolName"] for call in _BridgeHandler.tool_calls] == [
            "external_search", "progressive_research",
        ]
    finally:
        if transport is not None:
            await transport.close()
        await host.stop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


async def _run_internal_metrics_e2e(tmp_path: Path) -> None:
    node = _node_22_or_newer()
    if node is None:
        pytest.skip("Node.js 22+ is required")
    model_tokens = ModelGatewayTokenService("step-6-real-model-secret")
    tool_tokens = ToolGatewayTokenService("step-6-real-tool-secret")
    _BridgeHandler.model_tokens = model_tokens
    _BridgeHandler.tool_tokens = tool_tokens
    _BridgeHandler.model_calls = []
    _BridgeHandler.tool_calls = []
    _BridgeHandler.approvals = []
    _BridgeHandler.session_prompts = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _BridgeHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    tool = ToolProfileDefinition(
        name="compute_metrics", version="metrics-v1", source_type="internal",
        external_tool_id="data.compute_metrics@v1", capability_ref="data.compute_metrics@v1",
        description="Compute deterministic metrics",
        input_schema={
            "type": "object",
            "properties": {
                "records": {"type": "array", "items": {}},
                "calculations": {"type": "array", "items": {"type": "object"}},
                "per_item_calculations": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["records", "calculations"],
            "additionalProperties": False,
        },
        output_schema={"type": "object", "properties": {"success": {"type": "boolean"}}, "required": ["success"], "additionalProperties": True},
        output_validation="strict", risk_level="read", approval_required=False,
        required_scopes=("capabilities:read",), timeout_ms=2000,
    )
    profile = RuntimeProfileSnapshot(
        profile_version="profile-step-6", content_hash="d" * 64, tenant_id="tenant-a", subject_user_id="user-a",
        model_source_tenant_id="tenant-a", model_instance_id="model-a", provider_id="provider-a",
        provider_type="openai_compatible", provider_name="provider", model_name="model", display_name="model",
        capabilities=("chat", "tools"), tool_versions=(tool.version,), tools=(tool,),
    )
    store = InMemoryRuntimeProfileStore()
    await store.publish(profile, actor_id="admin", activate=False)
    resolver = RuntimeProfileResolver(
        store, model_tokens, gateway_url=f"http://127.0.0.1:{server.server_port}/model",
        tool_token_service=tool_tokens, tool_gateway_url=f"http://127.0.0.1:{server.server_port}/tools",
    )
    host = DshRuntimeHostManager(DshHostConfig(
        node_executable=node, host_entry=HOST_ENTRY, storage_root=tmp_path / "sessions", log_path=tmp_path / "host.log",
    ))
    transport = None
    try:
        transport = HttpKernelHostTransport(await host.start(), timeout_seconds=5)
        gateway = DshAgentKernelGateway(transport, profile_resolver=resolver)
        runtime = await gateway.create_runtime(CreateRuntimeRequest(
            tenant_id="tenant-a", profile_version=profile.profile_version, isolation_key="tenant-a:step-6",
        ))
        session = await gateway.create_session(CreateSessionRequest(
            runtime_id=runtime.runtime_id,
            session_spec=SessionSpec(conversation_id="conversation-step-6", tenant_id="tenant-a", user_id="user-a", profile_version=profile.profile_version),
        ))
        await gateway.send(SendRequest(
            session_id=session.session_id, request_id="request-step-6",
            content=[ContentBlock(type="text", data={"text": "compute deterministic total"})],
        ))
        events = await asyncio.wait_for(_collect(gateway, session.session_id), timeout=8)
        assert _BridgeHandler.tool_calls[0]["toolName"] == "compute_metrics"
        assert any(event.type == "tool.call.completed" for event in events)
        assert any(event.type == "agent.message.completed" for event in events)
    finally:
        if transport is not None:
            await transport.close()
        await host.stop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


async def _run_e2e(tmp_path: Path) -> None:
    node = _node_22_or_newer()
    if node is None:
        pytest.skip("Node.js 22+ is required")
    model_tokens = ModelGatewayTokenService("step-5-real-model-secret")
    tool_tokens = ToolGatewayTokenService("step-5-real-tool-secret")
    _BridgeHandler.model_tokens = model_tokens
    _BridgeHandler.tool_tokens = tool_tokens
    _BridgeHandler.model_calls = []
    _BridgeHandler.tool_calls = []
    _BridgeHandler.approvals = []
    _BridgeHandler.session_prompts = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _BridgeHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    tools = (
        _tool("askai_http_lookup", source="http", approval=False),
        _tool("askai_mcp_search", source="mcp", approval=False),
        _tool("askai_write_publish", source="http", approval=True),
    )
    profile = RuntimeProfileSnapshot(
        profile_version="profile-tools", content_hash="c" * 64, tenant_id="tenant-a", subject_user_id="user-a",
        model_source_tenant_id="tenant-a", model_instance_id="model-a", provider_id="provider-a",
        provider_type="openai_compatible", provider_name="provider", model_name="model", display_name="model",
        capabilities=("chat", "tools"), tool_versions=tuple(item.version for item in tools), tools=tools,
    )
    store = InMemoryRuntimeProfileStore()
    await store.publish(profile, actor_id="admin", activate=False)
    resolver = RuntimeProfileResolver(
        store, model_tokens, gateway_url=f"http://127.0.0.1:{server.server_port}/model",
        tool_token_service=tool_tokens, tool_gateway_url=f"http://127.0.0.1:{server.server_port}/tools",
    )
    host = DshRuntimeHostManager(DshHostConfig(
        node_executable=node, host_entry=HOST_ENTRY, storage_root=tmp_path / "sessions", log_path=tmp_path / "host.log",
    ))
    transport = None
    try:
        transport = HttpKernelHostTransport(await host.start(), timeout_seconds=5)
        gateway = DshAgentKernelGateway(transport, profile_resolver=resolver)
        runtime = await gateway.create_runtime(CreateRuntimeRequest(
            tenant_id="tenant-a", profile_version=profile.profile_version, isolation_key="tenant-a:tools",
        ))
        results = {}
        for index, prompt in enumerate(("use http", "use mcp", "use write", "reject write")):
            session = await gateway.create_session(CreateSessionRequest(
                runtime_id=runtime.runtime_id,
                session_spec=SessionSpec(
                    conversation_id=f"conversation-{index}", tenant_id="tenant-a", user_id="user-a",
                    profile_version=profile.profile_version,
                ),
            ))
            await gateway.send(SendRequest(
                session_id=session.session_id, request_id=f"request-{index}",
                content=[ContentBlock(type="text", data={"text": prompt})],
            ))
            results[prompt] = await asyncio.wait_for(_collect(gateway, session.session_id), timeout=8)

        assert len(_BridgeHandler.tool_calls) == 3
        assert all(
            "Before calling a tool, briefly explain" in str(call.get("system") or "")
            for call in _BridgeHandler.model_calls
        )
        assert {call["toolName"] for call in _BridgeHandler.tool_calls} == {
            "askai_http_lookup", "askai_mcp_search", "askai_write_publish",
        }
        assert len(_BridgeHandler.approvals) == 2
        assert any(event.type == "tool.approval.requested" for event in results["use write"])
        assert any(event.type == "tool.approval.decided" for event in results["reject write"])
        assert any(event.type == "tool.call.completed" for event in results["use http"])
        assert all(any(event.type == "agent.message.completed" for event in events) for events in results.values())
    finally:
        if transport is not None:
            await transport.close()
        await host.stop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
