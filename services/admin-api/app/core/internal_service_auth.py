from __future__ import annotations

import os


def resolve_backend_service_token(configured_alias: str = "") -> str:
    """Resolve the canonical admin-api -> chat-api service credential.

    ADMIN_BACKEND_SERVICE_TOKEN is shared with chat-api and therefore wins
    over the prefixed compatibility alias when both are present.
    """

    canonical = str(os.getenv("ADMIN_BACKEND_SERVICE_TOKEN") or "").strip()
    return canonical or str(configured_alias or "").strip()


__all__ = ["resolve_backend_service_token"]
