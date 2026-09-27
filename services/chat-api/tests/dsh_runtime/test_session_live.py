"""Real-mongod coverage for the durable session-live projection (T1).

QA-happy (plan row L98: coherent reads under concurrent durable writes,
canonical cursor round-trips, cold attach, valid resume behind the
high-water mark, the 201-row sentinel boundary from the safe side, the
exact LF-only frame sequence, invalidation frames, the no-ID accessor,
and the shared SessionReadAuthorizer) and QA-failure (plan row L99:
cursor-validation rejects, row gaps in both directions, the
non-contiguity regression guard, typed denials, the cumulative
byte-budget boundary, the control-frame no-ID rule, the bounded
reload-and-reopen anti-livelock, torn-snapshot recovery, and the
Settings env seam).
"""

# allow: SIZE_OK — one cohesive seam (SessionLiveService.poll plus the pure
# cursor codec and the shared authorizer); the frozen plan pins the whole
# T1 QA matrix to this single file (T3 extends it, so the path is fixed,
# not a choice).

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import string
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from bson import ObjectId

from app.core.config import Settings, get_settings
from app.dsh_runtime.bindings.repository import KernelBindingRepository
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.conversation.participants_repository import (
    SessionParticipantsRepository,
)
from app.dsh_runtime.contracts.events import KernelEventEnvelope, KernelEventSource
from app.dsh_runtime.contracts.kernel import TemporalContext
from app.dsh_runtime.events.durable_writer import DurableKernelEventWriter
from app.dsh_runtime.events.live_stream import LiveTurnStream
from app.dsh_runtime.errors import DshNotFoundError, DshRuntimeError
from app.dsh_runtime.events.repository import (
    KernelEventRepository,
    KernelEventWrite,
    StreamSequenceReservationError,
)
from app.dsh_runtime.events.turn_channel import TurnEventRegistry
from app.dsh_runtime.profile.models import RuntimeProfileSnapshot
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator
from app.dsh_runtime.turn_finalization import (
    TurnAssistantProjection,
    TurnFinalizationRetryableError,
    TurnStateFinalizer,
)
from app.dsh_runtime.turn_recovery import TurnTerminalRecovery
from app.dsh_runtime.turn_runner import DshTurnRunner
from app.dsh_runtime.session_access import (
    SessionReadAuthorizer,
    SessionReadDeniedError,
)
from app.dsh_runtime.session_live import (
    CURSOR_VERSION,
    EVENT_EXECUTION,
    EVENT_MEMBERS_CHANGED,
    EVENT_THREAD_CHANGED,
    EVENT_TURN_COMPLETED,
    EVENT_TURN_STARTED,
    FETCH_SENTINEL_ROWS,
    FRAME_BUDGET_BYTES,
    HEARTBEAT_COMMENT,
    REASON_CURSOR_GAP,
    REASON_CURSOR_INVALID,
    REASON_REPLAY_OVERFLOW,
    RESUME,
    SAFE_INT_MAX,
    InvalidLiveCursorError,
    SessionLiveService,
    build_live_cursor,
    classify_request,
    execution_frame_bytes,
    parse_live_cursor,
    public_execution_event,
)

TENANT = "tenant-a"
OTHER_TENANT = "tenant-b"
OWNER = "user-owner"
PARTICIPANT = "user-participant"
OTHER = "user-other"

# Any lowercase 64-hex value passes the cursor's revision format check
# (parse_live_cursor never matches it against the live digest), so minted
# test cursors carry this deterministic synthetic revision.
_SEEDED_REVISION = hashlib.sha256(b"session-live-test").hexdigest()

PROJECTIONS = KernelEventRepository.PROJECTIONS


def _service_kwargs(harness) -> dict[str, Any]:
    db = harness.db
    return {
        "conversations": ConversationRepository(db),
        "participants": SessionParticipantsRepository(db),
        "events": KernelEventRepository(db),
        "bindings": KernelBindingRepository(db),
        "authorizer": SessionReadAuthorizer(db),
    }


def _service(harness, *, heartbeat_seconds=None) -> SessionLiveService:
    return SessionLiveService(
        **_service_kwargs(harness), heartbeat_seconds=heartbeat_seconds
    )


def _create_session(harness, title="Live") -> dict[str, Any]:
    repo = ConversationRepository(harness.db)
    return harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title=title))


def _seed_participant(harness, session_id, user_id) -> None:
    repo = SessionParticipantsRepository(harness.db)
    harness.run(repo.add(tenant_id=TENANT, conversation_id=session_id, user_id=user_id))


def _remove_participant(harness, session_id, user_id) -> None:
    repo = SessionParticipantsRepository(harness.db)
    harness.run(repo.remove(session_id, tenant_id=TENANT, user_id=user_id))


def _append_message(harness, session_id, *, message_id, content="answer") -> dict[str, Any]:
    repo = ConversationRepository(harness.db)
    return harness.run(
        repo.append_message(
            conversation_id=session_id,
            tenant_id=TENANT,
            user_id=OWNER,
            role="assistant",
            content=content,
            message_id=message_id,
        )
    )


def _mark_active_run(harness, session_id, *, message_id, run_id) -> None:
    repo = ConversationRepository(harness.db)
    harness.run(
        repo.mark_active_run(
            conversation_id=session_id,
            tenant_id=TENANT,
            user_id=OWNER,
            message_id=message_id,
            run_id=run_id,
        )
    )


def _execution_row(
    message_id, *, seq, event_id=None, payload=None, stream_seq_raw=None
) -> dict[str, Any]:
    """One durable execution projection row in the shape list_for_message reads.

    The caller supplies DISTINCT event_id values: the projection collection
    declares a UNIQUE index on event_id (a repeat raises E11000 when the
    index exists). This suite never calls ensure_indexes, so the index does
    not exist here and the already-seen gap fixture's deliberate repeat
    seeds cleanly.
    """
    row: dict[str, Any] = {
        "message_id": message_id,
        "tenant_id": TENANT,
        "stream_seq": seq if stream_seq_raw is None else stream_seq_raw,
        "v": 1,
        "ts": None,
        "type": "item.delta",
        "item_kind": "final_answer",
        "item_id": f"item-{seq}",
        "payload": {"text": f"step-{seq}", "provisional": True}
        if payload is None
        else payload,
    }
    if event_id is not None:
        row["event_id"] = event_id
    return row


def _seed_execution_row(harness, message_id, **kwargs) -> None:
    async def seed():
        await harness.db[PROJECTIONS].insert_one(_execution_row(message_id, **kwargs))

    harness.run(seed())


def _seed_execution_rows(harness, message_id, *, seqs) -> None:
    for seq in seqs:
        _seed_execution_row(harness, message_id, seq=seq, event_id=f"evt-{message_id}-{seq}")


def _mint_cursor(
    session_id,
    *,
    last_message_seq,
    active_message_id,
    active_stream_seq,
    revision=_SEEDED_REVISION,
) -> str:
    return build_live_cursor(
        {
            "v": CURSOR_VERSION,
            "session_id": session_id,
            "revision": revision,
            "last_message_seq": last_message_seq,
            "active_message_id": active_message_id,
            "active_stream_seq": active_stream_seq,
        }
    )


def _cursor_param(raw: str) -> str:
    """Encode a hand-built cursor JSON (failure fixtures)."""
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _exec_stream_seqs(result, session_id) -> list[int]:
    """The replayed batch's stream_seqs, parsed from the emitted frame ids."""
    return [
        parse_live_cursor(frame.frame_id, session_id=session_id)["active_stream_seq"]
        for frame in result.frames
        if frame.event == EVENT_EXECUTION
    ]


def _assert_sole_control(result, *, event, reason=None) -> None:
    """One no-ID control frame, nothing else: no data beside it, no cursor."""
    assert result.kind == "control"
    assert len(result.frames) == 1
    frame = result.frames[0]
    assert frame.event == event
    assert frame.frame_id is None
    assert not frame.render().startswith("id: ")
    assert result.cursor is None
    if reason is not None:
        payload = json.loads(frame.data_json)
        assert payload["reason"] == reason
        assert "event_id" not in payload


class _TearingLiveService(SessionLiveService):
    """Runs one real durable write BEFORE the second digest read, so the
    poll is torn across moments without timing dependence."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._reads = 0
        self._tear = None

    async def _read_state(self, session_id, tenant_id):
        self._reads += 1
        if self._reads == 2 and self._tear is not None:
            await self._tear()
        return await super()._read_state(session_id, tenant_id)


def _tearing_service(harness, tear) -> _TearingLiveService:
    service = _TearingLiveService(**_service_kwargs(harness))
    service._tear = tear
    return service


class _WriteDuringPollService(SessionLiveService):
    """Runs a real durable write AFTER the first digest read, so new rows
    land inside the same poll's fetch deterministically (no timing
    dependence). Projection rows are not digest preimage, so the poll stays
    coherent despite the concurrent write."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._reads = 0
        self._midpoll_write = None

    async def _read_state(self, session_id, tenant_id):
        state = await super()._read_state(session_id, tenant_id)
        self._reads += 1
        if self._reads == 1 and self._midpoll_write is not None:
            await self._midpoll_write()
        return state


def _write_during_service(harness, write) -> _WriteDuringPollService:
    service = _WriteDuringPollService(**_service_kwargs(harness))
    service._midpoll_write = write
    return service


# ---------------------------------------------------------------------------
# QA-happy (plan row L98)
# ---------------------------------------------------------------------------


