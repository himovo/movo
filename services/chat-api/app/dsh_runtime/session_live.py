"""Durable, poll-based live session projection (session-sharing realtime, T1).

The SSE endpoint (T2) wraps :class:`SessionLiveService`. Each poll reads
tenant-scoped session/message/participant state and durable execution
projections, guards coherence by DIGEST REVALIDATION (read the session
revision digest first, read the state, re-read the digest — a torn poll
emits no data frame and the next poll recomputes), and classifies each
request exactly once as a cold attach or a resume. No broadcaster, no
Redis, no process-local turn registry, no new Mongo collection: per-
connection polling over durable state only.

# allow: SIZE_OK — the plan pins the co-location of SessionLiveService,
# public_execution_event(), the two pure helpers, the cursor codec, the
# revision digest, and the LF-only SSE renderer in this single module
# (the commit's file set is fixed at five paths).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from app.core.config import get_settings
from app.dsh_runtime.bindings.repository import KernelBindingRepository
from app.dsh_runtime.conversation.repository import ConversationRepository
from app.dsh_runtime.conversation.participants_repository import (
    SessionParticipantsRepository,
)
from app.dsh_runtime.events.repository import KernelEventRepository
from app.dsh_runtime.session_access import SessionReadAuthorizer

# ---------------------------------------------------------------------------
# Fixed protocol constants (plan Scope, "Fixed protocol and data rules")
# ---------------------------------------------------------------------------

COLD_ATTACH = "cold_attach"
RESUME = "resume"

CURSOR_VERSION = 1
CURSOR_KEYS = (
    "v",
    "session_id",
    "revision",
    "last_message_seq",
    "active_message_id",
    "active_stream_seq",
)
MAX_CURSOR_CHARS = 2048
SAFE_INT_MAX = 9007199254740991
SESSION_ID_RE = re.compile(r"^[0-9a-f]{24}$")
REVISION_RE = re.compile(r"^[0-9a-f]{64}$")
MESSAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_B64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")

FETCH_SENTINEL_ROWS = 201
EMIT_LIMIT_ROWS = 200
FRAME_BUDGET_BYTES = 262144

TERMINAL_RUN_TYPES = ("run.completed", "run.failed", "run.cancelled")
TERMINAL_TURN_STATUSES = ("completed", "failed", "cancelled")

EVENT_THREAD_CHANGED = "thread.changed"
EVENT_TURN_STARTED = "turn.started"
EVENT_EXECUTION = "execution"
EVENT_TURN_COMPLETED = "turn.completed"
EVENT_MEMBERS_CHANGED = "members.changed"
EVENT_ACCESS_REVOKED = "session.access.revoked"

REASON_CURSOR_INVALID = "cursor_invalid"
REASON_CURSOR_GAP = "cursor_gap"
REASON_REPLAY_OVERFLOW = "replay_overflow"

HEARTBEAT_COMMENT = ": heartbeat\n\n"


class InvalidLiveCursorError(ValueError):
    """The supplied resume position is unusable (reported as cursor_invalid).

    Deliberately echoes none of the offending value.
    """


# ---------------------------------------------------------------------------
# Request classification and the opaque cursor codec (both PURE)
# ---------------------------------------------------------------------------


def classify_request(last_event_id: str | None, after: str | None) -> str:
    """Classify a live request exactly once: cold attach or resume.

    ``Last-Event-ID`` always wins when both are present; either alone is a
    complete resume position, so classification only distinguishes "some
    position supplied" from "no position supplied". An empty string is
    treated as absent.
    """
    has_last = last_event_id is not None and last_event_id != ""
    has_after = after is not None and after != ""
    if has_last or has_after:
        return RESUME
    return COLD_ATTACH


def _validate_cursor_values(
    v: Any,
    session_id: Any,
    revision: Any,
    last_message_seq: Any,
    active_message_id: Any,
    active_stream_seq: Any,
) -> None:
    # type(...) is int (never bool) rejects alternate integer spellings:
    # "5", 5.0, 1e1 parse to str/float and are refused, not coerced.
    if type(v) is not int or v != CURSOR_VERSION:
        raise InvalidLiveCursorError("version")
    if type(session_id) is not str or not SESSION_ID_RE.match(session_id):
        raise InvalidLiveCursorError("session")
    if type(revision) is not str or not REVISION_RE.match(revision):
        raise InvalidLiveCursorError("revision")
    if (
        type(last_message_seq) is not int
        or last_message_seq < 0
        or last_message_seq > SAFE_INT_MAX
    ):
        raise InvalidLiveCursorError("last_message_seq")
    if (active_message_id is None) != (active_stream_seq is None):
        raise InvalidLiveCursorError("active-pair")
    if active_message_id is not None:
        if type(active_message_id) is not str or not MESSAGE_ID_RE.match(
            active_message_id
        ):
            raise InvalidLiveCursorError("active_message_id")
        if (
            type(active_stream_seq) is not int
            or active_stream_seq < 0
            or active_stream_seq > SAFE_INT_MAX
        ):
            raise InvalidLiveCursorError("active_stream_seq")


def _encode_cursor(fields: Mapping[str, Any]) -> str:
    blob = json.dumps(fields, ensure_ascii=False, separators=(",", ":"))
    return base64.urlsafe_b64encode(blob.encode("utf-8")).decode("ascii").rstrip("=")


def build_live_cursor(snapshot: Mapping[str, Any]) -> str:
    """Mint the opaque cursor from a position snapshot (PURE).

    ``snapshot`` carries exactly the six canonical fields; the output is
    strict ASCII unpadded base64url over the fixed-order compact JSON.
    """
    try:
        v = snapshot["v"]
        session_id = snapshot["session_id"]
        revision = snapshot["revision"]
        last_message_seq = snapshot["last_message_seq"]
        active_message_id = snapshot["active_message_id"]
        active_stream_seq = snapshot["active_stream_seq"]
    except (KeyError, TypeError):
        raise InvalidLiveCursorError("shape") from None
    _validate_cursor_values(
        v,
        session_id,
        revision,
        last_message_seq,
        active_message_id,
        active_stream_seq,
    )
    return _encode_cursor(
        {
            "v": v,
            "session_id": session_id,
            "revision": revision,
            "last_message_seq": last_message_seq,
            "active_message_id": active_message_id,
            "active_stream_seq": active_stream_seq,
        }
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise InvalidLiveCursorError("duplicate-key")
    return dict(pairs)


def parse_live_cursor(cursor: str, *, session_id: str) -> dict[str, Any]:
    """Strictly decode and canonically validate a resume cursor (PURE).

    Rejects, as ``cursor_invalid``, exactly: (1) undecodable values, (2)
    non-canonical values (duplicate/extra keys, alternate integer
    spellings, wrong key order, byte mismatch on re-encode), (3) oversized
    values, (4) wrong session or wrong version, and sequence values that
    would exceed validation done by the caller. Row gaps (reason five)
    are detected during replay, never here.
    """
    if type(cursor) is not str or not cursor or len(cursor) > MAX_CURSOR_CHARS:
        raise InvalidLiveCursorError("size")
    if not _B64URL_RE.match(cursor):
        raise InvalidLiveCursorError("alphabet")
    try:
        padded = cursor.encode("ascii") + b"=" * (-len(cursor) % 4)
        text = base64.urlsafe_b64decode(padded).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise InvalidLiveCursorError("undecodable") from None
    try:
        fields = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except InvalidLiveCursorError:
        raise
    except (ValueError, TypeError):
        raise InvalidLiveCursorError("undecodable") from None
    if not isinstance(fields, dict) or tuple(fields.keys()) != CURSOR_KEYS:
        raise InvalidLiveCursorError("key-set")
    _validate_cursor_values(
        fields["v"],
        fields["session_id"],
        fields["revision"],
        fields["last_message_seq"],
        fields["active_message_id"],
        fields["active_stream_seq"],
    )
    if fields["session_id"] != session_id:
        raise InvalidLiveCursorError("wrong-session")
    if _encode_cursor(fields) != cursor:
        raise InvalidLiveCursorError("non-canonical")
    return dict(fields)


# ---------------------------------------------------------------------------
# Fixed revision digest (plan Scope item, exact UTC/key-order/sort rules)
# ---------------------------------------------------------------------------


def _utc_iso(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    # The codebase stores naive UTC (datetime.utcnow()); aware values are
    # normalized to UTC first. %f is always 6 digits.
    moment = value
    if value.tzinfo is not None:
        moment = value.astimezone(timezone.utc).replace(tzinfo=None)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _participant_entry(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "user_id": str(row.get("user_id") or ""),
        "joined_at": _utc_iso(row.get("joined_at")),
        "removed_at": _utc_iso(row.get("removed_at")),
    }


def canonical_participants(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """The digest's participants component: active set, UTF-8 byte sort."""
    entries = [_participant_entry(row) for row in rows]
    entries.sort(
        key=lambda entry: (
            entry["user_id"].encode("utf-8"),
            entry["joined_at"] or "",
            entry["removed_at"] or "",
        )
    )
    return entries


