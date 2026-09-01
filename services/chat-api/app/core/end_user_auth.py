from __future__ import annotations

import hashlib
import hmac
import secrets


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    normalized_salt = salt or secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        normalized_salt.encode("utf-8"),
        120000,
    ).hex()
    return password_hash, normalized_salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    computed_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(computed_hash, str(password_hash or ""))


def build_session_token(secret: str, token_id: str) -> str:
    digest = hmac.new(
        str(secret or "").encode("utf-8"),
        str(token_id or "").encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"u.{token_id}.{digest}"


def parse_and_verify_session_token(secret: str, token: str) -> str | None:
    raw = str(token or "").strip()
    parts = raw.split(".")
    if len(parts) != 3 or parts[0] != "u":
        return None
    token_id, signature = parts[1], parts[2]
    expected = hmac.new(
        str(secret or "").encode("utf-8"),
        token_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    return token_id
