"""Resolve the separate browser origin for untrusted plugin client code."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from fastapi import HTTPException, Request


def _same_origin(left: str, right: str) -> bool:
    first, second = urlsplit(left), urlsplit(right)
    try:
        return (first.scheme, first.hostname, first.port or (443 if first.scheme == "https" else 80)) == (
            second.scheme, second.hostname, second.port or (443 if second.scheme == "https" else 80)
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="plugin_ui_origin_invalid") from exc


def plugin_ui_public_origin(request: Request) -> str:
    request_scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",", 1)[0].strip()
    request_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    main_origin = f"{request_scheme}://{request_host}"
    configured = os.environ.get("MOVO_PLUGIN_UI_PUBLIC_ORIGIN", "").strip().rstrip("/")
    if configured:
        value = urlsplit(configured)
        if value.scheme not in {"http", "https"} or not value.hostname or value.path or value.query or value.fragment:
            raise HTTPException(status_code=503, detail="plugin_ui_origin_invalid")
        if _same_origin(configured, main_origin):
            raise HTTPException(status_code=503, detail="plugin_ui_origin_must_be_separate")
        return configured
    if request_scheme != "http":
        raise HTTPException(status_code=503, detail="plugin_ui_public_origin_required")
    hostname = urlsplit(f"http://{request_host}").hostname
    default_port = "3200" if os.environ.get("ASKAI_ADMIN_APP_ENV") == "development" else "3100"
    # The edge gateway owns the public port mapping. Its overwritten header
    # takes precedence over a stale environment in a separately rebuilt API.
    # Environment fallback preserves direct local development and older gateways.
    port = request.headers.get("x-movo-plugin-ui-port")
    if port is None:
        port = os.environ.get("MOVO_PLUGIN_UI_PORT", "").strip() or default_port
    if not hostname or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise HTTPException(status_code=503, detail="plugin_ui_origin_invalid")
    host = f"[{hostname}]" if ":" in hostname else hostname
    origin = f"http://{host}:{int(port)}"
    if _same_origin(origin, main_origin):
        raise HTTPException(status_code=503, detail="plugin_ui_origin_must_be_separate")
    return origin
