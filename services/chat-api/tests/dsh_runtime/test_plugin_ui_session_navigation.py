"""Plugin session links must resolve to accessible MOVO conversations."""

import asyncio

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.dsh_runtime.plugin_ui.session_navigation import resolve_conversation, resolve_owned_kernel_session


class Collection:
    def __init__(self, rows):
        self.rows = rows

    async def find_one(self, query, projection=None):
        return next((row for row in self.rows if all(row.get(key) == value for key, value in query.items())), None)


class Database:
    def __init__(self, bindings, sessions, participants=()):
        self.collections = {
            "agent_kernel_bindings": Collection(bindings),
            "chat_sessions": Collection(sessions),
            "session_participants": Collection(participants),
        }
        self.chat_sessions = self.collections["chat_sessions"]
        self.session_participants = self.collections["session_participants"]

    def __getitem__(self, name):
        return self.collections[name]


def test_resolves_owner_and_active_shared_member():
    session_id = ObjectId()
    db = Database(
        [{"kernel_session_id": "dsh-123", "tenant_id": "tenant-a", "conversation_id": str(session_id)}],
        [{"_id": session_id, "main_id": "tenant-a", "user_id": "owner"}],
        [{"conversation_id": str(session_id), "main_id": "tenant-a", "user_id": "member", "removed_at": None}],
    )
    for user_id in ("owner", "member"):
        assert asyncio.run(resolve_conversation(db, tenant_id="tenant-a", user_id=user_id,
                                                kernel_session_id="dsh-123")) == str(session_id)


@pytest.mark.parametrize("tenant_id,user_id", [("tenant-b", "owner"), ("tenant-a", "stranger")])
def test_does_not_reveal_inaccessible_conversation(tenant_id, user_id):
    session_id = ObjectId()
    db = Database(
        [{"kernel_session_id": "dsh-123", "tenant_id": "tenant-a", "conversation_id": str(session_id)}],
        [{"_id": session_id, "main_id": "tenant-a", "user_id": "owner"}],
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(resolve_conversation(db, tenant_id=tenant_id, user_id=user_id,
                                         kernel_session_id="dsh-123"))
    assert error.value.status_code == 404


def test_conversation_launch_resolves_only_owner_server_binding():
    session_id = ObjectId()
    binding = {"kernel_session_id": "dsh-123", "tenant_id": "tenant-a",
               "conversation_id": str(session_id), "current": True,
               "execution_location": "server"}
    db = Database(
        [binding],
        [{"_id": session_id, "main_id": "tenant-a", "user_id": "owner"}],
        [{"conversation_id": str(session_id), "main_id": "tenant-a",
          "user_id": "member", "removed_at": None}],
    )
    assert asyncio.run(resolve_owned_kernel_session(
        db, tenant_id="tenant-a", user_id="owner",
        conversation_id=str(session_id))) == "dsh-123"
    with pytest.raises(HTTPException) as denied:
        asyncio.run(resolve_owned_kernel_session(
            db, tenant_id="tenant-a", user_id="member",
            conversation_id=str(session_id)))
    assert denied.value.status_code == 404
    binding["execution_location"] = "desktop"
    with pytest.raises(HTTPException) as desktop:
        asyncio.run(resolve_owned_kernel_session(
            db, tenant_id="tenant-a", user_id="owner",
            conversation_id=str(session_id)))
    assert desktop.value.status_code == 404
