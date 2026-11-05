from pathlib import Path
from concurrent.futures import Future

import pytest

from app.skill_environments import DependencyPreparationError, SkillEnvironments


class ImageEngine:
    def __init__(self):
        self.images = {"base:latest": "sha256:base"}
        self.created = None
        self.wait_timeout = None

    def image_id(self, name):
        return self.images.get(name)

    def find_compose_service(self, project, service):
        return "proxy"

    def create_internal_network(self, name):
        return "network"

    def connect_network(self, network, container, aliases):
        pass

    def create(self, name, payload):
        self.created = payload
        return "container"

    def start(self, container):
        pass

    def wait(self, container, timeout):
        self.wait_timeout = timeout
        return 0

    def commit(self, container, repository, tag):
        self.images[f"{repository}:{tag}"] = "sha256:prepared"
        return "sha256:prepared"

    def remove(self, container):
        pass

    def disconnect_network(self, network, container):
        pass

    def remove_network(self, network):
        pass


class RetryingEngine(ImageEngine):
    def __init__(self, failure: str, failures: int = 1):
        super().__init__()
        self.failure = failure
        self.failures = failures
        self.environments = []
        self.removed = []

    def create(self, name, payload):
        self.environments.append(list(payload["Env"]))
        return name

    def wait(self, container, timeout):
        return 1 if len(self.environments) <= self.failures else 0

    def logs(self, container):
        raw = self.failure.encode()
        return bytes([2, 0, 0, 0]) + len(raw).to_bytes(4, "big") + raw

    def remove(self, container):
        self.removed.append(container)


def test_dependency_image_is_keyed_by_bundle_and_base_image(tmp_path: Path, monkeypatch):
    digest = "a" * 64
    root = tmp_path / "skill-cache" / digest / "sample"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("sample")
    (root / "requirements.txt").write_text("humanize==4.13.0")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "base:latest")
    engine = ImageEngine()
    environments = SkillEnvironments(engine)
    assert environments.ready_image(digest) == environments.ready_image(digest)
    assert environments.status(digest) == "ready"
    assert engine.created["HostConfig"]["Mounts"][0]["ReadOnly"] is True
    assert engine.created["HostConfig"]["Mounts"][0]["VolumeOptions"]["Subpath"] == f"skill-cache/{digest}/sample"
    assert engine.created["HostConfig"]["NetworkMode"] == "network"
    assert engine.created["HostConfig"]["CapDrop"] == ["ALL"]
    assert engine.created["HostConfig"]["CapAdd"] == ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SETUID", "SETGID"]
    assert "MOVO_SKILL_DEPENDENCY_STEP_TIMEOUT=480" in engine.created["Env"]
    assert 1790 <= engine.wait_timeout <= 1800


def test_offline_build_does_not_attach_egress_proxy(tmp_path: Path, monkeypatch):
    digest = "f" * 64
    root = tmp_path / "skill-cache" / digest
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("sample")
    (root / "requirements.txt").write_text("humanize==4.13.0")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "base:latest")

    class OfflineEngine(ImageEngine):
        def find_compose_service(self, project, service):
            raise AssertionError("Offline build must not access the proxy")

    engine = OfflineEngine()
    environments = SkillEnvironments(engine)
    environments.packages.set_offline(True)
    assert environments.ready_image(digest).startswith("movo-skill-deps:")
    assert "MOVO_OFFLINE_ONLY=1" in engine.created["Env"]
    assert all(mount["Target"] != "/offline/collections" for mount in engine.created["HostConfig"]["Mounts"])


def test_dependency_build_timeouts_are_configurable_and_bounded(monkeypatch):
    monkeypatch.setenv("MOVO_SKILL_DEPENDENCY_STEP_TIMEOUT", "720")
    monkeypatch.setenv("MOVO_SKILL_DEPENDENCY_BUILD_TIMEOUT", "2400")
    assert SkillEnvironments._step_timeout() == 720
    assert SkillEnvironments._build_timeout() == 2400
    monkeypatch.setenv("MOVO_SKILL_DEPENDENCY_STEP_TIMEOUT", "99999")
    monkeypatch.setenv("MOVO_SKILL_DEPENDENCY_BUILD_TIMEOUT", "invalid")
    assert SkillEnvironments._step_timeout() == 1200
    assert SkillEnvironments._build_timeout() == 1800


def test_bundle_without_declarations_uses_base_image(tmp_path: Path, monkeypatch):
    digest = "b" * 64
    root = tmp_path / "skill-cache" / digest
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("sample")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "base:latest")
    engine = ImageEngine()
    environments = SkillEnvironments(engine)
    assert environments.ready_image(digest) == "base:latest"
    assert environments.status(digest) == "not_required"
    assert engine.created is None


