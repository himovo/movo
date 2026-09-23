# allow: SIZE_OK — one cohesive seam (the plan todo-31 regression guards for
# the six frozen boundaries + the documented owner-search limitation), pinned
# to the frozen plan's acceptance; mirrors T04/T07-T19's pinned single-file
# matrices and T18's real-service proof-suite shape.
"""Plan todo 31 — regression guards for the frozen boundaries.

The session-sharing change deliberately leaves six boundaries USER-scoped, and
this module pins each of them against a real mongod:

- Search: ``app/api/endpoints/sessions.py`` ``search_sessions`` — the search
  filters keep their ``user_id`` scoping (sessions candidates, message
  candidates, and the per-message session lookup).
- Compaction: ``app/api/endpoints/sessions.py``
  ``_maybe_compact_session_messages`` — compaction stays user-scoped.
- Prior-turn evidence: ``app/services/conversation_evidence_service.py:126-142``
  ``_load_rows`` — the evidence loader keeps its ``user_id`` filter.
- History RAG: ``app/services/rag_service/local_knowledge_rag_service.py:112-126``
  — RAG keeps its user scoping (chat-message and session-artifact candidates).
- Pending-approval aggregate: ``app/api/endpoints/sessions.py``
  ``_attach_pending_approval_counts`` — viewer-scoped (T16's known limitation:
  participant B never sees a badge for A's pending approval — PINNED here).
- Per-caller quota: ``app/core/quota_policy.py`` ``sum_usage`` /
  ``get_quota_summary`` — quota stays per-caller user-scoped.

A participant must NOT gain owner-row results through any of them. One
positive test records the documented limitation (T18's precedent): the
owner's search does not return participant-authored rows.

Every test runs the REAL service/endpoint code against the real mongod
(``real_mongo_db`` + ``harness.run(...)``); only the LLM compactor, the
evidence selection LLM and the artifact storage are faked (unavoidable
external seams). No HTTP, no sleeps, durable state through real collections.
"""

from __future__ import annotations

import importlib
import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from bson import ObjectId

import app.api.endpoints.sessions as sessions_module
import app.core.quota_policy as quota_module
import app.services.conversation_evidence_service as conversation_evidence_module
from app.api.endpoints.sessions import (
    _attach_pending_approval_counts,
    _maybe_compact_session_messages,
    search_sessions,
)
from app.core.quota_policy import get_quota_summary, sum_usage
from app.services.conversation_evidence_service import (
    ConversationEvidenceSelection,
    conversation_evidence_service,
)

# BITING GOTCHA: rag_service/__init__.py re-exports the `local_knowledge_rag_service`
# SINGLETON, so `import app.services.rag_service.local_knowledge_rag_service as m`
# binds the INSTANCE (the package attribute shadows the submodule) and the get_db
# setattr would AttributeError. importlib.import_module returns the sys.modules
# entry — the real module.
rag_module = importlib.import_module("app.services.rag_service.local_knowledge_rag_service")
# The singleton from-import resolves via getattr on the MODULE (not the package),
# so it is unaffected by the __init__ shadowing above.
from app.services.rag_service.local_knowledge_rag_service import local_knowledge_rag_service

TENANT = "tenant-frozen-boundaries"
OTHER_TENANT = "tenant-frozen-boundaries-other"

OWNER_ID = "owner-user-fb"
PARTICIPANT_ID = "participant-user-fb"

# Deterministic fixtures: fixed datetimes, no wall-clock reads (T01's rule).
_FIXED_NOW = datetime(2026, 9, 15, 8, 30, 0)
_FIXED_WINDOW_START = datetime(2026, 9, 1, 0, 0, 0)
_FIXED_WINDOW_END = datetime(2026, 10, 1, 0, 0, 0)
_FIXED_SEEDED_AT = datetime(2026, 9, 15, 12, 0, 0)

# sessions.py's compaction trigger: > 40 non-compacted, non-summary rows per
# caller; to_compact = rows[:-20]. The fixture seeds exactly 41 rows per user.
COMPACTION_TRIGGER = 41
COMPACTION_KEEP_RECENT = 20
COMPACTION_OWNER_SEQ_START = 50  # owner rows: seq 50..90


