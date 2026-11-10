import asyncio

from app.dsh_runtime.plugin_management import runtime_health


class Collection:
    def __init__(self):
        self.calls = []

    async def update_one(self, query, update):
        self.calls.append((query, update))


class Database:
    def __init__(self):
        self.dsh_plugin_installations = Collection()


def test_only_omitted_plugin_is_marked_unavailable(monkeypatch):
    database = Database()
    monkeypatch.setattr(runtime_health, "get_db", lambda: database)
    omitted = {"installation_id": "a" * 24, "version": "1.0.0"}
    active = {"installation_id": "b" * 24, "version": "2.0.0"}
    asyncio.run(runtime_health.mark_runtime_unavailable(
        tenant_id="tenant", requested=[omitted, active], activated=[active],
        reason="DSH plugin failed to activate",
    ))
    assert len(database.dsh_plugin_installations.calls) == 1
    query, update = database.dsh_plugin_installations.calls[0]
    assert query["main_id"] == "tenant"
    assert query["version"] == "1.0.0"
    assert update["$set"]["availability.status"] == "failed"
    assert update["$set"]["availability.error_code"] == "runtime_activation_failed"
