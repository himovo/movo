"""Preserve deployment identity and create cold volume backups before upgrades."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from common import compose, config, json_write, merge_env, read_env, run, sha256

RELEASE_KEYS = {"MOVO_IMAGE_PREFIX", "MOVO_VERSION", "MOVO_ALPINE_IMAGE", "MOVO_MONGO_IMAGE",
                "MOVO_REDIS_IMAGE", "MOVO_WEAVIATE_IMAGE", "MOVO_DOCUMENT_API_IMAGE",
                "MOVO_DOCUMENT_WORKER_IMAGE", "MOVO_SANDBOX_SCRIPT_IMAGE",
                "MOVO_SANDBOX_RUNTIME_IMAGE"}


def deployment_env(source, target):
    original = read_env(target / ".env")
    incoming = read_env(source / "release.env")
    updates = {key: value for key, value in incoming.items() if key in RELEASE_KEYS or key not in original}
    old_config = None
    if (target / "docker-compose.yml").is_file():
        previous_override = target / "offline-compose.json" if original.get("MOVO_OFFLINE_ONLY") == "1" else None
        old_config = config(target, override=previous_override)
        updates["COMPOSE_PROJECT_NAME"] = old_config["name"]
        # Preserve actual physical volume names, even if the old .env omitted a prefix.
        volumes = {name: {"name": volume["name"]} for name, volume in old_config.get("volumes", {}).items()}
    else:
        volumes = {}
    offline = json.loads((source / "offline-compose.json").read_text())["services"]
    updates.update({"MOVO_OFFLINE_ONLY": "1", "MOVO_OFFLINE_COMPOSE_FILE": "offline-compose.json",
                    "MOVO_ALPINE_IMAGE": offline["bootstrap"]["image"],
                    "MOVO_SANDBOX_SCRIPT_IMAGE": offline["sandbox-script"]["image"]})
    text = (target / ".env").read_text() if (target / ".env").exists() else (source / "release.env").read_text()
    return merge_env(text, updates), volumes, old_config


def check_identity(root, resolved):
    rows = run(["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={resolved['name']}",
                "--format", "{{.ID}}"], capture=True).splitlines()
    for container in rows:
        info = json.loads(run(["docker", "inspect", container], capture=True))[0]
        labels = info.get("Config", {}).get("Labels", {})
        directory = labels.get("com.docker.compose.project.working_dir")
        if not directory or Path(directory).resolve() != root.resolve():
            raise ValueError("Compose project already belongs to a different or unknown deployment directory")


def backup(target, resolved, alpine, backup_root):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = backup_root / timestamp
    destination.mkdir(parents=True, mode=0o700)
    config_root = destination / "deployment"
    config_root.mkdir()
    for name in ("movo", ".env", "docker-compose.yml", "release.json", "release.env",
                 "offline-compose.json", "deploy"):
        path = target / name
        if path.is_dir():
            shutil.copytree(path, config_root / name)
        elif path.is_file():
            shutil.copy2(path, config_root / name)
    previous_env = (config_root / ".env").read_text() if (config_root / ".env").exists() else ""
    (config_root / ".env").write_text(merge_env(previous_env, {"COMPOSE_PROJECT_NAME": resolved["name"]}))
    volumes = sorted({volume["name"] for volume in resolved.get("volumes", {}).values()})
    for volume in volumes:
        run(["docker", "volume", "inspect", volume], capture=True)
    # Bind mounts are not covered by named-volume archives; refuse before stopping.
    for service in resolved["services"].values():
        if any(mount.get("type") == "bind" and mount.get("source") != "/var/run/docker.sock" and not mount.get("read_only", False)
               for mount in service.get("volumes", []) if isinstance(mount, dict)):
            raise ValueError("Writable bind mounts require an explicit external backup; automatic upgrade refused")
    backup_bytes = sum(int(run(["docker", "run", "--rm", "--pull=never", "--network=none",
                               "--mount", f"type=volume,src={volume},dst=/source,readonly",
                               alpine, "du", "-sk", "/source"], capture=True).split()[0]) * 1024
                       for volume in volumes)
    if shutil.disk_usage(destination).free < backup_bytes * 1.2:
        raise ValueError("Insufficient backup disk space")
    run(compose() + ["stop"], cwd=target)
    try:
        for index, volume in enumerate(volumes):
            filename = f"volume-{index}.tar.gz"
            run(["docker", "run", "--rm", "--pull=never", "--network=none",
                 "--mount", f"type=volume,src={volume},dst=/source,readonly",
                 "--mount", f"type=bind,src={destination},dst=/backup",
                 alpine, "tar", "-C", "/source", "-czf", f"/backup/{filename}", "."])
        json_write(destination / "volumes.json", dict(zip(volumes, [f"volume-{i}.tar.gz" for i in range(len(volumes))])))
    except Exception:
        # No release files or database migrations have changed yet.
        run(compose() + ["start"], cwd=target)
        raise
    (destination / "RECOVERY.txt").write_text(
        "Cold backup created before migration. Keep services stopped before restoring volumes.\n"
        "Restore deployment files from deployment/ and every named volume listed in volumes.json.\n"
        "Never roll back image tags alone after database migrations. Old images were not deleted.\n")
    json_write(destination / "checksums.json", {p.relative_to(destination).as_posix(): sha256(p)
                                               for p in destination.rglob("*") if p.is_file()})
    return destination
