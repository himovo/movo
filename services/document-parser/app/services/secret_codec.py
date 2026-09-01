from __future__ import annotations

import base64
import hashlib
import hmac

from app.core.config import settings


def decrypt_admin_secret(value: str) -> str:
    if not value:
        return ""
    if not settings.admin_jwt_secret:
        return ""
    packed = base64.urlsafe_b64decode(value.encode("ascii"))
    nonce, mac, cipher = packed[:16], packed[16:48], packed[48:]
    expected = hmac.new(_secret_key(), nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        return ""
    stream = _keystream(nonce, len(cipher))
    payload = bytes(left ^ right for left, right in zip(cipher, stream))
    return payload.decode("utf-8")


def _secret_key() -> bytes:
    return hashlib.sha256(settings.admin_jwt_secret.encode("utf-8")).digest()


def _keystream(nonce: bytes, length: int) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < length:
        # Must match admin-api/app/repositories/model_repository.py exactly.
        counter_bytes = counter.to_bytes(4, "big")
        output.extend(hmac.new(_secret_key(), nonce + counter_bytes, hashlib.sha256).digest())
        counter += 1
    return bytes(output[:length])
