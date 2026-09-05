from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from time import monotonic
from types import SimpleNamespace

from app.dsh_runtime.chat_service import DshChatService
from app.dsh_runtime.contracts import KernelEventEnvelope, KernelEventSource
from app.dsh_runtime.events import KernelEventProjector, KernelEventWrite
from app.dsh_runtime.events.durable_writer import DurableKernelEventWriter
from app.dsh_runtime.events.live_stream import LiveTurnStream
from app.dsh_runtime.events.projection_writer import ProjectionScope
from app.dsh_runtime.events.turn_channel import TurnEventRegistry
from app.dsh_runtime.temporal_context import build_temporal_context
from app.dsh_runtime.profile.models import RuntimeProfileSnapshot


def _event(cursor: int, event_type: str, payload: dict) -> KernelEventEnvelope:
    return KernelEventEnvelope(
        event_id=f"runtime:session:{cursor}",
        runtime_id="runtime",
        session_id="session",
        profile_version="profile",
        cursor=cursor,
        type=event_type,
        occurred_at=datetime.now(timezone.utc),
        payload=payload,
        source=KernelEventSource(kernel_version="0.1.0-rc.6", native_event_type=event_type),
    )


class _BatchEvents:
    def __init__(self, delay: float = 0) -> None:
        self.delay = delay
        self.calls: list[list[KernelEventWrite]] = []
        self.persisted: list[dict] = []
        self.side_persisted: list[dict] = []
        self.projector = KernelEventProjector()

    def project(self, event, *, message_id, tool_presentations=None):
        return self.projector.project(
            event,
            message_id=message_id,
            tool_presentations=tool_presentations,
        )

    async def persist_batch(self, writes, **_scope):
        if self.delay:
            await asyncio.sleep(self.delay)
        self.calls.append(list(writes))
        self.persisted.extend(write.projected for write in writes if write.projected is not None)

    async def persist_projections(self, rows, **_scope):
        if self.delay:
            await asyncio.sleep(self.delay)
        self.side_persisted.extend(dict(row) for row in rows)
        self.persisted.extend(dict(row) for row in rows)

    async def all_for_message(self, *_args, **_kwargs):
        return list(self.persisted)


class _Bindings:
    def __init__(self) -> None:
        self.cursors: list[int] = []
        self.finished_at: float | None = None
        self.finished_status: str | None = None

    async def advance_cursor(self, _binding_id: str, cursor: int) -> None:
        self.cursors.append(cursor)

    async def finish_turn(self, *_args, **kwargs) -> None:
        self.finished_at = monotonic()
        self.finished_status = kwargs.get("status")


class _Conversations:
    def __init__(self) -> None:
        self.updated_at: float | None = None
        self.execution_events: list[dict] = []
        self.active_run_cleared = False

    async def update_assistant_projection(self, **kwargs) -> None:
        self.execution_events = kwargs["execution_events"]
        self.updated_at = monotonic()

    async def clear_active_run(self, **_kwargs) -> None:
        self.active_run_cleared = True


class _Gateway:
    async def send(self, _request) -> str:
        return "native-message"

    async def subscribe(self, _session_id: str, _after_cursor: int):
        events = [
            _event(1, "turn.started", {}),
            _event(2, "agent.message.delta", {"chunk": {"type": "text-delta", "text": "A"}}),
            _event(3, "agent.message.delta", {"chunk": {"type": "text-delta", "text": "B"}}),
            _event(4, "agent.message.completed", {"message": {"content": [{"type": "text", "text": "AB"}]}}),
            _event(5, "turn.completed", {"reason": {"kind": "stop"}}),
        ]
        for event in events:
            await asyncio.sleep(0.005)
            yield event


class _Profiles:
    async def get(self, _profile_version: str):
        return RuntimeProfileSnapshot(
            profile_version="profile", content_hash="a" * 64, tenant_id="tenant",
            model_source_tenant_id="tenant", model_instance_id="model", provider_id="provider",
            provider_type="openai_compatible", provider_name="provider", model_name="model",
            display_name="model", capabilities=("chat",),
        )


