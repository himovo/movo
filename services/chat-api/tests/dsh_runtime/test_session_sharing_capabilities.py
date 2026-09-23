# allow: SIZE_OK — one cohesive seam (the plan todo-18 proof suite: capability
# isolation, context continuity, per-turn model identity, and the forbidden
# rotation optimization), pinned to the frozen plan's seven acceptance
# assertions; mirrors T04/T07-T14's pinned single-file matrices.
"""Plan todo 18 — capability isolation, context continuity, per-turn model
identity, and the guard against the forbidden rotation optimization.

Every assertion here runs over the REAL Wave-3 code paths against a real
mongod: the real ``DshChatService.prepare_turn`` turn admission, the real
``ConversationProfileSynchronizer`` rotation, the real ``ModelProfileCompiler``
(the hashed payload carries ``subject_user_id``, ``profile/compiler.py:46,67-71``),
the real ``RuntimeProfileStore``, and the real per-user skill/tool visibility
(``profile/skills/catalog.py:21-36`` via ``user_skill_service``, the
``external_tools`` user-scope rows). Only the kernel-session gateway and the
turn runner are faked (T13/T15's pattern) — no HTTP, no sleeps, durable state
through the real repositories.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from bson import ObjectId
from fastapi import HTTPException

import app.dsh_runtime.chat_service as chat_service_module
import app.dsh_runtime.profile.catalog as profile_catalog_module
import app.dsh_runtime.profile.store as profile_store_module
import app.enterprise_capabilities.tools.repository as tools_repository_module
import app.services.external_tools as external_tools_module
import app.services.org_skill_adapter as org_skill_adapter_module
import app.services.skills as skills_module
from app.api.endpoints import dsh_chat, dsh_tool_gateway, session_shares, sessions
from app.api.principal import ApiPrincipal
from app.dsh_runtime.application import dsh_runtime_application
from app.dsh_runtime.bindings.repository import KernelBindingRepository
from app.dsh_runtime.chat_service import ConversationBusyError, DshChatService
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.conversation.participants_repository import (
    SessionParticipantsRepository,
)
from app.dsh_runtime.contracts import CreateRuntimeRequest, CreateSessionRequest
from app.dsh_runtime.events import KernelEventRepository
from app.dsh_runtime.profile.catalog import MongoModelCatalog
from app.dsh_runtime.profile.compiler import ModelProfileCompiler
from app.dsh_runtime.profile.service import RuntimeProfilePublisher
from app.dsh_runtime.profile.skills.catalog import MongoSkillCatalog
from app.dsh_runtime.profile.skills.compiler import SkillProfileCompiler
from app.dsh_runtime.profile.store import MongoRuntimeProfileStore
from app.dsh_runtime.profile.tools import MongoToolCatalog, ToolProfileCompiler
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator
from app.dsh_runtime.tool_gateway import ToolGatewayTokenService
from app.enterprise_capabilities.tools.contracts import (
    ApprovalAskRequest,
    ApprovalDecisionRequest,
)
from app.enterprise_capabilities.tools.repository import EnterpriseToolRepository
from app.enterprise_capabilities.tools.service import EnterpriseToolService

TENANT = "tenant-session-sharing-capabilities"

OWNER = "owner"
PARTICIPANT = "participant"

# The fixture grants these to the OWNER only; B's compiled profile must never
# contain them (acceptance (i)). Sabotage (a) grants B the skill and the test
# must fail.
A_ONLY_SKILL_ID = "skill-a"
A_ONLY_TOOL_ID = "tool-a"


# ---------------------------------------------------------------------------
# Fakes — the kernel-session seams only (T13/T15's pattern)
# ---------------------------------------------------------------------------


class _FakeRuntime:
    def __init__(self, runtime_id: str) -> None:
        self.runtime_id = runtime_id
        self.kernel_version = "test-kernel"


class _FakeGateway:
    """In-memory DSH gateway fake: the same profile version resolves to the
    same runtime (production discovery parity), ``create_session`` records the
    kernel sessions so the rotation count and the seed continuity are
    assertable against durable state."""

    def __init__(self) -> None:
        self.created_sessions: list[tuple[CreateSessionRequest, str]] = []
        self.disposed_sessions: list[str] = []
        self.cancelled: list[str] = []
        self._runtimes: dict[str, _FakeRuntime] = {}

    async def discover_runtime(self, *, tenant_id: str, profile_version: str, isolation_key: str):
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
        return {"turnPending": False, "jobsPending": False}

    async def events_once(self, session_id: str, cursor: int) -> list[dict[str, Any]]:
        return []


# ---------------------------------------------------------------------------
# Fixture — real repositories, real profile stack, production write paths only
# ---------------------------------------------------------------------------


@pytest.fixture
def capabilities_thread(real_mongo_db, monkeypatch):
    """A never-bound shared session (owner + one active participant).

    The REAL profile stack drives every profile compile: the real
    ``ModelProfileCompiler`` over the real ``MongoModelCatalog`` (the tenant
    default model, ``profile/catalog.py:45-49``), the real per-user
    skill/tool catalogs, and the real ``MongoRuntimeProfileStore``. One model
    instance is seeded, so ``subject_user_id`` is the ONLY difference between
    the two speakers' hashed payloads — the R1=A identity rule.

    The turn runner completes each turn through the REAL
    ``TurnStateFinalizer`` unless the test registered the message id in
    ``gated`` — then the run stays in flight until ``release`` (the durable
    in-flight state the removal tests assert against).
    """
    harness = real_mongo_db
    harness.run(SessionParticipantsRepository(harness.db).ensure_indexes())
    harness.run(KernelBindingRepository(harness.db).ensure_indexes())
    monkeypatch.setattr(profile_catalog_module, "get_db", lambda: harness.db)
    monkeypatch.setattr(profile_store_module, "get_db", lambda: harness.db)
    monkeypatch.setattr(skills_module, "get_db", lambda: harness.db)
    monkeypatch.setattr(external_tools_module, "get_db", lambda: harness.db)
    monkeypatch.setattr(org_skill_adapter_module, "get_db", lambda: harness.db)
    monkeypatch.setattr(tools_repository_module, "get_db", lambda: harness.db)
    monkeypatch.setattr(chat_service_module, "get_db", lambda: harness.db, raising=False)

    ids = {OWNER: ObjectId(), PARTICIPANT: ObjectId()}
    now = datetime.utcnow()

    provider_oid = ObjectId()
    model_a_oid = ObjectId()  # the tenant default (priority 1)
    harness.run(
        harness.db.admin_model_providers.insert_one(
            {
                "_id": provider_oid,
                "main_id": TENANT,
                "status": "active",
                "provider_type": "openai_compatible",
                "name": "Provider",
            }
        )
    )
    harness.run(
        harness.db.admin_model_instances.insert_one(
            {
                "_id": model_a_oid,
                "main_id": TENANT,
                "status": "active",
                "capabilities": ["chat"],
                "model_name": "model-a",
                "display_name": "Model A",
                "provider_id": provider_oid,
                "priority": 1,
                "max_context_tokens": 8192,
                "settings": {},
                "updated_at": now,
            }
        )
    )

    # Per-user capability grants (the REAL visibility path): the owner's
    # skill + tool are granted to the OWNER only; the participant has their
    # own. Neither speaker's profile may contain the other's grants.
    for name, skill_id, tool_id in (
        (OWNER, A_ONLY_SKILL_ID, A_ONLY_TOOL_ID),
        (PARTICIPANT, "skill-b", "tool-b"),
    ):
        user_id = str(ids[name])
        harness.run(
            harness.db.user_skills.insert_one(
                {
                    "_id": skill_id,
                    "user_id": user_id,
                    "main_id": TENANT,
                    "name": f"Skill {skill_id}",
                    "description": f"Skill granted only to {name}",
                    "skill_markdown": f"# {skill_id}\nInstructions for {name}.",
                    "enabled": True,
                }
            )
        )
        harness.run(
            harness.db.external_tools.insert_one(
                {
                    "_id": tool_id,
                    "scope": "user",
                    "owner_user_id": user_id,
                    "main_id": TENANT,
                    "name": f"Tool {tool_id}",
                    "type": "http",
                    "description": f"Tool granted only to {name}",
                    "config": {"method": "GET"},
                    "status": "active",
                }
            )
        )

    # The participant's approval-REQUIRED tool: an approval gate exists only
    # for tools whose compiled definition demands one (a plain GET tool
    # compiles to approval_required=False and request_approval returns
    # "allowed-once" without creating a row).
    harness.run(
        harness.db.external_tools.insert_one(
            {
                "_id": "tool-b-gate",
                "scope": "user",
                "owner_user_id": str(ids[PARTICIPANT]),
                "main_id": TENANT,
                "name": "Tool B gate",
                "type": "http",
                "description": "Approval-gated tool for the participant",
                "config": {"method": "POST", "approvalRequired": True},
                "status": "active",
            }
        )
    )

    # An ORGANIZATION-scope tool visible to EVERY user in the tenant: the
    # guard pair below compiles IDENTICAL payloads (the tool's compiled
    # definition is derived from the row, not from the viewer), so
    # subject_user_id is the ONLY difference between their hashed payloads.
    harness.run(
        harness.db.external_tools.insert_one(
            {
                "_id": "tool-shared",
                "scope": "organization",
                "main_id": TENANT,
                "name": "Tool shared",
                "type": "http",
                "description": "Organization-wide tool",
                "config": {"method": "GET"},
                "status": "active",
            }
        )
    )

    # The guard pair: two users with NO personal grants. Their compiled
    # profiles are byte-identical except subject_user_id — the state where the
    # subject is the only thing preventing the forbidden-rotation leak.
    guard_ids = {"guard-owner": ObjectId(), "guard-participant": ObjectId()}
    for name, oid in guard_ids.items():
        harness.run(
            harness.db.end_users.insert_one(
                {
                    "_id": oid,
                    "main_id": TENANT,
                    "name": f"User {name}",
                    "status": "active",
                }
            )
        )
    guard_oid = ObjectId()
    harness.run(
        harness.db.chat_sessions.insert_one(
            {
                "_id": guard_oid,
                "user_id": str(guard_ids["guard-owner"]),
                "main_id": TENANT,
                "title": "Guard chat",
                "created_at": now,
                "updated_at": now,
            }
        )
    )
    harness.run(
        SessionParticipantsRepository(harness.db).add(
            tenant_id=TENANT, conversation_id=str(guard_oid),
            user_id=str(guard_ids["guard-participant"]),
        )
    )

    for name in (OWNER, PARTICIPANT):
        harness.run(
            harness.db.end_users.insert_one(
                {
                    "_id": ids[name],
                    "main_id": TENANT,
                    "name": f"User {name}",
                    "status": "active",
                }
            )
        )

    session_oid = ObjectId()
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
    compiler = ModelProfileCompiler(
        MongoModelCatalog(),
        ToolProfileCompiler(MongoToolCatalog()),
        SkillProfileCompiler(MongoSkillCatalog()),
    )
    profiles = RuntimeProfilePublisher(compiler, MongoRuntimeProfileStore())
    chat = DshChatService(
        gateway=gateway,
        coordinator=RuntimeCoordinator(gateway, KernelBindingRepository(harness.db)),
        conversations=ConversationRepository(harness.db),
        bindings=KernelBindingRepository(harness.db),
        events=KernelEventRepository(harness.db),
        profiles=profiles,
        kernel_version="test-kernel",
    )

    release = asyncio.Event()
    gated_speakers: set[str] = set()

    async def _runner(*args: Any, binding: dict[str, Any] | None = None, message_id: str | None = None, **kwargs: Any) -> str:
        # Gated by SPEAKER, not by message id: the runner's first step may run
        # inside prepare_turn's own run_until_complete, before the test could
        # register a message id — the speaker is known before the turn starts.
        if str((binding or {}).get("user_id") or "") in gated_speakers:
            await release.wait()
        await chat._finalizer.finalize(
            binding=binding, message_id=message_id, status="completed",
        )
        return "completed"

    chat._turn_runner.run = _runner
    return harness, ids, session_oid, gateway, chat, release, gated_speakers, guard_ids, guard_oid


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


def _skill_source_ids(snapshot) -> set[str]:
    return {item.source_id for item in snapshot.skills}


def _tool_external_ids(snapshot) -> set[str]:
    return {item.external_tool_id for item in snapshot.tools}


# ---------------------------------------------------------------------------
# Acceptance (i) — capability isolation
# ---------------------------------------------------------------------------


def test_b_compiled_profile_never_contains_a_skill_or_tool_granted_only_to_a(capabilities_thread):
    """(i) B's compiled profile never contains a skill or tool granted only to
    A — both the direct compile (the REAL compiler resolves per-user
    visibility, ``profile/skills/catalog.py:21-36``) and the turn-path profile
    B's turn actually executes under (the REAL store's published snapshot for
    the binding's ``profile_version``)."""
    harness, ids, session_oid, _gateway, chat, _release, _gated_speakers, _guard_ids, _guard_oid = capabilities_thread
    owner_id = str(ids[OWNER])
    participant_id = str(ids[PARTICIPANT])

    compiler = chat._profiles._compiler
    a_profile = harness.run(
        compiler.compile(tenant_id=TENANT, user_id=owner_id, model_instance_id=None)
    )
    b_profile = harness.run(
        compiler.compile(tenant_id=TENANT, user_id=participant_id, model_instance_id=None)
    )
    assert a_profile.subject_user_id == owner_id
    assert b_profile.subject_user_id == participant_id
    assert {A_ONLY_SKILL_ID, A_ONLY_TOOL_ID}.isdisjoint(_skill_source_ids(b_profile))
    assert {A_ONLY_SKILL_ID, A_ONLY_TOOL_ID}.isdisjoint(_tool_external_ids(b_profile))
    # B's own grants ARE in B's profile (the visibility is per-user, not empty).
    assert "skill-b" in _skill_source_ids(b_profile)
    assert "tool-b" in _tool_external_ids(b_profile)
    # A's profile DOES contain A's grants (the fixture grants them to A only).
    assert A_ONLY_SKILL_ID in _skill_source_ids(a_profile)
    assert A_ONLY_TOOL_ID in _tool_external_ids(a_profile)

    # The turn path: A's turn then B's turn (both no explicit model — the
    # payloads differ only by subject). B's effective profile is the published
    # snapshot for the binding's profile_version.
    first, outcome = _send(chat, harness, session_oid, user_id=owner_id)
    assert outcome == "completed"
    second, outcome = _send(chat, harness, session_oid, user_id=participant_id)
    assert outcome == "completed"
    binding = _current_binding(harness, session_oid)
    assert binding["user_id"] == participant_id
    effective = harness.run(chat._profiles.get(str(binding["profile_version"])))
    assert effective.subject_user_id == participant_id
    assert {A_ONLY_SKILL_ID, A_ONLY_TOOL_ID}.isdisjoint(_skill_source_ids(effective))
    assert {A_ONLY_SKILL_ID, A_ONLY_TOOL_ID}.isdisjoint(_tool_external_ids(effective))

    # The turn-path isolation in the guard pair's state (the compiled payloads
    # are byte-identical except subject_user_id): the participant's turn
    # executes under a profile whose subject is the participant — the state a
    # stripped hash would break (the guard test below).
    guard_owner = str(_guard_ids["guard-owner"])
    guard_participant = str(_guard_ids["guard-participant"])
    guard_first, outcome = _send(chat, harness, _guard_oid, user_id=guard_owner, model_instance_id=None)
    assert outcome == "completed"
    guard_second, outcome = _send(chat, harness, _guard_oid, user_id=guard_participant, model_instance_id=None)
    assert outcome == "completed"
    guard_binding = _current_binding(harness, _guard_oid)
    assert guard_binding["user_id"] == guard_participant
    guard_effective = harness.run(chat._profiles.get(str(guard_binding["profile_version"])))
    assert guard_effective.subject_user_id == guard_participant
    assert "tool-shared" in _tool_external_ids(guard_effective)


