#!/usr/bin/env python3
"""Validate the pinned DSH artifact and license evidence for migration CI."""

from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path
from urllib.request import urlopen

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 used by the existing chat-api venv.
    import tomli as tomllib


CHAT_API_ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = CHAT_API_ROOT / "dsh" / "versions.lock"
LICENSE_PATH = CHAT_API_ROOT / "dsh" / "licenses" / "DEEPSEEK-HARNESS-MIT.txt"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_integrity(data: bytes, integrity: str) -> None:
    algorithm, encoded_digest = integrity.split("-", 1)
    if algorithm != "sha512":
        raise ValueError(f"unsupported integrity algorithm: {algorithm}")
    actual = base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")
    if actual != encoded_digest:
        raise ValueError("downloaded DSH artifact does not match the pinned SHA512 integrity")


def validate(*, download: bool, artifact_path: Path | None = None) -> None:
    lock = tomllib.loads(LOCK_PATH.read_text(encoding="utf-8"))
    release_version = lock["release_train"]["version"]
    artifacts = lock["artifact"]
    dsh = next(artifact for artifact in artifacts if artifact["name"] == "@deepseek-ai/dsh")

    if dsh["version"] != release_version:
        raise ValueError("DSH artifact version differs from the approved release train")
    if lock["upstream"]["allow_floating_versions"]:
        raise ValueError("floating DSH versions are forbidden")
    if _sha256(LICENSE_PATH) != lock["license_evidence"]["license_sha256"]:
        raise ValueError("vendored DSH MIT license hash differs from versions.lock")

    artifact: bytes | None = None
    if artifact_path is not None:
        artifact = artifact_path.read_bytes()
    elif download:
        with urlopen(dsh["tarball"], timeout=30) as response:
            artifact = response.read()

    if artifact is not None:
        _verify_integrity(artifact, dsh["integrity"])
        if hashlib.sha1(artifact).hexdigest() != dsh["shasum"]:  # noqa: S324 - npm metadata compatibility
            raise ValueError("downloaded DSH artifact does not match the pinned npm shasum")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--download",
        action="store_true",
        help="download the pinned npm tarball and verify both registry hashes",
    )
    parser.add_argument(
        "--artifact",
        type=Path,
        help="verify an already downloaded DSH npm tarball (preferred in CI)",
    )
    args = parser.parse_args()
    validate(download=args.download, artifact_path=args.artifact)
    print("DSH supply-chain evidence verified")


if __name__ == "__main__":
    main()
