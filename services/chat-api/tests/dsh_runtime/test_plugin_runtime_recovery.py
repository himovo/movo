import asyncio

import pytest

from app.dsh_runtime.errors import DshTransportError
from app.dsh_runtime.contracts import CreateRuntimeRequest
from app.dsh_runtime.gateway import DshAgentKernelGateway
from app.dsh_runtime.profile.plugin_runtime_recovery import profile_without_unavailable_plugins


class _Transport:
    def __init__(self):
        self.probed = []
        self.disposed = []

    async def request(self, method, path, *, json=None, params=None):
        if method == "DELETE":
            self.disposed.append(path)
            return {}
        plugin = json["modelProfile"]["plugins"][0]
        self.probed.append(plugin["name"])
        if plugin["name"] == "broken":
            raise DshTransportError("DSH plugin broken failed to install: ambiguous-install")
        return {"runtimeId": "probe-good"}


def test_failed_optional_plugin_is_removed_after_individual_runtime_probe():
    transport = _Transport()
    payload = {
        "profileVersion": "rp-one", "isolationKey": "tenant:one:profile:rp-one",
        "modelProfile": {"profileVersion": "rp-one", "plugins": [
            {"name": "broken", "version": "1", "spec": "broken@1"},
            {"name": "healthy", "version": "1", "spec": "healthy@1"},
        ]},
    }
    recovered = asyncio.run(profile_without_unavailable_plugins(
        transport, payload, DshTransportError("DSH plugin broken failed to install"),
    ))
    assert [plugin["name"] for plugin in recovered["modelProfile"]["plugins"]] == ["healthy"]
    assert transport.probed == ["broken", "healthy"]
    assert transport.disposed == ["/v1/runtimes/probe-good"]
    assert len(payload["modelProfile"]["plugins"]) == 2


def test_unrelated_runtime_failure_is_not_hidden():
    payload = {"modelProfile": {"plugins": [{"name": "healthy"}]}}
    with pytest.raises(DshTransportError, match="network unavailable"):
        asyncio.run(profile_without_unavailable_plugins(
            _Transport(), payload, DshTransportError("network unavailable"),
        ))


def test_sandbox_runtime_failure_does_not_silently_remove_plugins():
    payload = {"modelProfile": {"plugins": [{"name": "healthy"}]}}
    with pytest.raises(DshTransportError, match="did not become healthy"):
        asyncio.run(profile_without_unavailable_plugins(
            _Transport(), payload, DshTransportError("Container plugin Runtime did not become healthy"),
        ))


def test_gateway_retries_same_profile_with_only_healthy_plugins(monkeypatch):
    unavailable = []

    async def mark_unavailable(**kwargs):
        unavailable.append(kwargs)

    monkeypatch.setattr("app.dsh_runtime.gateway.mark_runtime_unavailable", mark_unavailable)

    class Resolver:
        async def resolve(self, profile_version, *, tenant_id=None):
            return {"profileVersion": profile_version, "modelInstanceId": "model-one", "plugins": [
                {"installation_id": "a" * 24, "name": "broken", "version": "1", "spec": "broken@1"},
                {"installation_id": "b" * 24, "name": "healthy", "version": "1", "spec": "healthy@1"},
            ]}

    class Transport(_Transport):
        def __init__(self):
            super().__init__()
            self.production_attempts = []

        async def request(self, method, path, *, json=None, params=None):
            if method == "POST" and path == "/v1/runtimes" and not json["isolationKey"].startswith("plugin-runtime-probe:"):
                names = [item["name"] for item in json["modelProfile"]["plugins"]]
                self.production_attempts.append(names)
                if "broken" in names:
                    raise DshTransportError("DSH plugin broken failed to install")
                return {"runtimeId": "runtime-one", "kernelVersion": "1", "profileVersion": json["profileVersion"],
                        "isolationKey": json["isolationKey"]}
            return await super().request(method, path, json=json, params=params)

    async def run():
        transport = Transport()
        gateway = DshAgentKernelGateway(transport, profile_resolver=Resolver())
        runtime = await gateway.create_runtime(CreateRuntimeRequest(
            tenant_id="tenant-one", profile_version="rp-one", isolation_key="tenant:one:profile:rp-one",
        ))
        assert runtime.profile_version == "rp-one"
        assert transport.production_attempts == [["broken", "healthy"], ["healthy"]]
        assert unavailable[0]["tenant_id"] == "tenant-one"
        assert [item["name"] for item in unavailable[0]["activated"]] == ["healthy"]

    asyncio.run(run())
