"""Validated Docker image transfer for isolated execution images."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import tarfile
import zipfile
from pathlib import Path
from urllib.parse import quote
from urllib.parse import urlsplit

from .docker_engine import DockerEngine
from .sandbox_image_inventory import inventory


MAX_IMAGE_BYTES = 8 * 1024 * 1024 * 1024
SKILL_TAG = re.compile(r"^movo-skill-deps:[0-9a-f]{40}$")


def _allowed_name(engine: DockerEngine, name: str) -> bool:
    general = os.environ.get("MOVO_SANDBOX_SCRIPT_IMAGE", "")
    plugin = os.environ.get("MOVO_SANDBOX_RUNTIME_IMAGE", "")
    return name in (general, plugin) or bool(SKILL_TAG.fullmatch(name))


def _skill_metadata(engine: DockerEngine, name: str) -> dict:
    if not SKILL_TAG.fullmatch(name):
        return {}
    items = inventory(engine, [])
    item = next((value for value in items if value["image"] == name and value["kind"] == "skill"), None)
    if item is None:
        raise ValueError("Skill image has no matching package in the local inventory")
    return {"digest": item["digest"], "baseImageId": item["baseImageId"]}


def export_image(engine: DockerEngine, name: str, output: Path) -> None:
    if not _allowed_name(engine, name) or not engine.image_id(name):
        raise ValueError("Image is unavailable for export")
    config = engine.request("GET", f"/images/{quote(name, safe='')}/json").json().get("Config") or {}
    for entry in config.get("Env") or []:
        key, _, value = entry.partition("=")
        name_upper = key.upper()
        if value and (any(fragment in name_upper for fragment in ("TOKEN", "PASSWORD", "SECRET", "API_KEY", "AUTH"))
                      or (key in ("PIP_INDEX_URL", "npm_config_registry", "MOVO_APT_MIRROR")
                          and (urlsplit(value).username or urlsplit(value).query))):
            raise ValueError("Image configuration contains credentials and cannot be exported")
    metadata = {"version": 1, "image": name, "imageId": engine.image_id(name),
                "architecture": platform.machine(), **_skill_metadata(engine, name)}
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("metadata.json", json.dumps(metadata, separators=(",", ":")))
        with archive.open("image.tar", "w", force_zip64=True) as target:
            with engine.client.stream("GET", f"/images/{quote(name, safe='')}/get", timeout=3600) as response:
                response.raise_for_status()
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_IMAGE_BYTES:
                        raise ValueError("Image archive exceeds the size limit")
                    target.write(chunk)


def import_image(engine: DockerEngine, source: Path) -> dict:
    if not source.is_file() or source.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError("Invalid image archive size")
    with zipfile.ZipFile(source) as archive:
        if set(archive.namelist()) != {"metadata.json", "image.tar"}:
            raise ValueError("Invalid image archive layout")
        metadata = json.loads(archive.read("metadata.json"))
        name = str(metadata.get("image") or "")
        if metadata.get("version") != 1 or not _allowed_name(engine, name):
            raise ValueError("Image is not an isolated sandbox image")
        if metadata.get("architecture") != platform.machine():
            raise ValueError("Image architecture does not match this host")
        if SKILL_TAG.fullmatch(name):
            base_id = engine.image_id(os.environ.get("MOVO_SANDBOX_SCRIPT_IMAGE", ""))
            digest = str(metadata.get("digest") or "")
            if not base_id or metadata.get("baseImageId") != base_id or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("Skill image base is incompatible with this deployment")
            expected = hashlib.sha256(f"{base_id}:{digest}".encode()).hexdigest()[:40]
            if name != f"movo-skill-deps:{expected}":
                raise ValueError("Skill image does not match its package digest")
        if archive.getinfo("image.tar").file_size > MAX_IMAGE_BYTES:
            raise ValueError("Image archive exceeds the size limit")
        with archive.open("image.tar") as image:
            with tarfile.open(fileobj=image, mode="r|") as tar:
                expected_config = None
                configs: dict[str, dict] = {}
                for member in tar:
                    if member.name == "manifest.json":
                        manifest_file = tar.extractfile(member)
                        if manifest_file is None or member.size > 1024 * 1024:
                            raise ValueError("Invalid Docker image manifest")
                        manifest = json.load(manifest_file)
                        tags = [tag for item in manifest for tag in item.get("RepoTags", [])]
                        if tags != [name]:
                            raise ValueError("Docker image tags do not match the archive")
                        expected_config = str(manifest[0].get("Config") or "")
                    elif member.name.endswith(".json") and member.size <= 2 * 1024 * 1024:
                        config_file = tar.extractfile(member)
                        if config_file is not None:
                            try:
                                configs[member.name] = json.load(config_file)
                            except ValueError:
                                pass
                if not expected_config:
                    raise ValueError("Docker image manifest is missing")
                config = configs.get(expected_config)
                if not config:
                    raise ValueError("Docker image configuration is missing")
                architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine(), platform.machine())
                if config.get("architecture") != architecture or config.get("os") != "linux":
                    raise ValueError("Docker image platform is incompatible with this host")
        with archive.open("image.tar") as image:
            response = engine.client.post("/images/load", params={"quiet": 1}, content=image,
                                          headers={"Content-Type": "application/x-tar"}, timeout=3600)
            response.raise_for_status()
            for line in response.content.splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict) and event.get("error"):
                    raise ValueError(f"Docker rejected the image: {event['error']}")
        image_id = engine.image_id(name)
        if image_id != metadata.get("imageId"):
            raise ValueError("Imported image ID does not match the archive")
        return {"image": name, "imageId": image_id}
