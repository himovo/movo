from __future__ import annotations

from time import monotonic
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.security import decode_access_token
from .constants import METHOD_ACTIONS, MODULE_LABELS, MUTATING_METHODS
from .repository import SystemAuditRepository


class SystemAuditMiddleware(BaseHTTPMiddleware):
    """Record every authenticated Admin API mutation without persisting request secrets."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        context = _audit_context(request)
        if request.method not in MUTATING_METHODS or context is None:
            return await call_next(request)

        started = monotonic()
        try:
            response = await call_next(request)
        except Exception:
            await _safe_record(request, context, 500, monotonic() - started)
            raise
        await _safe_record(request, context, response.status_code, monotonic() - started)
        return response


def _audit_context(request: Request) -> dict[str, str] | None:
    authorization = str(request.headers.get("authorization") or "")
    if not authorization.startswith("Bearer "):
        return None
    try:
        payload = decode_access_token(authorization.removeprefix("Bearer ").strip())
    except Exception:
        # A malformed/expired token is handled by the authentication dependency.
        # Audit discovery must not change that response path.
        return None
    subject = payload.get("sub") if isinstance(payload, dict) else None
    if not isinstance(subject, dict):
        return None
    main_id = str(subject.get("main_id") or "").strip()
    actor = str(subject.get("username") or "").strip()
    if not main_id or not actor:
        return None
    return {"main_id": main_id, "actor": actor}


async def _safe_record(request: Request, context: dict[str, str], status_code: int, elapsed: float) -> None:
    try:
        path = request.url.path
        route = request.scope.get("route")
        route_path = str(getattr(route, "path", "") or path)
        module_key = _module_key(path)
        await SystemAuditRepository().record_management_operation({
            **context,
            "category": "management",
            "module": module_key,
            "module_label": MODULE_LABELS.get(module_key, "管理后台"),
            "action": METHOD_ACTIONS.get(request.method, request.method.lower()),
            "method": request.method,
            "route": route_path,
            "target": path,
            "result": "success" if status_code < 400 else "failed",
            "status_code": status_code,
            "duration_ms": max(0, round(elapsed * 1000)),
            "client_ip": str(request.client.host if request.client else ""),
        })
    except Exception:
        # Audit storage must never turn a completed admin operation into a failure.
        return


def _module_key(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if parts and parts[0] == "api":
        parts = parts[1:]
    if not parts:
        return "system"
    if parts[0] == "settings" and len(parts) > 1:
        return "settings"
    return parts[0]
