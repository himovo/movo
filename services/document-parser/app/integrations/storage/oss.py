from __future__ import annotations

from typing import BinaryIO

from app.core.config import settings


class OSSStorageAdapter:
    def __init__(self) -> None:
        import oss2  # type: ignore

        auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
        self.bucket = oss2.Bucket(auth, settings.oss_endpoint, settings.oss_bucket)

    def put_file(self, source: BinaryIO, storage_key: str) -> None:
        self.bucket.put_object(storage_key, source)

    def open_file(self, storage_key: str) -> BinaryIO:
        return self.bucket.get_object(storage_key)

    def exists(self, storage_key: str) -> bool:
        return bool(self.bucket.object_exists(storage_key))
