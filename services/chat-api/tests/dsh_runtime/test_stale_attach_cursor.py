"""Stale attach-cursor live-delivery regression (shared-conversation defect).

Mechanism (verified live): after a session RESUME onto a (possibly new)
runtime, the Node journal is rebuilt by ``resetFromSession`` which renumbers
cursors from 1 — so the durable ``binding.event_cursor`` (a position in the
OLD journal space) falls INSIDE the reimported history. The turn runner then
subscribes ``after=<stale>``, the runtime replays the tail of OLD history
into the live HTTP response, and the ingest loop's bare
``event.type in {"turn.completed", "runtime.failed"}`` break fires on a STALE
``turn.completed`` — the HTTP response closes early while the real turn keeps
running invisibly server-side. The replayed historical events are also
projected onto the NEW message_id (wrong-content persistence).

The fix re-baselines the attach position to the session's CURRENT head
(``gateway.head_cursor``, probed before ``send``) instead of trusting the
stale durable cursor, skips any pre-attach event without projecting,
persisting, or delivering it (so a stale terminal can never close the live
stream), and advances the durable cursor past everything consumed.

Harness style mirrors ``test_step4_live_persistence.py`` (fake gateway with a
controllable journal + the REAL ``DshTurnRunner`` through ``DshChatService``,
no mongo, no sleeps beyond the stream drain).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.dsh_runtime.chat_service import DshChatService
from app.dsh_runtime.contracts import KernelEventEnvelope, KernelEventSource
from app.dsh_runtime.events import KernelEventProjector, KernelEventWrite
from app.dsh_runtime.events.live_stream import LiveTurnStream
from app.dsh_runtime.profile.models import RuntimeProfileSnapshot
from app.dsh_runtime.temporal_context import build_temporal_context


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


def _history() -> list[KernelEventEnvelope]:
    """Reimported OLD history after a resume (journal renumbered from 1)."""
    return [
        _event(1, "turn.started", {}),
        _event(2, "agent.message.delta", {"chunk": {"type": "text-delta", "text": "OLD-"}}),
        _event(3, "agent.message.delta", {"chunk": {"type": "text-delta", "text": "OLD"}}),
        _event(
            4,
            "agent.message.completed",
            {"message": {"content": [{"type": "text", "text": "OLD TEXT"}]}},
        ),
        _event(5, "turn.completed", {"reason": {"kind": "stop"}}),
    ]


def _live_turn() -> list[KernelEventEnvelope]:
    """The real NEW turn's events, appended by send() after the head probe."""
    return [
        _event(6, "turn.started", {}),
        _event(7, "agent.message.delta", {"chunk": {"type": "text-delta", "text": "NEW-"}}),
        _event(8, "agent.message.delta", {"chunk": {"type": "text-delta", "text": "NEW"}}),
        _event(
            9,
            "agent.message.completed",
            {"message": {"content": [{"type": "text", "text": "NEW TEXT"}]}},
        ),
        _event(10, "turn.completed", {"reason": {"kind": "stop"}}),
    ]


# Durable cursor from the OLD journal space, falling INSIDE the reimported
# history (positions shifted by the resume rebuild).
STALE_DURABLE_CURSOR = 3


class _JournalGateway:
    """Fake DSH gateway with a controllable journal.

    The journal starts with the reimported history; ``send()`` appends the
    live turn's events (cursors continue past the head, exactly like the Node
    host). ``head_cursor()`` reports the CURRENT head — the probe the fixed
    runner uses to re-baseline the attach position. A gateway built with
    ``with_head_probe=False`` has no ``head_cursor`` method at all, which
    reproduces the UNFIXED runner path (durable stale cursor trusted).
    """

    def __init__(self, *, with_head_probe: bool = True) -> None:
        self._journal = _history()
        self.subscribe_after: list[int] = []
        if with_head_probe:
            self.head_cursor = self._head_cursor_impl  # type: ignore[method-assign]

    async def _head_cursor_impl(self, _session_id: str) -> int:
        return max((event.cursor for event in self._journal), default=0)

    async def send(self, _request) -> str:
        self._journal.extend(_live_turn())
        return "native-message"

    async def subscribe(self, _session_id: str, after_cursor: int):
        self.subscribe_after.append(after_cursor)
        for event in [item for item in self._journal if item.cursor > after_cursor]:
            yield event


