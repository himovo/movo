from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException, status

from app.core.config import settings


class StoredFile:
    def __init__(self, *, storage_type: str, storage_key: str, local_path: str = "", bucket: str = "") -> None:
        self.storage_type = storage_type
        self.storage_key = storage_key
        self.local_path = local_path
        self.bucket = bucket


class StorageService:
    storage_type = "local"

    def put_file(self, source: BinaryIO, storage_key: str) -> StoredFile:
        raise NotImplementedError

    def open_file(self, storage_key: str) -> BinaryIO:
        raise NotImplementedError

    def delete_file(self, storage_key: str) -> None:
        raise NotImplementedError

    def exists(self, storage_key: str) -> bool:
        raise NotImplementedError


class LocalStorageAdapter(StorageService):
    storage_type = "local"

    def __init__(self, root_dir: str) -> None:
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, storage_key: str) -> Path:
        normalized = storage_key.strip().lstrip("/").replace("\\", "/")
        path = (self.root_dir / normalized).resolve()
        if self.root_dir not in path.parents and path != self.root_dir:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件路径无效")
        return path

    def put_file(self, source: BinaryIO, storage_key: str) -> StoredFile:
        target = self._path(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as output:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        return StoredFile(storage_type=self.storage_type, storage_key=storage_key, local_path=str(target))

    def open_file(self, storage_key: str) -> BinaryIO:
        path = self._path(storage_key)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
        return path.open("rb")

    def delete_file(self, storage_key: str) -> None:
        path = self._path(storage_key)
        if path.exists() and path.is_file():
            path.unlink()

    def exists(self, storage_key: str) -> bool:
        path = self._path(storage_key)
        return path.exists() and path.is_file()


class OSSStorageAdapter(StorageService):
    storage_type = "oss"

    def __init__(self) -> None:
        if not settings.knowledge_oss_endpoint or not settings.knowledge_oss_bucket:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="OSS 存储配置不完整")
        try:
            import oss2  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="OSS 依赖未安装，请安装 oss2") from exc
        auth = oss2.Auth(settings.knowledge_oss_access_key_id, settings.knowledge_oss_access_key_secret)
        self.bucket_name = settings.knowledge_oss_bucket
        self.bucket = oss2.Bucket(auth, settings.knowledge_oss_endpoint, self.bucket_name)

    def put_file(self, source: BinaryIO, storage_key: str) -> StoredFile:
        self.bucket.put_object(storage_key, source)
        return StoredFile(
            storage_type=self.storage_type,
            storage_key=storage_key,
            bucket=self.bucket_name,
        )

    def open_file(self, storage_key: str) -> BinaryIO:
        try:
            result = self.bucket.get_object(storage_key)
        except Exception as exc:  # pragma: no cover - network path
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在") from exc
        return result

    def delete_file(self, storage_key: str) -> None:
        self.bucket.delete_object(storage_key)

    def exists(self, storage_key: str) -> bool:
        return bool(self.bucket.object_exists(storage_key))


def get_storage_service(storage_type: str | None = None) -> StorageService:
    storage_type = str(storage_type or settings.knowledge_storage_type or "local").strip().lower()
    if storage_type == "oss":
        return OSSStorageAdapter()
    return LocalStorageAdapter(os.path.abspath(settings.knowledge_local_storage_dir))