def test_live_delta_bypasses_slow_persistence_but_terminal_waits_for_flush() -> None:
    asyncio.run(_test_live_delta_bypasses_slow_persistence_but_terminal_waits_for_flush())


async def _test_live_delta_bypasses_slow_persistence_but_terminal_waits_for_flush() -> None:
    events = _BatchEvents(delay=0.15)
    bindings = _Bindings()
    conversations = _Conversations()
    service = DshChatService(
        gateway=_Gateway(),
        coordinator=SimpleNamespace(),
        conversations=conversations,
        bindings=bindings,
        events=events,
        profiles=_Profiles(),
        kernel_version="0.1.0-rc.6",
    )
    live = LiveTurnStream()
    binding = {
        "binding_id": "binding",
        "tenant_id": "tenant",
        "user_id": "user",
        "conversation_id": "conversation",
        "kernel_session_id": "session",
        "runtime_id": "runtime",
        "profile_version": "profile",
        "event_cursor": 0,
    }
    started = monotonic()
    task = asyncio.create_task(
        service._turn_runner.run(
            binding=binding,
            message_id="message",
                request_id="request",
                text="hello",
                temporal_context=build_temporal_context("UTC"),
                live_stream=live,
        )
    )
    arrivals: list[tuple[str, float]] = []
    async for projected in live.events():
        arrivals.append((str(projected["type"]), monotonic()))
    await task

    first_delta_at = next(at for kind, at in arrivals if kind == "item.delta")
    terminal_at = next(at for kind, at in arrivals if kind == "run.completed")
    assert first_delta_at - started < 0.08
    assert terminal_at - started >= 0.15
    assert conversations.updated_at is not None and conversations.updated_at <= terminal_at
    assert bindings.finished_at is not None and bindings.finished_at <= terminal_at
    assert conversations.active_run_cleared is True
    assert bindings.cursors == [5]
    assert [event["type"] for event in conversations.execution_events] == [
        "run.started",
        "item.completed",
        "run.completed",
    ]


def test_durable_writer_batches_in_order_and_commits_one_cursor_per_batch() -> None:
    asyncio.run(_test_durable_writer_batches_in_order_and_commits_one_cursor_per_batch())


def test_active_turn_refreshes_credentials_during_a_long_tool_gap() -> None:
    async def run() -> None:
        class _SlowGateway(_Gateway):
            def __init__(self) -> None:
                self.refreshes = 0

            async def refresh_session_credentials(self, _session_id: str) -> None:
                self.refreshes += 1

            async def subscribe(self, _session_id: str, _after_cursor: int):
                yield _event(1, "turn.started", {})
                await asyncio.sleep(0.09)
                yield _event(2, "turn.completed", {"reason": {"kind": "stop"}})

        gateway = _SlowGateway()
        service = DshChatService(
            gateway=gateway,
            coordinator=SimpleNamespace(),
            conversations=_Conversations(),
            bindings=_Bindings(),
            events=_BatchEvents(),
            profiles=_Profiles(),
            kernel_version="0.1.0-rc.6",
        )
        service._turn_runner._credential_refresh_interval_seconds = 0.02
        live = LiveTurnStream()
        binding = {
            "binding_id": "binding", "tenant_id": "tenant", "user_id": "user",
            "conversation_id": "conversation", "kernel_session_id": "session",
            "runtime_id": "runtime", "profile_version": "profile", "event_cursor": 0,
        }
        task = asyncio.create_task(service._turn_runner.run(
            binding=binding,
            message_id="message",
            request_id="request",
            text="long tool",
            temporal_context=build_temporal_context("UTC"),
            live_stream=live,
        ))
        async for _event_row in live.events():
            pass
        assert await task == "completed"
        assert gateway.refreshes >= 1

    asyncio.run(run())