# ---------------------------------------------------------------------------
# Harness — the four module-level get_db seams (T02/T04/T08's pattern)
# ---------------------------------------------------------------------------


@pytest.fixture
def frozen(real_mongo_db, monkeypatch):
    """Real mongod with every frozen boundary's ``get_db`` seam pointed at it."""
    harness = real_mongo_db
    monkeypatch.setattr(sessions_module, "get_db", lambda: harness.db)
    monkeypatch.setattr(conversation_evidence_module, "get_db", lambda: harness.db)
    monkeypatch.setattr(rag_module, "get_db", lambda: harness.db)
    monkeypatch.setattr(quota_module, "get_db", lambda: harness.db)
    return harness


def _message_doc(
    *,
    session_id: ObjectId,
    user_id: str,
    main_id: str,
    content: str,
    seq: int,
    role: str = "user",
    message_type: str = "normal",
) -> dict:
    return {
        "_id": ObjectId(),
        "session_id": session_id,
        "user_id": str(user_id),
        "main_id": main_id,
        "role": role,
        "content": content,
        "seq": int(seq),
        "message_type": message_type,
        "created_at": _FIXED_NOW,
        "documents": [],
        "images": [],
    }


def _seed_session(harness, *, user_id: str, main_id: str, title: str, **extra) -> ObjectId:
    doc: dict[str, Any] = {
        "_id": ObjectId(),
        "user_id": str(user_id),
        "main_id": main_id,
        "title": title,
        "created_at": _FIXED_NOW,
        "updated_at": _FIXED_NOW,
    }
    doc.update(extra)
    harness.run(harness.db.chat_sessions.insert_one(doc))
    return doc["_id"]


def _seed_message(harness, **kwargs) -> ObjectId:
    doc = _message_doc(**kwargs)
    harness.run(harness.db.chat_messages.insert_one(doc))
    return doc["_id"]


def _seed_participant(harness, *, conversation_id: ObjectId, user_id: str, main_id: str) -> None:
    harness.run(harness.db.session_participants.insert_one({
        "_id": ObjectId(),
        "main_id": main_id,
        "conversation_id": conversation_id,
        "user_id": str(user_id),
        "role": "participant",
        "joined_at": _FIXED_NOW,
        "last_read_seq": 0,
        "removed_at": None,
    }))


def _seed_pending_approval(harness, *, conversation_id: ObjectId, user_id: str, main_id: str) -> ObjectId:
    doc = {
        "_id": ObjectId(),
        "tenant_id": main_id,
        "user_id": str(user_id),
        # The aggregate matches conversation_id as the STRING form of the
        # session _id ({"$in": list(by_id)} over str(_id) keys).
        "conversation_id": str(conversation_id),
        "status": "pending",
        "created_at": _FIXED_NOW,
    }
    harness.run(harness.db.enterprise_tool_approvals.insert_one(doc))
    return doc["_id"]


def _scope_as(user_id: str, main_id: str):
    async def _fake(authorization, *, claimed_user_id, claimed_main_id):
        # Mirrors the real _authorized_scope's return shape: the RESOLVED
        # viewer ids (T11's lesson — the caller claims its own ids).
        return str(user_id), str(main_id)

    return _fake


def _search(harness, monkeypatch, *, user_id: str, main_id: str, q: str):
    monkeypatch.setattr(sessions_module, "_authorized_scope", _scope_as(user_id, main_id))
    # ALL Query-defaulted params passed explicitly (T8's gotcha — a raw
    # Query(None) default object is truthy and hijacks main_id).
    return harness.run(search_sessions(
        user_id=user_id,
        main_id=main_id,
        main_id_snake=None,
        q=q,
        limit=20,
        offset=0,
        authorization=f"bearer {user_id}",
    ))


# ---------------------------------------------------------------------------
# (a) Search — the search filters keep their user_id scoping
# ---------------------------------------------------------------------------


