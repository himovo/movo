from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from app.dsh_runtime.desktop_binding import DesktopCodeBindingService, DesktopSessionIdentity


@dataclass
class Profile:
    tenant_id: str = "tenant-a"
    subject_user_id: str = "user-a"
    model_instance_id: str = "model-a"


class Profiles:
    async def get(self, version):
        assert version == "rp-a"
        return Profile()


class Conversations:
    def __init__(self): self.deleted, self.messages, self.active, self.projection, self.pending_count = [], {}, None, None, 0
    async def create(self, **kwargs): return {"_id": "conversation-a", **kwargs}
    async def delete_if_empty(self, conversation_id, **kwargs): self.deleted.append((conversation_id, kwargs))
    async def append_message(self, **kwargs):
        self.messages[kwargs["message_id"]] = {**kwargs, "execution_events": []}
        return self.messages[kwargs["message_id"]]
    async def mark_active_run(self, **kwargs): self.active = kwargs
    async def message(self, message_id, **kwargs): return self.messages.get(message_id)
    async def update_assistant_projection(self, **kwargs):
        self.projection = kwargs
        self.messages[kwargs["message_id"]].update(content=kwargs["content"], execution_events=kwargs["execution_events"])
    async def clear_active_run(self, **kwargs): self.active = None
    async def set_pending_approval_count(self, **kwargs): self.pending_count = kwargs["count"]


class Bindings:
    def __init__(self, existing=None, fail=False): self.existing, self.fail, self.created, self.finished, self.cursor = existing, fail, None, None, 0
    async def by_kernel_session(self, *args, **kwargs): return self.existing
    async def current(self, *args, **kwargs): return self.existing
    async def create(self, **kwargs):
        self.created = kwargs
        if self.fail: raise RuntimeError("insert failed")
        return {"binding_id": "binding-a", **kwargs}
    async def claim_turn(self, binding_id, **kwargs):
        self.existing["active_turn"] = {"message_id": kwargs["message_id"]}
        return self.existing
    async def finish_turn(self, binding_id, **kwargs): self.finished = kwargs
    async def advance_cursor(self, binding_id, cursor): self.cursor = cursor
    async def update_runtime(self, binding_id, **kwargs): self.existing["runtime_id"] = kwargs["runtime_id"]


def identity() -> DesktopSessionIdentity:
    return DesktopSessionIdentity(
        runtime_id="runtime-local", kernel_session_id="session-a", dsh_workspace_id="workspace-a",
        profile_version="rp-a", model_instance_id="model-a", device_id="device-a",
        source_workspace_id="workspace-a",
    )


def test_desktop_binding_commits_all_immutable_fields_without_a_path() -> None:
    async def run():
        bindings = Bindings()
        row = await DesktopCodeBindingService(
            Conversations(), bindings, Profiles(), kernel_version="0.1.0-rc.6"
        ).commit(tenant_id="tenant-a", user_id="user-a", identity=identity(), title="Fix bug")
        assert row["execution_location"] == "desktop"
        assert row["preset_id"] == "code"
        assert row["dsh_workspace_id"] == "workspace-a"
        assert not any("path" in key or "cwd" in key for key in bindings.created)
    asyncio.run(run())


def test_desktop_binding_is_idempotent_and_rejects_identity_switch() -> None:
    existing = {
        "binding_id": "binding-a", "conversation_id": "conversation-a", "runtime_id": "runtime-local",
        "kernel_session_id": "session-a", "dsh_workspace_id": "workspace-a", "profile_version": "rp-a",
        "model_instance_id": "model-a", "device_id": "device-a", "preset_id": "code",
        "execution_location": "desktop",
        "source_workspace_id": "workspace-a", "git_branch": None, "base_commit": None, "worktree": False,
    }
    async def run():
        service = DesktopCodeBindingService(Conversations(), Bindings(existing), Profiles(), kernel_version="v")
        assert await service.commit(tenant_id="tenant-a", user_id="user-a", identity=identity(), title="x") is existing
        bad = DesktopSessionIdentity(**{**identity().__dict__, "dsh_workspace_id": "workspace-b"})
        with pytest.raises(ValueError, match="another immutable identity"):
            await service.commit(tenant_id="tenant-a", user_id="user-a", identity=bad, title="x")
    asyncio.run(run())


def test_desktop_binding_compensates_empty_conversation_when_insert_fails() -> None:
    async def run():
        conversations = Conversations()
        with pytest.raises(RuntimeError, match="insert failed"):
            await DesktopCodeBindingService(
                conversations, Bindings(fail=True), Profiles(), kernel_version="v"
            ).commit(tenant_id="tenant-a", user_id="user-a", identity=identity(), title="x")
        assert conversations.deleted[0][0] == "conversation-a"
    asyncio.run(run())


