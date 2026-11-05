import asyncio
from types import SimpleNamespace

import pytest

from app.dsh_runtime.plugin_management import installer
from app.dsh_runtime.plugin_management.install_failure import install_error_text


def test_fixed_npm_version_retries_official_registry_after_mirror_miss(monkeypatch):
    calls = []

    class Transport:
        def __init__(self, *_args, **_kwargs):
            pass

        async def request(self, method, path, **kwargs):
            calls.append((method, path, kwargs.get("json")))
            if method == "POST" and path == "/v1/runtimes":
                return {"runtimeId": "validation"}
            if method == "GET":
                return {"bundles": [], "globalTools": []}
            if path.endswith("/inspect"):
                if kwargs["json"].get("registry") == installer.NPM_REGISTRY:
                    return {"status": "accepted", "kind": "registry"}
                return {"status": "refused", "problem": "not-found"}
            if path.endswith("/install"):
                return {"application": "failed", "error": {"code": "stop_after_registry_check"}}
            return {}

        async def close(self):
            pass

    monkeypatch.setattr(installer, "HttpKernelHostTransport", Transport)
    monkeypatch.setattr(installer, "get_settings", lambda: SimpleNamespace(
        DSH_RUNTIME_HOST_URL="http://localhost", DSH_RUNTIME_HOST_TOKEN="test",
    ))

    with pytest.raises(installer.PluginInstallError, match="stop_after_registry_check"):
        asyncio.run(installer.DshPluginInstaller().inspect_and_install("dsh-plugin-greet@0.3.2"))

    inspected = [body for _, path, body in calls if path.endswith("/inspect")]
    installed = [body for _, path, body in calls if path.endswith("/install")]
    assert inspected == [
        {"spec": "dsh-plugin-greet@0.3.2"},
        {"spec": "dsh-plugin-greet@0.3.2", "registry": installer.NPM_REGISTRY},
    ]
    assert installed == [{"spec": "dsh-plugin-greet@0.3.2", "registry": installer.NPM_REGISTRY}]


def test_registry_fallback_is_passed_to_runtime_validation(monkeypatch):
    profiles = []

    class Transport:
        def __init__(self, *_args, **_kwargs):
            pass

        async def request(self, method, path, **kwargs):
            body = kwargs.get("json") or {}
            if method == "POST" and path == "/v1/runtimes":
                profiles.append(body.get("modelProfile"))
                return {"runtimeId": str(len(profiles))}
            if path.endswith("/inspect"):
                return {"status": "accepted", "kind": "registry"} if body.get("registry") else {"status": "refused", "problem": "not-found"}
            if path.endswith("/install"):
                return {"bundle": "dsh-plugin-greet", "version": "0.3.2", "application": "restart-required"}
            if method == "GET":
                return {"bundles": [{"name": "dsh-plugin-greet", "version": "0.3.2"}], "globalTools": []}
            return {}

        async def close(self):
            pass

    monkeypatch.setattr(installer, "HttpKernelHostTransport", Transport)
    monkeypatch.setattr(installer, "get_settings", lambda: SimpleNamespace(
        DSH_RUNTIME_HOST_URL="http://localhost", DSH_RUNTIME_HOST_TOKEN="test",
    ))

    package = asyncio.run(installer.DshPluginInstaller().inspect_and_install("dsh-plugin-greet@0.3.2"))
    assert package["registry"] == installer.NPM_REGISTRY
    assert profiles[1]["plugins"][0]["registry"] == installer.NPM_REGISTRY


def test_missing_dependency_on_mirror_retries_whole_install_from_official_registry(monkeypatch):
    install_calls = []

    class Transport:
        def __init__(self, *_args, **_kwargs):
            pass

        async def request(self, method, path, **kwargs):
            body = kwargs.get("json") or {}
            if method == "POST" and path == "/v1/runtimes":
                return {"runtimeId": "validation"}
            if path.endswith("/inspect"):
                return {"status": "accepted", "kind": "registry"}
            if path.endswith("/install"):
                install_calls.append(body)
                if not body.get("registry"):
                    return {"application": "failed", "error": {
                        "code": "operation-error",
                        "diagnostic": "[ERR_PNPM_NO_MATCHING_VERSION] No matching version found for sqlite@0.2.1",
                    }}
                return {"bundle": "codegraph", "version": "0.2.1", "application": "restart-required"}
            if method == "GET":
                return {"bundles": [{"name": "codegraph", "version": "0.2.1"}], "globalTools": []}
            return {}

        async def close(self):
            pass

    monkeypatch.setattr(installer, "HttpKernelHostTransport", Transport)
    monkeypatch.setattr(installer, "get_settings", lambda: SimpleNamespace(
        DSH_RUNTIME_HOST_URL="http://localhost", DSH_RUNTIME_HOST_TOKEN="test",
    ))

    package = asyncio.run(installer.DshPluginInstaller().inspect_and_install("codegraph@0.2.1"))
    assert package["registry"] == installer.NPM_REGISTRY
    assert install_calls == [
        {"spec": "codegraph@0.2.1"},
        {"spec": "codegraph@0.2.1", "registry": installer.NPM_REGISTRY},
    ]


def test_install_failure_preserves_package_manager_diagnostic():
    failure = {"error": {"code": "operation-error", "diagnostic": "No matching version found for sqlite@0.2.1"}}
    assert install_error_text(failure) == "operation-error: No matching version found for sqlite@0.2.1"


def test_offline_mode_never_tries_official_registry(monkeypatch, tmp_path):
    (tmp_path / "offline-only").touch()
    monkeypatch.setenv("MOVO_OFFLINE_PACKAGE_ROOT", str(tmp_path))
    calls = []

    class Transport:
        def __init__(self, *_args, **_kwargs):
            pass

        async def request(self, method, path, **kwargs):
            calls.append((method, path, kwargs.get("json")))
            if method == "POST" and path == "/v1/runtimes":
                return {"runtimeId": "validation"}
            if method == "GET":
                return {"bundles": [], "globalTools": []}
            if path.endswith("/inspect"):
                return {"status": "refused", "problem": "not-found"}
            return {}

        async def close(self):
            pass

    monkeypatch.setattr(installer, "HttpKernelHostTransport", Transport)
    monkeypatch.setattr(installer, "get_settings", lambda: SimpleNamespace(
        DSH_RUNTIME_HOST_URL="http://localhost", DSH_RUNTIME_HOST_TOKEN="test",
    ))

    with pytest.raises(installer.PluginInstallError, match="plugin_offline_package_missing"):
        asyncio.run(installer.DshPluginInstaller().inspect_and_install("missing-plugin@1.0.0"))

    assert [body for _, path, body in calls if path.endswith("/inspect")] == [
        {"spec": "missing-plugin@1.0.0"},
    ]
