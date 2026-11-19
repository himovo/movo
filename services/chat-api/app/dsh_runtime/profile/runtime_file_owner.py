"""Keep MOVO-staged Runtime files writable by the Runtime process."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def runtime_owner(storage_root: Path) -> tuple[int, int]:
    owner = storage_root.stat()
    return owner.st_uid, owner.st_gid


def ensure_owned_directory(path: Path, *, boundary: Path, owner: tuple[int, int]) -> None:
    if path != boundary and boundary not in path.parents:
        raise ValueError("Runtime path is outside its storage boundary")
    boundary.mkdir(parents=True, exist_ok=True)
    current = boundary
    for part in (None, *path.relative_to(boundary).parts):
        if part is not None:
            current = current / part
            current.mkdir(exist_ok=True)
        info = current.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("Runtime storage path is not a directory")
        if (info.st_uid, info.st_gid) != owner:
            os.chown(current, *owner)
        if info.st_mode & stat.S_IRWXU != stat.S_IRWXU:
            os.chmod(current, stat.S_IMODE(info.st_mode) | stat.S_IRWXU)
