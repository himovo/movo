import asyncio

import httpx

from app.execution_isolation import runtime_policy


def test_last_confirmed_placement_survives_timeout_and_recovers(monkeypatch):
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_URL", "http://sandbox-manager")
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_TOKEN", "test-token")
    monkeypatch.setattr(runtime_policy, "_confirmed", {})
    results = iter([None, "on_demand", None, "unknown", "forced", None])
    create_client = httpx.AsyncClient

    def reply(request):
        assert request.url.path == "/v1/settings"
        assert request.headers["Authorization"] == "Bearer test-token"
        mode = next(results)
        if mode is None:
            raise httpx.ReadTimeout("fixture timeout", request=request)
        return httpx.Response(200, json={"runtime_mode": mode})

    def client(**kwargs):
        return create_client(transport=httpx.MockTransport(reply), **kwargs)

    monkeypatch.setattr(runtime_policy.httpx, "AsyncClient", client)

    async def run():
        assert [await runtime_policy.uses_on_demand_runtime() for _ in range(6)] == [
            False, True, True, True, False, False,
        ]

    asyncio.run(run())