def test_coherent_single_poll_read_under_concurrent_durable_writes(real_mongo_db):
    """A poll concurrent with a durable projection write stays a coherent
    data read: projection rows are not digest preimage, so the concurrent
    write never tears the digest. The concurrent row may or may not be in
    this poll's fetch — either way the read stays ordered and idempotent,
    never a control, never an unbounded read."""
    harness = real_mongo_db
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-race"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-race")
    _seed_execution_rows(harness, message_id, seqs=[1, 2, 3])

    async def scenario():
        return await asyncio.gather(
            service.poll(session_id, tenant_id=TENANT, user_id=OWNER),
            harness.db[PROJECTIONS].insert_one(
                _execution_row(message_id, seq=4, event_id="evt-race-4")
            ),
        )

    result, _ = harness.run(scenario())

    assert result.kind == "data"
    seqs = _exec_stream_seqs(result, session_id)
    assert seqs == sorted(seqs)
    assert seqs in ([1, 2, 3], [1, 2, 3, 4])
    event_ids = [
        json.loads(frame.data_json)["event_id"]
        for frame in result.frames
        if frame.event == EVENT_EXECUTION
    ]
    assert len(set(event_ids)) == len(event_ids)


@pytest.mark.parametrize(
    ("last_message_seq", "active_message_id", "active_stream_seq"),
    [
        (0, None, None),
        (6, "msg-1", 7),
        (SAFE_INT_MAX, None, None),
        (0, "A" + "." * 127, SAFE_INT_MAX),
        (1, "msg.x:9-y_1", 0),
    ],
)
def test_canonical_cursor_round_trips_for_every_valid_field_combination(
    last_message_seq, active_message_id, active_stream_seq
):
    session_id = "a" * 24
    fields = {
        "v": CURSOR_VERSION,
        "session_id": session_id,
        "revision": _SEEDED_REVISION,
        "last_message_seq": last_message_seq,
        "active_message_id": active_message_id,
        "active_stream_seq": active_stream_seq,
    }

    cursor = build_live_cursor(fields)

    assert parse_live_cursor(cursor, session_id=session_id) == fields
    assert cursor == build_live_cursor(fields)
    assert "=" not in cursor
    assert set(cursor) <= set(string.ascii_letters + string.digits + "-_")


def test_cold_attach_with_pending_rows_emits_turn_started_and_rows_without_invalidation(real_mongo_db):
    harness = real_mongo_db
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-cold"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-cold")
    _seed_execution_rows(harness, message_id, seqs=[1, 2, 3])

    result = harness.run(service.poll(session_id, tenant_id=TENANT, user_id=OWNER))

    assert result.kind == "data"
    assert [frame.event for frame in result.frames] == [
        EVENT_TURN_STARTED,
        EVENT_EXECUTION,
        EVENT_EXECUTION,
        EVENT_EXECUTION,
    ]
    assert _exec_stream_seqs(result, session_id) == [1, 2, 3]
    assert not any(
        frame.event in (EVENT_THREAD_CHANGED, EVENT_MEMBERS_CHANGED)
        for frame in result.frames
    )
    fields = parse_live_cursor(result.cursor, session_id=session_id)
    assert fields["active_message_id"] == message_id
    assert fields["active_stream_seq"] == 3


def test_valid_resume_behind_high_water_picks_up_rows_landing_midpoll(real_mongo_db):
    """A valid resume several rows behind the high-water mark while the
    session concurrently receives NEW rows: the mid-poll rows land inside
    the same poll's fetch, the read stays coherent, and the trailing cursor
    continues from the last emitted row."""
    harness = real_mongo_db
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-resume"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-resume")
    _seed_execution_rows(harness, message_id, seqs=[1, 2, 3, 4])
    cursor = _mint_cursor(
        session_id, last_message_seq=1, active_message_id=message_id, active_stream_seq=1
    )

    async def midpoll():
        for seq in (5, 6):
            await harness.db[PROJECTIONS].insert_one(
                _execution_row(message_id, seq=seq, event_id=f"evt-resume-{seq}")
            )

    service = _write_during_service(harness, midpoll)

    result = harness.run(
        service.poll(session_id, tenant_id=TENANT, user_id=OWNER, last_event_id=cursor)
    )

    assert result.kind == "data"
    assert _exec_stream_seqs(result, session_id) == [2, 3, 4, 5, 6]
    assert not any(frame.event == EVENT_TURN_STARTED for frame in result.frames)
    fields = parse_live_cursor(result.cursor, session_id=session_id)
    assert fields["active_message_id"] == message_id
    assert fields["active_stream_seq"] == 6


def test_invalid_resume_emits_typed_cursor_invalid_control(real_mongo_db):
    harness = real_mongo_db
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])

    result = harness.run(
        service.poll(session_id, tenant_id=TENANT, user_id=OWNER, last_event_id="not-a-cursor")
    )

    _assert_sole_control(result, event=EVENT_THREAD_CHANGED, reason=REASON_CURSOR_INVALID)


def test_200_rows_one_under_the_sentinel_emit_all_as_data(real_mongo_db):
    harness = real_mongo_db
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-200"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-200")
    _seed_execution_rows(harness, message_id, seqs=list(range(1, 201)))

    result = harness.run(service.poll(session_id, tenant_id=TENANT, user_id=OWNER))

    assert result.kind == "data"
    assert _exec_stream_seqs(result, session_id) == list(range(1, 201))


def test_execution_frame_sequence_is_exact_lf_only(real_mongo_db):
    harness = real_mongo_db
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-lf"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-lf")
    _seed_execution_rows(harness, message_id, seqs=[1, 2, 3])

    result = harness.run(service.poll(session_id, tenant_id=TENANT, user_id=OWNER))

    assert result.kind == "data"
    exec_frames = [frame for frame in result.frames if frame.event == EVENT_EXECUTION]
    for frame in exec_frames:
        rendered = frame.render()
        assert rendered.startswith("id: ")
        assert "\r" not in rendered
        assert rendered.endswith("\n\n")
        assert rendered.count("\n\n") == 1
        lines = rendered.split("\n")
        assert len(lines) == 5
        assert lines[1] == f"event: {EVENT_EXECUTION}"
        assert lines[2].startswith("data: ")
        assert lines[3] == ""
        assert frame.byte_length() == len(rendered.encode("utf-8"))
        fields = parse_live_cursor(frame.frame_id, session_id=session_id)
        assert fields["active_message_id"] == message_id
    assert _exec_stream_seqs(result, session_id) == [1, 2, 3]


def test_members_changed_sole_frame_control_via_known_fingerprint(real_mongo_db):
    harness = real_mongo_db
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])
    _seed_participant(harness, session_id, PARTICIPANT)

    result = harness.run(
        service.poll(
            session_id,
            tenant_id=TENANT,
            user_id=OWNER,
            known_member_fingerprint="0" * 64,
        )
    )

    _assert_sole_control(result, event=EVENT_MEMBERS_CHANGED)
    payload = json.loads(result.frames[0].data_json)
    assert set(payload) == {"session_id", "revision"}
    assert payload["session_id"] == session_id
    assert len(payload["revision"]) == 64
    assert result.member_fingerprint != "0" * 64


def test_heartbeat_comment_present_on_data_and_heartbeat_only_responses(real_mongo_db):
    harness = real_mongo_db
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-beat"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-beat")
    _seed_execution_rows(harness, message_id, seqs=[1, 2])

    async def tear():
        await harness.db.chat_sessions.update_one(
            {"_id": ObjectId(session_id)}, {"$set": {"updated_at": datetime.utcnow()}}
        )

    torn = _tearing_service(harness, tear)

    data = harness.run(_service(harness).poll(session_id, tenant_id=TENANT, user_id=OWNER))
    assert data.kind == "data"
    assert data.heartbeat_comment == HEARTBEAT_COMMENT

    only = harness.run(torn.poll(session_id, tenant_id=TENANT, user_id=OWNER))
    assert only.kind == "heartbeat"
    assert only.frames == ()
    assert only.heartbeat_comment == HEARTBEAT_COMMENT


def test_no_id_accessor_without_token_leakage(real_mongo_db):
    harness = real_mongo_db
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-leak"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-leak")
    _seed_execution_row(
        harness,
        message_id,
        seq=1,
        event_id="evt-leak-1",
        payload={
            "text": "secret scan",
            "provisional": True,
            "tenant_id": TENANT,
            "user_id": OWNER,
            "storage_key": "bucket/path",
            "path": "/etc/passwd",
            "internal": {"nested": "value"},
            "metadata": {"a": 1},
            "url": "javascript:alert(1)",
        },
    )

    result = harness.run(service.poll(session_id, tenant_id=TENANT, user_id=OWNER))

    assert result.kind == "data"
    exec_frames = [frame for frame in result.frames if frame.event == EVENT_EXECUTION]
    # the allowlist drops everything but text/provisional for item.delta
    assert json.loads(exec_frames[0].data_json)["payload"] == {
        "text": "secret scan",
        "provisional": True,
    }
    for frame in result.frames:
        payload = json.loads(frame.data_json)
        assert "user_id" not in payload
        assert "tenant_id" not in payload
        assert "storage_key" not in payload
        blob = json.dumps(payload)
        assert TENANT not in blob
        assert "javascript:" not in blob
        assert "/etc/passwd" not in blob
    assert exec_frames[0].frame_id is not None

    # the recursive sanitizer strips nested storage/ID keys and non-HTTP(S)
    # URL values at ANY depth, and keeps the fixed twelve-key shape
    public_event = public_execution_event(
        {
            "v": 1,
            "event_id": "evt-tool",
            "id": "cursor-x",
            "ts": None,
            "type": "item.completed",
            "item_kind": "tool",
            "item_id": "item-t",
            "parent_item_id": "item-p",
            "revision": None,
            "stream_seq": 1,
            "stream_seq_end": None,
            "payload": {
                "name": "tool",
                "callId": "c1",
                "args": {"path": "/etc/passwd", "tenant_id": TENANT, "deep": "data:text/html,x"},
                "result_summary": "ftp://host/file",
            },
        }
    )
    assert list(public_event) == [
        "v",
        "event_id",
        "id",
        "ts",
        "type",
        "item_kind",
        "item_id",
        "parent_item_id",
        "revision",
        "stream_seq",
        "stream_seq_end",
        "payload",
    ]
    assert public_event["payload"] == {"name": "tool", "callId": "c1", "args": {}}


