import asyncio

import pytest
from fastapi import HTTPException

from app.api.routes import skill_preparation_records as records


class SkillCollection:
    async def find_one(self, query, projection):
        if query["_id"] == "owned" and query["main_id"] == "tenant-a":
            return {"package_digest": "a" * 64, "pending_package": {"digest": "b" * 64}}
        return None


class Database:
    skills = SkillCollection()


def test_preparation_records_are_scoped_to_the_admin_tenant(monkeypatch):
    monkeypatch.setattr(records, "get_db", Database)
    assert asyncio.run(records._skill_build_digests("owned", {"main_id": "tenant-a"})) == ["b" * 64, "a" * 64]
    with pytest.raises(HTTPException) as error:
        asyncio.run(records._skill_build_digests("owned", {"main_id": "tenant-b"}))
    assert error.value.status_code == 404