class _BatchEvents:
    def __init__(self) -> None:
        self.projector = KernelEventProjector()
        self.persisted: list[dict] = []

    def project(self, event, *, message_id, tool_presentations=None):
        return self.projector.project(
            event, message_id=message_id, tool_presentations=tool_presentations
        )

    async def persist_batch(self, writes: list[KernelEventWrite], **_scope) -> None:
        self.persisted.extend(write.projected for write in writes if write.projected is not None)

    async def all_for_message(self, *_args, **_kwargs):
        return list(self.persisted)


class _Bindings:
    def __init__(self) -> None:
        self.cursors: list[int] = []
        self.finished_status: str | None = None

    async def advance_cursor(self, _binding_id: str, cursor: int) -> None:
        self.cursors.append(cursor)

    async def finish_turn(self, *_args, **kwargs) -> None:
        self.finished_status = kwargs.get("status")


class _Conversations:
    def __init__(self) -> None:
        self.content = ""
        self.execution_events: list[dict] = []
        self.active_run_cleared = False

    async def update_assistant_projection(self, **kwargs) -> None:
        self.content = kwargs["content"]
        self.execution_events = kwargs["execution_events"]

    async def clear_active_run(self, **_kwargs) -> None:
        self.active_run_cleared = True


class _Profiles:
    async def get(self, _profile_version: str):
        return RuntimeProfileSnapshot(
            profile_version="profile", content_hash="a" * 64, tenant_id="tenant",
            model_source_tenant_id="tenant", model_instance_id="model", provider_id="provider",
            provider_type="openai_compatible", provider_name="provider", model_name="model",
            display_name="model", capabilities=("chat",),
        )


def _binding() -> dict:
    return {
        "binding_id": "binding",
        "tenant_id": "tenant",
        "user_id": "user",
        "conversation_id": "conversation",
        "kernel_session_id": "session",
        "runtime_id": "runtime",
        "profile_version": "profile",
        "event_cursor": STALE_DURABLE_CURSOR,
    }


async def _run_turn(*, with_head_probe: bool) -> dict:
    gateway = _JournalGateway(with_head_probe=with_head_probe)
    events = _BatchEvents()
    bindings = _Bindings()
    conversations = _Conversations()
    service = DshChatService(
        gateway=gateway,  # type: ignore[arg-type]
        coordinator=SimpleNamespace(),
        conversations=conversations,  # type: ignore[arg-type]
        bindings=bindings,  # type: ignore[arg-type]
        events=events,  # type: ignore[arg-type]
        profiles=_Profiles(),  # type: ignore[arg-type]
        kernel_version="0.1.0-rc.6",
    )
    live = LiveTurnStream()
    task = asyncio.create_task(
        service._turn_runner.run(
            binding=_binding(),
            message_id="message-new",
            request_id="request-new",
            text="fresh send",
            temporal_context=build_temporal_context("UTC"),
            live_stream=live,
        )
    )
    frames: list[dict] = []
    async for projected in live.events():
        frames.append(projected)
    status = await task
    return {
        "status": status,
        "frames": frames,
        "persisted": events.persisted,
        "content": conversations.content,
        "execution_events": conversations.execution_events,
        "subscribe_after": list(gateway.subscribe_after),
        "cursors": list(bindings.cursors),
        "finished_status": bindings.finished_status,
    }


def _frame_texts(frames: list[dict]) -> str:
    texts: list[str] = []
    for frame in frames:
        payload = frame.get("payload") or {}
        if isinstance(payload.get("text"), str):
            texts.append(payload["text"])
    return "".join(texts)


