from __future__ import annotations

from pathlib import Path

from app.task_containers import TaskContainers


class EngineFake:
    def __init__(self) -> None:
        self.created = 0
        self.executed: list[list[str]] = []
        self.killed = False
        self.removed = False

    def find_compose_service(self, project, service):
        return "proxy"

    def create_outbound_network(self, name):
        return "network"

    def connect_network(self, *args):
        pass

    def create(self, name, payload):
        self.created += 1
        assert payload["HostConfig"]["ReadonlyRootfs"] is True
        assert payload["HostConfig"]["Mounts"][0]["VolumeOptions"]["Subpath"] == "a" * 32 + "/work"
        assert "NODE_PATH=/job/work/.dependencies/node/node_modules:/opt/movo-skill-node-modules" in payload["Env"]
        assert any(value.startswith("PATH=/job/work/.dependencies/bin:") for value in payload["Env"])
        return "container"

    def start(self, container):
        pass

    def execute(self, container, command, timeout):
        self.executed.append(command)
        return 0, b"ok", b""

    def kill(self, container):
        self.killed = True

    def remove(self, container):
        self.removed = True

    def disconnect_network(self, *args):
        pass

    def remove_network(self, *args):
        pass

    def inspect(self, container):
        return {"Id": container}


def test_task_reuses_one_container_and_freezes_before_disposal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "script:test")
    task_id = "a" * 32
    for call_id in ("b" * 32, "c" * 32):
        call = tmp_path / task_id / "work" / "calls" / call_id
        call.mkdir(parents=True)
        for filename in ("runner.py", "plugin.py", "stdin.json"):
            (call / filename).write_text("{}")
    engine = EngineFake()
    tasks = TaskContainers(engine)
    assert (tmp_path / ".manager-state" / "script-task-leases.json").is_file()
    assert tasks.execute(task_id, "b" * 32)["stdout"] == "ok"
    assert tasks.execute(task_id, "c" * 32)["stdout"] == "ok"
    assert engine.created == 1
    assert len(engine.executed) == 2
    restored = TaskContainers(engine)
    restored.freeze(task_id)
    assert engine.killed
    restored.dispose(task_id)
    assert engine.removed
