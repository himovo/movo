import asyncio
from types import SimpleNamespace

from app.dsh_runtime import plugin_command_runner as module


class Gateway:
    def __init__(self, kind="success"):
        self.kind = kind
        self.calls = []

    async def head_cursor(self, session_id):
        self.calls.append(("head", session_id))
        return 7

    async def execute_plugin_command(self, session_id, selected_id, line):
        self.calls.append(("execute", session_id, selected_id, line))
        return {"commandId": "native-command", "result": {"kind": self.kind, "text": "Command output"}}

    async def events_once(self, session_id, after_cursor):
        self.calls.append(("events", session_id, after_cursor))
        return [SimpleNamespace(type="kernel.native.event", cursor=8)]


class Events:
    def project(self, event, *, message_id):
        return None


class Registry:
    def __init__(self):
        self.rows = []
        self.finished = False
        self.aborted = False

    async def publish_standalone(self, message_id, row, *, publish_live=True):
        self.rows.append((message_id, row, publish_live))
        return {**row, "stream_seq": len(self.rows)}

    async def finish(self, message_id):
        self.finished = True
        return []

    async def flush(self, message_id):
        return None

    async def abort(self, message_id):
        self.aborted = True


class Bindings:
    def __init__(self):
        self.heads = []

    async def mark_plugin_command_head(self, binding_id, *, message_id, native_cursor):
        self.heads.append((binding_id, message_id, native_cursor))
        return True


class Writer:
    instances = []

    def __init__(self, **kwargs):
        self.writes = []
        self.closed = False
        self.instances.append(self)

    def enqueue(self, write):
        self.writes.append(write)

    async def close(self):
        self.closed = True

    async def abort(self):
        self.closed = True


class Finalizer:
    def __init__(self, bindings, conversations):
        self.calls = []

    async def finalize(self, **kwargs):
        self.calls.append(kwargs)


def test_native_plugin_command_persists_result_and_terminal(monkeypatch):
    monkeypatch.setattr(module, "DurableKernelEventWriter", Writer)
    monkeypatch.setattr(module, "TurnStateFinalizer", Finalizer)
    async def authorized(**kwargs):
        return ({"name": "plugin"}, {"name": "render"})
    monkeypatch.setattr(module, "require_plugin_command", authorized)
    gateway = Gateway()
    registry = Registry()
    bindings = Bindings()
    runner = module.PluginCommandRunner(
        gateway=gateway, conversations=object(), bindings=bindings,
        events=Events(), turn_events=registry,
    )
    binding = {"kernel_session_id": "native-session", "binding_id": "binding",
               "tenant_id": "tenant", "user_id": "user", "conversation_id": "conversation"}
    stream = module.LiveTurnStream()
    status = asyncio.run(runner.run(
        binding=binding, message_id="assistant", text="/render slide",
        selected_command_id="dsh_plugin_command:reference", live_stream=stream,
    ))
    assert status == "completed"
    assert gateway.calls == [
        ("head", "native-session"),
        ("execute", "native-session", "dsh_plugin_command:reference", "/render slide"),
        ("events", "native-session", 7),
    ]
    assert Writer.instances[-1].writes[0].event.cursor == 8
    assert bindings.heads == [("binding", "assistant", 7)]
    assert Writer.instances[-1].closed
    assert [row[1]["type"] for row in registry.rows] == [
        "run.started", "item.completed", "run.completed",
    ]
    assert registry.rows[-1][2] is False
    assert registry.finished
    assert runner._finalizer.calls[0]["assistant"].content == "Command output"


def test_revoked_plugin_command_never_reaches_native_runtime(monkeypatch):
    monkeypatch.setattr(module, "DurableKernelEventWriter", Writer)
    monkeypatch.setattr(module, "TurnStateFinalizer", Finalizer)

    async def denied(**kwargs):
        raise PermissionError("Selected plugin command is unavailable to this user")

    monkeypatch.setattr(module, "require_plugin_command", denied)
    gateway = Gateway()
    registry = Registry()
    runner = module.PluginCommandRunner(
        gateway=gateway, conversations=object(), bindings=Bindings(),
        events=Events(), turn_events=registry,
    )
    binding = {"kernel_session_id": "native-session", "binding_id": "binding",
               "tenant_id": "tenant", "user_id": "user", "conversation_id": "conversation"}
    status = asyncio.run(runner.run(
        binding=binding, message_id="assistant-denied", text="/render slide",
        selected_command_id="dsh_plugin_command:reference", live_stream=module.LiveTurnStream(),
    ))
    assert status == "failed"
    assert gateway.calls == []
    assert [row[1]["type"] for row in registry.rows] == ["item.completed", "run.failed"]


def test_native_success_with_persistence_failure_waits_for_durable_recovery(monkeypatch):
    monkeypatch.setattr(module, "DurableKernelEventWriter", Writer)
    monkeypatch.setattr(module, "TurnStateFinalizer", Finalizer)

    async def authorized(**kwargs):
        return ({"name": "plugin"}, {"name": "render"})

    monkeypatch.setattr(module, "require_plugin_command", authorized)

    class FailingGateway(Gateway):
        async def events_once(self, session_id, after_cursor):
            raise OSError("event store unavailable")

    registry = Registry()
    runner = module.PluginCommandRunner(
        gateway=FailingGateway(), conversations=object(), bindings=Bindings(),
        events=Events(), turn_events=registry,
    )
    binding = {"kernel_session_id": "native-session", "binding_id": "binding",
               "tenant_id": "tenant", "user_id": "user", "conversation_id": "conversation"}
    status = asyncio.run(runner.run(
        binding=binding, message_id="assistant-recovery", text="/render slide",
        selected_command_id="dsh_plugin_command:reference", live_stream=module.LiveTurnStream(),
    ))
    assert status == "pending_recovery"
    assert registry.aborted
    assert not registry.finished
    assert not runner._finalizer.calls
    assert [row[1]["type"] for row in registry.rows] == ["run.started"]
