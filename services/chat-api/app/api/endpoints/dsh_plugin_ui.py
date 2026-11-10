"""Dedicated-origin browser gateway for one authorized DSH plugin page."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.responses import RedirectResponse

from app.dsh_runtime.application import dsh_runtime_application
from app.dsh_runtime.plugin_ui.websocket import proxy_plugin_stream


router = APIRouter(prefix="/plugin-ui", tags=["dsh-plugin-ui"])
_COOKIE = "movo_plugin_ui"


def _service():
    return dsh_runtime_application.require_plugin_ui()


@router.get("/launch")
async def launch(request: Request, ticket: str):
    try:
        grant = _service().tickets.verify(ticket)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="plugin_ui_ticket_invalid") from exc
    locale = request.query_params.get("locale")
    params = {"surface": "conversation", "session": grant.kernel_session_id}
    if request.query_params.get("probe") == "conversation-view":
        params["probe"] = "conversation-view"
    if locale in {"zh", "en"}:
        params["locale"] = locale
    destination = f"/?{urlencode(params)}" if grant.kernel_session_id else "/"
    response = RedirectResponse(url=destination, status_code=303, headers={
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
    })
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",", 1)[0].strip()
    response.set_cookie(_COOKIE, ticket, max_age=_service().tickets.lifetime_seconds,
                        httponly=True, secure=scheme == "https", samesite="strict")
    return response


@router.websocket("/api/remote.mux")
async def plugin_stream(websocket: WebSocket):
    scheme = websocket.headers.get("x-forwarded-proto", websocket.url.scheme).split(",", 1)[0].strip()
    scheme = "https" if scheme in {"https", "wss"} else "http"
    host = websocket.headers.get("x-forwarded-host") or websocket.headers.get("host") or ""
    if websocket.headers.get("origin") != f"{scheme}://{host}":
        await websocket.close(code=1008)
        return
    try:
        grant = _service().tickets.verify(websocket.cookies.get(_COOKIE, ""))
    except ValueError:
        await websocket.close(code=1008)
        return
    await proxy_plugin_stream(_service(), grant, websocket)


@router.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_plugin_page(request: Request, path: str):
    token = request.cookies.get(_COOKIE, "")
    try:
        ticket = _service().tickets.verify(token)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="plugin_ui_ticket_invalid") from exc
    if request.method not in {"GET", "HEAD"}:
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",", 1)[0].strip()
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        if request.headers.get("origin") != f"{scheme}://{host}":
            raise HTTPException(status_code=403, detail="plugin_ui_origin_denied")
    response = await _service().proxy(ticket, request, path)
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response
