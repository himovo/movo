import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.endpoints import dsh_plugins
from app.api.principal import require_api_principal


def test_selectable_plugin_skill_endpoint_filters_scope_visibility_and_paginates(monkeypatch):
    class Catalog:
        async def list_enabled(self, main_id, user_id):
            assert (main_id, user_id) == ("tenant", "user")
            return (
                {"installation_id": "a" * 24, "source_scope": "personal", "name": "paper-plugin",
                 "skills": [{"name": "read-paper", "description": "Read a PDF", "userInvocable": True},
                            {"name": "private-helper", "userInvocable": False}]},
                {"installation_id": "b" * 24, "source_scope": "organization", "name": "design-plugin",
                 "skills": [{"name": "make-slide", "description": "Create a slide", "userInvocable": True}]},
            )

    monkeypatch.setattr(dsh_plugins, "MongoPluginCatalog", Catalog)
    principal = SimpleNamespace(kind="end_user", main_id="tenant", user_id="user")
    first = asyncio.run(dsh_plugins.selectable_plugin_skills(limit=1, principal=principal))
    assert [item["name"] for item in first["data"]["items"]] == ["read-paper"]
    assert first["data"]["nextCursor"] == "1"
    second = asyncio.run(dsh_plugins.selectable_plugin_skills(cursor=1, limit=1, principal=principal))
    assert [item["name"] for item in second["data"]["items"]] == ["make-slide"]
    assert second["data"]["hasMore"] is False
    org = asyncio.run(dsh_plugins.selectable_plugin_skills(scope="organization", principal=principal))
    assert [item["name"] for item in org["data"]["items"]] == ["make-slide"]
    search = asyncio.run(dsh_plugins.selectable_plugin_skills(keyword="pdf", principal=principal))
    assert [item["name"] for item in search["data"]["items"]] == ["read-paper"]


def test_selectable_plugin_skill_endpoint_rejects_non_user_and_invalid_query():
    admin = SimpleNamespace(kind="admin_service", main_id="tenant", user_id="")
    with pytest.raises(HTTPException) as denied:
        asyncio.run(dsh_plugins.selectable_plugin_skills(principal=admin))
    assert denied.value.status_code == 403
    user = SimpleNamespace(kind="end_user", main_id="tenant", user_id="user")
    with pytest.raises(HTTPException) as invalid:
        asyncio.run(dsh_plugins.selectable_plugin_skills(limit=51, principal=user))
    assert invalid.value.status_code == 400


def test_selectable_plugin_skill_http_contract(monkeypatch):
    class Catalog:
        async def list_enabled(self, main_id, user_id):
            return ({"installation_id": "a" * 24, "source_scope": "personal",
                     "name": "plugin", "skills": [{"name": "review", "description": "Review a paper",
                                                   "userInvocable": True}]},)

    monkeypatch.setattr(dsh_plugins, "MongoPluginCatalog", Catalog)
    app = FastAPI()
    app.include_router(dsh_plugins.router, prefix="/api")
    app.dependency_overrides[require_api_principal] = lambda: SimpleNamespace(
        kind="end_user", main_id="tenant", user_id="user",
    )
    response = TestClient(app).get("/api/dsh-plugins/personal/selectable-skills", params={"keyword": "paper"})
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["id"].startswith("dsh_plugin_skill:")
    assert TestClient(app).get("/api/dsh-plugins/personal/selectable-skills", params={"limit": 51}).status_code == 400


def test_personal_plugin_catalog_marks_execution_gate_without_hiding_installation(monkeypatch):
    async def list_rows(main_id, user_id):
        assert (main_id, user_id) == ("tenant", "user")
        return [{"id": "personal", "scope": "personal", "name": "example"}]

    async def denied(**kwargs):
        assert kwargs == {"main_id": "tenant", "user_id": "user", "capability": "plugin.runtime"}
        return False

    monkeypatch.setattr(dsh_plugins.repository, "list", list_rows)
    monkeypatch.setattr(dsh_plugins, "execution_is_allowed", denied)
    principal = SimpleNamespace(kind="end_user", main_id="tenant", user_id="user")
    result = asyncio.run(dsh_plugins.list_plugins("personal", principal))
    assert result["data"] == [{"id": "personal", "scope": "personal", "name": "example",
                               "execution_allowed": False}]


