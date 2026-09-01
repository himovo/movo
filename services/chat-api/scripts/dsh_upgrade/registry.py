from __future__ import annotations

import json
import subprocess

from .models import PackageMetadata


REGISTRY = "https://registry.npmjs.org"


class NpmRegistry:
    def __init__(self, npm: str = "npm", registry: str = REGISTRY) -> None:
        self.npm = npm
        self.registry = registry.rstrip("/")

    def resolve(self, name: str, selector: str) -> PackageMetadata:
        completed = subprocess.run(
            [
                self.npm, "view", f"{name}@{selector}",
                "version", "dependencies", "dist", "--json",
                f"--registry={self.registry}",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if completed.returncode != 0:
            raise ValueError(
                f"npm package {name!r} has no version matching {selector!r}: {completed.stderr.strip()}"
            )
        manifest = json.loads(completed.stdout)
        version = manifest.get("version")
        if not isinstance(version, str):
            raise ValueError(f"npm returned no exact version for {name}@{selector}")
        return PackageMetadata(
            name=name,
            version=str(version),
            dependencies={str(key): str(value) for key, value in (manifest.get("dependencies") or {}).items()},
            dist=dict(manifest.get("dist") or {}),
        )