def test_authorizer_grants_the_owner_role(real_mongo_db):
    harness = real_mongo_db
    session = _create_session(harness)
    authorizer = SessionReadAuthorizer(harness.db)

    lease = harness.run(
        authorizer.authorize_read(str(session["_id"]), tenant_id=TENANT, user_id=OWNER)
    )

    assert lease.role == "owner"
    assert lease.user_id == OWNER
    assert lease.session_id == str(session["_id"])


def test_authorizer_grants_the_active_participant_role(real_mongo_db):
    harness = real_mongo_db
    session = _create_session(harness)
    _seed_participant(harness, str(session["_id"]), PARTICIPANT)
    authorizer = SessionReadAuthorizer(harness.db)

    lease = harness.run(
        authorizer.authorize_read(str(session["_id"]), tenant_id=TENANT, user_id=PARTICIPANT)
    )

    assert lease.role == "participant"


@pytest.mark.parametrize(
    ("tenant_id", "user_id", "removed"),
    [
        (TENANT, "user-removed", True),
        (TENANT, OTHER, False),
        (OTHER_TENANT, PARTICIPANT, False),
    ],
)
def test_authorizer_denies_removed_member_non_member_and_cross_tenant(
    real_mongo_db, tenant_id, user_id, removed
):
    harness = real_mongo_db
    session = _create_session(harness)
    session_id = str(session["_id"])
    if removed:
        _seed_participant(harness, session_id, user_id)
        _remove_participant(harness, session_id, user_id)
    authorizer = SessionReadAuthorizer(harness.db)

    with pytest.raises(SessionReadDeniedError):
        harness.run(authorizer.authorize_read(session_id, tenant_id=tenant_id, user_id=user_id))


# ---------------------------------------------------------------------------
# QA-failure: cursor validation (plan row L99)
# ---------------------------------------------------------------------------


def _cursor_json_with(session_id, override: str) -> str:
    return (
        '{"v":1,'
        '"session_id":"' + session_id + '",'
        '"revision":"' + _SEEDED_REVISION + '",'
        + override
        + ',"active_message_id":null,'
        '"active_stream_seq":null}'
    )


@pytest.mark.parametrize("shape", ["duplicate-key", "extra-key"])
def test_cursor_duplicate_and_extra_keys_are_rejected(shape):
    session_id = "a" * 24
    head = _cursor_json_with(session_id, '"last_message_seq":0')
    if shape == "duplicate-key":
        raw = head[:-1] + ',"last_message_seq":0}'
    else:
        raw = head[:-1] + ',"extra":1}'
    cursor = _cursor_param(raw)

    with pytest.raises(InvalidLiveCursorError):
        parse_live_cursor(cursor, session_id=session_id)


@pytest.mark.parametrize(
    "override",
    [
        '"last_message_seq":"5"',
        '"last_message_seq":5.0',
        '"last_message_seq":1e1',
        '"last_message_seq":-1',
    ],
)
def test_cursor_alternate_integer_spellings_are_rejected(override):
    session_id = "a" * 24
    cursor = _cursor_param(_cursor_json_with(session_id, override))

    with pytest.raises(InvalidLiveCursorError):
        parse_live_cursor(cursor, session_id=session_id)


def test_cursor_boolean_version_spelling_is_rejected():
    session_id = "a" * 24
    raw = (
        '{"v":true,'
        '"session_id":"' + session_id + '",'
        '"revision":"' + _SEEDED_REVISION + '",'
        '"last_message_seq":0,'
        '"active_message_id":null,'
        '"active_stream_seq":null}'
    )

    with pytest.raises(InvalidLiveCursorError):
        parse_live_cursor(_cursor_param(raw), session_id=session_id)


def test_cursor_with_default_json_separators_is_non_canonical():
    # same fields, same order, but the compact re-encode cannot match the
    # spaced encoding: a byte mismatch on re-encode is non-canonical
    session_id = "a" * 24
    raw = json.dumps(
        {
            "v": 1,
            "session_id": session_id,
            "revision": _SEEDED_REVISION,
            "last_message_seq": 0,
            "active_message_id": None,
            "active_stream_seq": None,
        }
    )

    with pytest.raises(InvalidLiveCursorError):
        parse_live_cursor(_cursor_param(raw), session_id=session_id)


def test_cursor_with_wrong_key_order_is_rejected():
    session_id = "a" * 24
    raw = (
        '{"revision":"' + _SEEDED_REVISION + '",'
        '"v":1,'
        '"session_id":"' + session_id + '",'
        '"last_message_seq":0,'
        '"active_message_id":null,'
        '"active_stream_seq":null}'
    )

    with pytest.raises(InvalidLiveCursorError):
        parse_live_cursor(_cursor_param(raw), session_id=session_id)


def test_cursor_undecodable_padded_and_bad_alphabet_values_are_rejected():
    session_id = "a" * 24
    fields = {
        "v": 1,
        "session_id": session_id,
        "revision": _SEEDED_REVISION,
        "last_message_seq": 0,
        "active_message_id": None,
        "active_stream_seq": None,
    }
    canonical = build_live_cursor(fields)

    with pytest.raises(InvalidLiveCursorError):
        parse_live_cursor(_cursor_param("not json at all"), session_id=session_id)
    with pytest.raises(InvalidLiveCursorError):
        # padding retained: the canonical alphabet forbids '='
        parse_live_cursor(canonical + "=", session_id=session_id)
    with pytest.raises(InvalidLiveCursorError):
        parse_live_cursor("!!!", session_id=session_id)


@pytest.mark.parametrize("shape", ["wrong-session", "wrong-v"])
def test_cursor_wrong_session_and_wrong_version_are_rejected(shape):
    session_id = "a" * 24
    if shape == "wrong-session":
        cursor = _mint_cursor(
            "f" * 24, last_message_seq=0, active_message_id=None, active_stream_seq=None
        )
        # the session mismatch is checked at parse time
        with pytest.raises(InvalidLiveCursorError):
            parse_live_cursor(cursor, session_id=session_id)
    else:
        # a wrong version is rejected at MINT time: build_live_cursor never
        # produces one, so the guarantee holds one step earlier than parse
        with pytest.raises(InvalidLiveCursorError):
            build_live_cursor(
                {
                    "v": 2,
                    "session_id": session_id,
                    "revision": _SEEDED_REVISION,
                    "last_message_seq": 0,
                    "active_message_id": None,
                    "active_stream_seq": None,
                }
            )


def test_above_high_water_cursor_is_rejected_via_the_s1_probe(real_mongo_db):
    harness = real_mongo_db
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-high"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-high")
    _seed_execution_rows(harness, message_id, seqs=[1, 2, 3])
    # last_message_seq passes the durable high-water check; the active
    # position points above the stored rows, so the S-1 probe finds nothing
    cursor = _mint_cursor(
        session_id, last_message_seq=1, active_message_id=message_id, active_stream_seq=5
    )

    result = harness.run(
        service.poll(session_id, tenant_id=TENANT, user_id=OWNER, last_event_id=cursor)
    )

    _assert_sole_control(result, event=EVENT_THREAD_CHANGED, reason=REASON_CURSOR_INVALID)


@pytest.mark.parametrize(
    "rows_spec",
    [
        [(1, "evt-a"), (2, "evt-b"), (2, "evt-c")],
        [(1, "evt-a"), (2, "evt-b"), (3, None)],
        [(1, "evt-a"), (2, "evt-b"), (3, "")],
        [(1, "evt-a"), (2, "evt-b"), (3, "evt-a")],
    ],
    ids=["repeated-seq", "absent-event-id", "empty-event-id", "already-seen"],
)
def test_cursor_gap_variants_yield_no_id_invalidation(real_mongo_db, rows_spec):
    """A replayed row whose stream_seq is repeated, or whose event_id is
    absent, empty, or already seen in the same replay, is a ROW GAP: the
    no-ID invalidation carries reason cursor_gap. The unique event_id index
    is deliberately ABSENT here (this suite never calls ensure_indexes), so
    the already-seen fixture can seed a repeated event_id."""
    harness = real_mongo_db
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-gap"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-gap")
    for seq, event_id in rows_spec:
        _seed_execution_row(harness, message_id, seq=seq, event_id=event_id)

    result = harness.run(service.poll(session_id, tenant_id=TENANT, user_id=OWNER))

    _assert_sole_control(result, event=EVENT_THREAD_CHANGED, reason=REASON_CURSOR_GAP)


def test_cursor_gap_decreasing_storage_order_is_normalized_before_the_scan(real_mongo_db):
    """A decreasing STORAGE order (seq 2 written before seq 1) must NOT trip
    cursor_gap: the repository sorts the fetch by stream_seq ascending and
    its typed $gt filter admits only numeric ordinals, so the replayed batch
    the gap scan sees is normalized before the scan — a strictly-decreasing
    REPLAYED batch is unreachable through the public fetch. The tie (the
    repeated-seq case above) is the only observable non-monotonicity, and it
    fires the same `row_seq <= previous_seq` predicate; this test is the
    non-misfire guard for the decreasing side."""
    harness = real_mongo_db
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-decreasing"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-decreasing")
    _seed_execution_row(harness, message_id, seq=2, event_id="evt-d2")
    _seed_execution_row(harness, message_id, seq=1, event_id="evt-d1")

    result = harness.run(service.poll(session_id, tenant_id=TENANT, user_id=OWNER))

    assert result.kind == "data"
    assert _exec_stream_seqs(result, session_id) == [1, 2]


