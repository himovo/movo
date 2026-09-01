from __future__ import annotations

import asyncio

from app.dsh_runtime.events.live_stream import LiveTurnStream
from app.dsh_runtime.events.projection_writer import ProjectionScope
from app.dsh_runtime.events.turn_channel import TurnEventRegistry
from app.enterprise_capabilities.browser.progress import BrowserTimelineProjector
from app.enterprise_capabilities.browser.result_contract import BrowserResultEventAccumulator


class _ProjectionEvents:
    def __init__(self) -> None:
        self.batches: list[list[dict]] = []
        self.scopes: list[dict] = []

    async def persist_projections(self, rows, **scope) -> None:
        self.batches.append([dict(row) for row in rows])
        self.scopes.append(dict(scope))


def _scope(message_id: str, session_id: str = "session-a") -> ProjectionScope:
    return ProjectionScope(
        tenant_id="tenant-a",
        user_id="user-a",
        conversation_id=f"conversation-{message_id}",
        message_id=message_id,
        kernel_session_id=session_id,
    )


def _kernel_tool_start(call_id: str) -> dict:
    return {
        "v": 3,
        "event_id": f"dsh-v3:{call_id}",
        "id": f"dsh-v3:{call_id}",
        "ts": 1,
        "type": "item.started",
        "item_kind": "tool",
        "item_id": call_id,
        "revision": 1,
        "stream_seq": 99,
        "stream_seq_end": 99,
        "payload": {"callId": call_id, "name": "browser_task"},
    }


async def _collect(stream: LiveTurnStream) -> list[dict]:
    rows = []
    async for row in stream.events():
        rows.append(row)
    return rows


def test_browser_projector_uses_native_descriptions_and_real_action_lifecycle() -> None:
    projector = BrowserTimelineProjector(outer_action_id="call-browser")

    activity = projector.project({
        "type": "activity",
        "content": {"kind": "analyze", "message": "正在读取百度搜索结果"},
    })
    assert activity[0]["payload"]["label"] == "正在读取百度搜索结果"
    assert activity[0]["payload"]["source"] == "browser_agent"

    started = projector.project({
        "type": "tool_requested",
        "content": {
            "tool": "browser_fill",
            "rationale": "在搜索框输入 AskBot",
            "rationale_source": "model",
            "args": {"text": "AskBot"},
        },
    })[0]
    completed = projector.project({
        "type": "tool_completed",
        "content": {"tool": "browser_fill", "ok": True, "result": {"large": "ignored"}},
    })[0]
    assert started["type"] == "item.started"
    assert completed["type"] == "item.completed"
    assert completed["item_id"] == started["item_id"]
    assert completed["revision"] == 2
    assert completed["payload"]["label"] == "在搜索框输入 AskBot"
    assert "result" not in completed["payload"]


def test_browser_projector_does_not_invent_missing_action_text() -> None:
    projector = BrowserTimelineProjector(outer_action_id="call-browser")
    assert projector.project({
        "type": "tool_requested",
        "content": {"tool": "browser_click", "args": {"ref": "e1"}},
    }) == []


def test_browser_intervention_projects_canonical_resumable_handoff() -> None:
    projector = BrowserTimelineProjector(outer_action_id="call-browser")
    row = projector.project({
        "type": "intervention_required",
        "content": {
            "category": "browser",
            "reason": "请手动调整页面",
            "suspension_id": "susp-1",
            "run_id": "run-1",
            "node_id": "node-1",
            "browser_session_id": "browser-1",
            "resumable": True,
        },
    })[0]
    assert row["type"] == "item.started"
    assert row["item_kind"] == "browser_handoff"
    assert row["item_id"] == "browser-handoff:susp-1"
    assert row["payload"]["resumable"] is True
    assert row["payload"]["source"] == "browser_agent"
    assert projector.project({
        "type": "tool_completed",
        "content": {"tool": "browser_click", "ok": True},
    }) == []