def test_cancelled_runner_releases_binding_and_sidebar_state() -> None:
    async def run() -> None:
        started = asyncio.Event()

        class _HangingGateway(_Gateway):
            async def refresh_session_credentials(self, _session_id: str) -> None:
                return None

            async def subscribe(self, _session_id: str, _after_cursor: int):
                started.set()
                await asyncio.Event().wait()
                if False:
                    yield _event(1, "turn.started", {})

        bindings = _Bindings()
        conversations = _Conversations()
        service = DshChatService(
            gateway=_HangingGateway(),
            coordinator=SimpleNamespace(),
            conversations=conversations,
            bindings=bindings,
            events=_BatchEvents(),
            profiles=_Profiles(),
            kernel_version="0.1.0-rc.6",
        )
        binding = {
            "binding_id": "binding", "tenant_id": "tenant", "user_id": "user",
            "conversation_id": "conversation", "kernel_session_id": "session",
            "runtime_id": "runtime", "profile_version": "profile", "event_cursor": 0,
        }
        live = LiveTurnStream()
        task = asyncio.create_task(service._turn_runner.run(
            binding=binding,
            message_id="message",
            request_id="request",
            text="cancel me",
            temporal_context=build_temporal_context("UTC"),
            live_stream=live,
        ))
        await started.wait()
        task.cancel()
        assert await task == "cancelled"
        assert bindings.finished_status == "cancelled"
        assert conversations.active_run_cleared is True

    asyncio.run(run())


def test_stream_ending_without_terminal_event_fails_and_releases_turn() -> None:
    async def run() -> None:
        class _InterruptedGateway(_Gateway):
            async def refresh_session_credentials(self, _session_id: str) -> None:
                return None

            async def subscribe(self, _session_id: str, _after_cursor: int):
                if False:
                    yield _event(1, "turn.started", {})

        bindings = _Bindings()
        conversations = _Conversations()
        service = DshChatService(
            gateway=_InterruptedGateway(),
            coordinator=SimpleNamespace(),
            conversations=conversations,
            bindings=bindings,
            events=_BatchEvents(),
            profiles=_Profiles(),
            kernel_version="0.1.0-rc.6",
        )
        live = LiveTurnStream()
        result = await service._turn_runner.run(
            binding={
                "binding_id": "binding", "tenant_id": "tenant", "user_id": "user",
                "conversation_id": "conversation", "kernel_session_id": "session",
                "runtime_id": "runtime", "profile_version": "profile", "event_cursor": 0,
            },
            message_id="message",
            request_id="request",
            text="interrupt me",
            temporal_context=build_temporal_context("UTC"),
            live_stream=live,
        )
        assert result == "failed"
        assert bindings.finished_status == "failed"
        assert conversations.active_run_cleared is True

    asyncio.run(run())


async def _test_durable_writer_batches_in_order_and_commits_one_cursor_per_batch() -> None:
    events = _BatchEvents()
    bindings = _Bindings()
    writer = DurableKernelEventWriter(
        events=events,
        bindings=bindings,
        binding_id="binding",
        tenant_id="tenant",
        user_id="user",
        conversation_id="conversation",
        message_id="message",
        max_batch_size=64,
        max_batch_delay_seconds=10,
    )
    for cursor in range(1, 131):
        writer.enqueue(KernelEventWrite(event=_event(cursor, "kernel.native.event", {}), projected=None))
    await writer.close()

    assert [len(batch) for batch in events.calls] == [64, 64, 2]
    assert bindings.cursors == [64, 128, 130]


def test_durable_writer_flush_deadline_is_measured_from_first_event() -> None:
    asyncio.run(_test_durable_writer_flush_deadline_is_measured_from_first_event())


def test_browser_side_band_joins_the_same_live_and_history_order() -> None:
    asyncio.run(_test_browser_side_band_joins_the_same_live_and_history_order())


def test_standalone_approval_is_live_and_durable_without_matching_tool_call_id() -> None:
    async def run() -> None:
        events = _BatchEvents()
        registry = TurnEventRegistry(events)
        live = LiveTurnStream()
        registry.register(ProjectionScope(
            tenant_id="tenant", user_id="user", conversation_id="conversation",
            message_id="message", kernel_session_id="session",
        ), live)
        approval = {
            "event_id": "approval:protocol-id:1", "id": "approval:protocol-id:1",
            "type": "item.started", "item_kind": "approval", "item_id": "protocol-id",
            "revision": 1, "payload": {"source": "askai-approval", "status": "pending"},
        }
        await registry.publish_standalone("message", approval)
        delivered = await asyncio.wait_for(live._queue.get(), timeout=1)
        assert delivered["item_id"] == "protocol-id"
        history = await registry.finish("message")
        assert history[0]["item_id"] == "protocol-id"
        assert events.side_persisted[0]["item_id"] == "protocol-id"

    asyncio.run(run())


