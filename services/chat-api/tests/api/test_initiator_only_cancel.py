# allow: SIZE_OK — cohesive pinned matrix over one seam (the initiator-only
# cancel gate: the coordinator chokepoint + the endpoint's approval-clearing
# call), pinned to the frozen plan's todo-15 QA rows; T04/T07-T14 precedent.
"""Plan todo 15 — cancel is restricted to the run's initiator.

Cancel is allowed ONLY for the run's initiator. Every other member —
including the session owner when they did not initiate that run — is
denied (403 at the endpoint). The initiator source is T14's
``active_run.initiator_user_id`` (``mark_active_run`` records the caller);
a run with NO recorded initiator (a legacy row) FAILS CLOSED. The
membership gate denies a removed participant even for their own in-flight
run — that run simply completes.

TDD phases recorded in this module:
- baseline characterization passed on the UNCHANGED code (the owner-only
  ``owned()`` gate: the owner cancels anything in their session, every
  non-owner gets the LookupError denial),
- failing-first proofs (RED) for the participant-initiator cancel, the
  non-initiator and owner 403 denials, the removed-member denial, the
  legacy fail-closed denial, and the endpoint's approval-clearing call
  never running for a non-initiator,
- the two superseded baseline pins REMOVED when the implementation landed
  (the planned behavior change: a participant canceling their own run is
  now allowed, and the owner's cross-run cancel is now the 403 denial) —
  recorded in T15-failure.txt,
- pins that pass on BOTH the unchanged and the todo-15 code (the
  single-owner happy path, the malformed-id 4xx, the non-member 404
  boundary, the endpoint happy path).

The turn runner is faked as a NO-OP that never finalizes (T14's shape), so
the ``active_run`` claim and the binding's ``active_turn`` stay mid-run for
the denial assertions; the happy-path cancel settles the local runner and
finalizes through the real ``TurnStateFinalizer``.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.api.endpoints import dsh_chat
from app.api.endpoints.dsh_chat import CancelRequest
from app.dsh_runtime import chat_service as chat_service_module
from app.dsh_runtime.application import dsh_runtime_application
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

TENANT = "tenant-initiator-cancel"

OWNER = "owner"
PARTICIPANT = "participant"
SECOND = "second"

INITIATOR_REQUIRED_CODE = "session_cancel_initiator_required"


# ---------------------------------------------------------------------------
# Fakes — the narrowest seams (T13/T14's shapes). No HTTP, no sleeps.
# ---------------------------------------------------------------------------


class _FakeRuntime:
    def __init__(self, runtime_id: str) -> None:
        self.runtime_id = runtime_id
        self.kernel_version = "test-kernel"


class _FakeGateway:
    """In-memory DSH gateway fake at the kernel-session seams: the same
    profile version resolves to the same runtime (production discovery
    parity), so restore() re-attaches instead of migrating. ``cancel``
    records the kernel session it was asked to stop — a non-initiator's
    denial must never reach it."""

    def __init__(self, release: asyncio.Event) -> None:
        self._runtimes: dict[str, _FakeRuntime] = {}
        self._session_count = 0
        self.cancelled_sessions: list[str] = []
        self._release = release

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

    async def cancel(self, request: CancelRequest) -> dict[str, bool]:
        self.cancelled_sessions.append(str(request.session_id))
        # The gateway cancel stops the host: the in-flight local runner is
        # released, mirroring the real disconnect.
        self._release.set()
        return {"turnPending": False, "jobsPending": False}

    async def events_once(self, session_id: str, cursor: int) -> list[dict[str, Any]]:
        return []


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


class _FakeTools:
    """The MOVO tools-service seam at ``cancel_conversation``: records the
    caller so the tests prove the approval-clearing call only ever runs for
    the run's initiator."""

    def __init__(self) -> None:
        self.cancel_calls: list[dict[str, str]] = []

    async def cancel_conversation(
        self, *, tenant_id: str, user_id: str, conversation_id: str
    ) -> int:
        self.cancel_calls.append(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
            }
        )
        return 0


# ---------------------------------------------------------------------------
# Fixture — production write paths only
# ---------------------------------------------------------------------------


