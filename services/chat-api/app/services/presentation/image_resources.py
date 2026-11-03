"""Resolve stored slide images without routing internal files through HTTP."""
from __future__ import annotations

from io import BytesIO
from urllib.parse import parse_qs, urlparse

from PIL import Image

from app.core.config import get_settings
from app.services.local_file_signing import verify_local_file_signature
from app.utils.oss_uploader import AliyunOSSUploader


def _is_stored_url(value: str) -> bool:
    configured = "/" + str(get_settings().FILE_PUBLIC_PATH_PREFIX or "/askai-api/api/files").strip("/")
    path = urlparse(value).path
    return any(path.startswith(prefix + "/") for prefix in (configured, "/api/files"))


def is_image_reference(value: str) -> bool:
    return str(value or "").lower().startswith(("https://", "http://")) or _is_stored_url(str(value or ""))


def read_stored_image(reference: str, *, user_id: str = "") -> bytes | None:
    """Return owned stored bytes; None means an external resource.

    A saved deck may outlive its download signature. An authenticated export
    can read its owner's files directly; other callers need a valid signature.
    """
    if not _is_stored_url(reference):
        return None
    uploader = AliyunOSSUploader()
    object_path = uploader.object_path_from_url(reference)
    if not object_path:
        return None
    if any(part in {".", ".."} for part in object_path.split("/")):
        raise ValueError("Invalid slide image storage path")
    if uploader.storage_backend == "local":
        if user_id:
            if not object_path.startswith(f"{user_id}/"):
                raise ValueError("Slide image does not belong to the exporting user")
        else:
            query = parse_qs(urlparse(reference).query)
            try:
                expires = int(query.get("expires", [""])[0])
            except ValueError:
                expires = 0
            if not verify_local_file_signature(
                object_path, expires_at=expires,
                signature=query.get("signature", [""])[0],
                secret=uploader._local_file_signing_secret(),
            ):
                raise ValueError("Slide image signature is missing or expired")
    data = uploader.read_bytes(object_path)
    with Image.open(BytesIO(data)) as image:
        image.verify()
    return data
