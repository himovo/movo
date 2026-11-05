"""Describe declared dependencies without copying Skill content or secrets."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


PACKAGE = re.compile(r"^[A-Za-z0-9._-]+(?:==[A-Za-z0-9._+!-]+)?$")
APT = re.compile(r"^[a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?(?:=[a-z0-9:~+._-]+)?$")


def description(skill_root: Path) -> dict:
    declared: dict[str, list[str]] = {"pip": [], "npm": [], "apt": []}
    requirements = skill_root / "requirements.txt"
    if requirements.is_file():
        declared["pip"] = [line for raw in requirements.read_text(encoding="utf-8").splitlines()
                           if (line := raw.split("#", 1)[0].strip()) and PACKAGE.fullmatch(line)][:200]
    apt = skill_root / "apt-packages.txt"
    if apt.is_file():
        declared["apt"] = [line for raw in apt.read_text(encoding="utf-8").splitlines()
                           if (line := raw.split("#", 1)[0].strip()) and APT.fullmatch(line)][:200]
    lock = skill_root / "package-lock.json"
    if lock.is_file():
        try:
            data = json.loads(lock.read_text(encoding="utf-8"))
            packages = data.get("packages") or {}
            declared["npm"] = [f"{name.rsplit('node_modules/', 1)[-1]}@{version}"
                               for name, details in packages.items()
                               if name and isinstance(details, dict)
                               if (version := str(details.get("version") or ""))
                               if PACKAGE.fullmatch(name.rsplit("node_modules/", 1)[-1]) and PACKAGE.fullmatch(version)][:500]
        except (ValueError, OSError):
            pass
    return declared


def record(root: Path, *, digest: str, record_id: str, source: str,
           base_image_id: str, skill_root: Path) -> None:
    collections = root / "collections"
    collections.mkdir(parents=True, exist_ok=True)
    row = {"digest": digest, "recordId": record_id, "source": source,
           "kind": "skill",
           "baseImageId": base_image_id,
           "createdAt": datetime.now(timezone.utc).isoformat(),
           "declared": description(skill_root), "files": cache_files(root)}
    (collections / f"{digest}-{record_id}.json").write_text(json.dumps(row, separators=(",", ":")), encoding="utf-8")


def cache_files(root: Path) -> list[str]:
    kinds = ("pip", "npm", "pnpm", "pnpm-cache", "apt-archives", "apt-lists", "plugin-archives")
    return sorted(path.relative_to(root).as_posix()
                  for kind in kinds for path in (root / kind).rglob("*")
                  if path.is_file() and not path.is_symlink() and path.name != "lock" and "partial" not in path.relative_to(root).parts)


def record_plugin(root: Path, *, name: str, version: str, archive_digest: str = "") -> dict:
    collections = root / "collections"
    collections.mkdir(parents=True, exist_ok=True)
    record_id = uuid4().hex
    row = {"digest": "", "recordId": record_id, "source": "plugin", "kind": "plugin",
           "name": name[:200], "version": version[:100],
           "archiveDigest": archive_digest,
           "createdAt": datetime.now(timezone.utc).isoformat(),
           "declared": {"npm": [f"{name}@{version}"]}, "files": cache_files(root)}
    (collections / f"plugin-{record_id}.json").write_text(json.dumps(row, separators=(",", ":")), encoding="utf-8")
    return {key: value for key, value in row.items() if key != "files"}


def list_records(root: Path) -> list[dict]:
    records = []
    for path in sorted((root / "collections").glob("*.json"), reverse=True)[:200]:
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            row.pop("files", None)
            records.append(row)
        except (ValueError, OSError):
            continue
    return records
