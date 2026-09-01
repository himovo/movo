from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from app.dsh_runtime import (
    DshAgentKernelGateway,
    DshHostConfig,
    DshRuntimeHostManager,
    HttpKernelHostTransport,
)
from app.dsh_runtime.contracts import (
    CancelSessionRequest,
    ContentBlock,
    CreateRuntimeRequest,
    CreateSessionRequest,
    SendMode,
    SendRequest,
    SessionSpec,
)
from app.dsh_runtime.errors import DshTransportError


CHAT_API_ROOT = Path(__file__).parents[2]
HOST_ENTRY = CHAT_API_ROOT / "dsh" / "runtime-host" / "src" / "host.mjs"
CODEX_NODE = Path("/Users/jack/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node")


def _node_22_or_newer() -> Path | None:
    candidates = [Path(value) for value in [shutil.which("node"), CODEX_NODE] if value]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        result = subprocess.run(
            [str(candidate), "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
        try:
            major = int(result.stdout.strip().removeprefix("v").split(".", 1)[0])
        except ValueError:
            continue
        if major >= 22:
            return candidate
    return None


async def _collect_until(
    gateway: DshAgentKernelGateway,
    session_id: str,
    event_type: str,
    after_cursor: int = 0,
):
    events = []
    async for event in gateway.subscribe(session_id, after_cursor):
        events.append(event)
        if event.type == event_type:
            return events
    raise AssertionError(f"subscription ended before {event_type}")


def _runtime_request(isolation_key: str = "tenant-a:profile-1") -> CreateRuntimeRequest:
    return CreateRuntimeRequest(
        tenant_id="tenant-a",
        profile_version="profile-1",
        isolation_key=isolation_key,
    )


async def _session(gateway: DshAgentKernelGateway, runtime_id: str, conversation_id: str):
    return await gateway.create_session(
        CreateSessionRequest(
            runtime_id=runtime_id,
            session_spec=SessionSpec(
                conversation_id=conversation_id,
                tenant_id="tenant-a",
                user_id="user-a",
                profile_version="profile-1",
            ),
        )
    )


def test_real_dsh_host_session_replay_cancel_isolation_plugin_and_crash(tmp_path: Path) -> None:
    asyncio.run(_test_real_dsh_host_session_replay_cancel_isolation_plugin_and_crash(tmp_path))


async def _test_real_dsh_host_session_replay_cancel_isolation_plugin_and_crash(tmp_path: Path) -> None:
    node = _node_22_or_newer()
    if node is None:
        pytest.skip("Node.js 22+ is required for the pinned DSH runtime")

    storage_root = tmp_path / "sessions"
    manager = DshRuntimeHostManager(
        DshHostConfig(
            node_executable=node,
            host_entry=HOST_ENTRY,
            storage_root=storage_root,
            log_path=tmp_path / "host.log",
        )
    )
    transport: HttpKernelHostTransport | None = None
    try:
        base_url = await manager.start()
        transport = HttpKernelHostTransport(base_url, timeout_seconds=10)
        gateway = DshAgentKernelGateway(transport)
        runtime = await gateway.create_runtime(_runtime_request())
        session = await _session(gateway, runtime.runtime_id, "conversation-1")

        await gateway.send(
            SendRequest(
                session_id=session.session_id,
                request_id="request-1",
                content=[ContentBlock(type="text", data={"text": "hello from step 2"})],
            )
        )
        events = await asyncio.wait_for(
            _collect_until(gateway, session.session_id, "turn.completed"),
            timeout=5,
        )
        completed = [event for event in events if event.type == "agent.message.completed"]
        assert completed
        assert "DSH deterministic: hello from step 2" in str(completed[-1].payload)
        assert [event.cursor for event in events] == sorted({event.cursor for event in events})

        replay_from = completed[-1].cursor - 1
        replayed = await asyncio.wait_for(anext(gateway.subscribe(session.session_id, replay_from)), timeout=2)
        assert replayed.cursor == completed[-1].cursor

        await gateway.send(
            SendRequest(
                session_id=session.session_id,
                request_id="request-slow",
                content=[ContentBlock(type="text", data={"text": "[slow] cancel me"})],
            )
        )
        async with httpx.AsyncClient(timeout=1) as client:
            health_started = asyncio.get_running_loop().time()
            health = await client.get(f"{base_url}/health")
            health_elapsed = asyncio.get_running_loop().time() - health_started
        assert health.json()["ok"] is True
        assert health_elapsed < 0.5
        await gateway.cancel(CancelSessionRequest(session_id=session.session_id, cause="test cancellation"))
        cancelled = await asyncio.wait_for(
            _collect_until(gateway, session.session_id, "turn.completed", events[-1].cursor),
            timeout=3,
        )
        assert cancelled[-1].payload["reason"] == {"kind": "aborted", "reason": {"kind": "user"}}

        await gateway.send(
            SendRequest(
                session_id=session.session_id,
                request_id="request-steer",
                mode=SendMode.STEER,
                content=[ContentBlock(type="text", data={"text": "steer after cancellation"})],
            )
        )
        steered = await asyncio.wait_for(
            _collect_until(gateway, session.session_id, "turn.completed", cancelled[-1].cursor),
            timeout=3,
        )
        assert any(event.type == "agent.message.completed" for event in steered)

        second = await gateway.create_runtime(_runtime_request("tenant-b:profile-1"))
        with pytest.raises(DshTransportError, match="not live"):
            await transport.request(
                "GET",
                f"/v1/runtimes/{second.runtime_id}/sessions/{session.session_id}/events",
                params={"after": 0},
            )

        plugin = "@deepseek-ai/cordis-plugin-timer"
        assert (await gateway.native_plugin(runtime.runtime_id, "load", plugin))["loaded"] is True
        assert (await gateway.native_plugin(runtime.runtime_id, "probe", plugin))["capability"] == "timer.timeout"
        assert (await gateway.native_plugin(runtime.runtime_id, "unload", plugin))["unloaded"] is True

        persisted_session_id = session.session_id
        await transport.close()
        transport = None
        await manager.stop()

        base_url = await manager.start()
        transport = HttpKernelHostTransport(base_url, timeout_seconds=10)
        gateway_after_restart = DshAgentKernelGateway(transport)
        runtime_after_restart = await gateway_after_restart.create_runtime(_runtime_request())
        resumed = await transport.request(
            "POST",
            f"/v1/runtimes/{runtime_after_restart.runtime_id}/sessions/{persisted_session_id}/resume",
        )
        assert resumed["sessionId"] == persisted_session_id

        crash_session = await _session(gateway_after_restart, runtime_after_restart.runtime_id, "conversation-crash")
        assert manager.process is not None
        manager.process.kill()
        await manager.process.wait()
        failure = await asyncio.wait_for(anext(gateway_after_restart.subscribe(crash_session.session_id)), timeout=3)
        assert failure.type == "runtime.failed"
        assert failure.payload["retryable"] is True
    finally:
        if transport is not None:
            await transport.close()
        await manager.stop()
