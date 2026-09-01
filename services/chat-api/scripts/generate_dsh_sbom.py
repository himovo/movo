#!/usr/bin/env python3
"""Generate the checked-in CycloneDX component inventory for the DSH Host lock."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import yaml


CHAT_API_ROOT = Path(__file__).resolve().parents[1]
HOST_ROOT = CHAT_API_ROOT / "dsh" / "runtime-host"
LOCK_PATH = HOST_ROOT / "pnpm-lock.yaml"
OUTPUT_PATH = CHAT_API_ROOT / "dsh" / "sbom.cdx.json"


def package_identity(key: str) -> tuple[str, str]:
    identity = key.split("(", 1)[0]
    name, version = identity.rsplit("@", 1)
    if not name or not version:
        raise ValueError(f"invalid pnpm package identity: {key}")
    return name, version


def purl(name: str, version: str) -> str:
    if name.startswith("@"):
        namespace, package = name[1:].split("/", 1)
        return f"pkg:npm/{quote(namespace, safe='')}/{quote(package, safe='')}@{quote(version, safe='')}"
    return f"pkg:npm/{quote(name, safe='')}@{quote(version, safe='')}"


def sha512(integrity: str | None) -> list[dict[str, str]]:
    if not integrity or not integrity.startswith("sha512-"):
        return []
    digest = base64.b64decode(integrity.removeprefix("sha512-")).hex().upper()
    return [{"alg": "SHA-512", "content": digest}]


def generate() -> dict:
    lock = yaml.safe_load(LOCK_PATH.read_text(encoding="utf-8"))
    components = []
    seen: set[tuple[str, str]] = set()
    for key, package in sorted(lock.get("packages", {}).items()):
        name, version = package_identity(str(key))
        if (name, version) in seen:
            continue
        seen.add((name, version))
        component = {
            "type": "library",
            "bom-ref": purl(name, version),
            "name": name,
            "version": version,
            "purl": purl(name, version),
        }
        hashes = sha512((package or {}).get("resolution", {}).get("integrity"))
        if hashes:
            component["hashes"] = hashes
        components.append(component)
    host = json.loads((HOST_ROOT / "package.json").read_text(encoding="utf-8"))
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": "urn:uuid:5c8c8f40-2f59-5d35-a6bb-a5ca1d5a0001",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "component": {
                "type": "application",
                "name": host["name"],
                "version": host["version"],
            },
            "tools": {"components": [{"type": "application", "name": "MOVO DSH SBOM generator", "version": "1"}]},
        },
        "components": components,
    }


def main() -> None:
    OUTPUT_PATH.write_text(json.dumps(generate(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