@pytest.fixture
def cancellable_thread(real_mongo_db, monkeypatch):
    """A never-bound shared session (owner + two active participants), real
    repositories, the fake gateway at the kernel-session seams, and the REAL
    DshChatService whose turn runner is a NO-OP: it never finalizes, so the
    ``active_run`` claim and the binding's ``active_turn`` stay mid-run for
    the denial assertions.

    The ``get_db`` seam is patched with ``raising=False`` (T7's gotcha) so the
    module runs on the unchanged and the todo-15 code alike.
    """
    harness = real_mongo_db
    harness.run(SessionParticipantsRepository(harness.db).ensure_indexes())
    harness.run(KernelBindingRepository(harness.db).ensure_indexes())
    monkeypatch.setattr(chat_service_module, "get_db", lambda: harness.db, raising=False)

    ids = {OWNER: ObjectId(), PARTICIPANT: ObjectId(), SECOND: ObjectId()}
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
    for name in (PARTICIPANT, SECOND):
        harness.run(
            SessionParticipantsRepository(harness.db).add(
                tenant_id=TENANT, conversation_id=str(session_oid), user_id=str(ids[name]),
            )
        )

    release = asyncio.Event()
    gateway = _FakeGateway(release)
    chat = DshChatService(
        gateway=gateway,
        coordinator=RuntimeCoordinator(gateway, KernelBindingRepository(harness.db)),
        conversations=ConversationRepository(harness.db),
        bindings=KernelBindingRepository(harness.db),
        events=KernelEventRepository(harness.db),
        profiles=_SpeakerProfiles(),
        kernel_version="test-kernel",
    )

    async def _gated_run(*args: Any, **kwargs: Any) -> str:
        # The run stays in flight until released: the fake gateway's cancel
        # releases it (the initiator's happy path) and the tests' _drain
        # releases it (the denial cleanup). It never finalizes - the claims
        # stay mid-run until the cancel's real finalizer or the tests'
        # explicit completion drive them to terminal.
        await release.wait()
        return "completed"

    chat._turn_runner.run = _gated_run
    tools = _FakeTools()
    return harness, ids, session_oid, gateway, chat, tools, release


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _start_run(chat, harness, session_oid, *, user_id):
    """One turn through the REAL prepare_turn, left IN FLIGHT: the runner
    task stays pending and the claims stay mid-run."""
    return harness.run(
        chat.prepare_turn(
            tenant_id=TENANT,
            user_id=user_id,
            conversation_id=str(session_oid),
            text="turn",
            model_instance_id="model-x",
            timezone_name="UTC",
            images=[],
            documents=[],
        )
    )


def _drain(chat, harness, message_id: str, release: asyncio.Event) -> str:
    """Release the in-flight runner and drain the task (T14's cleanup
    pattern) — it never finalizes, so the claims stay mid-run afterwards."""
    release.set()
    return harness.run(chat.wait_turn(message_id))


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


def _endpoint_seams(monkeypatch, harness, ids: dict[str, str], chat, tools) -> None:
    """The endpoint seams (T7's pattern): the bearer-token-dispatching
    identity, the get_db seam, and the singletons swapped for the REAL
    DshChatService (the coordinator cancel) and the recording tools fake."""
    tokens = {f"bearer-{name}": oid for name, oid in ids.items()}

    async def resolve(authorization: str | None):
        token = str(authorization or "").removeprefix("Bearer ").strip()
        oid = tokens.get(token)
        if oid is None:
            raise LookupError(f"no seeded end-user for bearer token {token!r}")
        return {"user": {"_id": oid, "status": "active"}, "main_id": TENANT}

    monkeypatch.setattr(dsh_chat, "_resolve_session_user", resolve)
    monkeypatch.setattr(dsh_chat, "get_db", lambda: harness.db)
    monkeypatch.setattr(dsh_runtime_application, "chat", chat)
    monkeypatch.setattr(dsh_runtime_application, "tools", tools)


def _call_cancel(session_oid, token: str):
    return dsh_chat.chat_cancel(
        CancelRequest(session_id=str(session_oid)), authorization=token
    )


# ---------------------------------------------------------------------------
# Baseline characterization (passes on the UNCHANGED code)
# ---------------------------------------------------------------------------


