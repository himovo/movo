"""Read-only inventory of images used by isolated execution."""

from __future__ import annotations

import hashlib
import os

from .docker_engine import DockerEngine


def _inspect(engine: DockerEngine, name: str) -> dict:
    try:
        image = engine.request("GET", f"/images/{name}/json").json()
    except Exception:
        return {"image": name, "imageId": "", "createdAt": "", "available": False}
    return {"image": name, "imageId": str(image.get("Id") or ""),
            "createdAt": str(image.get("Created") or ""), "available": True}


def inventory(engine: DockerEngine, services: list[dict]) -> list[dict]:
    base_name = os.environ.get("MOVO_SANDBOX_SCRIPT_IMAGE", "").strip()
    plugin_name = os.environ.get("MOVO_SANDBOX_RUNTIME_IMAGE", "").strip()
    base = _inspect(engine, base_name) if base_name else {"image": "", "imageId": "", "createdAt": "", "available": False}
    plugin = _inspect(engine, plugin_name) if plugin_name else {"image": "", "imageId": "", "createdAt": "", "available": False}
    images = [
        {**base, "kind": "general", "scope": "all", "running": None, "baseImageId": "", "digest": ""},
        {**plugin, "kind": "plugin", "scope": "shared", "running": next((s["status"] == "running" for s in services if s["name"] == "dsh-runtime-host"), False), "baseImageId": "", "digest": ""},
    ]
    if not base["imageId"]:
        return images
    root = os.environ.get("MOVO_SANDBOX_WORKSPACE_ROOT", "/workspaces")
    from pathlib import Path
    cache = Path(root) / "skill-cache"
    for directory in sorted(cache.iterdir()) if cache.is_dir() else []:
        digest = directory.name
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            continue
        roots = [directory, *directory.iterdir()]
        if not any((root / "SKILL.md").is_file() and any((root / name).is_file() for name in ("requirements.txt", "package.json", "apt-packages.txt")) for root in roots if root.is_dir()):
            continue
        tag = hashlib.sha256(f"{base['imageId']}:{digest}".encode()).hexdigest()[:40]
        image = _inspect(engine, f"movo-skill-deps:{tag}")
        images.append({**image, "kind": "skill", "scope": "dedicated", "running": None,
                       "baseImageId": base["imageId"], "digest": digest})
    return images