# ---------------------------------------------------------------------------
# Acceptance (ii) + (iii) — rotation per speaker change, context continuity
# ---------------------------------------------------------------------------


def test_alternating_speakers_rotate_exactly_once_per_change(capabilities_thread):
    """(ii) Alternating speakers: exactly one rotation per speaker change
    REGARDLESS of model/preset equality — one model instance is seeded, so the
    two speakers' hashed payloads differ ONLY by ``subject_user_id``
    (``profile/compiler.py:46,67-71``) and every speaker change still rotates.
    The successor kernel session is seeded from the predecessor (context
    continuity) and every turn completes."""
    harness, ids, session_oid, gateway, chat, _release, _gated_speakers, _guard_ids, _guard_oid = capabilities_thread
    owner_id = str(ids[OWNER])
    participant_id = str(ids[PARTICIPANT])

    first, outcome = _send(chat, harness, session_oid, user_id=owner_id)
    assert outcome == "completed"
    predecessor = _current_binding(harness, session_oid)
    assert predecessor["user_id"] == owner_id
    predecessor_kernel = str(predecessor["kernel_session_id"])
    predecessor_runtime = str(predecessor["runtime_id"])

    second, outcome = _send(chat, harness, session_oid, user_id=participant_id)
    assert outcome == "completed"
    successor = _current_binding(harness, session_oid)
    assert successor is not None
    assert successor["binding_id"] != predecessor["binding_id"]
    assert successor["user_id"] == participant_id
    assert successor["preset_id"] == "askai-enterprise"
    assert successor["profile_version"] != predecessor["profile_version"]
    # Context continuity: the successor kernel session is SEEDED from the
    # predecessor's exported state.
    successor_kernel = str(successor["kernel_session_id"])
    seeded = [request for request, sid in gateway.created_sessions if sid == successor_kernel]
    assert len(seeded) == 1
    assert seeded[0].session_spec.seed_runtime_id == predecessor_runtime
    assert seeded[0].session_spec.seed_session_id == predecessor_kernel
    assert seeded[0].session_spec.user_id == participant_id
    assert predecessor_kernel in gateway.disposed_sessions
    assert successor_kernel not in gateway.disposed_sessions

    third, outcome = _send(chat, harness, session_oid, user_id=owner_id)
    assert outcome == "completed"
    final_binding = _current_binding(harness, session_oid)
    assert final_binding["user_id"] == owner_id
    # The compile is deterministic: the owner's third turn resolves the SAME
    # profile_version as their first (same subject, model and grants) — and a
    # NEW rotation still happened, because the version repeat does not
    # suppress rotation.
    assert final_binding["profile_version"] == predecessor["profile_version"]
    assert final_binding["binding_id"] != successor["binding_id"]
    # Exactly one rotation per speaker change: two changes, two rotations —
    # three kernel sessions total, only the current one alive.
    assert len(gateway.created_sessions) == 3
    created_ids = _created_kernel_ids(gateway)
    current_kernel = str(final_binding["kernel_session_id"])
    assert set(gateway.disposed_sessions) == created_ids - {current_kernel}
    assert gateway.disposed_sessions.count(current_kernel) == 0
    current_count = harness.run(
        harness.db.agent_kernel_bindings.count_documents(
            {"conversation_id": str(session_oid), "current": True}
        )
    )
    assert current_count == 1


