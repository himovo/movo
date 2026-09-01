from __future__ import annotations

from typing import BinaryIO, Protocol


class StorageAdapter(Protocol):
    def put_file(self, source: BinaryIO, storage_key: str) -> None:
        ...

    def open_file(self, storage_key: str) -> BinaryIO:
        ...

    def exists(self, storage_key: str) -> bool:
        ...
