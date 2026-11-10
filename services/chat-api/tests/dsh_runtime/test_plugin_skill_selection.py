import asyncio

import pytest

from app.dsh_runtime.profile import plugin_skill_selection as selection


def test_plugin_skill_requires_authorized_parent_and_user_invocation(monkeypatch):
    plugin = {
        "installation_id": "a" * 24,
        "skills": [{"name": "paper-review", "userInvocable": True},
                   {"name": "hidden-helper", "userInvocable": False}],
    }

    class Catalog:
        async def list_enabled(self, tenant_id, user_id):
            assert (tenant_id, user_id) == ("tenant", "user")
            return (plugin,)

    monkeypatch.setattr(selection, "MongoPluginCatalog", Catalog)
    selected = selection.selection_id("a" * 24, "paper-review")
    assert asyncio.run(selection.require_plugin_skill(
        tenant_id="tenant", user_id="user", selected_id=selected,
    ))[1]["name"] == "paper-review"
    with pytest.raises(PermissionError):
        asyncio.run(selection.require_plugin_skill(
            tenant_id="tenant", user_id="user",
            selected_id=selection.selection_id("a" * 24, "hidden-helper"),
        ))
    with pytest.raises(PermissionError):
        asyncio.run(selection.require_plugin_skill(
            tenant_id="tenant", user_id="user",
            selected_id=selection.selection_id("b" * 24, "paper-review"),
        ))
