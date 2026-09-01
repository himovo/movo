from __future__ import annotations

import json
import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import principal as principal_module
from app.api.principal import ApiPrincipal, _assert_end_user_scope, require_api_principal


def _request(
    *,
    query: str = "",
    body: dict[str, object] | None = None,
) -> Request:
    raw_body = json.dumps(body or {}).encode("utf-8")
    consumed = False

    async def receive():
        nonlocal consumed
        if consumed:
            return {"type": "http.request", "body": b"", "more_body": False}
        consumed = True
        return {"type": "http.request", "body": raw_body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/resource",
            "query_string": query.encode("utf-8"),
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )


def test_end_user_scope_accepts_matching_identity() -> None:
    principal = ApiPrincipal(kind="end_user", main_id="tenant-a", user_id="user-a")
    request = _request(body={"main_id": "tenant-a", "user_id": "user-a"})

    asyncio.run(_assert_end_user_scope(request, principal))


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"user_id": "user-b"}, "user_scope_mismatch"),
        ({"main_id": "tenant-b"}, "tenant_scope_mismatch"),
    ],
)
def test_end_user_scope_rejects_caller_controlled_identity(body, detail) -> None:
    principal = ApiPrincipal(kind="end_user", main_id="tenant-a", user_id="user-a")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_assert_end_user_scope(_request(body=body), principal))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == detail


def test_service_token_authentication_is_explicit(monkeypatch) -> None:
    monkeypatch.setattr(
        principal_module,
        "get_settings",
        lambda: type("Settings", (), {"ADMIN_BACKEND_SERVICE_TOKEN": "service-secret"})(),
    )

    resolved = asyncio.run(
        require_api_principal(
            _request(query="main_id=tenant-a"),
            authorization=None,
            service_token="service-secret",
        )
    )

    assert resolved == ApiPrincipal(kind="admin_service", main_id="tenant-a")


def test_invalid_service_token_falls_back_to_user_session(monkeypatch) -> None:
    monkeypatch.setattr(
        principal_module,
        "get_settings",
        lambda: type("Settings", (), {"ADMIN_BACKEND_SERVICE_TOKEN": "service-secret"})(),
    )

    async def fake_resolve_session_user(_authorization):
        return {"main_id": "tenant-a", "user": {"_id": "user-a"}}

    monkeypatch.setattr(principal_module, "resolve_session_user", fake_resolve_session_user)

    resolved = asyncio.run(
        require_api_principal(
            _request(body={"main_id": "tenant-a", "user_id": "user-a"}),
            authorization="Bearer user-token",
            service_token="wrong",
        )
    )

    assert resolved == ApiPrincipal(kind="end_user", main_id="tenant-a", user_id="user-a")
