import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.dsh_runtime.plugin_ui.public_origin import plugin_ui_public_origin


def _request(host: str = "movo.example:3000", scheme: str = "http", plugin_port: str | None = None) -> Request:
    headers = [(b"host", host.encode()), (b"x-forwarded-proto", scheme.encode())]
    if plugin_port is not None:
        headers.append((b"x-movo-plugin-ui-port", plugin_port.encode()))
    return Request({"type": "http", "method": "GET", "scheme": scheme,
                    "path": "/api/dsh-plugins/personal/x/ui-launch",
                    "headers": headers})


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


@pytest.mark.parametrize("main_port,plugin_port", [("3001", "3101"), ("3002", "3102"), ("8080", "9173")])
def test_gateway_port_overrides_stale_api_environment(monkeypatch, main_port, plugin_port):
    monkeypatch.delenv("MOVO_PLUGIN_UI_PUBLIC_ORIGIN", raising=False)
    monkeypatch.setenv("MOVO_PLUGIN_UI_PORT", "3100")
    request = _request(host=f"movo.example:{main_port}", plugin_port=plugin_port)
    assert plugin_ui_public_origin(request) == f"http://movo.example:{plugin_port}"


@pytest.mark.parametrize("port", ["", "0", "65536", "3101/path", "3101,3102", "not-a-port", "3001"])
def test_gateway_port_never_falls_back_when_invalid_or_same_origin(monkeypatch, port):
    monkeypatch.delenv("MOVO_PLUGIN_UI_PUBLIC_ORIGIN", raising=False)
    monkeypatch.setenv("MOVO_PLUGIN_UI_PORT", "3100")
    with pytest.raises(HTTPException) as error:
        plugin_ui_public_origin(_request(host="movo.example:3001", plugin_port=port))
    assert error.value.status_code == 503


def test_gateway_port_preserves_ipv6_host(monkeypatch):
    monkeypatch.delenv("MOVO_PLUGIN_UI_PUBLIC_ORIGIN", raising=False)
    assert plugin_ui_public_origin(_request(host="[::1]:3001", plugin_port="3101")) == "http://[::1]:3101"


def test_explicit_https_plugin_domain_remains_supported(monkeypatch):
    monkeypatch.setenv("MOVO_PLUGIN_UI_PUBLIC_ORIGIN", "https://plugins.example")
    assert plugin_ui_public_origin(_request(scheme="https", plugin_port="3101")) == "https://plugins.example"


@pytest.mark.parametrize("host,port", [("movo.example", "80"), ("movo.example:3001", "03001")])
def test_gateway_cannot_select_equivalent_main_origin(monkeypatch, host, port):
    monkeypatch.delenv("MOVO_PLUGIN_UI_PUBLIC_ORIGIN", raising=False)
    with pytest.raises(HTTPException) as error:
        plugin_ui_public_origin(_request(host=host, plugin_port=port))
    assert error.value.detail == "plugin_ui_origin_must_be_separate"
