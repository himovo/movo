# allow: SIZE_OK — one cohesive seam (the conversation-scoped shared binding:
# admission, the no-current-binding race, and rotation to the speaker), pinned
# to the frozen plan's todo-13 QA matrix; mirrors T04/T07/T08/T09/T10/T11/T12's
# pinned single-file matrices.
"""Plan todo 13 — the current binding is conversation-scoped, participants are
admitted at the DSH turn admission, and the binding rotates to the speaker.

R1=A: one ``agent_kernel_bindings`` current binding per conversation (the
partial unique index stays untouched); every member resolves the SAME binding;
a different speaker always rotates (``subject_user_id`` is inside the hashed
profile payload, so a different speaker always has a different
``profile_version``) and the successor kernel session is seeded from the
predecessor so conversation context survives.

Q11 pinning [review-3]: the predecessor's-model restriction applies only when
the conversation has another active member — a no-explicit-model turn resolves
to the speaker's own effective default (the tenant catalog default; no
user-level default model exists), never the predecessor's ``previous_model_id``
or the inherited ``preset_id``. For a solo-owner conversation today's fallback
is preserved (it is how a solo user's model choice survives a client reload).

TDD phases recorded in this module:
- baseline characterization passed on the UNCHANGED code (the index shape, the
  owner's first turn, the solo-owner fallback, the replacement-conflict
  conversion),
- failing-first proofs (RED) for the conversation-scoped ``current()``, the
  participant admission, the speaker rotation with the Q11 resolution and the
  no-current-binding race,
- the green run after the implementation.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from bson import ObjectId

from app.dsh_runtime import chat_service as chat_service_module
from app.dsh_runtime.bindings.repository import (
    BindingReplacementConflict,
    KernelBindingRepository,
)
from app.dsh_runtime.chat_service import ConversationBusyError, DshChatService
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.conversation.participants_repository import (
    SessionParticipantsRepository,
)
from app.dsh_runtime.contracts import CreateRuntimeRequest, CreateSessionRequest
from app.dsh_runtime.events import KernelEventRepository
from app.dsh_runtime.profile.models import RuntimeProfileSnapshot
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator

TENANT = "tenant-shared-binding-rotation"

OWNER = "owner"
PARTICIPANT = "participant"


# ---------------------------------------------------------------------------
# Fakes — the narrowest seams (T7/T12's pattern). The gateway wraps an HTTP
# transport to the DSH Runtime Host (unrunnable in tests); the fake records
# the kernel-session work so the tests can assert the successor's seed and
# the disposal invariants against durable state. No HTTP, no sleeps.
# ---------------------------------------------------------------------------


class _FakeRuntime:
    def __init__(self, runtime_id: str) -> None:
        self.runtime_id = runtime_id
        self.kernel_version = "test-kernel"


class _FakeGateway:
    """In-memory DSH gateway fake at the kernel-session seams.

    ``create_session`` records every ``CreateSessionRequest`` (so the tests
    can assert the successor's spec carries the predecessor's exported seed
    and the speaker's identity) and ``dispose_session`` records the cleanup
    the coordinator performs for the DuplicateKeyError race loser and the
    synchronizer's rotation.
    """

    def __init__(self) -> None:
        self.created_sessions: list[tuple[CreateSessionRequest, str]] = []
        self.disposed_sessions: list[str] = []
        self.cancelled: list[str] = []
        self._runtimes: dict[str, _FakeRuntime] = {}

    async def discover_runtime(self, *, tenant_id: str, profile_version: str, isolation_key: str):
        # Mirrors production discovery: the same profile version resolves to
        # the same runtime, so restore() re-attaches the predecessor to the
        # runtime it already lives on instead of migrating it.
        return self._runtimes.get(isolation_key)

    async def create_runtime(self, request: CreateRuntimeRequest):
        runtime = _FakeRuntime(f"rt-{len(self._runtimes) + 1}")
        self._runtimes[request.isolation_key] = runtime
        return runtime

    async def create_session(self, request: CreateSessionRequest):
        session_id = f"ks-{len(self.created_sessions) + 1}"
        self.created_sessions.append((request, session_id))
        return SimpleNamespace(session_id=session_id)

    def attach_session(self, **kwargs: Any) -> None:
        return None

    async def resume_session(self, session_id: str) -> None:
        return None

    async def dispose_session(self, session_id: str) -> None:
        self.disposed_sessions.append(str(session_id))

    async def cancel(self, request) -> dict[str, Any]:
        self.cancelled.append(str(request.session_id))
        return {"ok": True}


class _SpeakerProfiles:
    """``RuntimeProfilePublisher`` fake that mirrors the real compiler's
    identity rule (``profile/compiler.py:46,67-71``): the snapshot is compiled
    per (subject, model) and a different speaker or model yields a different
    ``profile_version`` — ``subject_user_id`` is inside the real hashed
    payload. ``None`` resolves to the tenant default model, like
    ``MongoModelCatalog._default_instance`` (``profile/catalog.py:45-49``).
    """

    DEFAULT_MODEL = "model-default"

    def __init__(self) -> None:
        self.published: list[str] = []
        self.compiled: list[tuple[str, str, str]] = []
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
        self.compiled.append((user_id, resolved, snapshot.profile_version))
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
        await self.publish_snapshot(snapshot, actor_id=actor_id, activate=activate)
        return snapshot

    async def publish_snapshot(
        self, snapshot: RuntimeProfileSnapshot, *, actor_id: str, activate: bool = False,
    ):
        self._snapshots[snapshot.profile_version] = snapshot
        self.published.append(snapshot.profile_version)
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
def shared_thread(real_mongo_db, monkeypatch):
    """A never-bound shared session: the owner + one active participant, real
    repositories, the fake gateway at the kernel-session seams, and the REAL
    DshChatService whose turn runner is faked to finalize turns like the real
    one (the TurnStateFinalizer drives the admission lock to terminal).

    The ``get_db`` seam is patched with ``raising=False`` (T7's gotcha) so the
    same module runs on the UNCHANGED code (no ``get_db`` import in
    chat_service yet) and on the todo-13 code.
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

    async def _finish_immediately(*, binding, message_id, **_kwargs):
        await chat._finalizer.finalize(
            binding=binding, message_id=message_id, status="completed",
        )
        return "completed"

    chat._turn_runner.run = _finish_immediately
    return harness, ids, session_oid, gateway, chat, _SpeakerProfiles_compiled(chat)


def _SpeakerProfiles_compiled(chat):
    return chat._profiles


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


def _created_kernel_ids(gateway) -> set[str]:
    return {session_id for _, session_id in gateway.created_sessions}


# ---------------------------------------------------------------------------
# Baseline characterization (passes on the UNCHANGED code)
# ---------------------------------------------------------------------------


def test_partial_unique_index_shape_is_unchanged(shared_thread):
    # Characterization: the partial unique index
    # one_current_kernel_binding_per_conversation is UNTOUCHED by todo 13 —
    # one current binding per conversation stays enforced by the server.
    harness, _ids, _session_oid, _gateway, _chat, _profiles = shared_thread
    info = harness.run(harness.db.agent_kernel_bindings.index_information())
    index = info["one_current_kernel_binding_per_conversation"]
    # index_information()'s key is a LIST of tuples on pymongo 3.12.3 (T03's
    # SON-vs-list gotcha, in reverse: never assert it against a plain dict).
    assert index["key"] == [("tenant_id", 1), ("conversation_id", 1)]
    assert index["partialFilterExpression"] == {"current": True}
    assert index["unique"] is True


def test_owner_turn_creates_the_first_binding(shared_thread):
    # Characterization: the owner's first turn on a never-bound conversation
    # creates the first DSH binding seeded with the owner's profile, and no
    # kernel session is disposed (nothing to clean up).
    harness, ids, session_oid, gateway, chat, _profiles = shared_thread
    owner_id = str(ids[OWNER])

    turn, outcome = _send(chat, harness, session_oid, user_id=owner_id, model_instance_id="model-x")

    assert outcome == "completed"
    assert turn.conversation_id == str(session_oid)
    binding = _current_binding(harness, session_oid)
    assert binding is not None
    assert binding["user_id"] == owner_id
    assert binding["model_instance_id"] == "model-x"
    assert binding["preset_id"] == "askai-enterprise"
    assert gateway.disposed_sessions == []


def test_solo_owner_turn_with_no_model_still_inherits_previous_model(shared_thread):
    # QA happy (plan todo 13, Q11 pinned): for a conversation with no other
    # active participant, a turn with no explicit model still inherits the
    # previous model — today's fallback is PRESERVED (it is how a solo user's
    # model choice survives a client reload). Characterization: passes on the
    # UNCHANGED code, and on the todo-13 code through the participants=None
    # fallback branch.
    harness, ids, _session_oid, gateway, chat, _profiles = shared_thread
    owner_id = str(ids[OWNER])
    solo_oid = ObjectId()
    now = datetime.utcnow()
    harness.run(
        harness.db.chat_sessions.insert_one(
            {
                "_id": solo_oid,
                "user_id": owner_id,
                "main_id": TENANT,
                "title": "Solo chat",
                "created_at": now,
                "updated_at": now,
            }
        )
    )

    first, outcome = _send(chat, harness, solo_oid, user_id=owner_id, model_instance_id="model-x")
    assert outcome == "completed"
    binding = _current_binding(harness, solo_oid)
    assert binding["model_instance_id"] == "model-x"
    created_after_first = len(gateway.created_sessions)

    second, outcome = _send(chat, harness, solo_oid, user_id=owner_id, model_instance_id=None)
    assert outcome == "completed"
    successor = _current_binding(harness, solo_oid)
    # No rotation: the compiled profile for the same speaker on the same
    # model matches the predecessor's version, so the synchronizer resumes.
    assert successor["binding_id"] == binding["binding_id"]
    assert successor["model_instance_id"] == "model-x"
    assert len(gateway.created_sessions) == created_after_first
    assert gateway.disposed_sessions == []


def test_binding_replacement_conflict_is_surfaced_as_a_retry_not_a_500() -> None:
    # QA failure (plan todo 13): a lost replacement claim (another turn won
    # the current-binding claim) is surfaced as ConversationBusyError — the
    # retryable 409 the endpoint maps — never as an unmapped
    # BindingReplacementConflict 500. Pure unit over the REAL synchronizer:
    # the fake profiles compile a changed version, the fake coordinator's
    # rotation loses the claim. Characterization: the conversion exists in
    # prepare_turn on the unchanged code too.
    async def run() -> None:
        current = {
            "binding_id": "binding-old",
            "tenant_id": "tenant-a",
            "user_id": "user-a",
            "conversation_id": "conversation-a",
            "kernel_session_id": "session-old",
            "runtime_id": "runtime-old",
            "profile_version": "rp-old",
            "model_instance_id": "model-a",
            "execution_location": "server",
            "active_turn": None,
        }

        class Conversations:
            async def owned(self, *_args, **_kwargs):
                return {"_id": "conversation-a"}

        class Bindings:
            async def current(self, *_args, **_kwargs):
                return current

            async def claim_turn(self, *_args, **_kwargs):
                raise AssertionError("the conflict must be raised before the claim")

            async def finish_turn(self, *_args, **_kwargs):
                return None

        class Profiles:
            async def compile_model_profile(self, **_scope):
                return SimpleNamespace(profile_version="rp-new", model_instance_id="model-a")

            async def publish_snapshot(self, snapshot, **_scope):
                return None

        class Coordinator:
            async def restore(self, binding):
                return binding

            async def rotate_binding(self, binding, *, profile_version, model_instance_id):
                raise BindingReplacementConflict("Conversation binding changed or is still running")

            async def dispose_restored_session(self, binding):
                return True

        service = DshChatService(
            gateway=SimpleNamespace(),
            coordinator=Coordinator(),  # type: ignore[arg-type]
            conversations=Conversations(),  # type: ignore[arg-type]
            bindings=Bindings(),  # type: ignore[arg-type]
            events=SimpleNamespace(),
            profiles=Profiles(),  # type: ignore[arg-type]
            kernel_version="test",
        )
        with pytest.raises(ConversationBusyError):
            await service.prepare_turn(
                tenant_id="tenant-a",
                user_id="user-a",
                conversation_id="conversation-a",
                text="retry turn",
                model_instance_id="model-a",
                timezone_name="UTC",
                images=[],
                documents=[],
            )

    asyncio.run(run())


# ---------------------------------------------------------------------------
# New behaviour (RED on the unchanged code)
# ---------------------------------------------------------------------------


def test_current_binding_read_is_conversation_scoped(shared_thread):
    # QA happy (plan todo 13): current() is conversation-scoped (the user_id
    # filter is dropped; the signature keeps it for call-shape compatibility
    # with the existing runtime callers), so a participant resolves the
    # conversation's current binding. RED on the unchanged code: the
    # user-scoped filter returns None for a non-owner caller.
    harness, ids, session_oid, _gateway, _chat, _profiles = shared_thread
    bindings = KernelBindingRepository(harness.db)
    harness.run(
        bindings.create(
            tenant_id=TENANT,
            user_id=str(ids[OWNER]),
            conversation_id=str(session_oid),
            kernel_session_id="ks-current-test",
            runtime_id="rt-test",
            profile_version="rp-owner-model-x",
            model_instance_id="model-x",
            kernel_version="test-kernel",
        )
    )

    owner_view = harness.run(bindings.current(str(session_oid), tenant_id=TENANT, user_id=str(ids[OWNER])))
    assert owner_view is not None

    participant_view = harness.run(
        bindings.current(str(session_oid), tenant_id=TENANT, user_id=str(ids[PARTICIPANT]))
    )
    assert participant_view is not None
    assert participant_view["binding_id"] == owner_view["binding_id"]


def test_participant_turn_is_admitted_and_rotation_carries_the_speaker(shared_thread):
    # QA happy (plan todo 13): A sends (explicit model), B sends (no model).
    # B's turn is admitted at the DSH turn admission (owner-or-ACTIVE-
    # participant), resolves the conversation's current binding (never
    # attempts create_binding on a bound conversation), and the rotation
    # carries the SPEAKER's user_id with the successor seeded from the
    # predecessor so the kernel session retains context. RED on the unchanged
    # code: the participant's send dies with LookupError
    # conversation_not_found at the owned() admission.
    harness, ids, session_oid, gateway, chat, profiles = shared_thread
    owner_id = str(ids[OWNER])
    participant_id = str(ids[PARTICIPANT])

    first, outcome = _send(chat, harness, session_oid, user_id=owner_id, model_instance_id="model-x")
    assert outcome == "completed"
    predecessor = _current_binding(harness, session_oid)
    assert predecessor["user_id"] == owner_id
    predecessor_kernel = str(predecessor["kernel_session_id"])
    predecessor_runtime = str(predecessor["runtime_id"])

    second, outcome = _send(chat, harness, session_oid, user_id=participant_id, model_instance_id=None)
    assert outcome == "completed"

    successor = _current_binding(harness, session_oid)
    assert successor is not None
    assert successor["binding_id"] != predecessor["binding_id"]
    # The successor carries the SPEAKER's identity, not the predecessor's.
    assert successor["user_id"] == participant_id
    # Q11: B sent no explicit model -> B's own effective default (the tenant
    # catalog default), never A's model-x and never the inherited preset.
    assert successor["model_instance_id"] == "model-default"
    assert successor["preset_id"] == "askai-enterprise"
    assert successor["profile_version"] == f"rp-{participant_id}-model-default"

    # The successor is seeded from the predecessor so context survives.
    successor_kernel = str(successor["kernel_session_id"])
    seeded = [request for request, session_id in gateway.created_sessions if session_id == successor_kernel]
    assert len(seeded) == 1
    assert seeded[0].session_spec.seed_runtime_id == predecessor_runtime
    assert seeded[0].session_spec.seed_session_id == predecessor_kernel
    assert seeded[0].session_spec.user_id == participant_id

    # The predecessor was disposed and superseded — no orphaned kernel session.
    assert predecessor_kernel in gateway.disposed_sessions
    assert successor_kernel not in gateway.disposed_sessions
    predecessor_row = harness.run(
        harness.db.agent_kernel_bindings.find_one({"binding_id": predecessor["binding_id"]})
    )
    assert predecessor_row["current"] is False
    assert predecessor_row["status"] == "superseded"
    assert profiles.published == [
        f"rp-{owner_id}-model-x",
        f"rp-{participant_id}-model-default",
    ]


def test_alternating_speakers_each_turn_resolves_the_speakers_own_model(shared_thread):
    # QA happy (plan todo 13): A sends (explicit model), B sends (no model),
    # A sends again — each turn's profile subject is the speaker; in the
    # two-active-participant case each turn's effective model and preset equal
    # the speaker's own resolution (the no-explicit-model turn resolves to the
    # tenant catalog default, never the predecessor's model).
    harness, ids, session_oid, gateway, chat, _profiles = shared_thread
    owner_id = str(ids[OWNER])
    participant_id = str(ids[PARTICIPANT])

    first, outcome = _send(chat, harness, session_oid, user_id=owner_id, model_instance_id="model-x")
    assert outcome == "completed"
    binding_one = _current_binding(harness, session_oid)
    assert binding_one["user_id"] == owner_id
    assert binding_one["model_instance_id"] == "model-x"
    assert binding_one["preset_id"] == "askai-enterprise"
    assert binding_one["profile_version"] == f"rp-{owner_id}-model-x"

    second, outcome = _send(chat, harness, session_oid, user_id=participant_id, model_instance_id=None)
    assert outcome == "completed"
    binding_two = _current_binding(harness, session_oid)
    assert binding_two["user_id"] == participant_id
    assert binding_two["model_instance_id"] == "model-default"
    assert binding_two["preset_id"] == "askai-enterprise"
    assert binding_two["profile_version"] == f"rp-{participant_id}-model-default"

    third, outcome = _send(chat, harness, session_oid, user_id=owner_id, model_instance_id=None)
    assert outcome == "completed"
    binding_three = _current_binding(harness, session_oid)
    assert binding_three["user_id"] == owner_id
    # A sent no explicit model with another active member present: A's own
    # effective default (the tenant default), never the inherited identity.
    assert binding_three["model_instance_id"] == "model-default"
    assert binding_three["preset_id"] == "askai-enterprise"
    assert binding_three["profile_version"] == f"rp-{owner_id}-model-default"

    # Exactly one rotation per speaker change: two speaker changes, two
    # rotations (three kernel sessions: the first binding + two successors).
    assert len(gateway.created_sessions) == 3
    created_ids = _created_kernel_ids(gateway)
    current_kernel = str(binding_three["kernel_session_id"])
    assert set(gateway.disposed_sessions) == created_ids - {current_kernel}
    assert gateway.disposed_sessions.count(current_kernel) == 0


def test_consecutive_same_speaker_turns_rotate_zero_times(shared_thread):
    # QA happy (plan todo 13): consecutive turns by the same speaker on the
    # same profile rotate zero times. B's first turn rotates to B's own
    # resolution; B's second turn (no model again) compiles the same profile
    # version and resumes without rotation or publication.
    harness, ids, session_oid, gateway, chat, profiles = shared_thread
    owner_id = str(ids[OWNER])
    participant_id = str(ids[PARTICIPANT])

    first, outcome = _send(chat, harness, session_oid, user_id=owner_id, model_instance_id="model-x")
    assert outcome == "completed"
    second, outcome = _send(chat, harness, session_oid, user_id=participant_id, model_instance_id=None)
    assert outcome == "completed"
    binding_two = _current_binding(harness, session_oid)
    created_after_rotation = len(gateway.created_sessions)

    third, outcome = _send(chat, harness, session_oid, user_id=participant_id, model_instance_id=None)
    assert outcome == "completed"
    binding_three = _current_binding(harness, session_oid)
    assert binding_three["binding_id"] == binding_two["binding_id"]
    assert binding_three["user_id"] == participant_id
    assert len(gateway.created_sessions) == created_after_rotation
    assert profiles.published.count(f"rp-{participant_id}-model-default") == 1


def test_concurrent_first_turns_on_never_bound_shared_session_do_not_500(shared_thread):
    # QA failure (plan todo 13): two users send simultaneously to a
    # never-bound shared session and neither receives a 500. The partial
    # unique index admits exactly one creator; the loser's create_binding
    # raises DuplicateKeyError, its kernel session is disposed by the
    # coordinator's except-handler, and prepare_turn re-resolves the winner's
    # binding once. RED on the unchanged code: the participant's send dies at
    # the user-scoped owned() admission (LookupError) before ever reaching
    # current()/create_binding, so the gather fails; on the todo-13 code the
    # gather never surfaces an unmapped DuplicateKeyError.
    harness, ids, session_oid, gateway, chat, _profiles = shared_thread

    async def _send_as(user_id: str):
        return await chat.prepare_turn(
            tenant_id=TENANT,
            user_id=user_id,
            conversation_id=str(session_oid),
            text="first turn",
            model_instance_id=None,
            timezone_name="UTC",
            images=[],
            documents=[],
        )

    async def _race():
        return await asyncio.gather(
            _send_as(str(ids[OWNER])),
            _send_as(str(ids[PARTICIPANT])),
            return_exceptions=True,
        )

    results = harness.run(_race())
    successes = [r for r in results if not isinstance(r, BaseException)]
    failures = [r for r in results if isinstance(r, Exception)]
    assert len(successes) >= 1
    assert all(isinstance(exc, ConversationBusyError) for exc in failures), failures

    for turn in successes:
        assert harness.run(chat.wait_turn(turn.message_id)) == "completed"

    binding = _current_binding(harness, session_oid)
    assert binding is not None
    current_count = harness.run(
        harness.db.agent_kernel_bindings.count_documents(
            {"conversation_id": str(session_oid), "current": True}
        )
    )
    assert current_count == 1
    # No orphaned kernel session: every created session except the current
    # binding's was disposed (the race loser's by the coordinator's
    # except-handler, a rotated predecessor's by the synchronizer).
    created_ids = _created_kernel_ids(gateway)
    current_kernel = str(binding["kernel_session_id"])
    assert current_kernel in created_ids
    assert set(gateway.disposed_sessions) == created_ids - {current_kernel}


def test_forced_back_to_back_rotations_leave_no_orphans_and_no_conflict_409(shared_thread):
    # QA failure (plan todo 13): forced back-to-back rotations leave no
    # orphaned kernel session and no BindingReplacementConflict 409 reaches
    # the client. Three turns, each completing before the next: the two
    # rotations dispose both predecessors and the replacement claims never
    # fail (each predecessor's active_turn is terminal), so no
    # ConversationBusyError (the 409) is raised at all.
    harness, ids, session_oid, gateway, chat, _profiles = shared_thread
    owner_id = str(ids[OWNER])
    participant_id = str(ids[PARTICIPANT])

    first, outcome = _send(chat, harness, session_oid, user_id=owner_id, model_instance_id="model-x")
    assert outcome == "completed"
    second, outcome = _send(chat, harness, session_oid, user_id=participant_id, model_instance_id=None)
    assert outcome == "completed"
    third, outcome = _send(chat, harness, session_oid, user_id=owner_id, model_instance_id=None)
    assert outcome == "completed"

    binding = _current_binding(harness, session_oid)
    assert binding is not None
    created_ids = _created_kernel_ids(gateway)
    current_kernel = str(binding["kernel_session_id"])
    assert len(created_ids) == 3
    assert set(gateway.disposed_sessions) == created_ids - {current_kernel}
    assert gateway.disposed_sessions.count(current_kernel) == 0

    async def _all_rows():
        cursor = harness.db.agent_kernel_bindings.find({"conversation_id": str(session_oid)})
        return [row async for row in cursor]

    all_rows = harness.run(_all_rows())
    assert len(all_rows) == 3
    predecessor_rows = [row for row in all_rows if row["binding_id"] != binding["binding_id"]]
    assert [row["status"] for row in predecessor_rows] == ["superseded", "superseded"]
    current_count = harness.run(
        harness.db.agent_kernel_bindings.count_documents(
            {"conversation_id": str(session_oid), "current": True}
        )
    )
    assert current_count == 1
