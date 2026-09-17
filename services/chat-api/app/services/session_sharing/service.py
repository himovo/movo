from __future__ import annotations

import datetime
import hashlib
import secrets

DEFAULT_SHARE_EXPIRY_DAYS = 30


class SessionShareError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def create_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    value = str(token or "").strip()
    if not value:
        raise SessionShareError("session_share_token_required", "A session share token is required")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def issue_share(
    session_doc: dict[str, object],
    *,
    now: datetime.datetime,
    expires_in_days: int = DEFAULT_SHARE_EXPIRY_DAYS,
) -> dict[str, object]:
    token = create_token()
    fields: dict[str, str | datetime.datetime | None] = {
        "share_token_hash": hash_token(token),
        "share_expires_at": now + datetime.timedelta(days=expires_in_days),
        "share_revoked_at": None,
    }
    return {"token": token, "fields": fields}


def revoke_share(*, now: datetime.datetime) -> dict[str, str | datetime.datetime | None]:
    return {"share_token_hash": None, "share_revoked_at": now}


def is_active(session_doc: dict[str, object], token: str, now: datetime.datetime) -> bool:
    if hash_token(token) != session_doc.get("share_token_hash"):
        return False
    expires_at = session_doc.get("share_expires_at")
    if not isinstance(expires_at, datetime.datetime):
        return False
    if expires_at.tzinfo is None:
        # pymongo returns naive UTC datetimes by default; treat them as UTC.
        expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
    if expires_at <= now:
        return False
    return session_doc.get("share_revoked_at") is None


def build_link(origin: str, token: str) -> str:
    return f"{origin}/?session-share={token}"
