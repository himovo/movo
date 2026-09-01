from __future__ import annotations

from datetime import datetime, timezone

from app.dsh_runtime.contracts import KernelEventEnvelope, KernelEventSource
from app.dsh_runtime.events import KernelEventProjector
from app.dsh_runtime.event_mapper import DshEventMapper
from app.dsh_runtime.profile.models import RuntimeProfileSnapshot
from app.dsh_runtime.profile.store import InMemoryRuntimeProfileStore


def _event(event_type: str, payload: dict, cursor: int = 1) -> KernelEventEnvelope:
    return KernelEventEnvelope(
        event_id=f"runtime:session:{cursor}",
        runtime_id="runtime",
        session_id="session",
        profile_version="profile",
        cursor=cursor,
        type=event_type,
        occurred_at=datetime.now(timezone.utc),
        payload=payload,
        source=KernelEventSource(kernel_version="0.1.0-rc.6", native_event_type="test"),
    )


def _profile(version: str, model: str) -> RuntimeProfileSnapshot:
    return RuntimeProfileSnapshot(
        profile_version=version,
        content_hash="a" * 64 if version == "profile-a" else "b" * 64,
        tenant_id="tenant-a",
        model_source_tenant_id="tenant-a",
        model_instance_id=model,
        provider_id="provider",
        provider_type="openai_compatible",
        provider_name="provider",
        model_name=model,
        display_name=model,
        capabilities=("chat",),
    )


def test_projects_only_stable_v3_answer_and_terminal_fields() -> None:
    projector = KernelEventProjector()
    delta = projector.project(
        _event("agent.message.delta", {"chunk": {"type": "text-delta", "text": "hello"}}),
        message_id="message-a",
    )
    assert delta is not None
    assert delta["type"] == "item.delta"
    assert delta["item_kind"] == "final_answer"
    assert delta["payload"] == {"text": "hello", "provisional": True}
    assert "chunk" not in delta["payload"]

    terminal = projector.project(
        _event("turn.completed", {"reason": {"kind": "aborted"}}, cursor=2),
        message_id="message-a",
    )
    assert terminal is not None
    assert terminal["type"] == "run.cancelled"
    assert terminal["stream_seq"] == 2


def test_tool_step_text_becomes_commentary_and_tool_completion_keeps_metadata() -> None:
    projector = KernelEventProjector()
    presentation = {
        "askai_mcp_search": {
            "display_name": "AI CRM/crm_search_customers",
            "description": "按名称查询客户",
        }
    }
    delta = projector.project(
        _event(
            "agent.message.delta",
            {"turn": 1, "step": 2, "chunk": {"type": "text-delta", "text": "正在缩短名称重试"}},
            cursor=10,
        ),
        message_id="message-a",
    )
    commentary = projector.project(
        _event(
            "agent.message.completed",
            {"turn": 1, "step": 2, "message": {"content": [
                {"type": "text", "text": "正在缩短名称重试"},
                {"type": "tool-call", "id": "call-a", "name": "askai_mcp_search", "arguments": "{\"query\":\"星河\"}"},
            ]}},
            cursor=11,
        ),
        message_id="message-a",
    )
    started = projector.project(
        _event(
            "tool.call.started",
            {"callId": "call-a", "name": "askai_mcp_search", "arguments": "{\"query\":\"星河\"}"},
            cursor=12,
        ),
        message_id="message-a",
        tool_presentations=presentation,
    )
    completed = projector.project(
        _event(
            "tool.call.completed",
            {"message": {"source": {"callId": "call-a"}, "content": [{
                "type": "tool-result", "toolCallId": "call-a", "isError": False,
                "content": [{"type": "text", "text": "{\"code\":0}"}],
            }]}},
            cursor=13,
        ),
        message_id="message-a",
        tool_presentations=presentation,
    )

    assert delta and commentary and started and completed
    assert delta["item_id"] == commentary["item_id"]
    assert commentary["item_kind"] == "commentary"
    assert commentary["payload"]["retract_provisional"] is True
    assert started["payload"]["display_name"] == "AI CRM/crm_search_customers"
    assert started["payload"]["risk_level"] == ""
    assert started["payload"]["args"] == {"query": "星河"}
    assert completed["type"] == "item.completed"
    assert completed["revision"] > started["revision"]
    assert completed["payload"]["status"] == "succeeded"


def test_failed_tool_result_projects_as_failed_item() -> None:
    projector = KernelEventProjector()
    projector.project(
        _event("tool.call.started", {"callId": "call-a", "name": "search", "arguments": "{}"}, cursor=20),
        message_id="message-a",
    )
    failed = projector.project(
        _event("tool.call.completed", {"message": {
            "source": {"callId": "call-a"},
            "error": {"code": "INVALID_TOOL_OUTPUT"},
            "content": [{"type": "tool-result", "toolCallId": "call-a", "isError": True,
                         "content": [{"type": "text", "text": "schema mismatch"}]}],
        }}, cursor=21),
        message_id="message-a",
    )
    assert failed is not None
    assert failed["type"] == "item.failed"
    assert failed["payload"]["error"] == "schema mismatch"


