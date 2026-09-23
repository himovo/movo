# allow: SIZE_OK — cohesive pinned matrix over one seam (the run initiator:
# the active_run claim, the claimed turn's metadata, and the session payload),
# pinned to the frozen plan's todo-14 QA rows; mirrors T04/T07-T13's pinned
# single-file matrices.
"""Plan todo 14 — the run initiator is recorded and exposed.

``active_run`` gains ``initiator_user_id`` (the run starter — the caller of
``mark_active_run``); the claimed turn's ``turn_metadata`` (server-built in
``prepare_turn``, stored verbatim by ``claim_turn``'s dict passthrough)
carries the same value; both are exposed in the session payload (the raw
``active_run`` passthrough in ``_serialize_session`` /
``_serialize_session_summary``, carried by ``SessionSummary``'s declared
``active_run`` dict field). A run with no recorded initiator means "unknown"
and cancel/approve fail closed (todo 15/16 consume this; the approval stamp
at ``tools/service.py`` already prefers ``turn_metadata.get
("initiator_user_id")`` — the metadata threading here closes that loop).

TDD phases recorded in this module:
- baseline characterization passed on the UNCHANGED code (the turn metadata
  carries language/locale only; ``active_run`` has no initiator field),
- failing-first proofs (RED) for the recorded initiator on participant- and
  owner-started runs, the metadata threading, the payload exposure and the
  suspend preservation,
- fail-closed pins that pass on BOTH the unchanged and the todo-14 code (the
  unknown state is never fabricated and a non-owner cancel attempt is denied).

The turn runner is faked as a NO-OP that never finalizes, so the
``active_run`` claim and the binding's ``active_turn`` stay mid-run for the
assertions — the real finalizer would clear both at terminal.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from bson import ObjectId

from app.api.endpoints import sessions
from app.dsh_runtime import chat_service as chat_service_module
from app.dsh_runtime.bindings.repository import KernelBindingRepository
from app.dsh_runtime.chat_service import DshChatService
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.conversation.participants_repository import (
    SessionParticipantsRepository,
)
from app.dsh_runtime.contracts import CreateRuntimeRequest, CreateSessionRequest
from app.dsh_runtime.events import KernelEventRepository
from app.dsh_runtime.profile.models import RuntimeProfileSnapshot
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator

TENANT = "tenant-run-initiator"

OWNER = "owner"
PARTICIPANT = "participant"


# ---------------------------------------------------------------------------
# Fakes — the narrowest seams (T13's shapes). No HTTP, no sleeps.
# ---------------------------------------------------------------------------


class _FakeRuntime:
    def __init__(self, runtime_id: str) -> None:
        self.runtime_id = runtime_id
        self.kernel_version = "test-kernel"


class _FakeGateway:
    """In-memory DSH gateway fake at the kernel-session seams: the same
    profile version resolves to the same runtime (production discovery
    parity), so restore() re-attaches instead of migrating."""

    def __init__(self) -> None:
        self._runtimes: dict[str, _FakeRuntime] = {}
        self._session_count = 0

    async def discover_runtime(self, *, tenant_id: str, profile_version: str, isolation_key: str):
        return self._runtimes.get(isolation_key)

    async def create_runtime(self, request: CreateRuntimeRequest):
        runtime = _FakeRuntime(f"rt-{len(self._runtimes) + 1}")
        self._runtimes[request.isolation_key] = runtime
        return runtime

    async def create_session(self, request: CreateSessionRequest):
        self._session_count += 1
        return SimpleNamespace(session_id=f"ks-{self._session_count}")

    def attach_session(self, **kwargs: Any) -> None:
        return None

    async def resume_session(self, session_id: str) -> None:
        return None

    async def dispose_session(self, session_id: str) -> None:
        return None


class _SpeakerProfiles:
    """``RuntimeProfilePublisher`` fake mirroring the real compiler's identity
    rule (``profile/compiler.py:46,67-71``): the snapshot is compiled per
    (subject, model) and a different speaker or model yields a different
    ``profile_version``. ``None`` resolves to the tenant default model, like
    ``MongoModelCatalog._default_instance`` (``profile/catalog.py:45-49``).
    """

    DEFAULT_MODEL = "model-default"

    def __init__(self) -> None:
        self._snapshots: dict[str, RuntimeProfileSnapshot] = {}

    def _snapshot(self, tenant_id: str, user_id: str, model_instance_id: str) -> RuntimeProfileSnapshot:
        return RuntimeProfileSnapshot(
            profile_version=f"rp-{user_id}-{model_instance_id}",
            content_hash="0" * 64,
            tenant_id=tenant_id,
            subject_user_id=user_id,
            model_source_tenant_id=tenant_id,
            model_instance_id=model_instance_id,
            provider_id="provider-1",
            provider_type="openai_compatible",
            provider_name="Provider",
            model_name="Model",
            display_name="Model",
            capabilities=(),
        )

    async def compile_model_profile(self, *, tenant_id: str, user_id: str, model_instance_id: str | None):
        resolved = model_instance_id or self.DEFAULT_MODEL
        snapshot = self._snapshot(tenant_id, user_id, resolved)
        self._snapshots[snapshot.profile_version] = snapshot
        return snapshot

    async def publish_model_profile(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        user_id: str = "",
        model_instance_id: str | None = None,
        activate: bool = True,
    ):
        snapshot = await self.compile_model_profile(
            tenant_id=tenant_id, user_id=user_id, model_instance_id=model_instance_id,
        )
        self._snapshots[snapshot.profile_version] = snapshot
        return snapshot

    async def publish_snapshot(self, snapshot, *, actor_id: str, activate: bool = False):
        self._snapshots[snapshot.profile_version] = snapshot
        return snapshot

    async def get(self, profile_version: str) -> RuntimeProfileSnapshot:
        snapshot = self._snapshots.get(profile_version)
        if snapshot is None:
            snapshot = self._snapshot(TENANT, "", self.DEFAULT_MODEL).model_copy(
                update={"profile_version": profile_version},
            )
        return snapshot


# ---------------------------------------------------------------------------
# Fixture — production write paths only
# ---------------------------------------------------------------------------


@pytest.fixture
def initiator_thread(real_mongo_db, monkeypatch):
    """A never-bound shared session (owner + one active participant), real
    repositories, the fake gateway at the kernel-session seams, and the REAL
    DshChatService whose turn runner is a NO-OP: it never finalizes, so the
    ``active_run`` claim and the binding's ``active_turn`` stay mid-run for
    the initiator assertions.

    The ``get_db`` seam is patched with ``raising=False`` (T7's gotcha) so the
    module runs on the unchanged and the todo-14 code alike.
    """
    harness = real_mongo_db
    harness.run(SessionParticipantsRepository(harness.db).ensure_indexes())
    harness.run(KernelBindingRepository(harness.db).ensure_indexes())
    monkeypatch.setattr(chat_service_module, "get_db", lambda: harness.db, raising=False)

    ids = {OWNER: ObjectId(), PARTICIPANT: ObjectId()}
    session_oid = ObjectId()
    now = datetime.utcnow()
    harness.run(
        harness.db.chat_sessions.insert_one(
            {
                "_id": session_oid,
                "user_id": str(ids[OWNER]),
                "main_id": TENANT,
                "title": "Shared chat",
                "created_at": now,
                "updated_at": now,
            }
        )
    )
    harness.run(
        SessionParticipantsRepository(harness.db).add(
            tenant_id=TENANT, conversation_id=str(session_oid), user_id=str(ids[PARTICIPANT]),
        )
    )

    gateway = _FakeGateway()
    chat = DshChatService(
        gateway=gateway,
        coordinator=RuntimeCoordinator(gateway, KernelBindingRepository(harness.db)),
        conversations=ConversationRepository(harness.db),
        bindings=KernelBindingRepository(harness.db),
        events=KernelEventRepository(harness.db),
        profiles=_SpeakerProfiles(),
        kernel_version="test-kernel",
    )

    async def _no_op_run(*args: Any, **kwargs: Any) -> str:
        # NO-OP turn runner: never finalizes — the active_run claim and the
        # binding's active_turn stay mid-run for the assertions.
        return "completed"

    chat._turn_runner.run = _no_op_run
    return harness, ids, session_oid, gateway, chat


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _send(chat, harness, session_oid, *, user_id, model_instance_id=None):
    """One turn through the REAL prepare_turn, waited to completion."""
    turn = harness.run(
        chat.prepare_turn(
            tenant_id=TENANT,
            user_id=user_id,
            conversation_id=str(session_oid),
            text="turn",
            model_instance_id=model_instance_id,
            timezone_name="UTC",
            images=[],
            documents=[],
        )
    )
    outcome = harness.run(chat.wait_turn(turn.message_id))
    return turn, outcome


def _current_binding(harness, session_oid):
    async def _one():
        return await harness.db.agent_kernel_bindings.find_one(
            {"conversation_id": str(session_oid), "current": True}
        )

    return harness.run(_one())


def _session_row(harness, session_oid):
    async def _one():
        return await harness.db.chat_sessions.find_one({"_id": session_oid})

    return harness.run(_one())


def _payload_seams(monkeypatch, harness, viewer_id: str) -> None:
    """get_db + _resolve_session_user patched at the sessions module seam
    (T8/T9's pattern); the viewer resolves from the fake identity."""
    async def _identity(_authorization: str | None) -> dict[str, Any]:
        return {"user": {"_id": viewer_id}, "main_id": TENANT}

    monkeypatch.setattr(sessions, "get_db", lambda: harness.db)
    monkeypatch.setattr(sessions, "_resolve_session_user", _identity)


def _get_session(harness, session_oid, *, viewer_id: str) -> dict[str, Any]:
    """The REAL get_session handler, driven directly — every Query-defaulted
    parameter passed explicitly (T8's gotcha)."""
    response = harness.run(
        sessions.get_session(
            str(session_oid),
            user_id=viewer_id,
            main_id=TENANT,
            main_id_snake=None,
            include_context_summary=False,
            authorization=None,
        )
    )
    assert response.code == 0
    return response.data


def _seed_legacy_run(harness, session_oid: ObjectId) -> None:
    """A pre-todo-14 active_run claim (no initiator_user_id — the legacy
    shape mark_active_run wrote before the field existed)."""
    now = datetime.utcnow()
    harness.run(
        harness.db.chat_sessions.update_one(
            {"_id": session_oid},
            {"$set": {
                "active_run": {
                    "run_id": "run-legacy",
                    "message_id": "msg-legacy",
                    "source": "dsh",
                    "status": "running",
                    "started_at": now,
                },
            }},
        )
    )


# ---------------------------------------------------------------------------
# Fail-closed pins (pass on BOTH the unchanged and the todo-14 code)
# ---------------------------------------------------------------------------


def test_claim_turn_stores_unknown_metadata_verbatim_without_fabrication(real_mongo_db):
    # Fail-closed pin: claim_turn stores the caller's turn_metadata verbatim —
    # the desktop claim path (desktop_binding.py:152) passes
    # {"source": "desktop_dsh_code"} with NO initiator, and the stored
    # metadata stays unknown (never fabricated). Passes on both the unchanged
    # and the todo-14 code.
    harness = real_mongo_db
    bindings = KernelBindingRepository(harness.db)
    harness.run(bindings.ensure_indexes())
    created = harness.run(bindings.create(
        tenant_id=TENANT,
        user_id="user-desktop",
        conversation_id=str(ObjectId()),
        kernel_session_id="ks-claim-test",
        runtime_id="rt-claim-test",
        profile_version="rp-desktop",
        model_instance_id="model-x",
        kernel_version="test-kernel",
    ))

    claimed = harness.run(bindings.claim_turn(
        created["binding_id"], message_id="msg-x", request_id="turn-x",
        turn_metadata={"source": "desktop_dsh_code"},
    ))

    assert claimed is not None
    assert claimed["active_turn"]["turn_metadata"] == {"source": "desktop_dsh_code"}


def test_payload_does_not_fabricate_an_initiator_for_a_legacy_run(real_mongo_db, monkeypatch):
    # Fail-closed pin: a legacy active_run (hand-seeded without
    # initiator_user_id) is exposed WITHOUT an initiator — the payload never
    # fabricates one, so "unknown" stays unknown for todo 15/16's fail-closed
    # consumption. Passes on both the unchanged and the todo-14 code.
    harness = real_mongo_db
    session_oid = ObjectId()
    now = datetime.utcnow()
    harness.run(
        harness.db.chat_sessions.insert_one(
            {
                "_id": session_oid,
                "user_id": "user-owner",
                "main_id": TENANT,
                "title": "Legacy chat",
                "created_at": now,
                "updated_at": now,
            }
        )
    )
    _seed_legacy_run(harness, session_oid)
    _payload_seams(monkeypatch, harness, "user-owner")

    data = _get_session(harness, session_oid, viewer_id="user-owner")

    assert data["active_run"]["run_id"] == "run-legacy"
    assert data["active_run"]["status"] == "running"
    assert "initiator_user_id" not in data["active_run"]


def test_a_run_without_a_recorded_initiator_denies_a_non_owner_cancel_attempt(real_mongo_db, monkeypatch):
    # Fail-closed pin (the cancel side): a run with NO recorded initiator is
    # never cancelable by another user — today the owner-only gate denies
    # every non-owner (LookupError -> 404 at the endpoint) and the active_run
    # claim stays intact (the run keeps running). Todo 15 replaces the gate
    # with the membership + initiator-identity check; this scenario must stay
    # denied there too (an unknown initiator fails closed).
    harness = real_mongo_db
    session_oid = ObjectId()
    now = datetime.utcnow()
    harness.run(
        harness.db.chat_sessions.insert_one(
            {
                "_id": session_oid,
                "user_id": "user-owner",
                "main_id": TENANT,
                "title": "Legacy chat",
                "created_at": now,
                "updated_at": now,
            }
        )
    )
    _seed_legacy_run(harness, session_oid)
    monkeypatch.setattr(chat_service_module, "get_db", lambda: harness.db, raising=False)
    gateway = _FakeGateway()
    chat = DshChatService(
        gateway=gateway,
        coordinator=RuntimeCoordinator(gateway, KernelBindingRepository(harness.db)),
        conversations=ConversationRepository(harness.db),
        bindings=KernelBindingRepository(harness.db),
        events=KernelEventRepository(harness.db),
        profiles=_SpeakerProfiles(),
        kernel_version="test-kernel",
    )

    with pytest.raises(LookupError):
        harness.run(chat.cancel(str(session_oid), tenant_id=TENANT, user_id="user-other"))

    row = _session_row(harness, session_oid)
    assert row["active_run"]["status"] == "running"
    assert "initiator_user_id" not in row["active_run"]


# ---------------------------------------------------------------------------
# New behaviour (RED on the unchanged code)
# ---------------------------------------------------------------------------


def test_participant_started_run_records_the_participant_in_active_run(initiator_thread):
    # QA happy (plan todo 14): a run started by a participant records the
    # participant. RED on the unchanged code: KeyError 'initiator_user_id'.
    harness, ids, session_oid, _gateway, chat = initiator_thread
    participant_id = str(ids[PARTICIPANT])

    turn, outcome = _send(chat, harness, session_oid, user_id=participant_id, model_instance_id="model-x")
    assert outcome == "completed"

    row = _session_row(harness, session_oid)
    assert row["active_run"]["status"] == "running"
    assert row["active_run"]["initiator_user_id"] == participant_id
    assert row["active_run"]["message_id"] == turn.message_id


def test_owner_started_run_records_the_owner_in_active_run(initiator_thread):
    # QA happy (plan todo 14): an owner-started run records the owner.
    # RED on the unchanged code: KeyError 'initiator_user_id'.
    harness, ids, session_oid, _gateway, chat = initiator_thread
    owner_id = str(ids[OWNER])

    turn, outcome = _send(chat, harness, session_oid, user_id=owner_id, model_instance_id="model-x")
    assert outcome == "completed"

    row = _session_row(harness, session_oid)
    assert row["active_run"]["status"] == "running"
    assert row["active_run"]["initiator_user_id"] == owner_id


def test_claimed_turn_metadata_carries_the_same_initiator(initiator_thread):
    # QA happy (plan todo 14): the claimed turn's metadata carries the SAME
    # value as active_run.initiator_user_id — two different writers record the
    # initiator (prepare_turn's server-built dict stored verbatim by
    # claim_turn; mark_active_run's $set) and cannot drift. RED on the
    # unchanged code: the metadata has no initiator_user_id.
    harness, ids, session_oid, _gateway, chat = initiator_thread
    participant_id = str(ids[PARTICIPANT])

    _turn, outcome = _send(chat, harness, session_oid, user_id=participant_id, model_instance_id="model-x")
    assert outcome == "completed"

    binding = _current_binding(harness, session_oid)
    metadata = binding["active_turn"]["turn_metadata"]
    assert set(metadata.keys()) == {"language", "locale", "initiator_user_id"}
    assert metadata["initiator_user_id"] == participant_id
    row = _session_row(harness, session_oid)
    assert row["active_run"]["initiator_user_id"] == participant_id


def test_suspended_run_preserves_the_recorded_initiator(initiator_thread):
    # The suspend path (turn_runner/turn_recovery -> suspend_active_run) uses
    # a dotted-path update: the recorded initiator_user_id is PRESERVED, not
    # replaced — a suspended run stays attributable to its initiator. RED on
    # the unchanged code: KeyError 'initiator_user_id'.
    harness, ids, session_oid, _gateway, chat = initiator_thread
    participant_id = str(ids[PARTICIPANT])

    turn, outcome = _send(chat, harness, session_oid, user_id=participant_id, model_instance_id="model-x")
    assert outcome == "completed"
    harness.run(
        ConversationRepository(harness.db).suspend_active_run(
            conversation_id=str(session_oid), tenant_id=TENANT, user_id=participant_id,
            message_id=turn.message_id,
            intervention={"suspension_id": "susp-1", "node_id": "node-1", "reason": "approval"},
        )
    )

    row = _session_row(harness, session_oid)
    assert row["active_run"]["status"] == "suspended"
    assert row["active_run"]["initiator_user_id"] == participant_id


def test_session_payload_exposes_the_run_initiator_to_the_member(initiator_thread, monkeypatch):
    # QA happy (plan todo 14): both are exposed in the session payload — the
    # client-visible GET /sessions/{id} (via the raw active_run passthrough in
    # _serialize_session, carried by SessionSummary's declared dict field)
    # reaches a member viewer with the initiator. RED on the unchanged code:
    # KeyError 'initiator_user_id'.
    harness, ids, session_oid, _gateway, chat = initiator_thread
    participant_id = str(ids[PARTICIPANT])

    _turn, outcome = _send(chat, harness, session_oid, user_id=participant_id, model_instance_id="model-x")
    assert outcome == "completed"
    _payload_seams(monkeypatch, harness, participant_id)

    data = _get_session(harness, session_oid, viewer_id=participant_id)

    assert data["access"] == "shared"
    assert data["active_run"]["status"] == "running"
    assert data["active_run"]["initiator_user_id"] == participant_id