async def _test_browser_side_band_joins_the_same_live_and_history_order() -> None:
    events = _BatchEvents()
    bindings = _Bindings()
    conversations = _Conversations()
    turn_events = TurnEventRegistry(events)
    live = LiveTurnStream()
    turn_events.register(
        ProjectionScope(
            tenant_id="tenant", user_id="user", conversation_id="conversation",
            message_id="message", kernel_session_id="session",
        ),
        live,
    )
    sink = turn_events.progress_sink("message", "call-browser")
    assert sink is not None

    class _BrowserGateway:
        async def send(self, _request) -> str:
            return "native-message"

        async def subscribe(self, _session_id: str, _after_cursor: int):
            yield _event(1, "turn.started", {})
            yield _event(2, "tool.call.started", {
                "callId": "call-browser", "name": "browser_task", "arguments": "{}",
            })
            await sink({
                "v": 3,
                "event_id": "askai-v3:browser:message:call-browser:1",
                "id": "askai-v3:browser:message:call-browser:1",
                "ts": 2,
                "type": "item.completed",
                "item_kind": "activity",
                "item_id": "call-browser:browser-activity:1",
                "parent_item_id": "call-browser",
                "revision": 1,
                "payload": {"label": "正在读取搜索结果", "category": "browser"},
            })
            yield _event(3, "tool.call.completed", {
                "message": {
                    "source": {"callId": "call-browser"},
                    "content": [{
                        "type": "tool-result", "toolCallId": "call-browser",
                        "content": [{"type": "text", "text": "{\"success\":true}"}],
                        "isError": False,
                    }],
                },
            })
            yield _event(4, "turn.completed", {"reason": {"kind": "stop"}})

    service = DshChatService(
        gateway=_BrowserGateway(),
        coordinator=SimpleNamespace(),
        conversations=conversations,
        bindings=bindings,
        events=events,
        profiles=_Profiles(),
        kernel_version="0.1.0-rc.6",
        turn_events=turn_events,
    )
    binding = {
        "binding_id": "binding", "tenant_id": "tenant", "user_id": "user",
        "conversation_id": "conversation", "kernel_session_id": "session",
        "runtime_id": "runtime", "profile_version": "profile", "event_cursor": 0,
    }
    task = asyncio.create_task(service._turn_runner.run(
        binding=binding,
        message_id="message",
        request_id="request",
        text="browse",
        temporal_context=build_temporal_context("UTC"),
        live_stream=live,
    ))
    delivered = []
    async for row in live.events():
        delivered.append(row)
    await task

    assert [row["stream_seq"] for row in delivered] == [1, 2, 3, 4, 5]
    assert delivered[2]["payload"]["label"] == "正在读取搜索结果"
    assert events.side_persisted[0]["stream_seq"] == 3
    assert [row["stream_seq"] for row in conversations.execution_events] == [1, 2, 3, 4, 5]


async def _test_durable_writer_flush_deadline_is_measured_from_first_event() -> None:
    events = _BatchEvents()
    bindings = _Bindings()
    writer = DurableKernelEventWriter(
        events=events,
        bindings=bindings,
        binding_id="binding",
        tenant_id="tenant",
        user_id="user",
        conversation_id="conversation",
        message_id="message",
        max_batch_size=64,
        max_batch_delay_seconds=0.05,
    )
    for cursor in range(1, 5):
        writer.enqueue(KernelEventWrite(event=_event(cursor, "kernel.native.event", {}), projected=None))
        await asyncio.sleep(0.02)
    assert events.calls
    assert len(events.calls[0]) in {3, 4}
    await writer.close()
