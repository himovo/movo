from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest

from app.dsh_runtime.contracts import (
    ContentBlock,
    CreateRuntimeRequest,
    CreateSessionRequest,
    SendRequest,
    SessionSpec,
)
from app.dsh_runtime.errors import DshProtocolError, DshTransportError
from app.dsh_runtime.gateway import DshAgentKernelGateway
from app.dsh_runtime.temporal_context import build_temporal_context


class FakeHostTransport:
    def __init__(self) -> None:
        self.session_id = ""
        self.event_responses: list[object] = []
        self.fail_events = False
        self.kernel_version = "0.1.0-rc.6"
        self.last_send_payload: Mapping[str, Any] | None = None
        self.last_session_payload: Mapping[str, Any] | None = None

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if method == "POST" and path == "/v1/runtimes":
            return {
                "runtimeId": "runtime-1",
                "kernelVersion": self.kernel_version,
                "profileVersion": json["profileVersion"],
                "isolationKey": json["isolationKey"],
            }
        if method == "POST" and path.endswith("/sessions"):
            self.last_session_payload = json
            self.session_id = str(json["sessionId"])
            return {
                "sessionId": self.session_id,
                "status": "idle",
                "presetId": json["presetId"],
                "workspaceId": json.get("workspaceId"),
            }
        if method == "POST" and path.endswith("/send"):
            self.last_send_payload = json
            return {"accepted": True, "messageId": "message-1"}
        if method == "GET" and path.endswith("/events"):
            if self.fail_events:
                raise DshTransportError("host died")
            value = self.event_responses.pop(0) if self.event_responses else []
            return {"events": value}
        if method in {"POST", "DELETE"}:
            return {"disposed": True, "accepted": True, "status": "idle", "sessionId": self.session_id}
        raise AssertionError((method, path, json, params))

    async def stream(self, method: str, path: str, *, params=None):
        assert method == "GET"
        assert path.endswith("/event-stream")
        if self.fail_events:
            raise DshTransportError("host died")
        value = self.event_responses.pop(0) if self.event_responses else []
        # The Runtime Host's journal stream guarantees cursor order, including
        # replayed events written before live subscription begins.
        for event in sorted(
            value,
            key=lambda item: item.get("cursor", -1) if isinstance(item.get("cursor"), int) else -1,
        ):
            yield event


async def _prepared_gateway(transport: FakeHostTransport) -> tuple[DshAgentKernelGateway, str]:
    gateway = DshAgentKernelGateway(transport)
    runtime = await gateway.create_runtime(
        CreateRuntimeRequest(tenant_id="tenant-a", profile_version="profile-1", isolation_key="tenant-a:profile-1")
    )
    session = await gateway.create_session(
        CreateSessionRequest(
            runtime_id=runtime.runtime_id,
            session_spec=SessionSpec(
                conversation_id="conversation-1",
                tenant_id="tenant-a",
                user_id="user-a",
                profile_version="profile-1",
            ),
        )
    )
    return gateway, session.session_id


def test_gateway_lifecycle_and_out_of_order_duplicate_replay() -> None:
    asyncio.run(_test_gateway_lifecycle_and_out_of_order_duplicate_replay())


def test_gateway_forwards_and_validates_immutable_session_preset() -> None:
    async def run() -> None:
        transport = FakeHostTransport()
        gateway = DshAgentKernelGateway(transport)
        runtime = await gateway.create_runtime(CreateRuntimeRequest(
            tenant_id="tenant-a", profile_version="profile-1", isolation_key="tenant-a:profile-1",
        ))
        session = await gateway.create_session(CreateSessionRequest(
            runtime_id=runtime.runtime_id,
            session_spec=SessionSpec(
                conversation_id="code-conversation", tenant_id="tenant-a", user_id="user-a",
                profile_version="profile-1", preset_id="code", execution_location="desktop",
                workspace_id="workspace-a",
            ),
        ))
        assert transport.last_session_payload is not None
        assert transport.last_session_payload["presetId"] == "code"
        assert transport.last_session_payload["workspaceId"] == "workspace-a"
        assert session.preset_id == "code"

    asyncio.run(run())


def test_gateway_forwards_predecessor_identity_for_native_session_seed() -> None:
    async def run() -> None:
        transport = FakeHostTransport()
        gateway = DshAgentKernelGateway(transport)
        runtime = await gateway.create_runtime(CreateRuntimeRequest(
            tenant_id="tenant-a", profile_version="profile-2", isolation_key="tenant-a:profile-2",
        ))
        await gateway.create_session(CreateSessionRequest(
            runtime_id=runtime.runtime_id,
            session_spec=SessionSpec(
                conversation_id="conversation-1", tenant_id="tenant-a", user_id="user-a",
                profile_version="profile-2", seed_runtime_id="runtime-old",
                seed_session_id="session-old",
            ),
        ))
        assert transport.last_session_payload is not None
        assert transport.last_session_payload["seedRuntimeId"] == "runtime-old"
        assert transport.last_session_payload["seedSessionId"] == "session-old"

    asyncio.run(run())


