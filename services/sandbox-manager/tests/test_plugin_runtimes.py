from __future__ import annotations

from pathlib import Path

from app.plugin_runtimes import PluginRuntimes


class EngineFake:
    def __init__(self) -> None:
        self.payload = None
        self.connected = []
        self.cleaned = []

    def find_compose_service(self, project, service):
        return service

    def create_internal_network(self, name):
        return "private-network"

    def connect_network(self, network_id, container_id, aliases):
        self.connected.append((container_id, aliases))

    def create(self, name, payload):
        self.payload = payload
        return "child-container"

    def start(self, container_id):
        pass

    def kill(self, container_id):
        self.cleaned.append("killed")

    def remove(self, container_id):
        self.cleaned.append("removed")

    def disconnect_network(self, network_id, container_id):
        self.cleaned.append(container_id)

    def remove_network(self, network_id):
        self.cleaned.append("network")


def test_plugin_runtime_has_private_storage_and_scoped_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("MOVO_SANDBOX_RUNTIME_IMAGE", "dsh-test:1")
    monkeypatch.setenv("MOVO_SANDBOX_RUNTIME_VOLUME", "runtime-volume")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "workspace-volume")
    (tmp_path / "plugin-archives").mkdir()
    engine = EngineFake()
    pool = PluginRuntimes(engine)
    lease = pool.create("tenant:t:profile:p")
    assert engine.payload["HostConfig"]["ReadonlyRootfs"] is True
    assert engine.payload["HostConfig"]["NetworkMode"] == "private-network"
    assert engine.payload["User"] == "1000:1000"
    assert engine.payload["HostConfig"]["Mounts"][0]["VolumeOptions"]["Subpath"].startswith("plugin-runtimes/")
    assert engine.payload["HostConfig"]["Mounts"][0]["Source"] == "workspace-volume"
    assert engine.payload["HostConfig"]["Mounts"][1]["Source"] == "runtime-volume"
    assert engine.payload["HostConfig"]["Mounts"][1]["ReadOnly"] is True
    assert len(lease["token"]) == 64
    assert ("dsh-runtime-host", ["sandbox-gateway"]) in engine.connected
    restarted = PluginRuntimes(engine)
    assert restarted.status()["plugin_runtimes"] == 1
    restarted.dispose(lease["lease_id"])
    assert engine.cleaned == ["killed", "removed", "dsh-runtime-host", "sandbox-egress", "network"]


def test_recreate_after_manager_restart_reclaims_old_lease(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("MOVO_SANDBOX_RUNTIME_IMAGE", "dsh-test:1")
    monkeypatch.setenv("MOVO_SANDBOX_RUNTIME_VOLUME", "runtime-volume")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "workspace-volume")
    engine = EngineFake()
    first = PluginRuntimes(engine).create("tenant:t:profile:p")
    second = PluginRuntimes(engine).create("tenant:t:profile:p")
    assert second["lease_id"] != first["lease_id"]
    assert engine.cleaned == ["killed", "removed", "dsh-runtime-host", "sandbox-egress", "network"]


def test_plugin_runtime_mounts_only_its_user_space(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("MOVO_SANDBOX_RUNTIME_IMAGE", "dsh-test:1")
    monkeypatch.setenv("MOVO_SANDBOX_RUNTIME_VOLUME", "runtime-volume")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "workspace-volume")
    engine = EngineFake()
    key = "a" * 64
    PluginRuntimes(engine).create("tenant:t:profile:p", key)
    mounts = engine.payload["HostConfig"]["Mounts"]
    personal = next(mount for mount in mounts if mount["Target"] == "/job/home")
    assert personal["VolumeOptions"]["Subpath"] == f"personal/{key}"
    assert "MOVO_PERSONAL_SPACE_ROOT=/job/home" in engine.payload["Env"]
    assert "TMPDIR=/job/home/tmp" in engine.payload["Env"]
    assert (tmp_path / "workspaces" / "personal" / key / "tmp").is_dir()


def test_existing_plugin_runtime_storage_remains_on_legacy_volume(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("MOVO_SANDBOX_RUNTIME_IMAGE", "dsh-test:1")
    monkeypatch.setenv("MOVO_SANDBOX_RUNTIME_VOLUME", "runtime-volume")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "workspace-volume")
    import hashlib
    key = hashlib.sha256(b"tenant:t:profile:p").hexdigest()
    legacy = tmp_path / "runtime" / "sandbox-runtimes" / key
    legacy.mkdir(parents=True)
    (legacy / "saved.txt").write_text("keep")
    engine = EngineFake()
    PluginRuntimes(engine).create("tenant:t:profile:p")
    mount = engine.payload["HostConfig"]["Mounts"][0]
    assert mount["Source"] == "runtime-volume"
    assert mount["VolumeOptions"]["Subpath"] == f"sandbox-runtimes/{key}"
    assert (legacy / "saved.txt").read_text() == "keep"