def test_characterization_owner_cancels_their_own_run_and_it_terminates(cancellable_thread):
    # The single-owner happy path (plan todo 15: single-owner sessions are
    # unaffected - the owner is always the initiator of their own runs).
    # Passes on BOTH the unchanged and the todo-15 code.
    harness, ids, session_oid, gateway, chat, _tools, release = cancellable_thread
    owner_id = str(ids[OWNER])
    _start_run(chat, harness, session_oid, user_id=owner_id)

    cancelled = harness.run(chat.cancel(str(session_oid), tenant_id=TENANT, user_id=owner_id))

    assert cancelled is True
    row = _session_row(harness, session_oid)
    assert "active_run" not in row
    binding = _current_binding(harness, session_oid)
    assert binding["active_turn"]["status"] == "cancelled"
    assert gateway.cancelled_sessions == [str(binding["kernel_session_id"])]


def test_characterization_malformed_session_id_is_a_clean_4xx(cancellable_thread):
    # A malformed conversation id never converts with ObjectId - the
    # is_valid guard raises LookupError (-> 404 at the endpoint), never a
    # 500 InvalidId. Passes on BOTH the unchanged and the todo-15 code.
    harness, ids, session_oid, gateway, chat, _tools, release = cancellable_thread

    with pytest.raises(LookupError):
        harness.run(chat.cancel("not-an-objectid", tenant_id=TENANT, user_id=str(ids[OWNER])))

    assert gateway.cancelled_sessions == []


# ---------------------------------------------------------------------------
# The initiator-only contract (RED on the unchanged code)
# ---------------------------------------------------------------------------


def test_a_participant_who_initiated_can_cancel_their_run(cancellable_thread):
    # QA happy (plan todo 15): a participant who initiated a run can cancel
    # it too. RED on the unchanged code: the owner-only owned() gate denies
    # every non-owner (LookupError).
    harness, ids, session_oid, gateway, chat, _tools, release = cancellable_thread
    participant_id = str(ids[PARTICIPANT])
    _start_run(chat, harness, session_oid, user_id=participant_id)

    cancelled = harness.run(chat.cancel(str(session_oid), tenant_id=TENANT, user_id=participant_id))

    assert cancelled is True
    row = _session_row(harness, session_oid)
    assert "active_run" not in row
    binding = _current_binding(harness, session_oid)
    assert binding["active_turn"]["status"] == "cancelled"
    assert gateway.cancelled_sessions == [str(binding["kernel_session_id"])]


def test_a_non_initiator_participant_receives_403_and_the_run_keeps_running(cancellable_thread):
    # QA failure (plan todo 15): a non-initiator participant receives the 403
    # denial and the run keeps running. RED on the unchanged code: the
    # owner-only gate raises LookupError instead of the initiator denial.
    harness, ids, session_oid, gateway, chat, _tools, release = cancellable_thread
    participant_id = str(ids[PARTICIPANT])
    second_id = str(ids[SECOND])
    turn = _start_run(chat, harness, session_oid, user_id=participant_id)

    with pytest.raises(PermissionError) as excinfo:
        harness.run(chat.cancel(str(session_oid), tenant_id=TENANT, user_id=second_id))

    assert excinfo.value.code == INITIATOR_REQUIRED_CODE
    row = _session_row(harness, session_oid)
    assert row["active_run"]["status"] == "running"
    assert row["active_run"]["initiator_user_id"] == participant_id
    binding = _current_binding(harness, session_oid)
    assert binding["active_turn"]["status"] == "running"
    assert gateway.cancelled_sessions == []
    _drain(chat, harness, turn.message_id, release)


def test_the_session_owner_who_did_not_initiate_receives_403(cancellable_thread):
    # QA failure (plan todo 15): the session owner who did not initiate the
    # run also receives the 403 denial. RED on the unchanged code: owned()
    # passes for the owner and the cancel proceeds (DID NOT RAISE).
    harness, ids, session_oid, gateway, chat, _tools, release = cancellable_thread
    participant_id = str(ids[PARTICIPANT])
    owner_id = str(ids[OWNER])
    turn = _start_run(chat, harness, session_oid, user_id=participant_id)

    with pytest.raises(PermissionError) as excinfo:
        harness.run(chat.cancel(str(session_oid), tenant_id=TENANT, user_id=owner_id))

    assert excinfo.value.code == INITIATOR_REQUIRED_CODE
    row = _session_row(harness, session_oid)
    assert row["active_run"]["status"] == "running"
    assert row["active_run"]["initiator_user_id"] == participant_id
    assert gateway.cancelled_sessions == []
    _drain(chat, harness, turn.message_id, release)


