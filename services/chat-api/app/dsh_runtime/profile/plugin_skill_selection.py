"""Opaque user selection references for DSH plugin-contributed Skills."""

from __future__ import annotations

import re
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Any

from .plugins import MongoPluginCatalog


PREFIX = "dsh_plugin_skill:"
_ID = re.compile(r"^dsh_plugin_skill:([0-9a-f]{24}):([A-Za-z0-9_-]+)$")


def _decode_name(encoded: str) -> str:
    try:
        name = urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Invalid plugin Skill selection") from exc
    if not name or len(name) > 256 or any(ord(char) < 32 for char in name):
        raise ValueError("Invalid plugin Skill selection")
    return name


def selection_id(plugin_id: str, skill_name: str) -> str:
    if (not re.fullmatch(r"[0-9a-f]{24}", plugin_id) or not skill_name or
            len(skill_name) > 256 or any(ord(char) < 32 for char in skill_name)):
        raise ValueError("Invalid plugin Skill selection")
    encoded = urlsafe_b64encode(skill_name.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{PREFIX}{plugin_id}:{encoded}"


async def require_plugin_skill(
    *, tenant_id: str, user_id: str, selected_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    match = _ID.fullmatch(selected_id)
    if match is None:
        raise ValueError("Invalid plugin Skill selection")
    plugin_id, encoded = match.groups()
    name = _decode_name(encoded)
    plugins = await MongoPluginCatalog().list_enabled(tenant_id, user_id)
    for plugin in plugins:
        if plugin.get("installation_id") == plugin_id:
            skill = next((item for item in plugin.get("skills") or []
                          if item.get("name") == name and item.get("userInvocable") is True), None)
            if skill:
                return plugin, skill
    raise PermissionError("Selected plugin Skill is unavailable to this user")
