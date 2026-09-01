from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Literal

from fastapi import Header, HTTPException, Request

from app.core.config import get_settings
from app.core.tenant import resolve_main_id
from app.services.end_user_session import resolve_session_user


@dataclass(frozen=True)
class ApiPrincipal:
    kind: Literal["end_user", "admin_service"]
    main_id: str
    user_id: str = ""


def _matches(value: str, expected: str) -> bool:
    return bool(value and expected and hmac.compare_digest(value, expected))


async def _assert_end_user_scope(request: Request, principal: ApiPrincipal) -> None:
    claims: dict[str, str] = {}
    for key in ("userId", "user_id", "mainId", "main_id"):
        value = request.query_params.get(key)
        if value:
            claims[key] = value

    content_type = str(request.headers.get("content-type") or "").lower()
    try:
        if "application/json" in content_type:
            body = await request.json()
            if isinstance(body, dict):
                for key in ("userId", "user_id", "mainId", "main_id"):
                    value = body.get(key)
                    if value:
                        claims[key] = str(value)
        elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
            form = await request.form()
            for key in ("userId", "user_id", "mainId", "main_id"):
                value = form.get(key)
                if isinstance(value, str) and value:
                    claims[key] = value
    except Exception:
        # Request validation remains FastAPI's responsibility. Scope checks are
        # applied whenever identity fields can be decoded safely.
        pass

    claimed_user = claims.get("userId") or claims.get("user_id")
    if claimed_user and claimed_user != principal.user_id:
        raise HTTPException(status_code=403, detail="user_scope_mismatch")

    claimed_main = claims.get("mainId") or claims.get("main_id")
    if claimed_main and resolve_main_id(claimed_main) != principal.main_id:
        raise HTTPException(status_code=403, detail="tenant_scope_mismatch")


async def require_api_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    service_token: str = Header(default="", alias="X-MOVO-Service-Token"),
) -> ApiPrincipal:
    settings = get_settings()
    expected_service_token = str(settings.ADMIN_BACKEND_SERVICE_TOKEN or "")
    if _matches(service_token, expected_service_token):
        main_id = resolve_main_id(
            request.query_params.get("mainId") or request.query_params.get("main_id")
        )
        return ApiPrincipal(kind="admin_service", main_id=main_id)

    resolved = await resolve_session_user(authorization)
    principal = ApiPrincipal(
        kind="end_user",
        main_id=resolve_main_id(resolved["main_id"]),
        user_id=str(resolved["user"].get("_id") or ""),
    )
    await _assert_end_user_scope(request, principal)
    return principal


async def require_end_user_principal(
    request: Request,
    authorization: str | None = Header(default=None),
) -> ApiPrincipal:
    resolved = await resolve_session_user(authorization)
    principal = ApiPrincipal(
        kind="end_user",
        main_id=resolve_main_id(resolved["main_id"]),
        user_id=str(resolved["user"].get("_id") or ""),
    )
    await _assert_end_user_scope(request, principal)
    return principal