def test_a_participant_removed_mid_run_cannot_cancel_their_own_run(cancellable_thread):
    # QA failure (plan todo 15): a participant removed while their own run is
    # in flight cannot cancel it - the membership gate denies them (403)
    # even though they initiated it - and the run simply completes. RED on
    # the unchanged code: the owner-only gate raises LookupError.
    harness, ids, session_oid, gateway, chat, _tools, release = cancellable_thread
    participant_id = str(ids[PARTICIPANT])
    turn = _start_run(chat, harness, session_oid, user_id=participant_id)
    harness.run(
        SessionParticipantsRepository(harness.db).remove(
            conversation_id=str(session_oid), tenant_id=TENANT, user_id=participant_id,
        )
    )

    with pytest.raises(PermissionError) as excinfo:
        harness.run(chat.cancel(str(session_oid), tenant_id=TENANT, user_id=participant_id))

    assert excinfo.value.code == INITIATOR_REQUIRED_CODE
    row = _session_row(harness, session_oid)
    assert row["active_run"]["status"] == "running"
    assert gateway.cancelled_sessions == []
    _drain(chat, harness, turn.message_id, release)
    # The run simply completes: the normal completion path still works after
    # the removal (the removal neither aborts nor wedges the run).
    binding = _current_binding(harness, session_oid)
    harness.run(
        chat._finalizer.finalize(
            binding=binding, message_id=turn.message_id, status="completed"
        )
    )
    row = _session_row(harness, session_oid)
    assert "active_run" not in row


def test_a_legacy_run_without_a_recorded_initiator_fails_closed(cancellable_thread):
    # Fail-closed pin (plan todo 15 + T14's handoff): a run with NO recorded
    # initiator is denied for EVERY member - the owner included, even though
    # they pass the membership gate - because the initiator is unknown.
    # T14's own pin keeps the non-owner LookupError form; this pins the
    # member-side fail-closed denial. RED on the unchanged code: owned()
    # passes for the owner and the cancel proceeds (DID NOT RAISE).
    harness, ids, session_oid, gateway, chat, _tools, release = cancellable_thread
    owner_id = str(ids[OWNER])
    participant_id = str(ids[PARTICIPANT])
    _seed_legacy_run(harness, session_oid)

    with pytest.raises(PermissionError) as excinfo:
        harness.run(chat.cancel(str(session_oid), tenant_id=TENANT, user_id=owner_id))
    assert excinfo.value.code == INITIATOR_REQUIRED_CODE

    with pytest.raises(PermissionError):
        harness.run(chat.cancel(str(session_oid), tenant_id=TENANT, user_id=participant_id))

    row = _session_row(harness, session_oid)
    assert row["active_run"]["status"] == "running"
    assert "initiator_user_id" not in row["active_run"]
    assert gateway.cancelled_sessions == []


def test_a_non_member_cannot_cancel_a_session(cancellable_thread):
    # The 404 boundary of the new gate (passes on BOTH the unchanged and the
    # todo-15 code): a never-a-member keeps the LookupError denial (cannot
    # see, todo 4's status matrix; T14's fail-closed pin relies on it).
    harness, ids, session_oid, gateway, chat, _tools, release = cancellable_thread
    turn = _start_run(chat, harness, session_oid, user_id=str(ids[PARTICIPANT]))

    with pytest.raises(LookupError):
        harness.run(chat.cancel(str(session_oid), tenant_id=TENANT, user_id="user-other"))

    row = _session_row(harness, session_oid)
    assert row["active_run"]["status"] == "running"
    _drain(chat, harness, turn.message_id, release)


# ---------------------------------------------------------------------------
# The endpoint surface (POST /chat/cancel)
# ---------------------------------------------------------------------------


def test_the_initiator_cancels_via_the_endpoint(cancellable_thread, monkeypatch):
    # The endpoint happy path (passes on BOTH the unchanged and the todo-15
    # code): the initiator's cancel returns code=0, the approval-clearing
    # call runs for them, and the run terminates.
    harness, ids, session_oid, gateway, chat, tools, release = cancellable_thread
    owner_id = str(ids[OWNER])
    _start_run(chat, harness, session_oid, user_id=owner_id)
    _endpoint_seams(monkeypatch, harness, ids, chat, tools)

    response = harness.run(_call_cancel(session_oid, "Bearer bearer-owner"))

    assert response.code == 0
    assert tools.cancel_calls == [
        {"tenant_id": TENANT, "user_id": owner_id, "conversation_id": str(session_oid)}
    ]
    row = _session_row(harness, session_oid)
    assert "active_run" not in row
    binding = _current_binding(harness, session_oid)
    assert binding["active_turn"]["status"] == "cancelled"


