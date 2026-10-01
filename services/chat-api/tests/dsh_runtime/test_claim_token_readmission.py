"""F2 re-admission: same-token retry converges on the durable claim.

The stable ``claim:{X-User-Message-Id}`` token derived in
``app/api/endpoints/dsh_chat.py`` must re-admit the live turn through
``prepare_turn`` -> ``claim_turn_authorized``'s same-token fallback: the
second call with the same token returns the EXISTING claim rows (no
``ConversationBusyError``, zero duplicate user/assistant rows, same
``message_id``/``request_id`` surfaced). A different token (what the
unwired endpoint minted fresh on every retry) still fast-409s.

Harness mirrors ``test_shared_binding_rotation.py`` (real mongo, real
``DshChatService``, the turn runner held open so the claim stays live)
and the T04 ``admission_env`` endpoint pattern in
``tests/api/test_legacy_append_guard.py`` for the derivation unit.
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from bson import ObjectId

from app.api.endpoints import dsh_chat
from app.api.endpoints.dsh_chat import ChatRequest, Message
from app.dsh_runtime import chat_service as chat_service_module
from app.dsh_runtime.application import dsh_runtime_application
from app.dsh_runtime.bindings import KernelBindingRepository
from app.dsh_runtime.chat_service import ConversationBusyError, DshChatService
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.conversation.participants_repository import (
    SessionParticipantsRepository,
)
from app.dsh_runtime.events import KernelEventRepository
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator

TENANT = "tenant-claim-readmission"


@pytest.fixture
def readmit_env(real_mongo_db, monkeypatch):
    harness = real_mongo_db
    monkeypatch.setattr(chat_service_module, "get_db", lambda: harness.db, raising=False)
    harness.run(SessionParticipantsRepository(harness.db).ensure_indexes())
    harness.run(KernelBindingRepository(harness.db).ensure_indexes())

    owner_id = str(ObjectId())
    session_id = str(
        harness.run(
            ConversationRepository(harness.db).create(
                tenant_id=TENANT, user_id=owner_id, title="f2-readmission"
            )
        )["_id"]
    )
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    binding_id = f"bind-{uuid.uuid4().hex}"
    harness.run(
        harness.db.agent_kernel_bindings.insert_one(
            {
                "binding_id": binding_id,
                "conversation_id": session_id,
                "tenant_id": TENANT,
                "user_id": owner_id,
                "current": True,
                "status": "idle",
                "active_turn": None,
                "kernel_session_id": f"ks-{uuid.uuid4().hex}",
                "execution_location": "server",
                "profile_version": "pv-f2",
                "model_instance_id": "model-a",
                "created_at": now,
                "updated_at": now,
            }
        )
    )
    chat = DshChatService(
        gateway=SimpleNamespace(),
        coordinator=RuntimeCoordinator(SimpleNamespace(), KernelBindingRepository(harness.db)),
        conversations=ConversationRepository(harness.db),
        bindings=KernelBindingRepository(harness.db),
        events=KernelEventRepository(harness.db),
        profiles=SimpleNamespace(),
        kernel_version="test-kernel",
    )
    release = asyncio.Event()
    chat._turn_runner.run = _hold_runner(chat, release)

    async def passthrough(binding, *, tenant_id, user_id, model_instance_id=None):
        return SimpleNamespace(binding=binding)

    chat._profile_sync.synchronize = passthrough
    return SimpleNamespace(
        harness=harness, chat=chat, release=release, session_id=session_id,
        owner_id=owner_id, binding_id=binding_id,
    )


def _hold_runner(chat, release):
    async def _run(*, binding, message_id, **_kwargs):
        await release.wait()
        await chat._finalizer.finalize(binding=binding, message_id=message_id, status="completed")
        return "completed"

    return _run


def _rows(env):
    return list(
        env.harness.run(ConversationRepository(env.harness.db).list_messages(TENANT, env.session_id))
    )


def test_same_derived_token_twice_returns_existing_claim_without_duplicates(readmit_env):
    env = readmit_env
    token = "claim:client-turn-1"
    first = env.harness.run(
        env.chat.prepare_turn(
            tenant_id=TENANT, user_id=env.owner_id, conversation_id=env.session_id,
            text="first attempt", model_instance_id="model-a", timezone_name="UTC",
            images=[], documents=[], claim_token=token, user_message_id="client-turn-1",
        )
    )
    live = env.harness.run(env.harness.db.agent_kernel_bindings.find_one({"binding_id": env.binding_id}))
    live_request_id = str((live.get("active_turn") or {}).get("request_id") or "")
    assert live_request_id

    # RED proof (the unwired endpoint behaviour): a fresh-minted token for the
    # same live turn — claim_token=None mints fresh inside prepare_turn — 409s.
    with pytest.raises(ConversationBusyError):
        env.harness.run(
            env.chat.prepare_turn(
                tenant_id=TENANT, user_id=env.owner_id, conversation_id=env.session_id,
                text="first attempt", model_instance_id="model-a", timezone_name="UTC",
                images=[], documents=[], claim_token=None, user_message_id="client-turn-1",
            )
        )

    second = env.harness.run(
        env.chat.prepare_turn(
            tenant_id=TENANT, user_id=env.owner_id, conversation_id=env.session_id,
            text="first attempt", model_instance_id="model-a", timezone_name="UTC",
            images=[], documents=[], claim_token=token, user_message_id="client-turn-1",
        )
    )
    assert second.message_id == first.message_id
    assert second.binding_id == first.binding_id
    assert second.user_message_id == "client-turn-1"

    rows = _rows(env)
    assert len(rows) == 2
    by_role = {row["role"]: str(row["message_id"]) for row in rows}
    assert by_role["user"] == "client-turn-1"
    assert by_role["assistant"] == first.message_id
    still_live = env.harness.run(
        env.harness.db.agent_kernel_bindings.find_one({"binding_id": env.binding_id})
    )
    assert str((still_live.get("active_turn") or {}).get("request_id") or "") == live_request_id

    env.release.set()
    assert env.harness.run(env.chat.wait_turn(first.message_id)) == "completed"


def test_different_token_while_live_still_fast_409s(readmit_env):
    env = readmit_env
    first = env.harness.run(
        env.chat.prepare_turn(
            tenant_id=TENANT, user_id=env.owner_id, conversation_id=env.session_id,
            text="owner streaming", model_instance_id="model-a", timezone_name="UTC",
            images=[], documents=[], claim_token="claim:client-a", user_message_id="client-a",
        )
    )
    with pytest.raises(ConversationBusyError):
        env.harness.run(
            env.chat.prepare_turn(
                tenant_id=TENANT, user_id=env.owner_id, conversation_id=env.session_id,
                text="concurrent send", model_instance_id="model-a", timezone_name="UTC",
                images=[], documents=[], claim_token="claim:client-b", user_message_id="client-b",
            )
        )
    env.release.set()
    assert env.harness.run(env.chat.wait_turn(first.message_id)) == "completed"


class _CapturingChat:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def prepare_turn(self, **kwargs: Any):
        self.calls.append(kwargs)
        from app.dsh_runtime.chat_service import PreparedTurn

        return PreparedTurn(
            conversation_id="session-x", message_id="msg-x",
            binding_id="binding-x", user_message_id=str(kwargs.get("user_message_id") or ""),
        )

    async def stream(self, turn, **kwargs: Any):
        yield b""


def _drive_header(monkeypatch, harness, *, header_value, chat):
    async def _fake_resolve(authorization: str | None) -> dict[str, Any]:
        return {"user": {"_id": ObjectId()}, "main_id": TENANT}

    async def _allow_quota(main_id: str, user: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def _admit(**kwargs: Any):
        return SimpleNamespace(selected_writing_skill_id=None, selected_skill_id=None)

    monkeypatch.setattr(dsh_chat, "_resolve_session_user", _fake_resolve)
    monkeypatch.setattr(dsh_chat, "assert_quota_available", _allow_quota)
    monkeypatch.setattr(dsh_chat, "admit_skill_selection", _admit)
    monkeypatch.setattr(dsh_runtime_application, "chat", chat)
    request = ChatRequest(messages=[Message(role="user", content="hi")], output_spec={})
    return harness.run(
        dsh_chat.chat_completions(request, authorization=None, x_user_message_id=header_value)
    )


def test_endpoint_derives_stable_claim_token_from_client_id(real_mongo_db, monkeypatch):
    harness = real_mongo_db
    chat = _CapturingChat()
    _drive_header(monkeypatch, harness, header_value="client-turn-9", chat=chat)
    assert chat.calls[0]["claim_token"] == "claim:client-turn-9"
    assert chat.calls[0]["user_message_id"] == "client-turn-9"


def test_endpoint_passes_none_claim_token_without_client_id(real_mongo_db, monkeypatch):
    harness = real_mongo_db
    chat = _CapturingChat()
    _drive_header(monkeypatch, harness, header_value=None, chat=chat)
    assert chat.calls[0]["claim_token"] is None
