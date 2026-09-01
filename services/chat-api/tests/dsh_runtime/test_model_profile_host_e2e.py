from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from app.dsh_runtime import (
    DshAgentKernelGateway,
    DshHostConfig,
    DshRuntimeHostManager,
    HttpKernelHostTransport,
)
from app.dsh_runtime.contracts import (
    ContentBlock,
    CreateRuntimeRequest,
    CreateSessionRequest,
    SendRequest,
    SessionSpec,
)
from app.dsh_runtime.model_gateway.token import ModelGatewayTokenService
from app.dsh_runtime.profile import InMemoryRuntimeProfileStore, RuntimeProfileResolver, RuntimeProfileSnapshot


CHAT_API_ROOT = Path(__file__).parents[2]
HOST_ENTRY = CHAT_API_ROOT / "dsh" / "runtime-host" / "src" / "host.mjs"
CODEX_NODE = Path("/Users/jack/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node")


def _node_22_or_newer() -> Path | None:
    candidates = [Path(value) for value in [shutil.which("node"), CODEX_NODE] if value]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        result = subprocess.run([str(candidate), "--version"], capture_output=True, text=True, check=False)
        try:
            if int(result.stdout.strip().removeprefix("v").split(".", 1)[0]) >= 22:
                return candidate
        except ValueError:
            continue
    return None


class _GatewayHandler(BaseHTTPRequestHandler):
    tokens: ModelGatewayTokenService
    calls: list[dict[str, object]] = []

    def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
        length = int(self.headers.get("content-length") or 0)
        payload = json.loads(self.rfile.read(length))
        authorization = self.headers.get("authorization") or ""
        content_type = "application/json"
        try:
            claims = self.tokens.verify(authorization.removeprefix("Bearer "))
            assert claims.profile_version == payload["profileVersion"]
            assert claims.model_instance_id == payload["modelInstanceId"]
            self.calls.append({"authorization": authorization, "payload": payload})
            user_text = next(
                block["text"]
                for message in reversed(payload["messages"])
                if message["role"] == "user"
                for block in message["content"]
                if block["type"] == "text"
                and not str(block["text"]).startswith("Current runtime context.")
            )
            if user_text == "[auth-fail]":
                body = {
                    "error": {
                        "code": "model_authentication_failed",
                        "message": "invalid managed provider credential",
                        "retryable": False,
                    }
                }
                encoded = json.dumps(body).encode()
                self.send_response(401)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                return
            events = [
                {"type": "text-delta", "text": f"MODEL[{payload['modelInstanceId']}]: "},
                {"type": "text-delta", "text": user_text},
                {"type": "usage", "usage": {"inputTokens": 5, "outputTokens": 7}},
                {"type": "finish", "reason": {"kind": "stop"}},
            ]
            encoded = "".join(f"{json.dumps(event)}\n" for event in events).encode()
            content_type = "application/x-ndjson"
            self.send_response(200)
        except Exception as exc:  # pragma: no cover - asserted through DSH failure
            encoded = json.dumps({"error": {"code": "mock_invalid", "message": str(exc)}}).encode()
            self.send_response(401)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _snapshot(profile: str, model_id: str, model_name: str) -> RuntimeProfileSnapshot:
    content_hash = ("a" if model_id == "model-a" else "b") * 64
    return RuntimeProfileSnapshot(
        profile_version=profile,
        content_hash=content_hash,
        tenant_id="tenant-a",
        model_source_tenant_id="tenant-a",
        model_instance_id=model_id,
        provider_id="provider-a",
        provider_type="openai_compatible",
        provider_name="managed provider",
        model_name=model_name,
        display_name=model_name,
        capabilities=("chat",),
        max_output_tokens=1024,
    )


async def _collect_completed(gateway: DshAgentKernelGateway, session_id: str, after_cursor: int = 0):
    events = []
    async for event in gateway.subscribe(session_id, after_cursor):
        events.append(event)
        if event.type == "turn.completed":
            return events
    raise AssertionError("DSH subscription ended without turn completion")


def test_real_dsh_uses_default_and_explicit_immutable_model_profiles(tmp_path: Path) -> None:
    asyncio.run(_test_real_dsh_uses_default_and_explicit_immutable_model_profiles(tmp_path))


