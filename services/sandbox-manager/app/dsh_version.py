"""Read the DSH version from the running runtime host container."""

from __future__ import annotations

import io
import json
import tarfile

import httpx

from .docker_engine import DockerEngine


def running_dsh_version(engine: DockerEngine, container_id: str) -> str:
    if not container_id:
        return ""
    try:
        archive = engine.request(
            "GET", f"/containers/{container_id}/archive", params={"path": "/app/package.json"},
        ).content
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as files:
            manifest = next((item for item in files if item.isfile() and item.name.rsplit("/", 1)[-1] == "package.json"), None)
            if manifest is None:
                return ""
            source = files.extractfile(manifest)
            if source is None:
                return ""
            package = json.load(source)
        return str((package.get("dependencies") or {}).get("@deepseek-ai/dsh") or "")
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, httpx.HTTPError):
        return ""
