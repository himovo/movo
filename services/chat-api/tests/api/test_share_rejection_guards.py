# allow: SIZE_OK — one cohesive seam (the share-create rejection gate's
# conversation-scoped verification, the desktop rebind participant guard, and
# the non-server ValueError -> 400 mapping), pinned to the frozen plan's
# todo-17 QA matrix; mirrors T04/T07/T08/T09/T10/T11/T12/T13's pinned
# single-file matrices.
"""Plan todo 17 — reject sharing for unbound and non-server sessions, and
guard post-join rebinding.

Three surfaces:
- The share-create gate (todo 4's implementation, verified here): with todo
  13's conversation-scoped ``current()`` the gate checks the CONVERSATION's
  current binding — an unbound legacy session is 409 ``session_share_no_binding``
  and creates no token, a desktop-bound session is 409 ``session_share_not_server``,
  and a server-bound session shares successfully even after the binding has
  rotated to a participant (the vacuous user-scoped check would have 409'd).
- The desktop rebind guard (todo 17's implementation): the rebind endpoint
  refuses to move a conversation to a desktop binding while it has an active
  participant -> 409 ``session_shared_rebind_blocked`` — the "auto-revoke
  instead" alternative is rejected, because revoke does not remove existing
  participants and would leave them permanently unable to send.
- A participant's turn on a non-server binding raises ``ValueError``, mapped
  to 400 at ``dsh_chat.py`` (``_start_chat_completions``'s ``except ValueError``)
  — never a 500.

TDD phases recorded in this module:
- baseline characterization passed on the UNCHANGED code (the share-create
  gate matrix, the solo-owner rebind, the unknown/malformed rebind 404, the
  400 mapping),
- failing-first proof (RED) for the rebind participant guard,
- the green run after the implementation.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.api.endpoints import dsh_chat, session_shares
from app.api.principal import ApiPrincipal
from app.core import quota_policy
from app.dsh_runtime import chat_service as chat_service_module
from app.dsh_runtime.application import dsh_runtime_application
from app.dsh_runtime.bindings.repository import KernelBindingRepository
from app.dsh_runtime.chat_service import DshChatService
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.conversation.participants_repository import (
    SessionParticipantsRepository,
)
from app.dsh_runtime.desktop_binding import DesktopCodeBindingService
from app.dsh_runtime.events import KernelEventRepository
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator
from app.services.session_sharing.service import hash_token


TENANT = "tenant-share-rejection-guards"
OWNER = "owner"
PARTICIPANT = "participant"

REBIND_BLOCKED = "session_shared_rebind_blocked"


def _principal(main_id: str, user_id: str) -> ApiPrincipal:
    return ApiPrincipal(kind="end_user", main_id=main_id, user_id=user_id)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


async def _seed_session(db: Any, *, tenant_id: str, owner_id: str, title: str = "Shared session") -> str:
    now = _now()
    result = await db.chat_sessions.insert_one({
        "user_id": owner_id,
        "main_id": tenant_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
    })
    return str(result.inserted_id)


async def _seed_binding(
    db: Any,
    *,
    tenant_id: str,
    owner_id: str,
    session_id: str,
    execution_location: str = "server",
    device_id: str | None = None,
    profile_version: str = "rp-1",
    runtime_id: str = "rt-1",
    replaces_binding_id: str | None = None,
) -> dict[str, Any]:
    """One binding through the REAL repository write path (T4/T12's technique).

    ``replaces_binding_id`` reproduces the exact rotation shape: the
    predecessor becomes current=False "replacing"->"superseded", the successor
    is current=True — the same write path production uses.
    """
    return await KernelBindingRepository(db).create(
        tenant_id=tenant_id,
        user_id=owner_id,
        conversation_id=session_id,
        kernel_session_id=f"ks-{uuid.uuid4()}",
        runtime_id=runtime_id,
        profile_version=profile_version,
        model_instance_id="model-instance",
        kernel_version="test-kernel",
        preset_id="code" if execution_location == "desktop" else "askai-enterprise",
        execution_location=execution_location,
        dsh_workspace_id="ws-1" if execution_location == "desktop" else None,
        device_id=device_id,
        source_workspace_id="src-1" if execution_location == "desktop" else None,
        replaces_binding_id=replaces_binding_id,
    )


def _current_binding(harness: Any, session_id: str) -> dict[str, Any] | None:
    async def _one():
        return await harness.db.agent_kernel_bindings.find_one(
            {"conversation_id": session_id, "current": True}
        )

    return harness.run(_one())


# ---------------------------------------------------------------------------
# Share-create gate (session_shares.py) — todo 4's implementation, verified
# ---------------------------------------------------------------------------


@pytest.fixture
def api_db(real_mongo_db, monkeypatch):
    harness = real_mongo_db
    monkeypatch.setattr(session_shares, "get_db", lambda: harness.db)
    harness.run(SessionParticipantsRepository(harness.db).ensure_indexes())
    return harness


def _create(harness: Any, session_id: str, principal: ApiPrincipal) -> dict[str, Any]:
    return harness.run(session_shares.create_session_share(
        session_id,
        session_shares.CreateShareRequest(expiresInDays=30),
        principal=principal,
    ))


def test_unbound_legacy_session_share_returns_409_no_binding_and_no_token(api_db) -> None:
    # QA failure (plan todo 17): a conversation with NO current binding at all
    # (legacy/unbound) is 409 session_share_no_binding and NO token is created.
    harness = api_db
    owner_id = "user-owner"
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))

    with pytest.raises(HTTPException) as excinfo:
        _create(harness, session_id, _principal(TENANT, owner_id))

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["code"] == "session_share_no_binding"
    doc = harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))
    assert doc.get("share_token_hash") is None


def test_desktop_bound_session_share_returns_409_not_server(api_db) -> None:
    # QA failure (plan todo 17): a conversation whose current binding's
    # execution_location != "server" is 409 session_share_not_server.
    harness = api_db
    owner_id = "user-owner"
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    harness.run(_seed_binding(
        harness.db, tenant_id=TENANT, owner_id=owner_id, session_id=session_id,
        execution_location="desktop", device_id="dev-1",
    ))

    with pytest.raises(HTTPException) as excinfo:
        _create(harness, session_id, _principal(TENANT, owner_id))

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["code"] == "session_share_not_server"
    doc = harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))
    assert doc.get("share_token_hash") is None


def test_server_bound_session_shares_successfully(api_db) -> None:
    # QA happy (plan todo 17): a server-located, bound session shares.
    harness = api_db
    owner_id = "user-owner"
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    harness.run(_seed_binding(
        harness.db, tenant_id=TENANT, owner_id=owner_id, session_id=session_id,
        execution_location="server",
    ))

    response = _create(harness, session_id, _principal(TENANT, owner_id))

    data = response["data"]
    assert isinstance(data["token"], str) and data["token"]
    assert data["expires_at"] > _now()
    doc = harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))
    assert doc["share_token_hash"] == hash_token(data["token"])


def test_share_gate_resolves_the_conversations_binding_after_rotation_to_a_participant(api_db) -> None:
    # The vacuous-check closure (todo 13 + todo 17): the gate checks the
    # CONVERSATION's current binding, not the OWNER's. After the binding has
    # rotated to a participant speaker (the successor is attributed to the
    # participant, the owner's predecessor is superseded), the owner's share
    # still succeeds on a server-located binding. Under the pre-T13
    # user-scoped current() this call found no binding and would have 409'd.
    harness = api_db
    owner_id = "user-owner"
    participant_id = "user-participant"
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    predecessor = harness.run(_seed_binding(
        harness.db, tenant_id=TENANT, owner_id=owner_id, session_id=session_id,
        execution_location="server",
    ))
    successor = harness.run(_seed_binding(
        harness.db, tenant_id=TENANT, owner_id=participant_id, session_id=session_id,
        execution_location="server", replaces_binding_id=str(predecessor["binding_id"]),
    ))
    assert successor["current"] is True
    assert successor["user_id"] == participant_id

    response = _create(harness, session_id, _principal(TENANT, owner_id))

    data = response["data"]
    assert isinstance(data["token"], str) and data["token"]
    doc = harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))
    assert doc["share_token_hash"] == hash_token(data["token"])


# ---------------------------------------------------------------------------
# Desktop rebind guard (dsh_chat.py) — todo 17's implementation
# ---------------------------------------------------------------------------


class _FakeGateway:
    """Kernel-session seams the DshChatService needs at construction; the
    non-server rejection and the rebind guard fire before any of it runs."""

    def __init__(self) -> None:
        self.disposed_sessions: list[str] = []

    async def discover_runtime(self, *, tenant_id: str, profile_version: str, isolation_key: str):
        return None

    async def create_runtime(self, request):
        raise AssertionError("no turn may reach runtime creation in these tests")

    async def create_session(self, request):
        raise AssertionError("no turn may reach kernel-session creation in these tests")

    def attach_session(self, **kwargs: Any) -> None:
        return None

    async def resume_session(self, session_id: str) -> None:
        return None

    async def dispose_session(self, session_id: str) -> None:
        self.disposed_sessions.append(str(session_id))

    async def cancel(self, request) -> dict[str, Any]:
        raise AssertionError("no cancel may run in these tests")


class _NoProfiles:
    """``RuntimeProfilePublisher`` placeholder: any call is a test-design bug
    (the non-server rejection fires before the profile work)."""

    def __getattr__(self, name: str):
        raise AssertionError(f"profiles.{name} must not run in these tests")


@pytest.fixture
def desktop_thread(real_mongo_db, monkeypatch):
    """Real repositories + the REAL DshChatService and REAL
    DesktopCodeBindingService; fakes only at the gateway/profile seams and
    the turn runner (finalizes turns like the real one — T13's pattern).

    All three ``get_db`` seams are patched (T10's lesson): ``dsh_chat.get_db``
    (the rebind guard's lookups), ``chat_service.get_db`` (the turn admission's
    participant branch) and ``quota_policy.get_db`` (the completions quota
    check) — each module imports it at module level and resolves it at call
    time. ``raising=False`` mirrors T7/T13's precedent.
    """
    harness = real_mongo_db
    harness.run(SessionParticipantsRepository(harness.db).ensure_indexes())
    harness.run(KernelBindingRepository(harness.db).ensure_indexes())
    monkeypatch.setattr(dsh_chat, "get_db", lambda: harness.db, raising=False)
    monkeypatch.setattr(chat_service_module, "get_db", lambda: harness.db, raising=False)
    monkeypatch.setattr(quota_policy, "get_db", lambda: harness.db, raising=False)

    gateway = _FakeGateway()
    chat = DshChatService(
        gateway=gateway,
        coordinator=RuntimeCoordinator(gateway, KernelBindingRepository(harness.db)),
        conversations=ConversationRepository(harness.db),
        bindings=KernelBindingRepository(harness.db),
        events=KernelEventRepository(harness.db),
        profiles=_NoProfiles(),
        kernel_version="test-kernel",
    )

    async def _finish_immediately(*, binding, message_id, **_kwargs):
        await chat._finalizer.finalize(
            binding=binding, message_id=message_id, status="completed",
        )
        return "completed"

    chat._turn_runner.run = _finish_immediately
    monkeypatch.setattr(dsh_runtime_application, "chat", chat)
    monkeypatch.setattr(
        dsh_runtime_application,
        "desktop_bindings",
        DesktopCodeBindingService(
            ConversationRepository(harness.db),
            KernelBindingRepository(harness.db),
            _NoProfiles(),
            kernel_version="test-kernel",
        ),
    )
    return harness


def _identity_seam(ids: dict[str, ObjectId]):
    async def resolve(authorization: str | None):
        token = str(authorization or "").removeprefix("Bearer ").strip()
        oid = ids.get(token)
        if oid is None:
            raise LookupError(f"no seeded end-user for bearer token {token!r}")
        # space_type="personal" + a seeded org row keep the completions quota
        # check (assert_quota_available) green in the 400-mapping tests.
        return {"user": {"_id": oid, "status": "active", "space_type": "personal"}, "main_id": TENANT}

    return resolve


async def _seed_desktop_conversation(
    harness: Any, ids: dict[str, ObjectId], *, with_participant: bool,
) -> str:
    session_id = await _seed_session(harness.db, tenant_id=TENANT, owner_id=str(ids[OWNER]))
    if with_participant:
        await SessionParticipantsRepository(harness.db).add(
            tenant_id=TENANT, conversation_id=session_id, user_id=str(ids[PARTICIPANT]),
        )
    await _seed_binding(
        harness.db, tenant_id=TENANT, owner_id=str(ids[OWNER]), session_id=session_id,
        execution_location="desktop", device_id="dev-1", profile_version="rp-1", runtime_id="rt-1",
    )
    return session_id


def _rebind(harness: Any, conversation_id: str, *, runtime_id: str = "rt-new") -> Any:
    return harness.run(dsh_chat.desktop_conversation_runtime_rebind(
        conversation_id,
        dsh_chat.DesktopRuntimeRebindRequest(device_id="dev-1", runtime_id=runtime_id, profile_version="rp-1"),
        "Bearer owner",
    ))


def test_rebind_refuses_while_the_conversation_has_an_active_participant(desktop_thread, monkeypatch) -> None:
    # QA failure (plan todo 17): rebinding a conversation with an active
    # participant to a desktop binding returns 409 session_shared_rebind_blocked
    # and does NOT move the binding. Failing-first: on the unchanged code the
    # endpoint had no guard and returned 200.
    harness = desktop_thread
    ids = {OWNER: ObjectId(), PARTICIPANT: ObjectId()}
    session_id = harness.run(_seed_desktop_conversation(harness, ids, with_participant=True))
    monkeypatch.setattr(dsh_chat, "_resolve_session_user", _identity_seam(ids))

    with pytest.raises(HTTPException) as excinfo:
        _rebind(harness, session_id)

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["code"] == REBIND_BLOCKED
    binding = _current_binding(harness, session_id)
    assert binding["runtime_id"] == "rt-1"


def test_rebind_solo_owner_session_behaves_as_today(desktop_thread, monkeypatch) -> None:
    # Characterization: a single-owner conversation (no participants) rebinds
    # as today — 200 and the binding's runtime_id is updated in the DB.
    harness = desktop_thread
    ids = {OWNER: ObjectId(), PARTICIPANT: ObjectId()}
    session_id = harness.run(_seed_desktop_conversation(harness, ids, with_participant=False))
    monkeypatch.setattr(dsh_chat, "_resolve_session_user", _identity_seam(ids))

    response = _rebind(harness, session_id)

    assert response.code == 0
    assert response.data == {"runtime_id": "rt-new"}
    binding = _current_binding(harness, session_id)
    assert binding["runtime_id"] == "rt-new"


def test_rebind_ignores_removed_participants(desktop_thread, monkeypatch) -> None:
    # The guard is keyed on ACTIVE participants (removed rows grant nothing):
    # a removed participant does not block the rebind.
    harness = desktop_thread
    ids = {OWNER: ObjectId(), PARTICIPANT: ObjectId()}
    session_id = harness.run(_seed_desktop_conversation(harness, ids, with_participant=True))
    harness.run(SessionParticipantsRepository(harness.db).remove(
        session_id, tenant_id=TENANT, user_id=str(ids[PARTICIPANT]),
    ))
    monkeypatch.setattr(dsh_chat, "_resolve_session_user", _identity_seam(ids))

    response = _rebind(harness, session_id)

    assert response.code == 0
    assert response.data == {"runtime_id": "rt-new"}


def test_rebind_unknown_conversation_returns_404(desktop_thread, monkeypatch) -> None:
    # Characterization: a conversation with no binding at all (and no
    # participants, so the guard does not fire) keeps the LookupError -> 404
    # desktop_code_session_not_found mapping.
    harness = desktop_thread
    ids = {OWNER: ObjectId(), PARTICIPANT: ObjectId()}
    monkeypatch.setattr(dsh_chat, "_resolve_session_user", _identity_seam(ids))

    with pytest.raises(HTTPException) as excinfo:
        _rebind(harness, str(ObjectId()))

    assert excinfo.value.status_code == 404


def test_rebind_malformed_conversation_id_returns_404_not_500(desktop_thread, monkeypatch) -> None:
    # New input parsing (adversarial): a malformed conversation id never
    # reaches an ObjectId conversion — the guard finds no rows and the
    # binding resolution misses, so the clean 404 stands.
    harness = desktop_thread
    ids = {OWNER: ObjectId(), PARTICIPANT: ObjectId()}
    monkeypatch.setattr(dsh_chat, "_resolve_session_user", _identity_seam(ids))

    with pytest.raises(HTTPException) as excinfo:
        _rebind(harness, "not-an-objectid")

    assert excinfo.value.status_code == 404


# ---------------------------------------------------------------------------
# The non-server ValueError -> 400 mapping (dsh_chat.py)
# ---------------------------------------------------------------------------


async def _seed_quota(harness: Any) -> None:
    # The personal-space path: remaining = total_points - used_points > 0, so
    # assert_quota_available passes and the turn reaches prepare_turn.
    await harness.db.organizations.insert_one({
        "main_id": TENANT, "total_points": 1000, "used_points": 0,
    })


def _completions(harness: Any, token: str, session_id: str) -> Any:
    # The completions endpoint targets an existing conversation through
    # output_spec's session_id (dsh_chat.py:196) — without it prepare_turn
    # takes the new-conversation branch.
    request = dsh_chat.ChatRequest(
        messages=[dsh_chat.Message(role="user", content="turn")],
        output_spec={"session_id": session_id},
    )
    return harness.run(dsh_chat.chat_completions(request, f"Bearer {token}"))


def test_participant_turn_on_desktop_binding_returns_400_not_500(desktop_thread, monkeypatch) -> None:
    # Consequence wording (plan todo 17): a participant's turn on a non-server
    # binding raises ValueError, mapped to 400 by _start_chat_completions'
    # except ValueError — never a 500. The REAL prepare_turn raises the
    # non-server rejection against the real desktop binding.
    harness = desktop_thread
    ids = {OWNER: ObjectId(), PARTICIPANT: ObjectId()}
    session_id = harness.run(_seed_desktop_conversation(harness, ids, with_participant=True))
    harness.run(_seed_quota(harness))
    monkeypatch.setattr(dsh_chat, "_resolve_session_user", _identity_seam(ids))

    with pytest.raises(HTTPException) as excinfo:
        _completions(harness, PARTICIPANT, session_id)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "this Code task must continue on its bound desktop Runtime"


def test_owner_turn_on_desktop_binding_maps_to_400_too(desktop_thread, monkeypatch) -> None:
    # Characterization: the same mapping holds for the owner's turn on a
    # desktop-bound conversation (the pre-existing desktop path).
    harness = desktop_thread
    ids = {OWNER: ObjectId(), PARTICIPANT: ObjectId()}
    session_id = harness.run(_seed_desktop_conversation(harness, ids, with_participant=False))
    harness.run(_seed_quota(harness))
    monkeypatch.setattr(dsh_chat, "_resolve_session_user", _identity_seam(ids))

    with pytest.raises(HTTPException) as excinfo:
        _completions(harness, OWNER, session_id)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "this Code task must continue on its bound desktop Runtime"
