"""Bounded, atomic writes into a user's mounted personal file space."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO


def require_personal_parent(personal_root: Path, parent: Path) -> None:
    try:
        parent.resolve().relative_to(personal_root.resolve())
    except ValueError as exc:
        raise PermissionError("Personal file destination escapes its owner") from exc


def atomic_personal_copy(personal_root: Path, target: Path, source: BinaryIO) -> None:
    require_personal_parent(personal_root, target.parent)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".movo-write-", delete=False) as output:
            temporary = Path(output.name)
            shutil.copyfileobj(source, output)
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
