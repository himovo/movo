"""Restore a cold offline upgrade backup only with explicit confirmation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from common import compose, config, inspect, run, safe_path, sha256
from upgrade import check_identity


def restore(target, backup, alpine):
    checksums = json.loads((backup / "checksums.json").read_text())
    for name, digest in checksums.items():
        if sha256(safe_path(backup, name)) != digest:
            raise ValueError(f"Backup checksum mismatch: {name}")
    volumes = json.loads((backup / "volumes.json").read_text())
    original = config(backup / "deployment", override=(backup / "deployment/offline-compose.json")
                      if (backup / "deployment/offline-compose.json").exists() else None)
    current = config(target, override=target / "offline-compose.json")
    if original["name"] != current["name"]:
        raise ValueError("Backup belongs to a different Compose project")
    check_identity(target, current)
    inspect(alpine)
    for volume, filename in volumes.items():
        if filename not in checksums:
            raise ValueError("Backup volume archive is not covered by checksums")
        safe_path(backup, filename)
        run(["docker", "volume", "inspect", volume], capture=True)
    for service in original["services"].values():
        inspect(service["image"])
    run(compose() + ["stop"], cwd=target)
    for volume, filename in volumes.items():
        run(["docker", "run", "--rm", "--pull=never", "--network=none",
             "--mount", f"type=volume,src={volume},dst=/restore",
             "--mount", f"type=bind,src={backup},dst=/backup,readonly", alpine,
             "sh", "-ec", 'find /restore -mindepth 1 -maxdepth 1 -exec rm -rf {} +; tar -xzf "$1" -C /restore',
             "restore", f"/backup/{filename}"])
    for name in ("deploy", "movo", ".env", "docker-compose.yml", "release.json", "release.env", "offline-compose.json"):
        source = backup / "deployment" / name
        destination = target / name
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        elif source.is_file():
            shutil.copy2(source, destination)
        elif destination.is_file():
            destination.unlink()
    # Start only already existing containers; never pull or run forward migrations.
    args = compose() + ["-f", str(target / "docker-compose.yml")]
    if (target / "offline-compose.json").exists():
        args += ["-f", str(target / "offline-compose.json")]
    run(args + ["up", "-d", "--pull", "never"], cwd=target)
    print("Backup restored. Verify service health before resuming user traffic.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--alpine-image", required=True)
    parser.add_argument("--confirm-restore", action="store_true", required=True)
    args = parser.parse_args()
    restore(args.target.resolve(), args.backup.resolve(), args.alpine_image)
