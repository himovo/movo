from __future__ import annotations

from pathlib import Path
from threading import Event, Thread

import pytest

from app.jobs import ScriptJobs


class EngineFake:
    def __init__(self) -> None:
        self.created = None
        self.cleaned = []

    def find_compose_service(self, project, service):
        return "proxy-id"

    def create_outbound_network(self, name):
        return "network-id"

    def connect_network(self, network_id, container_id, aliases):
        assert aliases == ["sandbox-egress"]

    def create(self, name, payload):
        self.created = payload
        return "job-container"

    def start(self, container_id):
        pass

    def wait(self, container_id, timeout):
        return 0

    def logs(self, container_id):
        return bytes([1, 0, 0, 0, 0, 0, 0, 3]) + b"ok\n"

    def remove(self, container_id):
        self.cleaned.append("container")

    def disconnect_network(self, network_id, container_id):
        self.cleaned.append("proxy")

    def remove_network(self, network_id):
        self.cleaned.append("network")


def test_job_is_scoped_to_one_volume_subpath_and_cleaned(tmp_path: Path, monkeypatch) -> None:
    job_id = "a" * 32
    job = tmp_path / job_id
    job.mkdir()
    for name in ("runner.py", "plugin.py", "stdin.json"):
        (job / name).write_text("{}")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "test-script:1")
    engine = EngineFake()
    result = ScriptJobs(engine).execute(job_id)
    assert result == {"exit_code": 0, "stdout": "ok\n", "stderr": ""}
    assert engine.created["HostConfig"]["Mounts"][0]["VolumeOptions"]["Subpath"] == job_id
    assert engine.created["HostConfig"]["ReadonlyRootfs"] is True
    assert engine.created["HostConfig"]["NetworkMode"] == "network-id"
    assert any(item.startswith("NODE_PATH=/opt/movo-skill-node-modules") for item in engine.created["Env"])
    assert any(item.startswith("PATH=/opt/movo-skill-node-modules/.bin:") for item in engine.created["Env"])
    assert engine.cleaned == ["container", "proxy", "network"]


def test_unprepared_job_does_not_start_container(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "test-script:1")
    engine = EngineFake()
    with pytest.raises(ValueError):
        ScriptJobs(engine).execute("b" * 32)
    assert engine.created is None


def test_second_job_waits_without_sharing_the_first_slot(tmp_path: Path, monkeypatch) -> None:
    for job_id in ("c" * 32, "d" * 32):
        job = tmp_path / job_id
        job.mkdir()
        for name in ("runner.py", "plugin.py", "stdin.json"):
            (job / name).write_text("{}")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "test-script:1")
    monkeypatch.setenv("MOVO_SANDBOX_MAX_CONCURRENT", "1")
    entered = Event()
    release = Event()

    class BlockingEngine(EngineFake):
        def wait(self, container_id, timeout):
            entered.set()
            release.wait(2)
            return 0

    jobs = ScriptJobs(BlockingEngine())
    first = Thread(target=jobs.execute, args=("c" * 32,))
    second = Thread(target=jobs.execute, args=("d" * 32,))
    first.start()
    assert entered.wait(1)
    second.start()
    assert jobs.status()["running"] == 1
    release.set()
    first.join(2)
    second.join(2)
    assert not first.is_alive() and not second.is_alive()
    assert jobs.status()["running"] == 0


def test_queue_setting_persists_across_manager_restart(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "test-script:1")
    first = ScriptJobs(EngineFake())
    assert first.set_max_pending(3)["max_pending"] == 3
    assert ScriptJobs(EngineFake()).status()["max_pending"] == 3
    assert (tmp_path / "workspaces" / ".manager-state" / "sandbox-settings.json").is_file()


def test_selected_skill_is_mounted_read_only_from_immutable_cache(tmp_path: Path, monkeypatch) -> None:
    job_id = "e" * 32
    digest = "f" * 64
    job = tmp_path / job_id
    job.mkdir()
    for name in ("runner.py", "plugin.py", "stdin.json"):
        (job / name).write_text("{}")
    (job / "skill-digest").write_text(digest)
    (tmp_path / "skill-cache" / digest).mkdir(parents=True)
    (tmp_path / "skill-cache" / digest / "SKILL.md").write_text("---\nname: sample\n---\n")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "test-script:1")
    engine = EngineFake()
    ScriptJobs(engine).execute(job_id)
    skill_mount = engine.created["HostConfig"]["Mounts"][1]
    assert skill_mount["ReadOnly"] is True
    assert skill_mount["Target"] == "/job/skills"
    assert skill_mount["VolumeOptions"]["Subpath"] == f"skill-cache/{digest}"
