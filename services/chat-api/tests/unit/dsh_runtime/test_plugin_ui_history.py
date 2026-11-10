from __future__ import annotations

import asyncio

from app.dsh_runtime.plugin_ui import history


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        self.iterator = iter(self.rows)
        return self

    async def __anext__(self):
        try:
            return next(self.iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class Collection:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def find(self, query, projection):
        self.queries.append(query)
        return Cursor(self.rows)


class Database:
    def __init__(self):
        self.chat_sessions = Collection([{"_id": "owned-conversation"}])
        self.agent_kernel_bindings = Collection([{
            "profile_version": "rp-old", "kernel_session_id": "dsh-owned",
        }])


class Http:
    def __init__(self):
        self.requests = []

    async def post(self, url, *, headers, json):
        self.requests.append((url, json))
        return self

    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"copied": 1, "unavailable": 0, "availableSessionIds": ["dsh-owned"]}


def test_plugin_history_uses_owned_conversations_only(monkeypatch):
    db = Database()
    http = Http()
    monkeypatch.setattr(history, "get_db", lambda: db)

    asyncio.run(history.hydrate_owned_history(
        http=http, host_url="http://host", headers={}, tenant_id="tenant-a",
        user_id="user-a", target_profile_version="rp-current", runtime_id="runtime-a",
    ))

    assert db.chat_sessions.queries == [{"main_id": "tenant-a", "user_id": "user-a"}]
    assert db.agent_kernel_bindings.queries == [{
        "tenant_id": "tenant-a", "conversation_id": {"$in": ["owned-conversation"]},
        "current": True, "execution_location": "server",
    }]
    assert http.requests == [("http://host/v1/runtimes/runtime-a/plugin-history/hydrate", {
        "tenantId": "tenant-a", "targetProfileVersion": "rp-current",
        "sessions": [{"profileVersion": "rp-old", "sessionId": "dsh-owned"}],
    })]