async def _test_gateway_lifecycle_and_out_of_order_duplicate_replay() -> None:
    transport = FakeHostTransport()
    gateway, session_id = await _prepared_gateway(transport)
    message_id = await gateway.send(
        SendRequest(
            session_id=session_id,
            request_id="request-1",
            content=[ContentBlock(type="text", data={"text": "hello"})],
            temporal_context=build_temporal_context("Asia/Shanghai"),
        )
    )
    assert message_id == "message-1"
    assert transport.last_send_payload is not None
    assert transport.last_send_payload["temporalContext"]["user_timezone"] == "Asia/Shanghai"

    transport.event_responses.append(
        [
            {"cursor": 2, "nativeType": "assistant/message", "nativeSeq": 9, "time": 1_786_764_523_000, "data": {}},
            {"cursor": 1, "nativeType": "turn/start", "nativeSeq": 1, "time": 1_786_764_522_000, "data": {}},
            {"cursor": 2, "nativeType": "assistant/message", "nativeSeq": 9, "time": 1_786_764_523_000, "data": {}},
        ]
    )
    events = []
    async for event in gateway.subscribe(session_id):
        events.append(event)
        if len(events) == 2:
            break
    assert [event.cursor for event in events] == [1, 2]
    assert [event.type for event in events] == ["turn.started", "agent.message.completed"]


def test_gateway_fails_loud_on_malformed_events() -> None:
    asyncio.run(_test_gateway_fails_loud_on_malformed_events())


async def _test_gateway_fails_loud_on_malformed_events() -> None:
    transport = FakeHostTransport()
    gateway, session_id = await _prepared_gateway(transport)
    transport.event_responses.append([{"cursor": "bad"}])
    with pytest.raises(DshProtocolError, match="malformed"):
        await anext(gateway.subscribe(session_id))


def test_gateway_projects_host_crash_as_terminal_failure() -> None:
    asyncio.run(_test_gateway_projects_host_crash_as_terminal_failure())


async def _test_gateway_projects_host_crash_as_terminal_failure() -> None:
    transport = FakeHostTransport()
    gateway, session_id = await _prepared_gateway(transport)
    transport.fail_events = True
    event = await anext(gateway.subscribe(session_id, after_cursor=7))
    assert event.cursor == 8
    assert event.type == "runtime.failed"
    assert event.payload["code"] == "dsh_runtime_unavailable"


def test_contract_survives_compatible_kernel_upgrade_fixture() -> None:
    asyncio.run(_test_contract_survives_compatible_kernel_upgrade_fixture())


async def _test_contract_survives_compatible_kernel_upgrade_fixture() -> None:
    transport = FakeHostTransport()
    transport.kernel_version = "0.1.0-rc.7-compat-fixture"
    gateway, session_id = await _prepared_gateway(transport)
    transport.event_responses.append(
        [{"cursor": 1, "nativeType": "turn/start", "nativeSeq": 0, "time": 1_786_764_522_000, "data": {}}]
    )
    event = await anext(gateway.subscribe(session_id))
    assert event.schema_version == "askai.kernel-event.v1"
    assert event.type == "turn.started"


def test_model_finish_failure_maps_to_standard_kernel_error_payload() -> None:
    asyncio.run(_test_model_finish_failure_maps_to_standard_kernel_error_payload())


async def _test_model_finish_failure_maps_to_standard_kernel_error_payload() -> None:
    transport = FakeHostTransport()
    gateway, session_id = await _prepared_gateway(transport)
    transport.event_responses.append(
        [{
            "cursor": 1,
            "nativeType": "assistant/chunk",
            "nativeSeq": 3,
            "time": 1_786_764_522_000,
            "data": {
                "chunk": {
                    "type": "finish",
                    "reason": {
                        "kind": "error",
                        "failure": {"code": "MODEL_AUTHENTICATION_FAILED", "message": "bad key", "status": 401},
                    },
                }
            },
        }]
    )
    event = await anext(gateway.subscribe(session_id))
    assert event.type == "model.request.failed"
    assert event.payload == {
        "code": "model.authentication.failed",
        "message": "bad key",
        "retryable": False,
        "details": {"status": 401},
        "native_seq": 3,
    }
