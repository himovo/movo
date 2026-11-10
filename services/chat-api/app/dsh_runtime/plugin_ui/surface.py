"""Identify plugin routes that can host a standalone browser page."""

from __future__ import annotations


def has_standalone_surface(plugin: dict) -> bool:
    return bool(plugin.get("client_modules"))
