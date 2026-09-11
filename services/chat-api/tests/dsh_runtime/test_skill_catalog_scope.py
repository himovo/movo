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


def test_personal_skill_is_not_filtered_by_organization_position_policy(monkeypatch):
    monkeypatch.setattr(catalog_module, "user_skill_service", PersonalService())
    monkeypatch.setattr(catalog_module, "organization_skill_adapter", OrganizationService())
    rows = asyncio.run(catalog_module.MongoSkillCatalog(PolicyResolver()).list_enabled("tenant-a", "user-a"))
    assert [row["id"] for row in rows] == ["personal-1"]
