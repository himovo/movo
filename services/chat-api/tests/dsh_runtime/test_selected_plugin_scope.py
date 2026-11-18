import asyncio
from unittest.mock import AsyncMock

import pytest

from app.dsh_runtime.profile import selected_plugin_scope as scope_module


def test_explicit_command_and_skill_use_current_authorization(monkeypatch):
    command = AsyncMock(return_value=({"installation_id": "command-owner"}, {}))
    skill = AsyncMock(return_value=({"installation_id": "skill-owner"}, {}))
    monkeypatch.setattr(scope_module, "require_plugin_command", command)
    monkeypatch.setattr(scope_module, "require_plugin_skill", skill)

    async def run():
        assert await scope_module.selected_plugin_scope("tenant", "user") == {}
        assert command.await_count == skill.await_count == 0
        assert await scope_module.selected_plugin_scope(
            "tenant", "user", command_id="dsh_plugin_command:opaque",
        ) == {"selected_plugin_id": "command-owner"}
        assert await scope_module.selected_plugin_scope(
            "tenant", "user", skill_id="dsh_plugin_skill:opaque",
        ) == {"selected_plugin_id": "skill-owner"}
        skill.side_effect = PermissionError("revoked")
        with pytest.raises(PermissionError):
            await scope_module.selected_plugin_scope("tenant", "user", skill_id="dsh_plugin_skill:revoked")

    asyncio.run(run())