def test_alternating_guard_pair_speakers_rotate_exactly_once_per_change(capabilities_thread):
    """(ii) in the guard pair's state: their compiled payloads differ ONLY by
    ``subject_user_id`` — the strongest form of the pin: exactly one rotation
    per speaker change even when NOTHING else differs (the state a stripped
    hash breaks; the guard test below)."""
    harness, ids, session_oid, gateway, chat, _release, _gated_speakers, guard_ids, guard_oid = capabilities_thread
    guard_owner = str(guard_ids["guard-owner"])
    guard_participant = str(guard_ids["guard-participant"])

    first, outcome = _send(chat, harness, guard_oid, user_id=guard_owner, model_instance_id=None)
    assert outcome == "completed"
    second, outcome = _send(chat, harness, guard_oid, user_id=guard_participant, model_instance_id=None)
    assert outcome == "completed"
    third, outcome = _send(chat, harness, guard_oid, user_id=guard_owner, model_instance_id=None)
    assert outcome == "completed"

    binding = _current_binding(harness, guard_oid)
    assert len(gateway.created_sessions) == 3
    assert binding["user_id"] == guard_owner
    # The deterministic compile: the owner's third turn resolves the same
    # profile_version as their first — and a NEW rotation still happened
    # (three binding rows, only the current one alive).
    rows = harness.run(
        harness.db.agent_kernel_bindings.find({"conversation_id": str(guard_oid)}).to_list(length=10)
    )
    assert len(rows) == 3
    assert len([row for row in rows if row["current"]]) == 1


