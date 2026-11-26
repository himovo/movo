import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.dsh_runtime.contracts import KernelEventEnvelope, KernelEventSource
from app.dsh_runtime.events import KernelEventProjector
from app.dsh_runtime.projected_documents import projected_documents
from app.dsh_runtime.projected_documents import update_projection
from app.enterprise_capabilities.images.service import ImageGenerationCapability
from app.enterprise_capabilities.runtime import CapabilityExecutionContext


def test_generated_images_survive_missing_model_links_and_duplicate_event_paths():
    async def check():
        progress = []

        async def publish(row):
            progress.append(row)

        async def generate(**kwargs):
            return {"image_url": "https://assets.test/image.webp", "object_path": "owner/image.webp"}

        context = CapabilityExecutionContext(
            tenant_id="tenant", user_id="owner", conversation_id="conversation",
            kernel_session_id="session", profile_version="profile", action_id="call",
            message_id="message", progress_sink=publish,
        )
        result = await ImageGenerationCapability(generate).run({"images": [{"prompt": "A cat"}]}, context)
        event = KernelEventEnvelope(
            event_id="event", runtime_id="runtime", session_id="session", profile_version="profile",
            cursor=1, type="tool.call.completed", occurred_at=datetime.now(timezone.utc),
            source=KernelEventSource(kernel_version="test", native_event_type="test"),
            payload={"message": {"source": {"callId": "call"}, "content": [{"type": "text", "text": json.dumps(result)}]}},
        )
        row = KernelEventProjector().project(event, message_id="message")
        assert row["payload"]["artifacts"] == result["documents"]
        # The model's final answer contains no link. Durable side events and
        # completed tool results still converge on one attachment per image.
        events = [*progress, row, {"type": "item.completed", "item_kind": "final_answer", "payload": {"text": "Done"}}]
        docs = projected_documents(events, [{"object_path": "owner/report.html", "type": "html"}])
        assert [doc["object_path"] for doc in docs] == ["owner/image.webp", "owner/report.html"]
        assert docs[0]["content_type"] == "image/webp"
        # Persisted events alone retain the image even if a later request is
        # cancelled before the tool can return a complete result.
        assert projected_documents(progress, []) == [{**result["documents"][0], "kind": "webp"}]

    asyncio.run(check())


def test_internal_and_unfinished_artifacts_are_not_persisted_as_deliveries():
    events = [
        {"type": "item.started", "item_kind": "artifact", "payload": {"object_path": "pending"}},
        {"type": "item.completed", "item_kind": "artifact", "payload": {"object_path": "private", "visibility": "internal"}},
        {"type": "item.completed", "item_kind": "tool", "payload": {"artifacts": [{"object_path": "temp", "lifecycle": "intermediate"}]}},
    ]
    assert projected_documents(events, []) == []


def test_finalizer_saves_image_and_workspace_attachments_together(monkeypatch):
    from app.dsh_runtime import turn_finalization as module

    image = {"object_path": "owner/cat.png", "type": "png", "url": "https://assets.test/cat.png"}
    workspace = {"object_path": "owner/report.html", "type": "html"}
    monkeypatch.setattr(module, "deliver_personal_outputs", AsyncMock(return_value=[workspace]))
    monkeypatch.setattr(module, "index_plugin_calls", AsyncMock())
    monkeypatch.setattr(module, "finalize_task_audit", AsyncMock(return_value=False))
    conversations = SimpleNamespace(update_assistant_projection=AsyncMock(), clear_active_run=AsyncMock())
    finalizer = module.TurnStateFinalizer(SimpleNamespace(finish_turn=AsyncMock(return_value=True)), conversations)
    asyncio.run(finalizer.finalize(
        binding={"tenant_id": "tenant", "user_id": "owner", "conversation_id": "conversation", "binding_id": "binding"},
        message_id="message", status="completed",
        assistant=module.TurnAssistantProjection(content="Done", execution_events=[
            {"type": "item.completed", "item_kind": "artifact", "payload": image},
        ]),
    ))
    saved = conversations.update_assistant_projection.call_args.kwargs
    assert saved["content"] == "Done"
    assert saved["documents"] == [image, workspace]


def test_terminal_replay_does_not_erase_an_edit_saved_during_projection():
    from copy import deepcopy

    original = {"object_path": "owner/original.png", "type": "png"}
    edited = {"object_path": "owner/edited.png", "source_object_path": "owner/original.png", "type": "png"}

    class Messages:
        row = {"documents": [original]}
        raced = False

        async def find_one(self, query, projection):
            return deepcopy(self.row)

        async def update_one(self, query, update):
            if not self.raced:
                self.row["documents"].append(edited)
                self.raced = True
            if query["documents"] != self.row["documents"]:
                return SimpleNamespace(matched_count=0)
            self.row.update(update["$set"])
            return SimpleNamespace(matched_count=1)

    messages = Messages()
    asyncio.run(update_projection(messages, {"message_id": "message"}, {"documents": [original], "content": "Done"}))
    assert messages.row["documents"] == [original, edited]
    asyncio.run(update_projection(messages, {"message_id": "message"}, {"documents": [original]}))
    assert messages.row["documents"] == [original, edited]
