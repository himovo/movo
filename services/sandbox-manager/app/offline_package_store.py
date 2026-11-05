"""Persistent, portable package-manager caches for isolated builds."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import tempfile
import zipfile
from pathlib import Path

from .storage_paths import manager_state_root


KINDS = ("pip", "npm", "pnpm", "pnpm-cache", "apt-archives", "apt-lists", "plugin-archives", "collections")
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_ENTRY_BYTES = MAX_ARCHIVE_BYTES


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class OfflinePackageStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(os.environ.get("MOVO_OFFLINE_PACKAGE_ROOT", str(manager_state_root() / "offline-packages")))
        for kind in KINDS:
            (self.root / kind).mkdir(parents=True, exist_ok=True)
            (self.root / kind).chmod(0o777)
        for kind in ("apt-archives", "apt-lists"):
            (self.root / kind / "partial").mkdir(exist_ok=True)
        self._write_npm_config()

    @property
    def offline(self) -> bool:
        return (self.root / "offline-only").is_file()

    def set_offline(self, enabled: bool) -> dict:
        marker = self.root / "offline-only"
        if enabled:
            marker.touch()
        else:
            marker.unlink(missing_ok=True)
        self._write_npm_config()
        return self.inventory()

    def _write_npm_config(self) -> None:
        config = self.root / ".npmrc"
        content = ("store-dir=/offline-packages/pnpm\ncache-dir=/offline-packages/pnpm-cache\n"
                   f"prefer-offline=true\noffline={'true' if self.offline else 'false'}\n")
        if not config.is_file() or config.read_text(encoding="utf-8") != content:
            temporary = self.root / f".npmrc-{os.getpid()}"
            temporary.write_text(content, encoding="utf-8")
            temporary.chmod(0o644)
            os.replace(temporary, config)

    def inventory(self) -> dict:
        from .offline_collections import list_records
        counts = {}
        sizes = {}
        for kind in KINDS:
            files = [path for path in (self.root / kind).rglob("*") if path.is_file() and not path.is_symlink()]
            counts[kind] = len(files)
            sizes[kind] = sum(path.stat().st_size for path in files)
        return {"offlineOnly": self.offline, "counts": counts, "sizes": sizes,
                "platform": platform.machine(), "os": platform.system().lower(),
                "collections": list_records(self.root)}

    def export_to(self, output: Path, record_ids: set[str] | None = None) -> None:
        manifest = {"version": 1, "platform": platform.machine(),
                    "os": platform.system().lower(), "files": []}
        selected_files = None
        if record_ids is not None:
            selected_files = set()
            for record_id in record_ids:
                matches = list((self.root / "collections").glob(f"*-{record_id}.json"))
                if len(matches) != 1:
                    raise ValueError("Preparation record was not found")
                selected_files.update(json.loads(matches[0].read_text(encoding="utf-8")).get("files") or [])
                selected_files.add(matches[0].relative_to(self.root).as_posix())
            missing = [relative for relative in selected_files if not (self.root / relative).is_file()]
            if missing:
                raise ValueError(f"Preparation record package files are missing: {len(missing)}")
        image_name = os.environ.get("MOVO_SANDBOX_SCRIPT_IMAGE", "")
        runtime_name = os.environ.get("MOVO_SANDBOX_RUNTIME_IMAGE", "")
        if image_name or runtime_name:
            from .docker_engine import DockerEngine
            engine = DockerEngine()
            if image_name:
                manifest["baseImageId"] = engine.image_id(image_name)
                if not manifest["baseImageId"]:
                    raise ValueError("Sandbox base image is unavailable")
            if runtime_name:
                manifest["runtimeImageId"] = engine.image_id(runtime_name)
                if not manifest["runtimeImageId"]:
                    raise ValueError("Plugin runtime image is unavailable")
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
            for kind in KINDS:
                for path in sorted((self.root / kind).rglob("*")):
                    if not path.is_file() or path.is_symlink():
                        continue
                    if path.name == "lock" or "partial" in path.relative_to(self.root).parts:
                        continue
                    relative = path.relative_to(self.root).as_posix()
                    if selected_files is not None and relative not in selected_files:
                        continue
                    manifest["files"].append({"path": relative, "size": path.stat().st_size,
                                              "sha256": _sha256_file(path)})
                    archive.write(path, relative)
            archive.writestr("manifest.json", json.dumps(manifest, separators=(",", ":")))
        if output.stat().st_size > MAX_ARCHIVE_BYTES:
            output.unlink(missing_ok=True)
            raise ValueError("Offline package archive exceeds the size limit")

    def import_archive(self, source: Path) -> dict:
        if not source.is_file() or not 0 < source.stat().st_size <= MAX_ARCHIVE_BYTES:
            raise ValueError("Invalid offline package archive size")
        with zipfile.ZipFile(source) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("version") != 1 or manifest.get("platform") != platform.machine() or manifest.get("os") != platform.system().lower():
                raise ValueError("Offline package archive is incompatible with this host")
            entries = manifest.get("files")
            if not isinstance(entries, list) or len(entries) > 100000:
                raise ValueError("Invalid offline package manifest")
            declared = {item.get("path") for item in entries if isinstance(item, dict)}
            actual = set(archive.namelist()) - {"manifest.json"}
            if declared != actual or len(declared) != len(entries):
                raise ValueError("Offline package archive contents do not match the manifest")
            kinds = {str(path).split("/", 1)[0] for path in declared}
            skill_packages = bool(kinds.intersection(("pip", "npm", "apt-archives", "apt-lists")))
            plugin_packages = bool(kinds.intersection(("pnpm", "pnpm-cache", "plugin-archives")))
            if skill_packages and os.environ.get("MOVO_SANDBOX_SCRIPT_IMAGE") and not manifest.get("baseImageId"):
                raise ValueError("Sandbox base image identity is missing from the archive")
            if plugin_packages and os.environ.get("MOVO_SANDBOX_RUNTIME_IMAGE") and not manifest.get("runtimeImageId"):
                raise ValueError("Plugin runtime identity is missing from the archive")
            if (manifest.get("baseImageId") and skill_packages) or (manifest.get("runtimeImageId") and plugin_packages):
                from .docker_engine import DockerEngine
                engine = DockerEngine()
                if manifest.get("baseImageId") and skill_packages and manifest["baseImageId"] != engine.image_id(os.environ.get("MOVO_SANDBOX_SCRIPT_IMAGE", "")):
                    raise ValueError("Skill packages require the same sandbox base image")
                if manifest.get("runtimeImageId") and plugin_packages and manifest["runtimeImageId"] != engine.image_id(os.environ.get("MOVO_SANDBOX_RUNTIME_IMAGE", "")):
                    raise ValueError("Plugin packages require the same runtime image")
            if sum(int(item.get("size", 0)) for item in entries) > MAX_ARCHIVE_BYTES * 2:
                raise ValueError("Offline package archive expands beyond the size limit")
            with tempfile.TemporaryDirectory(dir=self.root) as staging:
                for item in entries:
                    relative = str(item["path"])
                    parts = Path(relative).parts
                    if len(parts) < 2 or parts[0] not in KINDS or any(part in ("", ".", "..") for part in parts):
                        raise ValueError("Invalid offline package path")
                    info = archive.getinfo(relative)
                    if info.file_size > MAX_ENTRY_BYTES or info.file_size != item.get("size"):
                        raise ValueError("Invalid offline package entry size")
                    target = Path(staging) / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256()
                    with archive.open(relative) as source_file, target.open("wb") as target_file:
                        while chunk := source_file.read(1024 * 1024):
                            digest.update(chunk)
                            target_file.write(chunk)
                    if digest.hexdigest() != item.get("sha256"):
                        raise ValueError("Offline package checksum mismatch")
                for item in entries:
                    relative = str(item["path"])
                    source = Path(staging) / relative
                    target = self.root / relative
                    if not target.parent.resolve().is_relative_to(self.root.resolve()):
                        raise ValueError("Offline package path leaves the package store")
                    if target.is_symlink():
                        raise ValueError("Offline package target is a symbolic link")
                    if target.exists() and _sha256_file(target) != item["sha256"]:
                        raise ValueError("Offline package path conflicts with an existing package")
                for item in entries:
                    relative = str(item["path"])
                    source = Path(staging) / relative
                    target = self.root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    directory = target.parent
                    while directory != self.root:
                        directory.chmod(0o777)
                        directory = directory.parent
                    if not target.exists():
                        os.replace(source, target)
                        if Path(relative).parts[0] in ("npm", "pnpm", "pnpm-cache"):
                            target.chmod(0o666)
        return self.inventory()