def test_consecutive_same_speaker_turns_on_same_profile_rotate_zero_times(capabilities_thread):
    """(ii) Consecutive turns by the same speaker ON THE SAME PROFILE rotate
    zero times: B's first turn rotates to B's own resolution; B's second turn
    compiles the SAME profile version and resumes without rotation or
    republication."""
    harness, ids, session_oid, gateway, chat, _release, _gated_speakers, _guard_ids, _guard_oid = capabilities_thread
    owner_id = str(ids[OWNER])
    participant_id = str(ids[PARTICIPANT])

    first, outcome = _send(chat, harness, session_oid, user_id=owner_id)
    assert outcome == "completed"
    second, outcome = _send(chat, harness, session_oid, user_id=participant_id)
    assert outcome == "completed"
    binding_two = _current_binding(harness, session_oid)
    created_after_rotation = len(gateway.created_sessions)

    third, outcome = _send(chat, harness, session_oid, user_id=participant_id)
    assert outcome == "completed"
    binding_three = _current_binding(harness, session_oid)
    assert binding_three["binding_id"] == binding_two["binding_id"]
    assert binding_three["user_id"] == participant_id
    assert len(gateway.created_sessions) == created_after_rotation


def test_no_binding_replacement_conflict_409_reaches_the_client(capabilities_thread):
    """(iii) No ``BindingReplacementConflict`` 409 reaches the client: the
    endpoint's only path to that 409 is ``dsh_chat``'s ``except
    ConversationBusyError`` mapping (``dsh_chat.py:203-216`` family), so no
    ``ConversationBusyError`` may escape ``prepare_turn`` across a forced
    four-turn rotation sequence."""
    harness, ids, session_oid, _gateway, chat, _release, _gated_speakers, _guard_ids, _guard_oid = capabilities_thread
    owner_id = str(ids[OWNER])
    participant_id = str(ids[PARTICIPANT])

    busy_errors: list[ConversationBusyError] = []
    for speaker in (owner_id, participant_id, owner_id, participant_id):
        try:
            turn = harness.run(
                chat.prepare_turn(
                    tenant_id=TENANT,
                    user_id=speaker,
                    conversation_id=str(session_oid),
                    text="turn",
                    model_instance_id=None,
                    timezone_name="UTC",
                    images=[],
                    documents=[],
                )
            )
        except ConversationBusyError as exc:
            busy_errors.append(exc)
            continue
        assert harness.run(chat.wait_turn(turn.message_id)) == "completed"

    assert busy_errors == []


