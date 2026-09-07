"""Durable aliases shared by browser selection and action history.

URLs are canonicalized by the existing business-action identity rules.  Some
single-page applications expose a durable content identity even when opening a
detail view does not change the URL; those opaque identities are namespaced by
site so they cannot collide across unrelated systems.
"""
from __future__ import annotations

from typing import Any, Iterable

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation
from app.enterprise_capabilities.browser.engine.business_action import browser_target_identity


def normalize_target_alias(value: Any, *, system_id: str = "") -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("opaque:"):
        return raw
    parsed_system, url_target = browser_target_identity(raw)
    if url_target:
        return url_target
    if any(char.isspace() for char in raw) or len(raw) > 500:
        return ""
    namespace = str(system_id or parsed_system or "unknown").strip().casefold()
    return f"opaque:{namespace}:{raw}"


def observation_target_aliases(
    observation: Observation,
    *,
    target_hint: str = "",
) -> tuple[str, ...]:
    system_id, _target = browser_target_identity(observation.url)
    return _unique_aliases(
        (
            normalize_target_alias(target_hint, system_id=system_id),
            normalize_target_alias(observation.url, system_id=system_id),
        ),
    )


def element_target_aliases(
    element: Any,
    *,
    page_url: str = "",
) -> tuple[str, ...]:
    if not isinstance(element, dict):
        return ()
    system_id, _target = browser_target_identity(page_url)
    return _unique_aliases(
        (
            normalize_target_alias(element.get("href"), system_id=system_id),
            normalize_target_alias(element.get("contentContextId"), system_id=system_id),
        ),
    )


def _unique_aliases(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


__all__ = [
    "element_target_aliases",
    "normalize_target_alias",
    "observation_target_aliases",
]
