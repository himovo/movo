import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.dsh_runtime.plugin_ui.public_origin import plugin_ui_public_origin


def _request(host: str = "movo.example:3000", scheme: str = "http") -> Request:
    return Request({"type": "http", "method": "GET", "scheme": scheme,
                    "path": "/api/dsh-plugins/personal/x/ui-launch",
                    "headers": [(b"host", host.encode()),
                                (b"x-forwarded-proto", scheme.encode())]})


def test_plugin_ui_origin_uses_separate_port(monkeypatch):
    monkeypatch.delenv("MOVO_PLUGIN_UI_PUBLIC_ORIGIN", raising=False)
    monkeypatch.setenv("MOVO_PLUGIN_UI_PORT", "3100")
    assert plugin_ui_public_origin(_request()) == "http://movo.example:3100"


def test_plugin_ui_origin_uses_dev_gateway_port(monkeypatch):
    monkeypatch.delenv("MOVO_PLUGIN_UI_PUBLIC_ORIGIN", raising=False)
    monkeypatch.delenv("MOVO_PLUGIN_UI_PORT", raising=False)
    monkeypatch.setenv("ASKAI_ADMIN_APP_ENV", "development")
    assert plugin_ui_public_origin(_request(host="localhost:3000")) == "http://localhost:3200"


def test_plugin_ui_requires_explicit_https_origin(monkeypatch):
    monkeypatch.delenv("MOVO_PLUGIN_UI_PUBLIC_ORIGIN", raising=False)
    with pytest.raises(HTTPException):
        plugin_ui_public_origin(_request(scheme="https"))
    monkeypatch.setenv("MOVO_PLUGIN_UI_PUBLIC_ORIGIN", "https://plugins.example")
    assert plugin_ui_public_origin(_request(scheme="https")) == "https://plugins.example"
