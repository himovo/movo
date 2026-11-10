import asyncio
from types import SimpleNamespace

import pytest

from app.dsh_runtime.plugin_management import preflight
from app.dsh_runtime.plugin_management.installer import PluginInstallError


class FakeTransport:
    def __init__(self, *args, **kwargs):
        self.calls = []
        self.closed = False

    async def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == "/health":
            return {"ok": True, "kernel": "dsh", "version": "0.2.1-alpha.1", "lockedVersion": "0.2.1-alpha.1"}
        if method == "POST" and path == "/v1/runtimes":
            return {"runtimeId": "temporary"}
        if path.endswith("/inspect"):
            return {"status": "accepted", "kind": "registry", "name": "plugin-a", "version": "1.2.3", "registry": "https://registry.npmjs.org/"}
        if method == "DELETE":
            return {"disposed": True}
        raise AssertionError((method, path))

    async def close(self):
        self.closed = True


def test_preflight_reports_native_package_and_cleans_temporary_runtime(monkeypatch):
    transport = FakeTransport()
    monkeypatch.setattr(preflight, "HttpKernelHostTransport", lambda *args, **kwargs: transport)
    monkeypatch.setattr(preflight, "get_settings", lambda: SimpleNamespace(
        DSH_RUNTIME_HOST_URL="http://host", DSH_RUNTIME_HOST_TOKEN="token",
    ))
    result = asyncio.run(preflight.inspect_plugin_spec("plugin-a@1.2.3"))
    assert result["status"] == "pending_runtime_validation"
    assert result["version"] == "1.2.3"
    assert result["dshVersion"] == "0.2.1-alpha.1"
    assert any(method == "DELETE" and path == "/v1/runtimes/temporary" for method, path, _ in transport.calls)
    assert transport.closed


def test_preflight_rejects_deployment_version_mismatch_before_inspection(monkeypatch):
    class MismatchedTransport(FakeTransport):
        async def request(self, method, path, **kwargs):
            if path == "/health":
                return {"ok": True, "kernel": "dsh", "version": "0.2.2", "lockedVersion": "0.2.1-alpha.1"}
            return await super().request(method, path, **kwargs)

    transport = MismatchedTransport()
    monkeypatch.setattr(preflight, "HttpKernelHostTransport", lambda *args, **kwargs: transport)
    monkeypatch.setattr(preflight, "get_settings", lambda: SimpleNamespace(
        DSH_RUNTIME_HOST_URL="http://host", DSH_RUNTIME_HOST_TOKEN="token",
    ))
    with pytest.raises(PluginInstallError, match="dsh_runtime_version_mismatch"):
        asyncio.run(preflight.inspect_plugin_spec("plugin-a@1.2.3"))
    assert transport.closed
    assert not any(path == "/v1/runtimes" for _, path, _ in transport.calls)


def test_preflight_uses_imported_archive_when_offline(monkeypatch, tmp_path):
    transport = FakeTransport()
    async def no_op():
        return None

    monkeypatch.setattr(preflight, "HttpKernelHostTransport", lambda *args, **kwargs: transport)
    monkeypatch.setattr(preflight, "get_settings", lambda: SimpleNamespace(
        DSH_RUNTIME_HOST_URL="http://host", DSH_RUNTIME_HOST_TOKEN="token",
    ))
    monkeypatch.setattr(preflight, "initialize_package_source", no_op)
    monkeypatch.setattr(preflight, "imported_plugin_record", lambda spec: ("/cached/plugin-a.tgz", "0.2.1-alpha.1"))
    (tmp_path / "offline-only").touch()
    monkeypatch.setenv("MOVO_OFFLINE_PACKAGE_ROOT", str(tmp_path))
    result = asyncio.run(preflight.inspect_plugin_spec("plugin-a@1.2.3"))
    assert result["status"] == "pending_runtime_validation"
    assert result["offlineSourceDshVersion"] == "0.2.1-alpha.1"
    inspect_calls = [kwargs for method, path, kwargs in transport.calls if path.endswith("/inspect")]
    assert inspect_calls == [{"json": {"spec": "/cached/plugin-a.tgz"}}]


def test_preflight_keeps_native_refusal_diagnostic(monkeypatch):
    class RefusingTransport(FakeTransport):
        async def request(self, method, path, **kwargs):
            if path.endswith("/inspect"):
                return {"status": "refused", "problem": "not-a-bundle", "reason": "package has no dsh.bundle"}
            return await super().request(method, path, **kwargs)

    transport = RefusingTransport()
    monkeypatch.setattr(preflight, "HttpKernelHostTransport", lambda *args, **kwargs: transport)
    monkeypatch.setattr(preflight, "get_settings", lambda: SimpleNamespace(
        DSH_RUNTIME_HOST_URL="http://host", DSH_RUNTIME_HOST_TOKEN="token",
    ))
    result = asyncio.run(preflight.inspect_plugin_spec("plugin-a@1.2.3"))
    assert result["status"] == "refused"
    assert result["problem"] == "not-a-bundle"
    assert result["diagnostic"] == "package has no dsh.bundle"


def test_preflight_does_not_claim_git_package_is_identified(monkeypatch):
    class GitTransport(FakeTransport):
        async def request(self, method, path, **kwargs):
            if path.endswith("/inspect"):
                return {"status": "accepted", "kind": "git", "bundle": None, "registry": None}
            return await super().request(method, path, **kwargs)

    transport = GitTransport()
    monkeypatch.setattr(preflight, "HttpKernelHostTransport", lambda *args, **kwargs: transport)
    monkeypatch.setattr(preflight, "get_settings", lambda: SimpleNamespace(
        DSH_RUNTIME_HOST_URL="http://host", DSH_RUNTIME_HOST_TOKEN="token",
    ))
    result = asyncio.run(preflight.inspect_plugin_spec("https://example.com/plugin.git"))
    assert result["status"] == "unverified"
    assert result["name"] is None


def test_preflight_rejects_unpinned_registry_spec(monkeypatch):
    transport = FakeTransport()
    monkeypatch.setattr(preflight, "HttpKernelHostTransport", lambda *args, **kwargs: transport)
    monkeypatch.setattr(preflight, "get_settings", lambda: SimpleNamespace(
        DSH_RUNTIME_HOST_URL="http://host", DSH_RUNTIME_HOST_TOKEN="token",
    ))
    result = asyncio.run(preflight.inspect_plugin_spec("plugin-a@latest"))
    assert result["status"] == "refused"
    assert result["problem"] == "fixed_plugin_version_required"


def test_preflight_registry_source_does_not_expose_credentials():
    assert preflight._public_registry("https://user:secret@example.com/npm/?token=secret") == "https://example.com/npm/"
