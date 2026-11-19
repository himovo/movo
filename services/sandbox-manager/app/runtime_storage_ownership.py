"""Repair Runtime directories created by a different service before boot."""

from __future__ import annotations

import os
import stat
from pathlib import Path


RUNTIME_UID = 1000
RUNTIME_GID = 1000


def _own_directory(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("Runtime storage path is not a directory")
    if (info.st_uid, info.st_gid) != (RUNTIME_UID, RUNTIME_GID):
        os.chown(path, RUNTIME_UID, RUNTIME_GID)
    if info.st_mode & stat.S_IRWXU != stat.S_IRWXU:
        os.chmod(path, stat.S_IMODE(info.st_mode) | stat.S_IRWXU)


def repair_runtime_storage(domain: Path) -> None:
    """Repair only the Runtime root and MOVO-staged attachment directories."""
    if not domain.exists() and not domain.is_symlink():
        return
    _own_directory(domain)
    for name in ("dsh-home", "host-profile-home"):
        child = domain / name
        if child.exists() or child.is_symlink():
            _own_directory(child)
    attachments = domain / "dsh-home" / "attachments"
    if not attachments.exists() and not attachments.is_symlink():
        return
    _own_directory(attachments)
    for root, directories, _ in os.walk(attachments, followlinks=False):
        _own_directory(Path(root))
        for directory in directories:
            candidate = Path(root) / directory
            if candidate.is_symlink():
                raise ValueError("Runtime attachment path is a symbolic link")
