import asyncio
from datetime import datetime, timedelta, timezone

from app.dsh_runtime.plugin_management.revalidation import needs_revalidation, needs_surface_refresh, revalidate_installed_plugins
from app.dsh_runtime.plugin_management.failed_assessment import failed_assessment
from app.dsh_runtime.plugin_management.installer import PluginInstallError
from app.dsh_runtime.plugin_management import repository as repository_module


class Transport:
    async def request(self, method, path):
        assert (method, path) == ("GET", "/health")
        return {"ok": True, "kernel": "dsh", "version": "0.2.2"}


class Repository:
    def __init__(self):
        self.rows = [
            {"_id": "a" * 24, "main_id": "tenant", "owner_user_id": "", "name": "plugin-a",
             "version": "1.0.0", "spec": "plugin-a@1.0.0", "availability": {"dsh_version": "0.2.1"}},
            {"_id": "b" * 24, "main_id": "tenant", "owner_user_id": "", "name": "plugin-b",
             "version": "1.0.0", "spec": "plugin-b@1.0.0", "availability": {"dsh_version": "0.2.2"}},
        ]
        self.pending = []
        self.assessments = []

    async def list_enabled_installations(self):
        return self.rows

    async def restore_legacy_surface_pending(self, version):
        return None

    async def mark_revalidation_pending(self, row, version, surface_only=False):
        self.pending.append((row["spec"], version))
        return True

    async def clear_surface_refresh(self, row):
        return None

    async def update_assessment(self, **kwargs):
        self.assessments.append(kwargs)


class Installer:
    async def inspect_and_install(self, spec, **kwargs):
        assert spec == "plugin-a@1.0.0"
        return {
            "name": "plugin-a", "version": "1.0.0",
            "tool_names": ["plugin_a_tool"],
            "availability": {"status": "session_exposed", "dsh_version": "0.2.2"},
        }


def test_version_change_rechecks_only_stale_enabled_plugin():
    repository = Repository()
    asyncio.run(revalidate_installed_plugins(
        repository=repository, installer=Installer(), transport=Transport(),
    ))
    assert repository.pending == [("plugin-a@1.0.0", "0.2.2")]
    assert len(repository.assessments) == 1
    assert repository.assessments[0]["plugin_id"] == "a" * 24
    assert repository.assessments[0]["availability"]["dsh_version"] == "0.2.2"


def test_existing_active_plugin_without_release_check_is_revalidated():
    row = {"availability": {"dsh_version": "0.2.1-alpha.1", "status": "runtime_active"}}
    assert needs_revalidation(row, "0.2.1-alpha.1")
    row["availability"]["release_compatibility_checked"] = True
    assert not needs_revalidation(row, "0.2.1-alpha.1")


def test_existing_client_module_without_surface_metadata_is_revalidated():
    row = {"availability": {
        "dsh_version": "0.2.1-alpha.1", "status": "runtime_active",
        "release_compatibility_checked": True,
        "capabilities": {"clientModules": [{"id": "plugin", "rev": "one"}]},
    }}
    assert needs_revalidation(row, "0.2.1-alpha.1")
    row["availability"]["capabilities"]["clientModules"][0]["conversationView"] = False
    assert not needs_revalidation(row, "0.2.1-alpha.1")


def test_surface_metadata_refresh_preserves_existing_plugin_availability():
    repository = Repository()
    repository.rows = [{
        "_id": "a" * 24, "main_id": "tenant", "owner_user_id": "", "name": "plugin-a",
        "version": "1.0.0", "spec": "plugin-a@1.0.0",
        "availability": {
            "status": "verified", "reason": "invocation_verified", "dsh_version": "0.2.2",
            "release_compatibility_checked": True,
            "checks": {"package": True, "runtime": True, "session": True, "invocation": True},
            "capabilities": {"clientModules": [{"id": "plugin-a", "rev": "one"}]},
        },
    }]
    assert needs_surface_refresh(repository.rows[0], "0.2.2")

    class SurfaceInstaller:
        async def inspect_and_install(self, spec, **kwargs):
            return {"name": "plugin-a", "version": "1.0.0", "tool_names": ["plugin_a_tool"],
                    "availability": {"status": "runtime_active", "reason": "other_capabilities_available",
                                     "dsh_version": "0.2.2", "capabilities": {"clientModules": [
                                         {"id": "plugin-a", "rev": "one", "conversationView": True}]}}}

    asyncio.run(revalidate_installed_plugins(
        repository=repository, installer=SurfaceInstaller(), transport=Transport(),
    ))
    result = repository.assessments[0]
    assert result["expected_surface_refresh"] is True
    assert result["availability"]["status"] == "verified"
    assert result["availability"]["checks"]["invocation"] is True
    assert result["availability"]["capabilities"]["clientModules"][0]["conversationView"] is True