def test_stale_attach_cursor_delivers_only_the_current_turn() -> None:
    """Resume-with-history + stale durable cursor: only the current turn's
    events flow live, the stream stays open until the REAL terminal, and no
    historical content lands on the new message."""
    result = asyncio.run(_run_turn(with_head_probe=True))

    # The attach position is re-baselined to the session head (5), not the
    # stale durable cursor (3).
    assert result["subscribe_after"] == [5]

    # The stream stays open until the REAL terminal: live frames carry the
    # current turn's deltas and close with the real run.completed.
    assert result["status"] == "completed"
    frame_types = [frame["type"] for frame in result["frames"]]
    assert "item.delta" in frame_types
    assert frame_types[-1] == "run.completed"
    live_text = _frame_texts(result["frames"])
    assert "NEW" in live_text
    assert "OLD" not in live_text

    # No historical content is persisted onto the new message: every durable
    # row belongs to the current turn (stream_seq past the head).
    assert result["persisted"], "the current turn must persist rows"
    assert all(int(row["stream_seq"]) > 5 for row in result["persisted"])
    persisted_text = "".join(
        str((row.get("payload") or {}).get("text") or "") for row in result["persisted"]
    )
    assert "OLD" not in persisted_text
    assert "NEW TEXT" in persisted_text

    # The assistant projection converges on the real model output.
    assert result["content"] == "NEW TEXT"

    # The durable cursor advances past everything consumed, including the
    # skipped stale events — the lag cannot accumulate across turns.
    assert result["cursors"], "the binding cursor must advance"
    assert max(result["cursors"]) == 10


def test_without_head_probe_the_stale_terminal_closes_the_stream_early() -> None:
    """Pins the defect mechanism: a runner that trusts the stale durable
    cursor (no head probe — the pre-fix path) replays history, breaks on the
    STALE turn.completed, never sees the real turn, and persists the stale
    content onto the new message."""
    result = asyncio.run(_run_turn(with_head_probe=False))

    assert result["subscribe_after"] == [STALE_DURABLE_CURSOR]
    # Early close: the real turn's deltas never reach the live stream ...
    live_text = _frame_texts(result["frames"])
    assert "NEW" not in live_text
    # ... and the stale historical content is projected onto the new message.
    assert result["content"] == "OLD TEXT"
    assert "OLD" in live_text


def test_attach_without_resume_keeps_streaming() -> None:
    """Same-speaker consecutive turns with no rotation: the durable cursor is
    already at the head, so the probe changes nothing and the turn streams
    exactly as before (no-regression guard for the preserve requirement)."""
    gateway = _JournalGateway(with_head_probe=True)
    # No resume happened: the previous turn's terminal was consumed, so the
    # durable cursor already equals the journal head.
    gateway._journal = _history()
    binding = {**_binding(), "event_cursor": 5}

    events = _BatchEvents()
    bindings = _Bindings()
    conversations = _Conversations()
    service = DshChatService(
        gateway=gateway,  # type: ignore[arg-type]
        coordinator=SimpleNamespace(),
        conversations=conversations,  # type: ignore[arg-type]
        bindings=bindings,  # type: ignore[arg-type]
        events=events,  # type: ignore[arg-type]
        profiles=_Profiles(),  # type: ignore[arg-type]
        kernel_version="0.1.0-rc.6",
    )
    live = LiveTurnStream()

    async def scenario() -> str:
        task = asyncio.create_task(
            service._turn_runner.run(
                binding=binding,
                message_id="message-next",
                request_id="request-next",
                text="consecutive turn",
                temporal_context=build_temporal_context("UTC"),
                live_stream=live,
            )
        )
        frames: list[dict] = []
        async for projected in live.events():
            frames.append(projected)
        status = await task
        assert "NEW" in _frame_texts(frames)
        return status

    assert asyncio.run(scenario()) == "completed"
    assert gateway.subscribe_after == [5]
    assert conversations.content == "NEW TEXT"