def test_the_endpoint_denies_a_non_initiator_participant_with_403_before_the_approval_clearing_call(cancellable_thread, monkeypatch):
    # The approval-clearing call is treated the same way (plan todo 15): the
    # initiator-only gate fires BEFORE require_tools().cancel_conversation -
    # a non-initiator participant never reaches it, and the denial is a 403
    # with the stable code. RED on the unchanged code: the endpoint proceeds
    # (the approval-clearing call runs) and the LookupError maps to 404.
    harness, ids, session_oid, gateway, chat, tools, release = cancellable_thread
    participant_id = str(ids[PARTICIPANT])
    turn = _start_run(chat, harness, session_oid, user_id=participant_id)
    _endpoint_seams(monkeypatch, harness, ids, chat, tools)

    with pytest.raises(HTTPException) as excinfo:
        harness.run(_call_cancel(session_oid, "Bearer bearer-second"))

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail["code"] == INITIATOR_REQUIRED_CODE
    assert tools.cancel_calls == []
    row = _session_row(harness, session_oid)
    assert row["active_run"]["status"] == "running"
    _drain(chat, harness, turn.message_id, release)


def test_the_endpoint_denies_the_owner_with_403_before_the_approval_clearing_call(cancellable_thread, monkeypatch):
    # The headline case (plan todo 15): the session owner who did not
    # initiate that run receives 403, and the approval-clearing call never
    # runs for them. RED on the unchanged code: the owner proceeds and the
    # cancel succeeds (DID NOT RAISE).
    harness, ids, session_oid, gateway, chat, tools, release = cancellable_thread
    participant_id = str(ids[PARTICIPANT])
    turn = _start_run(chat, harness, session_oid, user_id=participant_id)
    _endpoint_seams(monkeypatch, harness, ids, chat, tools)

    with pytest.raises(HTTPException) as excinfo:
        harness.run(_call_cancel(session_oid, "Bearer bearer-owner"))

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail["code"] == INITIATOR_REQUIRED_CODE
    assert tools.cancel_calls == []
    row = _session_row(harness, session_oid)
    assert row["active_run"]["status"] == "running"
    _drain(chat, harness, turn.message_id, release)


def test_the_endpoint_denies_a_removed_member_with_403(cancellable_thread, monkeypatch):
    # The membership gate denies a removed member (plan todo 15): the removed
    # participant cannot cancel their own in-flight run - 403, and the
    # approval-clearing call never runs for them. RED on the unchanged code:
    # the endpoint proceeds (the approval-clearing call runs) and maps the
    # owner-only LookupError to 404.
    harness, ids, session_oid, gateway, chat, tools, release = cancellable_thread
    participant_id = str(ids[PARTICIPANT])
    turn = _start_run(chat, harness, session_oid, user_id=participant_id)
    harness.run(
        SessionParticipantsRepository(harness.db).remove(
            conversation_id=str(session_oid), tenant_id=TENANT, user_id=participant_id,
        )
    )
    _endpoint_seams(monkeypatch, harness, ids, chat, tools)

    with pytest.raises(HTTPException) as excinfo:
        harness.run(_call_cancel(session_oid, "Bearer bearer-participant"))

    assert excinfo.value.status_code == 403
    assert tools.cancel_calls == []
    row = _session_row(harness, session_oid)
    assert row["active_run"]["status"] == "running"
    _drain(chat, harness, turn.message_id, release)


def test_the_endpoint_maps_a_malformed_session_id_to_404(cancellable_thread, monkeypatch):
    # A malformed session id gets a clean 404 (a 4xx, never a 500), and the
    # approval-clearing call never runs for it. The 404 status passes on
    # BOTH the unchanged and the todo-15 code; the approval-clearing-call
    # assertion is the todo-15 addition.
    harness, ids, session_oid, gateway, chat, tools, release = cancellable_thread
    _endpoint_seams(monkeypatch, harness, ids, chat, tools)

    with pytest.raises(HTTPException) as excinfo:
        harness.run(_call_cancel("not-an-objectid", "Bearer bearer-owner"))

    assert excinfo.value.status_code == 404
    assert tools.cancel_calls == []
