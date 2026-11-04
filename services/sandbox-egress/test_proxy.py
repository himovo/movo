from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location("sandbox_proxy", Path(__file__).with_name("proxy.py"))
assert spec and spec.loader
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


@pytest.mark.parametrize("host", ["127.0.0.1", "169.254.169.254", "::1", "fe80::1"])
def test_local_and_metadata_destinations_are_rejected(host: str) -> None:
    with pytest.raises(PermissionError):
        asyncio.run(proxy._resolved_destination(host, 443))


@pytest.mark.parametrize("host", ["10.0.0.1", "172.16.0.1", "192.168.5.118", "fd00::1"])
def test_private_destinations_are_resolved_without_connecting(host: str) -> None:
    assert asyncio.run(proxy._resolved_destination(host, 22)) == (host, 22)


def test_public_destination_is_resolved_without_connecting() -> None:
    assert asyncio.run(proxy._resolved_destination("8.8.8.8", 443)) == ("8.8.8.8", 443)