def member_fingerprint(rows: Iterable[Mapping[str, Any]]) -> str:
    """Stable digest of the participant projection alone."""
    blob = json.dumps(
        canonical_participants(rows), ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _active_run_entry(active_run: Any) -> dict[str, Any] | None:
    if not isinstance(active_run, Mapping) or not dict(active_run):
        return None
    return {
        "run_id": active_run.get("run_id"),
        "message_id": active_run.get("message_id"),
        "status": active_run.get("status"),
        "started_at": _utc_iso(active_run.get("started_at")),
    }


def _latest_message_entry(messages: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    latest = messages[-1] if messages else None
    if latest is None:
        return None
    content = latest.get("content")
    raw = content.encode("utf-8") if isinstance(content, str) else b""
    return {
        "message_id": latest.get("message_id"),
        "seq": int(latest.get("seq") or 0),
        "content_sha256": hashlib.sha256(raw).hexdigest(),
    }


def revision_digest(
    *,
    session: Mapping[str, Any],
    messages: Sequence[Mapping[str, Any]],
    participants: Sequence[Mapping[str, Any]],
) -> str:
    """The fixed lowercase-SHA-256 session revision digest."""
    preimage = {
        "updated_at": _utc_iso(session.get("updated_at")),
        "next_message_seq": int(session.get("next_message_seq") or 0),
        "latest_message": _latest_message_entry(messages),
        "active_run": _active_run_entry(session.get("active_run")),
        "participants": canonical_participants(participants),
    }
    blob = json.dumps(preimage, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# LF-only compact SSE frames
# ---------------------------------------------------------------------------


def _compact_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def render_frame(*, event: str, data_json: str, frame_id: str | None = None) -> str:
    """Render one SSE frame: LF-only, compact JSON, no CR, no BOM."""
    parts: list[str] = []
    if frame_id is not None:
        parts.append("id: " + frame_id + "\n")
    parts.append("event: " + event + "\n")
    parts.append("data: " + data_json + "\n")
    parts.append("\n")
    return "".join(parts)


@dataclass(frozen=True)
class LiveFrame:
    event: str
    data_json: str
    frame_id: str | None = None

    def render(self) -> str:
        return render_frame(
            event=self.event, data_json=self.data_json, frame_id=self.frame_id
        )

    def byte_length(self) -> int:
        return len(self.render().encode("utf-8"))


def execution_frame_bytes(frame_id: str, data_json: str) -> int:
    """Complete-frame byte count used by the cumulative replay budget."""
    return len(
        render_frame(
            event=EVENT_EXECUTION, data_json=data_json, frame_id=frame_id
        ).encode("utf-8")
    )


def access_revoked_frame(session_id: str, reason: str) -> LiveFrame:
    """Terminal no-ID revocation frame; reason is the fixed two-member union."""
    if reason not in {"participant_removed", "participant_left"}:
        raise ValueError("unsupported access-revoked reason")
    return LiveFrame(
        event=EVENT_ACCESS_REVOKED,
        data_json=_compact_json({"session_id": session_id, "reason": reason}),
        frame_id=None,
    )


# ---------------------------------------------------------------------------
# public_execution_event(): recursive projection sanitizer
# ---------------------------------------------------------------------------

PUBLIC_EVENT_KEYS = (
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
)

# Storage paths, tenant/main/session/conversation/binding/kernel/runtime
# IDs, and internal metadata are dropped at ANY nesting depth.
_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "_oss_object_path",
        "object_path",
        "path",
        "storage_key",
        "bucket",
        "tenant_id",
        "main_id",
        "session_id",
        "conversation_id",
        "binding_id",
        "kernel_session_id",
        "runtime_id",
        "user_id",
        "internal",
        "metadata",
    }
)

# URL values: scheme:// values must be http(s); data:/javascript: never are.
_URL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")

_TOOL_PAYLOAD_KEYS = frozenset(
    {
        "callId",
        "name",
        "display_name",
        "description",
        "risk_level",
        "args",
        "status",
        "ok",
        "result_summary",
        "error",
        "evidence_bundle",
        "artifacts",
        "browser_intervention",
    }
)

# Allowlist per (type, item_kind), derived from the fixed set the
# KernelEventProjector emits; unknown combinations get nothing (fail-closed).
_PAYLOAD_ALLOWLIST: dict[tuple[str, str | None], frozenset[str]] = {
    ("run.started", None): frozenset({"kernel"}),
    ("run.completed", None): frozenset({"reason"}),
    ("run.failed", None): frozenset({"code", "message", "retryable"}),
    ("run.cancelled", None): frozenset({"reason"}),
    ("item.delta", "final_answer"): frozenset({"text", "provisional"}),
    ("item.completed", "final_answer"): frozenset({"text", "provisional"}),
    ("item.completed", "commentary"): frozenset(
        {"text", "source", "reason", "retract_provisional"}
    ),
    ("item.completed", "activity"): frozenset(
        {"category", "skill_name", "source_scope", "selection_mode"}
    ),
    ("item.started", "tool"): frozenset(
        {"callId", "name", "display_name", "description", "risk_level", "args", "status"}
    ),
    ("item.completed", "tool"): _TOOL_PAYLOAD_KEYS,
    ("item.failed", "tool"): _TOOL_PAYLOAD_KEYS,
    ("item.failed", "error"): frozenset({"code", "message", "retryable"}),
}

_DROP = object()


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for key, inner in value.items():
            name = str(key)
            if name in _FORBIDDEN_PAYLOAD_KEYS:
                continue
            kept = _sanitize_value(inner)
            if kept is _DROP:
                continue
            cleaned[name] = kept
        return cleaned
    if isinstance(value, (list, tuple)):
        kept_items = [
            _sanitize_value(item) for item in value if _sanitize_value(item) is not _DROP
        ]
        return [item for item in kept_items if item is not _DROP]
    if isinstance(value, str):
        if _URL_SCHEME_RE.match(value):
            head = value[:8].lower()
            if head == "https://" or head.startswith("http://"):
                return value
            return _DROP
        head = value[:11].lower()
        if head.startswith("data:") or head.startswith("javascript:"):
            return _DROP
        return value
    return value


def public_execution_event(row: Mapping[str, Any]) -> dict[str, Any]:
    """The fixed TWELVE-key public wire shape for a durable projection row.

    Every absent top-level value normalizes to JSON ``null`` — never an
    omitted key — so run-level rows (no ``item_kind``/``item_id``) and
    item-level rows share one shape for the typed consumer. ``payload`` is
    allowlisted by event/item type and recursively stripped of storage
    paths, internal IDs, metadata, and non-HTTP(S) URL values.
    """
    event_type = row.get("type")
    item_kind = row.get("item_kind")
    allow = _PAYLOAD_ALLOWLIST.get((str(event_type), item_kind if item_kind else None))
    raw_payload = row.get("payload")
    if not isinstance(raw_payload, Mapping):
        raw_payload = {}
    if allow is None:
        payload: dict[str, Any] = {}
    else:
        payload = {}
        for key, inner in raw_payload.items():
            if str(key) not in allow:
                continue
            kept = _sanitize_value(inner)
            if kept is _DROP:
                continue
            payload[str(key)] = kept
    return {
        "v": row.get("v"),
        "event_id": row.get("event_id"),
        "id": row.get("id"),
        "ts": row.get("ts"),
        "type": event_type,
        "item_kind": item_kind,
        "item_id": row.get("item_id"),
        "parent_item_id": row.get("parent_item_id"),
        "revision": row.get("revision"),
        "stream_seq": row.get("stream_seq"),
        "stream_seq_end": row.get("stream_seq_end"),
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# Poll results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PollResult:
    """One poll's SSE response: data, control, or heartbeat-only.

    Never mixes kinds: a control response carries exactly one no-ID frame
    and nothing else; a data response carries only data frames (the
    stream layer appends the trailing heartbeat comment per its own
    interval); a heartbeat-only response carries the comment alone.
    """

    kind: str  # "data" | "control" | "heartbeat"
    frames: tuple[LiveFrame, ...]
    revision: str
    member_fingerprint: str
    cursor: str | None = None
    heartbeat_comment: str = HEARTBEAT_COMMENT


# ---------------------------------------------------------------------------
# Poll-scoped frame helpers (cursor minting, thread.changed control)
# ---------------------------------------------------------------------------


def _row_cursor(
    *,
    session_id: str,
    revision: str,
    last_message_seq: int,
    active_message_id: str | None,
    active_stream_seq: int | None,
) -> str:
    """Mint the canonical cursor for one poll position (row/turn/trailing ID)."""
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


def _thread_changed_result(
    *,
    session_id: str,
    revision: str,
    last_message_seq: int,
    fingerprint: str,
    reason: str,
) -> PollResult:
    """The sole-frame ``thread.changed`` control response (no ID).

    Carries the fixed four-field payload; the position is deliberately
    unread — the next poll recomputes from scratch. ``reason`` is one of
    cursor_invalid / cursor_gap / replay_overflow.
    """
    return PollResult(
        kind="control",
        frames=(
            LiveFrame(
                event=EVENT_THREAD_CHANGED,
                data_json=_compact_json(
                    {
                        "session_id": session_id,
                        "revision": revision,
                        "last_message_seq": last_message_seq,
                        "reason": reason,
                    }
                ),
                frame_id=None,
            ),
        ),
        revision=revision,
        member_fingerprint=fingerprint,
    )


# ---------------------------------------------------------------------------
# SessionLiveService
# ---------------------------------------------------------------------------


class SessionLiveService:
    """Per-poll durable live projection; T2's SSE endpoint wraps this."""

    def __init__(
        self,
        *,
        conversations: ConversationRepository,
        participants: SessionParticipantsRepository,
        events: KernelEventRepository,
        bindings: KernelBindingRepository,
        authorizer: SessionReadAuthorizer,
        heartbeat_seconds: float | None = None,
    ) -> None:
        self._conversations = conversations
        self._participants = participants
        self._events = events
        self._bindings = bindings
        self._authorizer = authorizer
        # In-process override for T1's own pytest; deployment configuration
        # reaches the interval through the env-backed Settings field read
        # via get_settings() (a bare constructor argument as the sole seam
        # is insufficient and forbidden by the plan).
        self._heartbeat_seconds_override = heartbeat_seconds

    @property
    def heartbeat_seconds(self) -> float:
        if self._heartbeat_seconds_override is not None:
            return float(self._heartbeat_seconds_override)
        return float(get_settings().SESSION_LIVE_HEARTBEAT_SECONDS)

    # -- reads ---------------------------------------------------------------

    async def _read_state(
        self, session_id: str, tenant_id: str
    ) -> tuple[Mapping[str, Any], Sequence[Mapping[str, Any]], Sequence[Mapping[str, Any]]]:
        session = await self._conversations._sessions.find_one(
            {"_id": __import__("bson").ObjectId(session_id), "main_id": tenant_id}
        )
        participants = await self._participants.list(
            session_id, tenant_id=tenant_id
        )
        messages = await self._conversations.list_messages(tenant_id, session_id)
        return session, participants, messages

    # -- polling -------------------------------------------------------------

    async def poll(
        self,
        session_id: str,
        *,
        tenant_id: str,
        user_id: str | None,
        last_event_id: str | None = None,
        after: str | None = None,
        known_member_fingerprint: str | None = None,
    ) -> PollResult:
        lease = await self._authorizer.authorize_read(
            session_id, tenant_id=tenant_id, user_id=user_id
        )
        session, participants, messages = await self._read_state(session_id, tenant_id)
        digest1 = revision_digest(
            session=session, messages=messages, participants=participants
        )
        current_fingerprint = member_fingerprint(participants)
        kind = classify_request(last_event_id, after)
        message_high_water = int(session.get("next_message_seq") or 0)

        # -- resume position ---------------------------------------------------
        resume_active_message_id: str | None = None
        resume_active_stream_seq = 0
        if kind == RESUME:
            # classify_request returned RESUME, so a non-empty position is
            # guaranteed; Last-Event-ID wins when both are present.
            cursor = last_event_id if last_event_id else after
            try:
                fields = parse_live_cursor(cursor or "", session_id=session_id)
                if fields["last_message_seq"] > message_high_water:
                    raise InvalidLiveCursorError("last_message_seq")
            except InvalidLiveCursorError:
                return _thread_changed_result(
                    session_id=session_id,
                    revision=digest1,
                    last_message_seq=message_high_water,
                    fingerprint=current_fingerprint,
                    reason=REASON_CURSOR_INVALID,
                )
            # Validation pairs the active fields: message_id set iff seq set.
            resume_active_message_id = fields["active_message_id"]
            resume_active_stream_seq = fields["active_stream_seq"]

        # -- tracked message and pre-poll position -----------------------------
        active_run = session.get("active_run")
        run_entry = _active_run_entry(active_run)
        if kind == RESUME and resume_active_message_id is not None:
            tracked = resume_active_message_id
            position = resume_active_stream_seq
        else:
            tracked = run_entry.get("message_id") if run_entry else None
            position = 0

        binding = None
        if tracked is not None:
            binding = await self._bindings.by_message(tracked, tenant_id=tenant_id)

        run_id = active_run.get("run_id") if isinstance(active_run, Mapping) else None
        initiator_user_id: str | None = None
        if isinstance(active_run, Mapping):
            initiator_user_id = str(active_run.get("initiator_user_id") or "") or None
        if run_id is None and binding is not None and isinstance(
            binding.get("active_turn"), Mapping
        ):
            run_id = binding["active_turn"].get("request_id") or None
        run_status = run_entry.get("status") if run_entry else None

        # -- durable execution projections ---------------------------------------
        rows: list[dict[str, Any]] = []
        if tracked is not None:
            fetched = await self._events.list_for_message(
                tracked,
                tenant_id=tenant_id,
                user_id=lease.user_id,
                after_cursor=position,
            )
            rows = fetched[:FETCH_SENTINEL_ROWS]

        # -- above-high-water probe: one bounded probe at S-1 --------------------
        if kind == RESUME and tracked is not None and not rows and position > 0:
            probe = await self._events.list_for_message(
                tracked,
                tenant_id=tenant_id,
                user_id=lease.user_id,
                after_cursor=position - 1,
            )
            if not probe[:1]:
                return _thread_changed_result(
                    session_id=session_id,
                    revision=digest1,
                    last_message_seq=message_high_water,
                    fingerprint=current_fingerprint,
                    reason=REASON_CURSOR_INVALID,
                )

        # -- gap/overflow WHOLE-BATCH scan (before any emission) -----------------
        verdict = None  # None | REASON_CURSOR_GAP | REASON_REPLAY_OVERFLOW
        if len(rows) >= FETCH_SENTINEL_ROWS:
            verdict = REASON_REPLAY_OVERFLOW
        else:
            seen: set[str] = set()
            previous_seq: int | None = None
            for row in rows:
                row_seq = int(row.get("stream_seq") or 0)
                event_id = row.get("event_id")
                if previous_seq is not None and row_seq <= previous_seq:
                    verdict = REASON_CURSOR_GAP
                    break
                if not event_id or str(event_id) in seen:
                    verdict = REASON_CURSOR_GAP
                    break
                seen.add(str(event_id))
                previous_seq = row_seq

        frames: list[LiveFrame] = []
        if verdict is None and rows:
            total = 0
            for row in rows:
                row_seq = int(row.get("stream_seq") or 0)
                frame_id = _row_cursor(
                    session_id=session_id,
                    revision=digest1,
                    last_message_seq=message_high_water,
                    active_message_id=tracked,
                    active_stream_seq=row_seq,
                )
                data_json = _compact_json(public_execution_event(row))
                total += execution_frame_bytes(frame_id, data_json)
                if total > FRAME_BUDGET_BYTES:
                    verdict = REASON_REPLAY_OVERFLOW
                    frames = []
                    break
                frames.append(
                    LiveFrame(
                        event=EVENT_EXECUTION, data_json=data_json, frame_id=frame_id
                    )
                )

        # -- digest revalidation (full preimage re-read) -------------------------
        session2, participants2, messages2 = await self._read_state(
            session_id, tenant_id
        )
        digest2 = revision_digest(
            session=session2, messages=messages2, participants=participants2
        )
        if digest1 != digest2:
            return PollResult(
                kind="heartbeat",
                frames=(),
                revision=digest1,
                member_fingerprint=current_fingerprint,
            )

        # -- members.changed control ---------------------------------------------
        if (
            known_member_fingerprint is not None
            and known_member_fingerprint != current_fingerprint
        ):
            return PollResult(
                kind="control",
                frames=(
                    LiveFrame(
                        event=EVENT_MEMBERS_CHANGED,
                        data_json=_compact_json(
                            {"session_id": session_id, "revision": digest1}
                        ),
                        frame_id=None,
                    ),
                ),
                revision=digest1,
                member_fingerprint=current_fingerprint,
            )

        if verdict is not None:
            return _thread_changed_result(
                session_id=session_id,
                revision=digest1,
                last_message_seq=message_high_water,
                fingerprint=current_fingerprint,
                reason=verdict,
            )

        # -- emit -----------------------------------------------------------------
        binding_status = None
        if binding is not None and isinstance(binding.get("active_turn"), Mapping):
            binding_status = str(binding["active_turn"].get("status") or "")
        turn_started_emitted = tracked is not None and (
            kind == COLD_ATTACH or resume_active_message_id is None
        )
        turn_completed_emitted = tracked is not None and (
            binding_status in TERMINAL_TURN_STATUSES
            or any(str(row.get("type")) in TERMINAL_RUN_TYPES for row in rows)
        )

        data_frames: list[LiveFrame] = []
        if tracked is not None and turn_started_emitted:
            data_frames.append(
                LiveFrame(
                    event=EVENT_TURN_STARTED,
                    data_json=_compact_json(
                        {
                            "session_id": session_id,
                            "revision": digest1,
                            "run_id": run_id,
                            "message_id": tracked,
                            "initiator_user_id": initiator_user_id,
                            "status": run_status,
                        }
                    ),
                    frame_id=_row_cursor(
                        session_id=session_id,
                        revision=digest1,
                        last_message_seq=message_high_water,
                        active_message_id=tracked,
                        active_stream_seq=position,
                    ),
                )
            )
        data_frames.extend(frames)
        if tracked is not None and turn_completed_emitted:
            terminal_status = binding_status
            if terminal_status not in TERMINAL_TURN_STATUSES:
                for row in rows:
                    row_type = str(row.get("type"))
                    if row_type in TERMINAL_RUN_TYPES:
                        terminal_status = row_type.split(".", 1)[1]
                        break
            data_frames.append(
                LiveFrame(
                    event=EVENT_TURN_COMPLETED,
                    data_json=_compact_json(
                        {
                            "session_id": session_id,
                            "message_id": tracked,
                            "run_id": run_id,
                            "status": terminal_status,
                            "revision": digest1,
                        }
                    ),
                    frame_id=_row_cursor(
                        session_id=session_id,
                        revision=digest1,
                        last_message_seq=message_high_water,
                        active_message_id=None,
                        active_stream_seq=None,
                    ),
                )
            )

        # The never-ahead trailing position: a completed turn closes the
        # active pair; otherwise the last emitted row's position, or the
        # pre-poll position when nothing was emitted.
        final_active: str | None
        final_seq: int | None
        if turn_completed_emitted or tracked is None:
            final_active, final_seq = None, None
        elif frames:
            final_active, final_seq = tracked, int(rows[-1].get("stream_seq") or 0)
        else:
            final_active, final_seq = tracked, position
        return PollResult(
            kind="data",
            frames=tuple(data_frames),
            revision=digest1,
            member_fingerprint=current_fingerprint,
            cursor=_row_cursor(
                session_id=session_id,
                revision=digest1,
                last_message_seq=message_high_water,
                active_message_id=final_active,
                active_stream_seq=final_seq,
            ),
        )
