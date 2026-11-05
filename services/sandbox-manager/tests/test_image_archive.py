import io
import json
import os
import platform
import tarfile
from pathlib import Path

import httpx
import pytest

from app.image_archive import export_image, import_image


def _docker_tar(name: str) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        manifest = json.dumps([{"Config": "config.json", "RepoTags": [name], "Layers": []}]).encode()
        info = tarfile.TarInfo("manifest.json")
        info.size = len(manifest)
        archive.addfile(info, io.BytesIO(manifest))
        architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine(), platform.machine())
        config = json.dumps({"architecture": architecture, "os": "linux"}).encode()
        info = tarfile.TarInfo("config.json")
        info.size = len(config)
        archive.addfile(info, io.BytesIO(config))
    return output.getvalue()


class Engine:
    def __init__(self, tar: bytes) -> None:
        self.tar = tar
        self.loaded = False
        self.client = httpx.Client(transport=httpx.MockTransport(self._request), base_url="http://docker/v1.45")

    def image_id(self, name: str) -> str | None:
        return "sha256:example" if not self.loaded or name else None

    def request(self, method: str, path: str):
        return httpx.Response(200, json={"Config": {"Env": []}})

    def _request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/get"):
            return httpx.Response(200, content=self.tar)
        if request.url.path.endswith("/images/load"):
            assert request.read() == self.tar
            self.loaded = True
            return httpx.Response(200, json={"status": "Loaded"})
        return httpx.Response(404)


def test_image_round_trip(monkeypatch, tmp_path: Path) -> None:
    name = "movo-sandbox-script:test"
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", name)
    engine = Engine(_docker_tar(name))
    archive = tmp_path / "image.zip"
    export_image(engine, name, archive)
    assert import_image(engine, archive) == {"image": name, "imageId": "sha256:example"}


def test_image_import_rejects_extra_tag(monkeypatch, tmp_path: Path) -> None:
    name = "movo-sandbox-script:test"
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", name)
    engine = Engine(_docker_tar("other:tag"))
    archive = tmp_path / "image.zip"
    export_image(engine, name, archive)
    with pytest.raises(ValueError, match="tags"):
        import_image(engine, archive)


def test_image_export_rejects_embedded_credentials(monkeypatch, tmp_path: Path) -> None:
    name = "movo-sandbox-script:test"
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", name)
    engine = Engine(_docker_tar(name))
    engine.request = lambda *_args: httpx.Response(200, json={"Config": {"Env": ["PLUGIN_API_KEY=secret"]}})
    with pytest.raises(ValueError, match="credentials"):
        export_image(engine, name, tmp_path / "image.zip")
