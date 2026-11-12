import asyncio

import pytest
from fastapi import HTTPException

from app.services import chat_file_previews as previews
from app.api.endpoints import chat_file_preview as endpoints


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, length=None):
        return self.rows

    def __aiter__(self):
        self._iterator = iter(self.rows)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _Collection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query):
        return _Cursor(self.rows)

    async def find_one(self, query):
        return next((row for row in self.rows if all(row.get(key) == value for key, value in query.items())), None)


class _Database:
    def __init__(self):
        self.session_participants = _Collection([])
        self.chat_uploads = _Collection([
            {"_id": "owner/draft.xlsx", "main_id": "tenant", "user_id": "owner", "filename": "draft.xlsx"},
        ])
        self.chat_messages = _Collection([
            {"documents": [{"object_path": "owner/upload.pdf", "filename": "upload.pdf"}]},
            {"execution_events": [{"item_kind": "artifact", "type": "item.completed", "payload": {
                "object_path": "owner/output.xlsx", "filename": "output.xlsx",
            }}, {"item_kind": "tool", "type": "item.completed", "payload": {
                "artifacts": [{"object_path": "owner/page.html", "filename": "page.html"}],
            }}]},
        ])
        self.execution_runs_v3 = _Collection([])
        self.execution_logs = _Collection([])

    def __getitem__(self, name):
        return getattr(self, name)


def test_session_file_access_requires_membership_and_exact_reference(monkeypatch):
    async def allow(*args, **kwargs):
        return {}

    monkeypatch.setattr(previews, "get_db", _Database)
    monkeypatch.setattr(previews, "member_conversation", allow)
    session_id = "507f1f77bcf86cd799439011"

    async def verify():
        upload = await previews.require_session_file(session_id, "owner/upload.pdf", "tenant", "member")
        generated = await previews.require_session_file(session_id, "owner/output.xlsx", "tenant", "member")
        html = await previews.require_session_file(session_id, "owner/page.html", "tenant", "member")
        assert upload["filename"] == "upload.pdf"
        assert generated["filename"] == "output.xlsx"
        assert html["filename"] == "page.html"
        with pytest.raises(HTTPException) as denied:
            await previews.require_session_file(session_id, "owner/private.pdf", "tenant", "member")
        assert denied.value.status_code == 404

    asyncio.run(verify())

    async def deny(*args, **kwargs):
        raise LookupError("conversation_not_found")

    monkeypatch.setattr(previews, "member_conversation", deny)
    with pytest.raises(HTTPException) as denied:
        asyncio.run(previews.require_session_file(session_id, "owner/upload.pdf", "tenant", "outsider"))
    assert denied.value.status_code == 404


def test_draft_preview_requires_upload_owner(monkeypatch):
    async def identity(_authorization):
        return {"main_id": "tenant", "user": {"_id": "other"}}

    monkeypatch.setattr(endpoints, "get_db", _Database)
    monkeypatch.setattr(endpoints, "_resolve_session_user", identity)
    with pytest.raises(HTTPException) as denied:
        asyncio.run(endpoints._authorized_draft("owner/draft.xlsx", "Bearer token"))
    assert denied.value.status_code == 404


def test_generated_file_title_without_extension_uses_storage_path_type():
    assert previews.preview_kind("Quarterly report", "owner/output.docx") == "office"
    assert previews.preview_kind("Sales data", "owner/output.xlsx") == "office"
    assert previews.preview_kind("Final report", "owner/output.pdf") == "pdf"
    assert previews.preview_kind("Landing page", "owner/page.html") == "html"
    assert previews.preview_kind("Generated script", "owner/result.py") == "code"