def test_selectable_plugin_commands_inherit_parent_plugin_visibility(monkeypatch):
    class Catalog:
        async def list_enabled(self, main_id, user_id):
            assert (main_id, user_id) == ("tenant", "user")
            return ({"installation_id": "a" * 24, "source_scope": "organization",
                     "name": "design-plugin", "commands": [
                         {"name": "render", "description": "Render a design", "definitionId": "design/render"},
                         {"name": "stale", "description": "Unavailable"},
                     ]},)

    monkeypatch.setattr(dsh_plugins, "MongoPluginCatalog", Catalog)
    app = FastAPI()
    app.include_router(dsh_plugins.router, prefix="/api")
    app.dependency_overrides[require_api_principal] = lambda: SimpleNamespace(
        kind="end_user", main_id="tenant", user_id="user",
    )
    client = TestClient(app)
    response = client.get("/api/dsh-plugins/personal/selectable-commands", params={"keyword": "render"})
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["id"].startswith("dsh_plugin_command:")
    assert items[0]["entryKind"] == "command"
    assert items[0]["pluginName"] == "design-plugin"
    assert client.get("/api/dsh-plugins/personal/selectable-commands", params={"limit": 51}).status_code == 400


def test_personal_install_cannot_start_validation_runtime_without_sandbox_access(monkeypatch):
    async def denied(**kwargs):
        return False

    class Installer:
        def __init__(self):
            raise AssertionError("the installer must not run")

    monkeypatch.setattr(dsh_plugins, "execution_is_allowed", denied)
    monkeypatch.setattr(dsh_plugins, "DshPluginInstaller", Installer)
    principal = SimpleNamespace(kind="end_user", main_id="tenant", user_id="user")
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(dsh_plugins.install_plugin("personal", dsh_plugins.InstallRequest(spec="plugin@1.0.0"), principal))
    assert rejected.value.status_code == 403
    assert rejected.value.detail == "plugin_runtime_access_denied"


def test_enabling_old_plugin_requires_current_dsh_assessment(monkeypatch):
    row = {"_id": "a" * 24, "main_id": "tenant", "owner_user_id": "",
           "name": "plugin", "version": "1.0.0", "spec": "plugin@1.0.0",
           "availability": {"status": "session_exposed", "dsh_version": "0.2.1"}}
    calls = []

    async def get(**kwargs):
        return row

    async def version():
        return "0.2.2"

    async def reassess(existing, **kwargs):
        calls.append(existing["spec"])
        return {**existing, "availability": {"status": "version_incompatible", "dsh_version": "0.2.2"}}

    async def enable(**kwargs):
        raise AssertionError("incompatible plugin must not be enabled")

    monkeypatch.setattr(dsh_plugins.repository, "get", get)
    monkeypatch.setattr(dsh_plugins.repository, "set_enabled", enable)
    monkeypatch.setattr(dsh_plugins, "_running_version", version)
    monkeypatch.setattr(dsh_plugins, "assess_existing_installation", reassess)
    principal = SimpleNamespace(kind="admin_service", main_id="tenant", user_id="")
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(dsh_plugins.set_plugin_enabled(
            "organization", "a" * 24, dsh_plugins.EnabledRequest(enabled=True), principal,
        ))
    assert rejected.value.status_code == 409
    assert calls == ["plugin@1.0.0"]


def test_personal_plugin_access_endpoint_reads_enterprise_gate(monkeypatch):
    async def denied(**kwargs):
        assert kwargs == {"main_id": "tenant", "user_id": "user", "capability": "plugin.runtime"}
        return False

    monkeypatch.setattr(dsh_plugins, "execution_is_allowed", denied)
    app = FastAPI()
    app.include_router(dsh_plugins.router, prefix="/api")
    app.dependency_overrides[require_api_principal] = lambda: SimpleNamespace(
        kind="end_user", main_id="tenant", user_id="user",
    )
    response = TestClient(app).get("/api/dsh-plugins/personal/execution-access")
    assert response.status_code == 200
    assert response.json()["data"] == {"allowed": False}