# ---------------------------------------------------------------------------
# Acceptance (v) — binding reads used for capability resolution stay scoped
# ---------------------------------------------------------------------------


def test_binding_reads_for_capability_resolution_stay_scoped(capabilities_thread):
    """(v) The binding reads the capability path uses stay scoped as designed:
    ``current()`` is conversation-scoped (a participant resolves the SAME
    current binding — never None, never a create_binding) with the tenant
    scope retained; the execution-path read
    (``EnterpriseToolRepository.session_binding``) resolves the conversation's
    current kernel binding; ``by_message`` stays conversation-scoped so any
    member's poll finds the author-attributed binding (todo 7)."""
    harness, ids, session_oid, _gateway, chat, _release, _gated_speakers, _guard_ids, _guard_oid = capabilities_thread
    owner_id = str(ids[OWNER])
    participant_id = str(ids[PARTICIPANT])
    bindings = KernelBindingRepository(harness.db)
    harness.run(
        bindings.create(
            tenant_id=TENANT,
            user_id=owner_id,
            conversation_id=str(session_oid),
            kernel_session_id="ks-scope-test",
            runtime_id="rt-test",
            profile_version="rp-owner-scope-test",
            model_instance_id="model-x",
            kernel_version="test-kernel",
        )
    )

    owner_view = harness.run(bindings.current(str(session_oid), tenant_id=TENANT, user_id=owner_id))
    participant_view = harness.run(
        bindings.current(str(session_oid), tenant_id=TENANT, user_id=participant_id)
    )
    assert owner_view is not None
    assert participant_view is not None
    assert participant_view["binding_id"] == owner_view["binding_id"]

    cross_tenant = harness.run(
        bindings.current(str(session_oid), tenant_id=f"{TENANT}-other", user_id=participant_id)
    )
    assert cross_tenant is None

    # The execution-path read (tools/service.py:505) resolves the
    # conversation's current kernel binding for the capability check.
    execution_binding = harness.run(EnterpriseToolRepository().session_binding("ks-scope-test"))
    assert execution_binding is not None
    assert execution_binding["user_id"] == owner_id
    assert execution_binding["profile_version"] == "rp-owner-scope-test"

    # by_message: the author-attributed binding is found by ANY member's poll.
    harness.run(
        bindings.claim_turn(
            str(owner_view["binding_id"]),
            message_id="msg-scope-test", request_id="req-scope-test",
            turn_context={}, turn_metadata={},
        )
    )
    author_poll = harness.run(bindings.by_message("msg-scope-test", tenant_id=TENANT))
    participant_poll = harness.run(bindings.by_message("msg-scope-test", tenant_id=TENANT))
    assert author_poll is not None
    assert participant_poll["binding_id"] == owner_view["binding_id"]


# ---------------------------------------------------------------------------
# Acceptance (iv) — removal semantics
# ---------------------------------------------------------------------------


def _endpoint_seams(monkeypatch, harness, ids: dict[str, ObjectId], chat) -> None:
    """The endpoint seams (T15/T8/T9's pattern): the bearer-token-dispatching
    identity, the get_db seam, and the chat singleton swapped for the REAL
    DshChatService. Every non-owner claims their OWN user_id/main_id (what the
    real client sends) so denials provably come from the right gate."""
    tokens = {f"bearer-{name}": oid for name, oid in ids.items()}

    async def resolve(authorization: str | None):
        token = str(authorization or "").removeprefix("Bearer ").strip()
        oid = tokens.get(token)
        if oid is None:
            raise LookupError(f"no seeded end-user for bearer token {token!r}")
        return {"user": {"_id": oid, "status": "active"}, "main_id": TENANT}

    monkeypatch.setattr(sessions, "_resolve_session_user", resolve)
    monkeypatch.setattr(sessions, "get_db", lambda: harness.db)
    monkeypatch.setattr(dsh_chat, "_resolve_session_user", resolve)
    monkeypatch.setattr(dsh_chat, "get_db", lambda: harness.db)
    monkeypatch.setattr(dsh_runtime_application, "chat", chat)
    monkeypatch.setattr(session_shares, "get_db", lambda: harness.db)


def _get_session(harness, session_oid, *, token: str, claimed_user_id: str):
    return sessions.get_session(
        str(session_oid),
        user_id=claimed_user_id,
        main_id=TENANT,
        main_id_snake=None,
        include_context_summary=False,
        authorization=token,
    )


def _identity_seam(mapping: dict[str, tuple[str, str]]):
    async def _identity(authorization: str | None) -> tuple[str, str]:
        token = (authorization or "").removeprefix("Bearer ").strip()
        return mapping[token]

    return _identity


def _http_status(exc: BaseException) -> int:
    return getattr(exc, "status_code", 0)


def test_removed_participant_next_turn_is_denied_at_admission(capabilities_thread):
    """(iv) After ``remove``, the removed participant's next turn is denied at
    the DSH turn admission (LookupError -> 404 at the endpoint) — the
    membership gate, never 403, never admission."""
    harness, ids, session_oid, _gateway, chat, _release, _gated_speakers, _guard_ids, _guard_oid = capabilities_thread
    owner_id = str(ids[OWNER])
    participant_id = str(ids[PARTICIPANT])
    first, outcome = _send(chat, harness, session_oid, user_id=owner_id)
    assert outcome == "completed"
    harness.run(
        SessionParticipantsRepository(harness.db).remove(
            conversation_id=str(session_oid), tenant_id=TENANT, user_id=participant_id,
        )
    )

    with pytest.raises(LookupError):
        harness.run(
            chat.prepare_turn(
                tenant_id=TENANT,
                user_id=participant_id,
                conversation_id=str(session_oid),
                text="post-removal turn",
                model_instance_id=None,
                timezone_name="UTC",
                images=[],
                documents=[],
            )
        )


