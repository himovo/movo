import asyncio

import pytest

from app.dsh_runtime.profile import plugin_command_selection as selection


def test_plugin_command_requires_current_parent_permission(monkeypatch):
    plugin = {
        "installation_id": "a" * 24,
        "commands": [{"name": "paper:import", "definitionId": "paper-plugin/import"}],
    }

    class Catalog:
        async def list_enabled(self, tenant_id, user_id):
            assert (tenant_id, user_id) == ("tenant", "user")
            return (plugin,)

    monkeypatch.setattr(selection, "MongoPluginCatalog", Catalog)
    selected = selection.selection_id("a" * 24, "paper:import")
    assert asyncio.run(selection.require_plugin_command(
        tenant_id="tenant", user_id="user", selected_id=selected,
    ))[1]["name"] == "paper:import"
    with pytest.raises(PermissionError):
        asyncio.run(selection.require_plugin_command(
            tenant_id="tenant", user_id="user",
            selected_id=selection.selection_id("b" * 24, "paper:import"),
        ))
