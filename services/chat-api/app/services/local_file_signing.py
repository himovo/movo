from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode


def sign_local_file_url(
    base_url: str,
    object_path: str,
    *,
    secret: str,
    ttl_seconds: int,
) -> str:
    expires_at = int(time.time()) + max(1, int(ttl_seconds))
    signature = _signature(object_path, expires_at, secret)
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'expires': expires_at, 'signature': signature})}"


def verify_local_file_signature(
    object_path: str,
    *,
    expires_at: int,
    signature: str,
    secret: str,
    now: int | None = None,
) -> bool:
    if not secret or not signature or expires_at < int(now if now is not None else time.time()):
        return False
    expected = _signature(object_path, expires_at, secret)
    return hmac.compare_digest(signature, expected)


def _signature(object_path: str, expires_at: int, secret: str) -> str:
    message = f"{int(expires_at)}\n{str(object_path or '').strip().lstrip('/')}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
