"""Endpoint-level tests for the legacy append guard and the 409 conflict mapping (plan todo 10).

Pinned contract:

- ``POST /sessions/{session_id}/messages`` (the legacy ``max(seq)+1`` writer) is
  blocked with 409 ``session_shared_legacy_append_blocked`` for ANY session with
  an active participant, regardless of ``runtime_owner`` — the legacy writer is
  per-(session,user) and would collide sequence numbers in a shared thread.
- Single-member sessions keep today's behaviour: the owner appends, a
  non-owner receives 404 from the legacy writer's owner-only lookup, malformed
  payloads receive clean 400s, and a removed participant's session is not
  blocked.
- A duplicate-key error surfaced by a concurrent same-user legacy append on a
  single-member session maps to the SAME retryable 409 as the DSH path
  (``message_sequence_conflict``) rather than an unmapped 500. pymongo's
  ``insert_many`` raises ``BulkWriteError`` (``writeErrors`` code 11000),
  verified against real mongod 6.0.20 — both shapes are mapped.
- The DSH chat endpoint maps ``MessageSequenceConflict`` to 409 with the same
  stable code, mirroring the ``ConversationBusyError`` dict-detail style —
  never an unmapped 500.
- Purely observational invariant: after any legacy append on a single-member
  session, a subsequent DSH turn succeeds — T6's atomic ``$max`` seeding keeps
  the counter correct, not the legacy writer.
- Participant append via the DSH path (T6's session-scoped
  ``ConversationRepository.append_message``) is accepted and attributed to the
  participant.

TDD phases: baseline characterization (single-member legacy append, clean 400s,
non-owner 404 — passed on the UNCHANGED code) -> RED (shared-session 409,
conflict mapping, forced-duplicate mapping) -> GREEN.
"""

# allow: SIZE_OK — cohesive pinned matrix over two API surfaces (the legacy
# append guard + the DSH 409 mapping); T04/T07/T08/T09 precedent for
# session-sharing endpoint test files.

from __future__ import annotations

import asyncio
import datetime
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from bson import ObjectId
from fastapi import HTTPException

import app.services.session_persistence_service as session_persistence_module
from app.api.endpoints import dsh_chat, sessions
from app.api.endpoints.dsh_chat import ChatRequest, Message
from app.dsh_runtime import chat_service as chat_service_module
from app.dsh_runtime.application import dsh_runtime_application
from app.dsh_runtime.bindings import KernelBindingRepository
from app.dsh_runtime.chat_service import DshChatService
from app.dsh_runtime.conversation.participants_repository import SessionParticipantsRepository
from app.dsh_runtime.conversation.repository import (
    ConversationRepository,
    MessageSequenceConflict,
)
from app.dsh_runtime.events import KernelEventRepository
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator


TENANT = "tenant-a"


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _at(seconds_offset: int) -> datetime.datetime:
    return _now() + datetime.timedelta(seconds=offset)


async def _seed_user(db: Any, *, tenant_id: str, name: str) -> str:
    user_id = ObjectId()
    await db.end_users.insert_one({"_id": user_id, "main_id": tenant_id, "name": name, "status": "active"})
    return str(user_id)


async def _seed_session(db: Any, *, tenant_id: str, owner_id: str, title: str = "A session") -> str:
    now = _now()
    result = await db.chat_sessions.insert_one({
        "user_id": owner_id,
        "main_id": tenant_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
    })
    return str(result.inserted_id)


async def _seed_message(
    db: Any,
    *,
    session_id: str,
    user_id: str,
    tenant_id: str,
    seq: int,
    content: str,
    role: str = "user",
) -> None:
    await db.chat_messages.insert_one({
        "session_id": ObjectId(session_id),
        "user_id": user_id,
        "main_id": tenant_id,
        "role": role,
        "content": content,
        "created_at": _at(-100),
        "seq": seq,
        "message_type": "normal",
        "message_id": None,
    })


async def _join(db: Any, *, tenant_id: str, session_id: str, user_id: str) -> None:
    await SessionParticipantsRepository(db).add(
        tenant_id=tenant_id, conversation_id=session_id, user_id=user_id
    )