def test_removed_participant_reads_are_denied(capabilities_thread):
    """(iv) After ``remove``: the removed participant's reads are denied too —
    session GET 404, members list 404, event poll 404 (the message EXISTS, so
    the poll denial provably comes from the membership gate, not from a
    missing message)."""
    harness, ids, session_oid, _gateway, chat, _release, _gated_speakers, _guard_ids, _guard_oid = capabilities_thread
    monkeypatch = pytest.MonkeyPatch()
    try:
        first, outcome = _send(chat, harness, session_oid, user_id=str(ids[OWNER]))
        assert outcome == "completed"
        in_flight_message = first.message_id
        harness.run(
            SessionParticipantsRepository(harness.db).remove(
                conversation_id=str(session_oid), tenant_id=TENANT, user_id=str(ids[PARTICIPANT]),
            )
        )
        _endpoint_seams(monkeypatch, harness, ids, chat)
        participant_token = "Bearer bearer-participant"

        with pytest.raises(HTTPException) as excinfo:
            harness.run(_get_session(harness, session_oid, token=participant_token, claimed_user_id=str(ids[PARTICIPANT])))
        assert _http_status(excinfo.value) == 404

        with pytest.raises(HTTPException) as excinfo:
            harness.run(session_shares.list_participants(
                str(session_oid),
                principal=ApiPrincipal(kind="end_user", main_id=TENANT, user_id=str(ids[PARTICIPANT])),
            ))
        assert _http_status(excinfo.value) == 404

        with pytest.raises(HTTPException) as excinfo:
            harness.run(dsh_chat.chat_message_events(
                in_flight_message, after=0, after_cursor=None, authorization=participant_token,
            ))
        assert _http_status(excinfo.value) == 404

        # The owner's identical reads still work (the denial is per-viewer).
        owner_response = harness.run(_get_session(harness, session_oid, token="Bearer bearer-owner", claimed_user_id=str(ids[OWNER])))
        assert owner_response.code == 0
        owner_members = harness.run(session_shares.list_participants(
            str(session_oid),
            principal=ApiPrincipal(kind="end_user", main_id=TENANT, user_id=str(ids[OWNER])),
        ))
        assert owner_members["code"] == 0
    finally:
        monkeypatch.undo()


def test_run_in_flight_at_removal_completes_and_persists(capabilities_thread):
    """(iv + sabotage (d) plain variant): a run already in flight when the
    removal happened completes and persists normally — the removal neither
    aborts nor wedges the run — and the owner still sees the leaver's
    historical messages, attributed (Q15)."""
    harness, ids, session_oid, _gateway, chat, release, gated_speakers, _guard_ids, _guard_oid = capabilities_thread
    monkeypatch = pytest.MonkeyPatch()
    try:
        participant_id = str(ids[PARTICIPANT])
        first, outcome = _send(chat, harness, session_oid, user_id=str(ids[OWNER]))
        assert outcome == "completed"
        gated_speakers.add(participant_id)
        turn = harness.run(
            chat.prepare_turn(
                tenant_id=TENANT,
                user_id=participant_id,
                conversation_id=str(session_oid),
                text="in-flight turn",
                model_instance_id=None,
                timezone_name="UTC",
                images=[],
                documents=[],
            )
        )
        row = harness.run(
            harness.db.chat_sessions.find_one({"_id": session_oid})
        )
        assert row["active_run"]["status"] == "running"
        assert row["active_run"]["initiator_user_id"] == participant_id
        harness.run(
            SessionParticipantsRepository(harness.db).remove(
                conversation_id=str(session_oid), tenant_id=TENANT, user_id=participant_id,
            )
        )

        # The run completes and persists normally: the release mirrors the
        # host finishing the turn after the removal.
        release.set()
        outcome = harness.run(chat.wait_turn(turn.message_id))
        assert outcome == "completed"
        row = harness.run(
            harness.db.chat_sessions.find_one({"_id": session_oid})
        )
        assert "active_run" not in row
        binding = _current_binding(harness, session_oid)
        assert binding["active_turn"]["status"] == "completed"
        messages = harness.run(
            ConversationRepository(harness.db).list_messages(TENANT, str(session_oid))
        )
        leaver_rows = [m for m in messages if m.get("user_id") == participant_id]
        assert len(leaver_rows) == 2  # the user row + the assistant placeholder

        # The owner still sees the leaver's messages, attributed (Q15).
        _endpoint_seams(monkeypatch, harness, ids, chat)
        response = harness.run(_get_session(harness, session_oid, token="Bearer bearer-owner", claimed_user_id=str(ids[OWNER])))
        assert response.code == 0
        history = [m.get("user_id") for m in response.data["messages"]]
        assert participant_id in history
    finally:
        monkeypatch.undo()


