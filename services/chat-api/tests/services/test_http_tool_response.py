import asyncio

import pytest

from app.services.external_tools import ExternalToolService
from app.services.http_tool_response import decode_response_json_field


@pytest.mark.parametrize("mode", ["direct", "plugin_gateway"])
def test_http_tool_test_and_runtime_decode_configured_response_field(monkeypatch, mode):
    service = ExternalToolService()
    raw = {
        "data": {"payload": '{"rows":[{"id":123}]}', "other": '{"leave":"intact"}'},
        "status": "ok",
    }
    tool = {
        "id": "tool-1",
        "type": "http",
        "status": "active",
        "config": {"responseJsonPath": "data.payload"},
    }

    async def fake_http(*args):
        return {"success": True, "raw": raw}

    monkeypatch.setattr(service, "_resolve_http_request", lambda *_: {"executionMode": mode})
    monkeypatch.setattr(service, "_test_http_direct", fake_http)
    monkeypatch.setattr(service, "_test_http_via_plugin_gateway", fake_http)
    monkeypatch.setattr(service, "_build_debug_trace", lambda *_: {})

    async def fake_get(*args, **kwargs):
        return tool

    monkeypatch.setattr(service, "get", fake_get)

    test_result = asyncio.run(service._test_http(tool, {}))
    runtime_result = asyncio.run(service.execute_runtime(
        external_tool_id="tool-1", provider_type="http", arguments={}, actor_user_id="user-1"
    ))
    expected = {
        "data": {"payload": {"rows": [{"id": 123}]}, "other": '{"leave":"intact"}'},
        "status": "ok",
    }
    assert test_result["raw"] == runtime_result["raw"] == expected
    assert raw["data"]["payload"] == '{"rows":[{"id":123}]}'


@pytest.mark.parametrize("field", [None, {"id": 1}, "", "invalid", "123", '"text"'])
def test_decode_ignores_non_container_content(field):
    raw = {"payload": field}
    assert decode_response_json_field(raw, "payload") is raw
    assert decode_response_json_field(raw, "missing.payload") is raw
    assert decode_response_json_field(raw, "") is raw