async def _test_real_dsh_uses_default_and_explicit_immutable_model_profiles(tmp_path: Path) -> None:
    node = _node_22_or_newer()
    if node is None:
        pytest.skip("Node.js 22+ is required for the pinned DSH runtime")

    token_service = ModelGatewayTokenService("step-3-real-host-signing-secret")
    _GatewayHandler.tokens = token_service
    _GatewayHandler.calls = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GatewayHandler)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    store = InMemoryRuntimeProfileStore()
    profile_a = _snapshot("profile-a", "model-a", "deepseek-chat")
    profile_b = _snapshot("profile-b", "model-b", "deepseek-reasoner")
    await store.publish(profile_a, actor_id="admin")
    await store.publish(profile_b, actor_id="admin")
    resolver = RuntimeProfileResolver(
        store,
        token_service,
        gateway_url=f"http://127.0.0.1:{server.server_port}/generate",
    )
    host = DshRuntimeHostManager(
        DshHostConfig(
            node_executable=node,
            host_entry=HOST_ENTRY,
            storage_root=tmp_path / "sessions",
            log_path=tmp_path / "host.log",
        )
    )
    transport: HttpKernelHostTransport | None = None
    try:
        base_url = await host.start()
        # Loading the full official DSH composition is intentionally heavier
        # than an ordinary request; use the production transport budget so the
        # contract test does not become CPU-load dependent.
        transport = HttpKernelHostTransport(base_url, timeout_seconds=10)
        gateway = DshAgentKernelGateway(
            transport,
            profile_resolver=resolver,
        )
        handles = []
        for index, snapshot in enumerate((profile_a, profile_b), start=1):
            runtime = await gateway.create_runtime(
                CreateRuntimeRequest(
                    tenant_id="tenant-a",
                    profile_version=snapshot.profile_version,
                    isolation_key=f"tenant-a:{snapshot.profile_version}",
                )
            )
            session = await gateway.create_session(
                CreateSessionRequest(
                    runtime_id=runtime.runtime_id,
                    session_spec=SessionSpec(
                        conversation_id=f"conversation-{index}",
                        tenant_id="tenant-a",
                        user_id="user-a",
                        profile_version=snapshot.profile_version,
                    ),
                )
            )
            assert runtime.model_instance_id == snapshot.model_instance_id
            assert session.model_instance_id == snapshot.model_instance_id
            handles.append((runtime, session, snapshot))

        last_events: dict[str, list[object]] = {}
        for index, (_runtime, session, snapshot) in enumerate(handles, start=1):
            await gateway.send(
                SendRequest(
                    session_id=session.session_id,
                    request_id=f"request-{index}",
                    content=[ContentBlock(type="text", data={"text": f"hello-{index}"})],
                )
            )
            events = await asyncio.wait_for(_collect_completed(gateway, session.session_id), timeout=5)
            deltas = [event for event in events if event.type == "agent.message.delta"]
            completed = [event for event in events if event.type == "agent.message.completed"]
            assert len(deltas) >= 2
            assert completed
            assert f"MODEL[{snapshot.model_instance_id}]: hello-{index}" in str(completed[-1].payload)
            last_events[session.session_id] = events

        assert [call["payload"]["modelInstanceId"] for call in _GatewayHandler.calls] == ["model-a", "model-b"]
        assert all("LONG-LIVED" not in json.dumps(call) for call in _GatewayHandler.calls)
        for call in _GatewayHandler.calls:
            model_messages = call["payload"]["messages"]
            snapshots = [
                block["text"]
                for message in model_messages
                for block in message["content"]
                if block["type"] == "text" and str(block["text"]).startswith("Current runtime context.")
            ]
            assert snapshots
            assert "Trusted time context supplied by MOVO" in snapshots[-1]
            assert "User timezone: UTC" in snapshots[-1]

        error_session = handles[0][1]
        after_cursor = last_events[error_session.session_id][-1].cursor
        await gateway.send(
            SendRequest(
                session_id=error_session.session_id,
                request_id="request-auth-failure",
                content=[ContentBlock(type="text", data={"text": "[auth-fail]"})],
            )
        )
        failure_events = await asyncio.wait_for(
            _collect_completed(gateway, error_session.session_id, after_cursor),
            timeout=5,
        )
        failure = next(event for event in failure_events if event.type == "model.request.failed")
        assert failure.payload["code"] == "model.authentication.failed"
        assert failure.payload["retryable"] is False

        await store.disable(profile_b.profile_version, actor_id="admin")
        with pytest.raises(ValueError, match="disabled"):
            await gateway.create_runtime(
                CreateRuntimeRequest(
                    tenant_id="tenant-a",
                    profile_version=profile_b.profile_version,
                    isolation_key="tenant-a:disabled-profile",
                )
            )
    finally:
        if transport is not None:
            await transport.close()
        await host.stop()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)