def test_native_code_dispatch_projects_inner_dsh_tools_without_askai_code_tools() -> None:
    mapper = DshEventMapper(kernel_version="0.1.0-rc.6")
    projector = KernelEventProjector()
    started_native = mapper.map_event(
        {
            "cursor": 50, "nativeType": "tool/code-dispatch-start", "time": 1_700_000_000_000,
            "data": {
                "rootCallId": "root", "parentCallId": "run", "subCallId": "run:code:1",
                "name": "bash", "arguments": {"command": "npm test"},
            },
        },
        runtime_id="runtime", session_id="session", profile_version="profile",
    )
    completed_native = mapper.map_event(
        {
            "cursor": 51, "nativeType": "tool/code-dispatch", "time": 1_700_000_000_100,
            "data": {
                "rootCallId": "root", "parentCallId": "run", "subCallId": "run:code:1",
                "name": "bash", "arguments": {"command": "npm test"}, "isError": False,
                "content": [{"type": "text", "text": '{"exitCode":0,"stdout":{"text":"ok"}}'}],
            },
        },
        runtime_id="runtime", session_id="session", profile_version="profile",
    )
    started = projector.project(started_native, message_id="message-a")
    completed = projector.project(completed_native, message_id="message-a")
    assert started and completed
    assert started["item_id"] == "run:code:1"
    assert started["payload"]["name"] == "bash"
    assert started["payload"]["args"] == {"command": "npm test"}
    assert completed["item_id"] == "run:code:1"
    assert completed["payload"]["status"] == "succeeded"
    assert completed["payload"]["result_summary"].startswith('{"exitCode":0')


def test_internal_capability_results_project_knowledge_evidence_and_artifacts() -> None:
    import json

    projector = KernelEventProjector()
    projector.project(
        _event("tool.call.started", {"callId": "kb-1", "name": "knowledge_search", "arguments": "{}"}, cursor=30),
        message_id="message-a",
    )
    knowledge = projector.project(
        _event("tool.call.completed", {"message": {
            "source": {"callId": "kb-1"},
            "content": [{"type": "tool-result", "toolCallId": "kb-1", "content": [{"type": "text", "text": json.dumps({
                "success": True,
                "items": [{
                    "documentId": "doc-1", "chunkId": "chunk-2", "titlePath": ["制度", "休假"],
                    "text": "年假规则", "citation_ref": "kb://doc-1/chunk-2",
                }],
            }, ensure_ascii=False)}]}],
        }}, cursor=31),
        message_id="message-a",
    )
    assert knowledge is not None
    source = knowledge["payload"]["evidence_bundle"]["sources"][0]
    assert source["citation_id"] == "kb://doc-1/chunk-2"
    assert source["document_id"] == "doc-1"

    projector.project(
        _event("tool.call.started", {"callId": "artifact-1", "name": "artifact_export", "arguments": "{}"}, cursor=32),
        message_id="message-a",
    )
    artifact = projector.project(
        _event("tool.call.completed", {"message": {
            "source": {"callId": "artifact-1"},
            "content": [{"type": "tool-result", "toolCallId": "artifact-1", "content": [{"type": "text", "text": json.dumps({
                "success": True, "artifact": {"object_path": "tenant/report.docx", "filename": "report.docx"},
            })}]}],
        }}, cursor=33),
        message_id="message-a",
    )
    assert artifact is not None
    assert artifact["payload"]["artifacts"][0]["object_path"] == "tenant/report.docx"


def test_explicit_profile_publish_does_not_replace_tenant_default() -> None:
    async def scenario() -> None:
        store = InMemoryRuntimeProfileStore()
        default = _profile("profile-a", "model-a")
        explicit = _profile("profile-b", "model-b")
        await store.publish(default, actor_id="admin")
        await store.publish(explicit, actor_id="user", activate=False)
        assert (await store.active("tenant-a")).profile_version == "profile-a"
        assert (await store.get("profile-b")).model_instance_id == "model-b"

    import asyncio

    asyncio.run(scenario())


def test_browser_result_projects_resumable_human_intervention() -> None:
    import json

    projector = KernelEventProjector()
    projector.project(
        _event("tool.call.started", {"callId": "browser-1", "name": "browser_task", "arguments": "{}"}, cursor=40),
        message_id="message-a",
    )
    projected = projector.project(
        _event("tool.call.completed", {"message": {
            "source": {"callId": "browser-1"},
            "content": [{"type": "tool-result", "toolCallId": "browser-1", "content": [{"type": "text", "text": json.dumps({
                "success": True,
                "status": "suspended_waiting_approval",
                "intervention_suspension": {"suspension_id": "susp-1", "run_id": "run-1", "node_id": "node-1"},
                "domain_events": [{"type": "intervention_required", "content": {
                    "reason": "请完成登录", "category": "login", "url": "https://example.test",
                }}],
            }, ensure_ascii=False)}]}],
        }}, cursor=41),
        message_id="message-a",
    )
    assert projected is not None
    assert projected["payload"]["browser_intervention"] == {
        "suspension_id": "susp-1", "run_id": "run-1", "node_id": "node-1",
        "reason": "请完成登录", "category": "login", "url": "https://example.test", "status": "pending",
    }
