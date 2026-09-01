from __future__ import annotations

from typing import Any


COMMUNITY_EDITION = "community"


def is_community_organization(org: dict[str, Any] | None) -> bool:
    if not org:
        return False
    return str(org.get("edition") or org.get("tier") or "").strip().lower() == COMMUNITY_EDITION


def billing_enabled(org: dict[str, Any] | None) -> bool:
    if is_community_organization(org):
        return False
    return bool((org or {}).get("billing_enabled", True))


def member_limit(org: dict[str, Any] | None) -> int | None:
    if is_community_organization(org):
        return None
    raw_limit = (org or {}).get("user_limit", 5)
    if raw_limit is None:
        return None
    return max(0, int(raw_limit))


def product_edition_fields(org: dict[str, Any] | None) -> dict[str, Any]:
    community = is_community_organization(org)
    return {
        "edition": COMMUNITY_EDITION if community else str((org or {}).get("edition") or "cloud"),
        "billingEnabled": billing_enabled(org),
        "memberLimit": member_limit(org),
    }