def _approval_setup(harness, ids, session_oid, chat, release, gated_speakers):
    """A run in flight, paused on an approval gate: the REAL
    ``EnterpriseToolService`` over the chat profile stack, the binding mid-run
    with the REAL turn metadata (initiator = the participant speaker), and a
    pending approval stamped with that initiator."""
    participant_id = str(ids[PARTICIPANT])
    gated_speakers.add(participant_id)
    turn = harness.run(
        chat.prepare_turn(
            tenant_id=TENANT,
            user_id=participant_id,
            conversation_id=str(session_oid),
            text="approval-gated turn",
            model_instance_id=None,
            timezone_name="UTC",
            images=[],
            documents=[],
        )
    )
    binding = _current_binding(harness, session_oid)
    assert binding["user_id"] == participant_id
    profile = harness.run(chat._profiles.get(str(binding["profile_version"])))
    tool = next(t for t in profile.tools if t.approval_required)
    tokens = ToolGatewayTokenService("t18-tool-signing-secret")
    token = tokens.issue(
        tenant_id=TENANT, user_id=participant_id, profile_version=str(binding["profile_version"]),
        tool_names=[tool.name], scopes=list(tool.required_scopes),
    )
    claims = tokens.verify(token)
    service = EnterpriseToolService(EnterpriseToolRepository(), chat._profiles)
    return turn, binding, claims, service


def _approval_row(harness, action_id: str):
    return harness.db.enterprise_tool_approvals.find_one({"action_id": action_id})


def test_removed_initiator_can_still_decide_the_approval_gate(capabilities_thread, monkeypatch):
    """(iv + sabotage (d) approval-gated variant): a run paused on an approval
    gate whose initiator is removed mid-run — the removed initiator can still
    decide that approval until terminal (the decide gate binds to the STAMP,
    not to membership), the run reaches terminal and persists, and their
    write admission stays denied."""
    harness, ids, session_oid, _gateway, chat, release, gated_speakers, _guard_ids, _guard_oid = capabilities_thread
    participant_id = str(ids[PARTICIPANT])
    turn, binding, claims, service = _approval_setup(harness, ids, session_oid, chat, release, gated_speakers)
    harness.run(service._repository.ensure_indexes())
    monkeypatch.setattr(dsh_runtime_application, "tools", service)
    monkeypatch.setattr(dsh_tool_gateway, "_identity", _identity_seam({
        str(ids[OWNER]): (TENANT, str(ids[OWNER])),
        participant_id: (TENANT, participant_id),
    }))

    async def scenario():
        pending = asyncio.create_task(service.request_approval(
            ApprovalAskRequest(
                profileVersion=str(binding["profile_version"]),
                sessionId=str(binding["kernel_session_id"]),
                toolName=sorted(claims.tool_names)[0], actionId="action-gate", reason="write",
                timeoutSeconds=2,
            ),
            claims,
        ))
        while await _approval_row(harness, "action-gate") is None:
            await asyncio.sleep(0)
        await SessionParticipantsRepository(harness.db).remove(
            conversation_id=str(session_oid), tenant_id=TENANT, user_id=participant_id,
        )
        decided = await dsh_tool_gateway.decide_approval(
            "action-gate",
            payload=ApprovalDecisionRequest(decision="approved"),
            authorization=f"Bearer {participant_id}",
        )
        outcome = await pending
        return decided, outcome

    decided, outcome = harness.run(scenario())
    assert decided["data"]["status"] == "approved"
    assert decided["data"]["decided_by"] == participant_id
    assert outcome == "allowed-once"

    # The run reaches terminal and persists; the write admission stays denied.
    with pytest.raises(LookupError):
        harness.run(
            chat.prepare_turn(
                tenant_id=TENANT,
                user_id=participant_id,
                conversation_id=str(session_oid),
                text="post-removal turn",
                model_instance_id=None,
                timezone_name="UTC",
                images=[],
                documents=[],
            )
        )
    release.set()
    outcome = harness.run(chat.wait_turn(turn.message_id))
    assert outcome == "completed"
    row = harness.run(harness.db.chat_sessions.find_one({"_id": session_oid}))
    assert "active_run" not in row


def test_approval_deadline_releases_a_removed_initiators_gate(capabilities_thread, monkeypatch):
    """(iv, deadline variant): the removal does not leave the run permanently
    locked out — the 300s/900s approval deadline is simulated through durable
    state (the repository's expire, no real-time waits): the decide fails
    closed after the deadline and the run still reaches terminal and
    persists."""
    harness, ids, session_oid, _gateway, chat, release, gated_speakers, _guard_ids, _guard_oid = capabilities_thread
    participant_id = str(ids[PARTICIPANT])
    turn, binding, claims, service = _approval_setup(harness, ids, session_oid, chat, release, gated_speakers)
    harness.run(service._repository.ensure_indexes())
    monkeypatch.setattr(dsh_runtime_application, "tools", service)

    async def scenario():
        pending = asyncio.create_task(service.request_approval(
            ApprovalAskRequest(
                profileVersion=str(binding["profile_version"]),
                sessionId=str(binding["kernel_session_id"]),
                toolName=sorted(claims.tool_names)[0], actionId="action-deadline", reason="write",
                timeoutSeconds=2,
            ),
            claims,
        ))
        while await _approval_row(harness, "action-deadline") is None:
            await asyncio.sleep(0)
        await SessionParticipantsRepository(harness.db).remove(
            conversation_id=str(session_oid), tenant_id=TENANT, user_id=participant_id,
        )
        expired = await service._repository.expire("action-deadline")
        approval_outcome = await pending
        return expired, approval_outcome

    expired, approval_outcome = harness.run(scenario())
    assert expired is not None and expired.status == "expired"
    assert approval_outcome == "rejected"
    row = harness.run(harness.db.chat_sessions.find_one({"_id": session_oid}))
    assert row["active_run"]["status"] == "running"

    # The run still reaches terminal and persists — no member is left locked out.
    release.set()
    outcome = harness.run(chat.wait_turn(turn.message_id))
    assert outcome == "completed"
    row = harness.run(harness.db.chat_sessions.find_one({"_id": session_oid}))
    assert "active_run" not in row


# ---------------------------------------------------------------------------
# Acceptance (vi) — per-turn model/preset identity
# ---------------------------------------------------------------------------