def test_non_contiguous_healthy_ordinals_resume_from_the_correct_position(real_mongo_db):
    """A healthy multi-batch message whose ordinals are non-contiguous
    BECAUSE blocks were reserved (4-9 deliberately abandoned) must NOT trip
    cursor_gap, must resume successfully, and the client must continue from
    the correct active_stream_seq — the regression guard against
    contiguity-based misfire."""
    harness = real_mongo_db
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-blocks"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-blocks")
    _seed_execution_rows(harness, message_id, seqs=[1, 2, 3, 10, 11, 12])
    cursor = _mint_cursor(
        session_id, last_message_seq=1, active_message_id=message_id, active_stream_seq=3
    )

    result = harness.run(
        service.poll(session_id, tenant_id=TENANT, user_id=OWNER, last_event_id=cursor)
    )

    assert result.kind == "data"
    assert _exec_stream_seqs(result, session_id) == [10, 11, 12]
    fields = parse_live_cursor(result.cursor, session_id=session_id)
    assert fields["active_stream_seq"] == 12


def test_non_contiguous_healthy_ordinals_cold_attach_emits_all_rows(real_mongo_db):
    harness = real_mongo_db
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-blocks-cold"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-blocks")
    _seed_execution_rows(harness, message_id, seqs=[1, 2, 3, 10, 11, 12])

    result = harness.run(service.poll(session_id, tenant_id=TENANT, user_id=OWNER))

    assert result.kind == "data"
    assert _exec_stream_seqs(result, session_id) == [1, 2, 3, 10, 11, 12]


def test_missing_session_is_a_typed_denial_not_a_500(real_mongo_db):
    harness = real_mongo_db
    service = _service(harness)
    authorizer = SessionReadAuthorizer(harness.db)

    with pytest.raises(SessionReadDeniedError):
        harness.run(authorizer.authorize_read("f" * 24, tenant_id=TENANT, user_id=OWNER))
    with pytest.raises(SessionReadDeniedError) as excinfo:
        harness.run(service.poll("f" * 24, tenant_id=TENANT, user_id=OWNER))
    assert isinstance(excinfo.value, LookupError)


def test_terminal_run_without_an_active_claim_yields_zero_frames_data(real_mongo_db):
    harness = real_mongo_db
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])
    _append_message(harness, session_id, message_id="msg-done")
    _mark_active_run(harness, session_id, message_id="msg-done", run_id="run-done")
    harness.run(
        harness.db.chat_sessions.update_one(
            {"_id": ObjectId(session_id)}, {"$unset": {"active_run": ""}}
        )
    )

    result = harness.run(service.poll(session_id, tenant_id=TENANT, user_id=OWNER))

    assert result.kind == "data"
    assert result.frames == ()


def test_exactly_201_rows_emit_replay_overflow(real_mongo_db):
    harness = real_mongo_db
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-201"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-201")
    _seed_execution_rows(harness, message_id, seqs=list(range(1, 202)))

    result = harness.run(service.poll(session_id, tenant_id=TENANT, user_id=OWNER))

    _assert_sole_control(result, event=EVENT_THREAD_CHANGED, reason=REASON_REPLAY_OVERFLOW)


def _budget_setup(harness):
    """Seed a tracked run with three small rows; return the service, the
    session id, the message id, the first poll's observed execution-frame
    byte total, and the byte overhead of one more row (computed from the
    OBSERVED revision and the OBSERVED cursor fields, so the expected total
    is derived from the poll's own output plus the chosen fill)."""
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-budget"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-budget")
    _seed_execution_rows(harness, message_id, seqs=[1, 2, 3])
    first = harness.run(service.poll(session_id, tenant_id=TENANT, user_id=OWNER))
    assert first.kind == "data"
    fields = parse_live_cursor(first.cursor, session_id=session_id)
    total = sum(
        frame.byte_length() for frame in first.frames if frame.event == EVENT_EXECUTION
    )
    frame_id = build_live_cursor(
        {
            "v": CURSOR_VERSION,
            "session_id": session_id,
            "revision": first.revision,
            "last_message_seq": fields["last_message_seq"],
            "active_message_id": fields["active_message_id"],
            "active_stream_seq": 4,
        }
    )
    overhead = execution_frame_bytes(
        frame_id,
        json.dumps(
            public_execution_event(
                {
                    "v": 1,
                    "event_id": "evt-budget-4",
                    "id": None,
                    "ts": None,
                    "type": "item.delta",
                    "item_kind": "final_answer",
                    "item_id": "item-4",
                    "parent_item_id": None,
                    "revision": None,
                    "stream_seq": 4,
                    "stream_seq_end": None,
                    "payload": {"text": "", "provisional": True},
                }
            ),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )
    return service, session_id, message_id, total, overhead


def _seed_budget_fill(harness, message_id, fill: int) -> None:
    async def seed():
        await harness.db[PROJECTIONS].insert_one(
            _execution_row(
                message_id,
                seq=4,
                event_id="evt-budget-4",
                payload={"text": "x" * fill, "provisional": True},
            )
        )

    harness.run(seed())


def test_cumulative_frame_budget_exactly_262144_bytes_succeeds(real_mongo_db):
    harness = real_mongo_db
    service, session_id, message_id, total, overhead = _budget_setup(harness)
    fill = FRAME_BUDGET_BYTES - total - overhead
    assert fill > 0
    _seed_budget_fill(harness, message_id, fill)

    result = harness.run(service.poll(session_id, tenant_id=TENANT, user_id=OWNER))

    assert result.kind == "data"
    exec_frames = [frame for frame in result.frames if frame.event == EVENT_EXECUTION]
    assert len(exec_frames) == 4
    assert sum(frame.byte_length() for frame in exec_frames) == FRAME_BUDGET_BYTES
    assert all("\r" not in frame.render() for frame in exec_frames)


def test_cumulative_frame_budget_exactly_262145_bytes_emits_replay_overflow_only(real_mongo_db):
    harness = real_mongo_db
    service, session_id, message_id, total, overhead = _budget_setup(harness)
    fill = FRAME_BUDGET_BYTES + 1 - total - overhead
    assert fill > 0
    _seed_budget_fill(harness, message_id, fill)

    result = harness.run(service.poll(session_id, tenant_id=TENANT, user_id=OWNER))

    _assert_sole_control(result, event=EVENT_THREAD_CHANGED, reason=REASON_REPLAY_OVERFLOW)
    assert not any(frame.event == EVENT_EXECUTION for frame in result.frames)


def test_no_control_frame_ever_carries_an_id(real_mongo_db):
    """All control frames carry frame_id=None: the constructor and the
    service never put an ID on control output — an ID on a control frame is
    rejected by design. Sweeps every control path: cursor_invalid (bad and
    overlong cursor), members.changed, and cursor_gap (a cold attach over a
    repeated-seq replay)."""
    harness = real_mongo_db
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-ctrl"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-ctrl")
    for seq, event_id in ((1, "evt-c1"), (2, "evt-c2"), (2, "evt-c3")):
        _seed_execution_row(harness, message_id, seq=seq, event_id=event_id)
    service = _service(harness)

    controls = [
        harness.run(
            service.poll(session_id, tenant_id=TENANT, user_id=OWNER, last_event_id="garbage")
        ),
        harness.run(
            service.poll(session_id, tenant_id=TENANT, user_id=OWNER, last_event_id="x" * 4096)
        ),
        harness.run(
            service.poll(
                session_id, tenant_id=TENANT, user_id=OWNER, known_member_fingerprint="0" * 64
            )
        ),
        harness.run(service.poll(session_id, tenant_id=TENANT, user_id=OWNER)),
    ]

    for result in controls:
        assert result.kind == "control"
        for frame in result.frames:
            assert frame.frame_id is None
            assert not frame.render().startswith("id: ")


def test_members_changed_wins_over_pending_execution_rows(real_mongo_db):
    """A session where the member fingerprint changed while execution rows
    were also pending: the members.changed sole-frame control is emitted and
    the pending data is dropped — never mixed into one response."""
    harness = real_mongo_db
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-memb"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-memb")
    _seed_execution_rows(harness, message_id, seqs=[1, 2])

    result = harness.run(
        service.poll(
            session_id,
            tenant_id=TENANT,
            user_id=OWNER,
            known_member_fingerprint="0" * 64,
        )
    )

    _assert_sole_control(result, event=EVENT_MEMBERS_CHANGED)
    assert set(json.loads(result.frames[0].data_json)) == {"session_id", "revision"}


