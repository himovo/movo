"""Site Profile service.

A *site profile* is a small piece of reusable knowledge about one
web application (e.g. the company's OA, the Xiaohongshu creator console).
Composite-task skills point to site profiles so every skill that drives
the same site shares the same auth guidance and navigation hints.

Storage: MongoDB ``site_profiles`` collection.

Per-document shape::

    {
        "_id": "<uuid>",
        "owner_user_id": "<uid>",        # "" for admin-curated globals
        "name": "公司 OA",
        "domain": "oa.acme.com",          # bare host, lowercase
        "entry_url": "https://oa.acme.com/",
        "auth_method": "sso_wechat_work", # free-form hint
        "hints": "- 登陆走企业微信...\n- 左侧菜单 ...",
        "visibility": "private",          # private | team | global
        "created_at": datetime,
        "updated_at": datetime,
    }

Visibility matches what ``user_skills`` already uses; queries that list
profiles for a user should union their own privates with team / global
docs.
"""
from __future__ import annotations

import datetime
import re
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.core.tenant import add_main_scope, resolve_main_id
from app.core.db import get_db


_VISIBILITY_ALLOWED = {"private", "team", "global"}


def _normalize_visibility(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in _VISIBILITY_ALLOWED else "private"


def _normalize_domain(value: Any) -> str:
    """Reduce a URL or a host to the lowercase bare host.

    Accepts:
        "https://oa.acme.com/home?x=1"  → "oa.acme.com"
        "oa.acme.com/"                   → "oa.acme.com"
        "OA.ACME.COM"                    → "oa.acme.com"
    """
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "http://" + raw
    try:
        parsed = urlparse(raw)
        host = (parsed.hostname or "").strip().lower()
    except Exception:
        host = ""
    if not host:
        # Fallback: strip trailing path manually.
        host = re.split(r"[/?#]", str(value or "").strip().lower(), 1)[0]
    return host


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return {}
    created = doc.get("created_at")
    updated = doc.get("updated_at")
    return {
        "id": str(doc.get("_id") or ""),
        "owner_user_id": str(doc.get("owner_user_id") or ""),
        "main_id": resolve_main_id(doc.get("main_id")),
        "name": str(doc.get("name") or ""),
        "domain": str(doc.get("domain") or ""),
        "entry_url": str(doc.get("entry_url") or ""),
        "auth_method": str(doc.get("auth_method") or ""),
        "hints": str(doc.get("hints") or ""),
        "visibility": _normalize_visibility(doc.get("visibility")),
        "created_at": created.isoformat() if isinstance(created, datetime.datetime) else None,
        "updated_at": updated.isoformat() if isinstance(updated, datetime.datetime) else None,
    }


class SiteProfileService:
    async def list_for_user(self, user_id: str, main_id: str = "default") -> List[Dict[str, Any]]:
        """Return profiles visible to ``user_id``: own privates + team + global."""
        db = get_db()
        uid = str(user_id or "").strip()
        query: Dict[str, Any] = add_main_scope({
            "$or": [
                {"owner_user_id": uid},
                {"visibility": {"$in": ["team", "global"]}},
            ]
        }, main_id)
        cursor = db.site_profiles.find(query).sort("updated_at", -1)
        out: List[Dict[str, Any]] = []
        async for doc in cursor:
            out.append(_serialize(doc))
        return out

    async def get(self, user_id: str, profile_id: str, main_id: str = "default") -> Optional[Dict[str, Any]]:
        """Read one profile if it belongs to the user or is team / global."""
        db = get_db()
        uid = str(user_id or "").strip()
        doc = await db.site_profiles.find_one(
            add_main_scope({
                "_id": str(profile_id),
                "$or": [
                    {"owner_user_id": uid},
                    {"visibility": {"$in": ["team", "global"]}},
                ],
            }, main_id)
        )
        return _serialize(doc) if doc else None

    async def get_by_id_unscoped(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """Internal use: load a profile by id without the visibility filter.

        Intended for the planner side where we already trust the skill that
        referenced this profile. Not exposed through the REST layer.
        """
        db = get_db()
        doc = await db.site_profiles.find_one({"_id": str(profile_id)})
        return _serialize(doc) if doc else None

    async def create(
        self,
        user_id: str,
        *,
        name: str,
        domain: str = "",
        entry_url: str = "",
        auth_method: str = "",
        hints: str = "",
        visibility: str = "private",
        main_id: str = "default",
    ) -> Dict[str, Any]:
        db = get_db()
        uid = str(user_id or "").strip()
        trimmed_name = str(name or "").strip()
        if not trimmed_name:
            raise ValueError("site profile requires a name")
        doc: Dict[str, Any] = {
            "_id": uuid.uuid4().hex,
            "owner_user_id": uid,
            "main_id": resolve_main_id(main_id),
            "name": trimmed_name[:160],
            "domain": _normalize_domain(domain or entry_url),
            "entry_url": str(entry_url or "").strip(),
            "auth_method": str(auth_method or "").strip()[:120],
            "hints": str(hints or "").strip(),
            "visibility": _normalize_visibility(visibility),
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db.site_profiles.insert_one(doc)
        return _serialize(doc)

    async def update(
        self,
        user_id: str,
        profile_id: str,
        updates: Dict[str, Any],
        main_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        db = get_db()
        uid = str(user_id or "").strip()
        current = await db.site_profiles.find_one(add_main_scope({"_id": str(profile_id), "owner_user_id": uid}, main_id))
        if not current:
            return None

        patch: Dict[str, Any] = {}
        if "name" in updates:
            trimmed = str(updates.get("name") or "").strip()
            if trimmed:
                patch["name"] = trimmed[:160]
        if "domain" in updates or "entry_url" in updates:
            domain = _normalize_domain(
                updates.get("domain") if "domain" in updates else updates.get("entry_url")
            )
            patch["domain"] = domain
        if "entry_url" in updates:
            patch["entry_url"] = str(updates.get("entry_url") or "").strip()
        if "auth_method" in updates:
            patch["auth_method"] = str(updates.get("auth_method") or "").strip()[:120]
        if "hints" in updates:
            patch["hints"] = str(updates.get("hints") or "").strip()
        if "visibility" in updates:
            patch["visibility"] = _normalize_visibility(updates.get("visibility"))

        if not patch:
            return _serialize(current)
        patch["updated_at"] = _now()
        await db.site_profiles.update_one(add_main_scope({"_id": str(profile_id)}, main_id), {"$set": patch})
        doc = await db.site_profiles.find_one(add_main_scope({"_id": str(profile_id)}, main_id))
        return _serialize(doc) if doc else None

    async def delete(self, user_id: str, profile_id: str, main_id: str = "default") -> bool:
        db = get_db()
        uid = str(user_id or "").strip()
        result = await db.site_profiles.delete_one(add_main_scope({"_id": str(profile_id), "owner_user_id": uid}, main_id))
        return bool(result.deleted_count)


site_profile_service = SiteProfileService()