def test_desktop_turn_projection_persists_ordered_v3_history_and_terminal_state() -> None:
    async def run():
        existing = {
            "binding_id": "binding-a", "conversation_id": "conversation-a",
            "kernel_session_id": "session-a", "device_id": "device-a",
            "execution_location": "desktop", "active_turn": None,
        }
        conversations, bindings = Conversations(), Bindings(existing)
        service = DesktopCodeBindingService(conversations, bindings, Profiles(), kernel_version="v")
        await service.start_turn(
            tenant_id="tenant-a", user_id="user-a", device_id="device-a",
            kernel_session_id="session-a", text="fix it", message_id="desktop-msg-a",
        )
        await service.project_events(
            tenant_id="tenant-a", user_id="user-a", device_id="device-a",
            kernel_session_id="session-a", message_id="desktop-msg-a", events=[
                {"v": 3, "event_id": "approval", "id": "approval", "ts": 1, "type": "item.started", "item_kind": "approval", "item_id": "approval-a", "revision": 1, "stream_seq": 1, "stream_seq_end": 1, "payload": {"source": "dsh-local"}},
            ],
        )
        assert conversations.pending_count == 1
        events = [
            {"v": 3, "event_id": "e2", "id": "e2", "ts": 2, "type": "item.completed", "item_kind": "final_answer", "item_id": "a", "revision": 2, "stream_seq": 2, "stream_seq_end": 2, "payload": {"text": "done"}},
            {"v": 3, "event_id": "e1", "id": "e1", "ts": 1, "type": "run.started", "revision": 1, "stream_seq": 1, "stream_seq_end": 1, "payload": {}},
            {"v": 3, "event_id": "approval-done", "id": "approval-done", "ts": 2, "type": "item.completed", "item_kind": "approval", "item_id": "approval-a", "revision": 2, "stream_seq": 2, "stream_seq_end": 2, "payload": {"outcome": "allowed-once"}},
            {"v": 3, "event_id": "e3", "id": "e3", "ts": 3, "type": "run.completed", "revision": 3, "stream_seq": 3, "stream_seq_end": 3, "payload": {}},
        ]
        result = await service.project_events(
            tenant_id="tenant-a", user_id="user-a", device_id="device-a",
            kernel_session_id="session-a", message_id="desktop-msg-a", events=events,
        )
        assert result == {"cursor": 3, "terminal": True}
        assert conversations.projection["content"] == "done"
        assert [event["event_id"] for event in conversations.projection["execution_events"]] == ["approval", "e1", "approval-done", "e2", "e3"]
        assert bindings.finished["status"] == "completed"
        assert conversations.active is None
        assert conversations.pending_count == 0
    asyncio.run(run())


def test_desktop_turn_rejects_a_different_device() -> None:
    async def run():
        existing = {"binding_id": "b", "conversation_id": "c", "kernel_session_id": "session-a", "device_id": "device-a", "execution_location": "desktop"}
        service = DesktopCodeBindingService(Conversations(), Bindings(existing), Profiles(), kernel_version="v")
        with pytest.raises(ValueError, match="another desktop device"):
            await service.start_turn(
                tenant_id="tenant-a", user_id="user-a", device_id="device-b",
                kernel_session_id="session-a", text="x", message_id="m",
            )
    asyncio.run(run())


def test_desktop_runtime_rebind_preserves_profile_and_session_identity() -> None:
    async def run():
        existing = {
            "binding_id": "b", "conversation_id": "c", "kernel_session_id": "session-a",
            "device_id": "device-a", "execution_location": "desktop",
            "profile_version": "rp-a", "runtime_id": "runtime-old",
        }
        bindings = Bindings(existing)
        service = DesktopCodeBindingService(Conversations(), bindings, Profiles(), kernel_version="v")
        await service.rebind_runtime(
            tenant_id="tenant-a", user_id="user-a", device_id="device-a",
            conversation_id="c", profile_version="rp-a", runtime_id="runtime-new",
        )
        assert existing["runtime_id"] == "runtime-new"
        with pytest.raises(ValueError, match="Profile changed"):
            await service.rebind_runtime(
                tenant_id="tenant-a", user_id="user-a", device_id="device-a",
                conversation_id="c", profile_version="rp-b", runtime_id="runtime-x",
            )
    asyncio.run(run())