def test_search_stays_scoped_to_the_callers_own_rows(frozen, monkeypatch):
    harness = frozen
    shared_id = _seed_session(
        harness, user_id=OWNER_ID, main_id=TENANT,
        title="quantum alignment notes",
        last_message_preview="quantum alignment owner preview",
    )
    own_id = _seed_session(
        harness, user_id=PARTICIPANT_ID, main_id=TENANT,
        title="quantum participant notebook",
    )
    # The participant is an ACTIVE member of the owner's shared session —
    # membership must not gain owner-row results through search.
    _seed_participant(harness, conversation_id=shared_id, user_id=PARTICIPANT_ID, main_id=TENANT)

    response = _search(harness, monkeypatch, user_id=PARTICIPANT_ID, main_id=TENANT, q="quantum")

    items = response.data["items"]
    assert [item.id for item in items] == [str(own_id)]
    assert str(shared_id) not in [item.id for item in items]
    assert all(item.user_id == PARTICIPANT_ID for item in items)


def test_owner_search_scoping_excludes_participant_authored_rows(frozen, monkeypatch):
    """The DOCUMENTED limitation (plan todo 31, T18's precedent): the owner's
    search does not return participant-authored rows. Asserted as the pinned
    behavior, not a bug — the owner's OWN message still matches (the positive
    control), the participant's contributes zero."""
    harness = frozen
    shared_id = _seed_session(
        harness, user_id=OWNER_ID, main_id=TENANT,
        title="quantum alignment notes",
    )
    _seed_participant(harness, conversation_id=shared_id, user_id=PARTICIPANT_ID, main_id=TENANT)
    _seed_message(
        harness, session_id=shared_id, user_id=OWNER_ID, main_id=TENANT,
        content="quantum entanglement budget owner analysis", seq=1,
    )
    _seed_message(
        harness, session_id=shared_id, user_id=PARTICIPANT_ID, main_id=TENANT,
        content="quantum participant observation from the shared thread", seq=2,
    )

    response = _search(harness, monkeypatch, user_id=OWNER_ID, main_id=TENANT, q="quantum")

    items = response.data["items"]
    assert [item.id for item in items] == [str(shared_id)]
    entry = items[0]
    # ONLY the owner's own message matched — the participant-authored row
    # contributes zero (the documented limitation).
    assert entry.matched_message_count == 1
    joined = " | ".join(entry.snippets)
    assert "entanglement" in joined  # the positive control: the message pipeline works
    assert "participant observation" not in joined


def test_message_match_scoping_does_not_surface_the_owners_session(frozen, monkeypatch):
    harness = frozen
    shared_id = _seed_session(harness, user_id=OWNER_ID, main_id=TENANT, title="quarterly report")
    own_id = _seed_session(harness, user_id=PARTICIPANT_ID, main_id=TENANT, title="my workspace")
    _seed_participant(harness, conversation_id=shared_id, user_id=PARTICIPANT_ID, main_id=TENANT)
    _seed_message(
        harness, session_id=shared_id, user_id=OWNER_ID, main_id=TENANT,
        content="the xyzzy plugh analysis of the quarter", seq=1,
    )
    _seed_message(
        harness, session_id=own_id, user_id=PARTICIPANT_ID, main_id=TENANT,
        content="my own xyzzy plugh notes", seq=1,
    )

    response = _search(harness, monkeypatch, user_id=PARTICIPANT_ID, main_id=TENANT, q="xyzzy plugh")

    items = response.data["items"]
    assert [item.id for item in items] == [str(own_id)]
    assert items[0].matched_message_count == 1
    # The owner's matching message row gains no results for a member.
    assert str(shared_id) not in [item.id for item in items]


def test_search_tenant_scoping_bounds_the_share_blast_radius(frozen, monkeypatch):
    harness = frozen
    shared_id = _seed_session(harness, user_id=OWNER_ID, main_id=TENANT, title="quantum alignment notes")
    other_id = _seed_session(
        harness, user_id=OWNER_ID, main_id=OTHER_TENANT, title="quantum alignment notes",
    )

    response = _search(harness, monkeypatch, user_id=OWNER_ID, main_id=OTHER_TENANT, q="quantum")

    items = response.data["items"]
    assert [item.id for item in items] == [str(other_id)]
    # A live share link does not leak across tenants through search.
    assert str(shared_id) not in [item.id for item in items]


# ---------------------------------------------------------------------------
# (b) Compaction — compaction stays user-scoped
# ---------------------------------------------------------------------------


