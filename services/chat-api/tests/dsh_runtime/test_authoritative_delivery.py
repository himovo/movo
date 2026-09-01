from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from app.dsh_runtime.contracts import KernelEventEnvelope, KernelEventSource
from app.dsh_runtime.events import KernelEventProjector
from app.dsh_runtime.events.authoritative_delivery import AuthoritativeDeliveryGuard
from app.dsh_runtime.profile.tools import ToolProfileDefinition


def _event(cursor: int, event_type: str, payload: dict) -> KernelEventEnvelope:
    return KernelEventEnvelope(
        event_id=f"runtime:session:{cursor}", runtime_id="runtime", session_id="session",
        profile_version="profile", cursor=cursor, type=event_type,
        occurred_at=datetime.now(timezone.utc), payload=payload,
        source=KernelEventSource(kernel_version="test", native_event_type=event_type),
    )


class _Store:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    async def get(self, action_id: str, **scope):
        self.calls.append({"action_id": action_id, **scope})
        return {"content": self.content}


def _started(cursor: int, call_id: str, name: str) -> KernelEventEnvelope:
    return _event(cursor, "tool.call.started", {
        "callId": call_id, "name": name, "arguments": "{}",
    })


def _completed(cursor: int, call_id: str) -> KernelEventEnvelope:
    return _event(cursor, "tool.call.completed", {"message": {
        "source": {"callId": call_id},
        "content": [{
            "type": "tool-result", "toolCallId": call_id, "isError": False,
            "content": [{"type": "text", "text": json.dumps({"success": True})}],
        }],
    }})


def test_authoritative_content_replaces_only_the_post_tool_final_answer() -> None:
    async def run() -> None:
        projector = KernelEventProjector()
        store = _Store("# 权威成稿\n\n![配图](/askai-api/api/files/a.png)")
        tools = {"content_production": {"delivery_mode": "authoritative_markdown"}}
        guard = AuthoritativeDeliveryGuard(
            store=store, tool_presentations=tools,
            tenant_id="tenant", user_id="user", message_id="message",
        )
        started = _started(1, "content-1", "content_production")
        await guard.apply(started, projector.project(started, message_id="message", tool_presentations=tools))
        completed = _completed(2, "content-1")
        projected_tool = projector.project(completed, message_id="message", tool_presentations=tools)
        assert await guard.apply(completed, projected_tool) == projected_tool

        delta = _event(3, "agent.message.delta", {
            "turn": 1, "step": 2, "chunk": {"type": "text-delta", "text": "模型改写"},
        })
        assert await guard.apply(delta, projector.project(delta, message_id="message")) is None
        final = _event(4, "agent.message.completed", {
            "turn": 1, "step": 2,
            "message": {"content": [{"type": "text", "text": "📷 配图已生成，见文件"}]},
        })
        projected = await guard.apply(final, projector.project(final, message_id="message"))
        assert projected is not None
        assert projected["payload"]["text"] == store.content
        assert projected["payload"]["source"] == "askai_authoritative_tool"
        assert store.calls == [{
            "action_id": "content-1", "tenant_id": "tenant",
            "user_id": "user", "message_id": "message",
        }]

    asyncio.run(run())


def test_default_tools_keep_dsh_model_synthesis_unchanged() -> None:
    async def run() -> None:
        projector = KernelEventProjector()
        store = _Store("must not be used")
        tools = {"knowledge_search": {"delivery_mode": "model_synthesized"}}
        guard = AuthoritativeDeliveryGuard(
            store=store, tool_presentations=tools,
            tenant_id="tenant", user_id="user", message_id="message",
        )
        started = _started(1, "search-1", "knowledge_search")
        await guard.apply(started, projector.project(started, message_id="message", tool_presentations=tools))
        completed = _completed(2, "search-1")
        await guard.apply(
            completed,
            projector.project(completed, message_id="message", tool_presentations=tools),
        )
        final = _event(3, "agent.message.completed", {
            "message": {"content": [{"type": "text", "text": "DSH 综合后的知识回答"}]},
        })
        projected = await guard.apply(final, projector.project(final, message_id="message"))
        assert projected is not None
        assert projected["payload"]["text"] == "DSH 综合后的知识回答"
        assert store.calls == []

    asyncio.run(run())


def test_persisted_content_profile_is_migrated_without_affecting_other_tools() -> None:
    common = {
        "version": "v1", "source_type": "internal", "external_tool_id": "capability",
        "description": "tool", "input_schema": {}, "output_schema": {}, "risk_level": "read",
    }
    content = ToolProfileDefinition(
        **common, name="content_production", capability_ref="content.produce@v1",
    )
    knowledge = ToolProfileDefinition(
        **common, name="knowledge_search", capability_ref="knowledge.search@v1",
    )
    assert content.delivery_mode == "authoritative_markdown"
    assert knowledge.delivery_mode == "model_synthesized"
