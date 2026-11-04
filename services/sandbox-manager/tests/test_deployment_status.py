from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app import deployment_status_app
from app.deployment_status import inventory


class Response:
    def __init__(self, value):
        self.value = value

    def json(self):
        return self.value


class EngineFake:
    def request(self, method, path, **kwargs):
        if path == "/containers/json":
            assert json.loads(kwargs["params"]["filters"])["label"] == ["com.docker.compose.project=movo"]
            return Response([{
                "Id": "container-id", "Image": "movo-chat-api:latest", "ImageID": "sha256:image",
                "Labels": {"com.docker.compose.service": "chat-api"},
            }])
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
    assert sandbox["status"] == "disabled"
    assert result["deployment"]["version"] == "latest"
    assert result["scriptImage"]["available"] is False


def test_observer_requires_shared_token(monkeypatch):
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_TOKEN", "server-token")
    with pytest.raises(HTTPException) as error:
        deployment_status_app.status("Bearer wrong-token")
    assert error.value.status_code == 401
