import time

import pytest

from app.dsh_runtime.plugin_ui.tickets import PluginUiTickets


def test_plugin_ui_ticket_is_scoped_signed_and_expires(monkeypatch):
    clock = 1000
    monkeypatch.setattr(time, "time", lambda: clock)
    tickets = PluginUiTickets("s" * 48, lifetime_seconds=60)
    token = tickets.issue(tenant_id="tenant", user_id="user", plugin_id="plugin",
                          plugin_version="1.0.0", profile_version="profile")
    claim = tickets.verify(token)
    assert (claim.tenant_id, claim.user_id, claim.plugin_id) == ("tenant", "user", "plugin")
    with pytest.raises(ValueError):
        tickets.verify(token[:-1] + ("x" if token[-1] != "x" else "y"))
    monkeypatch.setattr(time, "time", lambda: clock + 61)
    with pytest.raises(ValueError):
        tickets.verify(token)
