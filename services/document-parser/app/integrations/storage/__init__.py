from __future__ import annotations

from app.core.config import settings
from app.integrations.storage.local import LocalStorageAdapter
from app.integrations.storage.oss import OSSStorageAdapter


def get_storage_adapter(storage_type: str):
    if storage_type == "oss":
        return OSSStorageAdapter()
    return LocalStorageAdapter(settings.resolved_local_storage_dir)
