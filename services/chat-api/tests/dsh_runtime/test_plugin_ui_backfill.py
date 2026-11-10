import asyncio

from app.dsh_runtime.plugin_ui import backfill


def test_legacy_plugin_page_capabilities_are_refreshed_once(monkeypatch):
    captured = []
    row = {"availability": {"capabilities": {"clientModules": [{"id": "plugin"}]}}}

    class Repository:
        async def get(self, **kwargs):
            captured.append(kwargs)
            return row

    async def version():
        return "0.2.1-alpha.1"

    async def assess(value, **kwargs):
        captured.append((value, kwargs["dsh_version"]))
        return value

    monkeypatch.setattr(backfill, "PluginInstallationRepository", Repository)
    monkeypatch.setattr(backfill, "running_dsh_version", version)
    monkeypatch.setattr(backfill, "assess_existing_installation", assess)
    plugin = {"installation_id": "plugin-id", "source_scope": "personal"}
    asyncio.run(backfill.backfill_browser_capabilities(
        tenant_id="tenant", user_id="user", plugin=plugin,
    ))
    assert captured[0] == {"main_id": "tenant", "user_id": "user", "plugin_id": "plugin-id"}
    assert captured[1] == (row, "0.2.1-alpha.1")
    row["availability"]["capabilities"].update({"webRoutes": [], "remoteEndpoints": []})
    captured.clear()
    asyncio.run(backfill.backfill_browser_capabilities(
        tenant_id="tenant", user_id="user", plugin=plugin,
    ))
    assert len(captured) == 1
