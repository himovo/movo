"""Authorized references for commands contributed by DSH plugins."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
import re
from typing import Any

from .plugins import MongoPluginCatalog


PREFIX = "dsh_plugin_command:"
_ID = re.compile(r"^dsh_plugin_command:([0-9a-f]{24}):([A-Za-z0-9_-]+)$")


def selected_command_name(selected_id: str) -> str:
    match = _ID.fullmatch(selected_id)
    if match is None:
        raise ValueError("Invalid plugin command selection")
    try:
        name = urlsafe_b64decode(match[2] + "=" * (-len(match[2]) % 4)).decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Invalid plugin command selection") from exc
    if not name or len(name) > 256 or any(ord(char) < 32 for char in name):
        raise ValueError("Invalid plugin command selection")
    return name


def selection_id(plugin_id: str, command_name: str) -> str:
    if (not re.fullmatch(r"[0-9a-f]{24}", plugin_id) or not command_name or
            len(command_name) > 256 or any(ord(char) < 32 for char in command_name)):
        raise ValueError("Invalid plugin command selection")
    encoded = urlsafe_b64encode(command_name.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{PREFIX}{plugin_id}:{encoded}"


async def require_plugin_command(
    *, tenant_id: str, user_id: str, selected_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    match = _ID.fullmatch(selected_id)
    if match is None:
        raise ValueError("Invalid plugin command selection")
    name = selected_command_name(selected_id)
    for plugin in await MongoPluginCatalog().list_enabled(tenant_id, user_id):
        if plugin.get("installation_id") != match[1]:
            continue
        command = next((item for item in plugin.get("commands") or []
                        if item.get("name") == name), None)
        if command and command.get("definitionId"):
            return plugin, command
    raise PermissionError("Selected plugin command is unavailable to this user")
