from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid

from app.core.config import settings


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    normalized_salt = salt or secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        normalized_salt.encode("utf-8"),
        120_000,
    ).hex()
    return password_hash, normalized_salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    computed_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(computed_hash, password_hash)


def create_access_token(subject: dict[str, object], expires_in_seconds: int | None = None) -> tuple[str, int, str]:
    expires_at = int(time.time()) + int(expires_in_seconds or settings.access_token_ttl_seconds)
    session_id = str(uuid.uuid4())
    payload = {
        "sub": {
            **subject,
            "session_id": session_id,
        },
        "exp": expires_at,
    }
    encoded_payload = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    signature = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
    return f"{encoded_payload}.{encoded_signature}", expires_at, session_id


def decode_access_token(token: str) -> dict[str, object]:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Invalid token format") from exc

    expected_signature = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    actual_signature = base64.urlsafe_b64decode(_with_padding(encoded_signature))
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise ValueError("Invalid token signature")

    payload_raw = base64.urlsafe_b64decode(_with_padding(encoded_payload)).decode("utf-8")
    payload = json.loads(payload_raw)
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Token expired")
    return payload


def _with_padding(value: str) -> str:
    return value + "=" * (-len(value) % 4)
