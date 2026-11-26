import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.endpoints import context_usage as endpoint
from app.api.principal import ApiPrincipal
from app.dsh_runtime.context_usage import ContextUsageReader
from app.dsh_runtime.session_access import SessionReadDeniedError


def test_context_usage_rejects_cross_tenant_or_removed_members_before_reading(monkeypatch):
    authorize = AsyncMock(side_effect=SessionReadDeniedError())
    reader = SimpleNamespace(read=AsyncMock())
    monkeypatch.setattr(endpoint, "get_db", lambda: object())
    monkeypatch.setattr(endpoint, "SessionReadAuthorizer", lambda _: SimpleNamespace(authorize_read=authorize))
    monkeypatch.setattr(endpoint.dsh_runtime_application, "context_usage", reader)
    with pytest.raises(HTTPException) as failure:
        asyncio.run(endpoint.context_usage("session", ApiPrincipal("end_user", "tenant", "user")))
    assert failure.value.status_code == 404
    reader.read.assert_not_called()


def test_context_usage_rechecks_membership_before_returning(monkeypatch):
    authorize = AsyncMock(side_effect=[None, SessionReadDeniedError()])
    reader = SimpleNamespace(read=AsyncMock(return_value={"available": True, "usedTokens": 123}))
    monkeypatch.setattr(endpoint, "get_db", lambda: object())
    monkeypatch.setattr(endpoint, "SessionReadAuthorizer", lambda _: SimpleNamespace(authorize_read=authorize))
    monkeypatch.setattr(endpoint.dsh_runtime_application, "context_usage", reader)
    with pytest.raises(HTTPException) as failure:
        asyncio.run(endpoint.context_usage("session", ApiPrincipal("end_user", "tenant", "user")))
    assert failure.value.status_code == 404
    assert authorize.await_count == 2


def test_context_usage_drops_a_measurement_from_a_rotated_binding():
    bindings = SimpleNamespace(current=AsyncMock(side_effect=[
        {"binding_id": "old", "kernel_session_id": "old-session"}, {"binding_id": "new"},
    ]))
    reader = ContextUsageReader(
        bindings=bindings, coordinator=SimpleNamespace(restore=AsyncMock()),
        gateway=SimpleNamespace(context_usage=AsyncMock(return_value={"available": True, "usedTokens": 456})),
    )
    assert asyncio.run(reader.read("session", tenant_id="tenant", user_id="user")) == {
        "available": False, "reason": "binding_changed",
    }
