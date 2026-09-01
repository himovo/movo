from __future__ import annotations

from urllib.parse import unquote

from app.utils.object_storage import ObjectStorageClient


async def download_bytes(object_path: str, *, timeout_s: float = 30.0) -> bytes:
    path = str(object_path or "").strip()
    if not path:
        return b""
    uploader = ObjectStorageClient()
    return uploader.read_bytes(unquote(path))


async def download_text(
    object_path: str,
    *,
    encoding: str = "utf-8",
    timeout_s: float = 30.0,
) -> str:
    data = await download_bytes(object_path, timeout_s=timeout_s)
    if not data:
        return ""
    try:
        return data.decode(encoding, errors="ignore")
    except Exception:
        return ""