def test_status_restarts_preparation_after_manager_restart(tmp_path: Path, monkeypatch):
    digest = "d" * 64
    root = tmp_path / "skill-cache" / digest
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("sample")
    (root / "requirements.txt").write_text("humanize==4.13.0")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "base:latest")
    environments = SkillEnvironments(ImageEngine())
    assert environments.status(digest) in {"preparing", "ready"}
    assert environments.ready_image(digest).startswith("movo-skill-deps:")


def test_pending_build_returns_bounded_retry_error(tmp_path: Path, monkeypatch):
    digest = "e" * 64
    root = tmp_path / "skill-cache" / digest
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("sample")
    (root / "requirements.txt").write_text("humanize==4.13.0")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "base:latest")
    environments = SkillEnvironments(ImageEngine())
    image = environments._image_name(digest)
    environments.pending[image] = Future()
    with pytest.raises(DependencyPreparationError, match="still preparing"):
        environments.ready_image(digest, timeout=0.01)


def test_build_error_is_reported_without_exposing_install_logs(tmp_path: Path, monkeypatch):
    digest = "c" * 64
    root = tmp_path / "skill-cache" / digest
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("sample")
    (root / "package.json").write_text("{}")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "base:latest")

    class FailingEngine(ImageEngine):
        def __init__(self):
            super().__init__()
            self.creates = 0

        def create(self, name, payload):
            self.creates += 1
            return super().create(name, payload)

        def wait(self, container, timeout):
            return 1

        def logs(self, container):
            output = b"secret-token"
            return bytes([2, 0, 0, 0]) + len(output).to_bytes(4, "big") + output

    engine = FailingEngine()
    environments = SkillEnvironments(engine)
    with pytest.raises(DependencyPreparationError, match="check sandbox manager logs") as error:
        environments.ready_image(digest)
    assert "secret-token" not in str(error.value)
    assert environments.status(digest) == "failed"
    with pytest.raises(DependencyPreparationError):
        environments.ready_image(digest)
    assert engine.creates == 1
    assert environments.start(digest, retry_failed=True) in {"preparing", "failed"}
    with pytest.raises(DependencyPreparationError):
        environments.ready_image(digest)
    assert engine.creates == 2
    records = environments.records.list(digest)
    assert len(records) == 2
    assert all(record["status"] == "failed" for record in records)
    assert all("secret-token" in environments.records.get(digest, item["id"])["log"] for item in records)


def test_network_failure_retries_in_fresh_container(tmp_path: Path, monkeypatch):
    digest = "f" * 64
    root = tmp_path / "skill-cache" / digest
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("sample")
    (root / "requirements.txt").write_text("humanize==4.13.0")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "base:latest")
    monkeypatch.setenv("MOVO_DEPENDENCY_MIRROR", "cn")
    engine = RetryingEngine("pip timed out")
    image = SkillEnvironments(engine).ready_image(digest)
    assert image.startswith("movo-skill-deps:")
    assert len(engine.environments) == 2
    assert "MOVO_DEPENDENCY_SOURCE=cn" in engine.environments[0]
    assert "MOVO_DEPENDENCY_SOURCE=global" in engine.environments[1]
    assert len(engine.removed) == 2


def test_network_failure_after_both_sources_gets_one_bounded_extra_attempt(tmp_path: Path, monkeypatch):
    digest = "1" * 64
    root = tmp_path / "skill-cache" / digest
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("sample")
    (root / "requirements.txt").write_text("humanize==4.13.0")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "base:latest")
    monkeypatch.setenv("MOVO_DEPENDENCY_MIRROR", "cn")
    monkeypatch.setenv("MOVO_SKILL_DEPENDENCY_RETRIES", "1")
    engine = RetryingEngine("pip timed out", failures=2)
    assert SkillEnvironments(engine).ready_image(digest).startswith("movo-skill-deps:")
    assert len(engine.environments) == 3
    assert [next(value for value in env if value.startswith("MOVO_DEPENDENCY_SOURCE=")) for env in engine.environments] == [
        "MOVO_DEPENDENCY_SOURCE=cn", "MOVO_DEPENDENCY_SOURCE=global", "MOVO_DEPENDENCY_SOURCE=cn",
    ]


def test_non_network_failure_does_not_retry(tmp_path: Path, monkeypatch):
    digest = "2" * 64
    root = tmp_path / "skill-cache" / digest
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("sample")
    (root / "requirements.txt").write_text("invalid-package")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "base:latest")
    engine = RetryingEngine("No matching distribution found", failures=3)
    with pytest.raises(DependencyPreparationError):
        SkillEnvironments(engine).ready_image(digest)
    assert len(engine.environments) == 1


def test_package_error_does_not_switch_source(tmp_path: Path, monkeypatch):
    digest = "0" * 64
    root = tmp_path / "skill-cache" / digest
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("sample")
    (root / "requirements.txt").write_text("missing==99")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "base:latest")
    engine = RetryingEngine("No matching distribution found")
    with pytest.raises(DependencyPreparationError):
        SkillEnvironments(engine).ready_image(digest)
    assert len(engine.environments) == 1
