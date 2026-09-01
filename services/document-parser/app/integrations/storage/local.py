from __future__ import annotations

from pathlib import Path
from typing import BinaryIO


class LocalStorageAdapter:
    def __init__(self, root_dir: str) -> None:
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, storage_key: str) -> Path:
        normalized = storage_key.strip().lstrip("/").replace("\\", "/")
        path = (self.root_dir / normalized).resolve()
        if self.root_dir not in path.parents and path != self.root_dir:
            raise ValueError("Invalid storage key")
        return path

    def put_file(self, source: BinaryIO, storage_key: str) -> None:
        target = self._path(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as output:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)

    def open_file(self, storage_key: str) -> BinaryIO:
        path = self._path(storage_key)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(storage_key)
        return path.open("rb")

    def exists(self, storage_key: str) -> bool:
        path = self._path(storage_key)
        return path.exists() and path.is_file()