def test_bounded_reload_reopen_cycle_reaches_data_within_two_requests(real_mongo_db):
    """A session ACTIVELY RECEIVING execution rows while the client performs
    the reload-and-reopen cycle, with the write rate BOUNDED to at most 200
    new execution rows between the authoritative read and the reopen: the
    post-read backlog stays inside the 201-row sentinel, the cycle reaches a
    DATA response within two requests, and — asserted against
    classify_request()/build_live_cursor() DIRECTLY — the reopen position is
    always a canonical valid RESUME cursor, so the cycle never repeats
    thread.changed indefinitely."""
    harness = real_mongo_db
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-cycle"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-cycle")
    _seed_execution_rows(harness, message_id, seqs=[1, 2, 3, 4, 5])

    first = harness.run(service.poll(session_id, tenant_id=TENANT, user_id=OWNER))
    assert first.kind == "data"

    _seed_execution_rows(harness, message_id, seqs=list(range(6, 206)))

    second = harness.run(
        service.poll(session_id, tenant_id=TENANT, user_id=OWNER, after=first.cursor)
    )
    assert second.kind == "data"
    assert _exec_stream_seqs(second, session_id) == list(range(6, 206))
    assert not any(frame.event == EVENT_THREAD_CHANGED for frame in first.frames)
    assert not any(frame.event == EVENT_THREAD_CHANGED for frame in second.frames)

    reopen_fields = parse_live_cursor(second.cursor, session_id=session_id)
    for _ in range(5):
        fresh = build_live_cursor(reopen_fields)
        assert classify_request(None, fresh) == RESUME
        assert parse_live_cursor(fresh, session_id=session_id) == reopen_fields


def test_failure_matrix_sweep_no_500_no_fabricated_event_no_unbounded_read(real_mongo_db):
    """Sweep assertion across the failure matrix: no response is a 500 (a
    bare non-typed exception), a fabricated event, or an unbounded read.
    Every frame event is in the fixed set; control responses carry exactly
    one no-ID frame and no cursor; data responses stay bounded; heartbeat
    responses carry no frames; denials are typed."""
    harness = real_mongo_db

    def _gap_poll():
        session = _create_session(harness)
        session_id = str(session["_id"])
        message_id = "msg-sweep-gap"
        _append_message(harness, session_id, message_id=message_id)
        _mark_active_run(harness, session_id, message_id=message_id, run_id="run-gap")
        for seq, event_id in ((1, "evt-g1"), (2, "evt-g2"), (2, "evt-g3")):
            _seed_execution_row(harness, message_id, seq=seq, event_id=event_id)
        return _service(harness).poll(session_id, tenant_id=TENANT, user_id=OWNER)

    def _overflow_poll():
        session = _create_session(harness)
        session_id = str(session["_id"])
        message_id = "msg-sweep-overflow"
        _append_message(harness, session_id, message_id=message_id)
        _mark_active_run(harness, session_id, message_id=message_id, run_id="run-overflow")
        _seed_execution_rows(harness, message_id, seqs=list(range(1, 202)))
        return _service(harness).poll(session_id, tenant_id=TENANT, user_id=OWNER)

    def _no_active_run_poll():
        session = _create_session(harness)
        return _service(harness).poll(str(session["_id"]), tenant_id=TENANT, user_id=OWNER)

    def _terminal_no_claim_poll():
        session = _create_session(harness)
        session_id = str(session["_id"])
        _append_message(harness, session_id, message_id="msg-sweep-term")
        _mark_active_run(harness, session_id, message_id="msg-sweep-term", run_id="run-term")
        harness.run(
            harness.db.chat_sessions.update_one(
                {"_id": ObjectId(session_id)}, {"$unset": {"active_run": ""}}
            )
        )
        return _service(harness).poll(session_id, tenant_id=TENANT, user_id=OWNER)

    service = _service(harness)
    base_id = str(_create_session(harness)["_id"])
    results = [
        ("invalid-resume", harness.run(service.poll(base_id, tenant_id=TENANT, user_id=OWNER, last_event_id="garbage"))),
        ("overlong-cursor", harness.run(service.poll(base_id, tenant_id=TENANT, user_id=OWNER, last_event_id="x" * 4096))),
        ("members-changed", harness.run(service.poll(base_id, tenant_id=TENANT, user_id=OWNER, known_member_fingerprint="0" * 64))),
        ("cursor-gap", harness.run(_gap_poll())),
        ("replay-overflow", harness.run(_overflow_poll())),
        ("no-active-run", harness.run(_no_active_run_poll())),
        ("terminal-no-claim", harness.run(_terminal_no_claim_poll())),
    ]
    with pytest.raises(SessionReadDeniedError):
        harness.run(service.poll("f" * 24, tenant_id=TENANT, user_id=OWNER))

    for name, result in results:
        events = {frame.event for frame in result.frames}
        assert events <= {
            EVENT_THREAD_CHANGED,
            EVENT_TURN_STARTED,
            EVENT_EXECUTION,
            EVENT_TURN_COMPLETED,
            EVENT_MEMBERS_CHANGED,
        }, name
        if result.kind == "control":
            assert len(result.frames) == 1, name
            assert result.frames[0].frame_id is None, name
            assert result.cursor is None, name
        elif result.kind == "data":
            assert len(result.frames) <= FETCH_SENTINEL_ROWS + 1, name
        else:
            assert result.frames == (), name


def test_torn_snapshot_poll_emits_no_data_frame_and_next_poll_recovers(real_mongo_db):
    """First read coherent, re-read diverged: the torn poll yields NO data
    frame (heartbeat-only, no data and no control) and the next poll
    recovers with the coherent data frames."""
    harness = real_mongo_db
    session = _create_session(harness)
    session_id = str(session["_id"])
    message_id = "msg-torn"
    _append_message(harness, session_id, message_id=message_id)
    _mark_active_run(harness, session_id, message_id=message_id, run_id="run-torn")
    _seed_execution_rows(harness, message_id, seqs=[1, 2])

    async def tear():
        await harness.db.chat_sessions.update_one(
            {"_id": ObjectId(session_id)}, {"$set": {"updated_at": datetime.utcnow()}}
        )

    torn = _tearing_service(harness, tear)

    first = harness.run(torn.poll(session_id, tenant_id=TENANT, user_id=OWNER))
    assert first.kind == "heartbeat"
    assert first.frames == ()
    assert first.heartbeat_comment == HEARTBEAT_COMMENT

    second = harness.run(torn.poll(session_id, tenant_id=TENANT, user_id=OWNER))
    assert second.kind == "data"
    assert _exec_stream_seqs(second, session_id) == [1, 2]


def test_overlong_4096_char_cursor_is_rejected_as_cursor_invalid(real_mongo_db):
    harness = real_mongo_db
    service = _service(harness)
    session = _create_session(harness)
    session_id = str(session["_id"])
    cursor = "x" * 4096
    assert len(cursor) == 4096

    result = harness.run(
        service.poll(session_id, tenant_id=TENANT, user_id=OWNER, last_event_id=cursor)
    )

    _assert_sole_control(result, event=EVENT_THREAD_CHANGED, reason=REASON_CURSOR_INVALID)
    payload = json.loads(result.frames[0].data_json)
    assert "event_id" not in payload


# ---------------------------------------------------------------------------
# QA-failure: Settings env seam (plan row L99, lru_cache leak guard)
# ---------------------------------------------------------------------------


def test_settings_reads_session_live_heartbeat_from_env(monkeypatch):
    monkeypatch.setenv("SESSION_LIVE_HEARTBEAT_SECONDS", "2.5")
    get_settings.cache_clear()
    try:
        assert Settings().SESSION_LIVE_HEARTBEAT_SECONDS == 2.5
    finally:
        get_settings.cache_clear()


def test_settings_session_live_heartbeat_defaults_to_fifteen(monkeypatch):
    monkeypatch.delenv("SESSION_LIVE_HEARTBEAT_SECONDS", raising=False)
    get_settings.cache_clear()
    try:
        assert Settings().SESSION_LIVE_HEARTBEAT_SECONDS == 15.0
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# T3: durable cursors, terminal convergence, process-restart recovery
# ---------------------------------------------------------------------------

T3_KERNEL = "kernel-t3"
T3_PROFILE = "profile-t3"


class _T3Profiles:
    def __init__(self) -> None:
        self._snapshots: dict[str, RuntimeProfileSnapshot] = {}

    async def get(self, profile_version: str) -> RuntimeProfileSnapshot:
        snapshot = self._snapshots.get(profile_version)
        if snapshot is None:
            snapshot = RuntimeProfileSnapshot(
                profile_version=profile_version,
                content_hash="0" * 64,
                tenant_id=TENANT,
                model_source_tenant_id=TENANT,
                model_instance_id="model-1",
                provider_id="provider-1",
                provider_type="openai_compatible",
                provider_name="Provider",
                model_name="Model",
                display_name="Model",
                capabilities=(),
            )
            self._snapshots[profile_version] = snapshot
        return snapshot


class _T3Gateway:
    """Deterministic gateway fake: replay, block, fail, or vanish on demand."""

    def __init__(
        self,
        events: list[KernelEventEnvelope] | None = None,
        *,
        send_error: Exception | None = None,
        events_error: Exception | None = None,
    ) -> None:
        self._events = list(events or [])
        self._send_error = send_error
        self._events_error = events_error
        self.subscribed = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()

    async def send(self, request: Any) -> None:
        if self._send_error is not None:
            raise self._send_error

    async def subscribe(self, session_id: str, after_cursor: int = 0):
        for event in self._events:
            if event.session_id != session_id or event.cursor <= int(after_cursor):
                continue
            yield event
            self.subscribed.set()
            await self.release.wait()

    async def events_once(self, session_id: str, after_cursor: int = 0) -> list[KernelEventEnvelope]:
        if self._events_error is not None:
            raise self._events_error
        return [
            event
            for event in self._events
            if event.session_id == session_id and event.cursor > int(after_cursor)
        ]

    async def discover_runtime(self, *, tenant_id: str, profile_version: str, isolation_key: str):
        return SimpleNamespace(runtime_id="runtime-t3", kernel_version="test-kernel")

    def attach_session(self, **kwargs: Any) -> None:
        return None

    async def resume_session(self, session_id: str) -> None:
        return None

    async def refresh_session_credentials(self, session_id: str) -> None:
        return None


