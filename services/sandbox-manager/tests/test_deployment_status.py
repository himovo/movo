from __future__ import annotations

import json
import hashlib
import io
import tarfile

import pytest
from fastapi import HTTPException

from app import deployment_status_app
from app.deployment_status import inventory
from app.dsh_version import running_dsh_version
from app.sandbox_image_inventory import inventory as sandbox_images


class Response:
    def __init__(self, value):
        self.value = value

    def json(self):
        return self.value


def test_running_dsh_version_reads_container_manifest():
    manifest = b'{"dependencies":{"@deepseek-ai/dsh":"0.2.1-alpha.1"}}'
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        item = tarfile.TarInfo("package.json")
        item.size = len(manifest)
        archive.addfile(item, io.BytesIO(manifest))

    class Engine:
        def request(self, method, path, **kwargs):
            assert (method, path, kwargs["params"]["path"]) == (
                "GET", "/containers/runtime-host/archive", "/app/package.json",
            )
            return type("Archive", (), {"content": output.getvalue()})()

    assert running_dsh_version(Engine(), "runtime-host") == "0.2.1-alpha.1"
    assert running_dsh_version(Engine(), "") == ""


class EngineFake:
    def request(self, method, path, **kwargs):
        if path == "/containers/json":
            assert json.loads(kwargs["params"]["filters"])["label"] == ["com.docker.compose.project=movo"]
            return Response([{
                "Id": "container-id", "Image": "movo-chat-api:latest", "ImageID": "sha256:image",
                "Labels": {"com.docker.compose.service": "chat-api"},
            }])
        if path == "/images/sha256:image/json":
            return Response({"Config": {"Labels": {"org.opencontainers.image.revision": "d4ccf30a6bc26737ee6a9a6092067b5f0345d288"}}})
        raise RuntimeError("Image unavailable")

    def inspect(self, container_id):
        assert container_id == "container-id"
        return {
            "Id": container_id, "Image": "sha256:image", "Config": {"Image": "movo-chat-api:latest"},
            "State": {"Status": "running", "Health": {"Status": "healthy"}, "StartedAt": "2026-11-04T00:00:00Z"},
            "RestartCount": 2,
        }


def test_inventory_reports_actual_image_and_optional_services(tmp_path, monkeypatch):
    record = tmp_path / "deployment.json"
    record.write_text('{"upgradedAt":"2026-11-04T00:00:00Z","version":"latest"}', encoding="utf-8")
    images = tmp_path / "image-ids.txt"
    images.write_text("chat-api sha256:previous\n", encoding="utf-8")
    monkeypatch.setenv("MOVO_DEPLOYMENT_RECORD", str(record))
    monkeypatch.setenv("MOVO_DEPLOYMENT_IMAGES", str(images))
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "movo-sandbox-script:latest")
    result = inventory(EngineFake())
    chat = next(item for item in result["services"] if item["name"] == "chat-api")
    sandbox = next(item for item in result["services"] if item["name"] == "sandbox-manager")
    assert (chat["image"], chat["imageId"], chat["restarts"]) == ("movo-chat-api:latest", "sha256:image", 2)
    assert chat["versionMismatch"] is True
    assert chat["revision"] == "d4ccf30a6bc26737ee6a9a6092067b5f0345d288"
    assert result["deployment"]["commit"] == chat["revision"]
    assert sandbox["status"] == "disabled"
    assert result["deployment"]["version"] == "latest"
    assert result["scriptImage"]["available"] is False
    assert [image["kind"] for image in result["sandboxImages"]] == ["general", "plugin"]


@pytest.mark.parametrize("contents", ["null", "[]"])
def test_inventory_survives_non_object_deployment_record(tmp_path, monkeypatch, contents):
    record = tmp_path / "deployment.json"
    record.write_text(contents, encoding="utf-8")
    monkeypatch.setenv("MOVO_DEPLOYMENT_RECORD", str(record))
    monkeypatch.setenv("MOVO_SANDBOX_COMPOSE_PROJECT", "movo")

    result = inventory(EngineFake())

    assert "version" not in result["deployment"]
    chat = next(item for item in result["services"] if item["name"] == "chat-api")
    assert chat["status"] == "running"
    assert result["deployment"]["commit"] == chat["revision"]


def test_observer_requires_shared_token(monkeypatch):
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_TOKEN", "server-token")
    with pytest.raises(HTTPException) as error:
        deployment_status_app.status("Bearer wrong-token")
    assert error.value.status_code == 401


def test_sandbox_images_include_a_prepared_skill_image(tmp_path, monkeypatch):
    digest = "a" * 64
    root = tmp_path / "skill-cache" / digest
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("name: sample")
    (root / "requirements.txt").write_text("example==1")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "base:latest")
    monkeypatch.setenv("MOVO_SANDBOX_RUNTIME_IMAGE", "runtime:latest")
    tag = hashlib.sha256(f"sha256:base:{digest}".encode()).hexdigest()[:40]

    class Images:
        def request(self, _method, path):
            names = {
                "/images/base:latest/json": "sha256:base",
                "/images/runtime:latest/json": "sha256:runtime",
                f"/images/movo-skill-deps:{tag}/json": "sha256:prepared",
            }
            return Response({"Id": names[path]})

    rows = sandbox_images(Images(), [{"name": "dsh-runtime-host", "status": "running"}])
    assert [row["kind"] for row in rows] == ["general", "plugin", "skill"]
    assert rows[1]["running"] is True
    assert rows[2]["imageId"] == "sha256:prepared"
    assert rows[2]["digest"] == digest