def test_native_incompatible_version_failure_is_distinct_from_dependency_failure():
    incompatible = failed_assessment(
        PluginInstallError(
            "incompatible-version: plugin requires another DSH release",
            code="incompatible-version", dsh_version="0.2.2",
        ),
        dsh_version="0.2.1", plugin_version="1.0.0",
    )
    assert incompatible["status"] == "version_incompatible"
    assert incompatible["dsh_version"] == "0.2.2"
    assert incompatible["error_code"] == "incompatible-version"
    dependency = failed_assessment(
        PluginInstallError("network timeout", code="network"),
        dsh_version="0.2.2", plugin_version="1.0.0",
    )
    assert dependency["status"] == "failed"


def test_runtime_activation_failure_is_retried_after_cooldown():
    row = {"availability": {
        "dsh_version": "0.2.2", "status": "failed",
        "error_code": "runtime_activation_failed",
    }, "updated_at": datetime.now(timezone.utc)}
    assert not needs_revalidation(row, "0.2.2")
    row["updated_at"] -= timedelta(minutes=6)
    assert needs_revalidation(row, "0.2.2")


def test_runtime_transport_failure_is_retried_after_cooldown():
    row = {"availability": {"dsh_version": "0.2.2", "status": "failed", "reason": "HTTP 404"},
           "updated_at": datetime.now(timezone.utc) - timedelta(minutes=6)}
    assert needs_revalidation(row, "0.2.2")
    row["updated_at"] = row["updated_at"].replace(tzinfo=None)
    assert needs_revalidation(row, "0.2.2")


def test_interrupted_revalidation_is_retried_after_cooldown():
    row = {"availability": {
        "dsh_version": "0.2.2", "status": "failed",
        "error_code": "revalidation_interrupted",
    }, "updated_at": datetime.now(timezone.utc)}
    assert not needs_revalidation(row, "0.2.2")
    row["updated_at"] -= timedelta(minutes=6)
    assert needs_revalidation(row, "0.2.2")


def test_stale_pending_revalidation_is_retried():
    row = {"availability": {
        "dsh_version": "0.2.2", "status": "unverified",
        "reason": "revalidation_in_progress",
        "revalidation_started_at": datetime.now(timezone.utc),
    }}
    assert not needs_revalidation(row, "0.2.2")
    row["availability"]["revalidation_started_at"] -= timedelta(minutes=16)
    assert needs_revalidation(row, "0.2.2")
    row["availability"]["reason"] = "dsh_version_changed"
    assert needs_revalidation(row, "0.2.2")


def test_unexpected_revalidation_error_records_retryable_failure():
    class BrokenInstaller:
        async def inspect_and_install(self, spec, **kwargs):
            raise RuntimeError("temporary runtime failure")

    repository = Repository()
    asyncio.run(revalidate_installed_plugins(
        repository=repository, installer=BrokenInstaller(), transport=Transport(),
    ))
    assert repository.assessments[0]["availability"]["status"] == "failed"
    assert repository.assessments[0]["availability"]["error_code"] == "revalidation_interrupted"


def test_background_result_only_updates_its_pending_claim(monkeypatch):
    captured = {}

    class Collection:
        async def find_one(self, query):
            return {"_id": "a" * 24, "availability": {"status": "unverified"}}

        async def find_one_and_update(self, query, update, **kwargs):
            captured.update(query)
            return None

    class Database:
        dsh_plugin_installations = Collection()

    monkeypatch.setattr(repository_module, "get_db", lambda: Database())
    asyncio.run(repository_module.PluginInstallationRepository().update_assessment(
        main_id="tenant", user_id="", plugin_id="a" * 24,
        availability={"status": "runtime_active", "dsh_version": "0.2.2"},
        tool_names=[], expected_version="1.0.0", expected_spec="plugin@1.0.0",
        expected_pending_target="0.2.2",
    ))
    assert captured["availability.status"] == "unverified"
    assert captured["availability.target_dsh_version"] == "0.2.2"
    assert captured["version"] == "1.0.0"