def _t3_envelope(event_id: str, cursor: int, event_type: str, **payload: Any) -> KernelEventEnvelope:
    return KernelEventEnvelope(
        event_id=event_id,
        runtime_id="runtime-t3",
        session_id=T3_KERNEL,
        profile_version=T3_PROFILE,
        cursor=cursor,
        type=event_type,
        occurred_at=datetime.now(timezone.utc),
        payload=payload,
        source=KernelEventSource(kernel_version="test-kernel"),
    )


def _t3_context() -> TemporalContext:
    now = datetime.now(timezone.utc)
    return TemporalContext(captured_at_utc=now, user_local_time=now, user_timezone="UTC")


def _t3_seed_claimed_turn(
    harness, *, message_id: str = "msg-t3", title: str = "T3"
) -> tuple[str, str, dict[str, Any]]:
    conversations = ConversationRepository(harness.db)
    session = harness.run(conversations.create(tenant_id=TENANT, user_id=OWNER, title=title))
    session_id = str(session["_id"])
    harness.run(
        conversations.append_message(
            conversation_id=session_id,
            tenant_id=TENANT,
            user_id=OWNER,
            role="assistant",
            content="",
            message_id=message_id,
        )
    )
    bindings = KernelBindingRepository(harness.db)
    created = harness.run(
        bindings.create(
            tenant_id=TENANT,
            user_id=OWNER,
            conversation_id=session_id,
            kernel_session_id=T3_KERNEL,
            runtime_id="runtime-t3",
            profile_version=T3_PROFILE,
            model_instance_id="model-1",
            kernel_version="test-kernel",
        )
    )
    claimed = harness.run(
        bindings.claim_turn_authorized(
            str(created["binding_id"]),
            message_id=message_id,
            request_id=f"turn-{message_id}",
            claim_token=f"token-{message_id}",
            turn_metadata={"initiator_user_id": OWNER},
        )
    )
    harness.run(
        conversations.mark_active_run(
            conversation_id=session_id,
            tenant_id=TENANT,
            user_id=OWNER,
            message_id=message_id,
            run_id=str(claimed["active_turn"]["request_id"]),
        )
    )
    return session_id, message_id, claimed


def _t3_runner(harness, gateway: Any) -> DshTurnRunner:
    return DshTurnRunner(
        gateway=gateway,
        conversations=ConversationRepository(harness.db),
        bindings=KernelBindingRepository(harness.db),
        events=KernelEventRepository(harness.db),
        profiles=_T3Profiles(),
        kernel_version="test-kernel",
    )


def _t3_rows(harness, message_id: str) -> list[dict[str, Any]]:
    repo = KernelEventRepository(harness.db)
    return harness.run(repo.all_for_message(message_id, tenant_id=TENANT, user_id=OWNER))


def _t3_binding(harness, session_id: str) -> dict[str, Any]:
    return harness.run(
        KernelBindingRepository(harness.db).current(
            session_id, tenant_id=TENANT, user_id=OWNER
        )
    )


def _t3_session_doc(harness, session_id: str) -> dict[str, Any]:
    return harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))


def _t3_run(
    harness, runner: DshTurnRunner, binding: dict[str, Any], message_id: str, *, text: str = "hello"
) -> str:
    return harness.run(
        runner.run(
            binding=binding,
            message_id=message_id,
            request_id=f"req-{message_id}",
            text=text,
            temporal_context=_t3_context(),
            live_stream=LiveTurnStream(),
        )
    )


def _t3_assert_normalized(rows: list[dict[str, Any]]) -> list[int]:
    seqs = [int(row["stream_seq"]) for row in rows]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)
    assert all(int(row["stream_seq_end"]) == int(row["stream_seq"]) for row in rows)
    return seqs


def test_t3_durable_ordinal_writers_and_compound_index(real_mongo_db):
    harness = real_mongo_db
    session_id, message_id, _binding = _t3_seed_claimed_turn(harness, message_id="msg-writers")
    repo = KernelEventRepository(harness.db)
    harness.run(repo.ensure_indexes())

    indexes = harness.run(repo._projections.index_information())
    assert indexes["durable_projection_message_stream"]["key"] == [
        ("tenant_id", 1),
        ("message_id", 1),
        ("stream_seq", 1),
    ]

    for cursor in (1, 2, 3):
        harness.run(
            repo.ingest(
                _t3_envelope(f"t3-idx-{cursor}", cursor, "turn.started"),
                tenant_id=TENANT,
                user_id=OWNER,
                conversation_id=session_id,
                message_id=message_id,
            )
        )
    rows = harness.run(
        repo.list_for_message(message_id, tenant_id=TENANT, user_id=OWNER, after_cursor=0)
    )
    seqs = _t3_assert_normalized(rows)

    registry = TurnEventRegistry(repo)
    fallback = harness.run(
        registry.publish_kernel(
            message_id, {"event_id": "evt-fb", "type": "item.delta", "payload": {}}
        )
    )
    assert fallback["stream_seq"] == fallback["stream_seq_end"]
    assert int(fallback["stream_seq"]) > seqs[-1]

    with pytest.raises(StreamSequenceReservationError):
        harness.run(repo.reserve_stream_ordinals(message_id="ghost-message", span=1))
    assert harness.run(harness.db.chat_messages.count_documents({"message_id": "ghost-message"})) == 0


