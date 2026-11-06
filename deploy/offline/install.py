"""Validate, import and install a complete offline release."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from common import compose, config, inspect, json_write, run, safe_path, sha256
from upgrade import backup, check_identity, deployment_env


def verify_bundle(source):
    manifest = json.loads((source / "offline-manifest.json").read_text())
    if manifest.get("schema") != 1 or manifest.get("architecture") not in ("amd64", "arm64"):
        raise ValueError("Unsupported offline manifest")
    for name, digest in manifest["files"].items():
        path = safe_path(source, name)
        if not path.is_file() or sha256(path) != digest:
            raise ValueError(f"Bundle checksum mismatch: {name}")
    required = {"images.tar", "offline-compose.json", "release.env", "release.json", "movo",
                "docker-compose.yml", "deploy/docker/nginx.conf"}
    if not required.issubset(manifest["files"]):
        raise ValueError("Offline manifest is incomplete")
    if json.loads((source / "release.json").read_text())["version"] != manifest["release"]:
        raise ValueError("Release metadata mismatch")
    return manifest


def install(source, target, backup_root):
    if source == target:
        raise ValueError("Use --target to select a separate new or existing deployment directory")
    if (target / ".env").exists() and not (target / "docker-compose.yml").is_file():
        raise ValueError("Existing environment has no Compose file; select the complete original deployment directory")
    manifest = verify_bundle(source)
    engine = json.loads(run(["docker", "info", "--format", "{{json .}}"], capture=True))
    arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(engine["Architecture"], engine["Architecture"])
    if engine.get("OSType") != "linux" or arch != manifest["architecture"]:
        raise ValueError("Offline image platform does not match the target Docker engine")
    if int(engine["ServerVersion"].split(".")[0]) < 26:
        raise ValueError("Docker Engine 26 or newer is required")
    required_bytes = (source / "images.tar").stat().st_size * 2
    docker_root = Path(engine.get("DockerRootDir", "/var/lib/docker"))
    if docker_root.exists() and shutil.disk_usage(docker_root).free < required_bytes:
        raise ValueError("Insufficient Docker disk space for importing the offline images")
    target.mkdir(parents=True, exist_ok=True)
    lock = target / ".offline-install-lock"
    lock.mkdir()  # A second installer must not race this upgrade.
    recovery = None
    try:
        run(["docker", "image", "load", "-i", str(source / "images.tar")])
        for image in manifest["images"]:
            actual = inspect(image["local"])
            if actual["Id"] != image["id"] or actual["Architecture"] != arch or actual["Os"] != "linux":
                raise ValueError(f"Imported image identity mismatch: {image['local']}")
        env, volumes, previous = deployment_env(source, target)
        override = json.loads((source / "offline-compose.json").read_text())
        override["volumes"] = volumes
        if previous:
            check_identity(target, previous)
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            shutil.copy2(source / "docker-compose.yml", stage / "docker-compose.yml")
            (stage / ".env").write_text(env)
            json_write(stage / "offline-compose.json", override)
            planned = config(stage, override=stage / "offline-compose.json")
            allowed = {image["local"] for image in manifest["images"]}
            if any(service.get("image") not in allowed for service in planned["services"].values()):
                raise ValueError("Offline configuration contains images not in the verified manifest")
            if not previous:
                check_identity(target, planned)
            if previous:
                for name in ("mongo", "redis", "weaviate"):
                    if inspect(previous["services"][name]["image"])["Id"] != inspect(planned["services"][name]["image"])["Id"]:
                        raise ValueError(f"Infrastructure image change requires a separate migration plan: {name}")
                alpine = override["services"]["bootstrap"]["image"]
                recovery = backup(target, previous, alpine, backup_root)
                print(f"Upgrade backup: {recovery}", flush=True)
            for name in ("movo", "docker-compose.yml", "release.json", "release.env"):
                shutil.copy2(source / name, target / name)
            for name in ("cli", "offline"):
                shutil.copytree(source / "deploy" / name, target / "deploy" / name, dirs_exist_ok=True)
            (target / "deploy/docker").mkdir(exist_ok=True)
            shutil.copy2(source / "deploy/docker/nginx.conf", target / "deploy/docker/nginx.conf")
            (target / ".env").write_text(env)
            (target / ".env").chmod(0o600)
            json_write(target / "offline-compose.json", override)
            package_volume = planned.get("volumes", {}).get("offline-packages", {}).get("name")
            if package_volume:
                run(["docker", "volume", "create", package_volume], capture=True)
                run(["docker", "run", "--rm", "--pull=never", "--network=none",
                     "--mount", f"type=volume,src={package_volume},dst=/packages",
                     override["services"]["bootstrap"]["image"], "touch", "/packages/offline-only"])
            if previous:
                run(compose() + ["--env-file", str(target / ".env"), "-f", str(target / "docker-compose.yml"),
                                 "-f", str(target / "offline-compose.json"), "up", "-d", "--pull", "never",
                                 "--wait", "mongo", "redis", "weaviate"], cwd=target)
                run(compose() + ["--env-file", str(target / ".env"), "-f", str(target / "docker-compose.yml"),
                                 "-f", str(target / "offline-compose.json"), "run", "--rm", "--no-deps",
                                 "--pull", "never", "chat-api", "python", "-m", "app.migrations"], cwd=target)
            run(["bash", "./movo", "--lang", "en", "up"], cwd=target)
            json_write(target / "offline-installed.json", {"release": manifest["release"], "architecture": arch,
                                                         "images": manifest["images"],
                                                         "backup": str(recovery) if recovery else None})
    except Exception:
        if recovery:
            try:
                run(compose() + ["stop"], cwd=target)
            except (OSError, subprocess.CalledProcessError):
                print("Could not stop services after failure; inspect the deployment before recovery.", flush=True)
            print(f"Upgrade did not complete. Recovery backup: {recovery}. Do not roll back images alone.", flush=True)
        raise
    finally:
        lock.rmdir()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()
    target = args.target.resolve()
    install(Path(__file__).resolve().parents[2], target,
            (args.backup_dir or target.parent / "movo-offline-backups").resolve())