@pytest.fixture
def api_db(real_mongo_db, monkeypatch):
    harness = real_mongo_db
    # Two seams: the endpoint's guard/read lookups AND the legacy writer's own
    # get_db() call inside session_persistence_service (module-level import).
    monkeypatch.setattr(sessions, "get_db", lambda: harness.db)
    monkeypatch.setattr(session_persistence_module, "get_db", lambda: harness.db)
    harness.run(SessionParticipantsRepository(harness.db).ensure_indexes())
    # The unique per-session sequence index (created by
    # ConversationRepository.ensure_indexes() in production,
    # app/dsh_runtime/conversation/repository.py) — the fixture mirrors the
    # production requirement without executing that module (the T4 rule).
    harness.run(harness.db.chat_messages.create_index(
        [("main_id", 1), ("session_id", 1), ("seq", 1)],
        unique=True,
        name="unique_main_session_seq",
    ))
    return harness


def _append(
    harness: Any,
    monkeypatch: Any,
    *,
    session_id: str,
    user_id: str,
    tenant_id: str = TENANT,
    messages: list[dict[str, str]] | None = None,
) -> Any:
    # The handler resolves the caller from the authorization header via
    # _authorized_scope; patch the module-level seam so each test drives the
    # handler directly as a specific seeded user. authorization is passed
    # explicitly — a handler called outside FastAPI keeps the raw
    # Header(default=None) object, which is truthy (T8's Query-default gotcha).
    async def _fake_resolve(authorization: str | None) -> dict[str, Any]:
        return {"user": {"_id": ObjectId(user_id)}, "main_id": tenant_id}

    monkeypatch.setattr(sessions, "_resolve_session_user", _fake_resolve)
    payload = sessions.MessageAppend(
        user_id=user_id,
        main_id=tenant_id,
        messages=messages if messages is not None else [{"role": "user", "content": "legacy note"}],
    )
    return harness.run(sessions.append_messages(
        session_id=session_id, payload=payload, authorization=None,
    ))


# --- baseline characterization (must pass on the UNCHANGED code) ---


