from unittest.mock import Mock

import httpx
import pytest

from app import skill_image_commit as saving
from app.skill_build_records import SkillBuildRecords


def docker_error(status=404, message="lease does not exist: not found"):
    response = httpx.Response(status, json={"message": message}, request=httpx.Request("POST", "http://docker/commit"))
    return httpx.HTTPStatusError("Docker error", request=response.request, response=response)


@pytest.fixture
def clock(monkeypatch):
    now = [0]
    monkeypatch.setattr(saving.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(saving.time, "sleep", lambda delay: now.__setitem__(0, now[0] + delay))
    return now


def engine_with(*outcomes):
    return Mock(commit=Mock(side_effect=outcomes), image_id=Mock(return_value=None))


def save(engine, deadline=900):
    return saving.save_skill_image(engine, "prepared-container", "movo-skill-deps:test", deadline=deadline, report=Mock())


def test_lease_retry_reuses_prepared_container_and_bounds_timeout(clock):
    engine = engine_with(docker_error(), "sha256:ready")
    assert save(engine, deadline=100) == "sha256:ready"
    assert [call.args for call in engine.commit.call_args_list] == [("prepared-container", "movo-skill-deps", "test")] * 2
    assert [call.kwargs["timeout"] for call in engine.commit.call_args_list] == [100, 98]
    engine.inspect.assert_called_once_with("prepared-container")
    engine.create.assert_not_called()
    engine.remove.assert_not_called()


def test_lease_failure_is_bounded(clock):
    engine = engine_with(*[docker_error() for _ in range(3)])
    with pytest.raises(saving.SkillImageCommitError, match="after 3 attempt"):
        save(engine)
    assert engine.commit.call_count == 3
    assert clock[0] == 6


@pytest.mark.parametrize("status,message", [(404, "No such container"), (403, "permission denied"),
                                            (500, "no space left on device")])
def test_permanent_errors_are_not_retried(clock, status, message):
    engine = engine_with(docker_error(status, message))
    with pytest.raises(saving.SkillImageCommitError, match=message):
        save(engine)
    assert engine.commit.call_count == 1
    engine.inspect.assert_not_called()


def test_published_image_is_reused_after_lease_cleanup_error(clock):
    engine = engine_with(docker_error())
    engine.image_id.return_value = "sha256:published"
    assert save(engine) == "sha256:published"
    assert engine.commit.call_count == 1
    engine.inspect.assert_not_called()


def test_missing_prepared_container_stops_retry(clock):
    engine = engine_with(docker_error())
    engine.inspect.side_effect = docker_error(404, "No such container")
    with pytest.raises(saving.SkillImageCommitError, match="recovery check failed.*No such container"):
        save(engine)
    assert engine.commit.call_count == 1


@pytest.mark.parametrize("deadline,calls", [(0, 0), (1, 1)])
def test_retry_respects_total_preparation_deadline(clock, deadline, calls):
    engine = engine_with(docker_error())
    with pytest.raises(saving.SkillImageCommitError):
        save(engine, deadline)
    assert engine.commit.call_count == calls
    assert clock[0] == 0


def test_progress_notes_keep_install_result_and_redact_errors(tmp_path):
    store = SkillBuildRecords(tmp_path)
    digest = "a" * 64
    record = store.create(digest, "base")
    store.append_attempt(digest, record, source="custom", exit_code=0, output="Successfully installed")
    store.append_note(digest, record, "Image save retry: token=private-value")
    current = store.get(digest, record)
    assert current["status"] == "preparing"
    assert current["attempts"] == [{"source": "custom", "exitCode": 0}]
    assert "Successfully installed" in current["log"]
    assert "private-value" not in current["log"]


@pytest.mark.parametrize("lease_failure", [True, False])
def test_build_records_image_stage_and_cleans_up_after_recovery(tmp_path, monkeypatch, clock, lease_failure):
    from test_skill_environments import ImageEngine
    from app.skill_environments import SkillEnvironments

    digest = "b" * 64
    root = tmp_path / "skill-cache" / digest
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("sample")
    (root / "requirements.txt").write_text("example")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "base:latest")
    monkeypatch.setenv("MOVO_PIP_INDEX_URL", "https://packages.example/simple")

    class BuildEngine(ImageEngine):
        creates = commits = removes = 0

        def create(self, name, payload):
            self.creates += 1
            return super().create(name, payload)

        def logs(self, container):
            data = b"Successfully installed dependencies"
            return bytes([1, 0, 0, 0]) + len(data).to_bytes(4, "big") + data

        def inspect(self, container):
            assert self.removes == 0
            return {"Id": container}

        def commit(self, container, repository, tag, *, timeout=300):
            self.commits += 1
            assert self.removes == 0
            if self.commits == 1:
                raise docker_error() if lease_failure else docker_error(500, "no space left on device")
            return super().commit(container, repository, tag, timeout=timeout)

        def remove(self, container):
            self.removes += 1

    engine = BuildEngine()
    environments = SkillEnvironments(engine)
    image = environments._image_name(digest)
    if lease_failure:
        assert environments._build(digest, image) == image
    else:
        with pytest.raises(saving.SkillImageCommitError, match="no space left"):
            environments._build(digest, image)
    record = environments.records.get(digest, environments.records.list(digest)[0]["id"])
    assert record["attempts"] == [{"source": "custom", "exitCode": 0}]
    assert engine.creates == engine.removes == 1
    if lease_failure:
        assert engine.commits == 2
        assert record["status"] == "ready"
        assert "retrying the same prepared container" in record["log"]
    else:
        assert engine.commits == 1
        assert record["status"] == "failed"
        assert "Dependencies installed; image save failed: Docker HTTP 500: no space left" in record["log"]
