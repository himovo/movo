from __future__ import annotations

import httpx
import pytest

from app.docker_engine import DockerEngine


def http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "http://docker/test")
    return httpx.HTTPStatusError("Docker request failed", request=request, response=httpx.Response(status, request=request))


def test_disconnect_accepts_missing_network_after_docker_500() -> None:
    engine = DockerEngine.__new__(DockerEngine)
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path))
        raise http_error(500 if method == "POST" else 404)

    engine.request = request
    engine.disconnect_network("network", "proxy")
    assert calls == [("POST", "/networks/network/disconnect"), ("GET", "/networks/network")]


def test_disconnect_preserves_error_when_proxy_still_attached() -> None:
    engine = DockerEngine.__new__(DockerEngine)

    def request(method, path, **kwargs):
        if method == "POST":
            raise http_error(500)
        return httpx.Response(200, json={"Containers": {"proxy": {}}})

    engine.request = request
    with pytest.raises(httpx.HTTPStatusError):
        engine.disconnect_network("network", "proxy")