def test_browser_projector_hides_debug_and_untranslated_runtime_text() -> None:
    chinese = BrowserTimelineProjector(outer_action_id="call-browser", language="zh")
    assert chinese.project({
        "type": "activity",
        "content": {"message": "Step 1: browser_navigate", "visibility": "debug"},
    }) == []
    assert chinese.project({
        "type": "activity",
        "content": {"message": "Page hydration completed"},
    }) == []
    assert chinese.project({
        "type": "tool_requested",
        "content": {
            "tool": "browser_navigate",
            "rationale": "auto-navigate from single resolved entry",
            "rationale_source": "system",
        },
    }) == []

    english = BrowserTimelineProjector(outer_action_id="call-browser-en", language="en")
    rows = english.project({
        "type": "activity",
        "content": {"message": "Page hydration completed"},
    })
    assert rows[0]["payload"]["label"] == "Page hydration completed"


def test_browser_result_accumulator_is_bounded_but_keeps_full_counts() -> None:
    accumulator = BrowserResultEventAccumulator(max_events=3)
    for index in range(1000):
        accumulator.record({"type": "activity", "content": {"message": str(index)}})
    for index in range(5):
        accumulator.record({"type": "runtime_status", "content": {"value": index}})
    accumulator.record({"type": "subagent_done", "content": {"status": "succeeded"}})
    assert len(accumulator.events) == 3
    assert accumulator.event_counts == {
        "activity": 1000,
        "runtime_status": 5,
        "subagent_done": 1,
    }
    assert accumulator.latest("subagent_done")["content"]["status"] == "succeeded"


def test_side_events_wait_for_parent_tool_then_stream_and_persist_in_order() -> None:
    asyncio.run(_test_side_events_wait_for_parent_tool_then_stream_and_persist_in_order())


async def _test_side_events_wait_for_parent_tool_then_stream_and_persist_in_order() -> None:
    events = _ProjectionEvents()
    registry = TurnEventRegistry(events)
    live = LiveTurnStream()
    registry.register(_scope("message-a"), live)
    sink = registry.progress_sink("message-a", "call-browser")
    assert sink is not None
    projector = BrowserTimelineProjector(outer_action_id="call-browser")
    progress = projector.project({
        "type": "activity",
        "content": {"kind": "analyze", "message": "开始观察页面"},
    })[0]

    # Tool Gateway may start executing before the DSH subscription observes
    # tool/call. Progress is held until its real parent item exists.
    await sink(progress)
    assert live._queue.empty()

    parent = await registry.publish_kernel("message-a", _kernel_tool_start("call-browser"))
    assert events.batches == []
    await registry.mark_action_durable("message-a", "call-browser")
    await registry.publish_kernel("message-a", {
        "v": 3, "event_id": "dsh-v3:after", "id": "dsh-v3:after", "ts": 2,
        "type": "item.completed", "item_kind": "commentary", "item_id": "commentary",
        "revision": 1, "payload": {"text": "继续"},
    })
    side_history = await registry.finish("message-a")
    live.finish()
    delivered = await _collect(live)

    assert [row["stream_seq"] for row in delivered] == [1, 2, 3]
    assert delivered[0]["event_id"] == parent["event_id"]
    assert delivered[1]["payload"]["label"] == "开始观察页面"
    assert side_history == [delivered[1]]
    assert events.batches == [[delivered[1]]]
    assert events.scopes[0]["message_id"] == "message-a"


def test_turn_channels_keep_conversations_isolated() -> None:
    asyncio.run(_test_turn_channels_keep_conversations_isolated())


async def _test_turn_channels_keep_conversations_isolated() -> None:
    events = _ProjectionEvents()
    registry = TurnEventRegistry(events)
    live_a, live_b = LiveTurnStream(), LiveTurnStream()
    registry.register(_scope("message-a", "session-a"), live_a)
    registry.register(_scope("message-b", "session-b"), live_b)
    await registry.publish_kernel("message-a", _kernel_tool_start("call-a"))
    await registry.publish_kernel("message-b", _kernel_tool_start("call-b"))
    await registry.mark_action_durable("message-a", "call-a")
    await registry.mark_action_durable("message-b", "call-b")
    sink_a = registry.progress_sink("message-a", "call-a")
    assert sink_a is not None
    await sink_a(BrowserTimelineProjector(outer_action_id="call-a").project({
        "type": "activity", "content": {"message": "只属于会话 A"},
    })[0])
    history_a = await registry.finish("message-a")
    history_b = await registry.finish("message-b")
    assert [row["payload"]["label"] for row in history_a] == ["只属于会话 A"]
    assert history_b == []
