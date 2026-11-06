"""Create a versioned offline deployment without running target images."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tarfile
import tempfile

from common import config, inspect, json_write, run, sha256


def copy_payload(source, target):
    # Allowlist: never copy customer data, credentials, source trees, or caches.
    for name in ("movo", "docker-compose.yml", "release.json", "INSTALL.txt",
                 "prepare-offline.sh", "install-offline.sh"):
        shutil.copy2(source / name, target / name)
    shutil.copy2(source / "release.env", target / ".env")
    shutil.copy2(source / "release.env", target / "release.env")
    for name in ("cli", "offline"):
        shutil.copytree(source / "deploy" / name, target / "deploy" / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (target / "deploy/docker").mkdir()
    shutil.copy2(source / "deploy/docker/nginx.conf", target / "deploy/docker/nginx.conf")


def prepare(source, arch, output):
    release = json.loads((source / "release.json").read_text())
    resolved = config(source, env_file=source / "release.env")
    services = resolved["services"]
    pinned = {item["image"]: item["image"].rsplit(":", 1)[0] + "@" + item["digest"]
              for item in release.get("images", {}).values()}
    if any("build" in service for service in services.values()):
        raise ValueError("Offline releases cannot contain source builds")
    if output.exists():
        raise ValueError("Output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        bundle = Path(temporary) / "movo-enterprise"
        bundle.mkdir()
        copy_payload(source, bundle)
        images = []
        aliases = {}
        by_ref = {}
        for name, service in services.items():
            ref = service.get("image")
            ref = pinned.get(ref, ref)
            if not ref:
                raise ValueError(f"Missing image for service {name}")
            if ref not in by_ref:
                run(["docker", "pull", "--platform", f"linux/{arch}", ref])
                metadata = inspect(ref)
                if metadata.get("Architecture") != arch or metadata.get("Os") != "linux":
                    raise ValueError(f"Wrong image platform: {ref}")
                image_id = metadata["Id"]
                alias = "movo-offline/image:" + image_id.removeprefix("sha256:")
                run(["docker", "tag", image_id, alias])
                record = {"source": ref, "local": alias, "id": image_id, "architecture": arch}
                images.append(record)
                by_ref[ref] = record
            aliases[name] = {"image": by_ref[ref]["local"], "pull_policy": "never"}
        run(["docker", "image", "save", "-o", str(bundle / "images.tar"),
             *sorted({record["local"] for record in images})])
        for name in ("sandbox-manager", "dsh-runtime-host"):
            if name in aliases:
                aliases[name]["environment"] = {
                    "MOVO_SANDBOX_SCRIPT_IMAGE": aliases["sandbox-script"]["image"],
                    "MOVO_SANDBOX_RUNTIME_IMAGE": aliases["dsh-runtime-host"]["image"],
                }
        json_write(bundle / "offline-compose.json", {"services": aliases})
        files = {p.relative_to(bundle).as_posix(): sha256(p)
                 for p in bundle.rglob("*") if p.is_file()}
        json_write(bundle / "offline-manifest.json", {
            "schema": 1, "architecture": arch, "release": release["version"],
            "images": images, "files": files,
        })
        staged = Path(temporary) / "output.tar.gz"
        with tarfile.open(staged, "w:gz") as archive:
            archive.add(bundle, arcname="movo-enterprise", filter=lambda entry: entry)
        staged.replace(output)
    print(f"Offline bundle ready: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", required=True, choices=("amd64", "arm64"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(Path(__file__).resolve().parents[2], args.arch, args.output.resolve())