class _FakeCompactor:
    """The LLM compactor seam (sessions.context_compactor). The boundary under
    test is the cursor filter's user_id scoping, not the summary text."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def compact_messages(self, rows, output_spec=None):
        self.calls.append({"rows": len(list(rows)), "output_spec": dict(output_spec or {})})
        return SimpleNamespace(summary="compacted summary text", memories=[], source="test-compactor")

    def heuristic_summary(self, rows):
        return "heuristic summary text"


@pytest.fixture
def compaction_thread(frozen):
    """A shared session whose owner AND participant each hold exactly
    COMPACTION_TRIGGER rows — both users' compaction triggers, and the
    sabotage (the cursor's user_id dropped) pulls the other user's rows into
    to_compact for either caller."""
    harness = frozen
    shared_id = _seed_session(harness, user_id=OWNER_ID, main_id=TENANT, title="quantum alignment notes")
    _seed_participant(harness, conversation_id=shared_id, user_id=PARTICIPANT_ID, main_id=TENANT)
    owner_docs = [
        _message_doc(
            session_id=shared_id, user_id=OWNER_ID, main_id=TENANT,
            content=f"owner prior turn {offset}",
            seq=COMPACTION_OWNER_SEQ_START + offset,
        )
        for offset in range(COMPACTION_TRIGGER)
    ]
    participant_docs = [
        _message_doc(
            session_id=shared_id, user_id=PARTICIPANT_ID, main_id=TENANT,
            content=f"participant prior turn {offset}", seq=offset + 1,
        )
        for offset in range(COMPACTION_TRIGGER)
    ]
    harness.run(harness.db.chat_messages.insert_many(owner_docs))
    harness.run(harness.db.chat_messages.insert_many(participant_docs))
    return harness, shared_id


def test_compaction_stays_scoped_to_the_callers_rows(compaction_thread, monkeypatch):
    harness, shared_id = compaction_thread
    fake = _FakeCompactor()
    monkeypatch.setattr(sessions_module, "context_compactor", fake)

    harness.run(_maybe_compact_session_messages(
        harness.db, session_id=shared_id, user_id=PARTICIPANT_ID, main_id=TENANT,
    ))

    # The participant's own rows compacted: 21 of 41 (the last 20 stay recent).
    assert harness.run(harness.db.chat_messages.count_documents({
        "session_id": shared_id, "user_id": PARTICIPANT_ID, "compacted": True,
    })) == COMPACTION_TRIGGER - COMPACTION_KEEP_RECENT
    # THE BOUNDARY: the owner's rows are untouched by the participant's
    # compaction.
    assert harness.run(harness.db.chat_messages.count_documents({
        "session_id": shared_id, "user_id": OWNER_ID, "compacted": True,
    })) == 0
    # The summary row is the participant's own, covering only their seqs.
    summary = harness.run(harness.db.chat_messages.find_one({
        "session_id": shared_id, "user_id": PARTICIPANT_ID, "message_type": "context_summary",
    }))
    assert summary is not None
    assert summary["covers"] == {"start_seq": 1, "end_seq": COMPACTION_TRIGGER - COMPACTION_KEEP_RECENT}
    assert int(summary["seq"]) == COMPACTION_TRIGGER + 1
    assert fake.calls == [{"rows": COMPACTION_TRIGGER - COMPACTION_KEEP_RECENT,
                           "output_spec": {"user_id": PARTICIPANT_ID, "main_id": TENANT,
                                           "session_id": str(shared_id)}}]


def test_owner_compaction_stays_scoped_to_the_owners_rows(compaction_thread, monkeypatch):
    harness, shared_id = compaction_thread
    fake = _FakeCompactor()
    monkeypatch.setattr(sessions_module, "context_compactor", fake)

    harness.run(_maybe_compact_session_messages(
        harness.db, session_id=shared_id, user_id=OWNER_ID, main_id=TENANT,
    ))

    assert harness.run(harness.db.chat_messages.count_documents({
        "session_id": shared_id, "user_id": OWNER_ID, "compacted": True,
    })) == COMPACTION_TRIGGER - COMPACTION_KEEP_RECENT
    # THE BOUNDARY: the participant's rows are untouched by the owner's
    # compaction.
    assert harness.run(harness.db.chat_messages.count_documents({
        "session_id": shared_id, "user_id": PARTICIPANT_ID, "compacted": True,
    })) == 0
    summary = harness.run(harness.db.chat_messages.find_one({
        "session_id": shared_id, "user_id": OWNER_ID, "message_type": "context_summary",
    }))
    assert summary is not None
    assert summary["covers"] == {
        "start_seq": COMPACTION_OWNER_SEQ_START,
        "end_seq": COMPACTION_OWNER_SEQ_START + COMPACTION_TRIGGER - COMPACTION_KEEP_RECENT - 1,
    }
    assert int(summary["seq"]) == COMPACTION_OWNER_SEQ_START + COMPACTION_TRIGGER


# ---------------------------------------------------------------------------
# (c) Prior-turn evidence — the evidence loader keeps its user_id filter
# ---------------------------------------------------------------------------


def _seed_evidence_thread(harness, shared_id: ObjectId) -> list[ObjectId]:
    """Owner + participant rows with the SAME seqs — the legacy per-(session,
    user) seq mint shape (the plan's migration section). Both users' rows are
    candidates only for their own loader call; the duplicate-seq shape makes
    the loader guard bite even at the shared seq slots."""
    owner_a = _seed_message(
        harness, session_id=shared_id, user_id=OWNER_ID, main_id=TENANT,
        content="owner prior turn about the quarterly forecast", seq=1,
    )
    owner_b = _seed_message(
        harness, session_id=shared_id, user_id=OWNER_ID, main_id=TENANT,
        content="owner second prior turn", seq=2,
    )
    participant_a = _seed_message(
        harness, session_id=shared_id, user_id=PARTICIPANT_ID, main_id=TENANT,
        content="participant prior turn notes", seq=1,
    )
    participant_b = _seed_message(
        harness, session_id=shared_id, user_id=PARTICIPANT_ID, main_id=TENANT,
        content="participant second prior turn", seq=2,
    )
    return [owner_a, owner_b, participant_a, participant_b]


def test_evidence_loader_scoping_returns_only_the_callers_rows(frozen):
    """THE SABOTAGE TARGET (the plan's failure QA): dropping the ``user_id``
    filter from ``_load_rows`` makes this guard fail."""
    harness = frozen
    shared_id = _seed_session(harness, user_id=OWNER_ID, main_id=TENANT, title="quantum alignment notes")
    _seed_participant(harness, conversation_id=shared_id, user_id=PARTICIPANT_ID, main_id=TENANT)
    _seed_evidence_thread(harness, shared_id)

    rows = harness.run(conversation_evidence_service._load_rows(
        session_id=str(shared_id), user_id=PARTICIPANT_ID, main_id=TENANT,
    ))

    assert [row["seq"] for row in rows] == [1, 2]
    assert all(row["user_id"] == PARTICIPANT_ID for row in rows)
    assert not any("quarterly forecast" in str(row.get("content") or "") for row in rows)


class _FakeEvidenceLLM:
    """The evidence selection LLM seam (get_llm_client): selects a fixed seq
    so the artifacts are deterministic."""

    def __init__(self, selected_seqs: list[int]) -> None:
        self._selected_seqs = selected_seqs

    def with_structured_output(self, schema, method=None):
        owner = self

        class _Model:
            async def ainvoke(self, messages):
                return ConversationEvidenceSelection(
                    selected_seqs=list(owner._selected_seqs),
                    canonical_subject="participant subject",
                    rationale="ok",
                    sufficient=True,
                )

        return _Model()


def test_evidence_collect_scoping_builds_artifacts_from_the_callers_rows_only(frozen, monkeypatch):
    harness = frozen
    shared_id = _seed_session(harness, user_id=OWNER_ID, main_id=TENANT, title="quantum alignment notes")
    _seed_participant(harness, conversation_id=shared_id, user_id=PARTICIPANT_ID, main_id=TENANT)
    _seed_evidence_thread(harness, shared_id)
    monkeypatch.setattr(
        conversation_evidence_module, "get_llm_client", lambda **kwargs: _FakeEvidenceLLM([2]),
    )

    artifacts = harness.run(conversation_evidence_service.collect(
        session_id=str(shared_id), user_id=PARTICIPANT_ID, main_id=TENANT,
        current_request="a fresh request",
    ))

    ids = list(artifacts["source_material"]["source_message_ids"])
    assert len(ids) == 1
    # The selected seq-2 row is the PARTICIPANT's row, never the owner's
    # duplicate-seq row.
    blob = json.dumps(artifacts, default=str)
    assert "owner second prior turn" not in blob
    assert "participant second prior turn" in blob


# ---------------------------------------------------------------------------
# (d) History RAG — RAG keeps its user scoping
# ---------------------------------------------------------------------------


def test_rag_search_scoping_returns_only_the_callers_chat_rows(frozen):
    harness = frozen
    shared_id = _seed_session(harness, user_id=OWNER_ID, main_id=TENANT, title="quantum alignment notes")
    _seed_participant(harness, conversation_id=shared_id, user_id=PARTICIPANT_ID, main_id=TENANT)
    owner_msg = _seed_message(
        harness, session_id=shared_id, user_id=OWNER_ID, main_id=TENANT,
        content="the quantum roadmap secret owner notes", seq=1,
    )
    participant_msg = _seed_message(
        harness, session_id=shared_id, user_id=PARTICIPANT_ID, main_id=TENANT,
        content="quantum roadmap participant summary", seq=2,
    )

    result = harness.run(local_knowledge_rag_service.search(
        query="quantum roadmap", user_id=PARTICIPANT_ID, main_id=TENANT,
        session_id=str(shared_id), fetch_artifacts=False,
    ))

    assert result["ok"] is True
    sources = [item["source"] for item in result["results"]]
    assert f"chat_message://{participant_msg}" in sources
    # THE BOUNDARY: the owner's matching row never reaches the participant's
    # RAG results.
    assert f"chat_message://{owner_msg}" not in sources
    assert "secret owner notes" not in json.dumps(result["results"], default=str)


def test_rag_session_artifact_scoping_stays_user_scoped(frozen, monkeypatch):
    harness = frozen
    _seed_session(
        harness, user_id=OWNER_ID, main_id=TENANT, title="quantum alignment notes",
        latest_artifact_ref={"object_path": "artifacts/owner-brief.md", "title": "owner brief", "type": "md"},
    )
    _seed_session(harness, user_id=PARTICIPANT_ID, main_id=TENANT, title="my workspace")

    class _FakeStorage:
        def __init__(self) -> None:
            self.downloads: list[str] = []

        async def download_text(self, key, timeout_s=None):
            self.downloads.append(str(key))
            return "quantum roadmap secret brief content"

    fake_storage = _FakeStorage()
    monkeypatch.setattr(rag_module, "storage_utils", fake_storage)

    result = harness.run(local_knowledge_rag_service.search(
        query="quantum roadmap", user_id=PARTICIPANT_ID, main_id=TENANT,
        session_id="", fetch_artifacts=True,
    ))

    assert result["ok"] is True
    # THE BOUNDARY: the owner's artifact-bearing session is excluded by the
    # sess_filter's user_id — the participant's search downloads nothing and
    # returns no artifact chunk.
    assert fake_storage.downloads == []
    assert not any(str(item["source"]).startswith("artifact://") for item in result["results"])


# ---------------------------------------------------------------------------
# (e) Pending-approval aggregate — viewer-scoped (T16's limitation, PINNED)
# ---------------------------------------------------------------------------


def test_pending_approval_aggregate_is_viewer_scoped(frozen):
    harness = frozen
    shared_id = _seed_session(harness, user_id=OWNER_ID, main_id=TENANT, title="quantum alignment notes")
    _seed_participant(harness, conversation_id=shared_id, user_id=PARTICIPANT_ID, main_id=TENANT)
    # The approval is stamped with the turn's initiator (T16) — the OWNER's.
    _seed_pending_approval(harness, conversation_id=shared_id, user_id=OWNER_ID, main_id=TENANT)
    session_doc = {"_id": shared_id, "title": "quantum alignment notes"}

    # THE PINNED LIMITATION: B's payload gains NO badge for A's pending
    # approval — the aggregate remains viewer-scoped.
    harness.run(_attach_pending_approval_counts(
        harness.db, [session_doc], main_id=TENANT, user_id=PARTICIPANT_ID,
    ))
    assert "pending_approval_count" not in session_doc

    # The aggregate itself works and is keyed to the VIEWER: the participant
    # sees their OWN badge...
    _seed_pending_approval(harness, conversation_id=shared_id, user_id=PARTICIPANT_ID, main_id=TENANT)
    harness.run(_attach_pending_approval_counts(
        harness.db, [session_doc], main_id=TENANT, user_id=PARTICIPANT_ID,
    ))
    assert session_doc.get("pending_approval_count") == 1

    # ...and the owner sees THEIR badge (their own row only — the
    # participant's row is excluded from the owner's payload too).
    harness.run(_attach_pending_approval_counts(
        harness.db, [session_doc], main_id=TENANT, user_id=OWNER_ID,
    ))
    assert session_doc.get("pending_approval_count") == 1


def test_search_badge_scoping_excludes_another_members_approval(frozen, monkeypatch):
    harness = frozen
    shared_id = _seed_session(harness, user_id=OWNER_ID, main_id=TENANT, title="quantum alignment notes")
    _seed_participant(harness, conversation_id=shared_id, user_id=PARTICIPANT_ID, main_id=TENANT)
    _seed_pending_approval(harness, conversation_id=shared_id, user_id=OWNER_ID, main_id=TENANT)

    # The participant's search: the shared session is not among their results
    # (boundary (a)) — no badge either way.
    participant_response = _search(harness, monkeypatch, user_id=PARTICIPANT_ID, main_id=TENANT, q="quantum")
    assert participant_response.data["items"] == []

    # The owner's search: their own session carries THEIR badge through the
    # search surface.
    owner_response = _search(harness, monkeypatch, user_id=OWNER_ID, main_id=TENANT, q="quantum")
    items = owner_response.data["items"]
    assert [item.id for item in items] == [str(shared_id)]
    assert items[0].pending_approval_count == 1


# ---------------------------------------------------------------------------
# (f) Per-caller quota — quota stays per-caller user-scoped
# ---------------------------------------------------------------------------


@pytest.fixture
def quota_thread(frozen, monkeypatch):
    """An enterprise tenant with per-user usage rows. ``period_window`` is
    faked to a fixed window so the test never depends on the wall clock (the
    frozen boundary is the ``user_id`` filter in ``sum_usage``, not the
    windowing); the direct ``sum_usage`` call passes the same window
    explicitly."""
    harness = frozen
    monkeypatch.setattr(
        quota_module, "period_window",
        lambda *args, **kwargs: (_FIXED_WINDOW_START, _FIXED_WINDOW_END),
    )
    harness.run(harness.db.organizations.insert_one({
        "_id": ObjectId(),
        "main_id": TENANT,
        "total_points": 1000,
        "used_points": 0,
        "org_name": "Acme",
    }))
    harness.run(harness.db.token_usage_logs.insert_many([
        {"main_id": TENANT, "user_id": OWNER_ID, "total_tokens": 300,
         "status": "success", "created_at": _FIXED_SEEDED_AT},
        {"main_id": TENANT, "user_id": OWNER_ID, "total_tokens": 300,
         "status": "success", "created_at": _FIXED_SEEDED_AT},
        {"main_id": TENANT, "user_id": PARTICIPANT_ID, "total_tokens": 120,
         "status": "success", "created_at": _FIXED_SEEDED_AT},
    ]))
    return harness


def test_quota_usage_aggregate_is_per_caller_scoped(quota_thread):
    harness = quota_thread

    # THE BOUNDARY: the per-caller aggregate sums only the caller's rows.
    assert harness.run(sum_usage(
        TENANT, user_id=PARTICIPANT_ID,
        start_at=_FIXED_WINDOW_START, end_at=_FIXED_WINDOW_END,
    )) == 120
    assert harness.run(sum_usage(
        TENANT, user_id=OWNER_ID,
        start_at=_FIXED_WINDOW_START, end_at=_FIXED_WINDOW_END,
    )) == 600


def test_quota_summary_scoping_excludes_other_users_usage_rows(quota_thread):
    harness = quota_thread

    participant_summary = harness.run(get_quota_summary(
        TENANT, {"_id": PARTICIPANT_ID, "space_type": "enterprise", "org_name": "Acme"},
    ))
    assert participant_summary["usedPoints"] == 120

    owner_summary = harness.run(get_quota_summary(
        TENANT, {"_id": OWNER_ID, "space_type": "enterprise", "org_name": "Acme"},
    ))
    assert owner_summary["usedPoints"] == 600