def test_t3_finalizer_coordination_matrix(real_mongo_db, monkeypatch):
    harness = real_mongo_db
    order: list[str] = []

    # (a) exact four-step order for a completed turn
    session_a, message_a, binding_a = _t3_seed_claimed_turn(harness, message_id="msg-order")
    conversations = ConversationRepository(harness.db)
    bindings = KernelBindingRepository(harness.db)

    async def flush() -> None:
        order.append("flush")

    async def projection(**kwargs: Any) -> None:
        order.append("projection")
        await ConversationRepository.update_assistant_projection(conversations, **kwargs)

    async def finish(*args: Any, **kwargs: Any) -> bool:
        order.append("binding")
        return await KernelBindingRepository.finish_turn(bindings, *args, **kwargs)

    async def clear(*args: Any, **kwargs: Any) -> None:
        order.append("clear")
        await ConversationRepository.clear_active_run(conversations, *args, **kwargs)

    conversations.update_assistant_projection = projection
    bindings.finish_turn = finish
    conversations.clear_active_run = clear
    harness.run(
        TurnStateFinalizer(bindings, conversations).finalize(
            binding=binding_a,
            message_id=message_a,
            status="completed",
            flush=flush,
            assistant=TurnAssistantProjection(content="done", execution_events=[]),
        )
    )
    assert order == ["flush", "projection", "binding", "clear"]
    current_a = _t3_binding(harness, session_a)
    assert current_a["active_turn"]["status"] == "completed"
    assert current_a["active_turn"]["claim_state"] == "finished"
    assert "active_run" not in _t3_session_doc(harness, session_a)
    assert harness.run(
        ConversationRepository(harness.db).message(message_a, tenant_id=TENANT, user_id=OWNER)
    )["content"] == "done"

    # (b) the suspension branch retains active_run
    session_b, message_b, binding_b = _t3_seed_claimed_turn(harness, message_id="msg-suspend")
    harness.run(
        TurnStateFinalizer(
            KernelBindingRepository(harness.db), ConversationRepository(harness.db)
        ).finalize(
            binding=binding_b,
            message_id=message_b,
            status="completed",
            clear_conversation=False,
            intervention={
                "suspension_id": "susp-1",
                "node_id": "node-1",
                "reason": "needs human assistance",
            },
            assistant=TurnAssistantProjection(content="partial", execution_events=[]),
        )
    )
    assert _t3_binding(harness, session_b)["active_turn"]["claim_state"] == "finished"
    active_run = _t3_session_doc(harness, session_b)["active_run"]
    assert active_run["status"] == "suspended"
    assert active_run["suspension_id"] == "susp-1"
    assert active_run["message_id"] == message_b

    # (c) a flush failure is typed/retryable and transitions nothing; the
    # retry resumes from the already-durable steps
    session_c, message_c, binding_c = _t3_seed_claimed_turn(harness, message_id="msg-ffail")
    finalizer_c = TurnStateFinalizer(
        KernelBindingRepository(harness.db), ConversationRepository(harness.db)
    )

    async def failing_flush() -> None:
        raise RuntimeError("terminal event flush exploded")

    with pytest.raises(TurnFinalizationRetryableError) as excinfo:
        harness.run(
            finalizer_c.finalize(
                binding=binding_c,
                message_id=message_c,
                status="completed",
                flush=failing_flush,
                assistant=TurnAssistantProjection(content="x", execution_events=[]),
            )
        )
    assert excinfo.value.retryable is True
    assert excinfo.value.code == "turn_finalization_retryable"
    current_c = _t3_binding(harness, session_c)
    assert current_c["active_turn"]["status"] == "running"
    assert current_c["active_turn"]["claim_state"] == "running"
    assert "active_run" in _t3_session_doc(harness, session_c)
    assert harness.run(
        ConversationRepository(harness.db).message(message_c, tenant_id=TENANT, user_id=OWNER)
    )["content"] == ""

    async def ok_flush() -> None:
        return None

    harness.run(
        finalizer_c.finalize(
            binding=binding_c,
            message_id=message_c,
            status="completed",
            flush=ok_flush,
            assistant=TurnAssistantProjection(content="x", execution_events=[]),
        )
    )
    assert _t3_binding(harness, session_c)["active_turn"]["status"] == "completed"

    # (d) a projection failure is retryable and resumes
    session_d, message_d, binding_d = _t3_seed_claimed_turn(harness, message_id="msg-pfail")
    finalizer_d = TurnStateFinalizer(
        KernelBindingRepository(harness.db), ConversationRepository(harness.db)
    )
    with pytest.raises(TurnFinalizationRetryableError):
        harness.run(
            finalizer_d.finalize(
                binding=binding_d,
                message_id="ghost-message",
                status="completed",
                assistant=TurnAssistantProjection(content="never", execution_events=[]),
            )
        )
    current_d = _t3_binding(harness, session_d)
    assert current_d["active_turn"]["status"] == "running"
    assert "active_run" in _t3_session_doc(harness, session_d)
    harness.run(
        finalizer_d.finalize(
            binding=binding_d,
            message_id=message_d,
            status="completed",
            assistant=TurnAssistantProjection(content="resumed", execution_events=[]),
        )
    )
    assert _t3_binding(harness, session_d)["active_turn"]["claim_state"] == "finished"

    # (e) a binding-transition failure is retryable and retains active_run
    session_e, message_e, binding_e = _t3_seed_claimed_turn(harness, message_id="msg-bfail")
    finalizer_e = TurnStateFinalizer(
        KernelBindingRepository(harness.db), ConversationRepository(harness.db)
    )

    async def failing_finish(*args: Any, **kwargs: Any) -> bool:
        raise RuntimeError("binding write failed")

    monkeypatch.setattr(KernelBindingRepository, "finish_turn", failing_finish)
    with pytest.raises(TurnFinalizationRetryableError):
        harness.run(
            finalizer_e.finalize(
                binding=binding_e,
                message_id=message_e,
                status="completed",
                assistant=TurnAssistantProjection(content="partial", execution_events=[]),
            )
        )
    current_e = _t3_binding(harness, session_e)
    assert current_e["active_turn"]["status"] == "running"
    assert "active_run" in _t3_session_doc(harness, session_e)
    monkeypatch.undo()
    harness.run(
        finalizer_e.finalize(
            binding=binding_e,
            message_id=message_e,
            status="completed",
            assistant=TurnAssistantProjection(content="partial", execution_events=[]),
        )
    )
    assert _t3_binding(harness, session_e)["active_turn"]["claim_state"] == "finished"

    # (f) a suspension failure is retryable and retains the run
    session_f, message_f, binding_f = _t3_seed_claimed_turn(harness, message_id="msg-sfail")
    finalizer_f = TurnStateFinalizer(
        KernelBindingRepository(harness.db), ConversationRepository(harness.db)
    )

    async def failing_suspend(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("suspension write failed")

    monkeypatch.setattr(ConversationRepository, "suspend_active_run", failing_suspend)
    with pytest.raises(TurnFinalizationRetryableError):
        harness.run(
            finalizer_f.finalize(
                binding=binding_f,
                message_id=message_f,
                status="completed",
                clear_conversation=False,
                intervention={"suspension_id": "s-1"},
                assistant=TurnAssistantProjection(content="partial", execution_events=[]),
            )
        )
    assert _t3_binding(harness, session_f)["active_turn"]["claim_state"] == "finished"
    assert _t3_session_doc(harness, session_f)["active_run"]["status"] == "running"
    monkeypatch.undo()


def test_t3_runner_terminal_exits_matrix(real_mongo_db, monkeypatch):
    harness = real_mongo_db

    # (a) normal exit converges and a live service replays only after the cursor
    session_a, message_a, binding_a = _t3_seed_claimed_turn(harness, message_id="msg-normal")
    gateway_a = _T3Gateway(
        [
            _t3_envelope("t3-n1", 1, "turn.started"),
            _t3_envelope(
                "t3-n2",
                2,
                "agent.message.completed",
                message={"content": [{"type": "text", "text": "hi"}]},
            ),
            _t3_envelope("t3-n3", 3, "turn.completed", reason={"kind": "stop"}),
        ]
    )
    assert _t3_run(harness, _t3_runner(harness, gateway_a), binding_a, message_a) == "completed"
    rows_a = _t3_rows(harness, message_a)
    seqs_a = _t3_assert_normalized(rows_a)
    assert rows_a[-1]["type"] == "run.completed"
    current_a = _t3_binding(harness, session_a)
    assert current_a["active_turn"]["status"] == "completed"
    assert current_a["active_turn"]["claim_state"] == "finished"
    assert "active_run" not in _t3_session_doc(harness, session_a)
    assert harness.run(
        ConversationRepository(harness.db).message(message_a, tenant_id=TENANT, user_id=OWNER)
    )["content"] == "hi"

    cursor = _mint_cursor(
        session_a, last_message_seq=1, active_message_id=message_a, active_stream_seq=seqs_a[0]
    )
    replay = harness.run(
        _service(harness).poll(
            session_a, tenant_id=TENANT, user_id=OWNER, last_event_id=cursor
        )
    )
    assert replay.kind == "data"
    assert _exec_stream_seqs(replay, session_a) == seqs_a[1:]
    completed = [frame for frame in replay.frames if frame.event == EVENT_TURN_COMPLETED]
    assert len(completed) == 1
    assert json.loads(completed[0].data_json)["status"] == "completed"

    # (b) cancellation flushes the queued rows instead of aborting them
    session_b, message_b, binding_b = _t3_seed_claimed_turn(harness, message_id="msg-cancel")
    gateway_b = _T3Gateway(
        [
            _t3_envelope(
                "t3-c1", 1, "agent.message.delta", chunk={"type": "text-delta", "text": "partial"}
            )
        ]
    )
    gateway_b.release.clear()
    runner_b = _t3_runner(harness, gateway_b)

    async def scenario_b() -> str:
        task = asyncio.create_task(
            runner_b.run(
                binding=binding_b,
                message_id=message_b,
                request_id="req-cancel",
                text="hello",
                temporal_context=_t3_context(),
                live_stream=LiveTurnStream(),
            )
        )
        await asyncio.wait_for(gateway_b.subscribed.wait(), timeout=5)
        await asyncio.sleep(0.05)
        task.cancel()
        return await task

    assert harness.run(scenario_b()) == "cancelled"
    rows_b = _t3_rows(harness, message_b)
    assert rows_b
    _t3_assert_normalized(rows_b)
    current_b = _t3_binding(harness, session_b)
    assert current_b["active_turn"]["status"] == "cancelled"
    assert current_b["active_turn"]["claim_state"] == "finished"
    assert "active_run" not in _t3_session_doc(harness, session_b)

    # (c) a send failure persists one normalized failure row and clears the run
    session_c, message_c, binding_c = _t3_seed_claimed_turn(harness, message_id="msg-failed")
    assert (
        _t3_run(
            harness,
            _t3_runner(harness, _T3Gateway(send_error=RuntimeError("dsh send failed"))),
            binding_c,
            message_c,
        )
        == "failed"
    )
    rows_c = _t3_rows(harness, message_c)
    _t3_assert_normalized(rows_c)
    assert [row["type"] for row in rows_c] == ["run.failed"]
    current_c = _t3_binding(harness, session_c)
    assert current_c["active_turn"]["status"] == "failed"
    assert current_c["active_turn"]["claim_state"] == "finished"
    assert "active_run" not in _t3_session_doc(harness, session_c)

    # (d) browser intervention suspends and retains the run
    session_d, message_d, binding_d = _t3_seed_claimed_turn(harness, message_id="msg-browser")
    intervention = {
        "intervention_suspension": {"suspension_id": "susp-9", "node_id": "node-9"},
        "domain_events": [
            {
                "type": "intervention_required",
                "content": {
                    "reason": "captcha",
                    "category": "browser",
                    "url": "https://example.com",
                },
            }
        ],
    }
    gateway_d = _T3Gateway(
        [
            _t3_envelope(
                "t3-b1", 1, "tool.call.started", callId="call-1", name="browser_task", arguments={}
            ),
            _t3_envelope(
                "t3-b2",
                2,
                "tool.call.completed",
                callId="call-1",
                codeDispatch=True,
                content=[{"type": "text", "text": json.dumps(intervention)}],
                isError=False,
            ),
            _t3_envelope("t3-b3", 3, "turn.completed", reason={"kind": "stop"}),
        ]
    )
    assert _t3_run(harness, _t3_runner(harness, gateway_d), binding_d, message_d) == "completed"
    _t3_assert_normalized(_t3_rows(harness, message_d))
    assert _t3_binding(harness, session_d)["active_turn"]["status"] == "completed"
    active_run_d = _t3_session_doc(harness, session_d)["active_run"]
    assert active_run_d["status"] == "suspended"
    assert active_run_d["suspension_id"] == "susp-9"

    # (e) a late projection failure keeps exactly one terminal event
    session_e, message_e, binding_e = _t3_seed_claimed_turn(harness, message_id="msg-late")
    calls = {"count": 0}
    original = ConversationRepository.update_assistant_projection

    async def flaky(self: Any, **kwargs: Any) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise LookupError("projection store unavailable")
        await original(self, **kwargs)

    monkeypatch.setattr(ConversationRepository, "update_assistant_projection", flaky)
    gateway_e = _T3Gateway(
        [
            _t3_envelope("t3-l1", 1, "turn.started"),
            _t3_envelope(
                "t3-l2",
                2,
                "agent.message.completed",
                message={"content": [{"type": "text", "text": "hi"}]},
            ),
            _t3_envelope("t3-l3", 3, "turn.completed", reason={"kind": "stop"}),
        ]
    )
    assert _t3_run(harness, _t3_runner(harness, gateway_e), binding_e, message_e) == "failed"
    assert calls["count"] == 1
    rows_e = _t3_rows(harness, message_e)
    _t3_assert_normalized(rows_e)
    terminals = [
        row for row in rows_e if row["type"] in {"run.completed", "run.failed", "run.cancelled"}
    ]
    assert [row["type"] for row in terminals] == ["run.completed"]
    current_e = _t3_binding(harness, session_e)
    assert current_e["active_turn"]["status"] == "failed"
    assert current_e["active_turn"]["claim_state"] == "finished"
    assert "active_run" not in _t3_session_doc(harness, session_e)
    monkeypatch.undo()


def test_t3_recovery_and_live_service_convergence(real_mongo_db):
    harness = real_mongo_db

    # (a) the recovery exit finalizes through the single finalizer
    session_a, message_a, binding_a = _t3_seed_claimed_turn(harness, message_id="msg-recover")
    events = KernelEventRepository(harness.db)
    harness.run(events.ensure_indexes())
    terminal = _t3_envelope("t3-rec-1", 1, "turn.completed", reason={"kind": "stop"})
    harness.run(
        events.persist_batch(
            [
                KernelEventWrite(
                    event=terminal,
                    projected=events.project(terminal, message_id=message_a),
                )
            ],
            tenant_id=TENANT,
            user_id=OWNER,
            conversation_id=session_a,
            message_id=message_a,
        )
    )
    recovery_a = TurnTerminalRecovery(
        gateway=_T3Gateway([terminal]),
        conversations=ConversationRepository(harness.db),
        bindings=KernelBindingRepository(harness.db),
        events=events,
        profiles=_T3Profiles(),
    )
    assert (
        harness.run(
            recovery_a.finalize_persisted_terminal(binding=binding_a, message_id=message_a)
        )
        is True
    )
    current_a = _t3_binding(harness, session_a)
    assert current_a["active_turn"]["status"] == "completed"
    assert current_a["active_turn"]["claim_state"] == "finished"
    assert "active_run" not in _t3_session_doc(harness, session_a)
    assert harness.run(
        ConversationRepository(harness.db).message(message_a, tenant_id=TENANT, user_id=OWNER)
    )["execution_events"][-1]["type"] == "run.completed"

    # (b) the live service reconciles exactly once per service instance
    session_b = _create_session(harness)
    session_b_id = str(session_b["_id"])
    calls: list[str] = []

    async def reconciler(candidate: str) -> None:
        calls.append(candidate)

    service_b = SessionLiveService(**_service_kwargs(harness), claim_reconciler=reconciler)
    harness.run(service_b.poll(session_b_id, tenant_id=TENANT, user_id=OWNER))
    harness.run(service_b.poll(session_b_id, tenant_id=TENANT, user_id=OWNER))
    assert calls == [session_b_id]

    # (c) the live service converges an orphaned claim before the first poll
    session_c, _message_c, _binding_c = _t3_seed_claimed_turn(harness, message_id="msg-live")
    recovery_c = TurnTerminalRecovery(
        gateway=_T3Gateway(events_error=DshNotFoundError("no such session")),
        conversations=ConversationRepository(harness.db),
        bindings=KernelBindingRepository(harness.db),
        events=KernelEventRepository(harness.db),
        profiles=_T3Profiles(),
    )
    service_c = SessionLiveService(
        **_service_kwargs(harness), claim_reconciler=recovery_c.reconcile_session_claims
    )
    result = harness.run(service_c.poll(session_c, tenant_id=TENANT, user_id=OWNER))
    current_c = _t3_binding(harness, session_c)
    assert current_c["active_turn"]["status"] == "failed"
    assert current_c["active_turn"]["claim_state"] == "finished"
    assert "active_run" not in _t3_session_doc(harness, session_c)
    assert result.kind == "data"


def test_t3_normalization_both_writers_ascending_distinct_with_zero_skipped(real_mongo_db):
    harness = real_mongo_db
    session_id, message_id, binding = _t3_seed_claimed_turn(harness, message_id="msg-norm")
    events = KernelEventRepository(harness.db)
    bindings = KernelBindingRepository(harness.db)

    async def runner_writer() -> None:
        writer = DurableKernelEventWriter(
            events=events,
            bindings=bindings,
            binding_id=str(binding["binding_id"]),
            tenant_id=TENANT,
            user_id=OWNER,
            conversation_id=session_id,
            message_id=message_id,
            max_batch_size=2,
        )
        first = _t3_envelope("t3-w1", 1, "turn.started")
        second = _t3_envelope(
            "t3-w2", 2, "agent.message.delta", chunk={"type": "text-delta", "text": "a"}
        )
        dropped = _t3_envelope("t3-w3", 3, "kernel.unknown")
        for event in (first, second, dropped):
            writer.enqueue(
                KernelEventWrite(
                    event=event, projected=events.project(event, message_id=message_id)
                )
            )
        await writer.close()

    harness.run(runner_writer())
    high_water = max(int(row["stream_seq"]) for row in _t3_rows(harness, message_id))

    recovery = TurnTerminalRecovery(
        gateway=_T3Gateway(
            [
                _t3_envelope(
                    "t3-r1", 10, "agent.message.delta", chunk={"type": "text-delta", "text": "b"}
                ),
                _t3_envelope("t3-r2", 11, "kernel.unknown"),
                _t3_envelope("t3-r3", 12, "turn.completed", reason={"kind": "stop"}),
            ]
        ),
        conversations=ConversationRepository(harness.db),
        bindings=bindings,
        events=events,
        profiles=_T3Profiles(),
    )
    harness.run(recovery.ingest_once(binding=binding, message_id=message_id))

    rows = _t3_rows(harness, message_id)
    seqs = _t3_assert_normalized(rows)
    recovery_ids = [
        row["event_id"]
        for row in rows
        if str(row["event_id"]).startswith("dsh-v3:t3-r")
    ]
    # t3-r2's kernel.unknown event dropped at the projector, so its reserved
    # ordinal is abandoned (a gap is healthy; a duplicate never is).
    assert recovery_ids == ["dsh-v3:t3-r1", "dsh-v3:t3-r3"]
    recovery_seqs = [
        int(row["stream_seq"])
        for row in rows
        if str(row["event_id"]).startswith("dsh-v3:t3-r")
    ]
    assert min(recovery_seqs) > high_water
    assert rows[-1]["type"] == "run.completed"

    resumed = harness.run(
        events.list_for_message(
            message_id, tenant_id=TENANT, user_id=OWNER, after_cursor=high_water
        )
    )
    assert [row["event_id"] for row in resumed] == ["dsh-v3:t3-r1", "dsh-v3:t3-r3"]
    assert len(resumed) == 2
    assert resumed[-1]["type"] == "run.completed"
    assert seqs == sorted(seqs)


def test_t3_restart_sweep_finalizes_orphaned_claim_and_admits_next_send(
    real_mongo_db, monkeypatch
):
    harness = real_mongo_db
    session_id, message_id, binding = _t3_seed_claimed_turn(harness, message_id="msg-restart")
    assert binding["active_turn"]["claim_state"] == "running"

    import app.dsh_runtime.application as application_module
    from app.dsh_runtime.application import DshRuntimeApplication
    from app.dsh_runtime.gateway import DshAgentKernelGateway
    from app.dsh_runtime.profile.store import MongoRuntimeProfileStore
    from app.dsh_runtime.transport import HttpKernelHostTransport
    from app.enterprise_capabilities.delivery import AuthoritativeDeliveryRepository
    from app.enterprise_capabilities.tools import EnterpriseToolRepository
    from app.services.presentation.execution import PresentationJobRepository

    async def noop_async(*args: Any, **kwargs: Any) -> None:
        return None

    def noop_sync(*args: Any, **kwargs: Any) -> None:
        return None

    async def offline_request(self: Any, method: str, path: str, **kwargs: Any) -> None:
        raise DshRuntimeError("runtime host offline")

    async def no_such_session(self: Any, session_id: str, after_cursor: int = 0) -> None:
        raise DshNotFoundError("no such session")

    async def fake_discover_runtime(self: Any, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(runtime_id="runtime-t3", kernel_version="test-kernel")

    monkeypatch.setattr(application_module, "get_db", lambda: harness.db)
    monkeypatch.setattr(HttpKernelHostTransport, "request", offline_request)
    monkeypatch.setattr(DshAgentKernelGateway, "discover_runtime", fake_discover_runtime)
    monkeypatch.setattr(DshAgentKernelGateway, "attach_session", noop_sync)
    monkeypatch.setattr(DshAgentKernelGateway, "resume_session", noop_async)
    monkeypatch.setattr(DshAgentKernelGateway, "events_once", no_such_session)
    monkeypatch.setattr(MongoRuntimeProfileStore, "ensure_indexes", noop_async)
    monkeypatch.setattr(EnterpriseToolRepository, "ensure_indexes", noop_async)
    monkeypatch.setattr(PresentationJobRepository, "ensure_indexes", noop_async)
    monkeypatch.setattr(PresentationJobRepository, "recover_running", noop_async)
    monkeypatch.setattr(AuthoritativeDeliveryRepository, "ensure_indexes", noop_async)

    app = DshRuntimeApplication()
    harness.run(app.start())
    try:
        current = _t3_binding(harness, session_id)
        assert current["active_turn"]["status"] == "failed"
        assert current["active_turn"]["claim_state"] == "finished"
        assert "active_run" not in _t3_session_doc(harness, session_id)
        rows = _t3_rows(harness, message_id)
        assert rows and rows[-1]["type"] == "run.failed"

        readmitted = harness.run(
            KernelBindingRepository(harness.db).claim_turn_authorized(
                str(current["binding_id"]),
                message_id="msg-restart-2",
                request_id="req-restart-2",
                claim_token="token-restart-2",
            )
        )
        assert readmitted is not None
        assert readmitted["active_turn"]["claim_state"] == "running"
    finally:
        harness.run(app.stop())
