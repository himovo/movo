from __future__ import annotations

import asyncio

from app.dsh_runtime.profile.skills import catalog as catalog_module


class PersonalService:
    async def list_skills(self, user_id, main_id):
        return [{"id": "personal-1", "name": "Mine", "enabled": True, "visibility": "private"}]


class OrganizationService:
    async def list_runtime_skills(self, *, main_id):
        return [{"id": "org_skill:org-1", "name": "Org", "enabled": True, "visibility": "organization"}]


class DenyOrganizationPolicy:
    def allows_skill(self, skill_id):
        return False


class PolicyResolver:
    async def resolve(self, tenant_id, user_id):
        return DenyOrganizationPolicy()


class PackagePersonalService:
    async def list_skills(self, user_id, main_id):
        return [{
            "id": "personal-package", "name": "Foshan guide", "enabled": True,
            "visibility": "private", "package_id": "package-1",
        }]


class EmptyOrganizationService:
    async def list_runtime_skills(self, *, main_id):
        return []


class AsyncCursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, length):
        return self.rows[:length]


class PackageCollection:
    def find(self, query):
        assert query == {"_id": {"$in": ["package-1"]}, "main_id": "tenant-a"}
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


def test_personal_skill_is_not_filtered_by_organization_position_policy(monkeypatch):
    monkeypatch.setattr(catalog_module, "user_skill_service", PersonalService())
    monkeypatch.setattr(catalog_module, "organization_skill_adapter", OrganizationService())
    rows = asyncio.run(catalog_module.MongoSkillCatalog(PolicyResolver()).list_enabled("tenant-a", "user-a"))
    assert [row["id"] for row in rows] == ["personal-1"]


def test_package_resources_are_attached_to_the_runtime_catalog(monkeypatch):
    monkeypatch.setattr(catalog_module, "user_skill_service", PackagePersonalService())
    monkeypatch.setattr(catalog_module, "organization_skill_adapter", EmptyOrganizationService())
    monkeypatch.setattr(catalog_module, "get_db", lambda: FakeDatabase())
    rows = asyncio.run(catalog_module.MongoSkillCatalog().list_enabled("tenant-a", "user-a"))
    assert rows[0]["runtime_bundle_base64"] == "YXJjaGl2ZQ=="
    assert rows[0]["runtime_bundle_root"] == "foshan/"
