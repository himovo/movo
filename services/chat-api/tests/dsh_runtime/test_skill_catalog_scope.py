from __future__ import annotations

import asyncio

from unittest.mock import AsyncMock

from app.dsh_runtime.profile.skills import catalog as catalog_module


class PersonalService:
    async def list_skills(self, user_id, main_id, *, include_package_files=True):
        assert include_package_files is False
        return [{"id": "personal-1", "name": "Mine", "enabled": True, "visibility": "private"}]


class OrganizationService:
    async def list_runtime_skills(self, *, main_id, include_package_files=True):
        assert include_package_files is False
        return [{"id": "org_skill:org-1", "name": "Org", "enabled": True, "visibility": "organization"}]


class PackagePersonalService:
    async def list_skills(self, user_id, main_id, *, include_package_files=True):
        assert include_package_files is False
        return [{
            "id": "personal-package", "name": "Foshan guide", "enabled": True,
            "visibility": "private", "package_id": "package-1",
        }]


class EmptyOrganizationService:
    async def list_runtime_skills(self, *, main_id, include_package_files=True):
        assert include_package_files is False
        return []


class AsyncCursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, length):
        return self.rows[:length]


class PackageCollection:
    def __init__(self, package, *, requires_execution=False):
        self.package = package
        self.requires_execution = requires_execution
        self.queries = []

    def find(self, query, projection):
        self.queries.append((query, projection))
        expected_scope = {"_id": {"$in": ["package-1"]}, "main_id": "tenant-a"}
        if projection == {"_id": 1}:
            assert query == {
                **expected_scope,
                "files.path": {"$regex": catalog_module.EXECUTABLE_PATH_PATTERN},
            }
            return AsyncCursor([{"_id": "package-1"}] if self.requires_execution else [])
        assert query == expected_scope
        assert projection["files"] == {"$slice": 3}
        return AsyncCursor([self.package])


class FakeDatabase:
    skill_packages = PackageCollection({
        "_id": "package-1", "archive_base64": "YXJjaGl2ZQ==", "root_prefix": "foshan/",
        "files": [
            {"path": "SKILL.md", "size": 10},
            {"path": "_meta.json", "size": 10},
            {"path": "assets/contacts.json", "size": 20},
        ],
    })


def test_personal_skill_is_not_filtered_by_organization_resource_policy(monkeypatch):
    monkeypatch.setattr(catalog_module, "user_skill_service", PersonalService())
    monkeypatch.setattr(catalog_module, "organization_skill_adapter", OrganizationService())
    async def deny_organization(*args, **kwargs):
        return set()
    monkeypatch.setattr(catalog_module, "filter_allowed_resource_ids", deny_organization)
    rows = asyncio.run(catalog_module.MongoSkillCatalog().list_enabled("tenant-a", "user-a"))
    assert [row["id"] for row in rows] == ["personal-1"]


def test_manager_outage_does_not_remove_an_installed_skill_from_profile(monkeypatch):
    monkeypatch.setattr(catalog_module, "user_skill_service", PersonalService())
    monkeypatch.setattr(catalog_module, "organization_skill_adapter", EmptyOrganizationService())

    readiness = AsyncMock(side_effect=RuntimeError("manager unavailable"))
    monkeypatch.setattr(catalog_module, "attach_environment_status", readiness)
    rows = asyncio.run(catalog_module.MongoSkillCatalog().list_enabled("tenant-a", "user-a"))
    assert [row["id"] for row in rows] == ["personal-1"]
    readiness.assert_not_awaited()


def test_preparing_environment_is_excluded_from_runtime_profile(monkeypatch):
    monkeypatch.setattr(catalog_module, "user_skill_service", PersonalService())
    monkeypatch.setattr(catalog_module, "organization_skill_adapter", EmptyOrganizationService())

    class PreparingPersonalService:
        async def list_skills(self, user_id, main_id, *, include_package_files=True):
            return [{"id": "personal-1", "enabled": True, "package_requires_environment": True}]

    monkeypatch.setattr(catalog_module, "user_skill_service", PreparingPersonalService())
    async def preparing(rows):
        rows[0]["environment_status"] = "preparing"
    monkeypatch.setattr(catalog_module, "attach_environment_status", preparing)
    rows = asyncio.run(catalog_module.MongoSkillCatalog().list_enabled("tenant-a", "user-a"))
    assert rows == []


def test_package_resources_are_attached_to_the_runtime_catalog(monkeypatch):
    monkeypatch.setattr(catalog_module, "user_skill_service", PackagePersonalService())
    monkeypatch.setattr(catalog_module, "organization_skill_adapter", EmptyOrganizationService())
    monkeypatch.setattr(catalog_module, "get_db", lambda: FakeDatabase())
    rows = asyncio.run(catalog_module.MongoSkillCatalog().list_enabled("tenant-a", "user-a"))
    assert rows[0]["runtime_bundle_base64"] == "YXJjaGl2ZQ=="
    assert rows[0]["runtime_bundle_root"] == "foshan/"
    assert rows[0]["package_requires_execution"] is False


def test_gridfs_package_is_referenced_without_embedding_archive(monkeypatch):
    class GridDatabase:
        skill_packages = PackageCollection({
            "_id": "package-1", "archive_gridfs_id": "a" * 32, "root_prefix": "foshan/",
            "files": [{"path": "references/info.txt", "size": 21 * 1024 * 1024}],
        })

    monkeypatch.setattr(catalog_module, "user_skill_service", PackagePersonalService())
    monkeypatch.setattr(catalog_module, "organization_skill_adapter", EmptyOrganizationService())
    monkeypatch.setattr(catalog_module, "get_db", lambda: GridDatabase())
    rows = asyncio.run(catalog_module.MongoSkillCatalog().list_enabled("tenant-a", "user-a"))
    assert rows[0]["runtime_bundle_archive_id"] == "a" * 32
    assert not rows[0]["runtime_bundle_base64"]


def test_legacy_executable_package_is_marked_for_execution(monkeypatch):
    class ExecutableDatabase:
        skill_packages = PackageCollection({
            "_id": "package-1", "archive_base64": "YXJjaGl2ZQ==", "root_prefix": "tool/",
            "files": [{"path": "scripts/run.py", "size": 20}],
        }, requires_execution=True)

    monkeypatch.setattr(catalog_module, "user_skill_service", PackagePersonalService())
    monkeypatch.setattr(catalog_module, "organization_skill_adapter", EmptyOrganizationService())
    monkeypatch.setattr(catalog_module, "get_db", lambda: ExecutableDatabase())
    rows = asyncio.run(catalog_module.MongoSkillCatalog().list_enabled("tenant-a", "user-a"))
    assert rows[0]["package_requires_execution"] is True
