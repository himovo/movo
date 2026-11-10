import asyncio

from app.dsh_runtime.profile import plugins as plugin_module
from app.dsh_runtime.profile.models import RuntimeProfileSnapshot


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, _order):
        return self

    async def to_list(self, *, length):
        return self.rows


class Collection:
    def __init__(self, rows):
        self.rows = rows
        self.query = None

    def find(self, query):
        self.query = query
        return Cursor(self.rows)


class Database:
    def __init__(self, rows):
        self.dsh_plugin_installations = Collection(rows)


def test_personal_plugin_overrides_same_named_enterprise_plugin(monkeypatch):
    db = Database([
        {"_id": "org-id", "name": "shared", "version": "1.0.0", "spec": "shared@1.0.0", "owner_user_id": "", "engine": "dsh", "tool_names": ["enterprise_tool"], "availability": {"status": "session_exposed"}},
        {"_id": "personal-id", "name": "shared", "version": "2.0.0", "spec": "shared@2.0.0", "owner_user_id": "user-a", "engine": "dsh", "tool_names": ["personal_tool"], "availability": {"status": "session_exposed"}},
    ])
    monkeypatch.setattr(plugin_module, "get_db", lambda: db)

    effective = asyncio.run(plugin_module.MongoPluginCatalog().list_enabled("tenant-a", "user-a"))

    assert db.dsh_plugin_installations.query == {
        "main_id": "tenant-a", "$or": [{"enabled": True}, {"owner_user_id": ""}],
        "owner_user_id": {"$in": ["", "user-a"]}, "engine": "dsh",
    }
    assert effective == ({
        "installation_id": "personal-id",
        "name": "shared", "version": "2.0.0", "spec": "shared@2.0.0",
        "source_scope": "personal", "tool_names": ["personal_tool"], "skills": [], "commands": [],
        "web_routes": [], "client_modules": [], "remote_endpoints": [],
    },)


def test_uploaded_plugin_profile_carries_immutable_archive_reference(monkeypatch):
    archive_id = "a" * 32
    digest = "b" * 64
    monkeypatch.setattr(plugin_module, "get_db", lambda: Database([{
        "name": "uploaded", "version": "1.0.0", "spec": f"archive:{digest}",
        "_id": "uploaded-id", "owner_user_id": "", "engine": "dsh", "tool_names": ["uploaded_tool"],
        "archive_id": archive_id, "archive_digest": digest,
        "availability": {"status": "session_exposed"},
    }]))
    plugins = asyncio.run(plugin_module.MongoPluginCatalog().list_enabled("tenant-a", "user-a"))
    assert plugins[0]["archive_id"] == archive_id
    assert digest in plugin_module.plugin_versions(plugins)[0]
    snapshot = RuntimeProfileSnapshot(
        profile_version="rp-test", content_hash="0" * 64, tenant_id="tenant-a",
        model_source_tenant_id="tenant-a", model_instance_id="model", provider_id="provider",
        provider_type="openai_compatible", provider_name="provider", model_name="model",
        display_name="model", capabilities=(), plugins=plugins,
    )
    payload = snapshot.host_payload(
        gateway_url="http://model", access_token="token",
        plugin_gateway_url="http://backend/internal/dsh/plugin-archives",
    )
    assert payload["pluginGatewayUrl"].endswith("/plugin-archives")
    assert payload["plugins"][0]["archive_digest"] == digest


def test_denied_enterprise_plugin_cannot_be_restored_by_personal_same_name(monkeypatch):
    monkeypatch.setattr(plugin_module, "get_db", lambda: Database([
        {"_id": "org-id", "name": "restricted", "version": "1", "spec": "restricted@1", "owner_user_id": "", "engine": "dsh", "availability": {"status": "runtime_active"}},
        {"_id": "self-id", "name": "restricted", "version": "2", "spec": "restricted@2", "owner_user_id": "user-b", "engine": "dsh", "availability": {"status": "runtime_active"}},
        {"_id": "self-only", "name": "personal", "version": "1", "spec": "personal@1", "owner_user_id": "user-b", "engine": "dsh", "availability": {"status": "runtime_active"}},
    ]))

    async def restricted(resource_type, *, main_id, user_id, resource_ids):
        assert (resource_type, main_id, user_id) == ("plugin", "tenant-a", "user-b")
        assert list(resource_ids) == ["org-id"]
        return set()

    monkeypatch.setattr(plugin_module, "filter_allowed_resource_ids", restricted)
    plugins = asyncio.run(plugin_module.MongoPluginCatalog().list_enabled("tenant-a", "user-b"))
    assert [item["name"] for item in plugins] == ["personal"]


def test_plugin_runtime_switch_removes_every_contributed_capability(monkeypatch):
    monkeypatch.setattr(plugin_module, "get_db", lambda: Database([{
        "_id": "plugin-id", "name": "bundle", "version": "1.0.0",
        "spec": "bundle@1.0.0", "owner_user_id": "user-a", "engine": "dsh",
        "enabled": True, "tool_names": ["bundle_tool"],
        "availability": {"capabilities": {"skills": [{
            "name": "bundle-skill", "userInvocable": True,
        }], "commands": [{"name": "bundle:run", "definitionId": "bundle/run"}]}},
    }]))

    async def denied(**kwargs):
        assert kwargs["capability"] == "plugin.runtime"
        return False

    monkeypatch.setattr(plugin_module, "execution_is_allowed", denied)
    assert asyncio.run(plugin_module.MongoPluginCatalog().list_enabled("tenant-a", "user-a")) == ()


def test_failed_runtime_plugin_is_not_exposed_from_stale_capability_snapshot(monkeypatch):
    monkeypatch.setattr(plugin_module, "get_db", lambda: Database([{
        "_id": "failed-plugin", "name": "unavailable", "version": "1.0.0",
        "spec": "unavailable@1.0.0", "owner_user_id": "user-a",
        "engine": "dsh", "enabled": True,
        "availability": {"status": "failed", "capabilities": {
            "skills": [{"name": "old-skill", "userInvocable": True}],
        }},
    }]))
    assert asyncio.run(plugin_module.MongoPluginCatalog().list_enabled("tenant-a", "user-a")) == ()


def test_revalidation_pending_plugin_is_not_exposed_from_stale_snapshot(monkeypatch):
    monkeypatch.setattr(plugin_module, "get_db", lambda: Database([{
        "_id": "pending-plugin", "name": "stale", "version": "1.0.0",
        "spec": "stale@1.0.0", "owner_user_id": "user-a",
        "engine": "dsh", "enabled": True,
        "availability": {"status": "unverified", "reason": "dsh_version_changed",
                         "capabilities": {"skills": [{"name": "old-skill", "userInvocable": True}]}},
    }]))
    assert asyncio.run(plugin_module.MongoPluginCatalog().list_enabled("tenant-a", "user-a")) == ()
