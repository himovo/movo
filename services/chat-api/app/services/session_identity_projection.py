"""Tenant-scoped author/avatar identity projection (session-sharing T5).

The single batch resolver shared by the participant listing and the session
detail message projection: every ``end_users`` read is scoped by the tenant's
``main_id`` (a cross-tenant id never resolves), every display name goes
through :func:`public_display_name`, and every avatar is either a safe direct
URL under the pinned grammar or the trusted signed URL of its object path -
the raw object path is never returned.

The module also owns the two per-message identity rules the detail contract
pins: ``seq`` (``0`` is RESERVED to mark a degraded unsequenced row, because
allocation starts at ``1``) and ``legacy_key`` (``message:{message_id}`` when
the stored row carries one, ``legacy:{role}:{seq}`` otherwise).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any
from urllib.parse import urlsplit

from bson import ObjectId

from app.core.tenant import add_main_scope
from app.services.member_identity import public_display_name
from app.utils.oss_uploader import ObjectStorageClient

SignUrl = Callable[[str], str]

# The pinned root-relative avatar grammar: exactly one leading slash that is
# not followed by another slash, and no control characters or backslashes.
ROOT_RELATIVE_AVATAR_RE = re.compile(r"^/(?!/)[^\x00-\x1f\\]*$")

_AUTHOR_FIELDS = {
    "name": 1,
    "display_name": 1,
    "nickname": 1,
    "login_name": 1,
    "username": 1,
    "avatar": 1,
    "avatar_object_path": 1,
}


def _has_control_or_backslash(value: str) -> bool:
    return any(ord(ch) < 0x20 or ord(ch) == 0x7F or ch == "\\" for ch in value)


def safe_avatar_url(
    avatar: Any,
    *,
    avatar_object_path: Any = "",
    sign_url: SignUrl | None = None,
) -> str | None:
    """Project one avatar to a safe URL, or ``None``.

    An object path WINS when present: only the trusted signed URL is
    returned, and a signing failure degrades to ``None`` - never the object
    path. A direct value is accepted only as an absolute ``http``/``https``
    URL with no credentials and no control characters, or as a root-relative
    path matching :data:`ROOT_RELATIVE_AVATAR_RE`; protocol-relative
    ``//...``, backslashes, control characters, ``data:``, ``javascript:``
    and every other scheme degrade to ``None``.
    """
    object_path = str(avatar_object_path or "").strip()
    if object_path:
        if sign_url is None:
            try:
                sign_url = ObjectStorageClient().sign_url
            except Exception:
                return None
        try:
            signed = str(sign_url(object_path) or "").strip()
        except Exception:
            return None
        return signed or None
    candidate = str(avatar or "").strip()
    if not candidate or _has_control_or_backslash(candidate):
        return None
    if candidate.startswith("/"):
        return candidate if ROOT_RELATIVE_AVATAR_RE.fullmatch(candidate) else None
    parsed = urlsplit(candidate)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    return candidate


def project_author(
    user_row: Mapping[str, Any] | None,
    *,
    user_id: str = "",
    sign_url: SignUrl | None = None,
) -> dict[str, Any] | None:
    """Project one ``end_users`` row to ``{user_id, display_name, avatar_url}``."""
    if user_row is None:
        return None
    key = str(user_row.get("_id") or user_id or "")
    return {
        "user_id": key,
        "display_name": public_display_name(user_row),
        "avatar_url": safe_avatar_url(
            user_row.get("avatar"),
            avatar_object_path=user_row.get("avatar_object_path"),
            sign_url=sign_url,
        ),
    }


async def resolve_author_projections(
    db: Any,
    *,
    tenant_id: str,
    user_ids: Iterable[Any],
    sign_url: SignUrl | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve a batch of user ids to author projections, tenant-scoped.

    Returns ``{user_id: author}`` only for ids that resolve INSIDE the
    tenant; an id with no ``end_users`` row - including a cross-tenant id -
    is simply absent, so callers project ``author: null`` instead of leaking
    another tenant's directory data.
    """
    requested = {str(value) for value in user_ids if str(value or "")}
    if not requested:
        return {}
    candidates = [
        ObjectId(value) if ObjectId.is_valid(value) else value
        for value in sorted(requested)
    ]
    rows = db.end_users.find(
        add_main_scope({"_id": {"$in": candidates}}, tenant_id),
        _AUTHOR_FIELDS,
    )
    projections: dict[str, dict[str, Any]] = {}
    async for row in rows:
        key = str(row.get("_id") or "")
        if key:
            projections[key] = project_author(row, sign_url=sign_url)
    return projections


def legacy_key(row: Mapping[str, Any], *, seq: int) -> str:
    """The stable per-row fallback identity: ``message:{id}`` or ``legacy:{role}:{seq}``."""
    message_id = str(row.get("message_id") or "").strip()
    if message_id:
        return f"message:{message_id}"
    return f"legacy:{str(row.get('role') or '')}:{seq}"


def message_identity(row: Mapping[str, Any]) -> tuple[int, str]:
    """Return ``(seq, legacy_key)`` for one stored message row.

    A row that reached the read path without an allocated ``seq`` (the
    mixed-session degrade path) reports the reserved ``0``; allocation
    starts at ``1``, so ``0`` can never collide with a real ordinal and
    ``legacy:{role}:0`` can never collide with ``legacy:{role}:{n}``.
    """
    raw_seq = row.get("seq")
    seq = int(raw_seq) if type(raw_seq) is int and raw_seq >= 0 else 0
    return seq, legacy_key(row, seq=seq)
