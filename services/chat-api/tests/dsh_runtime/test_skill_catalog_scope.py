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
    def find(self, query, projection):
        assert query == {"_id": {"$in": ["package-1"]}, "main_id": "tenant-a"}
        assert projection["files"] == {"$slice": 3}
        return AsyncCursor([{
            "_id": "package-1", "archive_base64": "YXJjaGl2ZQ==", "root_prefix": "foshan/",
            "files": [
                {"path": "SKILL.md", "size": 10},
                {"path": "_meta.json", "size": 10},
                {"path": "assets/contacts.json", "size": 20},
            ],
        }])


class FakeDatabase:
    skill_packages = PackageCollection()


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


def test_preparing_environment_keeps_installed_skill_in_profile(monkeypatch):
    monkeypatch.setattr(catalog_module, "user_skill_service", PersonalService())
    monkeypatch.setattr(catalog_module, "organization_skill_adapter", EmptyOrganizationService())

    class PreparingPersonalService:
        async def list_skills(self, user_id, main_id, *, include_package_files=True):
            return [{"id": "personal-1", "enabled": True, "environment_status": "preparing"}]

    monkeypatch.setattr(catalog_module, "user_skill_service", PreparingPersonalService())
    rows = asyncio.run(catalog_module.MongoSkillCatalog().list_enabled("tenant-a", "user-a"))
    assert [row["id"] for row in rows] == ["personal-1"]


def test_package_resources_are_attached_to_the_runtime_catalog(monkeypatch):
    monkeypatch.setattr(catalog_module, "user_skill_service", PackagePersonalService())
    monkeypatch.setattr(catalog_module, "organization_skill_adapter", EmptyOrganizationService())
    monkeypatch.setattr(catalog_module, "get_db", lambda: FakeDatabase())
    rows = asyncio.run(catalog_module.MongoSkillCatalog().list_enabled("tenant-a", "user-a"))
    assert rows[0]["runtime_bundle_base64"] == "YXJjaGl2ZQ=="
    assert rows[0]["runtime_bundle_root"] == "foshan/"


def test_gridfs_package_is_referenced_without_embedding_archive(monkeypatch):
    class GridPackageCollection:
        def find(self, query, projection):
            assert projection["files"] == {"$slice": 3}
            return AsyncCursor([{
                "_id": "package-1", "archive_gridfs_id": "a" * 32, "root_prefix": "foshan/",
                "files": [{"path": "references/info.txt", "size": 21 * 1024 * 1024}],
            }])

    class GridDatabase:
        skill_packages = GridPackageCollection()

    monkeypatch.setattr(catalog_module, "user_skill_service", PackagePersonalService())
    monkeypatch.setattr(catalog_module, "organization_skill_adapter", EmptyOrganizationService())
    monkeypatch.setattr(catalog_module, "get_db", lambda: GridDatabase())
    rows = asyncio.run(catalog_module.MongoSkillCatalog().list_enabled("tenant-a", "user-a"))
    assert rows[0]["runtime_bundle_archive_id"] == "a" * 32
    assert not rows[0]["runtime_bundle_base64"]
