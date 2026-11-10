import asyncio

import pytest
import httpx
from fastapi import HTTPException

from app.dsh_runtime.plugin_ui import service as plugin_ui_service


class Catalog:
    plugins = []

    async def list_enabled(self, tenant_id, user_id):
        assert (tenant_id, user_id) == ("tenant", "user")
        return self.plugins


def test_plugin_ui_requires_current_plugin_access_and_matching_version(monkeypatch):
    asyncio.run(_check_plugin_ui_access(monkeypatch))


async def _check_plugin_ui_access(monkeypatch):
    catalog = Catalog()
    monkeypatch.setattr(plugin_ui_service, "MongoPluginCatalog", lambda: catalog)
    plugin = {"installation_id": "plugin", "version": "1.0.0",
              "client_modules": [{"id": "plugin"}], "web_routes": [{"path": "/plugin"}]}
    catalog.plugins = [plugin]
    assert await plugin_ui_service.PluginUiService._authorized_plugin(
        "tenant", "user", "plugin", "1.0.0") == plugin
    with pytest.raises(HTTPException) as outdated:
        await plugin_ui_service.PluginUiService._authorized_plugin(
            "tenant", "user", "plugin", "2.0.0")
    assert outdated.value.status_code == 403
    catalog.plugins = []
    with pytest.raises(HTTPException) as revoked:
        await plugin_ui_service.PluginUiService._authorized_plugin(
            "tenant", "user", "plugin", "1.0.0")
    assert revoked.value.status_code == 403


def test_plugin_ui_requires_both_client_and_web_capabilities(monkeypatch):
    asyncio.run(_check_plugin_ui_capabilities(monkeypatch))


async def _check_plugin_ui_capabilities(monkeypatch):
    catalog = Catalog()
    monkeypatch.setattr(plugin_ui_service, "MongoPluginCatalog", lambda: catalog)
    catalog.plugins = [{"installation_id": "plugin", "version": "1.0.0",
                        "client_modules": [], "web_routes": [{"path": "/plugin"}]}]
    with pytest.raises(HTTPException) as unavailable:
        await plugin_ui_service.PluginUiService._authorized_plugin(
            "tenant", "user", "plugin")
    assert unavailable.value.status_code == 409
    catalog.plugins = [{"installation_id": "plugin", "version": "1.0.0",
                        "client_modules": [{"id": "plugin"}], "remote_endpoints": ["plugin/list"]}]
    assert await plugin_ui_service.PluginUiService._authorized_plugin(
        "tenant", "user", "plugin") == catalog.plugins[0]
    catalog.plugins = [{"installation_id": "plugin", "version": "1.0.0",
                        "client_modules": [{"id": "plugin"}], "web_routes": [
                            {"kind": "prefix", "path": "/api"},
                            {"kind": "prefix", "path": "/plugins"},
                        ]}]
    assert await plugin_ui_service.PluginUiService._authorized_plugin(
        "tenant", "user", "plugin") == catalog.plugins[0]


def test_plugin_ui_launch_without_host_token():
    asyncio.run(_launch_without_host_token())


async def _launch_without_host_token():
    class Publisher:
        async def publish_model_profile(self, **kwargs):
            return type("Profile", (), {"profile_version": "profile"})()

    class Coordinator:
        async def ensure_runtime(self, **kwargs):
            return type("Runtime", (), {"runtime_id": "runtime"})()

    async def handler(request):
        assert request.url.path == "/v1/runtimes/runtime/managed-plugins"
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"bundles": [
            {"name": "plugin", "version": "1.0.0", "enabled": True},
        ]})

    service = plugin_ui_service.PluginUiService(
        publisher=Publisher(), coordinator=Coordinator(),
        runtime_host_url="http://runtime-host", runtime_host_token="",
        signing_secret="test-signing-secret-with-at-least-32-characters",
    )
    service._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service._authorized_plugin = lambda *args, **kwargs: _plugin_for_launch()
    try:
        ticket, kernel_session_id = await service.launch(tenant_id="tenant", user_id="user", plugin_id="id")
        assert service.tickets.verify(ticket).plugin_id == "id"
        assert kernel_session_id is None
    finally:
        await service.close()


async def _plugin_for_launch():
    return {"installation_id": "id", "name": "plugin", "version": "1.0.0",
            "web_routes": [{"path": "/plugin"}], "client_modules": [{"id": "plugin"}]}