def test_single_member_legacy_append_assigns_per_user_seq(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Mine"))

    response = _append(harness, monkeypatch, session_id=session_id, user_id=owner_id)

    assert response.code == 0
    assert response.message == "success"
    rows = harness.run(harness.db.chat_messages.find({
        "main_id": TENANT, "session_id": ObjectId(session_id),
    }).sort("seq", 1).to_list(length=None))
    assert [row["seq"] for row in rows] == [1]
    assert [row["user_id"] for row in rows] == [owner_id]


def test_single_member_legacy_append_second_batch_continues_the_seq(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Mine"))
    _append(harness, monkeypatch, session_id=session_id, user_id=owner_id,
            messages=[{"role": "user", "content": "first"}])

    response = _append(harness, monkeypatch, session_id=session_id, user_id=owner_id,
                       messages=[{"role": "user", "content": "second"}])

    assert response.code == 0
    rows = harness.run(harness.db.chat_messages.find({
        "main_id": TENANT, "session_id": ObjectId(session_id),
    }).sort("seq", 1).to_list(length=None))
    assert [row["seq"] for row in rows] == [1, 2]


def test_legacy_append_invalid_session_id_returns_400(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))

    with pytest.raises(HTTPException) as exc_info:
        _append(harness, monkeypatch, session_id="not-an-objectid", user_id=owner_id)

    assert exc_info.value.status_code == 400


def test_legacy_append_empty_messages_returns_400(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Mine"))

    with pytest.raises(HTTPException) as exc_info:
        _append(harness, monkeypatch, session_id=session_id, user_id=owner_id, messages=[])

    assert exc_info.value.status_code == 400


def test_non_owner_legacy_append_on_single_member_session_returns_404(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    stranger_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Stranger"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Mine"))

    with pytest.raises(HTTPException) as exc_info:
        _append(harness, monkeypatch, session_id=session_id, user_id=stranger_id)

    # The legacy writer's owner-only lookup ({_id, user_id}) is today's 404;
    # single-member behaviour is preserved (no participant rows to trip the guard).
    assert exc_info.value.status_code == 404


def test_removed_participant_session_keeps_legacy_append_behaviour(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    participant_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Joined"))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=participant_id))
    harness.run(SessionParticipantsRepository(harness.db).remove(
        session_id, tenant_id=TENANT, user_id=participant_id))

    response = _append(harness, monkeypatch, session_id=session_id, user_id=owner_id)

    # The guard counts ACTIVE rows only (removed_at null) — a session whose
    # participant was removed is not a shared session any more.
    assert response.code == 0


def test_legacy_append_then_dsh_turn_succeeds_on_single_member_session(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    repo = ConversationRepository(harness.db)
    created = harness.run(repo.create(tenant_id=TENANT, user_id=owner_id, title="DSH session"))
    session_id = str(created["_id"])

    # Legacy append on the single-member DSH session (the guard does not fire):
    # the per-(session,user) writer mints seq without advancing next_message_seq.
    _append(harness, monkeypatch, session_id=session_id, user_id=owner_id,
            messages=[{"role": "user", "content": "legacy note"}])

    # The subsequent DSH turn: purely observational invariant — it succeeds,
    # the counter kept correct by T6's atomic $max seeding, not the legacy writer.
    harness.run(repo.append_message(
        conversation_id=session_id, tenant_id=TENANT, user_id=owner_id,
        role="user", content="dsh turn", message_id="user-turn-1",
    ))
    rows = harness.run(repo.list_messages(TENANT, session_id))
    assert [(row["seq"], row["content"], row["user_id"]) for row in rows] == [
        (1, "legacy note", owner_id),
        (2, "dsh turn", owner_id),
    ]


def test_participant_dsh_append_is_accepted_and_attributed(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    participant_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Joined"))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=participant_id))
    repo = ConversationRepository(harness.db)

    # T6's session-scoped append_message accepts the participant ({_id, main_id}
    # lookup) — the DSH path, not the legacy endpoint.
    harness.run(repo.append_message(
        conversation_id=session_id, tenant_id=TENANT, user_id=participant_id,
        role="user", content="hello from participant", message_id="user-turn-p1",
    ))

    rows = harness.run(repo.list_messages(TENANT, session_id))
    assert len(rows) == 1
    assert rows[0]["user_id"] == participant_id
    assert rows[0]["content"] == "hello from participant"


# --- the legacy guard (RED until implemented) ---


def test_owner_legacy_append_on_shared_session_returns_409(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    participant_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Joined"))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=participant_id))

    with pytest.raises(HTTPException) as exc_info:
        _append(harness, monkeypatch, session_id=session_id, user_id=owner_id)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "session_shared_legacy_append_blocked"
    assert exc_info.value.detail["session_id"] == session_id


def test_participant_legacy_append_on_shared_session_returns_409(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    participant_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Joined"))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=participant_id))

    with pytest.raises(HTTPException) as exc_info:
        _append(harness, monkeypatch, session_id=session_id, user_id=participant_id)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "session_shared_legacy_append_blocked"


def test_dsh_runtime_owner_session_also_blocks_legacy_append(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    participant_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="DSH"))
    harness.run(harness.db.chat_sessions.update_one(
        {"_id": ObjectId(session_id)}, {"$set": {"runtime_owner": "dsh"}}))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=participant_id))

    with pytest.raises(HTTPException) as exc_info:
        _append(harness, monkeypatch, session_id=session_id, user_id=owner_id)

    # The guard is keyed on the ACTIVE participant count, regardless of runtime_owner.
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "session_shared_legacy_append_blocked"


# --- the 409 conflict mappings (RED until implemented) ---


class _ConflictingChatService:
    """Narrowest seam for the endpoint's 409 mapping: prepare_turn raises the
    typed conflict T6's repository produces when a concurrent writer takes the
    per-session sequence slot (the mapping code is the surface under test)."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def prepare_turn(self, **kwargs: Any) -> Any:
        raise self._exc


def test_dsh_chat_maps_message_sequence_conflict_to_409(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Mine"))

    async def _fake_resolve(authorization: str | None) -> dict[str, Any]:
        return {"user": {"_id": ObjectId(owner_id)}, "main_id": TENANT}

    async def _allow_quota(main_id: str, user: dict[str, Any]) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(dsh_chat, "_resolve_session_user", _fake_resolve)
    monkeypatch.setattr(dsh_chat, "assert_quota_available", _allow_quota)
    monkeypatch.setattr(dsh_runtime_application, "chat", _ConflictingChatService(
        MessageSequenceConflict(conversation_id=session_id, seq=1)))
    request = ChatRequest(
        messages=[Message(role="user", content="hello")],
        output_spec={"session_id": session_id},
    )

    with pytest.raises(HTTPException) as exc_info:
        harness.run(dsh_chat.chat_completions(request, authorization=None))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "message_sequence_conflict"
    assert exc_info.value.detail["session_id"] == session_id


class _RacingCollection:
    """Deterministic interleaving (T6's technique): a "concurrent" writer
    persists the same (main_id, session_id, seq) row between _next_seq's read
    and the legacy insert_many — no sleeps."""

    def __init__(self, collection: Any) -> None:
        self._collection = collection

    async def insert_many(self, docs: Any, *args: Any, **kwargs: Any) -> Any:
        colliding = dict(list(docs)[0])
        colliding.setdefault("message_id", None)  # escapes any message-id index
        await self._collection.insert_one(colliding)
        return await self._collection.insert_many(docs, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._collection, name)


class _RacingDb:
    def __init__(self, db: Any) -> None:
        self._db = db
        self.chat_messages = _RacingCollection(db.chat_messages)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._db, name)


def test_forced_duplicate_legacy_append_returns_retryable_409_not_500(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Mine"))
    monkeypatch.setattr(session_persistence_module, "get_db", lambda: _RacingDb(harness.db))

    with pytest.raises(HTTPException) as exc_info:
        _append(harness, monkeypatch, session_id=session_id, user_id=owner_id,
                messages=[{"role": "user", "content": "dup race"}])

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "message_sequence_conflict"
    # Two concurrent legacy appends never produce duplicate seq: the colliding
    # insert was rejected by the unique index (only the "concurrent" row remains).
    rows_with_seq_one = harness.run(harness.db.chat_messages.count_documents({
        "main_id": TENANT, "session_id": ObjectId(session_id), "seq": 1,
    }))
    assert rows_with_seq_one == 1


# --- T04 (plan checkbox 4): validated user-message turn identity -------------
#
# X-User-Message-Id cases: the endpoint parse/pass-through/echo, the
# repository conflict mapping, and the sequential admission boundary driven
# through the REAL DshChatService (T2's claim/authorize structure untouched;
# only the user-row identity the admission persists changes).

_T04_BAD_IDS = [
    "x" * 129,          # overlong (cap is 128)
    "-leading-hyphen",  # first character must be alphanumeric
    "has space",
    "semi;colon",
    "sl/ash",
    "",
]


@pytest.fixture
def admission_env(real_mongo_db, monkeypatch):
    harness = real_mongo_db
    monkeypatch.setattr(chat_service_module, "get_db", lambda: harness.db, raising=False)
    harness.run(SessionParticipantsRepository(harness.db).ensure_indexes())
    harness.run(KernelBindingRepository(harness.db).ensure_indexes())

    owner_id = str(ObjectId())
    participant_id = str(ObjectId())
    session_id = str(harness.run(ConversationRepository(harness.db).create(
        tenant_id=TENANT, user_id=owner_id, title="t04-admission"))["_id"])
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=participant_id))

    foreign_tenant = "tenant-b"
    foreign_session_id = str(harness.run(ConversationRepository(harness.db).create(
        tenant_id=foreign_tenant, user_id=str(ObjectId()), title="t04-foreign"))["_id"])

    binding_id = f"bind-{uuid.uuid4().hex}"
    now = _now()
    harness.run(harness.db.agent_kernel_bindings.insert_one({
        "binding_id": binding_id,
        "conversation_id": session_id,
        "tenant_id": TENANT,
        "user_id": owner_id,
        "current": True,
        "status": "idle",
        "active_turn": None,
        "kernel_session_id": f"ks-{uuid.uuid4().hex}",
        "execution_location": "server",
        "profile_version": "pv-t04",
        "model_instance_id": "model-a",
        "created_at": now,
        "updated_at": now,
    }))

    chat = DshChatService(
        gateway=SimpleNamespace(),
        coordinator=RuntimeCoordinator(SimpleNamespace(), KernelBindingRepository(harness.db)),
        conversations=ConversationRepository(harness.db),
        bindings=KernelBindingRepository(harness.db),
        events=KernelEventRepository(harness.db),
        profiles=SimpleNamespace(),
        kernel_version="test-kernel",
    )

    class _GatedRunner:
        def __init__(self) -> None:
            self.release = asyncio.Event()

        async def __call__(self, *, binding, message_id, request_id, text,
                           temporal_context, turn_context, live_stream):
            await self.release.wait()
            await chat._finalizer.finalize(
                binding=binding, message_id=message_id, status="completed"
            )
            return "completed"

    runner = _GatedRunner()
    chat._turn_runner.run = runner

    async def passthrough(binding, *, tenant_id, user_id, model_instance_id=None):
        return SimpleNamespace(binding=binding)

    chat._profile_sync.synchronize = passthrough
    monkeypatch.setattr(dsh_runtime_application, "chat", chat)
    return SimpleNamespace(
        harness=harness, chat=chat, runner=runner, session_id=session_id,
        owner_id=owner_id, participant_id=participant_id, binding_id=binding_id,
        foreign_session_id=foreign_session_id, foreign_tenant=foreign_tenant,
    )


def _drive_completion(
    env: Any,
    monkeypatch: Any,
    *,
    user_message_id: str | None = None,
    user_id: str | None = None,
) -> Any:
    # The direct-endpoint-call pattern of this file: patch the identity and
    # quota seams, then call the real handler with the header value as the
    # handler receives it from FastAPI.
    async def _fake_resolve(authorization: str | None) -> dict[str, Any]:
        return {"user": {"_id": ObjectId(user_id or env.owner_id)}, "main_id": TENANT}

    async def _allow_quota(main_id: str, user: dict[str, Any]) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(dsh_chat, "_resolve_session_user", _fake_resolve)
    monkeypatch.setattr(dsh_chat, "assert_quota_available", _allow_quota)
    request = ChatRequest(
        messages=[Message(role="user", content="t04 identity")],
        output_spec={"session_id": env.session_id, "model_id": "model-a"},
    )
    return dsh_chat.chat_completions(
        request, authorization=None, x_user_message_id=user_message_id,
    )


def _t04_rows(env: Any) -> list[Any]:
    return list(env.harness.run(
        ConversationRepository(env.harness.db).list_messages(TENANT, env.session_id)
    ))


def test_client_user_message_id_is_persisted_and_echoed(admission_env, monkeypatch) -> None:
    env = admission_env
    response = env.harness.run(
        _drive_completion(env, monkeypatch, user_message_id="client-turn-1")
    )

    assistant_id = response.headers["X-Message-Id"]
    assert response.status_code == 200
    assert response.headers["X-User-Message-Id"] == "client-turn-1"
    assert response.headers["X-Session-Id"] == env.session_id
    assert assistant_id.startswith("msg-")
    assert assistant_id != "client-turn-1"

    rows = _t04_rows(env)
    user_row = next(row for row in rows if row["role"] == "user")
    assistant_row = next(row for row in rows if row["role"] == "assistant")
    # The committed user row matches the echoed header; the server keeps the
    # assistant identity distinct from the client id.
    assert str(user_row["message_id"]) == response.headers["X-User-Message-Id"]
    assert str(user_row["content"]) == "t04 identity"
    assert str(assistant_row["message_id"]) == assistant_id
    assert assistant_row["message_id"] != user_row["message_id"]

    env.runner.release.set()
    assert env.harness.run(env.chat.wait_turn(assistant_id)) == "completed"


@pytest.mark.parametrize("bad_id", _T04_BAD_IDS)
def test_invalid_client_id_falls_back_to_server_minted_id(
    admission_env, monkeypatch, bad_id: str
) -> None:
    env = admission_env
    response = env.harness.run(
        _drive_completion(env, monkeypatch, user_message_id=bad_id)
    )

    accepted = response.headers["X-User-Message-Id"]
    assert response.status_code == 200
    assert accepted.startswith("user-turn-")
    assert accepted != bad_id
    rows = _t04_rows(env)
    user_row = next(row for row in rows if row["role"] == "user")
    assert str(user_row["message_id"]) == accepted

    env.runner.release.set()
    assert env.harness.run(
        env.chat.wait_turn(response.headers["X-Message-Id"])
    ) == "completed"


def test_existing_same_scope_client_id_maps_to_409_conflict(
    admission_env, monkeypatch
) -> None:
    env = admission_env
    harness = env.harness
    harness.run(ConversationRepository(harness.db).append_message(
        conversation_id=env.session_id, tenant_id=TENANT, user_id=env.owner_id,
        role="user", content="seeded", message_id="client-dup",
    ))
    claims: list[str] = []
    real_claim = env.chat._bindings.claim_turn_authorized

    async def counting_claim(binding_id, **kwargs):
        claims.append(kwargs["message_id"])
        return await real_claim(binding_id, **kwargs)

    monkeypatch.setattr(env.chat._bindings, "claim_turn_authorized", counting_claim)

    with pytest.raises(HTTPException) as exc_info:
        harness.run(_drive_completion(env, monkeypatch, user_message_id="client-dup"))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "user_message_id_conflict"
    assert exc_info.value.detail["session_id"] == env.session_id
    # No assistant placeholder and no orphaned second user row: the conflict
    # fires before any write, and the losing claim is rolled back.
    rows = _t04_rows(env)
    assert [str(row["message_id"]) for row in rows] == ["client-dup"]
    binding = harness.run(
        harness.db.agent_kernel_bindings.find_one({"binding_id": env.binding_id})
    )
    assert binding["active_turn"]["status"] == "failed"
    assert len(claims) == 1


def test_existing_cross_session_client_id_maps_to_409_conflict(
    admission_env, monkeypatch
) -> None:
    env = admission_env
    harness = env.harness
    harness.run(ConversationRepository(harness.db).append_message(
        conversation_id=env.foreign_session_id, tenant_id=env.foreign_tenant,
        user_id=str(ObjectId()), role="user", content="foreign", message_id="client-cross",
    ))

    with pytest.raises(HTTPException) as exc_info:
        harness.run(_drive_completion(env, monkeypatch, user_message_id="client-cross"))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "user_message_id_conflict"
    assert _t04_rows(env) == []


def test_removal_at_claim_boundary_with_client_id_leaves_no_orphan(
    admission_env, monkeypatch
) -> None:
    env = admission_env
    harness = env.harness
    claims: list[str] = []
    real_claim = env.chat._bindings.claim_turn_authorized

    async def remove_then_claim(binding_id, **kwargs):
        claims.append(kwargs["message_id"])
        await SessionParticipantsRepository(harness.db).remove(
            env.session_id, tenant_id=TENANT, user_id=env.participant_id
        )
        return await real_claim(binding_id, **kwargs)

    monkeypatch.setattr(env.chat._bindings, "claim_turn_authorized", remove_then_claim)

    with pytest.raises(HTTPException) as exc_info:
        harness.run(_drive_completion(
            env, monkeypatch, user_message_id="client-race", user_id=env.participant_id,
        ))

    # A removal committed at the claim boundary rolls the claim back and the
    # endpoint maps the typed denial to 404 - one admission attempt, no retry,
    # no orphaned user row.
    assert exc_info.value.status_code == 404
    assert len(claims) == 1
    assert _t04_rows(env) == []
    binding = harness.run(
        harness.db.agent_kernel_bindings.find_one({"binding_id": env.binding_id})
    )
    assert binding["status"] == "failed"
    assert binding["active_turn"]["status"] == "failed"


def test_concurrent_turns_with_distinct_client_ids_claim_exactly_one(
    admission_env, monkeypatch
) -> None:
    env = admission_env
    claims: list[str] = []
    real_claim = env.chat._bindings.claim_turn_authorized

    async def counting_claim(binding_id, **kwargs):
        claims.append(kwargs["message_id"])
        return await real_claim(binding_id, **kwargs)

    monkeypatch.setattr(env.chat._bindings, "claim_turn_authorized", counting_claim)

    async def scenario():
        return await asyncio.gather(
            _drive_completion(env, monkeypatch, user_message_id="client-a"),
            _drive_completion(env, monkeypatch, user_message_id="client-b"),
            return_exceptions=True,
        )

    results = env.harness.run(scenario())
    responses = [item for item in results if not isinstance(item, BaseException)]
    failures = [item for item in results if isinstance(item, HTTPException)]
    assert len(responses) == 1
    assert len(failures) == 1
    assert failures[0].status_code == 409
    assert failures[0].detail["code"] == "session_already_running"
    assert failures[0].detail["session_id"] == env.session_id
    # Exactly one admission attempt per submitted turn: the loser is neither
    # queued nor auto-retried, and the winner's claim is untouched.
    assert len(claims) == 2

    winner_header = responses[0].headers["X-User-Message-Id"]
    assert winner_header in {"client-a", "client-b"}
    rows = _t04_rows(env)
    user_row = next(row for row in rows if row["role"] == "user")
    assistant_row = next(row for row in rows if row["role"] == "assistant")
    assert len(rows) == 2
    assert str(user_row["message_id"]) == winner_header
    assert str(assistant_row["message_id"]) == responses[0].headers["X-Message-Id"]
    assert assistant_row["message_id"] != user_row["message_id"]

    env.runner.release.set()
    assert env.harness.run(
        env.chat.wait_turn(str(assistant_row["message_id"]))
    ) == "completed"


def test_server_minted_reappend_stays_idempotent(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Mine"))
    repo = ConversationRepository(harness.db)

    first = harness.run(repo.append_message(
        conversation_id=session_id, tenant_id=TENANT, user_id=owner_id,
        role="user", content="one", message_id="server-1",
    ))
    second = harness.run(repo.append_message(
        conversation_id=session_id, tenant_id=TENANT, user_id=owner_id,
        role="user", content="one", message_id="server-1",
    ))

    assert first["message_id"] == second["message_id"] == "server-1"
    assert harness.run(
        harness.db.chat_messages.count_documents({"message_id": "server-1"})
    ) == 1
