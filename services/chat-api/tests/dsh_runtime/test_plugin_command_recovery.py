import asyncio
from types import SimpleNamespace

from app.dsh_runtime.plugin_command_recovery import recover_plugin_command_terminal
from app.dsh_runtime.profile.plugin_command_selection import selection_id


class Gateway:
    def __init__(self, native):
        self.native = native
        self.after = None

    async def events_once(self, session_id, after_cursor):
        self.after = (session_id, after_cursor)
        return self.native


class Events:
    def __init__(self):
        self.rows = []

    async def persist_projections(self, rows, **scope):
        self.rows.extend(rows)


def native(event_type, **payload):
    return SimpleNamespace(source=SimpleNamespace(native_event_type=event_type), payload=payload)


def test_recovery_uses_only_matching_native_command_after_claim_head():
    selected_id = selection_id("a" * 24, "render")
    binding = {
        "tenant_id": "tenant", "user_id": "user", "conversation_id": "conversation",
        "kernel_session_id": "session", "active_turn": {
            "turn_context": {"selected_command_id": selected_id},
            "command_after_cursor": 9,
        },
    }
    gateway = Gateway([
        native("command/run", commandId="other", name="unrelated"),
        native("command/done", commandId="other", kind="success", text="other"),
        native("command/run", commandId="match", name="render"),
        native("command/done", commandId="match", kind="success", text="Recovered output"),
    ])
    events = Events()
    recovered = asyncio.run(recover_plugin_command_terminal(
        gateway=gateway, events=events, binding=binding, message_id="assistant",
    ))
    assert recovered
    assert gateway.after == ("session", 9)
    assert [row["type"] for row in events.rows] == ["item.completed", "run.completed"]
    assert events.rows[0]["payload"]["text"] == "Recovered output"


def test_recovery_keeps_claim_running_without_matching_command_done():
    binding = {
        "tenant_id": "tenant", "user_id": "user", "conversation_id": "conversation",
        "kernel_session_id": "session", "active_turn": {
            "turn_context": {"selected_command_id": selection_id("a" * 24, "render")},
            "command_after_cursor": 9,
        },
    }
    events = Events()
    recovered = asyncio.run(recover_plugin_command_terminal(
        gateway=Gateway([native("command/run", commandId="match", name="render")]),
        events=events, binding=binding, message_id="assistant",
    ))
    assert not recovered
    assert events.rows == []