def _seed_model_instance(harness, *, name: str, priority: int, provider_oid):
    now = datetime.utcnow()
    oid = ObjectId()
    harness.run(
        harness.db.admin_model_instances.insert_one(
            {
                "_id": oid,
                "main_id": TENANT,
                "status": "active",
                "capabilities": ["chat"],
                "model_name": name,
                "display_name": name,
                "provider_id": provider_oid,
                "priority": priority,
                "max_context_tokens": 8192,
                "settings": {},
                "updated_at": now,
            }
        )
    )
    return str(oid)


def test_turn_model_and_preset_equal_the_speakers_own_resolution(capabilities_thread):
    """(vi) With another active participant, each turn's effective model and
    preset equal the speaker's own resolution — including the no-explicit-model
    case (the tenant catalog default via the REAL ``MongoModelCatalog
    ._default_instance``, never the predecessor's ``previous_model_id``) —
    while a solo-owner turn with no explicit model retains today's
    ``previous_model_id`` fallback (``synchronizer.py:48``)."""
    harness, ids, session_oid, gateway, chat, _release, _gated_speakers, _guard_ids, _guard_oid = capabilities_thread
    owner_id = str(ids[OWNER])
    participant_id = str(ids[PARTICIPANT])
    provider = harness.run(harness.db.admin_model_providers.find_one({"main_id": TENANT}))
    model_b = _seed_model_instance(harness, name="model-b", priority=2, provider_oid=provider["_id"])

    # Shared case: A pins model-b explicitly; B sends no model — B's own
    # resolution is the tenant default (model-a, priority 1), never A's model-b.
    first, outcome = _send(chat, harness, session_oid, user_id=owner_id, model_instance_id=model_b)
    assert outcome == "completed"
    binding_one = _current_binding(harness, session_oid)
    assert binding_one["model_instance_id"] == model_b
    assert binding_one["preset_id"] == "askai-enterprise"

    second, outcome = _send(chat, harness, session_oid, user_id=participant_id, model_instance_id=None)
    assert outcome == "completed"
    binding_two = _current_binding(harness, session_oid)
    assert binding_two["user_id"] == participant_id
    assert binding_two["model_instance_id"] != model_b
    assert binding_two["model_instance_id"] == harness.run(
        chat._profiles._compiler.compile(tenant_id=TENANT, user_id=participant_id, model_instance_id=None)
    ).model_instance_id
    assert binding_two["preset_id"] == "askai-enterprise"

    third, outcome = _send(chat, harness, session_oid, user_id=owner_id, model_instance_id=None)
    assert outcome == "completed"
    binding_three = _current_binding(harness, session_oid)
    assert binding_three["user_id"] == owner_id
    assert binding_three["model_instance_id"] == harness.run(
        chat._profiles._compiler.compile(tenant_id=TENANT, user_id=owner_id, model_instance_id=None)
    ).model_instance_id
    assert binding_three["preset_id"] == "askai-enterprise"

    # Solo case: the fallback is PRESERVED — a solo owner's no-model turn
    # inherits their previous model (model-b), NOT the tenant default.
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
    solo_first, outcome = _send(chat, harness, solo_oid, user_id=owner_id, model_instance_id=model_b)
    assert outcome == "completed"
    solo_second, outcome = _send(chat, harness, solo_oid, user_id=owner_id, model_instance_id=None)
    assert outcome == "completed"
    solo_binding = _current_binding(harness, solo_oid)
    assert solo_binding["model_instance_id"] == model_b


# ---------------------------------------------------------------------------
# Acceptance (vii) — the forbidden rotation optimization is impossible
# ---------------------------------------------------------------------------


def _stripped_hash(payload: dict[str, Any]) -> str:
    stripped = {key: value for key, value in payload.items() if key != "subject_user_id"}
    canonical = json.dumps(stripped, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_guard_removing_subject_user_id_from_the_hash_breaks_isolation_and_rotation(capabilities_thread, monkeypatch):
    """(vii) Guard: removing ``subject_user_id`` from the hashed payload makes
    BOTH the rotation-count assertion (ii) and the isolation assertion (i)
    fail. The guard pair's compiled payloads are byte-identical except
    ``subject_user_id`` — strip it and a speaker change stops rotating AND the
    new speaker's turn executes under the predecessor's profile (its subject —
    the tool token for their turn would be issued under the OTHER user's
    subject, ``profile/resolver.py:40-46``). The skill/tool-content dimension
    of (i) is pinned by the (i) test's direct-compile part (sabotage (a)
    bites it); this test demonstrates the leak the strip causes. The strip is
    in-test only (the monkeypatch auto-restores)."""
    harness, ids, session_oid, gateway, chat, _release, _gated_speakers, guard_ids, guard_oid = capabilities_thread
    guard_owner = str(guard_ids["guard-owner"])
    guard_participant = str(guard_ids["guard-participant"])
    monkeypatch.setattr(ModelProfileCompiler, "content_hash", staticmethod(_stripped_hash))

    first, outcome = _send(chat, harness, guard_oid, user_id=guard_owner, model_instance_id=None)
    assert outcome == "completed"
    second, outcome = _send(chat, harness, guard_oid, user_id=guard_participant, model_instance_id=None)
    assert outcome == "completed"

    binding = _current_binding(harness, guard_oid)
    # (ii)-violating state: the speaker change produced ZERO rotations — both
    # turns share one kernel session.
    assert len(gateway.created_sessions) == 1
    assert binding["user_id"] == guard_owner

    # (i)-violating state: the participant's turn executes under the OWNER's
    # compiled profile — its subject is the owner's, so the capability
    # identity of the participant's turn is the other user's.
    effective = harness.run(chat._profiles.get(str(binding["profile_version"])))
    assert effective.subject_user_id == guard_owner
